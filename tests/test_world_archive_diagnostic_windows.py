"""Real zstd diagnostic fixtures and Linux PowerShell Windows-wrapper simulation."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import diagnose_world_worker_archive as diagnostic
from tools import world_worker_archive_prefix as archive
from tools import world_worker_packages as packages
from tests import test_world_worker_archive_prefix as fixtures

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / 'wesnoth_client/build/host-tools/powershell-7.4.6/pwsh'
HELPER = 'Test-WindowsWorldWorkerArchive.ps1'


@unittest.skipUnless(shutil.which('zstd'), 'Existing local zstd is required; no tools installed')
class ArchiveDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArchivePrefix()
        self.fixture.zstd = shutil.which('zstd')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.pins = []; self.fixture.files = {}
        self.fixture.add_package('aom', {'bin/aom.exe': b'MZ synthetic archive fixture', 'share/empty': b''})
        self.fixture.write_manifest()
        self.root = self.fixture.root
        self.build = self.root / 'build'; self.build.mkdir()
        self.msys = self.root / 'msys'; self.msys.mkdir()
        self.report = self.root / 'report.json'
        for path in ('world-worker-prefix/keep', 'world-worker-prefix.archive-preparing/partial',
                     'world-worker-prefix.archive-preparation.json', 'runtime-v2/secret'):
            target = self.build / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'PRIVATE_PRESERVATION_SENTINEL')
        self.protected = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.enterContext(patch.object(diagnostic, 'ROOT', self.root))
        self.enterContext(patch.object(packages, 'MANIFEST', self.fixture.lock))
        self.enterContext(patch.object(packages, 'CACHE', self.fixture.cache))
        self.host = self.enterContext(patch.object(diagnostic, 'check_host'))

    def invoke(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = diagnostic.diagnose(self.msys, self.report)
        self.assertEqual(json.loads(self.report.read_text()), result)
        self.assertNotIn('PRIVATE', output.getvalue() + self.report.read_text())
        for path, content in self.protected.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertFalse(result['whole_prefix_prepared'])
        self.assertFalse(result['native_worker_tested'])
        return result, output.getvalue()

    def test_real_archive_preflight_extract_inventory_and_retained_unique_scratch(self):
        with patch.object(archive, '_scan', wraps=archive._scan) as scan:
            result, output = self.invoke()
        self.assertEqual(result['status'], 'passed')
        self.assertIn('WORLD WORKER ARCHIVE DIAGNOSTIC PASSED', output)
        self.assertEqual(scan.call_count, 2)
        self.assertNotIn('destination', scan.call_args_list[0].kwargs)
        scratch = Path(result['scratch'])
        self.assertTrue(scratch.name.startswith('world-worker-archive-check-'))
        self.assertEqual(scratch.parent, self.build)
        self.assertTrue((scratch / 'owner.json').is_file())
        self.assertEqual(scan.call_args_list[1].kwargs['destination'], scratch / 'payload')
        for phase in ('preflight', 'extract', 'verify'):
            row = next(item for item in result['phases'] if item['id'] == phase)
            self.assertEqual((row['status'], row['file_count'], row['bytes']), ('passed', 2, 28))

    def test_decoder_failure_report_keeps_safe_details_and_retains_partial_scratch(self):
        original = archive._scan
        def fail(pin, cache, destination=None, decoder=None):
            if destination is None:
                return original(pin, cache, decoder=decoder)
            (destination / 'partial').write_bytes(b'partial')
            error = archive.ArchiveReadError({'category': 'decoder_timeout', 'tar_reason': 'truncated_payload',
                'decoder_stage': 'parse', 'decoded_bytes': 10240, 'elapsed_ms': 300001,
                'timed_out': True, 'decoder_exit': -9, 'decoder_exit_hex': '0xFFFFFFF7',
                'forced_cleanup': False, 'cleanup_exit': -9, 'errno': None, 'winerror': None,
                'phase': 'extract', 'package': diagnostic.PACKAGE, 'member': 'mingw64/bin/aom.exe',
                'stderr': 'PRIVATE_STDERR_SENTINEL'})
            raise error
        with patch.object(archive, '_scan', side_effect=fail):
            result, output = self.invoke()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('WORLD WORKER ARCHIVE DIAGNOSTIC FAILED', output)
        row = result['phases'][-1]
        self.assertEqual((row['id'], row['error']['decoder_exit'], row['error']['timed_out']), ('extract', -9, True))
        self.assertEqual(row['error']['member'], 'mingw64/bin/aom.exe')
        self.assertTrue((Path(result['scratch']) / 'payload/partial').exists())

    def test_preflight_failure_creates_no_scratch_and_redacts_exception_text(self):
        with patch.object(archive, '_scan', side_effect=OSError(5, 'PRIVATE_READ_ERROR')):
            result, _ = self.invoke()
        self.assertEqual(result['phases'][-1]['error']['errno'], 5)
        self.assertIsNone(result['scratch'])
        self.assertEqual(list(self.build.glob('world-worker-archive-check-*')), [])

    def test_extra_output_is_not_counted_as_success(self):
        original = archive._scan
        def altered(pin, cache, destination=None, decoder=None):
            result = original(pin, cache, destination, decoder)
            if destination is not None:
                (destination / 'extra').write_bytes(b'extra')
            return result
        with patch.object(archive, '_scan', side_effect=altered):
            result, _ = self.invoke()
        self.assertEqual((result['status'], result['phases'][-1]['id']), ('failed', 'verify'))

    def test_existing_or_redirected_report_is_never_replaced(self):
        self.report.write_bytes(b'prior report')
        with self.assertRaises(diagnostic.BuildError):
            diagnostic.diagnose(self.msys, self.report)
        self.host.assert_not_called()
        self.assertEqual(self.report.read_bytes(), b'prior report')
        redirect = self.root / 'redirect.json'; redirect.symlink_to(self.report)
        with self.assertRaises(diagnostic.BuildError):
            diagnostic.diagnose(self.msys, redirect)
        self.assertEqual(self.report.read_bytes(), b'prior report')

    def test_main_cannot_publish_existing_report_and_returns_one(self):
        self.report.write_bytes(b'prior report')
        output = io.StringIO()
        with redirect_stdout(output):
            code = diagnostic.main(['--msys', str(self.msys), '--report', str(self.report)])
        self.assertEqual(code, 1)
        self.assertEqual(self.report.read_bytes(), b'prior report')
        self.assertIn('report could not be published', output.getvalue())
        self.host.assert_not_called()

    def test_error_classifications_do_not_copy_unknown_text(self):
        error = archive.ArchiveReadError({key: 'PRIVATE_TEXT' for key in diagnostic.CLASSIFICATIONS})
        error.details.update(stderr='PRIVATE_STDERR', member='../PRIVATE_PATH')
        result = diagnostic._error_details(error)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('member', result)
        error.details['decoder_stage'] = 'cleanup'
        self.assertEqual(diagnostic._error_details(error)['decoder_stage'], 'cleanup')


FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['ARCHIVE_CALLS'], 'a') as stream:
    stream.write(json.dumps({'args':args, 'cwd':os.getcwd(), 'path':os.environ['PATH']}) + '\n')
mode = os.environ.get('ARCHIVE_MODE', '')
report = pathlib.Path(args[args.index('--report') + 1])
value = {'format':1, 'purpose':'wesnoth-world-worker-archive-diagnostic', 'release':1192624,
         'scope':'one-pinned-package', 'status':'passed', 'package':{'name':'mingw-w64-x86_64-aom'},
         'whole_prefix_prepared':False, 'native_worker_tested':False,
         'phases':[{'id':name,'status':'passed'} for name in ('preflight','extract','verify')]}
if mode == 'failed': value['status'] = 'failed'
if mode == 'scope': value['scope'] = 'whole-prefix'
if mode == 'ready': value['native_worker_tested'] = True
if mode == 'phase': value['phases'].pop()
if mode == 'format': value['format'] = 2
if mode != 'missing':
    with report.open('x') as stream:
        if mode == 'malformed': stream.write('PRIVATE_JSON_SENTINEL invalid')
        elif mode == 'oversized': stream.write(' ' * 32769)
        else: json.dump(value, stream)
print('Simulated safe diagnostic stdout', flush=True)
print('Simulated safe diagnostic stderr', file=sys.stderr, flush=True)
sys.exit(1 if mode == 'failed' else 0)
'''
LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:ARCHIVE_SETTINGS -Raw | ConvertFrom-Json
function Start-Process { throw 'Forbidden process start.' }
function Stop-Process { throw 'Forbidden process stop.' }
function powershell.exe { throw 'Forbidden secondary helper.' }
function sc.exe { throw 'Forbidden service control.' }
$env:PATH = $env:ARCHIVE_BASE_PATH
$beforePath = $env:PATH
$beforeLocation = (Get-Location).Path
$arguments = @{ MsysRoot = $settings.msys }
if ($settings.explicit_python) { $arguments.PythonPath = $settings.python }
& $settings.helper @arguments
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper changed PATH.' }
if ((Get-Location).Path -cne $beforeLocation) { throw 'Helper changed working directory.' }
Write-Host 'CALLER STATE PRESERVED'
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), 'Existing Linux PowerShell required; no tools installed')
class ArchiveDiagnosticWindowsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='world archive wrapper ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / 'tools'; self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        shutil.copyfile(ROOT / 'tools' / HELPER, self.helper)
        (self.tools / 'diagnose_world_worker_archive.py').write_text('# isolated fake diagnostic\n')
        self.local = self.root / 'profile'
        self.python = self.local / 'Programs/Python/Python312/python.exe'
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON); self.python.chmod(0o755)
        self.msys = self.root / "MSYS $ & ' tree"; self.msys.mkdir()
        for relative in ('build/world-worker-prefix/receipt.json',
                'build/world-worker-prefix.archive-preparing/partial',
                'build/world-worker-prefix.archive-preparation.json',
                'build/world-worker-packages-1192624/pinned.tar.zst', 'runtime-v2/config.json', '.env', 'README.md'):
            path = self.repo / relative; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'PRIVATE_PRESERVATION_SENTINEL')
        self.protected = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in self.root.rglob('*') if path.is_file()}
        self.settings_path = self.root / 'settings.json'
        self.calls = self.root / 'calls.jsonl'
        self.settings = {'helper': str(self.helper), 'python': str(self.python),
                         'msys': str(self.msys), 'explicit_python': True}
        self.launcher = self.root / 'launcher.ps1'; self.launcher.write_text(LAUNCHER)
        self.env = {**os.environ, 'OS':'Windows_NT', 'LOCALAPPDATA':str(self.local),
                    'ARCHIVE_SETTINGS':str(self.settings_path), 'ARCHIVE_CALLS':str(self.calls),
                    'ARCHIVE_BASE_PATH': os.environ['PATH']}

    def invoke(self, mode='', success=True):
        self.settings_path.write_text(json.dumps(self.settings))
        result = subprocess.run([str(PWSH), '-NoProfile', '-NonInteractive', '-File', str(self.launcher)],
            cwd=self.root, env={**self.env, 'ARCHIVE_MODE':mode}, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual('WORLD WORKER ARCHIVE DIAGNOSTIC COMPLETE' in result.stdout, success, result.stdout)
        self.assertIn('CALLER STATE PRESERVED', result.stdout)
        self.assertNotIn('PRIVATE', result.stdout)
        logs = list((self.repo / 'diagnostics').glob('world-worker-archive-*.txt'))
        self.assertTrue(logs)
        for log in logs:
            self.assertNotIn('PRIVATE', log.read_text(encoding='utf-8-sig'))
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_explicit_python_only_one_isolated_call_with_literal_paths(self):
        result, calls = self.invoke()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['args'][:5], ['-I', '-B', str(self.tools / 'diagnose_world_worker_archive.py'), '--msys', str(self.msys)])
        self.assertEqual(calls[0]['args'][5], '--report')
        self.assertEqual(calls[0]['cwd'], str(self.root))
        self.assertEqual(calls[0]['path'], self.env['PATH'])
        self.assertIn('One package only', result.stdout)

    def test_default_python_selects_python312(self):
        self.settings['explicit_python'] = False
        _, calls = self.invoke()
        self.assertEqual(len(calls), 1)

    def test_child_failure_is_not_retried(self):
        _, calls = self.invoke(mode='failed', success=False)
        self.assertEqual(len(calls), 1)

    def test_invalid_or_overstated_reports_fail_closed(self):
        for mode in ('missing', 'malformed', 'oversized', 'scope', 'ready', 'phase', 'format'):
            with self.subTest(mode=mode):
                _, calls = self.invoke(mode=mode, success=False)
                self.assertEqual(len(calls), 1)
                self.calls.unlink()

    def test_wrong_host_stops_before_python(self):
        self.env['OS'] = 'Linux'
        _, calls = self.invoke(success=False)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
