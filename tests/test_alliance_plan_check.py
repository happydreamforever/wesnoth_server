"""Bounded snapshot/read-only diagnostic tests; optional real disposable local MongoDB."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest import mock
from uuid import UUID

from bson.int64 import Int64
from pymongo.errors import ServerSelectionTimeoutError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plan_check", ROOT / "tools/check_alliance_plan.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
NOW = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)
PRIVATE = "PRIVATE_CONFIGURATION_SENTINEL"


def uid(number):
    return str(UUID(int=number))


def values(document, parts):
    if not parts:
        return document if isinstance(document, list) else [document]
    if isinstance(document, list):
        return [value for item in document for value in values(item, parts)]
    if not isinstance(document, dict) or parts[0] not in document:
        return []
    return values(document[parts[0]], parts[1:])


def matches(document, query):
    for key, condition in query.items():
        if key == "$or":
            if not any(matches(document, item) for item in condition):
                return False
        else:
            found = values(document, key.split("."))
            if isinstance(condition, dict):
                if set(condition) != {"$in"}:
                    raise AssertionError("Unsupported test query")
                if not any(value in condition["$in"] for value in found):
                    return False
            elif condition not in found:
                return False
    return True


class Cursor:
    def __init__(self, owner, rows):
        self.owner, self.rows, self.maximum = owner, deepcopy(rows), None

    def sort(self, fields):
        self.owner.sorts.append(fields)
        for key, direction in reversed(fields):
            self.rows.sort(key=lambda item: item[key], reverse=direction == -1)
        return self

    def limit(self, maximum):
        self.owner.limits.append(maximum)
        self.maximum = maximum
        return self

    def __iter__(self):
        if self.maximum is None:
            raise AssertionError("Unbounded query")
        return iter(self.rows[:self.maximum])


class Collection:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def read(self, query, projection, session):
        if session is not self.owner.session or not session.active:
            raise AssertionError("Read outside consistent snapshot")
        if not projection or any(value not in (0, 1) for value in projection.values()):
            raise AssertionError("Unbounded projection")
        for key in projection:
            if any(secret in key for secret in ("password", "secret", "session", "cancel_reason", "result")):
                raise AssertionError("Private field requested")
        self.owner.calls.append((self.name, deepcopy(query), deepcopy(projection)))
        # Return extras deliberately: output must be reconstructed from validated public fields.
        return [row for row in self.owner.documents[self.name] if matches(row, query)]

    def find_one(self, query, projection, *, session):
        found = self.read(query, projection, session)
        return deepcopy(found[0]) if found else None

    def find(self, query, projection, *, session):
        return Cursor(self.owner, self.read(query, projection, session))

    def __getattr__(self, _):
        raise AssertionError("Database mutation or unsupported operation")


class Snapshot:
    def __init__(self, owner):
        self.owner, self.active, self.entered = owner, False, False

    def __enter__(self):
        if self.entered:
            self.active = True
        self.entered = True
        return self

    def __exit__(self, *_):
        self.active = False

    def start_transaction(self, **options):
        self.owner.transaction_options.append(options)
        if options["read_concern"].document != {"level": "snapshot"}:
            raise AssertionError("Missing snapshot concern")
        return self


class Client:
    def __init__(self, documents):
        self.documents, self.calls, self.limits, self.sorts, self.transaction_options = documents, [], [], [], []
        self.wesnoth_game = self
        self.session = Snapshot(self)
        for name in documents:
            setattr(self, name, Collection(self, name))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def start_session(self, **options):
        if options != {"causal_consistency": False}:
            raise AssertionError("Unexpected session options")
        return self.session

    def __getattr__(self, _):
        raise AssertionError("Only bounded read collections are available")


def fixtures():
    people = [{"_id": uid(index), "username": name, "username_key": name.casefold(),
        "role": "player", "status": "active", "leader": CHECK.rules.new_leader("spearman"),
        "active_run_id": None, "password_hash": PRIVATE, "private": PRIVATE}
        for index, name in enumerate(("UniPlayer", "UniRecruit", "UniSolo", "UniRival"), 1)]
    teams = [{"_id": uid(20 + index), "name": name, "status": "active", "area_id": "area-1",
        "captain_id": people[index * 2]["_id"], "members": [{"account_id": p["_id"]}
            for p in people[index * 2:index * 2 + 2]], "active_run_id": None, "private": PRIVATE}
        for index, name in enumerate(("Koichi", "RivalPlan"))]
    run = {"_id": uid(100), "kind": "alliance", "state": "draft", "area_id": "area-1",
        "map_id": "isars-cross", "ruleset_version": CHECK.rules.RULESET_VERSION,
        "created_at": NOW, "team_ids": [t["_id"] for t in teams], "lineups": {},
        "approvals": {t["_id"]: t["captain_id"] for t in teams}, "ready": [p["_id"] for p in people],
        "participants": [], "planning_teams": [{"id": t["_id"], "name": t["name"]} for t in teams],
        "cancel_reason": PRIVATE, "private": PRIVATE}
    for index, t in enumerate(teams):
        selected = people[index * 2:index * 2 + 2]
        run["lineups"][t["_id"]] = [p["_id"] for p in selected]
        for p, side in zip(selected, ((1, 4), (2, 3))[index]):
            run["participants"].append({"account_id": p["_id"], "username": p["username"],
                "team_id": t["_id"], "side": side, "leader": deepcopy(p["leader"]), "private": PRIVATE})
    return {"schema_metadata": [{"_id": "alliance", "version": 1}], "accounts": people,
        "teams": teams, "game_runs": [run],
        "areas": [{"_id": "area-1", "enabled": True, "approved_maps": list(CHECK.rules.MAPS)}]}


class PlanCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance plan diagnostic ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.report_path = self.root / "report.json"
        self.uri = ("mongodb://wesnoth_app:" + PRIVATE + "@127.0.0.1:27018/wesnoth_game"
                    "?authSource=wesnoth_game&replicaSet=wesnoth-rs&directConnection=true")
        (self.runtime / "owner.json").write_text(json.dumps({"format": 1, "purpose": "wesnoth-alliance-local"}))
        self.config = self.runtime / "config.json"
        self.config.write_text(json.dumps({"format": 1, "purpose": "wesnoth-alliance-local", "service": {
            "mongo_uri": self.uri, "host": "127.0.0.1", "port": 18765,
            "secret_key": "s" * 64, "bridge_secret": "b" * 64}}))
        self.documents = fixtures()
        self.factory = self.enterContext(mock.patch.object(CHECK, "_client", side_effect=self.new_client))
        self.enterContext(mock.patch("getpass.getpass", side_effect=AssertionError("No prompt permitted")))
        self.enterContext(mock.patch("builtins.input", side_effect=AssertionError("No prompt permitted")))

    def new_client(self, uri):
        self.assertEqual(uri, self.uri)
        self.client = Client(self.documents)
        return self.client

    def collect(self, username="UniPlayer", battle_id=None):
        before = deepcopy(self.documents)
        files = {p.name: p.read_bytes() for p in self.runtime.iterdir() if p.is_file()}
        report = CHECK.collect(self.runtime, username, battle_id)
        self.assertEqual(before, self.documents)
        self.assertEqual(files, {p.name: p.read_bytes() for p in self.runtime.iterdir() if p.is_file()})
        raw = json.dumps(report)
        for private in (PRIVATE, self.uri, "s" * 64, "b" * 64, "password_hash", "cancel_reason"):
            self.assertNotIn(private, raw)
        self.assertFalse(report["database_writes"])
        self.assertLess(len(raw), CHECK.MAX_REPORT_BYTES)
        return report

    def test_snapshot_sanitized_output_and_no_write_contract(self):
        report = self.collect("UNIPLAYER")
        self.assertEqual(report["status"], "collected")
        self.assertEqual(report["active_team_ids"], [uid(20)])
        plan = report["plans"][0]
        self.assertEqual((plan["state"], plan["derived_validity"]), ("draft", "valid"))
        self.assertTrue(all(p["saved_ready"] and p["currently_in_saved_team"] for p in plan["players"]))
        self.assertEqual(len(self.client.transaction_options), 1)
        self.assertEqual(set(name for name, _, _ in self.client.calls), set(self.documents))
        self.assertIn("current on-disk", report["scope"])
        self.assertEqual(set(report["disk_logic_sha256"]), {"alliance/domain.py", "alliance/rules.py"})
        self.assertTrue(all(len(value) == 64 for value in report["disk_logic_sha256"].values()))

    def test_leave_and_cancel_separate_saved_consent_from_live_membership(self):
        self.documents["teams"][1]["members"].pop()
        stale = self.collect()["plans"][0]
        self.assertEqual(stale["derived_validity"], "roster_changed")
        recruit = stale["players"][-1]
        self.assertTrue(recruit["saved_ready"])
        self.assertFalse(recruit["currently_in_saved_team"])
        self.documents["game_runs"][0].update(state="cancelled", finished_at=NOW + timedelta(minutes=2))
        cancelled = self.collect()["plans"][0]
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["players"], stale["players"])
        self.assertIsNotNone(cancelled["finished_at"])

    def test_cancelled_valid_snapshot_can_keep_mixed_saved_readiness_and_leaders(self):
        run = self.documents["game_runs"][0]
        run.update(state="cancelled", finished_at=NOW)
        run["ready"].remove(uid(3))
        self.documents["accounts"][2]["leader"] = CHECK.rules.new_leader("elvish-fighter")
        run["participants"][2]["leader"] = CHECK.rules.new_leader("elvish-fighter")
        record = self.collect(battle_id=uid(100))["plans"][0]
        self.assertEqual((record["state"], record["derived_validity"]), ("cancelled", "valid"))
        self.assertEqual(record["players"][2]["saved_unit_type"], "Elvish Fighter")
        self.assertFalse(record["players"][2]["saved_ready"])
        self.assertTrue(record["players"][3]["saved_ready"])
        self.assertTrue(record["players"][3]["currently_in_saved_team"])

    def test_former_member_remains_inspectable_but_unrelated_plan_not_selected(self):
        self.documents["teams"][1]["members"].pop()
        report = self.collect("UniRival", uid(100))
        self.assertEqual(report["active_team_ids"], [])
        self.assertEqual(len(report["plans"]), 1)
        self.assertEqual(self.collect(battle_id=uid(999))["outcome"], "battle_not_found")
        outsider = deepcopy(self.documents["accounts"][0])
        outsider.update(_id=uid(99), username="OtherPlayer", username_key="otherplayer")
        self.documents["accounts"].append(outsider)
        self.assertEqual(self.collect("OtherPlayer", uid(100))["outcome"], "battle_not_found")
        self.assertEqual(self.collect("OtherPlayer")["plans"], [])

    def test_latest_ten_are_bounded_sorted_and_exact_old_plan_can_be_selected(self):
        initial = deepcopy(self.documents["game_runs"][0])
        for index in range(1, 12):
            value = deepcopy(initial)
            value.update(_id=uid(100 + index), created_at=NOW + timedelta(minutes=index))
            self.documents["game_runs"].append(value)
        report = self.collect()
        self.assertEqual(len(report["plans"]), 10)
        self.assertTrue(report["has_more"])
        self.assertEqual([r["id"] for r in report["plans"]], [uid(index) for index in range(111, 101, -1)])
        self.assertEqual(self.client.sorts, [[("created_at", -1), ("_id", -1)]])
        self.assertIn(11, self.client.limits)
        exact = self.collect(battle_id=uid(100))
        self.assertEqual([r["id"] for r in exact["plans"]], [uid(100)])
        self.assertFalse(exact["has_more"])

    def test_missing_context_has_fixed_markers_and_does_not_synthesize_data(self):
        for collection, position, validity, error in (("teams", 1, "team_unavailable", "team_missing"),
                ("accounts", 3, "player_unavailable", "account_missing"),
                ("areas", 0, "map_unavailable", "area_missing")):
            original = deepcopy(self.documents)
            self.documents[collection].pop(position)
            record = self.collect()["plans"][0]
            self.assertEqual(record["derived_validity"], validity)
            self.assertIn(error, record["context_errors"])
            self.documents = original

    def test_all_other_validity_reasons_come_from_existing_domain_logic(self):
        cases = (("game_runs", "ruleset_version", "future-v2", "rules_changed"),
                 ("teams", "area_id", "different-area", "area_changed"),
                 ("areas", "enabled", False, "map_unavailable"),
                 ("accounts", "status", "suspended", "player_unavailable"),
                 ("accounts", "active_run_id", uid(999), "busy"))
        for collection, key, value, expected in cases:
            before = deepcopy(self.documents)
            self.documents[collection][0][key] = value
            self.assertEqual(self.collect()["plans"][0]["derived_validity"], expected)
            self.documents = before
        self.documents["accounts"][3]["leader"]["total_experience"] = 1
        self.assertEqual(self.collect()["plans"][0]["derived_validity"], "leader_changed")

    def test_invalid_selectors_configuration_and_schema_fail_without_private_output(self):
        for username in (None, "ab", "x" * 25, "name\n", {"$ne": ""}):
            self.assertEqual(self.collect(username)["outcome"], "invalid_username")
        for key in ("", "not-a-uuid", {"$ne": ""}):
            self.assertEqual(self.collect(battle_id=key)["outcome"], "invalid_battle_id")
        self.factory.assert_not_called()
        original = self.config.read_bytes()
        for raw in (b"x" * 32769, original.replace(b"127.0.0.1:27018", b"example.com:27018"),
                    original.replace(b"wesnoth_game", b"other_game"), original.replace(b"27018", b"27017"),
                    original.replace(b'"format": 1', b'"format": 1, "format": 1')):
            self.config.write_bytes(raw)
            self.assertEqual(self.collect()["outcome"], "invalid_configuration")
        self.factory.assert_not_called()
        self.config.write_bytes(original)
        for schema in (None, True, 2):
            self.documents["schema_metadata"] = [] if schema is None else [{"_id": "alliance", "version": schema}]
            self.assertEqual(self.collect()["outcome"], "unsupported_database")

    def test_malformed_records_are_fixed_errors_with_no_partial_plan_dump(self):
        cases = (("accounts", "username", "bad\nname", "invalid_account_record"),
            ("accounts", "leader", {"private": PRIVATE}, "invalid_account_record"),
            ("teams", "members", [{"account_id": uid(1)}] * 9, "invalid_team_record"),
            ("teams", "captain_id", PRIVATE, "invalid_team_record"),
            ("game_runs", "state", PRIVATE, "invalid_plan_record"),
            ("game_runs", "ready", [uid(999)], "invalid_plan_record"),
            ("game_runs", "approvals", {"unknown-team": uid(1)}, "invalid_plan_record"),
            ("game_runs", "participants", [], "invalid_plan_record"),
            ("game_runs", "created_at", PRIVATE, "invalid_plan_record"),
            ("game_runs", "map_id", PRIVATE, "invalid_plan_record"),
            ("areas", "approved_maps", [PRIVATE], "invalid_area_record"))
        for collection, key, value, expected in cases:
            with self.subTest(collection=collection, key=key):
                before = deepcopy(self.documents)
                self.documents[collection][0][key] = value
                report = self.collect()
                self.assertEqual(report["outcome"], expected)
                self.assertEqual(report["plans"], [])
                self.documents = before

    def test_duplicate_ids_wrong_lineup_membership_and_boolean_numbers_are_rejected(self):
        original = deepcopy(self.documents)
        for collection, index, expected in (("game_runs", 0, "invalid_plan_record"),
                ("accounts", 3, "invalid_account_record"), ("teams", 0, "invalid_team_record")):
            self.documents[collection].append(deepcopy(self.documents[collection][index]))
            self.assertEqual(self.collect()["outcome"], expected)
            self.documents = deepcopy(original)
        changes = (
            lambda run: run["participants"][0].update(account_id=uid(999)),
            lambda run: run["participants"][0].update(team_id=uid(999)),
            lambda run: run["participants"][0].update(side=True),
            lambda run: run["participants"][0]["leader"].update(level=True),
            lambda run: run["ready"].append(run["ready"][0]),
            lambda run: run["lineups"][uid(20)].__setitem__(1, uid(1)),
            lambda run: run["planning_teams"][0].update(id=uid(999)),
        )
        for change in changes:
            change(self.documents["game_runs"][0])
            self.assertEqual(self.collect()["outcome"], "invalid_plan_record")
            self.documents = deepcopy(original)

    def test_missing_selected_account_and_admin_are_fixed_errors(self):
        self.documents["accounts"].pop(0)
        self.assertEqual(self.collect()["outcome"], "account_missing")
        self.documents = fixtures()
        self.documents["accounts"][0]["role"] = "admin"
        self.assertEqual(self.collect()["outcome"], "account_ineligible")

    def test_legitimate_bson_long_leader_experience_and_legacy_names_are_supported(self):
        self.documents["accounts"][0]["leader"]["total_experience"] = Int64(0)
        run = self.documents["game_runs"][0]
        del run["planning_teams"]
        for participant in run["participants"]:
            del participant["username"]
        result = self.collect()["plans"][0]
        self.assertEqual(result["derived_validity"], "valid")
        self.assertIsNone(result["players"][0]["saved_username"])
        self.assertEqual(result["players"][0]["current_username"], "UniPlayer")
        self.assertIsNone(result["teams"][0]["saved_name"])
        self.assertEqual(result["teams"][0]["current_name"], "Koichi")

    def test_guarded_configuration_rejects_symlink_and_hardlink(self):
        preserved = self.runtime / "preserved.json"
        self.config.rename(preserved)
        for kind in ("symlink", "hardlink"):
            if kind == "symlink":
                self.config.symlink_to(preserved)
            else:
                os.link(preserved, self.config)
            try:
                self.assertEqual(CHECK.collect(self.runtime)["outcome"], "invalid_configuration")
            finally:
                self.config.unlink()
        self.factory.assert_not_called()

    def test_database_and_unexpected_failures_never_expose_exception_details(self):
        for exception, expected in ((ServerSelectionTimeoutError(self.uri), "database_unavailable"),
                (RuntimeError(PRIVATE), "unexpected_error"), (CHECK.DiagnosticError(PRIVATE), "unexpected_error"),
                (KeyboardInterrupt(), "collection_cancelled")):
            self.factory.side_effect = exception
            self.assertEqual(self.collect()["outcome"], expected)

    def test_main_exclusive_sanitized_report_and_no_overwrite(self):
        args = ["--runtime", str(self.runtime), "--report", str(self.report_path)]
        console = io.StringIO()
        with redirect_stdout(console):
            self.assertEqual(CHECK.main(args), 0)
        self.assertIn("ALLIANCE PLAN STATE COLLECTED", console.getvalue())
        self.assertIn("Report saved:", console.getvalue())
        original = self.report_path.read_bytes()
        self.assertNotIn(PRIVATE, original.decode() + console.getvalue())
        with mock.patch.object(CHECK, "collect") as collect, redirect_stdout(io.StringIO()):
            self.assertEqual(CHECK.main(args), 1)
        collect.assert_not_called()
        self.assertEqual(self.report_path.read_bytes(), original)

    def test_output_path_guards_preserve_runtime_and_link_targets_before_collection(self):
        redirected = self.root / "redirected"
        redirected.symlink_to(self.runtime, target_is_directory=True)
        existing = self.root / "existing.json"
        existing.write_text(PRIVATE)
        linked = self.root / "linked.json"
        linked.symlink_to(existing)
        targets = (self.runtime / "report.json", redirected / "report.json", linked,
                   self.root / "missing" / "new.json", Path("relative.json"), self.root / ".." / "new.json")
        for target in targets:
            with mock.patch.object(CHECK, "collect") as collect, redirect_stdout(io.StringIO()):
                self.assertEqual(CHECK.main(["--runtime", str(self.runtime), "--report", str(target)]), 1)
            collect.assert_not_called()
        self.assertEqual(existing.read_text(), PRIVATE)
        self.assertFalse((self.runtime / "report.json").exists())

    def test_report_byte_cap_and_invalid_cli_do_not_echo_extra_input(self):
        report = CHECK.empty_report()
        report["scope"] = PRIVATE * CHECK.MAX_REPORT_BYTES
        with mock.patch.object(CHECK, "collect", return_value=report), redirect_stdout(io.StringIO()):
            self.assertEqual(CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report_path)]), 1)
        saved = json.loads(self.report_path.read_text())
        self.assertEqual(saved["outcome"], "report_too_large")
        self.assertNotIn(PRIVATE, self.report_path.read_text())
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as caught:
            CHECK.main(["--runtime", str(self.runtime), "--report", str(self.report_path), "--password", PRIVATE])
        self.assertEqual(caught.exception.code, 1)
        self.assertNotIn(PRIVATE, output.getvalue())
        self.factory.assert_not_called()


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGOD"), "Requires explicit disposable MongoDB binary")
class RealPlanCheckTests(unittest.TestCase):
    def test_authenticated_snapshot_observes_leave_cancel_and_preserves_all_database_records(self):
        from alliance.config import Settings
        from alliance.deployment import initialize, _start_mongo, _stop_owned, _client
        from alliance.domain import AllianceService
        with tempfile.TemporaryDirectory(prefix="alliance plan state real ") as directory:
            runtime = Path(directory) / "runtime"
            mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
            with redirect_stdout(io.StringIO()), mock.patch("getpass.getpass", return_value=secrets.token_urlsafe(24)):
                initialize(runtime, mongod, admin_username="Operator")
            database = _start_mongo(runtime, mongod)
            try:
                with _client(Settings.load(runtime).mongo_uri) as client:
                    db = client.wesnoth_game
                    service = AllianceService(db)
                    people = [service.register(name, "$argon2id$fixture-not-used-for-login", "spearman")["_id"]
                              for name in ("UniPlayer", "UniRecruit", "UniSolo", "UniRival")]
                    teams = []
                    for index, name in enumerate(("Koichi", "RivalPlan")):
                        captain, member = people[index * 2:index * 2 + 2]
                        own = service.create_team(captain, name)["_id"]
                        service.request_join(member, own)
                        service.approve_member(captain, own, member)
                        teams.append(own)
                    planned = service.directory_propose_battle(people[0], teams[0], teams[1], "isars-cross",
                        [{"team_id": team_id, "account_ids": people[index * 2:index * 2 + 2]}
                         for index, team_id in enumerate(teams)])
                    for captain in (people[0], people[2]):
                        service.directory_approve_battle(captain, planned["id"])
                    for player in people:
                        service.directory_battle_ready(player, planned["id"], True)

                    def inspect(expected_state, expected_validity):
                        before = {name: list(db[name].find({}).sort("_id", 1)) for name in db.list_collection_names()}
                        report = CHECK.collect(runtime, "UniPlayer", planned["id"])
                        after = {name: list(db[name].find({}).sort("_id", 1)) for name in db.list_collection_names()}
                        self.assertEqual(before, after)
                        self.assertEqual(report["status"], "collected", report["outcome"])
                        result = report["plans"][0]
                        self.assertEqual((result["state"], result["derived_validity"]), (expected_state, expected_validity))
                        self.assertEqual(result["derived_validity"], service.directory_battle_detail(people[0], planned["id"])["validity"])
                        self.assertTrue(all(player["saved_ready"] for player in result["players"]))
                        print("PASS diagnostic snapshot: " + expected_state + "/" + expected_validity + "; all database records unchanged", flush=True)
                        return result

                    inspect("draft", "valid")
                    service.directory_leave_team(people[3], teams[1], False)
                    left = inspect("draft", "roster_changed")
                    self.assertFalse(left["players"][-1]["currently_in_saved_team"])
                    service.directory_cancel_battle(people[2], planned["id"])
                    cancelled = inspect("cancelled", "roster_changed")
                    self.assertEqual(left["players"], cancelled["players"])
                    self.assertIsNotNone(cancelled["finished_at"])
                    self.assertEqual(db.auth_sessions.count_documents({}), 0)
                    self.assertEqual(db.auth_attempts.count_documents({}), 0)
            finally:
                _stop_owned(database, runtime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
