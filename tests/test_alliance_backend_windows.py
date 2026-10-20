"""Execute the backend diagnostic wrapper with simulated Windows metadata and Python.

No service, database, bridge or Android process is started by these tests.
PowerShell runs on Linux; actual Windows 5.1 acceptance belongs to the user.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = "Test-WindowsAllianceBackend.ps1"
COMPLETE = "ALLIANCE BACKEND DIAGNOSTIC COMPLETE"
FAKE_PYTHON = r"""#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['BACKEND_CALLS'], 'a') as output:
    output.write(json.dumps({'executable':sys.argv[0], 'args':args,
                            'cwd':os.getcwd(), 'path':os.environ['PATH']}) + '\n')
report = pathlib.Path(args[args.index('--report') + 1])
mode = os.environ.get('BACKEND_REPORT', '')
failed = os.environ.get('BACKEND_FAIL') == 'yes'
if mode != 'missing':
    with report.open('x') as output:
        if mode == 'malformed':
            output.write('{"private":"PRIVATE_JSON_SENTINEL", invalid')
        elif mode == 'oversized':
            output.write(' ' * 32769)
        elif mode != 'empty':
            json.dump({'format':2 if mode == 'format' else 1,
                       'purpose':'unexpected' if mode == 'purpose' else 'wesnoth-alliance-backend-check',
                       'status':'failed' if failed or mode == 'status' else 'passed',
                       'outcome':'unavailable' if failed else 'healthy'}, output)
