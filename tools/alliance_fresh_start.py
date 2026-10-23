"""Create the unified game's empty database beside the retained legacy runtime.

The existing database is never deleted, renamed or copied into the fresh game.
Initialization uses the existing hidden administrator-password prompt. This tool
must not run under a transcript or accept passwords as command-line arguments.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.deployment import (initialize, owned_runtime, _write_new,
                                 InitializationError, _initialization_reason)
from alliance.schema import SCHEMA_VERSION
from alliance.runtime_lock import runtime_lock
from tools import alliance_maintenance as maintenance
from tools.alliance_workflow import workflow_lock

PURPOSE = "wesnoth-unified-fresh-game"
MARKER = "fresh-start.json"
COMPLETE = "fresh-start-complete.json"


def report_initialization_error(error):
    print("UNIFIED FRESH START STOPPED: initialization_incomplete")
    print(f"stage={error.stage}; reason={error.reason}")
    if error.cleanup_reason is not None:
        print(f"cleanup_stage=database-shutdown; cleanup_reason={error.cleanup_reason}")
        print("Database shutdown was not verified. Keep services stopped and send these diagnostic lines.")
    else:
        guidance = {
            "password_mismatch": "The two password entries did not match. Rerun the same command and enter the same password twice.",
            "invalid_password_length": "The administrator password must contain 12-128 characters. Rerun the same command with a password in that range.",
            "username_input_ended": "Username input ended. Rerun the same command in an interactive PowerShell window.",
            "invalid_admin_username": "Use 3-24 ASCII letters, digits or underscores for the administrator username.",
            "password_input_unavailable": "Hidden password input was unavailable or ended. Use an interactive PowerShell window without input redirection.",
            "interrupted": "Setup was interrupted. Keep the same runtime and backup paths when resuming.",
        }
        print(guidance.get(error.reason, "Send the stage and reason above for review; do not send passwords or private runtime files."))
    print("Keep the existing backup and both runtime folders. Do not delete files or choose a new destination.")


def checked_backup(archive):
    archive = maintenance.local_path(archive)
    if (archive / "INCOMPLETE").exists():
        raise maintenance.MaintenanceError("backup_incomplete")
    manifest = json.loads(maintenance.read_small(archive / "manifest.json", 8 * 1024**2))
    if (manifest.get("purpose") != maintenance.PURPOSE or manifest.get("format") != 1
            or manifest.get("mongodb_version") != maintenance.MONGO_VERSION
            or manifest.get("producer_schema_version") not in (1, SCHEMA_VERSION)):
        raise maintenance.MaintenanceError("unsupported_backup_version")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(maintenance.CONTROLS) - files.keys():
        raise maintenance.MaintenanceError("invalid_backup_manifest")
    if maintenance.inventory(archive / "runtime") != files:
        raise maintenance.MaintenanceError("backup_integrity_failed")
    return archive, files, maintenance.digest(archive / "manifest.json")


def fresh_start(previous, archive, destination, mongod):
    if SCHEMA_VERSION < 2:
        raise maintenance.MaintenanceError("unified_schema_not_installed")
    source = maintenance.validate_runtime(previous)
    archive, archived, manifest_digest = checked_backup(archive)
    target = maintenance.local_path(destination)
    for excluded in (source, archive):
        if target == excluded or target in excluded.parents or excluded in target.parents:
            raise maintenance.MaintenanceError("overlapping_destination")
    identity = {"purpose": PURPOSE, "format": 1, "schema_version": SCHEMA_VERSION,
                "previous_runtime": str(source), "backup": str(archive),
                "backup_manifest": manifest_digest}
    with ExitStack() as stack:
        stack.enter_context(runtime_lock(source))
        ports = stack.enter_context(maintenance.reserved_ports())
        stack.enter_context(maintenance.battle_storage_lock(source))
        if maintenance.inventory(source) != archived:
            raise maintenance.MaintenanceError("backup_does_not_match_stopped_runtime")
        if target.exists():
            owned_runtime(target)
            if json.loads(maintenance.read_small(target / MARKER)) != identity:
                raise maintenance.MaintenanceError("destination_is_not_this_fresh_start")
        else:
            # A partial directory with no complete identity is deliberately not
            # adopted on retry. No unrelated folder can become a reset target.
            owned_runtime(target, create=True)
            _write_new(target / MARKER, json.dumps(identity, sort_keys=True) + "\n")
        stack.enter_context(workflow_lock(target))
        if (target / COMPLETE).exists():
            if json.loads(maintenance.read_small(target / COMPLETE)) != identity:
                raise maintenance.MaintenanceError("fresh_start_completion_changed")
            maintenance.validate_runtime(target)
            return {"reused": True, "previous_runtime_preserved": True,
                    "database_stopped": True, "schema_version": SCHEMA_VERSION}
        ports[27018].close()
        # initialize itself locks the new runtime, creates fresh random DB and
        # web/session credentials, verifies the schema, and stops its child.
        # It resumes incomplete initialization; it never removes player data.
        initialize(target, mongod)
        maintenance.validate_runtime(target)
        if maintenance.inventory(source) != archived or maintenance.inventory(archive / "runtime") != archived:
            raise maintenance.MaintenanceError("protected_source_changed")
        _write_new(target / COMPLETE, json.dumps(identity, sort_keys=True) + "\n")
    return {"reused": False, "previous_runtime_preserved": True,
            "database_stopped": True, "schema_version": SCHEMA_VERSION}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-runtime", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--mongod", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = fresh_start(args.previous_runtime, args.backup, args.runtime, args.mongod)
    except InitializationError as error:
        report_initialization_error(error)
        return 1
    except maintenance.MaintenanceError as error:
        print("UNIFIED FRESH START STOPPED: " + str(error))
        print("Existing data is retained. Keep any incomplete new runtime for diagnosis.")
        return 1
    except (Exception, KeyboardInterrupt) as error:
        report_initialization_error(InitializationError("fresh-start", _initialization_reason(error)))
        return 1
    print("UNIFIED FRESH START VERIFIED")
    print(json.dumps(result, sort_keys=True))
    print("Use the new RuntimeRoot for all five services. The original runtime and trusted connection are retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
