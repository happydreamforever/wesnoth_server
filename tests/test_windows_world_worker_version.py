"""Actual Linux PowerShell orchestration with a controlled diagnostic child.

The collector JSON and Windows host are fixtures. These checks cover wrapper
arguments, report acceptance, failure handling and preservation; they do not
execute or accept the Windows worker or its DLLs.
"""
from __future__ import annotations

import hashlib
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
HELPER = 'Test-WindowsWorldWorkerVersion.ps1'
PRESERVATION = ('bin_unchanged', 'owner_unchanged', 'linked_executable_unchanged',
                'version_header_unchanged', 'dependency_receipt_unchanged',
                'source_binding_unchanged', 'no_receipt_created')

FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['VERSION_WRAPPER_CALLS'], 'a') as stream:
    stream.write(json.dumps({'args': args, 'cwd': os.getcwd(), 'path': os.environ['PATH']}) + '\n')
report = pathlib.Path(args[args.index('--report') + 1])
mode = os.environ.get('VERSION_WRAPPER_MODE', '')
fields = ('bin_unchanged', 'owner_unchanged', 'linked_executable_unchanged',
          'version_header_unchanged', 'dependency_receipt_unchanged',
          'source_binding_unchanged', 'no_receipt_created')
value = {'format': 1, 'purpose': 'wesnoth-world-worker-version-diagnostic',
         'release': 1192624, 'scope': 'existing-worker-version-only',
         'collection': {'complete': True}, 'receipt_written': False, 'build_performed': False,
         'preservation': {field: True for field in fields},
         'result': {'outcome': 'version_match', 'version_matches': True}}
if mode in ('incomplete', 'failed'): value['collection']['complete'] = False
if mode == 'nonboolean': value['collection']['complete'] = 'true'
if mode in ('version_mismatch', 'empty_stdout', 'nonzero_exit', 'timeout', 'launch_error', 'output_limit'):
    value['result'] = {'outcome': mode, 'version_matches': False}
if mode == 'purpose': value['purpose'] = 'unrelated-report'
if mode == 'format': value['format'] = 2
if mode == 'release': value['release'] = 1192623
if mode == 'scope': value['scope'] = 'completed-build'
if mode in ('receipt_written', 'build_performed'): value[mode] = True
if mode == 'nonboolean_receipt': value['receipt_written'] = 'false'
if mode == 'nonboolean_build': value['build_performed'] = 'false'
if mode.startswith('preservation:'): value['preservation'][mode.split(':', 1)[1]] = False
if mode == 'missing_preservation': value.pop('preservation')
if mode == 'nonboolean_preservation': value['preservation']['bin_unchanged'] = 'true'
if mode != 'missing':
    with report.open('x') as stream:
        if mode == 'malformed': stream.write('PRIVATE_BAD_JSON invalid')
        elif mode == 'empty': pass
        elif mode == 'oversized': stream.write(' ' * 1048577)
        else: json.dump(value, stream)
