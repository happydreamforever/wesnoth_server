"""Execute runtime-root selection with PowerShell and simulated native programs.

The temporary C: PowerShell drive maps to Linux storage. These exercise the
actual wrappers, but do not replace Windows 5.1, junction or MongoDB acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
WRAPPERS = {
    "init": "Initialize-WindowsAlliance.ps1",
    "database": "Run-WindowsAllianceDatabase.ps1",
    "serve": "Run-WindowsAlliance.ps1",
    "check": "Test-WindowsAlliance.ps1",
}


@unittest.skipUnless(PWSH.is_file(), "Linux PowerShell host unavailable")
class RuntimeRootPowerShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance runtime paths ")
        self.base = Path(self.temp.name)
        self.repo = self.base / "repository"
        self.drive = self.base / "profile drive"
        self.caller = self.base / "caller directory"
        self.drive.mkdir()
        self.caller.mkdir()
        (self.repo / "tools").mkdir(parents=True)
        for name in ("Alliance-Common.ps1", *WRAPPERS.values()):
            shutil.copy2(ROOT / "tools" / name, self.repo / "tools" / name)
        (self.repo / "tools/alliance_dependencies.py").touch()
        self.python = self.repo / "build/alliance-venv/Scripts/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,sys\n"
            'with open(os.environ["ALLIANCE_CALLS"], "a") as f:\n'
            ' f.write(json.dumps({"args":sys.argv[1:], "cwd":os.getcwd()})+"\\n")\n'
            'print("Simulated native output")\n'
            'sys.exit(9 if os.environ.get("ALLIANCE_FAIL") in sys.argv[1:] else 0)\n'
        )
        self.python.chmod(0o755)
        self.mongod = self.repo / "build/alliance-mongodb/bin/mongod.exe"
        self.mongod.parent.mkdir(parents=True)
        self.mongod.write_bytes(b"simulated mongod")
        self.calls = self.base / "calls.jsonl"
        self.sentinels = {}
        for parent in (
            self.repo / "runtime/alliance",
            self.repo / "build/previous fixture",
            self.drive / "Users/Uni/AppData/Local/WesnothAlliance",
        ):
            parent.mkdir(parents=True, exist_ok=True)
            marker = parent / "preserved marker"
            marker.write_bytes(b"preserve this existing state")
            self.sentinels[marker] = marker.read_bytes()
        self.driver = self.base / "driver.ps1"
        self.driver.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "$null = New-PSDrive -Name C -PSProvider FileSystem -Root $env:ALLIANCE_DRIVE\n"
            "if ($env:ALLIANCE_REMOTE -eq 'yes') {\n"
            " function Get-PSDrive {\n"
            "  param([string]$Name)\n"
            "  [pscustomobject]@{ Provider = @{Name='FileSystem'}; Root='C:\\'; DisplayRoot='\\\\server\\share' }\n"
            " }\n"
            "}\n"
            "$before = (Get-Location).Path\n"
            "$arguments = @{}\n"
            "if ($env:ALLIANCE_EXPLICIT -eq 'yes') { $arguments.RuntimeRoot = $env:ALLIANCE_ROOT }\n"
            "& $env:ALLIANCE_WRAPPER @arguments\n"
            "$code = $LASTEXITCODE\n"
            'Write-Host ("CALLER_RESTORED: " + ((Get-Location).Path -ceq $before))\n'
            "exit $code\n"
        )
        self.env = {
            **os.environ,
            "OS": "Windows_NT",
            "ALLIANCE_DRIVE": str(self.drive),
            "ALLIANCE_CALLS": str(self.calls),
        }

    def tearDown(self):
        for path, contents in self.sentinels.items():
            self.assertEqual(path.read_bytes(), contents, path)
        self.temp.cleanup()

    def invoke(self, command="check", *, root=None, failure="", remote=False):
        return subprocess.run(
            [str(PWSH), "-NoProfile", "-File", str(self.driver)],
            cwd=self.caller,
            env={
                **self.env,
                "ALLIANCE_WRAPPER": str(self.repo / "tools" / WRAPPERS[command]),
                "ALLIANCE_EXPLICIT": "yes" if root is not None else "no",
                "ALLIANCE_ROOT": root or "",
                "ALLIANCE_FAIL": failure,
                "ALLIANCE_REMOTE": "yes" if remote else "",
            },
            capture_output=True,
            text=True,
            timeout=30,
        )

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CALLER_RESTORED: True", result.stdout)

    def assert_rejected_without_native(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_calls(), [])
        self.assertIn("CALLER_RESTORED: True", result.stdout)
        self.assertFalse((self.repo / "diagnostics").exists())

    def test_all_four_forward_literal_nonexistent_profile_path_and_preserve_state(self):
        selected = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime [local] with spaces"
        for command in WRAPPERS:
            with self.subTest(command=command):
                result = self.invoke(command, root=r"C:\Users\Uni\AppData\Local\WesnothAlliance\runtime [local] with spaces")
                self.assert_success(result)
                calls = self.read_calls()
                args = calls[-1]["args"]
                self.assertEqual(args[:4], ["-E", "-s", "-m", "alliance"])
                self.assertEqual(args[args.index("--runtime") + 1], str(selected))
                self.assertEqual(args[-1], command)
                self.assertEqual("--mongod" in args, command in ("init", "database"))
                self.assertEqual(calls[-1]["cwd"], str(self.repo))
                self.assertIn("Alliance runtime: " + str(selected), result.stdout)
                self.assertIn("MongoDB log: " + str(selected / "logs/mongodb.log"), result.stdout)
                self.assertFalse(selected.exists(), "Wrapper must not create the runtime")

    def test_default_runtime_remains_repository_location(self):
        result = self.invoke()
        self.assert_success(result)
        args = self.read_calls()[-1]["args"]
        self.assertEqual(args[args.index("--runtime") + 1], str(self.repo / "runtime/alliance"))

    def test_existing_directory_is_forwarded_without_change(self):
        selected = self.drive / "Users/Uni/AppData/Local/WesnothAlliance"
        before = {str(p.relative_to(selected)): p.read_bytes() for p in selected.rglob("*") if p.is_file()}
        result = self.invoke(root=r"C:\Users\Uni\AppData\Local\WesnothAlliance")
        self.assert_success(result)
        self.assertEqual(before, {str(p.relative_to(selected)): p.read_bytes() for p in selected.rglob("*") if p.is_file()})

    def test_invalid_paths_stop_before_native_programs(self):
        for selected in (
            "", "  ", "relative", r"\rooted", "C:relative", r"\\server\share\game",
            r"\\?\C:\game", r"\\.\C:\game", r"Z:\absent drive\game",
            r"C:\Users\..\game", r"C:\Users\.\game", "C:\\game.\\runtime",
            "C:\\game \\runtime", r"C:\game:stream", r"C:\game*\runtime",
        ):
            with self.subTest(selected=selected):
                self.assert_rejected_without_native(self.invoke(root=selected))

    def test_network_mapped_drive_is_rejected_before_native_programs(self):
        self.assert_rejected_without_native(self.invoke(root=r"C:\runtime", remote=True))

    def test_existing_file_as_leaf_or_parent_is_rejected(self):
        (self.drive / "file").write_bytes(b"unchanged file")
        for selected in (r"C:\file", r"C:\file\runtime"):
            with self.subTest(selected=selected):
                self.assert_rejected_without_native(self.invoke(root=selected))
                self.assertEqual((self.drive / "file").read_bytes(), b"unchanged file")

    def test_symlink_as_leaf_or_parent_and_dangling_symlink_are_rejected(self):
        (self.drive / "redirect").symlink_to(self.drive / "Users", target_is_directory=True)
        (self.drive / "dangling").symlink_to(self.drive / "missing", target_is_directory=True)
        for selected in (r"C:\redirect", r"C:\redirect\runtime", r"C:\dangling\runtime"):
            with self.subTest(selected=selected):
                self.assert_rejected_without_native(self.invoke(root=selected))
                self.assertFalse((self.drive / "Users/runtime").exists())
                self.assertFalse((self.drive / "missing").exists())

    def test_init_never_starts_transcript_on_success_or_native_failure(self):
        for failure in ("", "init", "check-installed"):
            with self.subTest(failure=failure):
                result = self.invoke("init", root=r"C:\new runtime", failure=failure)
                self.assertEqual(result.returncode == 0, not failure, result.stdout + result.stderr)
                self.assertIn("CALLER_RESTORED: True", result.stdout)
                self.assertNotIn("Saved log:", result.stdout)
                self.assertFalse((self.repo / "diagnostics").exists())

    def test_pin_failures_stop_before_runtime_and_restore_location(self):
        for failure, expected_calls in (("check-python", 1), ("check-installed", 2)):
            with self.subTest(failure=failure):
                self.calls.unlink(missing_ok=True)
                result = self.invoke(root=r"C:\new runtime", failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.read_calls()), expected_calls)
                self.assertIn("CALLER_RESTORED: True", result.stdout)
                self.assertFalse((self.drive / "new runtime").exists())
                if failure == "check-installed":
                    self.assertIn("Saved log:", result.stdout)

    def test_runtime_failure_retains_transcript_and_restores_location(self):
        result = self.invoke(root=r"C:\new runtime", failure="check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CALLER_RESTORED: True", result.stdout)
        self.assertIn("Alliance check failed with exit 9", result.stdout)
        logs = list((self.repo / "diagnostics").glob("*.txt"))
        self.assertEqual(len(logs), 1)
        self.assertIn("Alliance runtime: " + str(self.drive / "new runtime"), logs[0].read_text(encoding="utf-8-sig"))
        self.assertFalse((self.drive / "new runtime").exists())


if __name__ == "__main__":
    unittest.main()
