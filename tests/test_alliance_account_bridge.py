"""Real TLS/native-listener checks against a disposable loopback HTTP backend.

Run inside the pinned native verification container with --network none. These
tests do not assert Windows, Android UI or real MongoDB acceptance.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
from copy import deepcopy
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
    "database_generation": "12345678-1234-1234-1234-123456789abd", "heroes": [],
}
TEAM = {
    "id": "22345678-1234-1234-1234-123456789abc", "name": "Lantern Guard",
    "area_id": "area-1", "area_name": "Area 1", "captain_id": ACCOUNT["_id"],
    "level": 1, "experience": 0, "rating": 1000, "capacity": 8,
    "members": [{"id": ACCOUNT["_id"], "username": ACCOUNT["username"],
                 "hero_count": 0}],
}
TEAM_SUMMARY = {key: TEAM[key] for key in
                ("id", "name", "area_id", "captain_id", "level", "experience", "rating")}
TEAM_SUMMARY["member_count"] = 1
DECISION = {'id': '32345678-1234-1234-1234-123456789abc', 'team_id': TEAM['id'],
    'team_name': TEAM['name'], 'status': 'rejected', 'created_at': '2026-10-21T12:34:56Z', 'unread': True}
BATTLE_MAP = {'id': 'isars-cross', 'name': "Isar's Cross", 'scenario_id': 'multiplayer_Isars_Cross',
              'size': 2, 'sides': [[1, 4], [2, 3]]}
BATTLE = {'id': '82345678-1234-1234-1234-123456789abc', 'area_id': 'area-1', 'state': 'draft',
    'created_at': '2026-10-21T12:34:56Z', 'map': BATTLE_MAP, 'validity': 'valid', 'teams': []}
for index, (team_id, name, ids) in enumerate((
    (TEAM['id'], TEAM['name'], [ACCOUNT['_id'], '52345678-1234-1234-1234-123456789abc']),
    ('42345678-1234-1234-1234-123456789abc', 'Opposing Team',
     ['62345678-1234-1234-1234-123456789abc', '72345678-1234-1234-1234-123456789abc']))):
    BATTLE['teams'].append({'id': team_id, 'name': name, 'captain_id': ids[0], 'approved': False,
        'players': [{'id': identifier, 'username': 'Player_' + str(side), 'selection': None, 'side': side, 'ready': False}
                    for identifier, side in zip(ids, BATTLE_MAP['sides'][index])]})
BATTLE_PROPOSAL = {'team_id': BATTLE['teams'][0]['id'], 'opponent_team_id': BATTLE['teams'][1]['id'],
    'map_id': BATTLE_MAP['id'], 'lineups': [{'team_id': team['id'], 'account_ids': [p['id'] for p in team['players']]}
                                         for team in BATTLE['teams']]}
BATTLE_SUMMARY = {key: BATTLE[key] for key in ('id', 'area_id', 'state', 'created_at')}
BATTLE_SUMMARY.update(map_id=BATTLE_MAP['id'], teams=[{key: team[key] for key in ('id', 'name')} for team in BATTLE['teams']])


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
                    value = {"status": "ok", "service": "alliance", "api_version": 1, "product_schema_version": 4, "implementation_release": 1192624}
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
                value = {"v": 4, "id": "b" * 32, "op": "me", "body": {},
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
                                           "api_version": 2 if parent.mode == "badhealth" else 1, "product_schema_version": 4, "implementation_release": 1192624}
                elif parent.mode == "outage":
                    code, response = 503, {"error": {"code": "private_config", "message": "must-not-leave-backend"}}
                elif parent.mode == "oversized":
                    code, response = 200, {"secret": "x" * 40000}
                elif self.path in ("/internal/v1/me", "/internal/v1/logout") and (
                        self.headers.get("X-Player-Token") != parent.token or parent.revoked):
                    code, response = 401, {"error": {"code": "invalid_session"}}
                elif self.path.startswith(("/internal/v1/team-directory/", "/internal/v1/progression/", "/internal/v1/coordination/", "/internal/v1/shared/", "/internal/v1/world/")):
                    if self.headers.get("X-Player-Token") != parent.token or parent.revoked:
                        code, response = 401, {"error": {"code": "invalid_session"}}
                    elif parent.directory_override is not None:
                        code, response = parent.directory_override
                    else:
                        operation = self.path.rsplit("/", 1)[1]
                        if operation == "areas":
                            code, response = 200, {"areas": [{"id": "area-1", "name": "Area 1"}], "next": ""}
                        elif operation == "teams":
                            code, response = 200, {"teams": [TEAM_SUMMARY], "next": ""}
                        elif operation == "my_applications":
                            code, response = 200, {"teams": [TEAM_SUMMARY] if parent.application_pending else [], "next": ""}
                        elif operation == "team_applicants":
                            code, response = 200, {"team_id": TEAM['id'],
                                "applicants": TEAM['members'] if parent.application_pending else [], "next": ""}
                        elif operation == 'application_decisions':
                            code, response = 200, {'decisions': parent.decisions}
                        elif operation == 'ack_decision':
                            decision_id = json.loads(raw)['decision_id']
                            matched = next((item for item in parent.decisions if item['id'] == decision_id), None)
                            if matched is None:
                                code, response = 404, {'error': {'code': 'not_found'}}
                            else:
                                matched['unread'] = False
                                code, response = 200, {'decision_id': decision_id, 'status': 'read'}
                                if parent.mode == 'decision_uncertain':
                                    code, response = 503, {'error': {'code': 'private_error', 'message': parent.secret}}
                        elif operation in ("apply_team", "withdraw_application", "approve_application", "reject_application"):
                            body = json.loads(raw)
                            parent.application_pending = operation == "apply_team"
                            code, response = 200, {"team_id": body['team_id'],
                                "account_id": body.get('account_id', ACCOUNT['_id']),
                                "status": {'apply_team': 'applied', 'withdraw_application': 'withdrawn',
                                    'approve_application': 'approved', 'reject_application': 'rejected'}[operation]}
                            if parent.mode == 'application_uncertain':
                                code, response = 503, {'error': {'code': 'private_error', 'message': parent.secret}}
                        elif operation == "create_team":
                            parent.directory_created = True
                            if parent.mode == "directory_uncertain":
                                code, response = 503, {"error": {"code": "private_error", "message": parent.secret}}
                            else:
                                code, response = 201, {"team": TEAM}
                        elif operation == "team_detail" or parent.directory_created:
                            code, response = 200, {"team": TEAM}
                        else:
                            code, response = 200, {"team": None}
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
        type(self).directory_override = None
        type(self).directory_created = False
        type(self).application_pending = False
        type(self).decisions = []

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
        value = {"v": 4, "id": "a" * 32, "op": operation, "body": body or {}}
        if operation in ("me", "logout", "areas", "teams", "my_team", "create_team", "team_detail",
                         "my_applications", "team_applicants", "apply_team", "withdraw_application",
                         "approve_application", "reject_application", "application_decisions", "ack_decision",
                         "leave_team", "transfer_captain", "standings", "battle_maps", "my_battles",
                         "battle_detail", "propose_battle", "approve_battle", "battle_ready", "cancel_battle",
                         "progression_catalog", "progression_start", "progression_status", "progression_finish",
                         "progression_cancel", "progression_advance", "progression_history",
                         "coordination_orders", "coordination_post", "shared_review", "shared_confirm", "world_query", "world_command"):
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

    def test_health_has_current_release_without_credentials_or_backend_calls(self):
        before = len(self.calls)
        with self.connect() as peer:
            body = gzip.compress(b'[alliance_health]\n[/alliance_health]\n')
            peer.sendall(struct.pack('!I', len(body)) + body)
            size, = struct.unpack('!I', self.read_exact(peer, 4))
            result = gzip.decompress(self.read_exact(peer, size)).decode()
            self.assertEqual(result, '[alliance_health]\nservice="alliance-accounts"\napi="4"\nimplementation_release="1192624"\n[/alliance_health]\n')
        self.assertEqual(len(self.calls), before)
        for request in (b'[alliance_health]\ntoken="secret"\n[/alliance_health]\n',
                        b'[alliance_health]\n[/alliance_health]\n[login]\n[/login]\n'):
            with self.connect() as peer:
                body = gzip.compress(request)
                peer.sendall(struct.pack('!I', len(body)) + body)
                self.assertEqual(peer.recv(4), b'')
        self.assertEqual(len(self.calls), before)

    def test_account_cycle_and_response_projection(self):
        credentials = {"username": "BridgePlayer", "password": "example-pass-1234"}
        registered = self.exchange(self.request("register", credentials))
        self.assertEqual(registered["status"], 201)
        self.assertTrue(registered["ok"])
        account = registered["data"]["account"]
        self.assertEqual(set(account), {"id", "username", "database_generation", "heroes"})
        self.assertEqual(account["heroes"], [])
        self.assertNotIn("password_hash", json.dumps(registered))
        logged_in = self.exchange(self.request("login", {key: credentials[key] for key in ("username", "password")}))
        self.assertEqual(logged_in["data"]["token"], self.token)
        self.assertEqual(self.exchange(self.request())["data"]["account"], account)
        self.assertEqual(self.exchange(self.request("logout"))["data"], {"status": "logged_out"})
        self.assertEqual(self.exchange(self.request())["status"], 401)

    def test_protocol2_receives_upgrade_rejection_without_backend_dispatch(self):
        before = len(self.calls)
        password = 'old-client-private-password'
        requests = [self.request('login', {'username': 'BridgePlayer', 'password': password}),
                    self.request('register', {'username': 'BridgePlayer', 'password': password}),
                    self.request('battle_ready', {'battle_id': BATTLE['id'], 'ready': True}),
                    self.request('logout')]
        for value in requests:
            value['v'] = 2
            reply = self.exchange(value)
            self.assertEqual(reply, {'v': 2, 'id': value['id'], 'ok': False, 'status': 426,
                'data': {'code': 'protocol', 'message': 'Update the game to release 1192624 before connecting to this server.'}})
        self.assertEqual(len(self.calls), before)
        self.assertFalse(type(self).revoked)
        log = self.log_path.read_text()
        self.assertIn('ALLIANCE ACCOUNT CLIENT UPDATE REQUIRED protocol=2 required_protocol=4 implementation_release=1192624', log)
        for private in (password, self.token, self.secret):
            self.assertNotIn(private, log)
        # This rejection is not a compatibility parser for malformed/unknown
        # envelopes, and must not weaken the current protocol validation.
        for change in ({'v': 1}, {'v': 5}, {'v': '2'}, {'id': 'A'*32},
                       {'body': []}, {'op': 'unsafe\noperation'}, {'token': 'invalid'}, {'extra': True}):
            malformed = dict(requests[0], **change)
            with self.subTest(change=change), self.connect() as peer:
                body = gzip.compress(json.dumps(malformed).encode())
                peer.sendall(struct.pack('!I', len(body))+body)
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)
        self.assertEqual(len(self.calls), before)

    def test_protocol3_is_rejected_before_dispatch(self):
        before=len(self.calls)
        value=self.request('me');value['v']=3
        reply=self.exchange(value)
        self.assertEqual(reply['v'],3);self.assertEqual(reply['status'],426)
        self.assertEqual(len(self.calls),before)

    def test_world_envelope_scopes_actor_and_forbids_reward_and_host_commands(self):
        envelope={'version':1,'balance_revision':'world-company-1',
                  'database_generation':ACCOUNT['database_generation'],'actor_id':ACCOUNT['_id'],
                  'data':{'company':None,'available':False}}
        type(self).directory_override=(200,envelope)
        request=self.request('world_query',{'operation':'company','payload':{}})
        reply=self.exchange(request)
        self.assertTrue(reply['ok']);self.assertEqual(reply['data'],envelope)
        self.assertEqual(self.calls[-1][1],'/internal/v1/world/query')
        self.assertEqual(self.calls[-1][2]['X-Player-Token'],self.token)
        self.assertEqual(json.loads(self.calls[-1][3]),request['body'])
        for operation,payload in [('worker_settle',{}),('bootstrap',{}),('company_initialize',{'earned_xp':500}),
                ('battle_ready',{'run_id':BATTLE['id'],'ready':True,'actor_id':ACCOUNT['_id']})]:
            before=len(self.calls)
            value=self.request('world_command',{'operation':operation,'payload':dict(payload,command_id=ACCOUNT['_id'])})
            with self.subTest(operation=operation),self.connect() as peer:
                body=gzip.compress(json.dumps(value).encode());peer.sendall(struct.pack('!I',len(body))+body)
                with self.assertRaises((EOFError,ssl.SSLError,ConnectionError)):self.read_exact(peer,4)
            self.assertEqual(len(self.calls),before)
        type(self).directory_override=(409,{'error':{'code':'force_review','message':'PRIVATE arbitrary server text'}})
        rejected=self.exchange(self.request('world_command',{'operation':'company_initialize','payload':{'command_id':ACCOUNT['_id']}}))
        self.assertFalse(rejected['ok']);self.assertEqual(rejected['data']['code'],'force_review')
        self.assertNotIn('PRIVATE',json.dumps(rejected))

    def test_invalid_requests_never_reach_backend(self):
        samples = []
        base = self.request()
        for change in ({"op": "settle"}, {"id": "A" * 32}, {"path": "/internal/v1/runs"},
                       {"body": {"xp": 999}}, {"token": "x\r\nHeader: unsafe"}):
            samples.append(json.dumps(dict(base, **change)).encode())
        samples.append(json.dumps(base).replace('"v": 4', '"v": 4, "v": 4').encode())
        samples.append(json.dumps(base).replace('"v": 4', '"v": 4, "\\u0076": 4').encode())
        samples.append(json.dumps({"v": 4, "id": "a" * 32, "op": "register", "token": self.token,
                                   "body": {"username": "BridgePlayer", "password": "example-pass-1234"}}).encode())
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
        for body in (gzip.compress(b"x" * 262145), valid + b"extra", valid + valid, b"not gzip"):
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

    def test_directory_cycle_uses_fixed_routes_and_public_fields(self):
        start = len(self.calls)
        self.assertEqual(self.exchange(self.request("areas", {"after": ""}))["data"],
                         {"areas": [{"id": "area-1", "name": "Area 1"}], "next": ""})
        self.assertEqual(self.exchange(self.request("teams", {"area_id": "area-1", "after": ""}))["data"],
                         {"teams": [TEAM_SUMMARY], "next": ""})
        self.assertIsNone(self.exchange(self.request("my_team"))["data"]["team"])
        created = self.exchange(self.request("create_team", {"name": " Lantern Guard ", "area_id": "area-1"}))
        self.assertEqual(created["status"], 201)
        self.assertEqual(created["data"]["team"], TEAM)
        self.assertEqual(self.exchange(self.request("my_team"))["data"]["team"], TEAM)
        self.assertEqual(self.exchange(self.request("team_detail", {"team_id": TEAM["id"]}))["data"]["team"], TEAM)
        for method, path, headers, _body in self.calls[start:]:
            self.assertEqual(method, "POST")
            self.assertTrue(path.startswith("/internal/v1/team-directory/"))
            self.assertEqual(headers["X-Player-Token"], self.token)

    def test_uncertain_team_creation_is_reconciled_without_repeating_mutation(self):
        type(self).mode = "directory_uncertain"
        start = len(self.calls)
        result = self.exchange(self.request("create_team", {"name": "Lantern Guard", "area_id": "area-1"}))
        self.assertEqual(result["status"], 503)
        self.assertTrue(type(self).directory_created)
        self.assertNotIn(self.secret, json.dumps(result))
        self.assertEqual(self.exchange(self.request("my_team"))["data"]["team"], TEAM)
        self.assertEqual(sum(path.endswith("/create_team") for _, path, _, _ in self.calls[start:]), 1)

    def test_membership_cycle_and_uncertain_mutation_never_retried(self):
        start = len(self.calls)
        team_id, account_id = TEAM['id'], ACCOUNT['_id']
        self.assertEqual(self.exchange(self.request('my_applications', {'after': ''}))['data'],
                         {'teams': [], 'next': ''})
        for operation, status in (('apply_team', 'applied'), ('withdraw_application', 'withdrawn'),
                                   ('approve_application', 'approved'), ('reject_application', 'rejected')):
            body = {'team_id': team_id}
            if operation in ('approve_application', 'reject_application'):
                body['account_id'] = account_id
            response = self.exchange(self.request(operation, body))
            self.assertEqual(response['status'], 200)
            self.assertEqual(response['data'], {'team_id': team_id, 'account_id': account_id, 'status': status})
        type(self).mode = 'application_uncertain'
        response = self.exchange(self.request('apply_team', {'team_id': team_id}))
        self.assertEqual(response['status'], 503)
        self.assertEqual(self.exchange(self.request('my_applications', {'after': ''}))['data'],
                         {'teams': [TEAM_SUMMARY], 'next': ''})
        self.assertEqual(self.exchange(self.request('team_applicants', {'team_id': team_id, 'after': ''}))['data'],
                         {'team_id': team_id, 'applicants': TEAM['members'], 'next': ''})
        self.assertEqual(sum(path.endswith('/apply_team') for _, path, _, _ in self.calls[start:]), 2)
        for method, path, headers, _body in self.calls[start:]:
            self.assertEqual(method, 'POST')
            self.assertTrue(path.startswith('/internal/v1/team-directory/'))
            self.assertEqual(headers['X-Player-Token'], self.token)

    def test_membership_page_bounds_identity_and_private_fields_are_rejected(self):
        team_id, account_id = TEAM['id'], ACCOUNT['_id']
        applicant = TEAM['members'][0]
        ack = {'team_id': team_id, 'account_id': account_id, 'status': 'approved'}
        other_id = '32345678-1234-1234-1234-123456789abc'
        cases = [
            ('my_applications', {'after': ''}, {'teams': [TEAM_SUMMARY] * 21, 'next': ''}),
            ('my_applications', {'after': team_id}, {'teams': [TEAM_SUMMARY], 'next': ''}),
            ('my_applications', {'after': ''}, {'teams': [TEAM_SUMMARY], 'next': team_id}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': other_id, 'applicants': [], 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': team_id, 'applicants': [applicant] * 21, 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': team_id, 'applicants': [applicant] * 2, 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': account_id},
             {'team_id': team_id, 'applicants': [applicant], 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': team_id, 'applicants': [{**applicant, 'password_hash': self.secret}], 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': team_id, 'applicants': [{**applicant, 'level': True}], 'next': ''}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
             {'team_id': team_id, 'applicants': [applicant], 'next': account_id}),
            ('approve_application', {'team_id': team_id, 'account_id': account_id}, {**ack, 'team_id': other_id}),
            ('approve_application', {'team_id': team_id, 'account_id': account_id}, {**ack, 'account_id': other_id}),
            ('approve_application', {'team_id': team_id, 'account_id': account_id}, {**ack, 'status': 'rejected'}),
            ('approve_application', {'team_id': team_id, 'account_id': account_id}, {**ack, 'secret': self.secret}),
            ('apply_team', {'team_id': team_id}, {**ack, 'status': 'applied', 'account_id': 'bad'}),
        ]
        for operation, body, response in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (200, response)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result['status'], 503)
                self.assertNotIn(self.secret, json.dumps(result))
        # Valid multi-area summaries and full applicant pages survive unchanged.
        summaries = [{**TEAM_SUMMARY, 'id': f'{index:08x}-1234-1234-1234-123456789abc',
                      'area_id': f'area-{index}'} for index in range(1, 21)]
        applicants = [{**applicant, 'id': item['id']} for item in summaries]
        for operation, body, response in (
            ('my_applications', {'after': ''}, {'teams': summaries, 'next': summaries[-1]['id']}),
            ('team_applicants', {'team_id': team_id, 'after': ''},
                {'team_id': team_id, 'applicants': applicants, 'next': applicants[-1]['id']})):
            type(self).directory_override = (200, response)
            self.assertEqual(self.exchange(self.request(operation, body))['data'], response)

    def test_decision_read_ack_and_uncertain_ack_recovery(self):
        start = len(self.calls)
        self.assertEqual(self.exchange(self.request('application_decisions'))['data'], {'decisions': []})
        type(self).decisions = [deepcopy(DECISION)]
        for _ in range(2):
            result = self.exchange(self.request('application_decisions'))
            self.assertEqual(result['data'], {'decisions': [DECISION]})
            self.assertTrue(type(self).decisions[0]['unread'])
        type(self).mode = 'decision_uncertain'
        marked = self.exchange(self.request('ack_decision', {'decision_id': DECISION['id']}))
        self.assertEqual(marked['status'], 503)
        self.assertFalse(self.exchange(self.request('application_decisions'))['data']['decisions'][0]['unread'])
        self.assertEqual(sum(path.endswith('/ack_decision') for _, path, _, _ in self.calls[start:]), 1)
        type(self).mode = 'normal'
        marked = self.exchange(self.request('ack_decision', {'decision_id': DECISION['id']}))
        self.assertEqual(marked['data'], {'decision_id': DECISION['id'], 'status': 'read'})
        missing = self.exchange(self.request('ack_decision', {'decision_id': TEAM['id']}))
        self.assertEqual((missing['status'], missing['data']['code']), (404, 'not_found'))
        for method, path, headers, _body in self.calls[start:]:
            self.assertEqual(method, 'POST')
            self.assertTrue(path.startswith('/internal/v1/team-directory/'))
            self.assertEqual(headers['X-Player-Token'], self.token)
        type(self).revoked = True
        for operation, body in (('application_decisions', {}), ('ack_decision', {'decision_id': DECISION['id']})):
            result = self.exchange(self.request(operation, body))
            self.assertEqual((result['status'], result['data']['code']), (401, 'invalid_session'))

    def test_decision_responses_reject_private_fields_wrong_types_dates_and_overflow(self):
        cases = [('application_decisions', {}, {'decisions': [DECISION] * 51}),
                 ('application_decisions', {}, {'decisions': [DECISION] * 2}),
                 ('application_decisions', {}, {'decisions': [], 'account_id': ACCOUNT['_id']}),
                 ('ack_decision', {'decision_id': DECISION['id']}, {'decision_id': TEAM['id'], 'status': 'read'}),
                 ('ack_decision', {'decision_id': DECISION['id']}, {'decision_id': DECISION['id'], 'status': 'unread'}),
                 ('ack_decision', {'decision_id': DECISION['id']},
                  {'decision_id': DECISION['id'], 'status': 'read', 'private': self.secret})]
        for key, value in (('id', 'not-a-uuid'), ('team_id', {'$ne': ''}), ('team_name', '<Team>'),
            ('status', 'pending'), ('unread', 1), ('created_at', '2026-02-29T12:34:56Z'),
            ('created_at', '0000-01-01T12:34:56Z'), ('created_at', '2026-01-01T24:34:56Z'),
            ('created_at', '2026-01-01T12:34:56+00:00'), ('created_at', '2026-13-01T12:34:56Z'),
            ('password_hash', self.secret)):
            cases.append(('application_decisions', {}, {'decisions': [{**DECISION, key: value}]}))
        for operation, body, response in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (200, response)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result['status'], 503)
                self.assertNotIn(self.secret, json.dumps(result))
        # Fifty unique notices fit the unchanged32KiB frame; preserve insertion order.
        records = [{**DECISION, 'id': f'{index:08x}-1234-1234-1234-123456789abc',
                    'created_at': '2024-02-29T12:34:56Z', 'unread': bool(index % 2)} for index in range(50)]
        type(self).directory_override = (200, {'decisions': records})
        self.assertEqual(self.exchange(self.request('application_decisions'))['data'], {'decisions': records})

    def test_directory_invalid_requests_are_rejected_before_forwarding(self):
        cases = [self.request("areas", {"after": {"$gt": ""}}),
                 self.request("teams", {"area_id": "../server/finish", "after": ""}),
                 self.request("teams", {"area_id": "area-1", "after": "A" * 36}),
                 self.request("my_team", {"actor_id": ACCOUNT["_id"]}),
                 self.request("create_team", {"name": "Bad<Name", "area_id": "area-1"}),
                 self.request("create_team", {"name": "Good Name", "area_id": "area-1", "experience": 99}),
                 self.request("team_detail", {"team_id": "area-1"}),
                 self.request("settle", {"team_id": TEAM["id"]}),
                 self.request('my_applications', {'after': {'$gt': ''}}),
                 self.request('team_applicants', {'team_id': TEAM['id'], 'after': '', 'limit': 64}),
                 self.request('apply_team', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']}),
                 self.request('withdraw_application', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']}),
                 self.request('approve_application', {'team_id': TEAM['id'], 'account_id': {'$ne': ''}}),
                 self.request('reject_application', {'team_id': TEAM['id'], 'account_id': '../admin'}),
                 self.request('application_decisions', {'account_id': ACCOUNT['_id']}),
                 self.request('application_decisions', {'after': ''}),
                 self.request('ack_decision', {'decision_id': {'$ne': ''}}),
                 self.request('leave_team', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']}),
                 self.request('leave_team', {'team_id': {'$ne': ''}}),
                 self.request('leave_team', {'team_id': TEAM['id']}),
                 self.request('leave_team', {'team_id': TEAM['id'], 'allow_archive': 1}),
                 self.request('leave_team', {'team_id': TEAM['id'], 'allow_archive': 'false'}),
                 self.request('transfer_captain', {'team_id': TEAM['id']}),
                 self.request('transfer_captain', {'team_id': TEAM['id'], 'account_id': {'$ne': ''}}),
                 self.request('standings', {'area_id': 'area-1', 'after': ''}),
                 self.request('standings', {'area_id': {'$ne': ''}}),
                 self.request('ack_decision', {'decision_id': DECISION['id'], 'account_id': ACCOUNT['_id']})]
        missing_token = self.request("areas", {"after": ""})
        missing_token.pop("token")
        cases.append(missing_token)
        for value in cases:
            with self.subTest(operation=value["op"]), self.connect() as peer:
                before = len(self.calls)
                body = gzip.compress(json.dumps(value).encode())
                peer.sendall(struct.pack("!I", len(body)) + body)
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)
                self.assertEqual(len(self.calls), before)

    def test_directory_backend_contract_rejects_leaks_bounds_and_invalid_rosters(self):
        cases = []
        for field, value in (("password_hash", "secret"), ("capacity", 9), ("level", True),
                             ("rating", 2147483648), ("captain_id", "32345678-1234-1234-1234-123456789abc"),
                             ("members", TEAM["members"] * 2), ("members", [])):
            team = deepcopy(TEAM)
            team[field] = value
            cases.append(("my_team", {}, {"team": team}))
        member_secret = deepcopy(TEAM)
        member_secret["members"][0]["password_hash"] = "secret"
        cases.append(("my_team", {}, {"team": member_secret}))
        cases += [("areas", {"after": ""}, {"areas": [{"id": "area-1", "name": "Area 1"}] * 21, "next": ""}),
                  ("areas", {"after": ""}, {"areas": [{"id": "area-1", "name": "Area 1"}], "next": "area-1"}),
                  ("areas", {"after": "area-1"}, {"areas": [{"id": "area-1", "name": "Area 1"}], "next": ""}),
                  ("teams", {"area_id": "other-area", "after": ""}, {"teams": [TEAM_SUMMARY], "next": ""}),
                  ("team_detail", {"team_id": "32345678-1234-1234-1234-123456789abc"}, {"team": TEAM}),
                  ("team_detail", {"team_id": TEAM["id"]}, {"team": None})]
        for operation, body, response in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (200, response)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result["status"], 503)
                self.assertNotIn("password_hash", json.dumps(result))
                self.assertNotIn('"secret"', json.dumps(result))

    def test_directory_safe_error_codes_and_session_scope(self):
        for status, backend, expected in ((401, "expired", "invalid_session"),
                (403, "private_permission_detail", "forbidden"), (404, "not_found", "not_found"),
                (409, "already_member", "already_member"), (409, "conflict", "conflict"),
                (409, "invalid_input", "invalid_input"), (409, "busy", "busy"),
                (409, "capacity", "capacity"), (409, "not_requested", "not_requested"),
                (409, "captain_transfer_required", "captain_transfer_required"),
                (409, "not_member", "not_member")):
            with self.subTest(status=status, code=backend):
                type(self).directory_override = (status, {"error": {"code": backend, "message": self.secret}})
                result = self.exchange(self.request("my_team"))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["data"]["code"], expected)
                self.assertNotIn(self.secret, json.dumps(result))
        type(self).directory_override = None
        type(self).revoked = True
        self.assertEqual(self.exchange(self.request("my_team"))["data"]["code"], "invalid_session")

    def test_management_fixed_routes_exact_responses_and_no_mutation_retry(self):
        leave = {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id'], 'status': 'left', 'archived': False}
        transfer = {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id'], 'status': 'transferred'}
        ranking = {'area_id': 'area-1', 'teams': [TEAM_SUMMARY], 'has_more': False}
        for operation, body, response in (
            ('leave_team', {'team_id': TEAM['id'], 'allow_archive': False}, leave),
            ('leave_team', {'team_id': TEAM['id'], 'allow_archive': True}, {**leave, 'archived': True}),
            ('transfer_captain', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']}, transfer),
            ('standings', {'area_id': 'area-1'}, ranking),
            ('standings', {'area_id': 'area-1'}, {**ranking, 'teams': []})):
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (200, response)
                before = len(self.calls)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result['data'], response)
                self.assertTrue(result['ok'])
                self.assertEqual(len(self.calls), before + 1)
                method, path, headers, sent = self.calls[-1]
                self.assertEqual((method, path), ('POST', '/internal/v1/team-directory/' + operation))
                self.assertEqual(json.loads(sent), body)
        for operation, body in (('leave_team', {'team_id': TEAM['id'], 'allow_archive': False}),
                                ('transfer_captain', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']})):
            type(self).directory_override = (503, {'error': {'code': 'private', 'message': self.secret}})
            before = len(self.calls)
            result = self.exchange(self.request(operation, body))
            self.assertEqual(result['status'], 503)
            self.assertNotIn(self.secret, json.dumps(result))
            self.assertEqual(len(self.calls), before + 1)

    def test_management_rejects_unbound_acknowledgements_and_malformed_rankings(self):
        leave = {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id'], 'status': 'left', 'archived': False}
        transfer = {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id'], 'status': 'transferred'}
        cases = []
        for key, value in (('team_id', DECISION['id']), ('account_id', 'bad'), ('status', 'withdrawn'),
                           ('archived', 1), ('archived', 'false'), ('archived', True), ('password_hash', 'secret')):
            cases.append(('leave_team', {'team_id': TEAM['id'], 'allow_archive': False}, {**leave, key: value}))
        for key, value in (('team_id', DECISION['id']), ('account_id', DECISION['id']),
                           ('status', 'approved'), ('members', [])):
            cases.append(('transfer_captain', {'team_id': TEAM['id'], 'account_id': ACCOUNT['_id']},
                          {**transfer, key: value}))
        ranked = [dict(TEAM_SUMMARY, id=f'{index:08x}-1234-1234-1234-123456789abc', rating=1000-index//2)
                  for index in range(20)]
        ranking = {'area_id': 'area-1', 'teams': ranked, 'has_more': True}
        for has_more in (True, False):
            type(self).directory_override = (200, {**ranking, 'has_more': has_more})
            result = self.exchange(self.request('standings', {'area_id': 'area-1'}))
            self.assertEqual(result['data'], {**ranking, 'has_more': has_more})
        variants = [{**ranking, 'area_id': 'area-2'}, {**ranking, 'has_more': 1},
                    {**ranking, 'next': ''}, {**ranking, 'teams': ranked[:19]},
                    {**ranking, 'teams': ranked + [ranked[-1]]},
                    {**ranking, 'teams': list(reversed(ranked))},
                    {**ranking, 'teams': [ranked[1], ranked[0]] + ranked[2:]},
                    {**ranking, 'teams': [ranked[0], ranked[0]] + ranked[2:]},
                    {**ranking, 'teams': [dict(ranked[0], area_id='area-2')] + ranked[1:]},
                    {**ranking, 'teams': [dict(ranked[0], join_requests=[])] + ranked[1:]},
                    {**ranking, 'teams': [dict(ranked[0], rating=True)] + ranked[1:]}]
        cases.extend(('standings', {'area_id': 'area-1'}, response) for response in variants)
        for operation, body, response in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (200, response)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result['status'], 503)
                self.assertNotIn('password_hash', json.dumps(result))
                self.assertNotIn('"secret"', json.dumps(result))

    def test_planning_fixed_contracts_safe_mutations_and_all_read_states(self):
        selector = {'battle_id': BATTLE['id']}
        approved = deepcopy(BATTLE)
        for team in approved['teams']:
            team['approved'] = True
            for player in team['players']:
                player['selection']={'hero_id':'konrad','form_id':'konrad-fighter','hero_level':2,'hero_revision':1,'unit_type':'UH_Konrad','unit_level':1}
        ready = deepcopy(approved)
        ready['teams'][0]['players'][0]['ready'] = True
        cases = [('battle_maps', {'area_id': 'area-1'}, {'area_id': 'area-1', 'maps': [BATTLE_MAP]}, 200),
                 ('my_battles', {'after': ''}, {'battles': [BATTLE_SUMMARY], 'next': ''}, 200),
                 ('propose_battle', BATTLE_PROPOSAL, {'battle': BATTLE}, 201),
                 ('approve_battle', selector, {'battle': approved}, 200),
                 ('battle_ready', {**selector, 'ready': True}, {'battle': ready}, 200),
                 ('battle_ready', {**selector, 'ready': False}, {'battle': {**approved, 'validity': 'leader_changed'}}, 200),
                 ('cancel_battle', selector, {'battle': {**ready, 'state': 'cancelled'}}, 200)]
        cases += [('battle_detail', selector, {'battle': {**BATTLE, 'state': state}}, 200)
                  for state in ('draft', 'running', 'completed', 'cancelled')]
        archived = deepcopy(BATTLE)
        archived.update(validity='team_unavailable', state='cancelled')
        archived['teams'][1]['captain_id'] = ''
        cases.append(('battle_detail', selector, {'battle': archived}, 200))
        for operation, body, response, status in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (status, response)
                before = len(self.calls)
                result = self.exchange(self.request(operation, body))
                self.assertTrue(result['ok'])
                self.assertEqual(result['data'], response)
                self.assertEqual(len(self.calls), before + 1)
                method, path, headers, sent = self.calls[-1]
                self.assertEqual((method, path), ('POST', '/internal/v1/team-directory/' + operation))
                self.assertEqual(json.loads(sent), body)
        for operation, body in (('propose_battle', BATTLE_PROPOSAL), ('approve_battle', selector),
                                ('battle_ready', {**selector, 'ready': True}), ('cancel_battle', selector)):
            type(self).directory_override = (503, {'error': {'code': 'private', 'message': self.secret}})
            before = len(self.calls)
            response = self.exchange(self.request(operation, body))
            self.assertEqual(response['status'], 503)
            self.assertNotIn(self.secret, json.dumps(response))
            self.assertEqual(len(self.calls), before + 1)

    def test_planning_request_rejection_before_forwarding_including_start(self):
        cases = [('battle_maps', {'area_id': {'$ne': ''}}), ('my_battles', {'after': 'bad'}),
            ('battle_detail', {'battle_id': {'$ne': ''}}),
            ('approve_battle', {'battle_id': BATTLE['id'], 'account_id': ACCOUNT['_id']}),
            ('battle_ready', {'battle_id': BATTLE['id'], 'ready': 1}),
            ('battle_ready', {'battle_id': BATTLE['id'], 'ready': 'false'}),
            ('cancel_battle', {'battle_id': BATTLE['id'], 'reason': 'private'}),
            ('start_battle', {'battle_id': BATTLE['id']}), ('finish_battle', {'battle_id': BATTLE['id']})]
        for key, value in (('map_id', 'external-map'), ('lineups', []), ('actor_id', ACCOUNT['_id']),
                           ('opponent_team_id', TEAM['id']), ('experience', 20)):
            cases.append(('propose_battle', {**BATTLE_PROPOSAL, key: value}))
        duplicate = deepcopy(BATTLE_PROPOSAL)
        duplicate['lineups'][1]['account_ids'][0] = duplicate['lineups'][0]['account_ids'][0]
        cases.append(('propose_battle', duplicate))
        extra = deepcopy(BATTLE_PROPOSAL)
        extra['lineups'][0]['password_hash'] = 'secret'
        cases.append(('propose_battle', extra))
        for operation, body in cases:
            with self.subTest(operation=operation, body=body), self.connect() as peer:
                value = self.request(operation, body)
                value['token'] = self.token
                before = len(self.calls)
                encoded = gzip.compress(json.dumps(value).encode())
                peer.sendall(struct.pack('!I', len(encoded)) + encoded)
                with self.assertRaises((EOFError, ssl.SSLError, ConnectionError)):
                    self.read_exact(peer, 4)
                self.assertEqual(len(self.calls), before)

    def test_planning_projection_rejects_private_fields_identity_sides_and_bounds(self):
        selector = {'battle_id': BATTLE['id']}
        cases = []
        for key, value in (('state', 'ready'), ('validity', 'private_error'), ('id', DECISION['id']),
                           ('password_hash', 'secret'), ('created_at', '2026-02-30T12:34:56Z')):
            cases.append(('battle_detail', selector, {'battle': {**BATTLE, key: value}}, 200))
        for key, value in (('name', 'Other Map'), ('scenario_id', 'unknown'), ('size', True),
                           ('sides', [[1, 2], [3, 4]]), ('id', 'unknown'), ('reward', 100)):
            changed = deepcopy(BATTLE)
            changed['map'][key] = value
            cases.append(('battle_detail', selector, {'battle': changed}, 200))
        for change in ('duplicate-team', 'duplicate-player', 'wrong-side', 'private-player', 'too-many', 'captain', 'approved', 'ready'):
            changed = deepcopy(BATTLE)
            first, second = changed['teams']
            if change == 'duplicate-team': second['id'] = first['id']
            elif change == 'duplicate-player': second['players'][0]['id'] = first['players'][0]['id']
            elif change == 'wrong-side': first['players'][0]['side'] = 4
            elif change == 'private-player': first['players'][0]['experience'] = 0
            elif change == 'too-many': first['players'].append(first['players'][0])
            elif change == 'captain': first.update(captain_id='', approved=True)
            elif change == 'approved': first['approved'] = 1
            else: first['players'][0]['ready'] = 1
            cases.append(('battle_detail', selector, {'battle': changed}, 200))
        wrong_order = deepcopy(BATTLE)
        wrong_order['teams'][0]['players'][0]['id'], wrong_order['teams'][0]['players'][1]['id'] = (
            wrong_order['teams'][0]['players'][1]['id'], wrong_order['teams'][0]['players'][0]['id'])
        cases.append(('propose_battle', BATTLE_PROPOSAL, {'battle': wrong_order}, 201))
        autoapproved = deepcopy(BATTLE)
        autoapproved['teams'][0]['approved'] = True
        cases.append(('propose_battle', BATTLE_PROPOSAL, {'battle': autoapproved}, 201))
        cases.extend([
            ('battle_maps', {'area_id': 'area-1'}, {'area_id': 'area-2', 'maps': [BATTLE_MAP]}, 200),
            ('battle_maps', {'area_id': 'area-1'}, {'area_id': 'area-1', 'maps': [BATTLE_MAP]*2}, 200),
            ('my_battles', {'after': ''}, {'battles': [BATTLE_SUMMARY]*21, 'next': ''}, 200),
            ('my_battles', {'after': ''}, {'battles': [BATTLE_SUMMARY]*2, 'next': ''}, 200),
            ('my_battles', {'after': ''}, {'battles': [BATTLE_SUMMARY], 'next': BATTLE['id']}, 200),
            ('my_battles', {'after': BATTLE['id']}, {'battles': [BATTLE_SUMMARY], 'next': ''}, 200),
            ('cancel_battle', selector, {'battle': BATTLE}, 200),
            ('approve_battle', selector, {'battle': {**BATTLE, 'state': 'running'}}, 200)])
        for operation, body, response, status in cases:
            with self.subTest(operation=operation, response=response):
                type(self).directory_override = (status, response)
                result = self.exchange(self.request(operation, body))
                self.assertEqual(result['status'], 503)
                self.assertNotIn('password_hash', json.dumps(result))
                self.assertNotIn('"secret"', json.dumps(result))

    def test_planning_safe_errors_preserve_current_session(self):
        for code in ('planning_exists', 'invalid_map', 'invalid_lineup', 'different_area', 'stale_proposal',
                     'advancement_required', 'approval_required', 'invalid_state'):
            type(self).directory_override = (409, {'error': {'code': code, 'message': self.secret}})
            result = self.exchange(self.request('battle_detail', {'battle_id': BATTLE['id']}))
            self.assertEqual((result['status'], result['data']['code']), (409, code))
            self.assertNotIn(self.secret, json.dumps(result))
        type(self).directory_override = (200, {'battle': BATTLE})
        self.assertTrue(self.exchange(self.request('battle_detail', {'battle_id': BATTLE['id']}))['ok'])

    def test_stalled_backend_does_not_block_other_connection(self):
        slow = self.request("register", {"username": "SlowPlayer", "password": "example-pass-1234"})
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


    def test_extension_routes_remain_closed_and_public(self):
        profile={'id':ACCOUNT['_id'],'username':'BridgePlayer','database_generation':ACCOUNT['database_generation'],'heroes':[]}
        order={'id':TEAM['id'],'author_id':ACCOUNT['_id'],'author_name':'BridgePlayer','text':'Guard north.',
               'created_at':'2026-10-23T01:02:03Z'}
        review={'run_id':BATTLE['id'],'state':'running','review_state':'awaiting_captains','candidate_digest':'a'*64,
                'winner_team_id':TEAM['id'],'draw':False,'reports_received':4,'required_reports':4,'captains_approved':1,'revision':2}
        cases=[('progression_advance',{'unit_type':'Swordsman'},{'profile':profile},'/internal/v1/progression/advance'),
               ('coordination_orders',{'team_id':TEAM['id']},{'team_id':TEAM['id'],'team_name':TEAM['name'],'orders':[order],'has_more':False},'/internal/v1/coordination/orders'),
               ('coordination_post',{'team_id':TEAM['id'],'text':'Guard north.'},{'order':order},'/internal/v1/coordination/post'),
               ('shared_review',{'run_id':BATTLE['id']},review,'/internal/v1/shared/review'),
               ('shared_confirm',{'run_id':BATTLE['id'],'candidate_digest':'a'*64},review,'/internal/v1/shared/confirm')]
        for operation,body,response,target in cases:
            with self.subTest(operation=operation):
                type(self).directory_override=(200,response)
                result=self.exchange(self.request(operation,body));self.assertEqual(result['data'],response)
                method,path,headers,sent=self.calls[-1]
                self.assertEqual((method,path,json.loads(sent)),('POST',target,body))
                self.assertEqual(headers['X-Player-Token'],self.token)
                type(self).directory_override=(200,dict(response,password_hash='private'))
                self.assertEqual(self.exchange(self.request(operation,body))['status'],503)

    def test_extension_unknown_backend_errors_never_expose_private_text(self):
        for status in (400,403,409,500,503):
            type(self).directory_override=(status,{'error':{'code':'private_config','message':self.secret}})
            result=self.exchange(self.request('progression_catalog'))
            self.assertFalse(result['ok']);self.assertNotIn(self.secret,json.dumps(result));self.assertNotIn('private_config',json.dumps(result))
        type(self).directory_override=(409,{'error':{'code':'busy','message':self.secret}})
        result=self.exchange(self.request('progression_catalog'))
        self.assertEqual(result['data']['code'],'busy');self.assertNotIn(self.secret,json.dumps(result))

    def test_extension_extra_authority_fields_rejected_before_backend(self):
        for operation,body in [('progression_catalog',{'account_id':ACCOUNT['_id']}),
                ('progression_finish',{'run_id':BATTLE['id'],'award_experience':9999}),
                ('shared_confirm',{'run_id':BATTLE['id'],'candidate_digest':'a'*64,'winner_team_id':TEAM['id']}),
                ('coordination_post',{'team_id':TEAM['id'],'text':'Guard north.','author_id':ACCOUNT['_id']})]:
            with self.subTest(operation=operation),self.connect() as peer:
                before=len(self.calls);payload=gzip.compress(json.dumps(self.request(operation,body)).encode())
                peer.sendall(struct.pack('!I',len(payload))+payload)
                with self.assertRaises((EOFError,ssl.SSLError,ConnectionError)):self.read_exact(peer,4)
                self.assertEqual(len(self.calls),before)

if __name__ == "__main__":
    unittest.main(verbosity=2)
