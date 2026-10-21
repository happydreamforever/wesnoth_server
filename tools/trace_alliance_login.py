"""Serve the existing local backend and capture one sanitized login outcome for 300 seconds."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.check_alliance_login import SafeParser, USERNAME, local_settings
from alliance.deployment import check_database, _client
from alliance.web import create_app
from waitress import create_server

CAPTURE_SECONDS = 300
OUTCOMES = frozenset({"service_authorization_rejected", "different_username", "invalid_input",
    "account_missing", "invalid_stored_hash", "password_mismatch", "password_verification_failed",
    "account_ineligible", "session_state_changed", "rate_limited", "login_accepted",
    "backend_unavailable", "backend_error", "request_rejected", "request_failed",
    "authorization_or_credentials_rejected", "capture_timeout_no_request",
    "capture_timeout_in_progress", "capture_cancelled"})


def initial_report(username):
    return {"format": 1, "purpose": "wesnoth-alliance-login-trace", "status": "starting",
            "outcome": "not_started", "username": username, "endpoint": "127.0.0.1:18765",
            "capture_seconds": CAPTURE_SECONDS, "http_status": None}


class LoginCapture:
    def __init__(self, trace):
        self.trace = trace
        self.outcome = None

    def observe(self, outcome):
        # Do not retain anything supplied by callbacks outside the fixed enum.
        if isinstance(outcome, str) and outcome in OUTCOMES:
            with self.trace.lock:
                if self.trace.state == "reserved":
                    self.outcome = outcome

    def finish(self, status):
        if type(status) is not int or not 100 <= status <= 599:
            status = None
        fallback = ("login_accepted" if status == 200 else "rate_limited" if status == 429 else
                    "authorization_or_credentials_rejected" if status == 401 else
                    "backend_unavailable" if status == 503 else "backend_error" if status == 500 else
                    "request_rejected" if status in (400, 403, 404, 405, 413, 415) else "request_failed")
        self.trace.finish(self.outcome or fallback, status, reserved_only=True)


class LoginTrace:
    """Thread-safe reservation and fixed report; no request object or credential is retained."""
    def __init__(self, output, username):
        self.output = output
        self.report = initial_report(username)
        self.state = "starting"
        self.lock = threading.Lock()
        self.timer = None
        self.deadline = None
        self._write()

    def _write(self):
        self.output.seek(0)
        json.dump(self.report, self.output, indent=2, ensure_ascii=True)
        self.output.write("\n")
        self.output.truncate()
        self.output.flush()
        os.fsync(self.output.fileno())

    def arm(self):
        with self.lock:
            self.report.update(status="armed", outcome="waiting_for_login")
            self._write()
            self.state = "armed"
            self.deadline = time.monotonic() + CAPTURE_SECONDS
            self.timer = threading.Timer(CAPTURE_SECONDS, self.finish, args=("capture_timeout", None))
            self.timer.daemon = True
            self.timer.start()
        print("ALLIANCE LOGIN TRACE READY", flush=True)
        print("Capture one Android login within 300 seconds. The backend keeps serving after capture or timeout.", flush=True)
        print("This is a normal login attempt: its usual attempt/session/password-rehash writes may occur.", flush=True)

    def reserve(self):
        with self.lock:
            if self.state != "armed":
                return None
            if time.monotonic() < self.deadline:
                self.state = "reserved"
                return LoginCapture(self)
        # The timer thread may be delayed. Never capture a request after its
        # deadline even when that thread has not yet written the timeout report.
        self.finish("capture_timeout", None)
        return None

    def finish(self, outcome, status, *, reserved_only=False):
        with self.lock:
            allowed = ("reserved",) if reserved_only else ("armed", "reserved")
            if self.state not in allowed:
                return
            if outcome == "capture_timeout":
                outcome = "capture_timeout_in_progress" if self.state == "reserved" else "capture_timeout_no_request"
            if not isinstance(outcome, str) or outcome not in OUTCOMES:
                outcome = "request_failed"
            if type(status) is not int or not 100 <= status <= 599:
                status = None
            self.state = "completed"
            if self.timer is not None:
                self.timer.cancel()
            self.report.update(status="completed", outcome=outcome, http_status=status)
            try:
                self._write()
            except BaseException:
                self.state = "failed"
                print("ALLIANCE LOGIN TRACE FAILED: report unavailable; backend remains running.", flush=True)
                return
        print("ALLIANCE LOGIN TRACE COMPLETE: outcome=" + outcome + "; http_status=" + str(status), flush=True)
        print("The diagnostic capture is disarmed. Keep this backend window open.", flush=True)

    def startup_failed(self):
        with self.lock:
            if self.state in ("completed", "failed"):
                return
            self.state = "failed"
            if self.timer is not None:
                self.timer.cancel()
            self.report.update(status="failed", outcome="startup_failed", http_status=None)
            try:
                self._write()
            except BaseException:
                pass


def open_report(path, runtime):
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError()
    for parent in path.parents:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError()
    if path.resolve().is_relative_to(runtime.resolve()):
        raise ValueError()
    return path.open("x+", encoding="ascii", newline="\n")


def serve(runtime, username, output):
    # Diagnostic process only: third-party exception/HTTP log formatting can
    # reflect private request material. Fixed print markers below remain available.
    logging.disable(sys.maxsize)
    trace = LoginTrace(output, username)
    server = None
    try:
        settings = local_settings(runtime)
        check_database(runtime)
        with _client(settings.mongo_uri) as client:
            app = create_app(settings, client.wesnoth_game, login_observer=trace, login_username=username)
            # create_server binds first. The capture window begins only after binding succeeds.
            server = create_server(app, host=settings.host, port=settings.port, threads=4,
                                   max_request_body_size=65536, channel_timeout=30,
                                   clear_untrusted_proxy_headers=True)
            print("Alliance admin: http://127.0.0.1:18765/", flush=True)
            trace.arm()
            try:
                server.run()
            except KeyboardInterrupt:
                pass
            trace.finish("capture_cancelled", None)
        return 0
    except KeyboardInterrupt:
        trace.startup_failed()
        print("ALLIANCE LOGIN TRACE FAILED: startup interrupted; existing runtime preserved.", flush=True)
        return 1
    except BaseException:
        trace.startup_failed()
        print("ALLIANCE LOGIN TRACE FAILED: backend could not start or continue; existing runtime preserved.", flush=True)
        return 1
    finally:
        if server is not None:
            try:
                server.close()
                server.task_dispatcher.shutdown()
            except BaseException:
                pass


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if not USERNAME.fullmatch(args.username):
        print("ALLIANCE LOGIN TRACE FAILED: invalid selected username.")
        return 1
    try:
        with open_report(args.report, args.runtime) as output:
            return serve(args.runtime, args.username, output)
    except BaseException:
        print("ALLIANCE LOGIN TRACE FAILED: report unavailable; existing files preserved.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
