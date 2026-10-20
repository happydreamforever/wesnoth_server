"""Run the MongoDB startup wrapper using isolated simulated Windows executables.

Linux PowerShell checks invocation, logging and preservation, not Windows storage
or real MongoDB startup. No installed MongoDB is started by these tests.
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
HELPER = "Test-WindowsMongoStartup.ps1"
SUCCESS = "ALLIANCE MONGODB STARTUP FIXTURE COMPLETE"
FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
action = args[-1] if args[-1] in ('check-python', 'check-installed') else 'startup'
with open(os.environ['MONGO_CALLS'], 'a') as output:
    output.write(json.dumps({'executable': sys.argv[0], 'action': action, 'args': args,
                            'cwd': os.getcwd(), 'path': os.environ['PATH']}) + '\n')
if action != 'startup':
    print('Simulated ' + action + ' output', flush=True)
    print('Simulated ' + action + ' stderr output', file=sys.stderr, flush=True)
    if os.environ.get('MONGO_FAIL') == action:
        print('Injected prerequisite failure', flush=True)
        sys.exit(9)
else:
    scratch = pathlib.Path(args[args.index('--scratch') + 1])
    scratch.mkdir()
    (scratch / 'fixture-sentinel').write_bytes(b'new disposable fixture data')
    report = pathlib.Path(args[args.index('--report') + 1])
    mode = os.environ.get('MONGO_REPORT', '')
    if mode != 'missing':
        with report.open('x') as output:
            if mode == 'malformed':
                output.write('{malformed JSON')
            elif mode != 'empty':
                json.dump({'simulated': True, 'format': 2 if mode == 'wrong-format' else 1,
                           'purpose': 'other-fixture' if mode == 'wrong-purpose' else 'wesnoth-mongodb-startup-check',
                           'status': 'failed' if os.environ.get('MONGO_FAIL') == action or mode == 'failed' else 'passed'}, output)
    print('Simulated MongoDB startup native output', flush=True)
    print('Simulated MongoDB startup stderr output', file=sys.stderr, flush=True)
    if os.environ.get('MONGO_FAIL') == action:
        print('Injected startup failure after partial report', flush=True)
        sys.exit(9)
'''
LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:MONGO_SETTINGS -Raw | ConvertFrom-Json
$env:PATH = $env:MONGO_BASE_PATH
$beforePath = $env:PATH
$beforeLocation = (Get-Location).Path
& $settings.helper
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper changed PATH.' }
if ((Get-Location).Path -cne $beforeLocation) { throw 'Helper changed the working directory.' }
@{ path = $env:PATH; cwd = (Get-Location).Path } | ConvertTo-Json | Set-Content -LiteralPath $settings.after_path
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), "Existing Linux PowerShell is unavailable; no tools are installed")
class MongoStartupPowerShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance mongo PS ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "server with spaces & literal $"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        self.helper.write_bytes((ROOT / "tools" / HELPER).read_bytes())
        self.python = self.repo / "build/alliance-venv/Scripts/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.mongod = self.repo / "build/alliance-mongodb/bin/mongod.exe"
        self.mongod.parent.mkdir(parents=True)
        self.mongod.write_bytes(b"Installed MongoDB sentinel; never executed in this simulation")
        self.dependency_check = self.tools / "alliance_dependencies.py"
        self.fixture = self.tools / "test_mongodb_startup.py"
        for path in (self.dependency_check, self.fixture):
            path.write_bytes(b"Python module fixture, never imported")
        sentinels = {
            ".env": b"PRIVATE_ENV_SENTINEL",
            "runtime/alliance/root.json": b"PRIVATE_ROOT_SENTINEL",
            "runtime/alliance/config.json": b"PRIVATE_CONFIG_SENTINEL",
            "runtime/alliance/keyfile": b"PRIVATE_MONGO_KEY_SENTINEL",
            "runtime/alliance/data/WiredTiger.turtle": b"ORIGINAL_MONGO_DATA",
            "runtime/alliance/data/WiredTiger.turtle.set": b"ORIGINAL_MONGO_PENDING_DATA",
            "runtime/alliance/logs/mongodb.log": b"ORIGINAL_MONGO_LOG",
            "runtime/alliance-transport/private-key.pem": b"PRIVATE_TRANSPORT_KEY_SENTINEL",
            "build/alliance-mongodb/bin/mongod.2026-10-19T19-37-33.mdmp": b"PRIVATE_CRASH_DUMP_SENTINEL",
            "build/alliance-mongodb/bin/vc_redist.x64.exe": b"INSTALLED_RUNTIME_INSTALLER",
            "build/alliance-cache/mongodb.zip": b"ORIGINAL_CACHE_ARCHIVE",
            "build/alliance-cache/wheels/pymongo.whl": b"ORIGINAL_CACHE_WHEEL",
            "build/alliance-venv/alliance-owned.json": b"EXISTING_VENV_RECEIPT",
            "build/windows-mingw64/bin/wesnothd.exe": b"COMPLETED_GUEST_SERVER",
            "build/alliance-mongo-startup-previous/fixture-data": b"OLDER_STARTUP_FIXTURE",
            "diagnostics/alliance-mongo-startup-previous.json": b"OLDER_STARTUP_REPORT",
            "README.md": b"UNRELATED_USER_CHANGES",
        }
        for name, content in sentinels.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.protected = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*") if path.is_file()
        }
        self.calls = self.root / "calls.jsonl"
        self.after_path = self.root / "after.json"
        self.settings = self.root / "settings.json"
        self.settings.write_text(json.dumps({"helper": str(self.helper), "after_path": str(self.after_path)}))
        self.launcher = self.root / "launcher.ps1"
        self.launcher.write_text(LAUNCHER)
        self.environment = {
            **os.environ, "OS": "Windows_NT", "MONGO_CALLS": str(self.calls),
            "MONGO_SETTINGS": str(self.settings), "MONGO_BASE_PATH": os.environ["PATH"],
        }

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def new_stages(self):
        return [path for path in (self.repo / "build").glob("alliance-mongo-startup-*")
                if path.name != "alliance-mongo-startup-previous"]

    def run_helper(self, *, success=True, failure="", report_mode="", expected_logs=1, logged=True):
        result = subprocess.run(
            [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(self.launcher)],
            env={**self.environment, "MONGO_FAIL": failure, "MONGO_REPORT": report_mode},
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual(SUCCESS in result.stdout, success, result.stdout)
        self.assertEqual(json.loads(self.after_path.read_text(encoding="utf-8-sig")),
                         {"path": self.environment["PATH"], "cwd": str(self.root)}, result.stdout)
        logs = sorted((self.repo / "diagnostics").glob("alliance-mongo-startup-*.txt"))
        self.assertEqual(len(logs), expected_logs, result.stdout)
        text = ""
        for path in logs:
            raw = path.read_bytes()
            text += raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if logged:
            self.assertIn("Saved log:", result.stdout)
            self.assertIn("JSON report (if produced):", text)
            self.assertIn("Disposable data and logs (if created):", text)
            self.assertEqual("ERROR:" in text, not success, text)
        else:
            self.assertNotIn("Saved log:", result.stdout)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        for secret in ("PRIVATE_ENV_SENTINEL", "PRIVATE_ROOT_SENTINEL", "PRIVATE_CONFIG_SENTINEL",
                       "PRIVATE_MONGO_KEY_SENTINEL", "PRIVATE_TRANSPORT_KEY_SENTINEL", "PRIVATE_CRASH_DUMP_SENTINEL"):
            self.assertNotIn(secret, result.stdout + text)
        for call in self.read_calls():
            self.assertEqual(call["path"], self.environment["PATH"])
            self.assertEqual(call["cwd"], str(self.root))
            self.assertEqual(call["executable"], str(self.python))
        return result, text

    def test_success_uses_only_exact_installed_tools_and_fresh_paths(self):
        result, transcript = self.run_helper()
        calls = self.read_calls()
        self.assertEqual([call["action"] for call in calls], ["check-python", "check-installed", "startup"])
        for index, command in enumerate(("check-python", "check-installed")):
            self.assertEqual(calls[index]["args"], ["-I", "-B", str(self.dependency_check), command])
        self.assertEqual(len(self.new_stages()), 1)
        stage = self.new_stages()[0]
        self.assertRegex(stage.name, r"^alliance-mongo-startup-\d{8}-\d{6}-\d{3}-[0-9a-f]{32}$")
        report = self.repo / "diagnostics" / (stage.name + ".json")
        self.assertEqual(calls[-1]["args"], ["-I", "-B", str(self.fixture), "--mongod", str(self.mongod),
                                            "--scratch", str(stage), "--report", str(report)])
        self.assertEqual(json.loads(report.read_text())["status"], "passed")
        self.assertTrue(report.with_suffix(".txt").is_file())
        for output in (result.stdout, transcript):
            self.assertIn("Simulated check-python output", output)
            self.assertIn("Simulated check-python stderr output", output)
            self.assertIn("Simulated check-installed output", output)
            self.assertIn("Simulated check-installed stderr output", output)
            self.assertIn("Simulated MongoDB startup native output", output)
            self.assertIn("Simulated MongoDB startup stderr output", output)
            self.assertIn("only the disposable database startup and persistence", output)
            self.assertIn("Original game database initialization, accounts and gameplay integration remain pending", output)

    def test_python_verification_failure_stops_before_installed_check_and_startup(self):
        _, transcript = self.run_helper(success=False, failure="check-python")
        self.assertEqual([call["action"] for call in self.read_calls()], ["check-python"])
        self.assertEqual(self.new_stages(), [])
        self.assertIn("CPython 3.14.3 is required", transcript)

    def test_installed_verification_failure_stops_before_startup(self):
        _, transcript = self.run_helper(success=False, failure="check-installed")
        self.assertEqual([call["action"] for call in self.read_calls()], ["check-python", "check-installed"])
        self.assertEqual(self.new_stages(), [])
        self.assertIn("no MongoDB startup was attempted", transcript)

    def test_startup_failure_preserves_partial_json_and_new_data(self):
        _, transcript = self.run_helper(success=False, failure="startup")
        calls = self.read_calls()
        self.assertEqual([call["action"] for call in calls], ["check-python", "check-installed", "startup"])
        self.assertEqual(len(self.new_stages()), 1)
        stage = self.new_stages()[0]
        report = self.repo / "diagnostics" / (stage.name + ".json")
        self.assertEqual(json.loads(report.read_text())["status"], "failed")
        self.assertEqual((stage / "fixture-sentinel").read_bytes(), b"new disposable fixture data")
        self.assertIn("startup fixture failed with exit 9", transcript)

    def test_missing_report_cannot_report_success(self):
        _, transcript = self.run_helper(success=False, report_mode="missing")
        self.assertEqual(len(self.new_stages()), 1)
        self.assertIn("did not produce a nonempty JSON report", transcript)

    def test_empty_report_cannot_report_success(self):
        _, transcript = self.run_helper(success=False, report_mode="empty")
        self.assertEqual(len(self.new_stages()), 1)
        self.assertIn("did not produce a nonempty JSON report", transcript)

    def test_malformed_report_cannot_report_success(self):
        _, transcript = self.run_helper(success=False, report_mode="malformed")
        self.assertIn("report is not valid JSON", transcript)

    def test_report_must_confirm_passed_status_and_expected_format_and_purpose(self):
        for index, mode in enumerate(("failed", "wrong-format", "wrong-purpose"), 1):
            with self.subTest(mode=mode):
                _, transcript = self.run_helper(success=False, report_mode=mode, expected_logs=index)
                self.assertIn("does not confirm successful completion", transcript)

    def test_nonwindows_stops_before_native_execution(self):
        self.environment["OS"] = "Linux"
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])
        self.assertEqual(self.new_stages(), [])

    def test_missing_mongod_stops_without_installing_or_starting(self):
        del self.protected[self.mongod]
        self.mongod.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])
        self.assertEqual(self.new_stages(), [])

    def test_empty_mongod_stops_without_native_execution(self):
        self.mongod.write_bytes(b"")
        self.protected[self.mongod] = hashlib.sha256(b"").hexdigest()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_selected_python_does_not_fall_back_to_path(self):
        del self.protected[self.python]
        self.python.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_unlaunchable_python_stops_without_accepting_previous_exit_code(self):
        self.python.chmod(0o644)
        _, transcript = self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])
        self.assertEqual(self.new_stages(), [])
        self.assertIn("selected installed Python could not be executed", transcript)

    def test_missing_dependency_check_stops_before_native_execution(self):
        del self.protected[self.dependency_check]
        self.dependency_check.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_fixture_stops_before_native_execution(self):
        del self.protected[self.fixture]
        self.fixture.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_repeat_preserves_all_first_run_artifacts_and_uses_distinct_paths(self):
        self.run_helper()
        first = {path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        self.run_helper(expected_logs=2)
        for path, content in first.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertEqual(len(self.new_stages()), 2)
        startup_calls = [call for call in self.read_calls() if call["action"] == "startup"]
        scratch_paths = [call["args"][call["args"].index("--scratch") + 1] for call in startup_calls]
        report_paths = [call["args"][call["args"].index("--report") + 1] for call in startup_calls]
        self.assertEqual(len(set(scratch_paths)), 2)
        self.assertEqual(len(set(report_paths)), 2)

    def test_diagnostics_creation_failure_preserves_conflicting_file(self):
        previous_report = self.repo / "diagnostics/alliance-mongo-startup-previous.json"
        del self.protected[previous_report]
        previous_report.unlink()
        diagnostics = self.repo / "diagnostics"
        diagnostics.rmdir()
        diagnostics.write_bytes(b"existing file at diagnostics path")
        self.protected[diagnostics] = hashlib.sha256(diagnostics.read_bytes()).hexdigest()
        self.run_helper(success=False, expected_logs=0, logged=False)
        self.assertEqual(self.read_calls(), [])


if __name__ == "__main__":
    unittest.main()
