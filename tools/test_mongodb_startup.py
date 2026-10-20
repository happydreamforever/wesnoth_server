#!/usr/bin/env python3
"""Exercise fresh disposable MongoDB storage; never open the Alliance runtime.

The Windows wrapper verifies the installed dependency pins before invocation.
This diagnostic keeps every scratch file and reports startup, journaled storage,
clean shutdown and restart separately. It does not initialize game accounts.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time

from pymongo import MongoClient
from pymongo.errors import AutoReconnect, ConnectionFailure, PyMongoError
from pymongo.write_concern import WriteConcern

VERSION = "8.0.32"
PURPOSE = "wesnoth-mongodb-startup-check"
SUCCESS = "ALLIANCE MONGODB STARTUP CHECK PASSED"
STARTUP_SECONDS = 30
STOP_SECONDS = 15
ROOT = Path(__file__).absolute().parents[1]


class ProbeFailure(Exception):
    """Only fixed, non-sensitive error codes are included in reports."""


def absolute(path):
    return Path(os.path.abspath(path))


def check_path(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ProbeFailure("redirected_path")


def restrict_directory(path):
    if os.name != "nt":
        path.chmod(0o700)
        return
    result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, timeout=10, check=True)
    rows = list(csv.reader(result.stdout.strip().splitlines()))
    if len(rows) != 1 or len(rows[0]) != 2 or not re.fullmatch(r"S-1-5-(?:\d+-)*\d+", rows[0][1]):
        raise ProbeFailure("owner_sid_unavailable")
    result = subprocess.run(["icacls.exe", str(path), "/inheritance:r", "/grant:r",
                            f"*{rows[0][1]}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ProbeFailure("scratch_permissions_failed")


def write_new(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as output:
        json.dump(content, output, sort_keys=True, indent=2)
        output.write("\n")


def choose_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    if port == 27018:
        raise ProbeFailure("reserved_port_selected")
    return port


def client_for(port):
    return MongoClient(f"mongodb://127.0.0.1:{port}/?directConnection=true",
                       serverSelectionTimeoutMS=500, connectTimeoutMS=500,
                       socketTimeoutMS=5000, timeoutMS=5000, retryReads=False,
                       retryWrites=False, appname="AllianceDisposableStorageCheck")


def verify_identity(client, process, scratch, port):
    if process.poll() is not None:
        raise ProbeFailure("owned_process_exited")
    status = client.admin.command("serverStatus", maxTimeMS=1000)
    if not isinstance(status.get("pid"), int) or isinstance(status["pid"], bool) or status["pid"] != process.pid:
        raise ProbeFailure("server_pid_mismatch")
    if status.get("version") != VERSION:
        raise ProbeFailure("server_version_mismatch")
    options = client.admin.command("getCmdLineOpts", maxTimeMS=1000).get("parsed", {})
    net = options.get("net", {})
    storage = options.get("storage", {})
    if (net.get("bindIp") != "127.0.0.1" or net.get("port") != port
            or absolute(storage.get("dbPath", "")) != scratch / "data"
            or options.get("replication") or options.get("security", {}).get("authorization") == "enabled"):
        raise ProbeFailure("server_options_mismatch")
    if process.poll() is not None:
        raise ProbeFailure("owned_process_exited")


def wait_ready(client, process, scratch, port):
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("owned_process_exited")
        try:
            verify_identity(client, process, scratch, port)
            client.admin.command("ping", maxTimeMS=1000)
            return
        except ConnectionFailure:
            time.sleep(0.1)
    raise ProbeFailure("startup_timeout")


def clean_stop(client, process, scratch, port):
    # Identity is rechecked immediately before issuing any shutdown command.
    verify_identity(client, process, scratch, port)
    try:
        client.admin.command("shutdown", timeoutSecs=5)
    except AutoReconnect:
        pass  # Normal MongoDB shutdown closes the requesting connection.
    try:
        code = process.wait(timeout=STOP_SECONDS)
    except subprocess.TimeoutExpired:
        raise ProbeFailure("shutdown_timeout") from None
    if code != 0:
        raise ProbeFailure("unclean_shutdown_exit")


def force_cleanup(process):
    """Bound cleanup to this Popen handle, never a discovered PID or service."""
    if process is None or process.poll() is not None:
        return "not_needed"
    process.terminate()
    try:
        process.wait(timeout=5)
        return "terminated"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=5)
            return "killed"
        except subprocess.TimeoutExpired:
            return "owned_child_still_running"


def check_version(mongod, scratch):
    path = scratch / "logs" / "version.txt"
    with path.open("xb") as output:
        result = subprocess.run([str(mongod), "--version"], cwd=scratch,
                                stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, timeout=15)
    # Read only this new command's bounded version output, never runtime logs.
    if path.stat().st_size > 65536:
        raise ProbeFailure("version_output_oversize")
    first_line = path.read_bytes().splitlines()[:1]
    if result.returncode or first_line != [f"db version v{VERSION}".encode("ascii")]:
        raise ProbeFailure("mongod_version_mismatch")


def exercise(mongod, scratch, report):
    report["phase"] = "version"
    check_version(mongod, scratch)
    report["checks"].append("mongodb_8.0.32")
    print("PASS MongoDB 8.0.32 executable version", flush=True)
    port = choose_port()
    report["port"] = port
    canary = {"_id": "disposable-startup-check", "value": secrets.token_hex(16)}
    for attempt in (1, 2):
        process = None
        client = None
        shutdown_attempted = False
        entry = {"start": attempt, "pid": None, "exit_code": None, "cleanup": "not_needed"}
        report["processes"].append(entry)
        report["phase"] = "first_start" if attempt == 1 else "restart"
        print("RUN " + report["phase"] + " in retained disposable storage", flush=True)
        process_log = scratch / "logs" / f"process-{attempt}.log"
        mongo_log = scratch / "logs" / f"mongodb-{attempt}.log"
        with process_log.open("xb") as output:
            try:
                process = subprocess.Popen([
                    str(mongod), "--dbpath", str(scratch / "data"),
                    "--bind_ip", "127.0.0.1", "--port", str(port),
                    "--wiredTigerCacheSizeGB", "0.25", "--logpath", str(mongo_log),
                ], cwd=scratch, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
                entry["pid"] = process.pid
                client = client_for(port)
                wait_ready(client, process, scratch, port)
                report["checks"].append("first_start_ping" if attempt == 1 else "restart_ping")
                print("PASS " + report["checks"][-1], flush=True)
                collection = client.alliance_startup_fixture.get_collection(
                    "canary", write_concern=WriteConcern(w=1, j=True, wtimeout=3000))
                verify_identity(client, process, scratch, port)
                report["phase"] = "journaled_write" if attempt == 1 else "persisted_read"
                if attempt == 1:
                    collection.insert_one(canary)
                    report["checks"].append("journaled_write")
                    print("PASS journaled_write", flush=True)
                report["phase"] = "initial_read" if attempt == 1 else "persisted_read"
                if collection.find_one({"_id": canary["_id"]}, max_time_ms=1000) != canary:
                    raise ProbeFailure("canary_mismatch")
                report["checks"].append("initial_read" if attempt == 1 else "persisted_read")
                print("PASS " + report["checks"][-1], flush=True)
                report["phase"] = "first_shutdown" if attempt == 1 else "final_shutdown"
                shutdown_attempted = True
                clean_stop(client, process, scratch, port)
                report["checks"].append("first_clean_shutdown" if attempt == 1 else "final_clean_shutdown")
                print("PASS " + report["checks"][-1], flush=True)
            finally:
                try:
                    # A failed write/read still deserves an orderly storage
                    # shutdown. Never send it until the identity check passes.
                    if (not shutdown_attempted and process is not None
                            and process.poll() is None and client is not None):
                        try:
                            clean_stop(client, process, scratch, port)
                            entry["cleanup"] = "graceful_after_failure"
                        except (ProbeFailure, PyMongoError, OSError, subprocess.SubprocessError):
                            pass
                    forced = force_cleanup(process)
                    if forced != "not_needed":
                        entry["cleanup"] = forced
                except (OSError, subprocess.SubprocessError):
                    entry["cleanup"] = "cleanup_failed"
                if process is not None:
                    entry["exit_code"] = process.poll()
                if client is not None:
                    client.close()
        if entry["cleanup"] != "not_needed":
            raise ProbeFailure("forced_cleanup_required")


def run(mongod, scratch, report_path):
    mongod, scratch, report_path = map(absolute, (mongod, scratch, report_path))
    report = {"format": 1, "purpose": PURPOSE, "status": "failed", "phase": "paths",
              "checks": [], "processes": [], "paths": {"scratch": str(scratch), "report": str(report_path)},
              "scope": "Disposable standalone storage only; game database, authentication and replica set untested."}
    # Reserve this new report first, so validation/startup failures are recorded.
    check_path(report_path)
    reserved = ROOT / "runtime" / "alliance"
    if report_path == reserved or reserved in report_path.parents:
        raise ProbeFailure("production_runtime_forbidden")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(report_path, flags, 0o600), "w", encoding="utf-8") as output:
        try:
            if scratch == reserved or reserved in scratch.parents:
                raise ProbeFailure("production_runtime_forbidden")
            for path in (mongod, scratch):
                check_path(path)
            if scratch.exists():
                raise ProbeFailure("scratch_already_exists")
            if not stat.S_ISREG(mongod.stat().st_mode):
                raise ProbeFailure("mongod_not_regular_file")
            scratch.mkdir(mode=0o700)
            restrict_directory(scratch)
            write_new(scratch / "owner.json", {"format": 1, "purpose": PURPOSE})
            (scratch / "data").mkdir(mode=0o700)
            (scratch / "logs").mkdir(mode=0o700)
            exercise(mongod, scratch, report)
            report.update(status="passed", phase="complete")
        except BaseException as error:
            report["error"] = {"type": type(error).__name__,
                               "code": str(error) if isinstance(error, ProbeFailure) else "operation_failed"}
        finally:
            report["cleanup"] = [entry["cleanup"] for entry in report["processes"]]
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongod", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.mongod, args.scratch, args.report)
    except (ProbeFailure, OSError, ValueError) as error:
        print(f"ERROR: Report could not be created ({type(error).__name__}); existing paths preserved.")
        return 1
    print("Report: " + str(absolute(args.report)))
    print("Retained scratch: " + str(absolute(args.scratch)))
    if report["status"] != "passed":
        print(f"ERROR: MongoDB diagnostic failed in {report['phase']} ({report['error']['code']}).")
        return 1
    print(SUCCESS)
    print(report["scope"])
    return 0


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
