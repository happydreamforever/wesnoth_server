"""Bounded existing-executable diagnosis; no native worker build is performed."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import inspect_world_worker_version as version
from tools import world_worker_recovery as recovery
from tools import world_worker_ninja_recovery as ninja
from tools.build_alliance_bridge import BuildError


def digest(raw): return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value) + '\n')


class VersionInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker version ')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo with spaces'
        self.stage = self.repo / 'build/windows-world-worker'
        self.binary = self.stage / 'bin'
        self.binary.mkdir(parents=True)
        (self.stage / 'engine/src').mkdir(parents=True)
        (self.stage / 'source/src').mkdir(parents=True)
        (self.repo / 'diagnostics').mkdir()
        self.prefix = self.repo / 'build/world-worker-prefix'
        self.prefix.mkdir()
        self.executable = self.binary / 'world-worker.exe'
        self.executable.write_bytes(b'MZ synthetic existing native worker bytes')
        self.linked_executable = self.stage / 'engine/world-worker.exe'
        self.linked_executable.write_bytes(self.executable.read_bytes())
        (self.binary / 'library.dll').write_bytes(b'MZ pinned private DLL fixture')
        (self.stage / 'source/src/wesconfig.h').write_text('#define VERSION "1.19.26"\n')
        dependencies = {'format': 1, 'purpose': 'wesnoth-world-worker-mingw64-prefix', 'packages': [],
                        'files': {'bin/library.dll': {'bytes': (self.binary / 'library.dll').stat().st_size,
                                                    'sha256': digest((self.binary / 'library.dll').read_bytes())}}}
        write_json(self.prefix / 'receipt.json', dependencies)
        self.owner = {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
                      'inputs': {'wesnoth_server/tools/build_world_worker.py': '1' * 64,
                                 'wesnoth_server/build/world-worker-prefix/receipt.json': digest((self.prefix / 'receipt.json').read_bytes())}}
        write_json(self.stage / 'owner.json', self.owner)
        with ninja.build_lock(self.stage): pass
        (self.repo / 'runtime-v2').mkdir()
        (self.repo / 'runtime-v2/private.json').write_bytes(b'DO NOT READ RUNTIME')
        (self.repo / '.env').write_bytes(b'DO NOT READ ENV')
        self.system = self.repo.parent / 'fake Windows'
        (self.system / 'System32').mkdir(parents=True)
        self.environment = {'SYSTEMROOT': str(self.system), 'PATH': 'UNSAFE',
                            'ALLIANCE_WORKER_TICKET': 'PRIVATE_TOKEN', 'WESNOTH_PUBLIC_PROFILE': 'PRIVATE_PROFILE'}
        self.before = recovery._inventory(self.stage)
        self.runner = Mock(side_effect=self.success)
        self.binding = Mock(return_value=deepcopy(self.owner))

    def success(self, command, env, cwd):
        self.assertEqual(command[0], self.executable)
        self.assertEqual(command[1:4], ['--simple-version', '--no-log-to-file', '--wnoconsole'])
        self.assertEqual(command[4], '--userdata-dir')
        self.assertEqual(command[6], '--usercache-dir')
        self.assertEqual(Path(command[5]), cwd / 'userdata')
        self.assertEqual(Path(command[7]), cwd / 'cache')
        self.assertEqual(cwd.parent, self.repo / 'build')
        self.assertTrue(cwd.name.startswith('world-worker-version-check-'))
        self.assertEqual(env['PATH'], str(self.binary) + os.pathsep + str(self.system / 'System32'))
        self.assertEqual(set(env), {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'})
        self.assertNotIn('PRIVATE', str(env))
        (cwd / 'userdata/generated-in-scratch').write_bytes(b'scratch only')
        return self.result()

    @staticmethod
    def result(stdout=b'1.19.26\r\n', stderr=b'', code=0, status='exited', complete=True):
        return {'status': status, 'exit_code': code, 'timed_out': status == 'timeout',
                'output_limited': status == 'output_limit', 'stdout': stdout, 'stderr': stderr,
                'capture_complete': complete}

    def collect(self):
        return version.collect(self.repo, binding_function=self.binding,
                               run_process=self.runner, environ=self.environment)

    def test_exact_version_one_run_with_isolated_paths_and_preserved_inputs(self):
        self.assertFalse((self.stage / 'engine/src/world-worker.exe').exists())
        report = self.collect()
        self.assertTrue(report['collection']['complete'], report)
        self.assertEqual(report['result']['outcome'], 'version_match')
        self.assertEqual(report['result']['stdout']['version_text'], '1.19.26')
        self.assertTrue(all(report['preservation'].values()))
        self.assertEqual(recovery._inventory(self.stage), self.before)
        self.assertFalse((self.stage / 'receipt.json').exists())
        self.assertEqual(self.runner.call_count, 1)
        self.assertEqual(self.binding.call_count, 2)
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertEqual(report['artifacts']['version_header']['declared_version'], '1.19.26')

    def test_root_output_layout_matches_the_pinned_engine_cmake_setting(self):
        engine = Path(__file__).resolve().parents[2] / 'wesnoth_client/engine/CMakeLists.txt'
        self.assertRegex(engine.read_text(),
                         r'(?m)^set\(EXECUTABLE_OUTPUT_PATH "\$\{CMAKE_BINARY_DIR\}" CACHE STRING ')

    def test_old_nested_layout_cannot_replace_the_required_root_executable(self):
        nested = self.stage / 'engine/src/world-worker.exe'
        self.linked_executable.rename(nested)
        before = recovery._inventory(self.stage)
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.assertEqual(report['result']['outcome'], 'not_run')
        self.assertEqual(report['failure']['phase'], 'artifacts')
        self.assertEqual(report['failure']['check'], 'linked_executable')
        self.assertEqual(report['failure']['type'], 'FileNotFoundError')
        self.assertEqual(report['failure']['errno'], 2)
        self.assertEqual(recovery._inventory(self.stage), before)
        self.runner.assert_not_called()

    def test_wrong_empty_nonzero_timeout_output_limit_are_complete_observations(self):
        cases = [({'stdout': b'9.8.7\n'}, 'version_mismatch'), ({'stdout': b''}, 'empty_stdout'),
                 ({'code': 17}, 'nonzero_exit'), ({'code': -9, 'status': 'timeout'}, 'timeout'),
                 ({'code': -9, 'status': 'output_limit'}, 'output_limit')]
        for kwargs, outcome in cases:
            with self.subTest(outcome=outcome):
                self.runner.side_effect = lambda *args, values=kwargs: self.result(**values)
                report = self.collect()
                self.assertTrue(report['collection']['complete'], report)
                self.assertEqual(report['result']['outcome'], outcome)
                self.assertFalse(report['result']['version_matches'])
                self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_unrecognized_streams_never_expose_private_text_or_control_sequences(self):
        self.runner.side_effect = lambda *args: self.result(stdout=b'PRIVATE_TOKEN\x1b[31m\n', stderr=b'C:\\private\\password=secret\n')
        report = self.collect()
        self.assertTrue(report['collection']['complete'])
        for name in ('stdout', 'stderr'):
            row = report['result'][name]
            self.assertIsNone(row['version_text'])
            self.assertIsNone(row['version_bytes_base64'])
            self.assertTrue(row['unrecognized_text_omitted'])
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(report))
        self.assertNotIn('password', json.dumps(report))

    def test_linked_or_extra_binary_files_prevent_execution(self):
        os.link(self.binary / 'library.dll', self.binary / 'other.dll')
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.runner.assert_not_called()
        (self.binary / 'other.dll').unlink()
        (self.binary / 'foreign.txt').write_text('foreign')
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.runner.assert_not_called()

    def test_wrong_binding_receipt_dll_or_binary_prevent_execution(self):
        changed = deepcopy(self.owner)
        changed['inputs']['wesnoth_server/tools/build_world_worker.py'] = '2' * 64
        self.binding.return_value = changed
        self.assertFalse(self.collect()['collection']['complete'])
        self.binding.return_value = deepcopy(self.owner)
        dll = self.binary / 'library.dll'
        dll.write_bytes(b'changed DLL')
        self.assertFalse(self.collect()['collection']['complete'])
        self.runner.assert_not_called()

    def test_executable_must_match_linked_output(self):
        self.linked_executable.write_bytes(b'different worker')
        # A matching nested copy must not bypass the pinned root-output check.
        (self.stage / 'engine/src/world-worker.exe').write_bytes(self.executable.read_bytes())
        before = recovery._inventory(self.stage)
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.assertEqual(report['failure']['check'], 'copied_executable_match')
        self.assertEqual(recovery._inventory(self.stage), before)
        self.runner.assert_not_called()

    def test_missing_artifact_labels_are_fixed_and_do_not_expose_paths(self):
        for path, label in ((self.linked_executable, 'linked_executable'),
                            (self.prefix / 'receipt.json', 'prefix_receipt'),
                            (self.stage / 'source/src/wesconfig.h', 'version_header')):
            with self.subTest(check=label):
                retained = path.with_name('private-retained-artifact')
                path.rename(retained)
                before = recovery._inventory(self.stage)
                try:
                    report = self.collect()
                    self.assertFalse(report['collection']['complete'])
                    failure = report['failure']
                    self.assertEqual(failure['phase'], 'artifacts')
                    self.assertEqual(failure['check'], label)
                    self.assertEqual(set(failure), {'phase', 'check', 'type', 'errno', 'winerror'})
                    self.assertNotIn(str(self.repo), json.dumps(failure))
                    self.assertNotIn('private-retained-artifact', json.dumps(failure))
                    self.assertEqual(recovery._inventory(self.stage), before)
                    self.runner.assert_not_called()
                finally:
                    retained.rename(path)

    def test_linked_root_executable_is_rechecked_after_the_invocation(self):
        def remove_linked(*args):
            self.linked_executable.unlink()
            return self.result()
        self.runner.side_effect = remove_linked
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.assertEqual(report['result']['outcome'], 'version_match')
        self.assertEqual(report['failure']['phase'], 'preservation')
        self.assertEqual(report['failure']['check'], 'linked_executable')
        self.assertEqual(report['failure']['type'], 'FileNotFoundError')
        self.assertFalse(self.linked_executable.exists())

    def test_existing_completed_receipt_is_not_modified_or_reused(self):
        (self.stage / 'receipt.json').write_bytes(b'original receipt')
        self.assertFalse(self.collect()['collection']['complete'])
        self.assertEqual((self.stage / 'receipt.json').read_bytes(), b'original receipt')
        self.runner.assert_not_called()

    def test_missing_lock_is_not_created_and_competing_build_prevents_run(self):
        lock = self.stage.with_name(self.stage.name + '.build.lock')
        lock_raw = lock.read_bytes()
        lock.unlink()
        self.assertFalse(self.collect()['collection']['complete'])
        self.assertFalse(lock.exists())
        lock.write_bytes(lock_raw)
        with ninja.build_lock(self.stage):
            self.assertFalse(self.collect()['collection']['complete'])
        self.runner.assert_not_called()

    def test_changed_artifacts_or_sources_make_collection_incomplete(self):
        def change_binary(*args):
            self.executable.write_bytes(b'changed while running')
            return self.result()
        self.runner.side_effect = change_binary
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.assertFalse(report['preservation']['bin_unchanged'])
        self.assertEqual(self.executable.read_bytes(), b'changed while running')

    def test_capture_cleanup_failure_is_not_complete(self):
        self.runner.side_effect = lambda *args: self.result(complete=False)
        report = self.collect()
        self.assertFalse(report['collection']['complete'])
        self.assertTrue(all(report['preservation'].values()))

    def test_environment_alias_missing_root_and_redirected_ancestor_refused(self):
        self.environment['SystemRoot'] = self.environment['SYSTEMROOT']
        self.assertFalse(self.collect()['collection']['complete'])
        self.environment.pop('SystemRoot')
        self.environment.pop('SYSTEMROOT')
        self.assertFalse(self.collect()['collection']['complete'])
        self.runner.assert_not_called()
        redirected = self.repo.parent / 'redirected'
        redirected.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(BuildError): version.collect(redirected)

    def test_report_is_exclusive_and_only_in_diagnostics(self):
        report = self.collect()
        path = self.repo / 'diagnostics/version.json'
        version.write_report(self.repo, path, report)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError): version.write_report(self.repo, path, report)
        with self.assertRaises(BuildError): version.write_report(self.repo, self.repo / 'owner.json', report)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_main_prints_only_classified_outcome_and_writes_report(self):
        report = self.collect()
        destination = self.repo / 'diagnostics/main.json'
        output = io.StringIO()
        with patch.object(version, 'ROOT', self.repo), patch.object(version.sys, 'platform', 'win32'), \
                patch.object(version.sys, 'version_info', (3, 12, 10)), patch.object(version, 'collect', return_value=report), \
                patch.object(version.sys, 'argv', ['diagnostic', '--report', str(destination)]), redirect_stdout(output):
            self.assertEqual(version.main(), 0)
            self.assertEqual(version.main(), 1)
        self.assertIn('WORLD WORKER VERSION STATE COLLECTED', output.getvalue())
        self.assertIn('Captured version: 1.19.26', output.getvalue())
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_main_prints_fixed_failure_check_without_private_exception_details(self):
        self.linked_executable.unlink()
        report = self.collect()
        destination = self.repo / 'diagnostics/incomplete.json'
        output = io.StringIO()
        with patch.object(version, 'ROOT', self.repo), patch.object(version.sys, 'platform', 'win32'), \
                patch.object(version.sys, 'version_info', (3, 12, 10)), patch.object(version, 'collect', return_value=report), \
                patch.object(version.sys, 'argv', ['diagnostic', '--report', str(destination)]), redirect_stdout(output):
            self.assertEqual(version.main(), 1)
        self.assertIn('WORLD WORKER VERSION STATE COLLECTION INCOMPLETE', output.getvalue())
        self.assertIn('failure_phase=artifacts; check=linked_executable; error_type=FileNotFoundError; errno=2; winerror=None', output.getvalue())
        self.assertNotIn(str(self.linked_executable), output.getvalue())
        self.assertNotIn('No such file or directory', output.getvalue())
        self.assertNotIn('PRIVATE', output.getvalue())
        self.runner.assert_not_called()


class BoundedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)

    def run_child(self, script, **kwargs):
        return version.run_bounded([sys.executable, '-I', '-B', '-c', script],
                                   dict(os.environ), self.cwd, **kwargs)

    def test_real_subprocess_captures_both_streams_and_closed_stdin(self):
        row = self.run_child("import sys; assert sys.stdin.read() == ''; print('1.19.26'); print('warning',file=sys.stderr)")
        self.assertEqual(row['stdout'], b'1.19.26\n')
        self.assertEqual(row['stderr'], b'warning\n')
        self.assertTrue(row['capture_complete'])
        self.assertEqual(row['exit_code'], 0)

    def test_real_subprocess_timeout_stops_child_and_finishes_capture(self):
        row = self.run_child('import time; time.sleep(30)', timeout=0.1)
        self.assertEqual(row['status'], 'timeout')
        self.assertTrue(row['capture_complete'])
        self.assertIsNotNone(row['exit_code'])
        self.assertLess(row['elapsed_seconds'], 6)

    def test_real_output_flood_is_bounded_and_other_stream_remains_exact(self):
        row = self.run_child("import sys; print('1.19.26',flush=True); sys.stderr.write('x'*1000000); sys.stderr.flush()", max_bytes=1024)
        self.assertTrue(row['output_limited'])
        self.assertLessEqual(len(row['stderr']), 1024)
        self.assertEqual(row['stdout'], b'1.19.26\n')
        self.assertFalse(row['stdout_limited'])
        self.assertTrue(row['stderr_limited'])
        self.assertTrue(row['capture_complete'])

    def test_launch_error_is_captured_without_exception_message(self):
        row = version.run_bounded([self.cwd / 'missing-private-token.exe'], dict(os.environ), self.cwd)
        self.assertEqual(row['status'], 'launch_error')
        self.assertTrue(row['capture_complete'])
        self.assertNotIn('private-token', json.dumps({k: v for k, v in row.items() if k not in ('stdout', 'stderr')}))


if __name__ == '__main__': unittest.main()
