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
import ssl
import stat
import subprocess
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.deployment import MONGO_VERSION, _client, _credentials, _uri
from alliance.runtime_lock import _acquire, _file_identity, _release
from alliance.startup_progress import ProgressError, create_progress, read_progress, utc_now
from alliance.court import SCHEMA as SCHEMA_VERSION
from alliance.config import Settings
from tools.alliance_maintenance import local_path, validate_runtime
from tools.alliance_transport import read_json, tls_client_context, validate_profile
from tools.check_alliance_backend import collect

ROOT = Path(__file__).resolve().parents[1]
STEPS = (("W02", "database", 27018, "Run-WindowsAllianceDatabase.ps1"),
         ("W03", "backend", 18765, "Run-WindowsAlliance.ps1"),
         ("W04", "bridge", 15001, "Run-WindowsAllianceBridge.ps1"))
BATTLE_STEP = ("W05", "battles", 15002, "Run-WindowsAllianceBattles.ps1")
MULTIPLAYER_STEP = ("W06", "multiplayer", 15000, "Run-WindowsMultiplayer.ps1")
EXPECTED_IMPLEMENTATION_RELEASE = 1192626
BACKEND_RELEASE_ERROR = "W03_backend_release_mismatch"
BATTLE_STARTUP_LIMITS = {"preflight": 300, "worker_verification": 900, "listener": 75, "total": 1275}


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


def open_port(address, port, timeout=1):
    try:
        if timeout <= 0: return False
        with socket.create_connection((address, port), timeout=min(1, timeout)): return True
    except OSError: return False


def database_check(runtime):
    try:
        settings = Settings.load(runtime)
        credentials = _credentials(runtime)
        with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin", endpoint=settings.database)) as client:
            if client.server_info()["version"] != MONGO_VERSION: return False
            hello = client.admin.command("hello")
            if hello.get("setName") != settings.database.replica_set or not hello.get("isWritablePrimary"): return False
            options = client.admin.command("getCmdLineOpts")["parsed"]
            if Path(options["storage"]["dbPath"]).resolve() != runtime / "data": return False
            return client[settings.database.name].schema_metadata.find_one({"_id": "alliance", "version": SCHEMA_VERSION}) is not None
    except Exception: return False


def backend_check(runtime):
    health = collect(runtime)
    if health["status"] != "passed": return False
    release = health.get("implementation_release")
    if type(release) is not int or release != EXPECTED_IMPLEMENTATION_RELEASE:
        raise WorkflowError(BACKEND_RELEASE_ERROR)
    return True


def public_profile(identity_root=None):
    profile = read_json((Path(identity_root) if identity_root is not None else ROOT / "runtime/alliance-transport") / "public-profile.json")
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


def service_health_outcome(raw, *, battles=False, world_workers=None):
    # Accept only this fixed, credential-free protocol response. No generic WML
    # evaluation, nested tags or arbitrary response content enters the report.
    try: lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError: return "invalid_health"
    if len(lines) != (6 if battles else 5) or lines[0] != "[alliance_health]" or lines[-1] != "[/alliance_health]": return "invalid_health"
    fields = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'(service|api|implementation_release|native_workers)\s*=\s*"([^"\\]*)"', line)
        if not match or match[1] in fields: return "invalid_health"
        fields[match[1]] = match[2]
    if battles:
        workers=fields.pop("native_workers", "")
        if workers not in ("1", "2", "3", "4"): return "worker_unavailable"
        if world_workers is not None and workers!=str(world_workers):return "worker_count_mismatch"
    if set(fields) != {"service", "api", "implementation_release"}: return "invalid_health"
    if fields["service"] != ("alliance-battles" if battles else "alliance-accounts"): return "service_mismatch"
    if fields["api"] != ("1" if battles else "5"): return "protocol_mismatch"
    if fields["implementation_release"] != str(EXPECTED_IMPLEMENTATION_RELEASE): return "release_mismatch"
    return "healthy"


