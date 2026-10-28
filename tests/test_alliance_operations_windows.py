"""Run the actual PowerShell workflow/maintenance/report wrappers with simulated tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
WRAPPERS = ("Invoke-WindowsAllianceMaintenance.ps1", "Start-WindowsAllianceStack.ps1",
            "New-WindowsAllianceTestReport.ps1")


@unittest.skipUnless(PWSH.is_file(), "Linux PowerShell fixture host unavailable")
class OperationsWindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance operations windows ")
        self.base = Path(self.temp.name)
        self.repo = self.base / "repository"; self.drive = self.base / "drive"; self.drive.mkdir()
        (self.repo / "tools").mkdir(parents=True)
        for name in (*WRAPPERS, "Alliance-Common.ps1"):
            shutil.copy2(ROOT / "tools" / name, self.repo / "tools" / name)
        for name in ("alliance_maintenance.py", "alliance_workflow.py", "alliance_dependencies.py"):
            (self.repo / "tools" / name).touch()
        python = self.repo / "build/alliance-venv-py312/Scripts/python.exe"; python.parent.mkdir(parents=True)
        python.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
            "with open(os.environ['OPS_CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "print('SIMULATED TOOL RESULT')\n"
            "sys.exit(7 if os.environ.get('OPS_FAIL') in sys.argv[1:] else 0)\n")
        python.chmod(0o755)
        self.calls = self.base / "calls.jsonl"
        self.driver = self.base / "driver.ps1"
        self.driver.write_text("$ErrorActionPreference='Stop'\n"
            "$null=New-PSDrive -Name C -PSProvider FileSystem -Root $env:OPS_DRIVE\n"
            "$null=New-PSDrive -Name D -PSProvider FileSystem -Root $env:OPS_DRIVE\n"
            "$arguments=@{}\n"
            "($env:OPS_ARGUMENTS | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $arguments[$_.Name]=$_.Value }\n"
            "$before=(Get-Location).Path\n"
            "& $env:OPS_WRAPPER @arguments\n"
            "$code=$LASTEXITCODE\n"
            "Write-Host ('CALLER_UNCHANGED: '+((Get-Location).Path -ceq $before))\n"
            "exit $code\n")
        self.env = {**os.environ, "OS": "Windows_NT", "LOCALAPPDATA": r"C:\Users\Uni\AppData\Local",
            "OPS_DRIVE": str(self.drive), "OPS_CALLS": str(self.calls)}
        self.sentinel = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime/sentinel"
        self.sentinel.parent.mkdir(parents=True); self.sentinel.write_bytes(b"preserve original runtime")

    def tearDown(self):
        self.assertEqual(self.sentinel.read_bytes(), b"preserve original runtime")
        self.temp.cleanup()

    def invoke(self, wrapper, arguments, failure=""):
        result = subprocess.run([str(PWSH), "-NoProfile", "-File", str(self.driver)], cwd=self.base,
            env={**self.env, "OPS_WRAPPER": str(self.repo / "tools" / wrapper),
                 "OPS_ARGUMENTS": json.dumps(arguments), "OPS_FAIL": failure},
            text=True, capture_output=True, timeout=30)
        self.assertIn("CALLER_UNCHANGED: True", result.stdout, result.stdout + result.stderr)
        return result

    def native_calls(self):
        return [json.loads(row) for row in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_backup_and_restore_forward_only_selected_private_paths(self):
        for operation in ("Backup", "Restore"):
            with self.subTest(operation=operation):
                arguments = {"Operation": operation, "DestinationPath": r"C:\Recovery\copy with spaces"}
                if operation == "Restore": arguments["BackupPath"] = r"C:\Recovery\private backup"
                result = self.invoke(WRAPPERS[0], arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                args = self.native_calls()[-1]
                self.assertEqual(args[:2], ["-I", "-B"])
                self.assertEqual(args[3], operation.lower())
                self.assertEqual(args[args.index("--runtime") + 1], str(self.sentinel.parent))
                self.assertEqual(args[args.index("--destination") + 1], str(self.drive / "Recovery/copy with spaces"))
                self.assertEqual("--backup" in args, operation == "Restore")
                self.assertEqual("--mongod" in args, operation == "Restore")
                self.assertFalse((self.drive / "Recovery").exists(), "Wrapper does not create recovery folders")

    def test_invalid_recovery_paths_stop_before_tools(self):
        for path in (r"\\server\share\backup", "relative", r"C:\Recovery\..\backup"):
            with self.subTest(path=path):
                result = self.invoke(WRAPPERS[0], {"Operation": "Backup", "DestinationPath": path})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.native_calls(), [])

    def test_pin_failure_prevents_maintenance(self):
        result = self.invoke(WRAPPERS[0], {"Operation": "Backup", "DestinationPath": r"C:\Recovery\new"}, "check-installed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.native_calls()), 2)
        self.assertNotIn("backup", self.native_calls()[-1])

    def test_workflow_default_starts_and_optional_check_only_is_forwarded(self):
        for arguments in ({}, {"CheckOnly": True}, {"IncludeBattles": True}, {"CheckOnly": True, "IncludeBattles": True}):
            with self.subTest(arguments=arguments):
                result = self.invoke(WRAPPERS[1], arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                args = self.native_calls()[-1]
                self.assertEqual(args[args.index("--runtime") + 1], str(self.sentinel.parent.with_name("runtime-v2")))
                self.assertEqual("--start" in args, not arguments.get("CheckOnly", False))
                self.assertEqual("--include-battles" in args, arguments.get("IncludeBattles", False))
                self.assertIn("--report", args)

    def test_workflow_tool_failure_is_not_reported_as_success(self):
        result = self.invoke(WRAPPERS[1], {}, "--start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Workflow stopped", result.stdout)

    def test_combined_user_report_records_explicit_evidence_without_running_tools(self):
        result = self.invoke(WRAPPERS[2], {"BatchId": "1192615", "WanStatus": "Disconnected",
            "PassedSteps": ["A", "B"], "FailedSteps": ["C"], "NotRunSteps": ["D", "W05"]})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.native_calls(), [])
        reports = list((self.repo / "diagnostics").glob("alliance-acceptance-*.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text())
        self.assertEqual(report["evidence"], "user_reported")
        self.assertEqual(report["wan_status"], "Disconnected")
        self.assertEqual(report["steps"], [{"id": "A", "status": "passed"}, {"id": "B", "status": "passed"},
            {"id": "C", "status": "failed"}, {"id": "D", "status": "not_run"}, {"id": "W05", "status": "not_run"}])

    def test_report_rejects_ambiguous_or_duplicate_step_results(self):
        for arguments in ({"PassedSteps": ["A"], "FailedSteps": ["A"]}, {"PassedSteps": ["a"]}, {},
                          {"PassedSteps": ["A password"]}):
            with self.subTest(arguments=arguments):
                result = self.invoke(WRAPPERS[2], {"BatchId": "1192615", "WanStatus": "NotRecorded", **arguments})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.repo / "diagnostics").exists())

    def test_report_comma_list_through_native_file_argument_boundary(self):
        wrapper = self.repo / "tools" / WRAPPERS[2]
        result = subprocess.run([str(PWSH), "-NoProfile", "-File", str(wrapper), "-BatchId", "1192615",
            "-WanStatus", "Disconnected", "-PassedSteps", "A,B,C", "-NotRunSteps", "D,E"],
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.repo / "diagnostics").glob("alliance-acceptance-*.json"))
        record = json.loads(reports[0].read_text())
        self.assertEqual([row["id"] for row in record["steps"]], list("ABCDE"))

    def test_launcher_preserves_host_and_native_output_in_exact_step_log(self):
        # Read the production generator without importing database dependencies
        # into this host-only PowerShell test process.
        import ast
        source = ast.parse((ROOT / "tools/alliance_workflow.py").read_text())
        names = {"quoted", "launcher_script"}
        module = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        namespace = {"ROOT": self.repo, "STEPS": (("W02", "database", 27018, "Run-WindowsAllianceDatabase.ps1"),),
                     "BATTLE_STEP": ("W05", "battles", 15002, "Run-WindowsAllianceBattles.ps1"),
                     "MULTIPLAYER_STEP": ("W06", "multiplayer", 15000, "Run-WindowsMultiplayer.ps1"), "WorkflowError": ValueError}
        exec(compile(module, "production-launcher-generator", "exec"), namespace)
        wrapper = self.repo / "tools/Run-WindowsAllianceDatabase.ps1"
        wrapper.write_text("param([string]$RuntimeRoot)\nWrite-Host 'HOST READY'\n'FORMATTED READY' | Out-Host\nWrite-Output ('RUNTIME='+$RuntimeRoot)\nexit 7\n")
        log = self.base / "step ' log.txt"; log.touch()
        runtime = self.base / "runtime ' literal $(must-not-run)"
        script = namespace["launcher_script"](wrapper.name, runtime, self.base, log, PWSH)
        result = subprocess.run([str(PWSH), "-NoProfile", "-Command", script], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        contents = log.read_text()
        self.assertIn("HOST READY", contents)
        self.assertIn("FORMATTED READY", contents)
        self.assertIn("RUNTIME=" + str(runtime), contents)


if __name__ == "__main__": unittest.main()
