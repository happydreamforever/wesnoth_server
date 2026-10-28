"""Real filesystem recovery with synthetic, explicitly bound diagnostic provenance."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import world_worker_ninja_recovery as ninja
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import inspect_world_worker_ninja as inspection
from tools.build_alliance_bridge import BuildError


def dump(path, value):
    path.write_bytes((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


def digest(data):
    return hashlib.sha256(data).hexdigest()


class NinjaRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'windows-world-worker'
        self.stage.mkdir()
        self.engine = self.stage / 'engine'
        self.engine.mkdir()
        self.expected = {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
                         'inputs': {**ninja.REVIEWED_SOURCES, ninja.INPUT: 'a' * 64,
                                    'wesnoth_client/engine/CMakeLists.txt': 'b' * 64,
                                    'wesnoth_server/build/world-worker-prefix/receipt.json': 'c' * 64}}
        self.expected['inputs'][recovery.BUILDER_INPUT] = 'd' * 64
        self.owner = deepcopy(self.expected)
        self.owner['inputs'].pop(ninja.INPUT)
        self.owner['inputs'][recovery.BUILDER_INPUT] = ninja.REVIEWED_BUILDER
        before_resource = deepcopy(self.owner)
        before_resource['inputs'].pop(resource.RESOURCE_INPUT)
        pair = next(pair for pair in resource.LEGACY_PAIRS if pair[0].startswith('766'))
        before_resource['inputs'][recovery.BUILDER_INPUT], before_resource['inputs'][recovery.RECOVERY_INPUT] = pair
        dump(self.stage / 'owner.json', before_resource)
        (self.stage / 'source').mkdir()
        (self.stage / 'source/CMakeLists.txt').write_text('unchanged native source')
        (self.stage / 'worker-toolchain.cmake').write_text('unchanged toolchain')
        self.paths = ['src/unit%d.obj' % i for i in range(571)] + ['src/library%d.a' % i for i in range(4)]
        (self.engine / 'src').mkdir()
        for index, name in enumerate(self.paths):
            path = self.engine / name
            path.write_bytes(('native output ' + name).encode())
            os.utime(path, ns=(1700000000000000000 + index, 1700000000000000000 + index))
        self.log = b'# ninja log v7\n' + ''.join('1\t2\t3\t%s\t123abc\n' % name for name in self.paths).encode()
        (self.engine / '.ninja_log').write_bytes(self.log)
        (self.engine / '.ninja_deps').write_bytes(b'# ninjadeps\n' + bytes(range(256)) * 100)
        (self.engine / 'build.ninja').write_bytes(b'old generated build graph')
        original_inventory = recovery._inventory(self.stage)
        self.original_log_row = original_inventory['files']['engine/.ninja_log']
        self.resource_journal = self.stage.with_name(self.stage.name + '.resource-recovery.json')
        prior = {'format': 1, 'purpose': resource.PURPOSE, 'stage': str(self.stage),
                 'original_owner': before_resource, 'original_owner_hex': (self.stage / 'owner.json').read_bytes().hex(),
                 'expected_binding': self.owner, 'inventory': original_inventory}
        dump(self.resource_journal, prior)
        dump(self.stage.with_name(self.stage.name + '.resource-recovery-complete.json'), resource._completion(prior))
        dump(self.stage / 'owner.json', self.owner)
        (self.engine / '.ninja_log').unlink()
        (self.engine / '.ninja_log.restat').write_bytes(self.log)
        (self.engine / 'build.ninja').write_bytes(b'partially regenerated build graph')
        self.report = {'format': 1, 'purpose': inspection.PURPOSE, 'collection': {'complete': True},
                       'files': {}, 'checks': {}}
        for name in (*ninja.NAMES, *ninja.VARIANTS, 'build.ninja'):
            self.report['files'][name] = inspection.inspect_file(self.engine / name,
                include_raw=name == '.ninja_log.restat', access_probe=lambda *a, **kw: {'status': 'observed'})
        self.report['checks']['ownership'] = inspection.inspect_file(self.stage / 'owner.json', access_probe=lambda *a, **kw: {'status': 'observed'})
        self.report['checks']['resource_journal'] = inspection.inspect_file(self.resource_journal, access_probe=lambda *a, **kw: {'status': 'observed'})
        self.report['checks']['resource_journal']['files'] = {'.ninja_log': {**self.original_log_row, 'status': 'recorded'}}
        self.report_path = self.root / 'reviewed.json'
        dump(self.report_path, self.report)
        for name, value in (('REVIEWED_REPORT_SHA256', digest(self.report_path.read_bytes())),
                            ('REVIEWED_LOG_SHA256', digest(self.log)), ('REVIEWED_LOG_BYTES', len(self.log))):
            p = patch.object(ninja, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.validate = Mock()
        self.initial = recovery._inventory(self.stage)
        self.journal = self.stage.with_name(self.stage.name + '.ninja-recovery.json')
        self.complete = self.stage.with_name(self.stage.name + '.ninja-recovery-complete.json')

    def recover(self, report=True):
        with ninja.build_lock(self.stage):
            return ninja.recover_reviewed(self.stage, self.expected,
                                          self.report_path if report else None, self.validate)

    def assert_preserved(self):
        actual = recovery._inventory(self.stage)
        expected = deepcopy(self.initial)
        actual['files'].pop('owner.json')
        actual['files'].pop('engine/.ninja_log', None)
        expected['files'].pop('owner.json')
        self.assertEqual(actual, expected)

    def test_reviewed_history_is_restored_and_objects_retained(self):
        prior = self.resource_journal.read_bytes()
        self.assertTrue(self.recover())
        self.assert_preserved()
        self.assertEqual(ninja._row(self.engine / '.ninja_log'), self.original_log_row)
        self.assertEqual(self.resource_journal.read_bytes(), prior)
        self.assertEqual((self.engine / '.ninja_log.restat').read_bytes(), self.log)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        journal = recovery._read_json(self.journal)
        self.assertEqual(journal['inventory'], self.initial)
        self.assertEqual(bytes.fromhex(journal['report_hex']), self.report_path.read_bytes())
        self.assertFalse(ninja.pending(self.stage))
        self.assertFalse((self.stage / 'receipt.json').exists())

    def test_completed_recovery_accepts_later_compilation(self):
        self.recover()
        (self.engine / self.paths[0]).write_bytes(b'legitimate later native output')
        (self.engine / '.ninja_log').write_bytes(b'later normal Ninja history')
        (self.stage / 'receipt.json').write_bytes(b'completed native worker')
        before = recovery._inventory(self.stage)
        self.validate.reset_mock()
        self.assertTrue(self.recover(False))
        self.assertEqual(recovery._inventory(self.stage), before)
        self.validate.assert_not_called()
        retained = self.stage.with_name('retained')
        self.stage.rename(retained)
        self.assertFalse(ninja.pending(self.stage))

    def test_missing_or_altered_report_cannot_start_repair(self):
        with self.assertRaises(BuildError): self.recover(False)
        self.report_path.write_bytes(self.report_path.read_bytes() + b' ')
        with self.assertRaises(BuildError): self.recover()
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertFalse(self.journal.exists())

    def test_changed_log_deps_output_and_file_identity_rejected(self):
        for path in (self.engine / '.ninja_log.restat', self.engine / '.ninja_deps', self.engine / self.paths[0]):
            before = path.read_bytes()
            stamp = path.stat().st_mtime_ns
            path.write_bytes(before + b'changed')
            with self.assertRaises(BuildError): self.recover()
            path.write_bytes(before)
            os.utime(path, ns=(stamp, stamp))
        path = self.engine / '.ninja_log.restat'
        original = path.with_name('held-original')
        path.rename(original)
        path.write_bytes(original.read_bytes())
        os.utime(path, ns=(original.stat().st_mtime_ns, original.stat().st_mtime_ns))
        with self.assertRaises(BuildError): self.recover()
        self.assertFalse(self.journal.exists())

    def test_foreign_source_or_completed_stage_rejected(self):
        for name in (recovery.BUILDER_INPUT, recovery.RECOVERY_INPUT, resource.RESOURCE_INPUT,
                     'wesnoth_client/engine/CMakeLists.txt'):
            owner = deepcopy(self.owner)
            owner['inputs'][name] = 'f' * 64
            with self.assertRaises(BuildError): ninja._legacy(owner, self.expected)
        (self.stage / 'receipt.json').write_bytes(b'complete')
        with self.assertRaises(BuildError): self.recover()
        self.assertFalse(self.journal.exists())

    def test_expected_binding_must_include_new_helper_and_all_other_inputs(self):
        for name in (ninja.INPUT, 'wesnoth_server/build/world-worker-prefix/receipt.json'):
            changed = deepcopy(self.expected)
            changed['inputs'].pop(name)
            with self.assertRaises(BuildError): ninja._legacy(self.owner, changed)
        changed = deepcopy(self.expected)
        changed['inputs']['wesnoth_client/engine/CMakeLists.txt'] = 'e' * 64
        with self.assertRaises(BuildError): ninja._legacy(self.owner, changed)

    def test_pending_recovery_rejects_changed_original_resource_journal(self):
        with patch.object(ninja, '_copy', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.recover()
        self.resource_journal.write_bytes(self.resource_journal.read_bytes() + b' ')
        with self.assertRaises(BuildError): self.recover(False)
        self.assertFalse((self.engine / '.ninja_log').exists())

    def test_log_output_syntax_duplicates_and_non_object_outputs_rejected(self):
        self.assertEqual(len(ninja._log_outputs(self.log)), 575)
        for raw in (self.log.replace(b'v7', b'v6'), self.log.replace(b'src/unit0.obj', b'../unit0.obj'),
                    self.log.replace(b'src/unit0.obj', b'src/unit1.obj'),
                    self.log.replace(b'src/unit0.obj', b'build.ninja')):
            with self.assertRaises(BuildError): ninja._log_outputs(raw)

    def test_interrupted_copy_and_owner_publication_resume(self):
        real_copy = ninja._copy
        def partial(source, destination, row, **kw):
            if destination == self.engine / '.ninja_log':
                destination.write_bytes(self.log[:100])
                raise KeyboardInterrupt
            return real_copy(source, destination, row, **kw)
        with patch.object(ninja, '_copy', side_effect=partial):
            with self.assertRaises(KeyboardInterrupt): self.recover()
        self.assertTrue(ninja.pending(self.stage))
        self.assert_preserved()
        self.assertTrue(self.recover(False))
        self.assertEqual(ninja._row(self.engine / '.ninja_log'), self.original_log_row)

    def test_interrupt_after_owner_resumes_without_rewriting_objects(self):
        publish = recovery._publish
        def interrupted(path, value):
            if path == self.complete: raise KeyboardInterrupt
            return publish(path, value)
        with patch.object(recovery, '_publish', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.recover()
        self.assertTrue(ninja.pending(self.stage))
        self.assert_preserved()
        self.assertTrue(self.recover(False))
        self.assert_preserved()

    def test_pending_recovery_rejects_changed_partial_or_other_files(self):
        with patch.object(ninja, '_copy', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.recover()
        (self.engine / '.ninja_log').write_bytes(b'foreign prefix')
        with self.assertRaises(BuildError): self.recover(False)
        (self.engine / '.ninja_log').unlink()
        (self.engine / self.paths[2]).write_bytes(b'changed output')
        with self.assertRaises(BuildError): self.recover(False)
        self.assertFalse(self.complete.exists())

    def test_changed_validation_input_and_journal_fail_closed(self):
        self.validate.side_effect = lambda: (self.stage / 'source/CMakeLists.txt').write_bytes(b'changed')
        with self.assertRaises(BuildError): self.recover()
        self.assertFalse(self.journal.exists())

    def test_links_and_lock_conflict_rejected(self):
        with ninja.build_lock(self.stage):
            with self.assertRaises(BuildError):
                with ninja.build_lock(self.stage): pass
        source = self.engine / self.paths[0]
        os.link(source, self.engine / 'extra-hardlink')
        with self.assertRaises(BuildError): self.recover()


class ConfigureGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'windows-world-worker'
        self.stage.mkdir()
        self.engine = self.stage / 'engine'
        self.engine.mkdir()
        (self.stage / 'owner.json').write_bytes(b'{"owned":"fixture"}\n')
        (self.engine / '.ninja_log').write_bytes(b'# ninja log v7\n1\t2\t3\tunit.obj\t1234\n')
        (self.engine / '.ninja_deps').write_bytes(b'# ninjadeps\n' + bytes(range(256)) * 8)
        (self.engine / '.ninja_log.restat').write_bytes(b'original retained diagnostic')
        (self.engine / 'unit.obj').write_bytes(b'unchanged compiled object')
        for path in self.engine.iterdir(): os.utime(path, ns=(1700000000000000000, 1700000000000000000))
        self.before = recovery._inventory(self.stage)
        self.command = ['cmake', '-S', 'source', '-B', str(self.engine)]
        self.environment = {'fixture': 'value'}

    def configure(self, run):
        with ninja.build_lock(self.stage):
            return ninja.configure(self.stage, self.command, self.environment, run)

    def generated(self, command, environment):
        self.assertEqual(command[-1], '-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON')
        self.assertEqual(environment, self.environment)
        self.assertFalse((self.engine / '.ninja_log').exists())
        self.assertFalse((self.engine / '.ninja_deps').exists())
        self.assertTrue((self.engine / '.ninja_log.restat').exists())
        return 123

    def test_guarded_configuration_preserves_history_and_original_temporary(self):
        self.assertEqual(self.configure(self.generated), 123)
        self.assertEqual(recovery._inventory(self.stage), self.before)
        self.assertFalse(ninja.configure_pending(self.stage))
        directories = list(self.root.glob('windows-world-worker.ninja-configure-*'))
        self.assertEqual(len(directories), 1)
        for name in ninja.NAMES:
            self.assertEqual(ninja._row(directories[0] / name), ninja._row(self.engine / name))
        self.assertTrue((directories[0] / 'complete.json').exists())

    def test_failed_configure_restores_before_propagating(self):
        def failure(*args):
            self.generated(*args)
            raise subprocess.CalledProcessError(1, 'cmake')
        with self.assertRaises(subprocess.CalledProcessError): self.configure(failure)
        self.assertEqual(recovery._inventory(self.stage), self.before)
        self.assertFalse(ninja.configure_pending(self.stage))

    def test_missing_originals_remain_missing_on_first_configure(self):
        for name in (*ninja.NAMES, *ninja.VARIANTS):
            path = self.engine / name
            if path.exists(): path.unlink()
        before = recovery._inventory(self.stage)
        self.configure(lambda command, env: None)
        self.assertEqual(recovery._inventory(self.stage), before)

    def test_missing_log_with_restat_requires_review(self):
        (self.engine / '.ninja_log').unlink()
        with self.assertRaises(BuildError): self.configure(Mock())
        self.assertFalse(list(self.root.glob('*.ninja-configure-*')))

    def test_missing_log_with_deps_or_other_variant_requires_review(self):
        (self.engine / '.ninja_log').unlink()
        (self.engine / '.ninja_log.restat').unlink()
        with self.assertRaises(BuildError): self.configure(Mock())
        (self.engine / '.ninja_deps').unlink()
        for name in ('.ninja_log.recompact', '.ninja_deps.recompact'):
            (self.engine / name).write_bytes(b'retained partial history')
            with self.assertRaises(BuildError): self.configure(Mock())
            (self.engine / name).unlink()
        self.assertFalse(list(self.root.glob('*.ninja-configure-*')))

    def test_changed_file_before_unlink_rejected_and_original_not_overwritten(self):
        original = recovery._publish
        def changed(path, value):
            original(path, value)
            if path.name == 'journal.json': (self.engine / '.ninja_log').write_bytes(b'changed by concurrent process')
        with patch.object(recovery, '_publish', side_effect=changed):
            with self.assertRaises(BuildError): self.configure(Mock())
        self.assertEqual((self.engine / '.ninja_log').read_bytes(), b'changed by concurrent process')
        self.assertTrue(ninja.configure_pending(self.stage))

    def test_unexpected_new_history_preserved_rejected(self):
        def foreign(command, env): (self.engine / '.ninja_log').write_bytes(b'new unowned history')
        with self.assertRaises(BuildError): self.configure(foreign)
        self.assertEqual((self.engine / '.ninja_log').read_bytes(), b'new unowned history')
        self.assertTrue(ninja.configure_pending(self.stage))

    def test_partial_removal_failure_restores_both_files(self):
        original = Path.unlink
        def failure(path, *args, **kw):
            if path == self.engine / '.ninja_deps': raise PermissionError('blocked')
            return original(path, *args, **kw)
        with patch.object(Path, 'unlink', failure):
            with self.assertRaises(PermissionError): self.configure(Mock())
        self.assertEqual(recovery._inventory(self.stage), self.before)
        self.assertFalse(ninja.configure_pending(self.stage))

    def test_process_interruption_before_finally_resumes_first(self):
        with patch.object(ninja, '_restore_guard', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.configure(self.generated)
        self.assertTrue(ninja.configure_pending(self.stage))
        self.assertFalse((self.engine / '.ninja_log').exists())
        with ninja.build_lock(self.stage): self.assertTrue(ninja.resume_configure(self.stage))
        self.assertEqual(recovery._inventory(self.stage), self.before)
        self.assertFalse(ninja.resume_configure(self.stage))

    def test_interrupted_partial_restore_appends_only_verified_prefix(self):
        original = ninja._copy
        def interrupted(source, destination, row, **kw):
            if destination == self.engine / '.ninja_deps':
                destination.write_bytes(source.read_bytes()[:17])
                raise KeyboardInterrupt
            return original(source, destination, row, **kw)
        with patch.object(ninja, '_copy', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.configure(self.generated)
        self.assertTrue(ninja.configure_pending(self.stage))
        ninja.resume_configure(self.stage)
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_tampered_backup_or_partial_restore_rejected(self):
        with patch.object(ninja, '_restore_guard', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.configure(self.generated)
        directory, _ = ninja._guards(self.stage)[0]
        original = (directory / '.ninja_log').read_bytes()
        (directory / '.ninja_log').write_bytes(b'changed backup')
        with self.assertRaises(BuildError): ninja.resume_configure(self.stage)
        self.assertFalse((self.engine / '.ninja_log').exists())
        self.assertNotEqual((directory / '.ninja_log').read_bytes(), original)

    def test_tampered_partial_restore_and_foreign_restore_marker_rejected(self):
        original = ninja._copy
        def interrupted(source, destination, row, **kw):
            if destination == self.engine / '.ninja_deps':
                destination.write_bytes(b'foreign partial bytes')
                raise KeyboardInterrupt
            return original(source, destination, row, **kw)
        with patch.object(ninja, '_copy', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.configure(self.generated)
        with self.assertRaises(BuildError): ninja.resume_configure(self.stage)
        self.assertEqual((self.engine / '.ninja_deps').read_bytes(), b'foreign partial bytes')
        directory, _ = ninja._guards(self.stage)[0]
        dump(directory / 'restoring.json', {'foreign': True})
        with self.assertRaises(BuildError): ninja.resume_configure(self.stage)

    def test_multiple_incomplete_guards_rejected(self):
        with patch.object(ninja, '_restore_guard', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.configure(self.generated)
        directory, record = ninja._guards(self.stage)[0]
        other = self.stage.with_name(self.stage.name + '.ninja-configure-' + 'a' * 32)
        other.mkdir()
        dump(other / 'journal.json', record)
        with self.assertRaises(BuildError): ninja.resume_configure(self.stage)

    def test_changed_variant_preserved_rejected(self):
        def changed(*args): (self.engine / '.ninja_log.restat').write_bytes(b'changed temporary')
        with self.assertRaises(BuildError): self.configure(changed)
        self.assertEqual((self.engine / '.ninja_log.restat').read_bytes(), b'changed temporary')

    def test_subsequent_configuration_uses_fresh_logs_and_retains_old_backups(self):
        self.configure(self.generated)
        (self.engine / '.ninja_log').write_bytes(b'legitimate incremental history')
        after_compile = recovery._inventory(self.stage)
        self.configure(self.generated)
        self.assertEqual(recovery._inventory(self.stage), after_compile)
        self.assertEqual(len(list(self.root.glob('*.ninja-configure-*'))), 2)
        self.stage.rename(self.stage.with_name('preserved'))
        self.assertFalse(ninja.configure_pending(self.stage))

    def test_foreign_lock_and_redirected_paths_rejected(self):
        (self.root / (self.stage.name + '.build.lock')).write_bytes(b'foreign')
        with self.assertRaises(BuildError):
            with ninja.build_lock(self.stage): pass
        (self.engine / '.ninja_log').unlink()
        (self.engine / '.ninja_log').symlink_to(self.engine / '.ninja_deps')
        with self.assertRaises(BuildError): ninja.configure(self.stage, self.command, {}, Mock())

    def test_bound_and_suppress_regeneration_cannot_be_disabled(self):
        with patch.object(recovery, 'MAX_METADATA', 10):
            with self.assertRaises(BuildError): ninja._row(self.engine / '.ninja_deps')
        command = self.command + ['-DCMAKE_SUPPRESS_REGENERATION=OFF']
        with self.assertRaises(BuildError): ninja.configure(self.stage, command, {}, Mock())
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_extra_or_duplicate_regeneration_arguments_rejected(self):
        for suffix in ('-DCMAKE_SUPPRESS_REGENERATION=OFF', '-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON'):
            command = self.command + ['-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON', suffix]
            with self.assertRaises(BuildError): ninja.configure(self.stage, command, {}, Mock())
            self.assertEqual(recovery._inventory(self.stage), self.before)


if __name__ == '__main__':
    unittest.main()