def valid_service_health(raw, *, battles=False, world_workers=None):
    return service_health_outcome(raw, battles=battles, world_workers=world_workers) == "healthy"


def valid_multiplayer_health(raw):
    """Require the bounded authenticated-lobby greeting and individual rooms."""
    try:
        lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError:
        return False
    if len(lines) != 5 or lines[0] != "[version]" or lines[-1] != "[/version]":
        return False
    fields = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'(alliance_protocol|implementation_release|individual_rooms)\s*=\s*"([0-9]+)"', line)
        if not match or match[1] in fields: return False
        fields[match[1]] = match[2]
    return fields == {"alliance_protocol": "5", "implementation_release": str(EXPECTED_IMPLEMENTATION_RELEASE),
                      "individual_rooms": "1"}


def bridge_probe(profile, *, battles=False, multiplayer=False, world_workers=None, deadline=None):
    def result(outcome): return {"passed": outcome == "healthy", "outcome": outcome}
    phase = "profile"
    try:
        context = tls_client_context(profile)
        deadline = min(time.monotonic() + 6, deadline) if deadline is not None else time.monotonic() + 6
        port = 15000 if multiplayer else (15002 if battles else 15001)
        phase = "connection"
        remaining = deadline-time.monotonic()
        if remaining <= 0: return result("probe_timeout")
        with socket.create_connection((profile["server_address"], port), timeout=min(3, remaining)) as raw:
            raw.settimeout(max(.001, deadline-time.monotonic()))
            raw.sendall(b"\0\0\0\1")
            if receive_exact(raw, 4, deadline) != b"\0\0\0\0": return result("preamble_mismatch")
            raw.settimeout(max(.001, deadline - time.monotonic()))
            phase = "tls"
            with context.wrap_socket(raw, server_hostname=profile["server_address"]) as peer:
                if hashlib.sha256(peer.getpeercert(binary_form=True)).hexdigest() != profile["certificate_sha256"]: return result("certificate_pin_mismatch")
                phase = "health"
                if not multiplayer:
                    request = gzip.compress(b"[alliance_health]\n[/alliance_health]\n", mtime=0)
                    peer.settimeout(max(.001, deadline-time.monotonic()))
                    peer.sendall(len(request).to_bytes(4, "big") + request)
                size = int.from_bytes(receive_exact(peer, 4, deadline), "big")
                if not 1 <= size <= 8192: return result("invalid_frame_size")
                compressed = receive_exact(peer, size, deadline)
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                message = decoder.decompress(compressed, 16385)
                if len(message) > 16384 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail: return result("invalid_compression")
                return result(("healthy" if valid_multiplayer_health(message) else "greeting_mismatch") if multiplayer else
                              service_health_outcome(message, battles=battles,world_workers=world_workers))
    except ConnectionRefusedError: return result("connection_refused")
    except (TimeoutError, socket.timeout): return result("probe_timeout")
    except ssl.SSLError: return result("tls_failed")
    except zlib.error: return result("invalid_compression")
    except WorkflowError as error:
        return result(str(error) if str(error) in ("health_timeout", "health_incomplete") else "probe_failed")
    except OSError: return result("profile_unavailable" if phase == "profile" else "connection_error")
    except Exception: return result("profile_invalid" if phase == "profile" else "probe_failed")


def bridge_check(profile, *, battles=False, multiplayer=False, world_workers=None):
    """Boolean compatibility interface for existing diagnostic/test companions."""
    return bridge_probe(profile, battles=battles, multiplayer=multiplayer, world_workers=world_workers)["passed"]


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


