"""Real native team-management client/bridge/backend/MongoDB and restart proof.

All data, identities and credentials belong to a disposable offline container.
No existing game runtime, shared database or .env is accessed.
"""
from contextlib import contextmanager, redirect_stdout
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
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(all(os.environ.get(key) for key in (
    "ALLIANCE_TEST_MONGOD", "ALLIANCE_ACCOUNT_BRIDGE", "ALLIANCE_MANAGEMENT_CLIENT")),
    "Requires explicit disposable MongoDB and native team binaries")
class RealManagementFlow(unittest.TestCase):
    def test_native_management_and_backend_restart(self):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo, _stop_owned, _client

        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        bridge = Path(os.environ["ALLIANCE_ACCOUNT_BRIDGE"])
        probe = Path(os.environ["ALLIANCE_MANAGEMENT_CLIENT"])
        for executable in (mongod, bridge, probe):
            self.assertTrue(executable.is_file())
        for port in (27018, 18765, 15001):
            with socket.socket() as peer:
                self.assertNotEqual(peer.connect_ex(("127.0.0.1", port)), 0,
                                    "Fixture requires free loopback ports")
        spec = importlib.util.spec_from_file_location("team_identity", ROOT / "tools/alliance_transport.py")
        identity_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity_module)

        with tempfile.TemporaryDirectory(prefix="alliance real management ") as directory:
            scratch = Path(directory)
            runtime, identity = scratch / "runtime", scratch / "identity"
            with redirect_stdout(io.StringIO()), patch("getpass.getpass", return_value=secrets.token_urlsafe(24)):
                initialize(runtime, mongod, admin_username="Operator")
                identity_module.prepare_identity(identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
            settings = Settings.load(runtime)
            username = "Captain_" + secrets.token_hex(4)
            applicant = "Applicant_" + secrets.token_hex(4)
            extra_username = "Solo_" + secrets.token_hex(4)
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
                                        input=json.dumps(data), text=True, capture_output=True, timeout=180)
                # The C++ probe prints only fixed stage names and success markers.
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("ALLIANCE MANAGEMENT FLOW CHECK PASSED", result.stdout)
                print(result.stdout, end="", flush=True)

            base = {"captain_username": username, "applicant_username": applicant,
                    "extra_username": extra_username, "password": password, "team_name": team_name}

            def persisted_state():
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    players = [db.accounts.find_one({"username": name})
                               for name in (username, applicant, extra_username)]
                    self.assertTrue(all(players))
                    captain, member, solo = players
                    team = db.teams.find_one({"name": team_name, "status": "active"})
                    self.assertIsNotNone(team)
                    self.assertEqual(team["captain_id"], captain["_id"])
                    self.assertEqual({item["account_id"] for item in team["members"]},
                                     {captain["_id"], member["_id"]})
                    self.assertEqual(team["join_requests"], [])
                    self.assertIsNone(team["active_run_id"])
                    self.assertEqual((team["experience"], team["level"], team["rating"]), (0, 1, 1000))
                    for account in players:
                        self.assertEqual(account["leader"]["unit_type"], "Spearman")
                        self.assertEqual(account["leader"]["level"], 1)
                        self.assertEqual(account["leader"]["experience"], 0)
                        self.assertEqual(account["leader"]["total_experience"], 0)
                        self.assertIsNone(account["active_run_id"])
                    for account in (captain, member):
                        self.assertEqual(db.teams.count_documents({"members.account_id": account["_id"]}), 1)
                    self.assertEqual(db.teams.count_documents({"members.account_id": solo["_id"]}), 0)
                    archived = list(db.teams.find({"status": "archived"}))
                    self.assertEqual(len(archived), 1)
                    archived = archived[0]
                    self.assertEqual(archived["members"], [])
                    self.assertEqual(archived["join_requests"], [])
                    self.assertIsNone(archived["captain_id"])
                    return {
                        "team": {key: team[key] for key in ("_id", "name", "area_id", "captain_id",
                            "members", "join_requests", "experience", "level", "rating", "active_run_id", "status")},
                        "players": [{"id": account["_id"], "leader": account["leader"],
                            "decisions": account.get("application_decisions", [])} for account in players],
                        "archived": {key: archived[key] for key in ("_id", "status", "captain_id", "members", "join_requests")},
                    }

            with stack():
                native(dict(base, mode="flow"))
                before = persisted_state()
            with stack():
                native(dict(base, mode="verify"))
                self.assertEqual(persisted_state(), before)
            print("PASS native captain transfer, member leave/rejoin and final-member archival", flush=True)
            print("PASS real restart preserves captain, roster, leaders, notices and archived team", flush=True)


if __name__ == "__main__":
    unittest.main()
