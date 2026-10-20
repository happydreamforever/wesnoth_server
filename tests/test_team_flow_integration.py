"""Actual native team client/bridge/backend/MongoDB in a disposable offline container.

Requires explicit test executables and free loopback ports. No existing runtime
or .env is accessed. Private temporary process logs are never copied to reports.
"""
from contextlib import contextmanager, redirect_stdout
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(all(os.environ.get(key) for key in (
    "ALLIANCE_TEST_MONGOD", "ALLIANCE_ACCOUNT_BRIDGE", "ALLIANCE_TEAM_CLIENT")),
    "Requires explicit disposable MongoDB and native team binaries")
class RealTeamFlow(unittest.TestCase):
    def test_native_team_creation_recovery_and_backend_restart(self):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo, _stop_owned, _client
        from alliance.domain import AllianceService
        from alliance.auth import AuthService, hash_password

        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        bridge = Path(os.environ["ALLIANCE_ACCOUNT_BRIDGE"])
        probe = Path(os.environ["ALLIANCE_TEAM_CLIENT"])
        for executable in (mongod, bridge, probe):
            self.assertTrue(executable.is_file())
        for port in (27018, 18765, 15001):
            with socket.socket() as peer:
                self.assertNotEqual(peer.connect_ex(("127.0.0.1", port)), 0,
                                    "Fixture requires free loopback ports")
        spec = importlib.util.spec_from_file_location("team_identity", ROOT / "tools/alliance_transport.py")
        identity_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity_module)

        with tempfile.TemporaryDirectory(prefix="alliance real teams ") as directory:
            scratch = Path(directory)
            runtime, identity = scratch / "runtime", scratch / "identity"
            with redirect_stdout(io.StringIO()), patch("getpass.getpass", return_value=secrets.token_urlsafe(24)):
                initialize(runtime, mongod, admin_username="Operator")
                profile, _ = identity_module.prepare_identity(identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
            settings = Settings.load(runtime)
            username = "Captain_" + secrets.token_hex(4)
            password = "équipe-勇者-" + secrets.token_urlsafe(24)
            team_name = "Team " + secrets.token_hex(4)

            @contextmanager
            def stack():
                database = _start_mongo(runtime, mongod)
                service = listener = None
                try:
                    with tempfile.TemporaryFile() as private_log:
                        service = subprocess.Popen([sys.executable, "-B", "-m", "alliance", "--runtime", str(runtime), "serve"],
                                                   cwd=ROOT, stdout=private_log, stderr=private_log)
                        for _ in range(100):
                            self.assertIsNone(service.poll(), "Backend exited")
                            try:
                                with urllib.request.urlopen("http://127.0.0.1:18765/login", timeout=1) as response:
                                    self.assertEqual(response.status, 200)
                                break
                            except urllib.error.URLError:
                                time.sleep(.1)
                        else:
                            self.fail("Backend readiness timeout")
                        listener = subprocess.Popen([str(bridge), "--runtime", str(runtime), "--identity", str(identity)],
                                                    stdout=private_log, stderr=private_log)
                        for _ in range(100):
                            self.assertIsNone(listener.poll(), "Native bridge exited")
                            with socket.socket() as peer:
                                if peer.connect_ex(("127.0.0.1", 15001)) == 0:
                                    break
                            time.sleep(.1)
                        else:
                            self.fail("Native bridge readiness timeout")
                        yield
                finally:
                    try:
                        for process in (listener, service):
                            if process is not None and process.poll() is None:
                                process.send_signal(signal.SIGINT)
                                try:
                                    process.wait(timeout=15)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                    process.wait(timeout=5)
                                    self.fail("Fixture child needed forced cleanup")
                    finally:
                        _stop_owned(database, runtime)

            def native(data):
                result = subprocess.run([str(probe), str(identity / "public-profile.json")],
                                        input=json.dumps(data), text=True, capture_output=True, timeout=90)
                # The C++ probe prints only fixed stage names and success markers.
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("ALLIANCE TEAM FLOW CHECK PASSED", result.stdout)
                print(result.stdout, end="", flush=True)

            with stack():
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    domain = AllianceService(db)
                    admin = db.accounts.find_one({"role": "admin"})["_id"]
                    for index in range(23):
                        domain.admin_create_area(admin, f"Directory Area {index:02d}")
                        seed = domain.register(f"Seed_{index:02d}", "$argon2id$fixture-not-for-login", "spearman")
                        domain.create_team(seed["_id"], f"Directory Team {index:02d}")
                native({"username": username, "password": password, "team_name": team_name, "restart": False})
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    account = db.accounts.find_one({"username": username})
                    team = db.teams.find_one({"captain_id": account["_id"]})
                    account_id, team_id = account["_id"], team["_id"]
                    self.assertEqual(db.teams.count_documents({"members.account_id": account_id}), 1)
                    self.assertEqual(account["leader"]["total_experience"], 0)
                    # Deterministic lost application acknowledgement: transfer
                    # a creation reply, discard it without decoding/displaying,
                    # then reconcile by the authenticated own-team operation.
                    lost_name = "Lost " + secrets.token_hex(4)
                    lost_user = "Lost_" + secrets.token_hex(4)
                    domain = AllianceService(db)
                    lost_account = domain.register(lost_user, hash_password(password), "spearman")
                    login = AuthService(db).authenticate(lost_user, password, "player")

                def exact(peer, count):
                    data = bytearray()
                    while len(data) < count:
                        part = peer.recv(count - len(data))
                        if not part:
                            self.fail("Lost-ack fixture peer closed early")
                        data.extend(part)
                    return bytes(data)

                raw = socket.create_connection(("127.0.0.1", 15001), timeout=10)
                raw.sendall(b"\0\0\0\1")
                self.assertEqual(exact(raw, 4), b"\0\0\0\0")
                context = ssl.create_default_context(cadata=profile["certificate_pem"])
                with context.wrap_socket(raw, server_hostname="127.0.0.1") as peer:
                    request = {"v": 1, "id": secrets.token_hex(16), "op": "create_team", "token": login["token"],
                               "body": {"name": lost_name, "area_id": "area-1"}}
                    body = gzip.compress(json.dumps(request).encode())
                    peer.sendall(struct.pack("!I", len(body)) + body)
                    size, = struct.unpack("!I", exact(peer, 4))
                    self.assertTrue(0 < size <= 65536)
                    exact(peer, size)  # Deliberately do not parse the acknowledgement.
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    lost_team = db.teams.find_one({"captain_id": lost_account["_id"]})
                    self.assertIsNotNone(lost_team)
                    self.assertEqual(db.teams.count_documents({"members.account_id": lost_account["_id"]}), 1)
                native({"username": lost_user, "password": password, "team_name": lost_name, "restart": True,
                        "account_id": lost_account["_id"], "team_id": lost_team["_id"]})
                print("PASS own-team lookup recovers a committed team after discarded acknowledgement", flush=True)

            with stack():
                native({"username": username, "password": password, "team_name": team_name, "restart": True,
                        "account_id": account_id, "team_id": team_id})
                with _client(settings.mongo_uri) as connection:
                    self.assertEqual(connection.wesnoth_game.teams.count_documents({"members.account_id": account_id}), 1)
            print("PASS real MongoDB/backend restart preserves captain, roster, team and personal leader", flush=True)


if __name__ == "__main__":
    unittest.main()
