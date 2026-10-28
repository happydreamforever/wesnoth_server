"""Actual PowerShell orchestration; Python/native builds are controlled children."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / 'wesnoth_client/build/host-tools/powershell-7.4.6/pwsh'


@unittest.skipUnless(PWSH.is_file(), 'Pinned PowerShell required')
class WorldWorkerResumeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker resume ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "server $ & ' with spaces"
        (self.repo / 'tools').mkdir(parents=True)
        self.helper = self.repo / 'tools/Build-WindowsWorldWorker.ps1'
        shutil.copyfile(ROOT / 'tools/Build-WindowsWorldWorker.ps1', self.helper)
        self.python = self.root / 'python.exe'
        self.python.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
pathlib.Path(os.environ['RESUME_CALL']).write_text(json.dumps(sys.argv[1:]))
print('CONTROLLED WORKER CHILD')
sys.exit(int(os.environ.get('RESUME_EXIT', '0')))
''')
        self.python.chmod(0o755)
        self.call = self.root / 'call.json'
        self.env = dict(os.environ, LOCALAPPDATA=str(self.root), RESUME_CALL=str(self.call))
        self.report = self.root / "report $ & ' spaces.json"
        self.report.write_bytes(b'reviewed report sentinel')
        self.sentinel = self.repo / 'build/previous-stage/old.obj'
        self.sentinel.parent.mkdir(parents=True)
        self.sentinel.write_bytes(b'compiled data sentinel')
        self.before = self.sentinel.stat()

    def run_helper(self, *extra):
        result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File', str(self.helper),
            '-PythonPath', str(self.python), *extra], env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        self.assertEqual(self.sentinel.read_bytes(), b'compiled data sentinel')
        self.assertEqual(self.sentinel.stat().st_mtime_ns, self.before.st_mtime_ns)
        self.assertEqual(self.report.read_bytes(), b'reviewed report sentinel')
        self.assertEqual(len(list((self.repo / 'diagnostics').glob('*.txt'))), 1)
        self.assertIn('Saved log:', result.stdout)
        return result

    def test_report_path_is_one_literal_child_argument(self):
        result = self.run_helper('-PreservePreviousBuild', '-NinjaReportPath', str(self.report))
        self.assertEqual(result.returncode, 0, result.stdout)
        args = json.loads(self.call.read_text())
        self.assertEqual(args[:2], ['-I', '-B'])
        self.assertEqual(args[-3:], ['--preserve-previous', '--ninja-report', str(self.report)])
        self.assertIn('--msys', args)
        self.assertIn('--cmake', args)
        self.assertIn('--game-data', args)

    def test_original_build_without_report_stays_supported(self):
        result = self.run_helper('-PreservePreviousBuild')
        self.assertEqual(result.returncode, 0, result.stdout)
        args = json.loads(self.call.read_text())
        self.assertNotIn('--ninja-report', args)
        self.assertEqual(args[-1], '--preserve-previous')

    def test_fresh_build_stays_supported(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stdout)
        args = json.loads(self.call.read_text())
        self.assertNotIn('--ninja-report', args)
        self.assertNotIn('--preserve-previous', args)

    def test_report_requires_explicit_preservation(self):
        result = self.run_helper('-NinjaReportPath', str(self.report))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.call.exists())
        self.assertIn('requires -PreservePreviousBuild', result.stdout)

    def test_empty_report_is_not_silently_ignored(self):
        result = self.run_helper('-PreservePreviousBuild', '-NinjaReportPath', '')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.call.exists())

    def test_child_failure_is_returned_without_automatic_retry(self):
        self.env['RESUME_EXIT'] = '7'
        result = self.run_helper('-PreservePreviousBuild', '-NinjaReportPath', str(self.report))
        self.assertEqual(result.returncode, 1)
        self.assertIn('Full native World worker build stopped', result.stdout)
        self.assertEqual(result.stdout.count('CONTROLLED WORKER CHILD'), 1)


if __name__ == '__main__':
    unittest.main()
