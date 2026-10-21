"""Bounded login observation; Mongo cases require an explicit disposable replica set."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
import io
import json
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError
from pymongo import MongoClient
from pymongo.errors import AutoReconnect

from alliance import auth
from alliance.auth import AuthError, AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService
from alliance.schema import bootstrap_schema
from alliance.web import create_app
from tools import trace_alliance_login as tracer


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.console = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.timer = self.stack.enter_context(patch.object(tracer.threading, "Timer"))
        self.output = self.stack.enter_context(tempfile.TemporaryFile(mode="w+", encoding="ascii"))
        self.trace = tracer.LoginTrace(self.output, "UniPlayer")

    def report(self):
        self.output.seek(0)
        return json.load(self.output)

    def test_only_one_concurrent_reservation_and_first_completion(self):
        self.assertIsNone(self.trace.reserve())
        self.trace.arm()
        with ThreadPoolExecutor(max_workers=12) as workers:
            captures = list(workers.map(lambda _: self.trace.reserve(), range(60)))
        selected = [capture for capture in captures if capture is not None]
        self.assertEqual(len(selected), 1)
        selected[0].observe("password_mismatch")
        selected[0].finish(401)
        first = self.report()
        selected[0].observe("login_accepted")
        selected[0].finish(200)
        self.trace.finish("capture_cancelled", None)
        self.assertIsNone(self.trace.reserve())
        self.assertEqual(self.report(), first)
        self.assertEqual(first["outcome"], "password_mismatch")
        self.assertEqual(first["http_status"], 401)

    def test_ready_arms_fixed_window_and_exact_report(self):
        self.assertEqual(self.report()["status"], "starting")
        self.trace.arm()
        self.assertEqual(self.timer.call_args.args[0], 300)
        self.assertEqual(self.report(), {
            "format": 1, "purpose": "wesnoth-alliance-login-trace", "status": "armed",
            "outcome": "waiting_for_login", "username": "UniPlayer", "endpoint": "127.0.0.1:18765",
            "capture_seconds": 300, "http_status": None})
        self.assertIn("ALLIANCE LOGIN TRACE READY", self.console.getvalue())
        self.assertIn("normal login attempt", self.console.getvalue())

    def test_timeout_without_request_disarms(self):
        self.trace.arm()
        self.trace.finish("capture_timeout", None)
        self.assertEqual(self.report()["outcome"], "capture_timeout_no_request")
        self.assertIsNone(self.trace.reserve())

    def test_timeout_during_request_cannot_be_overwritten(self):
        self.trace.arm()
        capture = self.trace.reserve()
        capture.observe("password_mismatch")
        self.trace.finish("capture_timeout", None)
        capture.finish(401)
        self.assertEqual(self.report()["outcome"], "capture_timeout_in_progress")
        self.assertIsNone(self.report()["http_status"])

    def test_delayed_timer_does_not_extend_capture_deadline(self):
        with patch.object(tracer.time, "monotonic", return_value=100):
            self.trace.arm()
        with patch.object(tracer.time, "monotonic", return_value=400):
            self.assertIsNone(self.trace.reserve())
        self.assertEqual(self.report()["outcome"], "capture_timeout_no_request")

    def test_untrusted_outcomes_and_status_cannot_enter_report_or_console(self):
        secret = "private-body-password-hash-token-fingerprint"
        self.trace.arm()
        capture = self.trace.reserve()
        capture.observe(secret)
        capture.observe({"secret": secret})
        capture.finish(secret)
        self.assertEqual(self.report()["outcome"], "request_failed")
        self.assertIsNone(self.report()["http_status"])
        self.assertNotIn(secret, json.dumps(self.report()) + self.console.getvalue())

    def test_write_failure_is_fixed_and_disarms_without_exception(self):
        self.trace.arm()
        capture = self.trace.reserve()
        with patch.object(self.trace, "_write", side_effect=OSError("private-disk-error")):
            capture.finish(200)
        self.assertEqual(self.trace.state, "failed")
        self.assertIsNone(self.trace.reserve())
        self.assertIn("report unavailable", self.console.getvalue())
        self.assertNotIn("private-disk-error", self.console.getvalue())

    def test_cancel_and_startup_failure_are_terminal(self):
        self.trace.startup_failed()
        self.assertEqual(self.report()["outcome"], "startup_failed")
        self.assertIsNone(self.trace.reserve())
        other = tracer.LoginTrace(self.output, "UniPlayer")
        other.arm()
        other.finish("capture_cancelled", None)
        self.assertEqual(self.report()["outcome"], "capture_cancelled")
        other.startup_failed()
        self.assertEqual(self.report()["status"], "completed")

    def test_report_is_exclusive_and_outside_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "runtime"
            runtime.mkdir()
            report = root / "trace.json"
            with tracer.open_report(report, runtime) as output:
                output.write("sentinel")
            with self.assertRaises(FileExistsError):
                tracer.open_report(report, runtime)
            self.assertEqual(report.read_text(), "sentinel")
            with self.assertRaises(ValueError):
                tracer.open_report(runtime / "trace.json", runtime)
            self.assertEqual(list(runtime.iterdir()), [])

    def test_cli_never_reflects_unknown_arguments_or_invalid_username(self):
        private = "private-supplied-argument"
        stderr = io.StringIO()
        with patch.object(tracer.sys, "stderr", stderr), self.assertRaises(SystemExit) as raised:
            tracer.main(["--password", private])
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn(private, stderr.getvalue() + self.console.getvalue())
        self.assertEqual(tracer.main(["--runtime", "/unused", "--report", "/unused/report",
                                      "--username", private + "!"]), 1)
        self.assertNotIn(private, self.console.getvalue())

    def test_diagnostic_launcher_suppresses_exception_logs_and_cancels_on_stop(self):
        private = "private-error-content-never-print"
        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        logger = logging.getLogger("alliance-trace-test")
        logger.addHandler(handler)
        previous_disabled = logging.root.manager.disable
        self.addCleanup(logging.disable, previous_disabled)
        self.addCleanup(logger.removeHandler, handler)
        server = Mock()
        def run():
            try:
                raise RuntimeError(private)
            except RuntimeError:
                logger.exception(private)
            raise KeyboardInterrupt()
        server.run.side_effect = run
        settings = SimpleNamespace(host="127.0.0.1", port=18765, mongo_uri="fixture")
        with patch.object(tracer, "local_settings", return_value=settings), \
                patch.object(tracer, "check_database"), patch.object(tracer, "_client"), \
                patch.object(tracer, "create_app"), patch.object(tracer, "create_server", return_value=server):
            self.assertEqual(tracer.serve(Path("/fixture"), "UniPlayer", self.output), 0)
        self.assertEqual(self.report()["outcome"], "capture_cancelled")
        self.assertEqual(log_output.getvalue(), "")
        self.assertNotIn(private, self.console.getvalue())
        server.close.assert_called_once()
        server.task_dispatcher.shutdown.assert_called_once()


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGO_URI"), "Explicit disposable MongoDB URI required")
class LoginObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ["ALLIANCE_TEST_MONGO_URI"]
        parsed = urlsplit(uri)
        if parsed.scheme != "mongodb" or parsed.hostname != "127.0.0.1":
            raise RuntimeError("Tests require an isolated loopback database.")
        cls.mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        cls.db = cls.mongo["alliance_test_login_trace_" + uuid4().hex]
        bootstrap_schema(cls.db)
        bootstrap_auth_schema(cls.db)
        cls.password = "  équipe-勇者-trace-fixture-password  "
        cls.encoded = hash_password(cls.password)
        cls.settings = SimpleNamespace(host="127.0.0.1", port=18765,
            secret_key="fixture-cookie-" + uuid4().hex, bridge_secret="fixture-bridge-" + uuid4().hex)

    @classmethod
    def tearDownClass(cls):
        cls.mongo.drop_database(cls.db.name)
        cls.mongo.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.console = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(tracer.threading, "Timer"))
        for collection in ("accounts", "auth_attempts", "auth_sessions"):
            self.db[collection].delete_many({})
        self.player = AllianceService(self.db).register("UniPlayer", self.encoded)
        self.auth = AuthService(self.db)
        self.observed = []
        self.headers = {"Authorization": "Bearer " + self.settings.bridge_secret}
        self.outputs = []

    def capture_client(self, *, observer=None):
        output = self.stack.enter_context(tempfile.TemporaryFile(mode="w+", encoding="ascii"))
        self.outputs.append(output)
        trace = tracer.LoginTrace(output, "UniPlayer")
        trace.arm()
        app = create_app(self.settings, self.db, login_observer=observer or trace, login_username="UniPlayer")
        return app.test_client(), trace, output

    def report(self, output):
        output.seek(0)
        return json.load(output)

    def login(self, client, *, username="UniPlayer", password=None, headers=None):
        return client.post("/internal/v1/login", json={"username": username,
            "password": self.password if password is None else password},
            headers=self.headers if headers is None else headers)

    def assert_failure(self, username, password, outcome, code="invalid_credentials"):
        with self.assertRaises(AuthError) as raised:
            self.auth.authenticate(username, password, "player", observer=self.observed.append)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.observed[-1], outcome)
        self.assertEqual(self.db.auth_sessions.count_documents({}), 0)

    def test_real_password_outcomes_and_casefold_success(self):
        self.assert_failure("UniPlayer", "wrong-password", "password_mismatch")
        self.assert_failure("NoSuchPlayer", self.password, "account_missing")
        result = self.auth.authenticate("UNIPLAYER", self.password, "player", observer=self.observed.append)
        self.assertEqual(self.observed[-1], "login_accepted")
        self.assertEqual(self.auth.validate_token(result["token"], "player")["_id"], self.player["_id"])
        self.assertEqual(self.db.auth_sessions.count_documents({}), 1)
        # Success deletes only its own existing bucket, exactly as ordinary login.
        self.assertEqual(self.db.auth_attempts.count_documents({}), 1)
        self.assertNotIn(self.password, repr(self.observed))
        self.assertNotIn(self.encoded, repr(self.observed))

    def test_invalid_input_and_rate_limit_preserve_attempt_rules(self):
        self.assert_failure("UniPlayer", "x" * 129, "invalid_input")
        self.assertEqual(self.db.auth_attempts.count_documents({}), 0)
        self.assert_failure("UniPlayer", "wrong-password", "password_mismatch")
        self.db.auth_attempts.update_many({}, {"$set": {"count": 10}})
        with patch.object(auth, "_HASHER", wraps=auth._HASHER) as hasher:
            self.assert_failure("UniPlayer", self.password, "rate_limited", "rate_limited")
            hasher.verify.assert_not_called()
        self.assertEqual(self.db.auth_attempts.find_one()["count"], 11)

    def test_corrupt_hash_and_verification_error_are_not_password_mismatch(self):
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"password_hash": "corrupt-hash"}})
        self.assert_failure("UniPlayer", self.password, "invalid_stored_hash")
        with patch.object(auth, "_HASHER", wraps=auth._HASHER) as hasher:
            hasher.verify.side_effect = VerificationError("private-argon-error")
            self.assert_failure("UniPlayer", self.password, "password_verification_failed")
        self.assertNotIn("private-argon-error", repr(self.observed))

    def test_ineligible_status_and_scope_remain_generic(self):
        for change in ({"status": "suspended", "role": "player"}, {"status": "active", "role": "admin"}):
            with self.subTest(change=change):
                self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": change})
                self.assert_failure("UniPlayer", self.password, "account_ineligible")

    def test_session_state_race_still_rejects_without_session(self):
        original = auth._HASHER.verify
        def suspend(encoded, password):
            verified = original(encoded, password)
            self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"status": "suspended"}})
            return verified
        with patch.object(auth, "_HASHER", wraps=auth._HASHER) as hasher:
            hasher.verify.side_effect = suspend
            self.assert_failure("UniPlayer", self.password, "session_state_changed")

    def test_observer_exception_cannot_change_success_or_failure(self):
        observer = Mock(side_effect=KeyboardInterrupt("private-observer-error"))
        with self.assertRaises(AuthError) as raised:
            self.auth.authenticate("UniPlayer", "wrong-password", "player", observer=observer)
        self.assertEqual(raised.exception.code, "invalid_credentials")
        self.assertEqual(self.db.auth_attempts.find_one()["count"], 1)
        result = self.auth.authenticate("UniPlayer", self.password, "player", observer=observer)
        self.assertEqual(self.auth.validate_token(result["token"], "player")["_id"], self.player["_id"])
        self.assertEqual(self.db.auth_attempts.count_documents({}), 0)
        self.assertEqual(self.db.auth_sessions.count_documents({}), 1)
        self.assertEqual(self.db.accounts.find_one()["revision"], self.player["revision"] + 1)

    def test_normal_rehash_write_is_preserved(self):
        old = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1, type=Type.ID).hash(self.password)
        self.db.accounts.update_one({"_id": self.player["_id"]}, {"$set": {"password_hash": old}})
        self.auth.authenticate("UniPlayer", self.password, "player", observer=self.observed.append)
        updated = self.db.accounts.find_one()["password_hash"]
        self.assertNotEqual(updated, old)
        self.assertTrue(auth._HASHER.verify(updated, self.password))
        self.assertFalse(auth._HASHER.check_needs_rehash(updated))
        self.assertEqual(self.observed, ["login_accepted"])

    def test_wrong_service_credential_captures_once_without_auth_write(self):
        client, trace, output = self.capture_client()
        self.assertEqual(self.login(client, headers={}).status_code, 401)
        first = self.report(output)
        self.assertEqual(first["outcome"], "service_authorization_rejected")
        self.assertEqual(self.db.auth_attempts.count_documents({}), 0)
        self.assertEqual(self.db.auth_sessions.count_documents({}), 0)
        self.assertEqual(self.login(client).status_code, 200)
        self.assertEqual(self.report(output), first)
        self.assertIsNone(trace.reserve())
        self.assertEqual(self.db.auth_sessions.count_documents({}), 1)

    def test_different_username_normal_login_unchanged_and_not_recorded(self):
        other_name = "PrivateOtherPlayer"
        AllianceService(self.db).register(other_name, self.encoded)
        client, _, output = self.capture_client()
        response = self.login(client, username=other_name)
        self.assertEqual(response.status_code, 200)
        report = self.report(output)
        self.assertEqual(report["outcome"], "different_username")
        self.assertEqual(report["username"], "UniPlayer")
        self.assertNotIn(other_name, json.dumps(report) + self.console.getvalue())
        self.assertNotIn(response.json["token"], json.dumps(report) + self.console.getvalue())

    def test_http_observer_failures_preserve_public_responses(self):
        normal = create_app(self.settings, self.db).test_client()
        baseline = self.login(normal, password="wrong-password")
        for failure in ("reserve", "observe", "finish"):
            with self.subTest(failure=failure):
                capture = SimpleNamespace(observe=Mock(), finish=Mock())
                observer = SimpleNamespace(reserve=Mock(return_value=capture))
                target = observer if failure == "reserve" else capture
                getattr(target, failure).side_effect = RuntimeError("private-callback-error")
                client = create_app(self.settings, self.db, login_observer=observer,
                                    login_username="UniPlayer").test_client()
                response = self.login(client, password="wrong-password")
                self.assertEqual((response.status_code, response.json), (baseline.status_code, baseline.json))
                self.assertEqual(self.login(client).status_code, 200)
        self.assertNotIn("private-callback-error", self.console.getvalue())

    def test_report_failure_cannot_fail_real_login(self):
        client, trace, _ = self.capture_client()
        with patch.object(trace, "_write", side_effect=OSError("private-report-error")):
            response = self.login(client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.auth_sessions.count_documents({}), 1)
        self.assertEqual(trace.state, "failed")
        self.assertNotIn("private-report-error", self.console.getvalue())

    def test_malformed_request_fixed_report_and_other_routes_do_not_capture(self):
        client, _, output = self.capture_client()
        self.assertEqual(client.get("/internal/v1/health", headers=self.headers).status_code, 200)
        self.assertEqual(client.get("/internal/v1/login", headers=self.headers).status_code, 405)
        self.assertEqual(self.report(output)["status"], "armed")
        response = client.post("/internal/v1/login", data="private-broken-json",
                               content_type="application/json", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.report(output)["outcome"], "request_rejected")
        self.assertEqual(self.db.auth_attempts.count_documents({}), 0)
        self.assertNotIn("private-broken-json", json.dumps(self.report(output)) + self.console.getvalue())

    def test_database_and_unexpected_error_fixed_fallbacks(self):
        for error, status, outcome in ((AutoReconnect("private-db-error"), 503, "backend_unavailable"),
                                       (RuntimeError("private-body-error"), 500, "backend_error")):
            with self.subTest(outcome=outcome):
                client, _, output = self.capture_client()
                with patch.object(AuthService, "authenticate", side_effect=error):
                    response = self.login(client)
                self.assertEqual(response.status_code, status)
                self.assertEqual(self.report(output)["outcome"], outcome)
                rendered = json.dumps(self.report(output)) + self.console.getvalue() + response.get_data(as_text=True)
                self.assertNotIn(str(error), rendered)


if __name__ == "__main__":
    unittest.main()