def launcher_script(wrapper, runtime, msys, log, powershell, world_workers=1, *, startup_progress=None, startup_launch_id=None, identity_root=None):
    if type(world_workers) is not int or not 1 <= world_workers <= 4: raise WorkflowError("invalid_worker_count")
    if wrapper not in {row[3] for row in (*STEPS, BATTLE_STEP, MULTIPLAYER_STEP)}:
        raise WorkflowError("unsupported_service_wrapper")
    # A native child PowerShell converts its Write-Host/Out-Host output into
    # console output too. Running a .ps1 in this pipeline directly would omit
    # host-only readiness/error lines from the step log.
    command = "& " + quoted(powershell) + " -NoProfile -ExecutionPolicy Bypass -File " + quoted(ROOT / "tools" / wrapper) + " -RuntimeRoot " + quoted(runtime)
    if wrapper in ("Run-WindowsAllianceBridge.ps1", "Run-WindowsMultiplayer.ps1"): command += " -MsysRoot " + quoted(msys)
    if wrapper == "Run-WindowsAllianceBattles.ps1":
        command += " -IdentityRoot " + quoted(identity_root or ROOT / "runtime/alliance-transport") + " -Workers " + str(world_workers)
    elif identity_root is not None and wrapper in ("Run-WindowsAllianceBridge.ps1", "Run-WindowsMultiplayer.ps1"):
        command += " -IdentityRoot " + quoted(identity_root)
    if (startup_progress is None) != (startup_launch_id is None): raise WorkflowError("startup_progress_pair_required")
    if startup_progress is not None:
        if wrapper != BATTLE_STEP[3]: raise WorkflowError("unexpected_startup_progress")
        command += " -StartupProgressPath " + quoted(startup_progress) + " -StartupLaunchId " + quoted(startup_launch_id)
    # Arguments are PowerShell single-quoted literals, not command interpolation.
    # Only these noninteractive service wrappers are transcribed here.
    return "$ErrorActionPreference='Continue'; " + command + " 2>&1 | ForEach-Object { " + \
        "$line='['+[DateTime]::UtcNow.ToString('o')+'] '+$_.ToString(); [IO.File]::AppendAllText(" + quoted(log) + \
        ", $line + [Environment]::NewLine); Write-Host $line }; exit $LASTEXITCODE"