print('Simulated safe diagnostic stdout', flush=True)
print('Simulated safe diagnostic stderr', file=sys.stderr, flush=True)
print('ALLIANCE BACKEND CHECK ' + ('FAILED' if failed else 'PASSED'), flush=True)
sys.exit(1 if failed else 0)
"""
LAUNCHER = r"""
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:BACKEND_SETTINGS -Raw | ConvertFrom-Json
$null = New-PSDrive -Name C -PSProvider FileSystem -Root $env:BACKEND_DRIVE
function Get-NetTCPConnection {
    [CmdletBinding()]param([string]$State)
    if ($State -cne 'Listen') { throw 'Unexpected metadata query.' }
    if ($settings.query_error) { throw 'PRIVATE_LISTENER_ERROR_SENTINEL' }
    $settings.listeners
}
function Get-Process {
    [CmdletBinding()]param([int]$Id)
    if ($settings.process_error) { throw 'PRIVATE_PROCESS_ERROR_SENTINEL' }
    [pscustomobject]@{ProcessName=$settings.process_name; CommandLine='PRIVATE_COMMANDLINE_SENTINEL'; Path='PRIVATE_EXEPATH_SENTINEL'}
}
function Get-Content {
    [CmdletBinding()]param([string]$LiteralPath, [switch]$Raw, [string]$Encoding)
    if (-not $LiteralPath.EndsWith('.json') -or -not $LiteralPath.Contains('alliance-backend-')) {
        throw 'Wrapper attempted to read a file other than its diagnostic report.'
    }
    Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw -Encoding UTF8
}
function Start-Process { throw 'Forbidden process start.' }
function Stop-Process { throw 'Forbidden process stop.' }
function powershell.exe { throw 'Forbidden secondary helper.' }
function sc.exe { throw 'Forbidden service control.' }
$env:PATH = $env:BACKEND_BASE_PATH
$beforePath = $env:PATH
$beforeLocation = (Get-Location).Path
$arguments = @{}
if ($settings.PSObject.Properties.Name -contains 'runtime_root') {
    $arguments.RuntimeRoot = $settings.runtime_root
}
& $settings.helper @arguments
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper changed PATH.' }
if ((Get-Location).Path -cne $beforeLocation) { throw 'Helper changed the working directory.' }
Write-Host 'CALLER STATE PRESERVED'
exit $result
"""


@unittest.skipUnless(PWSH.is_file(), "Existing Linux PowerShell is unavailable; no tools are installed")
class BackendWindowsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance backend PS ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        for name in (HELPER, "Alliance-Common.ps1"):
            shutil.copyfile(ROOT / "tools" / name, self.tools / name)
        self.python = self.repo / "build/alliance-venv/Scripts/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.diagnostic = self.tools / "check_alliance_backend.py"
        self.diagnostic.write_text("# simulated diagnostic module\n")
        self.drive = self.root / "profile drive"
        self.runtime = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime"
        self.runtime.mkdir(parents=True)
        sentinels = {
            self.repo / ".env": b"PRIVATE_ENV_SENTINEL",
            self.repo / "runtime/alliance/config.json": b"PRIVATE_OLD_CONFIG_SENTINEL",
            self.repo / "runtime/alliance-transport/server-key.pem": b"PRIVATE_IDENTITY_SENTINEL",
            self.repo / "build/alliance-account-bridge/alliance-account-bridge.exe": b"EXISTING_BRIDGE_BINARY",
            self.repo / "build/alliance-account-bridge/receipt.json": b"EXISTING_BRIDGE_RECEIPT",
            self.repo / "build/windows-mingw64/bin/wesnothd.exe": b"EXISTING_GUEST_SERVER",
            self.repo / "alliance_bridge/main.cpp": b"EXISTING_BRIDGE_SOURCE",
            self.repo / "build/alliance-mongodb/bin/mongod.exe": b"EXISTING_MONGODB_BINARY",
            self.repo / "build/alliance-venv/alliance-owned.json": b"EXISTING_VENV_RECEIPT",
            self.repo / "README.md": b"UNRELATED_USER_CHANGES",
            self.repo / "diagnostics/alliance-backend-previous.json": b"PREVIOUS_REPORT",
            self.runtime / "config.json": b"PRIVATE_PROFILE_CONFIG_SENTINEL",
            self.runtime / "root.json": b"PRIVATE_PROFILE_ROOT_SENTINEL",
            self.runtime / "data/WiredTiger.turtle": b"EXISTING_DATABASE",
            self.runtime / "logs/mongodb.log": b"EXISTING_DATABASE_LOG",
            self.runtime / "operation.lock": b"EXISTING_OPERATION_LOCK",
            self.root / "wesnoth_client/build/android-account-game/prefix/game.apk": b"EXISTING_APK",
        }
        for path, content in sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.protected = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in self.root.rglob("*") if path.is_file()}
        self.calls = self.root / "calls.jsonl"
        self.settings_path = self.root / "settings.json"
        self.settings = {
            "helper": str(self.helper), "query_error": False, "process_error": False,
            "process_name": "python",
            "listeners": [
                {"LocalAddress": "127.0.0.1", "LocalPort": 18765, "OwningProcess": 501,
                 "CommandLine": "PRIVATE_LISTENER_COMMANDLINE_SENTINEL"},
                {"LocalAddress": "127.0.0.1", "LocalPort": 27018, "OwningProcess": 502},
                {"LocalAddress": "10.10.10.10", "LocalPort": 445, "OwningProcess": 503},
            ],
        }
        self.launcher = self.root / "launcher.ps1"
        self.launcher.write_text(LAUNCHER)
        self.env = {**os.environ, "OS": "Windows_NT",
                    "LOCALAPPDATA": r"C:\Users\Uni\AppData\Local",
                    "BACKEND_DRIVE": str(self.drive), "BACKEND_SETTINGS": str(self.settings_path),
                    "BACKEND_CALLS": str(self.calls), "BACKEND_BASE_PATH": os.environ["PATH"]}

    def invoke(self, *, success=True, failure=False, mode=""):
        self.settings_path.write_text(json.dumps(self.settings))
        before_logs = set((self.repo / "diagnostics").glob("*.txt"))
        result = subprocess.run(
            [str(PWSH), "-NoProfile", "-NonInteractive", "-File", str(self.launcher)],
            cwd=self.root, env={**self.env, "BACKEND_FAIL": "yes" if failure else "", "BACKEND_REPORT": mode},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual(COMPLETE in result.stdout, success, result.stdout)
        self.assertIn("CALLER STATE PRESERVED", result.stdout)
        logs = set((self.repo / "diagnostics").glob("*.txt")) - before_logs
        self.assertEqual(len(logs), 1, result.stdout)
        self.log = logs.pop()
        self.transcript = self.log.read_text(encoding="utf-8-sig")
        self.output = result.stdout
        self.assertIn("Saved log:", self.output)
        self.assertIn("JSON report (if produced):", self.transcript)
        self.assertEqual("ERROR:" in self.transcript, not success, self.transcript)
        for secret in ("PRIVATE_ENV_SENTINEL", "PRIVATE_OLD_CONFIG_SENTINEL", "PRIVATE_IDENTITY_SENTINEL",
                       "PRIVATE_PROFILE_CONFIG_SENTINEL", "PRIVATE_PROFILE_ROOT_SENTINEL",
                       "PRIVATE_LISTENER_ERROR_SENTINEL", "PRIVATE_PROCESS_ERROR_SENTINEL",
                       "PRIVATE_COMMANDLINE_SENTINEL", "PRIVATE_EXEPATH_SENTINEL",
                       "PRIVATE_LISTENER_COMMANDLINE_SENTINEL", "PRIVATE_JSON_SENTINEL"):
            self.assertNotIn(secret, self.output + self.transcript)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        self.invocations = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        for call in self.invocations:
            self.assertEqual(call["executable"], str(self.python))
            self.assertEqual(call["cwd"], str(self.root))
            self.assertEqual(call["path"], self.env["PATH"])
        return result

    def test_success_uses_only_backend_diagnostic_and_profile_runtime(self):
        self.invoke()
        self.assertEqual(len(self.invocations), 1)
        args = self.invocations[0]["args"]
        self.assertEqual(args[:5], ["-I", "-B", str(self.diagnostic), "--runtime", str(self.runtime)])
        self.assertEqual(args[5], "--report")
        self.assertEqual(Path(args[6]), self.log.with_suffix(".json"))
        self.assertIn("18765", self.transcript)
        self.assertIn("27018", self.transcript)
        self.assertIn("501", self.transcript)
        self.assertIn("502", self.transcript)
        self.assertIn("python", self.transcript)
        self.assertNotIn("10.10.10.10", self.transcript)
        self.assertIn("Simulated safe diagnostic stdout", self.transcript)
        self.assertIn("Simulated safe diagnostic stderr", self.transcript)

    def test_explicit_literal_path_is_forwarded_without_creation(self):
        self.settings["runtime_root"] = r"C:\other runtime [literal] $ & ' path"
        self.invoke()
        selected = self.drive / "other runtime [literal] $ & ' path"
        self.assertEqual(self.invocations[0]["args"][4], str(selected))
        self.assertFalse(selected.exists())

    def test_no_listener_does_not_skip_http(self):
        self.settings["listeners"] = []
        self.invoke()
        self.assertEqual(len(self.invocations), 1)
        self.assertIn("No listeners were reported", self.transcript)

    def test_listener_query_failure_is_redacted_and_does_not_skip_http(self):
        self.settings["query_error"] = True
        self.invoke()
        self.assertEqual(len(self.invocations), 1)
        self.assertIn("WARNING: Listener metadata could not be collected", self.transcript)

    def test_process_query_failure_shows_unknown_and_continues(self):
        self.settings["process_error"] = True
        self.invoke()
        self.assertIn("Unknown", self.transcript)
        self.assertEqual(len(self.invocations), 1)

    def test_nonstandard_process_name_is_not_reflected(self):
        self.settings["process_name"] = "PRIVATE_PROCESS_ERROR_SENTINEL\nunsafe"
        self.invoke()
        self.assertIn("Unknown", self.transcript)

    def test_native_failure_saves_both_reports_and_returns_nonzero(self):
        self.invoke(success=False, failure=True)
        self.assertEqual(len(self.invocations), 1)
        self.assertIn("ALLIANCE BACKEND CHECK FAILED", self.transcript)
        report = json.loads(self.log.with_suffix(".json").read_text())
        self.assertEqual(report["status"], "failed")

    def test_invalid_report_cannot_claim_completion(self):
        for mode in ("missing", "empty", "malformed", "oversized", "format", "purpose", "status"):
            with self.subTest(mode=mode):
                self.invoke(success=False, mode=mode)
                self.assertNotIn(COMPLETE, self.transcript)

    def test_missing_default_profile_environment_stops_before_python(self):
        self.env["LOCALAPPDATA"] = ""
        self.invoke(success=False)
        self.assertEqual(self.invocations, [])

    def test_invalid_runtime_paths_stop_before_python(self):
        for path in ("", "relative", r"\\server\share\runtime", r"C:\Users\..\runtime", r"C:\runtime:stream"):
            with self.subTest(path=path):
                self.settings["runtime_root"] = path
                self.invoke(success=False)
                self.assertEqual(self.invocations, [])

    def test_runtime_symlink_stops_before_python(self):
        (self.drive / "redirect").symlink_to(self.runtime, target_is_directory=True)
        self.settings["runtime_root"] = r"C:\redirect"
        self.invoke(success=False)
        self.assertEqual(self.invocations, [])

    def test_missing_or_empty_executable_and_diagnostic_fail_without_native(self):
        for target in (self.python, self.diagnostic):
            data = target.read_bytes()
            digest = self.protected.pop(target)
            for empty in (False, True):
                with self.subTest(target=target.name, empty=empty):
                    target.unlink(missing_ok=True)
                    if empty:
                        target.write_bytes(b"")
                    self.invoke(success=False)
                    self.assertEqual(self.invocations, [])
            target.write_bytes(data)
            if target == self.python:
                target.chmod(0o755)
            self.protected[target] = digest

    def test_wrong_operating_system_is_rejected_without_native(self):
        self.env["OS"] = "Linux"
        self.invoke(success=False)
        self.assertEqual(self.invocations, [])

    def test_two_runs_preserve_previous_reports_and_use_unique_names(self):
        self.invoke()
        first = self.log
        old = first.read_bytes(), first.with_suffix(".json").read_bytes()
        self.invoke()
        self.assertNotEqual(first, self.log)
        self.assertEqual((first.read_bytes(), first.with_suffix(".json").read_bytes()), old)
        self.assertEqual(len(self.invocations), 2)


if __name__ == "__main__":
    unittest.main()
