"""Check/start the existing Windows Alliance services and write a sanitized report."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.deployment import MONGO_VERSION, _client, _credentials, _uri
from alliance.runtime_lock import _acquire, _file_identity, _release
from alliance.schema import SCHEMA_VERSION
from tools.alliance_maintenance import local_path, validate_runtime
from tools.alliance_transport import read_json, tls_client_context, validate_profile
from tools.check_alliance_backend import collect

ROOT = Path(__file__).resolve().parents[1]
STEPS = (("W02", "database", 27018, "Run-WindowsAllianceDatabase.ps1"),
         ("W03", "backend", 18765, "Run-WindowsAlliance.ps1"),
         ("W04", "bridge", 15001, "Run-WindowsAllianceBridge.ps1"))
BATTLE_STEP = ("W05", "battles", 15002, "Run-WindowsAllianceBattles.ps1")
MULTIPLAYER_STEP = ("W06", "multiplayer", 15000, "Run-WindowsMultiplayer.ps1")
EXPECTED_IMPLEMENTATION_RELEASE = 1192616
BACKEND_RELEASE_ERROR = "W03_backend_release_mismatch"


class WorkflowError(Exception): pass


@contextmanager
def workflow_lock(runtime):
    path = runtime / "workflow.guard"
    local_path(path)
    if path.exists() and (not stat.S_ISREG(path.lstat().st_mode) or path.lstat().st_nlink != 1):
        raise WorkflowError("invalid_workflow_guard")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    locked = False
    try:
        _file_identity(path, fd)
        try: _acquire(fd)
        except OSError: raise WorkflowError("another_workflow_is_running") from None
        locked = True
        info = _file_identity(path, fd)
        if info.st_size == 0:
            os.write(fd, b"\0"); os.fsync(fd)
        elif info.st_size != 1 or os.read(fd, 1) != b"\0":
            raise WorkflowError("invalid_workflow_guard")
        yield
    finally:
        if locked: _release(fd)
        os.close(fd)


def open_port(address, port):
    try:
        with socket.create_connection((address, port), timeout=1): return True
    except OSError: return False


def database_check(runtime):
    try:
        credentials = _credentials(runtime)
        with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
            if client.server_info()["version"] != MONGO_VERSION: return False
            hello = client.admin.command("hello")
            if hello.get("setName") != "wesnoth-rs" or not hello.get("isWritablePrimary"): return False
            options = client.admin.command("getCmdLineOpts")["parsed"]
            if Path(options["storage"]["dbPath"]).resolve() != runtime / "data": return False
            return client.wesnoth_game.schema_metadata.find_one({"_id": "alliance", "version": SCHEMA_VERSION}) is not None
    except Exception: return False


def backend_check(runtime):
    health = collect(runtime)
    if health["status"] != "passed": return False
    release = health.get("implementation_release")
    if type(release) is not int or release != EXPECTED_IMPLEMENTATION_RELEASE:
        raise WorkflowError(BACKEND_RELEASE_ERROR)
    return True


def public_profile():
    profile = read_json(ROOT / "runtime/alliance-transport/public-profile.json")
    validate_profile(profile)
    if profile["port"] != 15001: raise WorkflowError("unexpected_bridge_port")
    # A configured numeric IP must belong to this computer. No Internet target
    # or replacement identity is discovered when Ethernet settings change.
    family = socket.AF_INET6 if ":" in profile["server_address"] else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try: probe.bind((profile["server_address"], 0))
        except OSError: raise WorkflowError("saved_bridge_address_is_not_local") from None
    return profile


def receive_exact(peer, length, deadline):
    data = bytearray()
    while len(data) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise WorkflowError("health_timeout")
        peer.settimeout(remaining)
        part = peer.recv(length - len(data))
        if not part: raise WorkflowError("health_incomplete")
        data.extend(part)
    return bytes(data)


def valid_battle_health(raw):
    # Accept only this fixed, credential-free protocol response. No generic WML
    # evaluation, nested tags or arbitrary response content enters the report.
    lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(lines) != 4 or lines[0] != "[alliance_health]" or lines[-1] != "[/alliance_health]": return False
    fields = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'(service|api)\s*=\s*"([^"\\]*)"', line)
        if not match or match[1] in fields: return False
        fields[match[1]] = match[2]
    return fields == {"service": "alliance-battles", "api": "1"}


def valid_multiplayer_health(raw):
    """Read only the bounded unsolicited authenticated-lobby version greeting."""
    try:
        lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError:
        return False
    if len(lines) != 4 or lines[0] != "[version]" or lines[-1] != "[/version]":
        return False
    fields = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'(alliance_protocol|implementation_release)\s*=\s*"([0-9]+)"', line)
        if not match or match[1] in fields: return False
        fields[match[1]] = match[2]
    return fields == {"alliance_protocol": "2", "implementation_release": str(EXPECTED_IMPLEMENTATION_RELEASE)}


def bridge_check(profile, *, battles=False, multiplayer=False):
    try:
        context = tls_client_context(profile)
        deadline = time.monotonic() + 6
        port = 15000 if multiplayer else (15002 if battles else 15001)
        with socket.create_connection((profile["server_address"], port), timeout=3) as raw:
            raw.sendall(b"\0\0\0\1")
            if receive_exact(raw, 4, deadline) != b"\0\0\0\0": return False
            raw.settimeout(max(.001, deadline - time.monotonic()))
            with context.wrap_socket(raw, server_hostname=profile["server_address"]) as peer:
                if hashlib.sha256(peer.getpeercert(binary_form=True)).hexdigest() != profile["certificate_sha256"]: return False
                if not battles and not multiplayer: return True
                if battles:
                    request = gzip.compress(b"[alliance_health]\n[/alliance_health]\n", mtime=0)
                    peer.sendall(len(request).to_bytes(4, "big") + request)
                size = int.from_bytes(receive_exact(peer, 4, deadline), "big")
                if not 1 <= size <= 8192: return False
                compressed = receive_exact(peer, size, deadline)
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                message = decoder.decompress(compressed, 16385)
                if len(message) > 16384 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail: return False
                return valid_multiplayer_health(message) if multiplayer else valid_battle_health(message)
    except Exception: return False


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


def launcher_script(wrapper, runtime, msys, log, powershell):
    if wrapper not in {row[3] for row in (*STEPS, BATTLE_STEP, MULTIPLAYER_STEP)}:
        raise WorkflowError("unsupported_service_wrapper")
    # A native child PowerShell converts its Write-Host/Out-Host output into
    # console output too. Running a .ps1 in this pipeline directly would omit
    # host-only readiness/error lines from the step log.
    command = "& " + quoted(powershell) + " -NoProfile -ExecutionPolicy Bypass -File " + quoted(ROOT / "tools" / wrapper) + " -RuntimeRoot " + quoted(runtime)
    if wrapper in ("Run-WindowsAllianceBridge.ps1", "Run-WindowsMultiplayer.ps1"): command += " -MsysRoot " + quoted(msys)
    if wrapper == "Run-WindowsAllianceBattles.ps1": command += " -IdentityRoot " + quoted(ROOT / "runtime/alliance-transport")
    # Arguments are PowerShell single-quoted literals, not command interpolation.
    # Only these noninteractive service wrappers are transcribed here.
    return "$ErrorActionPreference='Continue'; " + command + " 2>&1 | ForEach-Object { " + \
        "$line=$_.ToString(); [IO.File]::AppendAllText(" + quoted(log) + \
        ", $line + [Environment]::NewLine); Write-Host $line }; exit $LASTEXITCODE"


def launch(wrapper, runtime, msys, log):
    if os.name != "nt": raise WorkflowError("start_requires_windows")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = launcher_script(wrapper, runtime, msys, log, powershell)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.Popen([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)


def run(runtime, msys, start, report, *, include_battles=False):
    runtime = validate_runtime(runtime)
    profile = public_profile()
    if include_battles and not (ROOT / "tools" / BATTLE_STEP[3]).is_file():
        raise WorkflowError("battles_helper_unavailable")
    report["steps"].append({"id": "W01", "service": "configuration", "status": "passed"})
    print("W01 PASS owned runtime and saved local identity", flush=True)
    with workflow_lock(runtime):
        for step, name, port, wrapper in (*STEPS, *((BATTLE_STEP,) if include_battles else ()), MULTIPLAYER_STEP):
            address = profile["server_address"] if name in ("bridge", "battles", "multiplayer") else "127.0.0.1"
            check = (lambda: database_check(runtime)) if name == "database" else (
                (lambda: backend_check(runtime)) if name == "backend" else (
                    (lambda: bridge_check(profile, multiplayer=True)) if name == "multiplayer" else
                    (lambda: bridge_check(profile, battles=name == "battles"))))
            row = {"id": step, "service": name, "status": "checking", "action": "none"}
            report["steps"].append(row)
            def checked():
                try: return check()
                except WorkflowError:
                    row["status"] = "failed"
                    raise
            if open_port(address, port):
                if not checked():
                    row["status"] = "failed"
                    raise WorkflowError(step + "_occupied_but_unhealthy")
                row.update(status="passed", action="reused")
                print(step + " PASS existing " + name, flush=True)
                continue
            if not start:
                row["status"] = "stopped"
                raise WorkflowError(step + "_service_stopped")
            log = Path(report["report_path"]).with_name(Path(report["report_path"]).stem + "-" + step + ".txt")
            with log.open("x", encoding="utf-8") as output: output.write(step + " " + name + " startup\n")
            row["log"] = str(log)
            child = launch(wrapper, runtime, msys, log)
            row.update(action="started", launcher_pid=child.pid)
            print(step + " START " + name + "; log: " + str(log), flush=True)
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    row["status"] = "failed"
                    raise WorkflowError(step + "_launcher_exited")
                if open_port(address, port) and checked():
                    row["status"] = "passed"
                    break
                time.sleep(1)
            else:
                row["status"] = "unconfirmed"
                raise WorkflowError(step + "_startup_unconfirmed")
            print(step + " PASS " + name, flush=True)
    report["status"] = "passed"
    report["steps"].append({"id": "W07", "service": "workflow", "status": "passed"})
    print("W07 UNIFIED GAME SERVICES READY. Keep the service windows open.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--msys", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--include-battles", action="store_true")
    args = parser.parse_args(argv)
    report = {"format": 1, "purpose": "wesnoth-alliance-service-workflow", "status": "failed", "steps": [],
        "created_at": datetime.now(timezone.utc).isoformat(), "report_path": str(args.report),
        "scope": "Local database identity/schema, authenticated HTTP health and pinned bridge TLS and optional battle-service health only; no player login or gameplay tested.",
        "expected_backend_implementation_release": EXPECTED_IMPLEMENTATION_RELEASE,
        "wan_disconnected": "not_observed"}
    try:
        path = local_path(args.report)
        with path.open("x", encoding="utf-8") as output:
            try: run(args.runtime, args.msys, args.start, report, include_battles=args.include_battles)
            except WorkflowError as error: report["error"] = str(error)
            except (Exception, KeyboardInterrupt): report["error"] = "workflow_incomplete"
            json.dump(report, output, indent=2); output.write("\n")
    except Exception:
        print("ALLIANCE WORKFLOW FAILED: report_unavailable; no existing process was stopped.")
        return 1
    if report["status"] != "passed":
        print("ALLIANCE WORKFLOW STOPPED: " + report.get("error", "unconfirmed"))
        if report.get("error") == BACKEND_RELEASE_ERROR:
            print("W03: The admin service does not report required implementation release " + str(EXPECTED_IMPLEMENTATION_RELEASE) + ".")
            print("In the admin service PowerShell window, press Ctrl+C and wait for its prompt. Restart Run-WindowsAlliance.ps1 with the same -RuntimeRoot, then rerun Start-WindowsAllianceStack.ps1.")
            print("Keep the database and other service windows open. No process was stopped or restarted automatically.")
        print("Existing and newly started services were left running. Check the named step/log before retrying; no process was killed.")
    print("Workflow report: " + str(path))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
