"""Reviewed finalization with real retained files and controlled report provenance."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import world_worker_version_completion as completion
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_ninja_recovery as ninja
from tools.build_alliance_bridge import BuildError
from tests import test_world_worker_account_recovery as account_tests

dump = account_tests.dump


class VersionCompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = account_tests.AccountSourceRecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.resume()
        self.stage, self.root = self.fixture.stage, self.fixture.root
        self.owner = deepcopy(self.fixture.expected)
        self.owner['inputs'][recovery.BUILDER_INPUT] = next(x for x in completion.LEGACY_BUILDERS if x.startswith('03c'))
        for index in range(1707 - len(self.owner['inputs'])):
            self.owner['inputs']['wesnoth_client/engine/fixture-%d.cpp' % index] = 'a' * 64
        dump(self.stage / 'owner.json', self.owner)
        self.expected = deepcopy(self.owner)
        self.expected['inputs'][recovery.BUILDER_INPUT] = '8' * 64
        self.expected['inputs'][completion.INPUT] = '9' * 64
        self.binary = self.stage / 'bin'
        self.binary.mkdir()
        self.executable = self.binary / 'world-worker.exe'
        self.executable.write_bytes(b'MZ completed native worker')
        self.linked = self.stage / 'engine/world-worker.exe'
        self.linked.write_bytes(self.executable.read_bytes())
        for index in range(53):
            (self.binary / ('library%d.dll' % index)).write_bytes(('MZ private DLL %d' % index).encode())
        (self.stage / 'source/src').mkdir()
        (self.stage / 'source/src/wesconfig.h').write_bytes(b'#define VERSION "1.19.26"\n')
        prefix = self.root / 'world-worker-prefix'
        prefix.mkdir()
        dump(prefix / 'receipt.json', {'retained': 'synthetic pinned prefix'})
        artifacts = {'owner': completion._file(self.stage / 'owner.json'),
                     'bin': {p.name: completion._file(p) for p in self.binary.iterdir()},
                     'linked_executable': completion._file(self.linked),
                     'version_header': {'declared_version': completion.VERSION,
                                        'file': completion._file(self.stage / 'source/src/wesconfig.h')},
                     'prefix_receipt': completion._file(prefix / 'receipt.json'),
                     'binding_sha256': recovery._hash(self.owner)}
        self.report = {'format': 1, 'purpose': 'wesnoth-world-worker-version-diagnostic',
                       'release': 1192624, 'scope': 'existing-worker-version-only',
                       'collection': {'complete': True}, 'binding_input_count': 1707,
                       'build_performed': False, 'receipt_written': False, 'artifacts': artifacts,
                       'result': {'outcome': 'version_match', 'version_matches': True, 'exit_code': 0,
                                  'stdout': {'version_text': completion.VERSION}},
                       'preservation': {name: True for name in (
                           'bin_unchanged', 'dependency_receipt_unchanged', 'linked_executable_unchanged',
                           'no_receipt_created', 'owner_unchanged', 'source_binding_unchanged', 'version_header_unchanged')}}
        self.report_path = self.root / 'accepted-version.json'
        dump(self.report_path, self.report)
        for name, value in (('REVIEWED_REPORT_SHA256', hashlib.sha256(self.report_path.read_bytes()).hexdigest()),
                            ('REVIEWED_BINDING_SHA256', recovery._hash(self.owner))):
            p = patch.object(completion, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.receipt = {'binding': self.expected, 'version': completion.VERSION,
                        'executable': {key: artifacts['bin']['world-worker.exe'][key] for key in ('bytes', 'sha256')},
                        'dlls': {'private': {name.casefold(): {'filename': name, **{key: row[key] for key in ('bytes', 'sha256')}}
                                             for name, row in artifacts['bin'].items() if name != 'world-worker.exe'},
                                 'windows_system': ['kernel32.dll']},
                        'game_data': str(self.root / 'game-data'),
                        'game_data_files': {'data/_main.cfg': {'bytes': 4, 'sha256': 'b' * 64}},
                        'build_tools': {name: {'path': str(self.root / (name + '.exe')), 'sha256': 'c' * 64,
                                              'version': value} for name, value in (('cmake', 'cmake version 4.3.0'), ('ninja', '1.13.2'))}}
        self.validate = Mock(return_value=self.receipt)
        self.initial = recovery._inventory(self.stage)
        self.history = completion._history(self.stage)
        _, self.journal, self.complete, self.lock = completion._paths(self.stage)

    def finish(self, report=True):
        with ninja.build_lock(self.stage):
            return completion.finalize_reviewed(self.stage, self.expected,
                self.report_path if report else None, self.validate)

    def unchanged(self):
        actual = recovery._inventory(self.stage)
        for name in ('owner.json', 'receipt.json'): actual['files'].pop(name, None)
        expected = deepcopy(self.initial)
        expected['files'].pop('owner.json')
        self.assertEqual(actual, expected)
        self.assertEqual(completion._history(self.stage), self.history)

    def test_finalize_preserves_all_native_files_and_history_and_retains_evidence(self):
        self.assertEqual(self.finish(), self.receipt)
        self.unchanged()
        self.validate.assert_called_once()
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertEqual(recovery._read_json(self.stage / 'receipt.json'), self.receipt)
        record = recovery._read_json(self.journal)
        self.assertEqual(record['inventory'], self.initial)
        self.assertEqual(bytes.fromhex(record['report_hex']), self.report_path.read_bytes())
        self.assertEqual(json.loads(bytes.fromhex(record['original_owner_hex'])), self.owner)
        self.assertFalse(completion.pending(self.stage))
        self.assertFalse(list(self.root.glob('windows-world-worker-before-*')))
        before = recovery._inventory(self.stage)
        self.validate.reset_mock()
        self.assertEqual(self.finish(False), self.receipt)
        self.assertEqual(recovery._inventory(self.stage), before)
        self.validate.assert_not_called()

    def test_report_required_and_only_exact_reviewed_bytes_allowed(self):
        with self.assertRaises(BuildError): self.finish(False)
        self.report_path.write_bytes(self.report_path.read_bytes() + b' ')
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.validate.assert_not_called()

    def test_only_builder_and_added_completion_source_may_differ(self):
        completion._legacy(self.owner, self.expected)
        for name in (account_tests.account.INPUT, ninja.INPUT, resource.RESOURCE_INPUT,
                     recovery.RECOVERY_INPUT, account_tests.account.ACCOUNT_INPUT,
                     'wesnoth_server/build/world-worker-prefix/receipt.json'):
            changed = deepcopy(self.expected)
            changed['inputs'][name] = '0' * 64
            with self.assertRaises(BuildError): completion._legacy(self.owner, changed)
        changed = deepcopy(self.expected)
        changed['inputs'].pop(completion.INPUT)
        with self.assertRaises(BuildError): completion._legacy(self.owner, changed)
        changed = deepcopy(self.owner)
        changed['inputs'][recovery.BUILDER_INPUT] = '1' * 64
        with self.assertRaises(BuildError): completion._legacy(changed, self.expected)

    def test_changed_report_artifacts_refused_before_any_publication(self):
        for path in (self.executable, self.linked, self.binary / 'library0.dll',
                     self.stage / 'source/src/wesconfig.h', self.root / 'world-worker-prefix/receipt.json'):
            with self.subTest(path=path.name):
                original, info = path.read_bytes(), path.stat()
                path.write_bytes(original + b'changed')
                with self.assertRaises(BuildError): self.finish()
                self.assertFalse(self.journal.exists())
                self.validate.assert_not_called()
                path.write_bytes(original)
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))

    def test_changed_owner_or_unexpected_binary_refused(self):
        extra = self.binary / 'unexpected.dll'
        extra.write_bytes(b'foreign')
        with self.assertRaises(BuildError): self.finish()
        extra.unlink()
        with (self.stage / 'owner.json').open('ab') as stream: stream.write(b' ')
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())

    def test_completed_stage_or_pending_earlier_recovery_refused(self):
        receipt = self.stage / 'receipt.json'
        receipt.write_bytes(b'foreign receipt')
        with self.assertRaises(BuildError): self.finish()
        self.assertEqual(receipt.read_bytes(), b'foreign receipt')
        receipt.unlink()
        self.fixture.complete.unlink()
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())

    def test_interruption_before_owner_replacement_resumes_without_report(self):
        with patch.object(resource, '_replace_owner', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        self.assertTrue(completion.pending(self.stage))
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertEqual(self.finish(False), self.receipt)
        self.unchanged()

    def test_interruption_after_owner_before_receipt_resumes(self):
        with patch.object(completion, '_publish_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertFalse((self.stage / 'receipt.json').exists())
        self.assertTrue(completion.pending(self.stage))
        self.assertEqual(self.finish(False), self.receipt)
        self.unchanged()

    def test_interruption_after_receipt_before_completion_resumes(self):
        publish = recovery._publish
        def stop(path, value):
            if path == self.complete: raise KeyboardInterrupt
            return publish(path, value)
        with patch.object(recovery, '_publish', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        before_receipt = completion._file(self.stage / 'receipt.json')
        self.assertTrue(completion.pending(self.stage))
        self.assertEqual(self.finish(False), self.receipt)
        self.assertEqual(completion._file(self.stage / 'receipt.json'), before_receipt)
        self.unchanged()

    def test_interrupted_external_receipt_staging_does_not_pollute_stage(self):
        with patch.object(completion, '_publish_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        with patch.object(recovery.packages, 'publish_artifact', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish(False)
        self.assertTrue(list(self.root.glob('.windows-world-worker.version-receipt-pending-*')))
        self.assertFalse((self.stage / 'receipt.json').exists())
        self.assertEqual(self.finish(False), self.receipt)
        self.unchanged()

    def test_pending_changed_object_history_or_receipt_is_preserved_and_rejected(self):
        with patch.object(completion, '_publish_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        extra = self.fixture.extra
        raw, info = extra.read_bytes(), extra.stat()
        extra.write_bytes(b'changed compiled object')
        with self.assertRaises(BuildError): self.finish(False)
        self.assertEqual(extra.read_bytes(), b'changed compiled object')
        extra.write_bytes(raw)
        os.utime(extra, ns=(info.st_atime_ns, info.st_mtime_ns))
        prior = self.fixture.complete
        prior.write_bytes(prior.read_bytes() + b' ')
        with self.assertRaises(BuildError): self.finish(False)
        self.assertFalse(self.complete.exists())
        (self.stage / 'receipt.json').write_bytes(b'partial or foreign receipt')
        with self.assertRaises(BuildError): self.finish(False)
        self.assertEqual((self.stage / 'receipt.json').read_bytes(), b'partial or foreign receipt')

    def test_validation_failure_and_mutation_do_not_update_owner(self):
        self.validate.side_effect = BuildError('version differs')
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        def mutate():
            self.fixture.extra.write_bytes(b'changed by forbidden callback')
            return self.receipt
        self.validate.side_effect = mutate
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.owner)

    def test_wrong_callback_receipt_and_resume_validation_are_rejected(self):
        wrong = deepcopy(self.receipt)
        wrong['version'] = '1.19.25'
        self.validate.return_value = wrong
        with self.assertRaises(BuildError): self.finish()
        self.validate.return_value = self.receipt
        with patch.object(completion, '_publish_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        wrong = deepcopy(self.receipt)
        wrong['game_data_files']['data/_main.cfg']['sha256'] = 'f' * 64
        self.validate.return_value = wrong
        with self.assertRaises(BuildError): self.finish(False)
        self.assertFalse(self.complete.exists())

    def test_resume_rejects_equal_binary_replacement_during_validation(self):
        with patch.object(completion, '_publish_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.finish()
        path = self.binary / 'library0.dll'
        before = completion._file(path)
        def replace():
            alternate = self.root / 'same-bytes-different-file.dll'
            alternate.write_bytes(path.read_bytes())
            alternate.chmod(path.stat().st_mode)
            os.utime(alternate, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
            os.replace(alternate, path)
            return self.receipt
        self.validate.side_effect = replace
        with self.assertRaises(BuildError): self.finish(False)
        after = completion._file(path)
        self.assertEqual({key: after[key] for key in ('bytes', 'sha256', 'mode', 'mtime_ns')},
                         {key: before[key] for key in ('bytes', 'sha256', 'mode', 'mtime_ns')})
        self.assertNotEqual(after['file_id'], before['file_id'])
        self.assertFalse(self.complete.exists())
        self.assertFalse((self.stage / 'receipt.json').exists())

    def test_hardlinks_and_competing_completion_lock_rejected(self):
        with resource._lock(self.lock):
            with self.assertRaises(BuildError): self.finish()
        os.link(self.executable, self.root / 'linked-worker.exe')
        with self.assertRaises(BuildError): self.finish()
        self.assertFalse(self.journal.exists())

    def test_historical_complete_journal_allows_absent_stage_but_tampering_fails(self):
        self.assertFalse(completion.pending(self.root / 'never-built'))
        self.finish()
        self.stage.rename(self.root / 'retained-completed-stage')
        self.assertFalse(completion.pending(self.stage))
        dump(self.complete, {'foreign': True})
        with self.assertRaises(BuildError): completion.pending(self.stage)


class VersionProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker version probe ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / 'bin'
        self.binary.mkdir()
        self.executable = self.binary / 'world-worker.exe'
        self.executable.write_bytes(b'MZ private executable')
        self.system = self.root / 'Windows'
        (self.system / 'System32').mkdir(parents=True)
        self.environment = {'SYSTEMROOT': str(self.system), 'PATH': 'unsafe',
                            'WESNOTH_PUBLIC_PROFILE': 'PRIVATE', 'ALLIANCE_WORKER_TICKET': 'PRIVATE'}

    def test_probe_uses_exact_flags_clean_environment_and_retained_isolated_directories(self):
        before = completion._file(self.executable)
        def capture(command, env, cwd):
            self.assertEqual(command[:4], [self.executable, '--simple-version', '--no-log-to-file', '--wnoconsole'])
            self.assertEqual(command[4:], ['--userdata-dir', cwd / 'userdata', '--usercache-dir', cwd / 'cache'])
            self.assertEqual(set(env), {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'})
            self.assertNotIn('PRIVATE', str(env))
            self.assertEqual(env['PATH'], str(self.binary) + os.pathsep + str(self.system / 'System32'))
            self.assertEqual(cwd.parent, self.root)
            self.assertTrue((cwd / 'userdata').is_dir())
            self.assertTrue((cwd / 'cache').is_dir())
            return b'1.19.26\r\n'
        with patch.object(completion, '_capture', side_effect=capture) as run:
            self.assertEqual(completion.probe_version(self.executable, self.environment, self.root), '1.19.26')
            run.assert_called_once()
        self.assertEqual(completion._file(self.executable), before)

    def test_wrong_empty_or_private_output_never_matches_or_leaks(self):
        for raw in (b'', b'1.19.25', b'prefix 1.19.26 suffix', b'PRIVATE_TOKEN=secret\n'):
            with self.subTest(raw=raw), patch.object(completion, '_capture', return_value=raw):
                with self.assertRaises(BuildError) as result:
                    completion.probe_version(self.executable, self.environment, self.root)
                self.assertNotIn('PRIVATE_TOKEN', str(result.exception))

    def test_duplicate_or_missing_systemroot_stops_before_execution(self):
        for env in ({'SYSTEMROOT': str(self.system), 'SystemRoot': str(self.system)}, {}, {'SYSTEMROOT': ''}):
            with self.subTest(env=env), patch.object(completion, '_capture') as run:
                with self.assertRaises(BuildError): completion.probe_version(self.executable, env, self.root)
                run.assert_not_called()

    def test_actual_subprocess_captures_version_and_closed_stdin(self):
        raw = completion._capture([sys.executable, '-I', '-B', '-c',
            "import sys; assert sys.stdin.read()==''; print('1.19.26'); print('ignored diagnostic',file=sys.stderr)"], dict(os.environ), self.root)
        self.assertEqual(raw, b'1.19.26\n')

    def test_actual_subprocess_nonzero_timeout_and_output_flood_are_rejected(self):
        cases = [("import sys; print('1.19.26'); sys.exit(7)", {}),
                 ('import time; time.sleep(20)', {'timeout': 0.1}),
                 ("import sys; sys.stdout.write('x'*1000000)", {'limit': 1024})]
        for script, kwargs in cases:
            with self.subTest(script=script):
                with self.assertRaises(BuildError):
                    completion._capture([sys.executable, '-I', '-B', '-c', script], dict(os.environ), self.root, **kwargs)

    def test_actual_launch_failure_is_sanitized(self):
        with self.assertRaises(BuildError) as result:
            completion._capture([self.root / 'PRIVATE_TOKEN.exe'], dict(os.environ), self.root)
        self.assertNotIn('PRIVATE_TOKEN', str(result.exception))


if __name__ == '__main__': unittest.main()
