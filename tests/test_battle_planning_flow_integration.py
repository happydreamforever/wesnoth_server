"""Real native battle-planning client/bridge/backend/MongoDB and restart proof.

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
    "ALLIANCE_TEST_MONGOD", "ALLIANCE_ACCOUNT_BRIDGE", "ALLIANCE_BATTLE_CLIENT")),
    "Requires explicit disposable MongoDB and native team binaries")
class RealBattlePlanningFlow(unittest.TestCase):
    def test_native_planning_restart_and_cancellation(self):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo, _stop_owned, _client

        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        bridge = Path(os.environ["ALLIANCE_ACCOUNT_BRIDGE"])
        probe = Path(os.environ["ALLIANCE_BATTLE_CLIENT"])
        for executable in (mongod, bridge, probe):
            self.assertTrue(executable.is_file())
        for port in (27018, 18765, 15001):
            with socket.socket() as peer:
                self.assertNotEqual(peer.connect_ex(("127.0.0.1", port)), 0,
                                    "Fixture requires free loopback ports")
        spec = importlib.util.spec_from_file_location("battle_identity", ROOT / "tools/alliance_transport.py")
        identity_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity_module)

        with tempfile.TemporaryDirectory(prefix="alliance real planning ") as directory:
            scratch = Path(directory)
            runtime, identity = scratch / "runtime", scratch / "identity"
            with redirect_stdout(io.StringIO()), patch("getpass.getpass", return_value=secrets.token_urlsafe(24)):
                initialize(runtime, mongod, admin_username="Operator")
                identity_module.prepare_identity(identity, "127.0.0.1", 15001, Path("/usr/bin/openssl"))
            settings = Settings.load(runtime)
            username = "Captain_" + secrets.token_hex(4)
            applicant = "Applicant_" + secrets.token_hex(4)
            opponent = "Opponent_" + secrets.token_hex(4)
            opponent_member = "Partner_" + secrets.token_hex(4)
            password = "équipe-勇者-" + secrets.token_urlsafe(24)
            team_name = "Team " + secrets.token_hex(4)
            opponent_team_name = "Rivals " + secrets.token_hex(4)

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
                self.assertIn("ALLIANCE BATTLE PLANNING FLOW CHECK PASSED", result.stdout)
                print(result.stdout, end="", flush=True)

            base = {"captain_username": username, "member_username": applicant,
                    "opponent_username": opponent, "opponent_member_username": opponent_member,
                    "password": password, "team_name": team_name,
                    "opponent_team_name": opponent_team_name}

            def persisted_state(expected_state="draft"):
                with _client(settings.mongo_uri) as connection:
                    db = connection.wesnoth_game
                    players = [db.accounts.find_one({"username": name})
                               for name in (username, applicant, opponent, opponent_member)]
                    self.assertTrue(all(players))
                    teams = [db.teams.find_one({"name": name, "status": "active"})
                             for name in (team_name, opponent_team_name)]
                    self.assertTrue(all(teams))
                    for index, team in enumerate(teams):
                        captain, member = players[index * 2:index * 2 + 2]
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
                        self.assertEqual(db.teams.count_documents({"members.account_id": account["_id"]}), 1)
                    runs = list(db.game_runs.find({"kind": "alliance"}))
                    self.assertEqual(len(runs), 1, "Duplicate proposal must not create another draft")
                    run = runs[0]
                    self.assertEqual(run["state"], expected_state)
                    self.assertEqual(run["map_id"], "isars-cross")
                    self.assertEqual(run["team_ids"], [team["_id"] for team in teams])
                    self.assertEqual(run["lineups"], {teams[0]["_id"]: [p["_id"] for p in players[:2]],
                                                       teams[1]["_id"]: [p["_id"] for p in players[2:]]})
                    self.assertEqual(run["approvals"], {teams[0]["_id"]: players[0]["_id"],
                                                         teams[1]["_id"]: players[2]["_id"]})
                    self.assertEqual(set(run["ready"]), {p["_id"] for p in players})
                    self.assertEqual(len(run["participants"]), 4)
                    self.assertEqual([p["side"] for p in run["participants"]], [1, 4, 2, 3])
                    self.assertEqual([p["account_id"] for p in run["participants"]], [p["_id"] for p in players])
                    self.assertEqual([p["leader"] for p in run["participants"]], [p["leader"] for p in players])
                    self.assertEqual(db.settlements.count_documents({}), 0)
                    return {
                        "run": run,
                        "teams": [{key: team[key] for key in ("_id", "name", "area_id", "captain_id",
                            "members", "join_requests", "experience", "level", "rating", "active_run_id", "status")}
                            for team in teams],
                        "players": [{"id": account["_id"], "leader": account["leader"],
                            "decisions": account.get("application_decisions", [])} for account in players],
                    }

            with stack():
                native(dict(base, mode="flow"))
                before = persisted_state()
            with stack():
                native(dict(base, mode="verify"))
                self.assertEqual(persisted_state(), before)
                native(dict(base, mode="cancel"))
                after = persisted_state("cancelled")
                self.assertEqual(after["players"], before["players"])
                self.assertEqual(after["teams"], before["teams"])
                for key in ("_id", "map_id", "area_id", "team_ids", "lineups", "participants", "approvals", "ready"):
                    self.assertEqual(after["run"][key], before["run"][key])
            print("PASS native four-player proposal, two approvals, ready/unready and cancellation", flush=True)
            print("PASS full restart preserves fixed lineups, side assignments, approvals and ready draft", flush=True)
            print("PASS planning reserves no accounts or teams and grants no XP or settlements", flush=True)


if __name__ == "__main__":
    unittest.main()
