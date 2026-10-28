"""Execute the unchanged Windows transport wrapper with simulated native tools.

Uses the existing Linux PowerShell host, never Windows, OpenSSL or the database.
The fixture checks command boundaries, failure logs and preservation; actual
Windows Python/OpenSSL/TLS execution still requires the user's returned report.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = "Test-WindowsAllianceTransport.ps1"
SUCCESS = "ALLIANCE TRANSPORT FIXTURE COMPLETE"
FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["TRANSPORT_CALLS"], "a") as output:
    output.write(json.dumps({"args": args, "path": os.environ["PATH"]}) + "\n")
check = args[-1] == "check-python"
print("Simulated Python version check" if check else "Simulated TLS fixture")
if os.environ.get("TRANSPORT_FAIL") == ("check-python" if check else "fixture"):
    print("Injected native failure")
    sys.exit(9)
if not check:
    report = pathlib.Path(args[args.index("--report") + 1])
    with report.open("x") as output:
        json.dump({"fixture": True}, output)
'''
LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:TRANSPORT_SETTINGS -Raw | ConvertFrom-Json
$env:PATH = $env:TRANSPORT_BASE_PATH
$beforePath = $env:PATH
$parameters = @{}
foreach ($property in $settings.parameters.PSObject.Properties) {
    $parameters[$property.Name] = $property.Value
}
& $settings.helper @parameters
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper did not restore PATH.' }
[IO.File]::WriteAllText($settings.after_path, $env:PATH)
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), "Existing Linux PowerShell is unavailable; no tools are installed by this test")
class TransportPowerShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance transport PS ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "server with spaces & literal $"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        self.helper.write_bytes((ROOT / "tools" / HELPER).read_bytes())
        self.localappdata = self.root / "Local App Data"
        self.python = self.localappdata / "Programs/Python/Python312/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.msys = self.root / "MSYS with spaces & literal $"
        self.openssl = self.msys / "mingw64/bin/openssl.exe"
        self.openssl.parent.mkdir(parents=True)
        self.openssl.write_bytes(b"OpenSSL must only be invoked by the Python implementation")
        for name in ("alliance_dependencies.py", "alliance_transport.py"):
            (self.tools / name).write_bytes(b"Python module fixture, never imported")
        self.protected = {}
        for name, content in (
            (".env", b"PRIVATE_ENV_SENTINEL"),
            ("runtime/alliance/root.json", b"PRIVATE_RUNTIME_SENTINEL"),
            ("build/windows-mingw64/bin/wesnothd.exe", b"KEEP_COMPLETED_SERVER"),
            ("configs/lan.cfg", b"KEEP_GUEST_CONFIG"),
            ("README.md", b"KEEP_UNRELATED_USER_CHANGES"),
        ):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.protected[path] = hashlib.sha256(content).hexdigest()
        self.protected[self.helper] = hashlib.sha256(self.helper.read_bytes()).hexdigest()
        self.calls = self.root / "calls.jsonl"
        self.after_path = self.root / "after-path.txt"
        self.settings = self.root / "settings.json"
        self.launcher = self.root / "launcher.ps1"
        self.launcher.write_text(LAUNCHER)
        self.parameters = {"MsysRoot": str(self.msys)}
        self.environment = {
            **os.environ, "OS": "Windows_NT", "LOCALAPPDATA": str(self.localappdata),
            "TRANSPORT_CALLS": str(self.calls), "TRANSPORT_SETTINGS": str(self.settings),
            "TRANSPORT_BASE_PATH": os.environ["PATH"],
        }

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def run_helper(self, *, failure="", success=True, expected_logs=1, logged=True):
        self.settings.write_text(json.dumps({
            "helper": str(self.helper), "parameters": self.parameters,
            "after_path": str(self.after_path),
        }))
        result = subprocess.run(
            [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(self.launcher)],
            env={**self.environment, "TRANSPORT_FAIL": failure}, cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual(SUCCESS in result.stdout, success, result.stdout)
        self.assertEqual(self.after_path.read_text(), self.environment["PATH"], result.stdout)
        logs = sorted((self.repo / "diagnostics").glob("alliance-transport-*.txt"))
        self.assertEqual(len(logs), expected_logs, result.stdout)
        reports = ""
        for path in logs:
            raw = path.read_bytes()
            reports += raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if logged:
            self.assertIn("Saved log:", result.stdout)
            self.assertEqual("ERROR:" in reports, not success, reports)
            self.assertEqual(SUCCESS in reports, success, reports)
        else:
            self.assertNotIn("Saved log:", result.stdout)
        self.assertNotIn("PRIVATE_ENV_SENTINEL", result.stdout + reports)
        self.assertNotIn("PRIVATE_RUNTIME_SENTINEL", result.stdout + reports)
        for path, expected in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, str(path))
        return result, reports

    def test_success_uses_pinned_native_tools_and_separate_owned_paths(self):
        result, report = self.run_helper()
        calls = self.read_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["args"], ["-I", "-B", str(self.tools / "alliance_dependencies.py"), "check-python"])
        args = calls[1]["args"]
        json_reports = list((self.repo / "diagnostics").glob("alliance-transport-*.json"))
        self.assertEqual(len(json_reports), 1)
        self.assertEqual(args, [
            "-I", "-B", str(self.tools / "alliance_transport.py"),
            "--identity-root", str(self.repo / "runtime/alliance-transport"),
            "--server-address", "127.0.0.1", "--port", "15001",
            "--openssl", str(self.openssl), "--report", str(json_reports[0]),
            "--require-openssl-version", "3.6.3",
        ])
        self.assertTrue(all(call["path"] == str(self.openssl.parent) + ";" + self.environment["PATH"] for call in calls))
        self.assertIn("Python loopback TLS", report)
        self.assertIn("native game account integration and Android acceptance remain pending", report)
        self.assertIn("Transport report:", result.stdout)
        self.assertFalse((self.repo / "runtime/alliance-transport").exists())

    def test_custom_address_port_and_python_are_single_literal_arguments(self):
        custom_python = self.root / "Python custom & $ executable.exe"
        custom_python.write_bytes(self.python.read_bytes())
        custom_python.chmod(0o755)
        self.python.unlink()
        self.parameters.update(PythonPath=str(custom_python), ServerAddress="100.99.99.14", Port=15123)
        self.run_helper()
        args = self.read_calls()[-1]["args"]
        self.assertEqual(args[args.index("--server-address") + 1], "100.99.99.14")
        self.assertEqual(args[args.index("--port") + 1], "15123")

    def test_python_version_failure_stops_fixture_and_restores_path(self):
        _, report = self.run_helper(failure="check-python", success=False)
        self.assertEqual(len(self.read_calls()), 1)
        self.assertIn("Windows x86_64 CPython 3.12.10 is required", report)
        self.assertEqual(list((self.repo / "diagnostics").glob("*.json")), [])

    def test_fixture_failure_is_saved_without_success_marker(self):
        _, report = self.run_helper(failure="fixture", success=False)
        self.assertEqual(len(self.read_calls()), 2)
        self.assertIn("fixture failed with exit 9", report)
        self.assertNotIn("Transport report:", report)

    def test_nonwindows_stops_before_any_native_command(self):
        self.environment["OS"] = "Linux"
        _, report = self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])
        self.assertIn("This helper requires Windows", report)

    def test_missing_python_stops_with_saved_error(self):
        self.python.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_empty_openssl_stops_before_python_check(self):
        self.openssl.write_bytes(b"")
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_transport_module_stops_before_python_check(self):
        (self.tools / "alliance_transport.py").unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_version_checker_stops_before_python_execution(self):
        (self.tools / "alliance_dependencies.py").unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_repeated_runs_preserve_logs_and_use_unique_reports(self):
        self.run_helper()
        first = {path: path.read_bytes() for path in (self.repo / "diagnostics").iterdir()}
        self.run_helper(expected_logs=2)
        for path, data in first.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(len(list((self.repo / "diagnostics").glob("*.json"))), 2)
        self.assertEqual(len(self.read_calls()), 4)

    def test_diagnostics_creation_error_stops_before_native_execution(self):
        (self.repo / "diagnostics").write_bytes(b"existing file must stay unchanged")
        result, _ = self.run_helper(success=False, expected_logs=0, logged=False)
        self.assertEqual(self.read_calls(), [])
        self.assertIn("ERROR:", result.stdout)
        self.assertEqual((self.repo / "diagnostics").read_bytes(), b"existing file must stay unchanged")


if __name__ == "__main__":
    unittest.main()
