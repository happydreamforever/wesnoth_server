"""Real TLS/native-listener checks against a disposable loopback HTTP backend.

Run inside the pinned native verification container with --network none. These
tests do not assert Windows, Android UI or real MongoDB acceptance.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import gzip
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(os.environ.get("ALLIANCE_ACCOUNT_BRIDGE", ROOT / "build/alliance-bridge-vps/alliance-account-bridge"))
SPEC = importlib.util.spec_from_file_location("bridge_identity", ROOT / "tools/alliance_transport.py")
IDENTITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IDENTITY)
ACCOUNT = {
    "_id": "12345678-1234-1234-1234-123456789abc", "username": "BridgePlayer",
    "password_hash": "must-never-leave-backend", "role": "player",
    "leader": {"starter_id": "spearman", "unit_type": "Spearman", "level": 1,
               "experience": 0, "total_experience": 0, "advancement_choices": []},
}


class Backend(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@unittest.skipUnless(BRIDGE.is_file(), "Build the native account bridge first")
class BridgeIdentityTests(unittest.TestCase):
    """Exercise the Windows PEM newline representation without changing keys."""
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="alliance identity newline ")
        cls.scratch = Path(cls.temporary.name)
        cls.original = cls.scratch / "original-identity"
        with contextlib.redirect_stdout(io.StringIO()):
            cls.profile, _ = IDENTITY.prepare_identity(cls.original, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
        cls.secret = secrets.token_urlsafe(32)
        cls.calls = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_):
                pass
            def do_GET(self):
                if self.headers.get("Authorization") != "Bearer " + cls.secret:
                    self.send_error(401)
                    return
                cls.calls.append(self.path)
                if self.path == "/internal/v1/health":
                    value = {"status": "ok", "service": "alliance", "api_version": 1}
                else:
                    value = {"account": ACCOUNT}
                data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
        cls.backend = Backend(("127.0.0.1", 18765), Handler)
        cls.backend_thread = threading.Thread(target=cls.backend.serve_forever, daemon=True)
        cls.backend_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.backend.shutdown()
        cls.backend.server_close()
        cls.backend_thread.join(timeout=3)
        cls.temporary.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.scratch, prefix="case-"))
        self.identity = self.case / "identity"
        shutil.copytree(self.original, self.identity)
        self.runtime = self.case / "runtime"
        self.runtime.mkdir()
        (self.runtime / "config.json").write_text(json.dumps({
            "format": 1, "purpose": "wesnoth-alliance-local",
            "service": {"host": "127.0.0.1", "port": 18765, "bridge_secret": self.secret},
        }))
        self.process = None
        self.log_path = self.case / "bridge.log"
        self.log = self.log_path.open("wb")
        self.addCleanup(self.log.close)
        self.addCleanup(self.stop_process)

    def stop_process(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def fixture_receipt(self):
        # Model the receipt produced with native Windows OpenSSL output. Only
        # disposable fixture metadata is updated, never a real identity.
        receipt = self.identity / "prepared.json"
        value = json.loads(receipt.read_text())
        value["files"] = {
            name: hashlib.sha256((self.identity / name).read_bytes()).hexdigest()
            for name in IDENTITY.FILES
        }
        receipt.write_text(json.dumps(value))

    def snapshot(self):
        return {
            str(path.relative_to(self.case)): path.read_bytes()
            for root in (self.identity, self.runtime) for path in root.rglob("*") if path.is_file()
        }

    def launch(self, *, accepted, stage=None):
        before = self.snapshot()
        count = len(self.calls)
        self.process = subprocess.Popen(
            [str(BRIDGE), "--runtime", str(self.runtime), "--identity", str(self.identity)],
            stdout=self.log, stderr=subprocess.STDOUT)
        if not accepted:
            self.assertEqual(self.process.wait(timeout=8), 1)
            self.assertNotIn("ALLIANCE ACCOUNT BRIDGE READY", self.log_path.read_text())
            self.assertEqual(len(self.calls), count, "Invalid identity reached the backend")
        else:
            limit = time.monotonic() + 8
            while time.monotonic() < limit:
                if self.process.poll() is not None:
                    self.fail("Valid identity rejected: " + self.log_path.read_text())
                if "ALLIANCE ACCOUNT BRIDGE READY" in self.log_path.read_text():
                    break
                time.sleep(.02)
            else:
                self.fail("Valid identity did not become ready")
            # Confirm actual TLS and a bounded application response, rather
            # than treating a startup marker as certificate acceptance.
            raw = socket.create_connection(("127.0.0.1", 15001), timeout=3)
            raw.sendall(b"\0\0\0\1")
            self.assertEqual(BridgeTests.read_exact(raw, 4), b"\0\0\0\0")
            context = ssl.create_default_context(cadata=self.profile["certificate_pem"])
            with context.wrap_socket(raw, server_hostname="127.0.0.1") as peer:
                value = {"v": 1, "id": "b" * 32, "op": "me", "body": {},
                         "token": secrets.token_urlsafe(32)}
                encoded = gzip.compress(json.dumps(value).encode())
                peer.sendall(struct.pack("!I", len(encoded)) + encoded)
                size, = struct.unpack("!I", BridgeTests.read_exact(peer, 4))
                self.assertLessEqual(size, 65536)
                response = json.loads(gzip.decompress(BridgeTests.read_exact(peer, size)))
                self.assertTrue(response["ok"])
                self.assertEqual(response["data"]["account"]["username"], "BridgePlayer")
            self.stop_process()
        self.assertEqual(self.snapshot(), before, "Identity or runtime files changed")
        output = self.log_path.read_text()
        self.assertNotIn(self.secret, output)
        self.assertNotIn("PRIVATE KEY", output)
        if stage is not None:
            self.assertRegex(output, rf"stage={stage}(?:; error_code=\d+)?\.")

    def test_lf_certificate_still_accepted(self):
        self.assertEqual(IDENTITY.verify_identity(self.identity), self.profile)
        self.launch(accepted=True)

    def test_crlf_certificate_and_key_match_lf_public_profile(self):
        for name in ("server-cert.pem", "server-key.pem"):
            path = self.identity / name
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.fixture_receipt()
        # This is already supported by the identity preparation/verification
        # helper, which canonicalizes the public profile only.
        self.assertEqual(IDENTITY.verify_identity(self.identity), self.profile)
        self.launch(accepted=True)

    def test_certificate_content_mismatch_is_not_hidden_by_normalization(self):
        path = self.identity / "server-cert.pem"
        value = path.read_bytes().replace(b"\n", b"\r\n")
        lines = value.split(b"\r\n")
        lines[1] = (b"A" if lines[1][:1] != b"A" else b"B") + lines[1][1:]
        path.write_bytes(b"\r\n".join(lines))
        self.fixture_receipt()
        self.launch(accepted=False, stage="certificate-profile")

    def test_wrong_certificate_pin_is_rejected(self):
        path = self.identity / "public-profile.json"
        value = json.loads(path.read_text())
        value["certificate_sha256"] = "0" * 64
        path.write_text(json.dumps(value))
        self.fixture_receipt()
        self.launch(accepted=False, stage="certificate-validation")

    def test_bare_carriage_returns_are_not_valid_pem_newlines(self):
        path = self.identity / "server-cert.pem"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r"))
        self.fixture_receipt()
        self.launch(accepted=False, stage="certificate-profile")

    def test_missing_certificate_has_safe_file_stage(self):
        (self.identity / "server-cert.pem").unlink()
        self.launch(accepted=False, stage="certificate-file")

    def test_missing_private_key_has_safe_file_stage(self):
        (self.identity / "server-key.pem").unlink()
        self.launch(accepted=False, stage="private-key-file")

    def test_invalid_private_key_does_not_leak_bytes(self):
        (self.identity / "server-key.pem").write_text(
            "-----BEGIN PRIVATE KEY-----\n" + self.secret + "\n-----END PRIVATE KEY-----\n")
        self.launch(accepted=False, stage="tls-context")

    def test_malformed_runtime_does_not_leak_private_input(self):
        (self.runtime / "config.json").write_text('{"private_input":"' + self.secret)
        self.launch(accepted=False, stage="runtime-config")

    def test_malformed_profile_has_safe_stage(self):
        (self.identity / "public-profile.json").write_text('{"format":')
        self.launch(accepted=False, stage="public-profile")


@unittest.skipUnless(BRIDGE.is_file(), "Build the native account bridge first")
class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="alliance account bridge ")
        cls.scratch = Path(cls.temporary.name)
        cls.runtime = cls.scratch / "runtime"
        cls.runtime.mkdir()
        cls.identity = cls.scratch / "identity"
        cls.secret = secrets.token_urlsafe(32)
        cls.token = secrets.token_urlsafe(32)
        (cls.runtime / "config.json").write_text(json.dumps({
            "format": 1, "purpose": "wesnoth-alliance-local",
            "service": {"host": "127.0.0.1", "port": 18765, "bridge_secret": cls.secret},
        }))
        cls.profile, _ = IDENTITY.prepare_identity(cls.identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
        cls.calls = []
        cls.mode = "normal"
        cls.revoked = False

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.handle_request()
            def do_POST(self):
                self.handle_request()
            def handle_request(self):
                parent = cls
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                parent.calls.append((self.command, self.path, dict(self.headers), raw))
                if self.headers.get("Authorization") != "Bearer " + parent.secret:
                    code, response = 401, {"error": "wrong bridge credential"}
                elif self.path == "/internal/v1/health":
                    code, response = 200, {"status": "ok", "service": "alliance",
                                           "api_version": 2 if parent.mode == "badhealth" else 1}
                elif parent.mode == "outage":
                    code, response = 503, {"error": {"code": "private_config", "message": "must-not-leave-backend"}}
                elif parent.mode == "oversized":
                    code, response = 200, {"secret": "x" * 40000}
                elif self.path in ("/internal/v1/me", "/internal/v1/logout") and (
                        self.headers.get("X-Player-Token") != parent.token or parent.revoked):
                    code, response = 401, {"error": {"code": "invalid_session"}}
                elif self.path == "/internal/v1/register":
                    body = json.loads(raw)
                    if body["username"] == "SlowPlayer":
                        time.sleep(7)
                    code, response = 201, {"account": ACCOUNT}
                elif self.path == "/internal/v1/login":
                    parent.revoked = False
                    code, response = 200, {"token": parent.token, "account": ACCOUNT, "expires_at": "unused"}
                elif self.path == "/internal/v1/me":
                    code, response = 200, {"account": ACCOUNT}
                elif self.path == "/internal/v1/logout":
                    parent.revoked = True
                    code, response = 200, {"status": "logged_out"}
                else:
                    code, response = 404, {}
                payload = json.dumps(response).encode()
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        cls.backend = Backend(("127.0.0.1", 18765), Handler)
        cls.backend_thread = threading.Thread(target=cls.backend.serve_forever, daemon=True)
        cls.backend_thread.start()
        cls.log_path = cls.scratch / "bridge.log"
        cls.log = cls.log_path.open("wb")
        cls.process = subprocess.Popen([str(BRIDGE), "--runtime", str(cls.runtime), "--identity", str(cls.identity)],
                                       stdout=cls.log, stderr=subprocess.STDOUT)
        limit = time.monotonic() + 8
        while time.monotonic() < limit:
            if cls.process.poll() is not None:
                raise AssertionError("Bridge exited before readiness: " + cls.log_path.read_text())
            if "ALLIANCE ACCOUNT BRIDGE READY" in cls.log_path.read_text():
                break
            time.sleep(.02)
        else:
            raise AssertionError("Bridge did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.process.send_signal(signal.SIGTERM)
        cls.process.wait(timeout=5)
        cls.log.close()
        cls.backend.shutdown()
        cls.backend.server_close()
        cls.backend_thread.join(timeout=3)
        cls.temporary.cleanup()

    def setUp(self):
        type(self).mode = "normal"
        type(self).revoked = False

    def connect(self):
        raw = socket.create_connection(("127.0.0.1", 15001), timeout=12)
        raw.sendall(b"\0\0\0\1")
        self.assertEqual(self.read_exact(raw, 4), b"\0\0\0\0")
        context = ssl.create_default_context(cafile=str(self.identity / "server-cert.pem"))
        return context.wrap_socket(raw, server_hostname="127.0.0.1")

    @staticmethod
    def read_exact(peer, size):
        data = b""
        while len(data) < size:
            chunk = peer.recv(size - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        return data

    def request(self, operation="me", body=None, token=None):
        value = {"v": 1, "id": "a" * 32, "op": operation, "body": body or {}}
        if operation in ("me", "logout"):
            value["token"] = token or self.token
        return value

    def exchange(self, value):
        with self.connect() as peer:
            body = gzip.compress(json.dumps(value).encode())
            peer.sendall(struct.pack("!I", len(body)) + body)
            size, = struct.unpack("!I", self.read_exact(peer, 4))
            self.assertLessEqual(size, 65536)
            result = json.loads(gzip.decompress(self.read_exact(peer, size)))
            self.assertEqual(set(result), {"v", "id", "ok", "status", "data"})
            self.assertEqual(result["id"], value["id"])
            return result

    def test_account_cycle_and_response_projection(self):
        credentials = {"username": "BridgePlayer", "password": "example-pass-1234", "starter_id": "spearman"}
        registered = self.exchange(self.request("register", credentials))
        self.assertEqual(registered["status"], 201)
        self.assertTrue(registered["ok"])
        account = registered["data"]["account"]
        self.assertEqual(set(account), {"id", "username", "leader"})
        self.assertEqual(set(account["leader"]), {"starter_id", "unit_type", "level", "experience", "total_experience"})
        self.assertNotIn("password_hash", json.dumps(registered))
        logged_in = self.exchange(self.request("login", {key: credentials[key] for key in ("username", "password")}))
        self.assertEqual(logged_in["data"]["token"], self.token)
        self.assertEqual(self.exchange(self.request())["data"]["account"], account)
        self.assertEqual(self.exchange(self.request("logout"))["data"], {"status": "logged_out"})
        self.assertEqual(self.exchange(self.request())["status"], 401)

    def test_invalid_requests_never_reach_backend(self):
        samples = []
        base = self.request()
        for change in ({"op": "settle"}, {"id": "A" * 32}, {"path": "/internal/v1/runs"},
                       {"body": {"xp": 999}}, {"token": "x\r\nHeader: unsafe"}):
            samples.append(json.dumps(dict(base, **change)).encode())
        samples.append(json.dumps(base).replace('"v": 1', '"v": 1, "v": 1').encode())
        samples.append(json.dumps(base).replace('"v": 1', '"v": 1, "\\u0076": 1').encode())
        samples.append(json.dumps({"v": 1, "id": "a" * 32, "op": "register", "token": self.token,
                                   "body": {"username": "BridgePlayer", "password": "example-pass-1234", "starter_id": "spearman"}}).encode())
        for value in samples:
            with self.subTest(value=value), self.connect() as peer:
                before = len(self.calls)
                body = gzip.compress(value)
                peer.sendall(struct.pack("!I", len(body)) + body)
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)
                self.assertEqual(len(self.calls), before)

    def test_compression_limits_and_trailing_data(self):
        valid = gzip.compress(json.dumps(self.request()).encode())
        for body in (gzip.compress(b"x" * 32769), valid + b"extra", valid + valid, b"not gzip"):
            with self.subTest(size=len(body)), self.connect() as peer:
                before = len(self.calls)
                peer.sendall(struct.pack("!I", len(body)) + body)
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)
                self.assertEqual(len(self.calls), before)
        for size in (0, 65537, 0xffffffff):
            with self.subTest(size=size), self.connect() as peer:
                peer.sendall(struct.pack("!I", size))
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)

    def test_backend_errors_are_safe_and_bounded(self):
        for mode in ("outage", "oversized"):
            type(self).mode = mode
            result = self.exchange(self.request())
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], 503)
            self.assertNotIn("must-not-leave", json.dumps(result))
            self.assertNotIn("private_config", json.dumps(result))

    def test_stalled_backend_does_not_block_other_connection(self):
        slow = self.request("register", {"username": "SlowPlayer", "password": "example-pass-1234", "starter_id": "spearman"})
        started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(self.exchange, slow)
            time.sleep(.15)
            fast_started = time.monotonic()
            self.assertTrue(self.exchange(self.request())["ok"])
            self.assertLess(time.monotonic() - fast_started, 2)
            self.assertEqual(result.result(timeout=8)["status"], 503)
        self.assertGreater(time.monotonic() - started, 5)
        self.assertLess(time.monotonic() - started, 8)

    def test_plaintext_rejected_and_preamble_has_total_deadline(self):
        before = len(self.calls)
        with socket.create_connection(("127.0.0.1", 15001), timeout=12) as peer:
            peer.sendall(b"POST /internal/v1/login")
            try:
                self.assertEqual(peer.recv(4), b"")
            except ConnectionResetError:
                pass
        with socket.create_connection(("127.0.0.1", 15001), timeout=12) as peer:
            start = time.monotonic()
            self.assertEqual(peer.recv(4), b"")
            self.assertGreater(time.monotonic() - start, 9)
            self.assertLess(time.monotonic() - start, 12)
        self.assertEqual(len(self.calls), before)

    def test_second_listener_refused_without_disrupting_first(self):
        result = subprocess.run([str(BRIDGE), "--runtime", str(self.runtime), "--identity", str(self.identity)],
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(self.secret.encode(), result.stdout + result.stderr)
        self.assertRegex(result.stderr, rb"stage=listener-bind; error_code=\d+\.")
        self.assertTrue(self.exchange(self.request())["ok"])

    def test_startup_rejects_incompatible_backend(self):
        type(self).mode = "badhealth"
        result = subprocess.run([str(BRIDGE), "--runtime", str(self.runtime), "--identity", str(self.identity)],
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"ALLIANCE ACCOUNT BRIDGE READY", result.stdout)
        self.assertNotIn(self.secret.encode(), result.stdout + result.stderr)
        self.assertIn(b"stage=backend-health.", result.stderr)

    def test_connection_capacity_recovers_after_peers_close(self):
        peers = []
        try:
            for _ in range(32):
                peer = socket.create_connection(("127.0.0.1", 15001), timeout=2)
                peers.append(peer)
                # Completing the preamble ensures the listener admitted this
                # connection; the unfinished TLS handshake keeps it reserved.
                peer.sendall(b"\0\0\0\1")
                self.assertEqual(self.read_exact(peer, 4), b"\0\0\0\0")
            with socket.create_connection(("127.0.0.1", 15001), timeout=2) as extra:
                self.assertEqual(extra.recv(4), b"")
        finally:
            for peer in peers:
                peer.close()
        time.sleep(.1)
        self.assertTrue(self.exchange(self.request())["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
