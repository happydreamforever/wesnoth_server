"""Run in the offline verification container; only a disposable loopback server."""
from __future__ import annotations

import contextlib
import http.client
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("backend_check", ROOT / "tools/check_alliance_backend.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
HEALTH = {"status": "ok", "service": "alliance", "api_version": 1,
          "game_bridge_integrated": False, "campaign_content_ready": False}


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BackendCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="alliance backend check ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.config = self.runtime / "config.json"
        self.secret = secrets.token_urlsafe(48)
        self.config.write_text(json.dumps({
            "format": 1, "purpose": "wesnoth-alliance-local",
            "service": {"host": "127.0.0.1", "port": 18765, "bridge_secret": self.secret},
        }))
        self.original_config = self.config.read_bytes()
        self.report = self.root / "report.json"
        self.mode = {"status": 200, "type": "application/json", "body": json.dumps(HEALTH).encode(),
                     "delay": 0, "header": "safe"}
        self.calls = []
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_):
                pass
            def do_GET(self):
                parent.calls.append((self.path, self.headers.get("Authorization")))
                time.sleep(parent.mode["delay"])
                try:
                    self.send_response(parent.mode["status"])
                    self.send_header("Content-Type", parent.mode["type"])
                    self.send_header("Content-Length", str(len(parent.mode["body"])))
                    self.send_header("X-Fixture", parent.mode["header"])
                    if parent.mode["status"] == 302:
                        self.send_header("Location", "http://127.0.0.1:18765/forbidden-redirect")
                    self.end_headers()
                    self.wfile.write(parent.mode["body"])
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = Server(("127.0.0.1", 18765), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None

    def collect(self):
        report = CHECK.collect(self.runtime)
        encoded = json.dumps(report)
        self.assertNotIn(self.secret, encoded)
        self.assertEqual(report["format"], 1)
        self.assertEqual(report["purpose"], "wesnoth-alliance-backend-check")
        self.assertEqual(set(report["checks"]), {"application_json", "status_ok", "service_alliance", "api_v1"})
        self.assertTrue(all(type(item) is bool for item in report["checks"].values()))
        self.assertLess(len(encoded), 2048)
        return report

    def test_real_health_and_cli_report_preserve_runtime(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report)])
        self.assertEqual(code, 0)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["outcome"], "healthy")
        self.assertEqual(report["http_status"], 200)
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(self.calls, [("/internal/v1/health", "Bearer " + self.secret)])
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertEqual(sorted(item.name for item in self.runtime.iterdir()), ["config.json"])
        self.assertNotIn(self.secret, self.report.read_text() + output.getvalue())
        self.assertIn("ALLIANCE BACKEND CHECK PASSED", output.getvalue())

    def test_error_statuses_do_not_parse_or_return_error_bodies(self):
        self.mode.update(body=self.secret.encode(), header=self.secret)
        for status in (401, 404, 500):
            with self.subTest(status=status):
                self.mode["status"] = status
                report = self.collect()
                self.assertEqual(report["http_status"], status)
                self.assertEqual(report["outcome"], "http_rejected")
                self.assertFalse(report["checks"]["status_ok"])

    def test_redirect_is_not_followed(self):
        self.mode["status"] = 302
        report = self.collect()
        self.assertEqual(report["outcome"], "http_rejected")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "/internal/v1/health")

    def test_environment_proxy_is_ignored(self):
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1",
                                          "http_proxy": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}):
            self.assertEqual(self.collect()["outcome"], "healthy")

    def test_no_json_and_large_response_are_rejected(self):
        for updates, outcome in (
                ({"type": "text/html"}, "unexpected_content_type"),
                ({"body": b"x" * 32769}, "response_too_large"),
                ({"header": "x" * 9000}, "response_headers_too_large")):
            with self.subTest(outcome=outcome):
                self.mode.update(type="application/json", body=json.dumps(HEALTH).encode(), header="safe")
                self.mode.update(updates)
                self.assertEqual(self.collect()["outcome"], outcome)

    def test_malformed_or_ambiguous_json_is_rejected(self):
        nested = {"value": "unused"}
        for _ in range(10):
            nested = {"nested": nested}
        samples = [
            b'{"status":', b"\xff",
            b'{"status":"bad","status":"ok","service":"alliance","api_version":1}',
            b'{"status":"ok","service":"alliance","api_version":1,"extra":NaN}',
            json.dumps(dict(HEALTH, extra=nested)).encode(),
        ]
        for raw in samples:
            with self.subTest(raw=raw):
                self.mode["body"] = raw
                self.assertEqual(self.collect()["outcome"], "invalid_json")

    def test_health_values_require_expected_types_and_values(self):
        for update in ({"status": "wrong"}, {"service": "wrong"}, {"api_version": True},
                       {"api_version": 1.0}, {"api_version": "1"}, {"api_version": 2}):
            with self.subTest(update=update):
                self.mode["body"] = json.dumps(dict(HEALTH, **update)).encode()
                report = self.collect()
                self.assertEqual(report["outcome"], "unexpected_health")
                self.assertEqual(report["status"], "failed")

    def test_payload_extra_fields_never_enter_report_or_console(self):
        self.mode.update(body=json.dumps(dict(HEALTH, credential=self.secret)).encode(), header=self.secret)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report)])
        self.assertEqual(code, 0)
        self.assertNotIn(self.secret, self.report.read_text() + output.getvalue())
        self.assertNotIn("credential", self.report.read_text())

    def test_socket_timeout_is_bounded(self):
        self.mode["delay"] = .3
        started = time.monotonic()
        with mock.patch.object(CHECK, "SOCKET_TIMEOUT", .04), mock.patch.object(CHECK, "WORKER_TIMEOUT", .15):
            report = self.collect()
        self.assertEqual(report["outcome"], "timeout")
        self.assertEqual(report["network_error"], "timeout")
        self.assertLess(time.monotonic() - started, .2)

    def test_total_deadline_uses_daemon_not_blocking_executor(self):
        def slow(_):
            time.sleep(.3)
            return CHECK.result("healthy")
        started = time.monotonic()
        with mock.patch.object(CHECK, "request_health", slow), mock.patch.object(CHECK, "WORKER_TIMEOUT", .03):
            report = self.collect()
        self.assertEqual(report["network_error"], "total_deadline")
        self.assertLess(time.monotonic() - started, .2)

    def test_real_connection_refusal_is_safe(self):
        self.stop_server()
        report = self.collect()
        self.assertEqual(report["outcome"], "network_error")
        self.assertEqual(report["network_error"], "connection_refused")

    def test_arbitrary_exception_text_is_never_output(self):
        output = io.StringIO()
        with mock.patch.object(CHECK.http.client.HTTPConnection, "request", side_effect=RuntimeError(self.secret)):
            with contextlib.redirect_stdout(output):
                code = CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report)])
        self.assertEqual(code, 1)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["network_error"], "unexpected_error")
        self.assertNotIn(self.secret, self.report.read_text() + output.getvalue())

    def test_invalid_configuration_never_contacts_backend(self):
        samples = [b'{"private":"' + self.secret.encode(), b"x" * 32769,
                   self.original_config.replace(b"18765", b"18766"),
                   self.original_config.replace(b'"format": 1', b'"format": true'),
                   self.original_config.replace(b'"format": 1', b'"format": 1, "format": 1')]
        for raw in samples:
            with self.subTest(raw_size=len(raw)):
                self.config.write_bytes(raw)
                self.assertEqual(self.collect()["outcome"], "invalid_configuration")
        self.assertEqual(self.calls, [])

    def test_link_and_nonordinary_configuration_are_rejected(self):
        original = self.runtime / "preserved.json"
        self.config.rename(original)
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.config.symlink_to(original)
                elif kind == "hardlink":
                    os.link(original, self.config)
                else:
                    os.mkfifo(self.config)
                try:
                    self.assertEqual(self.collect()["outcome"], "invalid_configuration")
                finally:
                    self.config.unlink()
        self.assertEqual(original.read_bytes(), self.original_config)
        self.assertEqual(self.calls, [])

    def test_existing_report_is_preserved_before_any_request(self):
        self.report.write_text("preserved report")
        output = io.StringIO()
        with mock.patch.object(CHECK, "collect") as collect, contextlib.redirect_stdout(output):
            code = CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report)])
        collect.assert_not_called()
        self.assertEqual(code, 1)
        self.assertEqual(self.report.read_text(), "preserved report")
        self.assertEqual(self.calls, [])

    def test_configuration_metadata_error_is_safe(self):
        with mock.patch.object(Path, "is_symlink", side_effect=OSError(self.secret)):
            self.assertEqual(self.collect()["outcome"], "invalid_configuration")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
