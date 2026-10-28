"""Actual Linux PowerShell wrappers with simulated Python children.

This does not execute Windows, download packages, or compile the native worker.
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


@unittest.skipUnless(PWSH.is_file(), "The recorded Linux PowerShell executable is unavailable.")
class WorkerPackageWrappers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="world wrapper paths ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "server with spaces"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        for filename in ("Prepare-WindowsWorldWorkerPackages.ps1", "Prepare-WindowsWorldWorker.ps1"):
            shutil.copy2(ROOT / "tools" / filename, self.tools / filename)
        for filename in ("world_worker_packages.py", "build_world_worker.py"):
            (self.tools / filename).write_text("# Wrapper path fixture only.\n", encoding="utf-8")
        self.msys = self.root / "existing msys64"
        self.msys.mkdir()
        (self.msys / "retain.txt").write_bytes(b"existing tools remain")
        self.capture = self.root / "child-arguments.json"
        self.python = self.root / "fixture python"
        self.python.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
pathlib.Path(os.environ['WORLD_WRAPPER_CAPTURE']).write_text(json.dumps(args))
if '--report' in args:
    report = pathlib.Path(args[args.index('--report') + 1])
    report.write_text(json.dumps({'fixture': True, 'exit': int(os.environ.get('WORLD_WRAPPER_EXIT', '0'))}))
print('SIMULATED PYTHON CHILD COMPLETE', flush=True)
sys.exit(int(os.environ.get('WORLD_WRAPPER_EXIT', '0')))
""", encoding="utf-8")
        self.python.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment.update(LOCALAPPDATA=str(self.root), WORLD_WRAPPER_CAPTURE=str(self.capture))

    def invoke(self, filename, *, download=False, exit_code=0, python=None):
        environment = self.environment.copy()
        environment["WORLD_WRAPPER_EXIT"] = str(exit_code)
        command = [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(self.tools / filename),
                   "-MsysRoot", str(self.msys), "-PythonPath", str(python or self.python)]
        if download:
            command.append("-Download")
        return subprocess.run(command, env=environment, capture_output=True, text=True, timeout=45, check=False)

    def test_package_verification_forwards_owned_paths_without_download(self):
        result = self.invoke("Prepare-WindowsWorldWorkerPackages.ps1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads(self.capture.read_text())
        self.assertEqual(args[:5], ["-I", "-B", str(self.tools / "world_worker_packages.py"), "--msys", str(self.msys)])
        self.assertNotIn("--download", args)
        self.assertNotIn("--install", args)
        report = Path(args[args.index("--report") + 1])
        self.assertEqual(report.parent, self.repo / "diagnostics")
        self.assertEqual(json.loads(report.read_text()), {"fixture": True, "exit": 0})
        self.assertIn("without downloading or installing", result.stdout)
        self.assertEqual(len(list(report.parent.glob("world-worker-packages-*.txt"))), 1)

    def test_download_switch_reaches_only_cache_helper(self):
        result = self.invoke("Prepare-WindowsWorldWorkerPackages.ps1", download=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads(self.capture.read_text())
        self.assertEqual(args.count("--download"), 1)
        self.assertNotIn("--install", args)
        self.assertEqual((self.msys / "retain.txt").read_bytes(), b"existing tools remain")

    def test_failed_child_retains_report_and_log_then_retry_uses_new_paths(self):
        retained = self.repo / "build" / "original-preparation-journal.json"
        retained.parent.mkdir()
        retained.write_bytes(b'{"retained": true}')
        first = self.invoke("Prepare-WindowsWorldWorkerPackages.ps1", exit_code=7)
        self.assertEqual(first.returncode, 1, first.stdout + first.stderr)
        args = json.loads(self.capture.read_text())
        first_report = Path(args[args.index("--report") + 1])
        first_bytes = first_report.read_bytes()
        self.assertEqual(json.loads(first_bytes)["exit"], 7)
        self.assertIn("Worker package operation stopped", first.stdout)
        self.assertIn(str(first_report), first.stdout)
        second = self.invoke("Prepare-WindowsWorldWorkerPackages.ps1")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        args = json.loads(self.capture.read_text())
        second_report = Path(args[args.index("--report") + 1])
        self.assertNotEqual(first_report, second_report)
        self.assertEqual(first_report.read_bytes(), first_bytes)
        self.assertEqual(retained.read_bytes(), b'{"retained": true}')
        self.assertEqual(len(list(first_report.parent.glob("world-worker-packages-*.txt"))), 2)

    def test_prefix_preparation_forwards_offline_action_and_failure(self):
        for exit_code in (0, 9):
            with self.subTest(exit_code=exit_code):
                result = self.invoke("Prepare-WindowsWorldWorker.ps1", exit_code=exit_code)
                self.assertEqual(result.returncode, 0 if exit_code == 0 else 1, result.stdout + result.stderr)
                self.assertEqual(json.loads(self.capture.read_text()), ["-I", "-B", str(self.tools / "build_world_worker.py"), "--msys", str(self.msys), "--prepare-dependencies"])
                self.assertIn("package scripts and hooks are not run", result.stdout)
                self.assertIn("Saved log:", result.stdout)
                if exit_code:
                    self.assertIn("preparation stopped", result.stdout)
        self.assertEqual(len(list((self.repo / "diagnostics").glob("world-worker-prepare-*.txt"))), 2)

    def test_unavailable_python_still_saves_failure_transcript(self):
        for filename, stem in (("Prepare-WindowsWorldWorkerPackages.ps1", "world-worker-packages-"),
                               ("Prepare-WindowsWorldWorker.ps1", "world-worker-prepare-")):
            with self.subTest(filename=filename):
                result = self.invoke(filename, python=self.root / "missing interpreter")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("ERROR:", result.stdout)
                self.assertIn("Saved log:", result.stdout)
                logs = list((self.repo / "diagnostics").glob(stem + "*.txt"))
                self.assertEqual(len(logs), 1)
                self.assertIn("ERROR:", logs[0].read_text())
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