print('SIMULATED VERSION COLLECTOR STDOUT', flush=True)
print('SIMULATED VERSION COLLECTOR STDERR', file=sys.stderr, flush=True)
sys.exit(7 if mode == 'failed' else 0)
'''

LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:VERSION_WRAPPER_SETTINGS -Raw | ConvertFrom-Json
function Start-Process { throw 'Forbidden process start.' }
function Stop-Process { throw 'Forbidden process stop.' }
function powershell.exe { throw 'Forbidden secondary helper.' }
function cmake.exe { throw 'Forbidden configure.' }
function ninja.exe { throw 'Forbidden build.' }
function Remove-Item { throw 'Forbidden removal.' }
function Set-Acl { throw 'Forbidden ACL change.' }
$env:PATH = $env:VERSION_WRAPPER_BASE_PATH
$beforePath = $env:PATH
$beforeLocation = (Get-Location).Path
$arguments = @{}
if ($settings.explicit_python) { $arguments.PythonPath = $settings.python }
& $settings.helper @arguments
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper changed caller PATH.' }
if ((Get-Location).Path -cne $beforeLocation) { throw 'Helper changed caller working directory.' }
Write-Host 'CALLER STATE PRESERVED'
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), 'Existing pinned Linux PowerShell is required; no tools installed')
class WorkerVersionWrapperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='worker version wrapper ')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / 'tools'
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        shutil.copyfile(ROOT / 'tools' / HELPER, self.helper)
        (self.tools / 'inspect_world_worker_version.py').write_text('# Controlled collector child fixture.\n')
        self.local = self.root / 'profile'
        self.python = self.local / 'Programs/Python/Python312/python.exe'
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON.replace('#!/usr/bin/python3', '#!' + sys.executable, 1))
        self.python.chmod(0o755)
        for relative in ('build/windows-world-worker/owner.json',
                'build/windows-world-worker/engine/.ninja_log',
                'build/windows-world-worker/engine/.ninja_log.restat',
                'build/windows-world-worker/engine/.ninja_deps',
                'build/windows-world-worker/engine/src/world-worker.exe',
                'build/windows-world-worker/bin/world-worker.exe',
                'build/windows-world-worker/bin/retained.dll',
                'build/windows-world-worker/engine/src/retained.obj',
                'build/windows-world-worker/source/src/wesconfig.h',
                'build/windows-world-worker.account-recovery.json',
                'build/windows-world-worker.ninja-recovery.json',
                'build/windows-world-worker.resource-recovery.json',
                'build/world-worker-prefix/receipt.json',
                'runtime-v2/private.json', '.env', 'README.md'):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'PRIVATE_PRESERVATION_SENTINEL')
        self.protected = {path: self.fingerprint(path) for path in self.root.rglob('*') if path.is_file()}
        self.calls = self.root / 'calls.jsonl'
        self.settings_path = self.root / 'settings.json'
        self.settings = {'helper': str(self.helper), 'python': str(self.python), 'explicit_python': True}
        self.launcher = self.root / 'launcher.ps1'
        self.launcher.write_text(LAUNCHER)
        self.env = {**os.environ, 'OS': 'Windows_NT', 'LOCALAPPDATA': str(self.local),
                    'VERSION_WRAPPER_SETTINGS': str(self.settings_path),
                    'VERSION_WRAPPER_CALLS': str(self.calls),
                    'VERSION_WRAPPER_BASE_PATH': os.environ['PATH']}

    @staticmethod
    def fingerprint(path):
        info = path.stat()
        return (hashlib.sha256(path.read_bytes()).hexdigest(), info.st_size, info.st_mtime_ns,
                info.st_mode, info.st_ino)

    def invoke(self, *, mode='', success=True):
        self.settings_path.write_text(json.dumps(self.settings))
        result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-NonInteractive',
                                 '-File', str(self.launcher)], cwd=self.root,
            env={**self.env, 'VERSION_WRAPPER_MODE': mode},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual('WORLD WORKER VERSION DIAGNOSTIC COMPLETE' in result.stdout, success, result.stdout)
        self.assertNotIn('FULL NATIVE WORLD WORKER BUILD PASSED', result.stdout)
        self.assertIn('CALLER STATE PRESERVED', result.stdout)
        self.assertNotIn('PRIVATE', result.stdout)
        self.assertNotIn('Forbidden', result.stdout)
        for path, before in self.protected.items():
            self.assertEqual(self.fingerprint(path), before, str(path))
        logs = list((self.repo / 'diagnostics').glob('world-worker-version-*.txt'))
        self.assertTrue(logs)
        for path in logs:
            self.assertNotIn('PRIVATE', path.read_text(encoding='utf-8-sig'))
        self.assertFalse((self.repo / 'build/windows-world-worker/receipt.json').exists())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_exact_child_arguments_literal_paths_and_caller_state(self):
        result, calls = self.invoke()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'][:4], ['-I', '-B', str(self.tools / 'inspect_world_worker_version.py'), '--report'])
        self.assertEqual(len(calls[0]['args']), 5)
        report = Path(calls[0]['args'][4])
        self.assertEqual(report.parent, self.repo / 'diagnostics')
        self.assertTrue(json.loads(report.read_text())['collection']['complete'])
        self.assertEqual(calls[0]['cwd'], str(self.root))
        self.assertEqual(calls[0]['path'], self.env['PATH'])
        self.assertIn('SIMULATED VERSION COLLECTOR STDERR', result.stdout)
        self.assertIn('Version collection only.', result.stdout)

    def test_default_python_uses_verified_python312(self):
        self.settings['explicit_python'] = False
        _, calls = self.invoke()
        self.assertEqual(len(calls), 1)

    def test_collected_failure_outcomes_are_not_build_acceptance(self):
        for mode in ('version_mismatch', 'empty_stdout', 'nonzero_exit', 'timeout', 'launch_error', 'output_limit'):
            with self.subTest(mode=mode):
                before = len(self.calls.read_text().splitlines()) if self.calls.exists() else 0
                _, calls = self.invoke(mode=mode)
                self.assertEqual(len(calls), before + 1)
                report = json.loads(Path(calls[-1]['args'][-1]).read_text())
                self.assertEqual(report['result']['outcome'], mode)
                self.assertFalse(report['result']['version_matches'])

    def test_child_failure_retains_report_without_retry(self):
        result, calls = self.invoke(mode='failed', success=False)
        self.assertEqual(len(calls), 1)
        report = Path(calls[0]['args'][-1])
        self.assertFalse(json.loads(report.read_text())['collection']['complete'])
        self.assertIn('stage=collection', result.stdout)
        self.assertIn(str(report), result.stdout)

    def test_missing_report_is_rejected(self):
        result, calls = self.invoke(mode='missing', success=False)
        self.assertEqual(len(calls), 1)
        self.assertFalse(Path(calls[0]['args'][-1]).exists())
        self.assertIn('stage=report', result.stdout)

    def test_malformed_report_retained_without_printing_contents(self):
        result, calls = self.invoke(mode='malformed', success=False)
        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0]['args'][-1]).read_text(), 'PRIVATE_BAD_JSON invalid')
        self.assertIn('stage=report', result.stdout)

    def test_empty_and_oversized_reports_are_rejected(self):
        for mode in ('empty', 'oversized'):
            with self.subTest(mode=mode):
                result, calls = self.invoke(mode=mode, success=False)
                self.assertIn('stage=report', result.stdout)
                self.assertEqual(Path(calls[-1]['args'][-1]).stat().st_size, 0 if mode == 'empty' else 1048577)

    def test_incomplete_or_nonboolean_collection_is_not_success(self):
        for mode in ('incomplete', 'nonboolean'):
            with self.subTest(mode=mode): self.invoke(mode=mode, success=False)

    def test_wrong_report_identity_or_scope_is_rejected(self):
        for mode in ('purpose', 'format', 'release', 'scope'):
            with self.subTest(mode=mode): self.invoke(mode=mode, success=False)

    def test_receipt_or_build_claim_is_rejected(self):
        for mode in ('receipt_written', 'build_performed', 'nonboolean_receipt', 'nonboolean_build'):
            with self.subTest(mode=mode): self.invoke(mode=mode, success=False)

    def test_every_preservation_field_is_required(self):
        for field in PRESERVATION:
            with self.subTest(field=field): self.invoke(mode='preservation:' + field, success=False)
        for mode in ('missing_preservation', 'nonboolean_preservation'):
            with self.subTest(mode=mode): self.invoke(mode=mode, success=False)

    def test_wrong_host_stops_before_python(self):
        self.env['OS'] = 'Linux'
        result, calls = self.invoke(success=False)
        self.assertEqual(calls, [])
        self.assertIn('stage=host', result.stdout)

    def test_missing_interpreter_stops_before_collection(self):
        self.settings['python'] = str(self.root / 'not installed')
        result, calls = self.invoke(success=False)
        self.assertEqual(calls, [])
        self.assertIn('stage=paths', result.stdout)

    def test_missing_default_profile_stops_before_collection(self):
        self.settings['explicit_python'] = False
        self.env.pop('LOCALAPPDATA')
        result, calls = self.invoke(success=False)
        self.assertEqual(calls, [])
        self.assertIn('stage=host', result.stdout)

    def test_repeated_invocation_retains_prior_reports(self):
        _, first = self.invoke()
        report = Path(first[0]['args'][-1])
        before = self.fingerprint(report)
        _, second = self.invoke()
        self.assertEqual(len(second), 2)
        self.assertNotEqual(first[0]['args'][-1], second[1]['args'][-1])
        self.assertEqual(self.fingerprint(report), before)
        self.assertEqual(len(list((self.repo / 'diagnostics').glob('world-worker-version-*.txt'))), 2)


if __name__ == '__main__':
    unittest.main()
