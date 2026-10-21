"""Disposable real MongoDB/Waitress/native-bridge trace tests; explicit binaries only."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(all(os.environ.get(name) for name in (
    "ALLIANCE_TEST_MONGOD", "ALLIANCE_ACCOUNT_BRIDGE", "ALLIANCE_ACCOUNT_CLIENT")),
    "Requires isolated MongoDB and explicit native verification binaries")
class LoginTraceIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo
        for port in (27018, 18765, 15001):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Integration requires unoccupied isolated ports.")
        cls.temp = tempfile.TemporaryDirectory(prefix="alliance trace integration ")
        cls.scratch = Path(cls.temp.name)
        cls.runtime = cls.scratch / "runtime"
        cls.mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        with redirect_stdout(io.StringIO()):
            initialize(cls.runtime, cls.mongod, admin_username="Operator",
                       admin_password=secrets.token_urlsafe(24))
        cls.settings = Settings.load(cls.runtime)
        cls.database = _start_mongo(cls.runtime, cls.mongod)

    @classmethod
    def tearDownClass(cls):
        from alliance.deployment import _stop_owned
        try:
            _stop_owned(cls.database, cls.runtime)
        finally:
            cls.temp.cleanup()

    def setUp(self):
        self.processes = []
        self.logs = []
        self.addCleanup(self.cleanup_processes)
        self.username = "Trace_" + secrets.token_hex(5)
        self.report = self.scratch / (self.username + ".json")

    def cleanup_processes(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for stream in self.logs:
            stream.close()

    def start_trace(self, *, short_timeout=False):
        arguments = ["--runtime", str(self.runtime), "--username", self.username,
                     "--report", str(self.report)]
        if short_timeout:
            # Test-only clock shortening; the shipped CLI has no timeout override.
            script = ("import sys;sys.path.insert(0," + repr(str(ROOT)) + ");"
                      "from tools import trace_alliance_login as t;"
                      "t.CAPTURE_SECONDS=1;raise SystemExit(t.main(sys.argv[1:]))")
            command = [sys.executable, "-I", "-B", "-c", script, *arguments]
        else:
            command = [sys.executable, "-I", "-B", str(ROOT / "tools/trace_alliance_login.py"),
                       *arguments]
        log = tempfile.TemporaryFile()
        self.logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log)
        self.processes.append(process)
        for _ in range(150):
            self.assertIsNone(process.poll(), "Trace backend exited during startup; raw log withheld.")
            try:
                report = json.loads(self.report.read_text())
                if report["status"] == "armed":
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        else:
            self.fail("Trace readiness timed out.")
        return process, log

    def read_completed(self):
        for _ in range(100):
            try:
                report = json.loads(self.report.read_text())
                if report["status"] == "completed":
                    return report
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        self.fail("Trace report completion timed out.")

    def request(self, path, payload=None, *, secret=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request("http://127.0.0.1:18765" + path, data=data,
            headers={"Authorization": "Bearer " + (secret or self.settings.bridge_secret),
                     "Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def assert_private_material_absent(self, log, *materials):
        log.seek(0)
        output = log.read().decode(errors="replace")
        report = self.report.read_text()
        for value in (self.settings.bridge_secret, self.settings.secret_key,
                      self.settings.mongo_uri, *materials):
            self.assertTrue(value not in output, "Private material in trace output.")
            self.assertTrue(value not in report, "Private material in trace report.")
        self.assertTrue("$argon2" not in output + report, "Hash material in trace output/report.")
        self.assertIn("ALLIANCE LOGIN TRACE READY", output)
        self.assertIn("ALLIANCE LOGIN TRACE COMPLETE", output)

    def test_native_flow_captures_wrong_password_then_serves_successful_login(self):
        from alliance.deployment import _client
        spec = importlib.util.spec_from_file_location("trace_test_identity", ROOT / "tools/alliance_transport.py")
        identity_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity_module)
        identity = self.scratch / (self.username + " identity")
        with redirect_stdout(io.StringIO()):
            identity_module.prepare_identity(identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
        process, log = self.start_trace()
        private_log = tempfile.TemporaryFile()
        self.logs.append(private_log)
        bridge = subprocess.Popen([os.environ["ALLIANCE_ACCOUNT_BRIDGE"], "--runtime", str(self.runtime),
                                   "--identity", str(identity)], stdout=private_log, stderr=private_log)
        self.processes.append(bridge)
        for _ in range(100):
            self.assertIsNone(bridge.poll(), "Native bridge failed to start; raw log withheld.")
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", 15001)) == 0:
                    break
            time.sleep(.1)
        else:
            self.fail("Native bridge readiness timed out.")
        password = " équipe-勇者-" + secrets.token_urlsafe(24) + " "
        result = subprocess.run([os.environ["ALLIANCE_ACCOUNT_CLIENT"], str(identity / "public-profile.json")],
            input=json.dumps({"username": self.username, "password": password}), text=True,
            capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, "Native account flow failed; output withheld.")
        self.assertIn("ALLIANCE ACCOUNT FLOW CHECK PASSED", result.stdout)
        report = self.read_completed()
        self.assertEqual((report["outcome"], report["http_status"]), ("password_mismatch", 401))
        saved = self.report.read_bytes()
        self.assertIsNone(process.poll())
        status, health = self.request("/internal/v1/health")
        self.assertEqual((status, health["status"]), (200, "ok"))
        self.assertEqual(saved, self.report.read_bytes(), "Capture changed after disarming.")
        with _client(self.settings.mongo_uri) as connection:
            db = connection.wesnoth_game
            account = db.accounts.find_one({"username": self.username})
            self.assertIsNotNone(account)
            self.assertEqual(account["leader"]["experience"], 0)
            sessions = list(db.auth_sessions.find({"account_id": account["_id"]}))
            self.assertEqual(len(sessions), 1)
            self.assertTrue(sessions[0]["revoked"])
            self.assert_private_material_absent(log, password, account["password_hash"])

    def test_service_authorization_failure_is_captured_without_auth_writes(self):
        from bson import BSON
        from alliance.deployment import _client
        process, log = self.start_trace()
        with _client(self.settings.mongo_uri) as connection:
            db = connection.wesnoth_game
            def snapshot():
                return {name: sorted(BSON.encode(row) for row in db[name].find({}))
                        for name in ("accounts", "auth_sessions", "auth_attempts")}
            before = snapshot()
            wrong_secret = "bad-service-" + secrets.token_urlsafe(24)
            password = "private-request-" + secrets.token_urlsafe(24)
            status, body = self.request("/internal/v1/login",
                {"username": self.username, "password": password}, secret=wrong_secret)
            self.assertEqual(status, 401)
            self.assertNotIn("service_authorization_rejected", json.dumps(body))
            report = self.read_completed()
            self.assertEqual((report["outcome"], report["http_status"]),
                             ("service_authorization_rejected", 401))
            self.assertEqual(before, snapshot())
        self.assertEqual(self.request("/internal/v1/health")[0], 200)
        self.assertIsNone(process.poll())
        self.assert_private_material_absent(log, wrong_secret, password)

    def test_timeout_disarms_capture_and_keeps_backend_running(self):
        process, log = self.start_trace(short_timeout=True)
        report = self.read_completed()
        self.assertEqual(report["outcome"], "capture_timeout_no_request")
        saved = self.report.read_bytes()
        self.assertIsNone(process.poll())
        self.assertEqual(self.request("/internal/v1/health")[0], 200)
        self.request("/internal/v1/login", {"username": self.username, "password": "dummy invalid password"})
        self.assertEqual(saved, self.report.read_bytes())
        self.assert_private_material_absent(log, "dummy invalid password")

    def test_interrupt_cancels_unfinished_capture_and_releases_backend_port(self):
        process, log = self.start_trace()
        process.send_signal(signal.SIGINT)
        self.assertEqual(process.wait(timeout=12), 0)
        self.assertEqual(self.read_completed()["outcome"], "capture_cancelled")
        with socket.socket() as sock:
            self.assertNotEqual(sock.connect_ex(("127.0.0.1", 18765)), 0)
        self.assertIsNone(self.database.poll(), "Stopping the backend stopped MongoDB.")
        self.assert_private_material_absent(log)


if __name__ == "__main__":
    unittest.main()
