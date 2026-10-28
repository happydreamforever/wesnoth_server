"""Run the real PowerShell collector wrapper with simulated Windows boundaries.

These Linux pwsh tests exercise orchestration, failure reporting and preservation.
The child JSON, CIM process query and Windows ACL query are controlled fixtures;
they do not establish native Windows file-access or Ninja build acceptance.
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
HELPER = 'Test-WindowsWorldWorkerNinja.ps1'

FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['NINJA_WRAPPER_CALLS'], 'a') as stream:
    stream.write(json.dumps({'args': args, 'cwd': os.getcwd(), 'path': os.environ['PATH']}) + '\n')
report = pathlib.Path(args[args.index('--report') + 1])
mode = os.environ.get('NINJA_WRAPPER_MODE', '')
value = {'format': 1, 'purpose': 'wesnoth-world-worker-ninja-state',
         'collection': {'complete': True}, 'native_probe_fixture': True}
if mode in ('incomplete', 'failed'):
    value['collection']['complete'] = False
if mode == 'nonboolean': value['collection']['complete'] = 'true'
if mode == 'purpose': value['purpose'] = 'unrelated-report'
if mode == 'format': value['format'] = 2
if mode != 'missing':
    with report.open('x') as stream:
        if mode == 'malformed': stream.write('PRIVATE_BAD_JSON invalid')
        elif mode == 'empty': pass
        else: json.dump(value, stream)
print('SIMULATED NINJA STATE COLLECTOR STDOUT', flush=True)
print('SIMULATED NINJA STATE COLLECTOR STDERR', file=sys.stderr, flush=True)
sys.exit(7 if mode == 'failed' else 0)
'''

LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:NINJA_WRAPPER_SETTINGS -Raw | ConvertFrom-Json
function Save-FixtureCall($Value) {
    [IO.File]::AppendAllText($env:NINJA_WRAPPER_BOUNDARIES, (($Value | ConvertTo-Json -Compress) + "`n"))
}
function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName, [string]$Filter, [string[]]$Property)
    Save-FixtureCall @{ operation = 'processes'; class_name = $ClassName; filter = $Filter; properties = $Property }
    # PowerShell transcripts may include caught exception text. These synthetic
    # query errors carry no account data; excluded properties are tested below.
    if ($env:NINJA_WRAPPER_AUXILIARY -eq 'process') { throw 'SIMULATED_PROCESS_QUERY_DENIED' }
    if ($env:NINJA_WRAPPER_AUXILIARY -eq 'empty_processes') { return }
    [pscustomobject]@{
        ProcessId = 42; ParentProcessId = 21; Name = 'ninja.exe'
        ExecutablePath = '/fixture/ninja.exe'; CreationDate = '2026-10-28T12:15:27Z'
        CommandLine = 'PRIVATE_PROCESS_COMMAND_LINE'
    }
}
function Get-Acl {
    [CmdletBinding()]
    param([string]$LiteralPath)
    Save-FixtureCall @{ operation = 'acl'; path = $LiteralPath }
    if ($env:NINJA_WRAPPER_AUXILIARY -eq 'acl') { throw 'SIMULATED_ACL_QUERY_DENIED' }
    [pscustomobject]@{
        Owner = 'fixture owner'; Group = 'fixture group'; AreAccessRulesProtected = $false
        AccessToString = 'fixture permissions'; PrivateUnrequestedField = 'PRIVATE_ACL_FIELD'
    }
}
function Start-Process { throw 'Forbidden process start.' }
function Stop-Process { throw 'Forbidden process stop.' }
function powershell.exe { throw 'Forbidden secondary helper.' }
function cmake.exe { throw 'Forbidden configure.' }
function ninja.exe { throw 'Forbidden build.' }
function Remove-Item { throw 'Forbidden removal.' }
function Set-Acl { throw 'Forbidden ACL change.' }
$env:PATH = $env:NINJA_WRAPPER_BASE_PATH
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
class NinjaDiagnosticWrapperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='world ninja wrapper ')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / 'tools'
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        shutil.copyfile(ROOT / 'tools' / HELPER, self.helper)
        (self.tools / 'inspect_world_worker_ninja.py').write_text('# Controlled collector child fixture.\n')
        self.local = self.root / 'profile'
        self.python = self.local / 'Programs/Python/Python312/python.exe'
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON.replace('#!/usr/bin/python3', '#!' + sys.executable, 1))
        self.python.chmod(0o755)
        self.engine = self.repo / 'build/windows-world-worker/engine'
        for relative in (
                'build/windows-world-worker/owner.json',
                'build/windows-world-worker/engine/.ninja_log',
                'build/windows-world-worker/engine/.ninja_log.restat',
                'build/windows-world-worker/engine/.ninja_log.recompact',
                'build/windows-world-worker/engine/.ninja_deps',
                'build/windows-world-worker/engine/.ninja_deps.recompact',
                'build/windows-world-worker/engine/build.ninja',
                'build/windows-world-worker/engine/src/retained.obj',
                'build/windows-world-worker.resource-recovery.json',
                'build/windows-world-worker.resource-recovery-complete.json',
                'build/windows-world-worker.sysroot-recovery.json',
                'build/world-worker-prefix/receipt.json',
                'runtime-v2/private.json', '.env', 'README.md'):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'PRIVATE_PRESERVATION_SENTINEL')
        self.protected = {path: self.fingerprint(path) for path in self.root.rglob('*') if path.is_file()}
        self.calls = self.root / 'calls.jsonl'
        self.boundaries = self.root / 'boundaries.jsonl'
        self.settings_path = self.root / 'settings.json'
        self.settings = {'helper': str(self.helper), 'python': str(self.python), 'explicit_python': True}
        self.launcher = self.root / 'launcher.ps1'
        self.launcher.write_text(LAUNCHER)
        self.env = {**os.environ, 'OS': 'Windows_NT', 'LOCALAPPDATA': str(self.local),
                    'NINJA_WRAPPER_SETTINGS': str(self.settings_path),
                    'NINJA_WRAPPER_CALLS': str(self.calls), 'NINJA_WRAPPER_BOUNDARIES': str(self.boundaries),
                    'NINJA_WRAPPER_BASE_PATH': os.environ['PATH']}

    @staticmethod
    def fingerprint(path):
        info = path.stat()
        return (hashlib.sha256(path.read_bytes()).hexdigest(), info.st_size, info.st_mtime_ns,
                info.st_mode, info.st_ino)

    def invoke(self, *, mode='', auxiliary='', success=True):
        self.settings_path.write_text(json.dumps(self.settings))
        result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-NonInteractive',
                                 '-File', str(self.launcher)], cwd=self.root,
            env={**self.env, 'NINJA_WRAPPER_MODE': mode, 'NINJA_WRAPPER_AUXILIARY': auxiliary},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual('WORLD WORKER NINJA DIAGNOSTIC COMPLETE' in result.stdout, success, result.stdout)
        self.assertIn('CALLER STATE PRESERVED', result.stdout)
        self.assertNotIn('PRIVATE', result.stdout)
        self.assertNotIn('Forbidden', result.stdout)
        for path, before in self.protected.items():
            self.assertEqual(self.fingerprint(path), before, str(path))
        logs = list((self.repo / 'diagnostics').glob('world-worker-ninja-*.txt'))
        self.assertTrue(logs)
        for path in logs:
            self.assertNotIn('PRIVATE', path.read_text(encoding='utf-8-sig'))
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        boundaries = [json.loads(line) for line in self.boundaries.read_text().splitlines()] if self.boundaries.exists() else []
        return result, calls, boundaries

    def test_exact_child_arguments_literal_paths_and_caller_state(self):
        result, calls, boundaries = self.invoke()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'][:4], ['-I', '-B', str(self.tools / 'inspect_world_worker_ninja.py'), '--report'])
        self.assertEqual(len(calls[0]['args']), 5)
        report = Path(calls[0]['args'][4])
        self.assertEqual(report.parent, self.repo / 'diagnostics')
        self.assertTrue(json.loads(report.read_text())['collection']['complete'])
        self.assertEqual(calls[0]['cwd'], str(self.root))
        self.assertEqual(calls[0]['path'], self.env['PATH'])
        self.assertIn('SIMULATED NINJA STATE COLLECTOR STDERR', result.stdout)
        self.assertIn('Collection only.', result.stdout)
        self.assertEqual(boundaries[0]['properties'], ['ProcessId', 'ParentProcessId', 'Name', 'ExecutablePath', 'CreationDate'])
        self.assertEqual(boundaries[0]['class_name'], 'Win32_Process')
        self.assertNotIn('CommandLine', json.dumps(boundaries))
        acl_paths = {row['path'] for row in boundaries if row['operation'] == 'acl'}
        self.assertEqual(acl_paths, {str(self.engine), *(str(self.engine / leaf) for leaf in
            ('.ninja_log', '.ninja_log.restat', '.ninja_log.recompact', '.ninja_deps', '.ninja_deps.recompact', 'build.ninja'))})

    def test_default_python_uses_separate_python312_installation(self):
        self.settings['explicit_python'] = False
        _, calls, _ = self.invoke()
        self.assertEqual(len(calls), 1)

    def test_empty_process_snapshot_is_valid(self):
        result, calls, _ = self.invoke(auxiliary='empty_processes')
        self.assertEqual(len(calls), 1)
        self.assertIn('No matching build processes.', result.stdout)

    def test_child_failure_retains_report_without_retry(self):
        result, calls, _ = self.invoke(mode='failed', success=False)
        self.assertEqual(len(calls), 1)
        report = Path(calls[0]['args'][-1])
        self.assertFalse(json.loads(report.read_text())['collection']['complete'])
        self.assertIn('stage=collection', result.stdout)
        self.assertIn(str(report), result.stdout)

    def test_missing_report_is_rejected(self):
        result, calls, _ = self.invoke(mode='missing', success=False)
        self.assertEqual(len(calls), 1)
        self.assertFalse(Path(calls[0]['args'][-1]).exists())
        self.assertIn('stage=report', result.stdout)

    def test_malformed_report_retained_without_printing_contents(self):
        result, calls, _ = self.invoke(mode='malformed', success=False)
        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0]['args'][-1]).read_text(), 'PRIVATE_BAD_JSON invalid')
        self.assertIn('stage=report', result.stdout)

    def test_empty_report_is_rejected(self):
        _, calls, _ = self.invoke(mode='empty', success=False)
        self.assertEqual(Path(calls[0]['args'][-1]).stat().st_size, 0)

    def test_incomplete_collection_is_not_success(self):
        _, calls, _ = self.invoke(mode='incomplete', success=False)
        self.assertEqual(len(calls), 1)

    def test_nonboolean_collection_is_not_success(self):
        _, calls, _ = self.invoke(mode='nonboolean', success=False)
        self.assertEqual(len(calls), 1)

    def test_wrong_report_purpose_is_rejected(self):
        self.invoke(mode='purpose', success=False)

    def test_wrong_report_format_is_rejected(self):
        self.invoke(mode='format', success=False)

    def test_process_failure_still_collects_json_and_permissions(self):
        result, calls, boundaries = self.invoke(auxiliary='process', success=False)
        self.assertEqual(len(calls), 1)
        self.assertTrue(json.loads(Path(calls[0]['args'][-1]).read_text())['collection']['complete'])
        self.assertIn('PROCESS SNAPSHOT UNAVAILABLE', result.stdout)
        self.assertEqual(sum(row['operation'] == 'acl' for row in boundaries), 7)

    def test_acl_failure_still_collects_json_and_other_permissions(self):
        result, calls, boundaries = self.invoke(auxiliary='acl', success=False)
        self.assertEqual(len(calls), 1)
        self.assertTrue(json.loads(Path(calls[0]['args'][-1]).read_text())['collection']['complete'])
        self.assertEqual(result.stdout.count('PERMISSION SNAPSHOT UNAVAILABLE'), 7)
        self.assertEqual(sum(row['operation'] == 'acl' for row in boundaries), 7)

    def test_wrong_host_stops_before_process_or_python(self):
        self.env['OS'] = 'Linux'
        result, calls, boundaries = self.invoke(success=False)
        self.assertEqual((calls, boundaries), ([], []))
        self.assertIn('stage=host', result.stdout)

    def test_missing_interpreter_stops_before_collection(self):
        self.settings['python'] = str(self.root / 'not installed')
        _, calls, boundaries = self.invoke(success=False)
        self.assertEqual((calls, boundaries), ([], []))

    def test_repeated_invocation_preserves_prior_reports(self):
        _, first, _ = self.invoke()
        report = Path(first[0]['args'][-1])
        before = self.fingerprint(report)
        _, second, _ = self.invoke()
        self.assertEqual(len(second), 2)
        self.assertNotEqual(first[0]['args'][-1], second[1]['args'][-1])
        self.assertEqual(self.fingerprint(report), before)
        self.assertEqual(len(list((self.repo / 'diagnostics').glob('world-worker-ninja-*.txt'))), 2)


if __name__ == '__main__':
    unittest.main()