def launch(wrapper, runtime, msys, log, world_workers=1, *, startup_progress=None, startup_launch_id=None, identity_root=None):
    if os.name != "nt": raise WorkflowError("start_requires_windows")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = launcher_script(wrapper, runtime, msys, log, powershell, world_workers,
                             startup_progress=startup_progress, startup_launch_id=startup_launch_id, identity_root=identity_root)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.Popen([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)


class StartupWatch:
    """Diagnostics can select a bounded phase budget, never establish health."""
    def __init__(self, path, launch_id, started):
        self.path, self.launch_id, self.started = path, launch_id, started
        self.limits = dict(BATTLE_STARTUP_LIMITS)
        self.hard_deadline = started + self.limits["total"]
        self.deadline = min(started + self.limits["preflight"], self.hard_deadline)
        self.budget_phase = "preflight"
        self.phase_started = started
        self.phase = "preflight"
        state = read_progress(path, launch_id)
        if state["records"] or state["partial"]:
            raise ProgressError("startup_progress_not_fresh")
        self.raw, self.identity = state["raw"], state["identity"]
        self.records = []
        self.partial = False

    def observe(self, now):
        state = read_progress(self.path, self.launch_id)
        if state["identity"] != self.identity or not state["raw"].startswith(self.raw):
            raise ProgressError("startup_progress_replaced_or_truncated")
        self.raw, self.partial = state["raw"], state["partial"]
        # A transition observed after a phase expired cannot rescue it. UTC and
        # child-supplied elapsed values are diagnostic only, never deadline clocks.
        expired = now >= self.deadline
        for record in state["records"][len(self.records):]:
            self.phase = record["phase"]
            self.records.append({key: record[key] for key in ("phase", "pid", "elapsed_ms", "at_utc")})
            self.records[-1]["observed_elapsed_ms"] = max(0, round((now - self.started) * 1000))
            next_budget = ("worker_verification" if self.phase == "worker_verification" else
                           "listener" if self.phase in ("listener", "serving") else "preflight")
            if not expired and next_budget != self.budget_phase:
                self.budget_phase, self.phase_started = next_budget, now
                self.deadline = min(now + self.limits[next_budget], self.hard_deadline)
        return not expired and now < self.deadline

    def report(self, row, now):
        row.update(startup_phase=self.phase, startup_budget_phase=self.budget_phase,
                   startup_elapsed_seconds=round(max(0, now-self.started), 3),
                   startup_phase_elapsed_seconds=round(max(0, now-self.phase_started), 3),
                   startup_limits_seconds=self.limits, startup_phases=list(self.records),
                   startup_progress_partial=self.partial)


def wait_for_startup(child, address, port, checked, row, *, watch=None):
    started = watch.started if watch is not None else time.monotonic()
    deadline = started + 75
    last_notice = started
    row["startup_started_at_utc"] = utc_now()
    row.setdefault("probe_attempts", 0)
    row.setdefault("last_health_outcome", "not_probed")
    while True:
        now = time.monotonic()
        if watch is not None:
            try:
                within_budget = watch.observe(now)
            except (ProgressError, OSError, ValueError):
                row.update(status="failed", startup_progress_error="invalid_progress")
                raise WorkflowError(row["id"] + "_startup_progress_invalid") from None
            watch.report(row, now)
            deadline = watch.deadline
        else:
            within_budget = now < deadline
            row["startup_elapsed_seconds"] = round(max(0, now-started), 3)
        if child.poll() is not None:
            row["status"] = "failed"
            raise WorkflowError(row["id"] + "_launcher_exited")
        if not within_budget:
            row["status"] = "unconfirmed"
            if watch is not None:
                row["startup_timeout_phase"] = "total" if now >= watch.hard_deadline else watch.budget_phase
            raise WorkflowError(row["id"] + "_startup_unconfirmed")
        if open_port(address, port, timeout=max(0, deadline-time.monotonic())):
            if time.monotonic() >= deadline:
                continue
            passed = checked(deadline=deadline)
            finished = time.monotonic()
            # Even a successful slow probe must respect the bounded wait.
            if passed and finished < deadline:
                if watch is not None:
                    try:
                        if not watch.observe(finished):
                            continue
                    except (ProgressError, OSError, ValueError):
                        row.update(status="failed", startup_progress_error="invalid_progress")
                        raise WorkflowError(row["id"] + "_startup_progress_invalid") from None
                row["status"] = "passed"
                if watch is not None: watch.report(row, finished)
                else: row["startup_elapsed_seconds"] = round(max(0, finished-started), 3)
                return
        else:
            row["last_health_outcome"] = "port_not_open"
        now = time.monotonic()
        if watch is not None and now-last_notice >= 30:
            print(row["id"] + " WAIT phase=" + watch.phase + "; elapsed_seconds=" + str(round(now-started))
                  + "; health=" + row["last_health_outcome"], flush=True)
            last_notice = now
        time.sleep(min(1, max(0, deadline-now)))


def run(runtime, msys, start, report, *, include_battles=False, world_workers=1, identity_root=None):
    if type(world_workers) is not int or not 1 <= world_workers <= 4: raise WorkflowError("invalid_worker_count")
    runtime = validate_runtime(runtime)
    profile = public_profile() if identity_root is None else public_profile(identity_root)
    mongo_port = Settings.load(runtime).database.port
    if include_battles and not (ROOT / "tools" / BATTLE_STEP[3]).is_file():
        raise WorkflowError("battles_helper_unavailable")
    report["steps"].append({"id": "W01", "service": "configuration", "status": "passed"})
    print("W01 PASS owned runtime and saved local identity", flush=True)
    with workflow_lock(runtime):
        for step, name, port, wrapper in (*STEPS, *((BATTLE_STEP,) if include_battles else ()), MULTIPLAYER_STEP):
            if name == "database": port = mongo_port
            address = profile["server_address"] if name in ("bridge", "battles", "multiplayer") else "127.0.0.1"
            check = (lambda deadline=None: database_check(runtime)) if name == "database" else (
                (lambda deadline=None: backend_check(runtime)) if name == "backend" else (
                    (lambda deadline=None: bridge_probe(profile, multiplayer=True,deadline=deadline)) if name == "multiplayer" else
                    (lambda deadline=None: bridge_probe(profile, battles=True,world_workers=world_workers,deadline=deadline)) if name=="battles" else
                    (lambda deadline=None: bridge_probe(profile,deadline=deadline))))
            row = {"id": step, "service": name, "status": "checking", "action": "none"}
            if name=="battles":row["requested_native_workers"]=world_workers
            report["steps"].append(row)
            def checked(deadline=None):
                try:
                    result = check(deadline=deadline)
                    if isinstance(result, dict):
                        row["probe_attempts"] = row.get("probe_attempts", 0) + 1
                        row["last_health_outcome"] = result["outcome"]
                        return result["passed"]
                    return result
                except WorkflowError:
                    row["status"] = "failed"
                    raise
            if open_port(address, port):
                if not checked():
                    row["status"] = "failed"
                    if name=="battles":raise WorkflowError("W05_existing_health_or_worker_count_differs_safe_restart_required")
                    raise WorkflowError(step + "_occupied_but_unhealthy")
                row.update(status="passed", action="reused")
                if name=="battles":row["verified_native_workers"]=world_workers
                print(step + " PASS existing " + name, flush=True)
                continue
            if not start:
                row["status"] = "stopped"
                raise WorkflowError(step + "_service_stopped")
            log = Path(report["report_path"]).with_name(Path(report["report_path"]).stem + "-" + step + ".txt")
            with log.open("x", encoding="utf-8") as output: output.write("[" + utc_now() + "] " + step + " " + name + " startup\n")
            row["log"] = str(log)
            watch = None
            launch_arguments = {}
            if name == "battles":
                progress_path = log.with_name(log.stem + "-startup.jsonl")
                launch_id = create_progress(progress_path)
                watch = StartupWatch(progress_path, launch_id, time.monotonic())
                row["startup_progress_path"] = str(progress_path)
                launch_arguments = {"startup_progress": progress_path, "startup_launch_id": launch_id}
                print(step + " startup progress: " + str(progress_path), flush=True)
            if identity_root is not None: launch_arguments["identity_root"] = identity_root
            child = launch(wrapper, runtime, msys, log, world_workers, **launch_arguments)
            row.update(action="started", launcher_pid=child.pid)
            print(step + " START " + name + "; log: " + str(log), flush=True)
            wait_for_startup(child, address, port, checked, row, watch=watch)
            if name=="battles":row["verified_native_workers"]=world_workers
            print(step + " PASS " + name, flush=True)
            if name == "battles":
                print(step + " verified startup: elapsed_seconds=" + str(row["startup_elapsed_seconds"])
                      + "; health=" + row["last_health_outcome"], flush=True)
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
    parser.add_argument("--world-workers", type=int, choices=(1,2,3,4), default=1)
    parser.add_argument("--identity", type=Path)
    args = parser.parse_args(argv)
    report = {"format": 1, "purpose": "wesnoth-alliance-service-workflow", "status": "failed", "steps": [],
        "created_at": datetime.now(timezone.utc).isoformat(), "report_path": str(args.report),
        "scope": "Local database identity/schema, authenticated backend release and pinned TLS protocol/release checks for accounts, optional shared battles and native Multiplayer; no player login or gameplay tested.",
        "expected_backend_implementation_release": EXPECTED_IMPLEMENTATION_RELEASE,
        "wan_disconnected": "not_observed"}
    try:
        path = local_path(args.report)
        with path.open("x", encoding="utf-8") as output:
            try: run(args.runtime, args.msys, args.start, report, include_battles=args.include_battles, world_workers=args.world_workers, identity_root=args.identity)
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
