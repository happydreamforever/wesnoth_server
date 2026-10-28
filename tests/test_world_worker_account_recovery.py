"""Preserving source continuation over a completed, synthetic Ninja recovery."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_ninja_recovery as ninja
from tools import world_worker_account_recovery as account
from tools import build_world_worker as worker
from tools.build_alliance_bridge import BuildError
from tests import test_world_worker_ninja_recovery as ninja_tests

dump = ninja_tests.dump


class AccountSourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        old = next(name for name in account.ACCOUNT_REVISIONS if name.startswith('5a3'))
        source_patch = patch.object(ninja, 'REVIEWED_SOURCES', {**ninja.REVIEWED_SOURCES, account.ACCOUNT_INPUT: old})
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.fixture = ninja_tests.NinjaRecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.stage, self.engine, self.root = self.fixture.stage, self.fixture.engine, self.fixture.root
        self.fixture.expected['inputs'][recovery.BUILDER_INPUT] = next(x for x in account.LEGACY_BUILDERS if x.startswith('ca3'))
        self.fixture.expected['inputs'][ninja.INPUT] = next(x for x in account.NINJA_HELPERS if x.startswith('df68'))
        self.fixture.recover()
        self.owner = deepcopy(self.fixture.expected)
        self.expected = deepcopy(self.owner)
        self.expected['inputs'][recovery.BUILDER_INPUT] = '1' * 64
        self.expected['inputs'][account.INPUT] = '2' * 64
        self.expected['inputs'][account.ACCOUNT_INPUT] = account.ACCOUNT_REVISIONS[old]
        self.extra = self.engine / 'src/new-world-worker.cpp.obj'
        self.extra.write_bytes(b'new object completed after recovered Ninja configuration')
        with (self.engine / '.ninja_log').open('ab') as stream:
            stream.write(b'4\t5\t6\tsrc/new-world-worker.cpp.obj\t123456\n')
        with (self.engine / '.ninja_deps').open('ab') as stream: stream.write(b'new native dependency records')
        (self.engine / 'CMakeCache.txt').write_text('CMAKE_SUPPRESS_REGENERATION:BOOL=ON\n')
        (self.engine / 'build.ninja').write_text('build src/new-world-worker.cpp.obj: CXX_COMPILER native.cpp\n')
        self.initial = recovery._inventory(self.stage)
        self.old_journals = {path.name: path.read_bytes() for path in self.root.glob('windows-world-worker.*.json')}
        self.validate = Mock()
        _, self.journal, self.complete, self.lock = account._paths(self.stage)

    def resume(self):
        with ninja.build_lock(self.stage):
            return account.resume_account_stage(self.stage, self.expected, self.validate)

    def unchanged(self):
        actual = recovery._inventory(self.stage)
        actual['files'].pop('owner.json')
        expected = deepcopy(self.initial)
        expected['files'].pop('owner.json')
        self.assertEqual(actual, expected)
        for name, raw in self.old_journals.items(): self.assertEqual((self.root / name).read_bytes(), raw)

    def test_rebind_preserves_previous_and_additional_objects_and_all_old_journals(self):
        self.assertTrue(self.resume())
        self.unchanged()
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        record = recovery._read_json(self.journal)
        self.assertEqual(record['inventory'], self.initial)
        self.assertEqual(record['original_owner'], self.owner)
        self.assertEqual(json.loads(bytes.fromhex(record['original_owner_hex'])), self.owner)
        self.assertFalse(account.account_recovery_pending(self.stage))
        self.assertFalse((self.stage / 'receipt.json').exists())
        self.assertFalse(list(self.root.glob('windows-world-worker-before-*')))
        self.validate.assert_called_once()

    def test_completed_transition_allows_later_incremental_objects_and_historical_stage(self):
        self.resume()
        self.extra.write_bytes(b'legitimate later native compilation')
        (self.stage / 'receipt.json').write_bytes(b'completed worker')
        before = recovery._inventory(self.stage)
        self.validate.reset_mock()
        self.assertTrue(self.resume())
        self.assertEqual(recovery._inventory(self.stage), before)
        self.validate.assert_not_called()
        self.stage.rename(self.stage.with_name('retained-completed-worker'))
        self.assertFalse(account.account_recovery_pending(self.stage))

    def test_no_stage_and_current_owner_need_no_recovery(self):
        fresh = self.root / 'never-built'
        self.assertFalse(account.account_recovery_pending(fresh))
        dump(self.stage / 'owner.json', self.expected)
        before = recovery._inventory(self.stage)
        self.assertFalse(self.resume())
        self.assertEqual(recovery._inventory(self.stage), before)

    def test_only_reviewed_old_and_new_account_source_hashes_are_accepted(self):
        account._legacy(self.owner, self.expected)
        for name in (recovery.BUILDER_INPUT, account.ACCOUNT_INPUT, ninja.INPUT,
                     recovery.RECOVERY_INPUT, resource.RESOURCE_INPUT,
                     'wesnoth_client/engine/CMakeLists.txt'):
            changed = deepcopy(self.owner)
            changed['inputs'][name] = '9' * 64
            with self.assertRaises(BuildError): account._legacy(changed, self.expected)
        for name in (account.ACCOUNT_INPUT, recovery.RECOVERY_INPUT,
                     'wesnoth_server/build/world-worker-prefix/receipt.json'):
            changed = deepcopy(self.expected)
            changed['inputs'][name] = '9' * 64
            with self.assertRaises(BuildError): account._legacy(self.owner, changed)
        changed = deepcopy(self.expected)
        changed['inputs'].pop(account.INPUT)
        with self.assertRaises(BuildError): account._legacy(self.owner, changed)

    def test_preserves_incidental_objects_not_present_in_the_old_log(self):
        (self.engine / 'compiler-probe.obj').write_bytes(b'incidental CMake probe')
        self.initial = recovery._inventory(self.stage)
        self.assertTrue(self.resume())
        self.unchanged()

    def test_changed_original_compiled_output_or_temporary_refused(self):
        original = self.engine / self.fixture.paths[0]
        original.write_bytes(b'changed original object')
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.journal.exists())

    def test_missing_or_incomplete_old_ninja_recovery_refused(self):
        self.fixture.complete.unlink()
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.journal.exists())

    def test_completed_worker_refused_without_modifying_objects(self):
        (self.stage / 'receipt.json').write_bytes(b'existing receipt')
        before = recovery._inventory(self.stage)
        with self.assertRaises(BuildError): self.resume()
        self.assertEqual(recovery._inventory(self.stage), before)

    def test_interrupt_before_owner_publication_resumes(self):
        with patch.object(resource, '_replace_owner', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        self.assertTrue(account.account_recovery_pending(self.stage))
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertTrue(self.resume())
        self.unchanged()

    def test_interrupt_after_owner_publication_resumes(self):
        publish = recovery._publish
        def interrupted(path, value):
            if path == self.complete: raise KeyboardInterrupt
            return publish(path, value)
        with patch.object(recovery, '_publish', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        self.assertTrue(account.account_recovery_pending(self.stage))
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.unchanged()
        self.assertTrue(self.resume())
        self.unchanged()

    def test_pending_changes_to_new_objects_or_old_journals_refused(self):
        with patch.object(resource, '_replace_owner', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        self.extra.write_bytes(b'changed while recovery pending')
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.complete.exists())

    def test_pending_old_journal_change_refused(self):
        with patch.object(resource, '_replace_owner', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        prior = self.fixture.complete
        prior.write_bytes(prior.read_bytes() + b' ')
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.complete.exists())

    def test_source_validation_failure_and_change_never_publish_owner(self):
        self.validate.side_effect = BuildError('changed overlay')
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.journal.exists())
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.validate.side_effect = lambda: (self.stage / 'source/CMakeLists.txt').write_bytes(b'changed')
        with self.assertRaises(BuildError): self.resume()
        self.assertFalse(self.journal.exists())

    def test_hardlink_and_competing_lock_refused(self):
        with resource._lock(self.lock):
            with self.assertRaises(BuildError): self.resume()
        os.link(self.extra, self.engine / 'linked.obj')
        with self.assertRaises(BuildError): self.resume()

    def test_completion_tampering_refused(self):
        self.resume()
        dump(self.complete, {'foreign': True})
        with self.assertRaises(BuildError): account.account_recovery_pending(self.stage)
        with self.assertRaises(BuildError): self.resume()

    def builder(self, *, preserve=True, report=None, stop_after_rebind=False):
        calls = []
        class StopAfterRebind(Exception): pass
        with ExitStack() as stack:
            def setmock(name, **kwargs): return stack.enter_context(patch.object(worker, name, **kwargs))
            setmock('STAGE', new=self.stage)
            setmock('ROOT', new=self.root)
            setmock('DEPENDENCY_PREFIX', new=self.root)
            setmock('REQUIRED', new={})
            setmock('safe_path', side_effect=lambda path, **kw: Path(path))
            setmock('data_inventory', return_value={})
            setmock('compiler_environment', return_value={})
            setmock('compiler_preflight')
            setmock('game_resource_preflight')
            setmock('digest', return_value='0' * 64)
            setmock('binding', return_value=self.expected)
            setmock('capture', side_effect=['cmake version 4.3.0', '1.13.2', 'x86_64-w64-mingw32', '16.2.0'])
            overlay = setmock('prepare_worker_overlay', side_effect=lambda **kw: calls.append(('overlay', kw)))
            rules = setmock('verify_resource_rule', side_effect=lambda stage: calls.append(('rules', stage)))
            cache = setmock('verify_ninja_configuration', side_effect=lambda stage: calls.append(('regeneration', stage)))
            setmock('prepare_toolchain', side_effect=StopAfterRebind)
            stack.enter_context(patch('tools.world_worker_archive_prefix.verify_locked_prefix'))
            old_resource = stack.enter_context(patch.object(resource, 'resume_resource_stage', side_effect=AssertionError('old resource recovery must not run')))
            old_ninja = stack.enter_context(patch.object(ninja, 'recover_reviewed', side_effect=AssertionError('old Ninja recovery must not run')))
            old_preserve = stack.enter_context(patch.object(recovery, 'preserve_failed_stage', side_effect=AssertionError('no stage preservation/rebuild')))
            if stop_after_rebind:
                with self.assertRaises(StopAfterRebind): worker.build_locked('msys', 'cmake', 'data', preserve, report)
            else:
                worker.build_locked('msys', 'cmake', 'data', preserve, report)
        return calls

    def test_builder_dispatch_resumes_account_source_before_old_helpers(self):
        calls = self.builder(stop_after_rebind=True)
        self.assertEqual(calls[0], ('overlay', {'validate_existing': True}))
        self.assertEqual([name for name, _ in calls[1:]], ['rules', 'regeneration'])
        self.unchanged()
        self.assertFalse(account.account_recovery_pending(self.stage))
        self.assertEqual(self.builder(stop_after_rebind=True), [])

    def test_builder_requires_preserve_and_rejects_stale_ninja_report(self):
        for preserve, report in ((False, None), (True, self.fixture.report_path)):
            with self.assertRaises(BuildError): self.builder(preserve=preserve, report=report)
            self.assertFalse(self.journal.exists())
            self.assertEqual(recovery._inventory(self.stage), self.initial)


if __name__ == '__main__':
    unittest.main()
