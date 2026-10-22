"""Collect bounded, read-only saved-plan and current-membership facts from local MongoDB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo import ReadPreference, timeout
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern

from alliance.domain import AllianceService
from alliance import rules
from alliance.deployment import _client
from tools.check_alliance_login import DiagnosticError, local_settings, USERNAME, UUID

ROOT = Path(__file__).resolve().parents[1]
MAX_PLANS = 10
MAX_REPORT_BYTES = 131072
FAILURES = frozenset({"invalid_configuration", "invalid_username", "invalid_battle_id",
    "unsupported_database", "database_unavailable", "account_missing", "account_ineligible",
    "battle_not_found", "invalid_account_record", "invalid_team_record", "invalid_plan_record",
    "invalid_area_record", "logic_unavailable", "report_too_large", "collection_cancelled",
    "unexpected_error"})
AREA_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
TEAM_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{2,39}\Z")
VERSION = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
ACCOUNT_FIELDS = {key: 1 for key in ("_id", "username", "username_key", "role", "status", "leader", "active_run_id")}
TEAM_FIELDS = {key: 1 for key in ("_id", "name", "area_id", "status", "captain_id", "members.account_id", "active_run_id")}
RUN_FIELDS = {key: 1 for key in ("_id", "kind", "state", "ruleset_version", "map_id", "area_id",
    "team_ids", "lineups", "approvals", "ready", "participants.account_id", "participants.team_id",
    "participants.side", "participants.username", "participants.leader", "planning_teams.id",
    "planning_teams.name", "created_at", "finished_at")}
AREA_FIELDS = {key: 1 for key in ("_id", "enabled", "approved_maps")}
SCOPE = (
    "Direct local database snapshot only. Validity is derived using the current on-disk domain logic; "
    "this does not identify the code loaded by the running HTTP service or bridge, or the installed Android APK. "
    "Saved Ready flags and fixed lineups are history, not a current-membership check. "
    "No login, mutation, database initialization or gameplay is performed."
)


def require(condition, error):
    if not condition:
        raise DiagnosticError(error)


def text(value, pattern, error):
    require(isinstance(value, str) and pattern.fullmatch(value) is not None, error)
    return value


def identifier(value, error, nullable=False):
    return None if nullable and value is None else text(value, UUID, error)


def sequence(value, maximum, error):
    require(isinstance(value, list) and len(value) <= maximum, error)
    return value


def timestamp(value, error):
    require(isinstance(value, datetime) and value.utcoffset() is not None, error)
    result = value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    require(len(result) == 20, error)
    return result


def leader(value, error):
    keys = {"starter_id", "unit_type", "level", "experience", "total_experience", "advancement_choices"}
    require(isinstance(value, dict) and set(value) == keys, error)
    require(isinstance(value["starter_id"], str) and value["starter_id"] in rules.STARTERS, error)
    require(isinstance(value["unit_type"], str) and value["unit_type"] in rules.UNIT_TYPES, error)
    for key in ("level", "experience", "total_experience"):
        require(isinstance(value[key], int) and not isinstance(value[key], bool)
                and 0 <= value[key] <= 9223372036854775807, error)
    require(value["level"] == rules.UNIT_TYPES[value["unit_type"]][0], error)
    choices = sequence(value["advancement_choices"], 3, error)
    require(all(isinstance(choice, str) and choice in rules.UNIT_TYPES for choice in choices), error)
    require(len(set(choices)) == len(choices), error)
    return {**{key: value[key] for key in keys - {"advancement_choices"}}, "advancement_choices": list(choices)}


def account(value):
    error = "invalid_account_record"
    require(isinstance(value, dict), error)
    result = {"_id": identifier(value.get("_id"), error),
              "username": text(value.get("username"), USERNAME, error)}
    require(value.get("username_key") == result["username"].casefold(), error)
    require(value.get("role") in ("player", "admin") and value.get("status") in ("active", "suspended"), error)
    require("active_run_id" in value, error)
    result.update(role=value["role"], status=value["status"], leader=leader(value.get("leader"), error),
                  active_run_id=identifier(value["active_run_id"], error, nullable=True))
    return result


def team(value):
    error = "invalid_team_record"
    require(isinstance(value, dict), error)
    result = {"_id": identifier(value.get("_id"), error), "name": text(value.get("name"), TEAM_NAME, error),
              "area_id": text(value.get("area_id"), AREA_ID, error)}
    require(value.get("status") in ("active", "archived") and "captain_id" in value and "active_run_id" in value, error)
    members = sequence(value.get("members"), rules.TEAM_CAPACITY, error)
    require(all(isinstance(member, dict) for member in members), error)
    ids = [identifier(member.get("account_id"), error) for member in members]
    require(len(ids) == len(set(ids)), error)
    captain = identifier(value["captain_id"], error, nullable=True)
    require((value["status"] == "active" and captain in ids) or
            (value["status"] == "archived" and captain is None and not ids), error)
    result.update(status=value["status"], captain_id=captain, members=[{"account_id": key} for key in ids],
                  active_run_id=identifier(value["active_run_id"], error, nullable=True))
    return result


def plan(value):
    error = "invalid_plan_record"
    require(isinstance(value, dict) and value.get("kind") == "alliance", error)
    result = {"_id": identifier(value.get("_id"), error), "kind": "alliance",
              "area_id": text(value.get("area_id"), AREA_ID, error),
              "ruleset_version": text(value.get("ruleset_version"), VERSION, error)}
    require(value.get("state") in ("draft", "running", "completed", "cancelled"), error)
    require(isinstance(value.get("map_id"), str) and value["map_id"] in rules.MAPS, error)
    result.update(state=value["state"], map_id=value["map_id"], created_at=timestamp(value.get("created_at"), error),
                  finished_at=None if value.get("finished_at") is None else timestamp(value["finished_at"], error))
    ids = sequence(value.get("team_ids"), 2, error)
    require(len(ids) == 2, error)
    result["team_ids"] = [identifier(key, error) for key in ids]
    require(len(set(ids)) == 2 and isinstance(value.get("lineups"), dict) and set(value["lineups"]) == set(ids), error)
    size = rules.MAPS[result["map_id"]]["size"]
    result["lineups"] = {}
    for key in ids:
        selected = sequence(value["lineups"][key], size, error)
        require(len(selected) == size, error)
        result["lineups"][key] = [identifier(player, error) for player in selected]
    flat = [player for key in ids for player in result["lineups"][key]]
    require(len(flat) == len(set(flat)), error)
    participants = sequence(value.get("participants"), size * 2, error)
    require(len(participants) == size * 2, error)
    result["participants"] = []
    for index, participant in enumerate(participants):
        require(isinstance(participant, dict), error)
        team_index, seat_index = divmod(index, size)
        require(participant.get("account_id") == flat[index] and participant.get("team_id") == ids[team_index], error)
        side = participant.get("side")
        require(type(side) is int and side == rules.MAPS[result["map_id"]]["sides"][team_index][seat_index], error)
        entry = {"account_id": flat[index], "team_id": ids[team_index], "side": side,
                 "leader": leader(participant.get("leader"), error)}
        if "username" in participant:
            entry["username"] = text(participant["username"], USERNAME, error)
        result["participants"].append(entry)
    ready = sequence(value.get("ready"), size * 2, error)
    result["ready"] = [identifier(key, error) for key in ready]
    require(len(set(ready)) == len(ready) and set(ready).issubset(flat), error)
    approvals = value.get("approvals")
    require(isinstance(approvals, dict) and set(approvals).issubset(ids), error)
    result["approvals"] = {key: identifier(actor, error) for key, actor in approvals.items()}
    if "planning_teams" in value:
        saved = sequence(value["planning_teams"], 2, error)
        require(len(saved) == 2, error)
        result["planning_teams"] = []
        for key, item in zip(ids, saved):
            require(isinstance(item, dict) and item.get("id") == key, error)
            result["planning_teams"].append({"id": key, "name": text(item.get("name"), TEAM_NAME, error)})
    return result


def area(value):
    error = "invalid_area_record"
    require(isinstance(value, dict), error)
    key = text(value.get("_id"), AREA_ID, error)
    require(type(value.get("enabled")) is bool, error)
    maps = sequence(value.get("approved_maps"), len(rules.MAPS), error)
    require(all(isinstance(item, str) and item in rules.MAPS for item in maps), error)
    require(len(set(maps)) == len(maps), error)
    return {"_id": key, "enabled": value["enabled"], "approved_maps": list(maps)}


def bounded_find(collection, query, fields, session, limit, error, sort=None):
    cursor = collection.find(query, fields, session=session)
    if sort:
        cursor = cursor.sort(sort)
    documents = list(cursor.limit(limit))
    require(len(documents) <= limit, error)
    return documents


def indexed(documents, validate, expected_ids, error):
    result = {}
    for document in documents:
        value = validate(document)
        require(value["_id"] in expected_ids and value["_id"] not in result, error)
        result[value["_id"]] = value
    return result


def plan_report(run, teams, accounts, areas):
    current = [teams.get(key) for key in run["team_ids"]]
    region = areas.get(run["area_id"])
    validity = AllianceService._planning_validity(run, current, accounts, region)
    result = {"id": run["_id"], "state": run["state"], "created_at": run["created_at"],
        "finished_at": run["finished_at"], "area_id": run["area_id"], "map_id": run["map_id"],
        "ruleset_matches_disk": run["ruleset_version"] == rules.RULESET_VERSION,
        "derived_validity": validity, "teams": [], "players": [], "context_errors": []}
    errors = set()
    if region is None:
        errors.add("area_missing")
    for index, (key, present) in enumerate(zip(run["team_ids"], current)):
        saved = run.get("planning_teams")
        result["teams"].append({"id": key, "saved_name": saved[index]["name"] if saved else None,
            "current_found": present is not None, "current_name": present["name"] if present else None,
            "current_status": present["status"] if present else None,
            "current_captain_id": present["captain_id"] if present else None,
            "current_captain_account_found": bool(present and present["captain_id"] in accounts),
            "current_member_ids": [member["account_id"] for member in present["members"]] if present else [],
            "saved_approval_actor_id": run["approvals"].get(key),
            "approved_by_current_captain": bool(present and present["status"] == "active" and
                run["approvals"].get(key) == present["captain_id"])})
        if present is None:
            errors.add("team_missing")
        elif present["captain_id"] and present["captain_id"] not in accounts:
            errors.add("account_missing")
    for saved in run["participants"]:
        present = accounts.get(saved["account_id"])
        current_team = teams.get(saved["team_id"])
        result["players"].append({"id": saved["account_id"], "saved_team_id": saved["team_id"],
            "saved_username": saved.get("username"), "current_username": present["username"] if present else None,
            "side": saved["side"], "saved_unit_type": saved["leader"]["unit_type"],
            "saved_level": saved["leader"]["level"], "saved_ready": saved["account_id"] in run["ready"],
            "currently_in_saved_team": bool(current_team and current_team["status"] == "active" and
                saved["account_id"] in [member["account_id"] for member in current_team["members"]]),
            "current_account_found": present is not None,
            "current_account_active_player": bool(present and present["status"] == "active" and present["role"] == "player"),
            "leader_snapshot_matches": present["leader"] == saved["leader"] if present else None})
        if present is None:
            errors.add("account_missing")
    result["context_errors"] = sorted(errors)
    return result


def read_snapshot(db, session, username, battle_id):
    schema = db.schema_metadata.find_one({"_id": "alliance"}, {"_id": 0, "version": 1}, session=session)
    require(isinstance(schema, dict) and type(schema.get("version")) is int and schema["version"] == 1, "unsupported_database")
    raw_actor = db.accounts.find_one({"username_key": username.casefold()}, ACCOUNT_FIELDS, session=session)
    require(raw_actor is not None, "account_missing")
    actor = account(raw_actor)
    require(actor["username"].casefold() == username.casefold(), "invalid_account_record")
    require(actor["role"] == "player", "account_ineligible")
    own_teams = bounded_find(db.teams, {"status": "active", "members.account_id": actor["_id"]},
                             TEAM_FIELDS, session, 2, "invalid_team_record")
    require(len(own_teams) <= 1, "invalid_team_record")
    own = [team(value) for value in own_teams]
    require(all(value["status"] == "active" and actor["_id"] in [m["account_id"] for m in value["members"]] for value in own), "invalid_team_record")
    own_ids = [value["_id"] for value in own]
    query = {"kind": "alliance", "$or": [{"team_ids": {"$in": own_ids}}, {"participants.account_id": actor["_id"]}]}
    if battle_id:
        query["_id"] = battle_id
    raw_runs = bounded_find(db.game_runs, query, RUN_FIELDS, session, MAX_PLANS + 1,
                           "invalid_plan_record", [("created_at", -1), ("_id", -1)])
    if battle_id:
        require(len(raw_runs) == 1, "battle_not_found")
    runs = [plan(value) for value in raw_runs[:MAX_PLANS]]
    require(len({run["_id"] for run in runs}) == len(runs), "invalid_plan_record")
    for run in runs:
        require((not battle_id or run["_id"] == battle_id) and (set(own_ids).intersection(run["team_ids"]) or
            any(player["account_id"] == actor["_id"] for player in run["participants"])), "invalid_plan_record")
    team_ids = {key for run in runs for key in run["team_ids"]} | set(own_ids)
    teams = indexed(bounded_find(db.teams, {"_id": {"$in": sorted(team_ids)}}, TEAM_FIELDS,
        session, 22, "invalid_team_record"), team, team_ids, "invalid_team_record") if team_ids else {}
    account_ids = {player["account_id"] for run in runs for player in run["participants"]}
    account_ids.update(value["captain_id"] for value in teams.values() if value["captain_id"])
    accounts = indexed(bounded_find(db.accounts, {"_id": {"$in": sorted(account_ids)}}, ACCOUNT_FIELDS,
        session, 101, "invalid_account_record"), account, account_ids, "invalid_account_record") if account_ids else {}
    area_ids = {run["area_id"] for run in runs}
    areas = indexed(bounded_find(db.areas, {"_id": {"$in": sorted(area_ids)}}, AREA_FIELDS,
        session, 11, "invalid_area_record"), area, area_ids, "invalid_area_record") if area_ids else {}
    return {"account": {"id": actor["_id"], "username": actor["username"], "status": actor["status"]},
        "active_team_ids": own_ids, "has_more": len(raw_runs) > MAX_PLANS,
        "plans": [plan_report(run, teams, accounts, areas) for run in runs]}


def logic_hashes():
    result = {}
    for name in ("alliance/domain.py", "alliance/rules.py"):
        with (ROOT / name).open("rb") as source:
            raw = source.read(1048577)
        require(len(raw) <= 1048576, "logic_unavailable")
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def empty_report():
    return {"format": 1, "purpose": "wesnoth-alliance-plan-state", "status": "failed",
        "outcome": "unexpected_error", "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": "127.0.0.1:27018", "database": "wesnoth_game", "database_writes": False,
        "read_concern": "snapshot", "maximum_plans": MAX_PLANS, "account": None,
        "active_team_ids": [], "has_more": False, "plans": [], "disk_logic_sha256": {}, "scope": SCOPE}


def collect(runtime, username="UniPlayer", battle_id=None):
    report = empty_report()
    try:
        text(username, USERNAME, "invalid_username")
        if battle_id is not None:
            identifier(battle_id, "invalid_battle_id")
        settings = local_settings(runtime)
        hashes = logic_hashes()
        with _client(settings.mongo_uri) as client, timeout(10):
            with client.start_session(causal_consistency=False) as session:
                with session.start_transaction(read_concern=ReadConcern("snapshot"), read_preference=ReadPreference.PRIMARY):
                    facts = read_snapshot(client.wesnoth_game, session, username, battle_id)
        report.update(facts, disk_logic_sha256=hashes, status="collected", outcome="collected")
    except DiagnosticError as error:
        report["outcome"] = error.args[0] if error.args and error.args[0] in FAILURES else "unexpected_error"
    except PyMongoError:
        report["outcome"] = "database_unavailable"
    except (KeyboardInterrupt, EOFError):
        report["outcome"] = "collection_cancelled"
    except Exception:
        report["outcome"] = "unexpected_error"
    return report


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(1, "ALLIANCE PLAN STATE FAILED: invalid arguments; no password argument is accepted.\n")


def report_target(report, runtime):
    if not report.is_absolute() or ".." in report.parts or not runtime.is_absolute() or ".." in runtime.parts:
        raise ValueError()
    for parent in report.parents:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError()
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise ValueError()
    if report.resolve().is_relative_to(runtime.resolve()):
        raise ValueError()


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--username", default="UniPlayer")
    parser.add_argument("--battle-id")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report_target(args.report, args.runtime)
        # Exclusive reservation precedes configuration/database reads. No existing output is overwritten.
        with args.report.open("x", encoding="ascii", newline="\n") as output:
            report = collect(args.runtime, args.username, args.battle_id)
            encoded = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
            if len(encoded.encode("ascii")) > MAX_REPORT_BYTES:
                report = empty_report()
                report["outcome"] = "report_too_large"
                encoded = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
            output.write(encoded)
    except (OSError, ValueError, RuntimeError):
        print("ALLIANCE PLAN STATE FAILED: report unavailable; existing files preserved.")
        return 1
    print("Report saved: " + str(args.report))
    print("outcome=" + report["outcome"] + "; plans=" + str(len(report["plans"])) + "; has_more=" + str(report["has_more"]))
    print("Direct database reads only. Saved readiness and current membership are reported separately.")
    print("ALLIANCE PLAN STATE " + ("COLLECTED" if report["status"] == "collected" else "FAILED"))
    return 0 if report["status"] == "collected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
