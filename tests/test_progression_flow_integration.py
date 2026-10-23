"""Real C++ client -> native TLS bridge -> Flask -> authenticated MongoDB.

Runs only in an isolated verification container with --network none and explicit
test binary paths. Creates its own temporary runtime; never uses an existing DB.
"""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import socket
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
    "ALLIANCE_TEST_MONGOD", "ALLIANCE_ACCOUNT_BRIDGE", "ALLIANCE_PROGRESSION_CLIENT")),
    "Requires explicit disposable MongoDB and native verification binaries")
class RealProgressionFlow(unittest.TestCase):
    def test_native_progression_coordination_and_restart(self):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo, _stop_owned, _client
        from alliance.auth import AuthService, AuthError

        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        bridge = Path(os.environ["ALLIANCE_ACCOUNT_BRIDGE"])
        client_probe = Path(os.environ["ALLIANCE_PROGRESSION_CLIENT"])
        for executable in (mongod, bridge, client_probe):
            self.assertTrue(executable.is_file())
        # Tests must not attach to an already running application or DB.
        for port in (27018, 18765, 15001):
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0,
                                    "Verification requires unoccupied local ports.")
        spec = importlib.util.spec_from_file_location("account_identity", ROOT / "tools/alliance_transport.py")
        identity_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity_module)
        with tempfile.TemporaryDirectory(prefix="alliance real account ") as directory:
            scratch = Path(directory)
            runtime = scratch / "runtime"
            identity = scratch / "identity"
            username = "Check_" + secrets.token_hex(5)
            password = "équipe-勇者-" + secrets.token_urlsafe(24)
            output = io.StringIO()
            with redirect_stdout(output), patch("getpass.getpass", return_value=secrets.token_urlsafe(24)):
                initialize(runtime, mongod, admin_username="Operator")
                identity_module.prepare_identity(identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
            settings = Settings.load(runtime)
            database = _start_mongo(runtime, mongod)
            service = native = None
            try:
                with tempfile.TemporaryFile() as private_log:
                    service = subprocess.Popen(
                        [sys.executable, "-B", "-m", "alliance", "--runtime", str(runtime), "serve"],
                        cwd=ROOT, stdout=private_log, stderr=private_log)
                    for _ in range(100):
                        self.assertIsNone(service.poll(), "Production backend exited during startup")
                        try:
                            with urllib.request.urlopen("http://127.0.0.1:18765/login", timeout=1) as response:
                                self.assertEqual(response.status, 200)
                            break
                        except urllib.error.URLError:
                            time.sleep(.1)
                    else:
                        self.fail("Production backend readiness timed out")
                    native = subprocess.Popen([str(bridge), "--runtime", str(runtime),
                                               "--identity", str(identity)],
                                              stdout=private_log, stderr=private_log)
                    for _ in range(100):
                        self.assertIsNone(native.poll(), "Native bridge exited during startup")
                        with socket.socket() as sock:
                            if sock.connect_ex(("127.0.0.1", 15001)) == 0:
                                break
                        time.sleep(.1)
                    else:
                        self.fail("Native bridge readiness timed out")
                    result = subprocess.run(
                        [str(client_probe), str(identity / "public-profile.json")],
                        input=json.dumps({"username": username, "password": password}),
                        text=True, capture_output=True, timeout=90)
                    # Probe output contains fixed markers only. Never echo a backend log.
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("ALLIANCE PROGRESSION FLOW CHECK PASSED", result.stdout)
                    print(result.stdout, end="", flush=True)
                    with _client(settings.mongo_uri) as connection:
                        db = connection.wesnoth_game
                        account = db.accounts.find_one({"username": username})
                        self.assertIsNotNone(account)
                        account_id = account["_id"]
                        self.assertTrue(account["password_hash"].startswith("$argon2id$"))
                        self.assertNotIn(password, account["password_hash"])
                        self.assertEqual(account["leader"]["unit_type"], "Swordsman")
                        self.assertEqual(account["leader"]["experience"], 18)
                        self.assertEqual(db.accounts.count_documents({"username": username}), 1)
                        self.assertEqual(account["leader"]["total_experience"], 60)
                        self.assertEqual(account["leader"]["level"], 2)
                        self.assertIsNone(account["active_run_id"])
                        self.assertEqual(db.settlements.count_documents({}), 3)
                        self.assertEqual(db.game_runs.count_documents({"state":"completed"}), 3)
                        self.assertEqual(db.game_runs.count_documents({"state":"cancelled"}), 1)
                        team=db.teams.find_one({"captain_id":account_id})
                        self.assertEqual(len(team["orders"]),1)
                        sessions = list(db.auth_sessions.find({"account_id": account_id}))
                        self.assertEqual(len(sessions), 1)
                        self.assertTrue(sessions[0]["revoked"])
                        self.assertNotIn(password, json.dumps(sessions, default=str))
                    print("PASS real MongoDB player, Argon2 hash, one leader and revoked session", flush=True)
            finally:
                try:
                    for process in (native, service):
                        if process is not None and process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=15)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)
                finally:
                    _stop_owned(database, runtime)
            # Real restart persistence, using the same disposable authenticated DB.
            database = _start_mongo(runtime, mongod)
            try:
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    account = db.accounts.find_one({"username": username})
                    self.assertEqual(account["_id"], account_id)
                    self.assertEqual(account["leader"]["unit_type"], "Swordsman")
                    login = AuthService(db).authenticate(username, password, "player")
                    self.assertEqual(login["account"]["_id"], account_id)
                    AuthService(db).revoke_token(login["token"])
                    with self.assertRaises(AuthError):
                        AuthService(db).validate_token(login["token"], "player")
                print("PASS real MongoDB restart preserves account and personal leader", flush=True)
            finally:
                _stop_owned(database, runtime)


if __name__ == "__main__":
    unittest.main()
