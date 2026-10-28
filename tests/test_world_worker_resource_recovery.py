"""Real filesystem continuation fixtures; native compilation is tested separately."""
from copy import deepcopy
from contextlib import ExitStack, contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools.build_alliance_bridge import BuildError


class WorkerResourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / 'windows-world-worker'
        self.stage.mkdir()
        self.expected = {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
                         'inputs': {recovery.BUILDER_INPUT: 'a' * 64,
                                    recovery.RECOVERY_INPUT: 'b' * 64,
                                    resource.RESOURCE_INPUT: 'c' * 64,
                                    'wesnoth_client/engine/CMakeLists.txt': 'd' * 64,
                                    'wesnoth_server/build/world-worker-prefix/receipt.json': 'e' * 64}}
        self.owner = deepcopy(self.expected)
        self.owner['inputs'].pop(resource.RESOURCE_INPUT)
        pair = sorted(resource.LEGACY_PAIRS)[0]
        self.owner['inputs'][recovery.BUILDER_INPUT] = pair[0]
        self.owner['inputs'][recovery.RECOVERY_INPUT] = pair[1]
        (self.stage / 'owner.json').write_bytes(json.dumps(self.owner).encode() + b'\r\n')
        (self.stage / 'source').mkdir()
        (self.stage / 'source' / 'empty').mkdir()
        (self.stage / 'source' / 'CMakeLists.txt').write_bytes(b'original validated CMake source\r\n')
        (self.stage / 'worker-toolchain.cmake').write_bytes(b'owned pre-resource toolchain')
        (self.stage / 'engine').mkdir()
        self.obj = self.stage / 'engine' / 'existing.cpp.obj'
        self.obj.write_bytes(bytes(range(256)) * 4)
        os.utime(self.obj, ns=(1234567890000000000, 1234567890000000000))
        self.initial = recovery._inventory(self.stage)
        self.original_owner = (self.stage / 'owner.json').read_bytes()
        _, self.journal, self.complete, self.lock = resource._paths(self.stage)
        self.validate = Mock(side_effect=self.validate_source)

    def validate_source(self):
        self.assertEqual((self.stage / 'source' / 'CMakeLists.txt').read_bytes(),
                         b'original validated CMake source\r\n')
        self.assertEqual((self.stage / 'worker-toolchain.cmake').read_bytes(),
                         b'owned pre-resource toolchain')

    def resume(self):
        return resource.resume_resource_stage(self.stage, self.expected, self.validate)

    def assert_non_owner_preserved(self):
        actual = recovery._inventory(self.stage)
        expected = deepcopy(self.initial)
        actual['files'].pop('owner.json')
        expected['files'].pop('owner.json')
        self.assertEqual(actual, expected)

    def interrupt_before_owner(self):
        with patch.object(resource, '_replace_owner', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        self.assertTrue(resource.resource_recovery_pending(self.stage))
        self.assertEqual(recovery._inventory(self.stage), self.initial)

    def interrupt_after_owner(self):
        publish = recovery._publish
        def interrupt(path, value):
            if path == self.complete:
                raise KeyboardInterrupt
            return publish(path, value)
        with patch.object(recovery, '_publish', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.resume()
        self.assertTrue(resource.resource_recovery_pending(self.stage))
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assert_non_owner_preserved()

    def test_exact_legacy_update_preserves_every_object_and_original_owner(self):
        self.assertTrue(self.resume())
        self.assert_non_owner_preserved()
        record = recovery._read_json(self.journal)
        self.assertEqual(bytes.fromhex(record['original_owner_hex']), self.original_owner)
        self.assertEqual(record['inventory'], self.initial)
        self.assertEqual(record['original_owner'], self.owner)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertEqual(recovery._read_json(self.complete)['status'],
                         'source_binding_updated_not_verified_build')
        self.assertFalse(resource.resource_recovery_pending(self.stage))
        self.assertFalse((self.stage / 'receipt.json').exists())
        self.assertFalse(list(self.root.glob('windows-world-worker-before-*')))
        self.validate.assert_called()

    def test_both_matching_line_endings_accepted_but_mixed_hashes_rejected(self):
        self.assertEqual(len(resource.LEGACY_PAIRS), 2)
        pairs = sorted(resource.LEGACY_PAIRS)
        for builder, helper in pairs:
            owner = deepcopy(self.owner)
            owner['inputs'][recovery.BUILDER_INPUT] = builder
            owner['inputs'][recovery.RECOVERY_INPUT] = helper
            resource._legacy(owner, self.expected)
        owner['inputs'][recovery.BUILDER_INPUT] = pairs[0][0]
        owner['inputs'][recovery.RECOVERY_INPUT] = pairs[1][1]
        with self.assertRaises(BuildError): resource._legacy(owner, self.expected)

    def test_repeat_accepts_later_native_objects_without_touching_journals(self):
        self.resume()
        before_journal = self.journal.read_bytes()
        before_complete = self.complete.read_bytes()
        self.obj.write_bytes(b'later native build output')
        (self.stage / 'engine' / 'new.cpp.obj').write_bytes(b'newly compiled object')
        (self.stage / 'receipt.json').write_bytes(b'completed normal build receipt')
        inventory = recovery._inventory(self.stage)
        self.validate.reset_mock()
        self.assertTrue(self.resume())
        self.assertEqual(recovery._inventory(self.stage), inventory)
        self.assertEqual(self.journal.read_bytes(), before_journal)
        self.assertEqual(self.complete.read_bytes(), before_complete)
        self.validate.assert_not_called()

    def test_current_stage_without_transition_is_not_changed(self):
        (self.stage / 'owner.json').write_bytes(resource._new_owner(self.expected))
        (self.stage / 'receipt.json').write_bytes(b'existing current receipt')
        before = recovery._inventory(self.stage)
        self.assertFalse(self.resume())
        self.assertEqual(recovery._inventory(self.stage), before)
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.complete.exists())
        self.assertFalse(self.lock.exists())
        self.validate.assert_not_called()

    def test_fresh_absent_stage_has_no_pending_resource_transition(self):
        fresh = self.root / 'fresh-worker'
        self.assertFalse(resource.resource_recovery_pending(fresh))
        self.assertFalse(fresh.exists())
        self.assertEqual(list(self.root.glob('fresh-worker*')), [])
        with self.assertRaisesRegex(BuildError, 'directory is missing'):
            resource.resume_resource_stage(fresh, self.expected, self.validate)
        self.validate.assert_not_called()

    def test_completed_historical_transition_allows_stage_retained_elsewhere(self):
        self.resume()
        journal = self.journal.read_bytes()
        complete = self.complete.read_bytes()
        retained = self.root / 'completed-worker-retained-for-later-update'
        self.stage.rename(retained)
        self.assertFalse(resource.resource_recovery_pending(self.stage))
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.journal.read_bytes(), journal)
        self.assertEqual(self.complete.read_bytes(), complete)
        self.assertEqual((retained / 'engine' / 'existing.cpp.obj').read_bytes(), bytes(range(256)) * 4)

    def test_pending_transition_still_requires_its_existing_stage(self):
        self.interrupt_before_owner()
        retained = self.root / 'unexpectedly-moved-stage'
        self.stage.rename(retained)
        with self.assertRaisesRegex(BuildError, 'directory is missing'):
            resource.resource_recovery_pending(self.stage)
        self.assertTrue(retained.is_dir())
        self.assertFalse(self.complete.exists())

    def test_before_owner_interruption_resumes_same_immutable_intent(self):
        self.interrupt_before_owner()
        journal = self.journal.read_bytes()
        self.assertTrue(self.resume())
        self.assertEqual(self.journal.read_bytes(), journal)
        self.assert_non_owner_preserved()
        self.assertFalse(resource.resource_recovery_pending(self.stage))

    def test_after_owner_interruption_resumes_without_replacing_owner_again(self):
        self.interrupt_after_owner()
        info = (self.stage / 'owner.json').stat()
        with patch.object(resource, '_replace_owner') as replace:
            self.assertTrue(self.resume())
            replace.assert_not_called()
        self.assertEqual(recovery._identity((self.stage / 'owner.json').stat()), recovery._identity(info))
        self.assert_non_owner_preserved()
        self.assertFalse(resource.resource_recovery_pending(self.stage))

    def test_changed_file_rejected_before_and_after_owner_upgrade(self):
        for after in (False, True):
            with self.subTest(after_owner=after):
                if after:
                    self.resume()
                    self.complete.unlink()
                else:
                    self.interrupt_before_owner()
                self.obj.write_bytes(b'changed during pending continuation')
                before = recovery._inventory(self.stage)
                with self.assertRaisesRegex(BuildError, 'files changed'):
                    self.resume()
                self.assertEqual(recovery._inventory(self.stage), before)
                self.assertFalse(self.complete.exists())
                self.obj.write_bytes(bytes(range(256)) * 4)
                os.utime(self.obj, ns=(1234567890000000000, 1234567890000000000))

    def test_unknown_source_hash_or_unrelated_input_change_is_rejected(self):
        for field in (recovery.BUILDER_INPUT, recovery.RECOVERY_INPUT,
                      'wesnoth_client/engine/CMakeLists.txt'):
            with self.subTest(field=field):
                owner = deepcopy(self.owner)
                owner['inputs'][field] = 'f' * 64
                (self.stage / 'owner.json').write_text(json.dumps(owner), encoding='utf-8')
                before = recovery._inventory(self.stage)
                with self.assertRaisesRegex(BuildError, 'recognized resource-stage'):
                    self.resume()
                self.assertEqual(recovery._inventory(self.stage), before)
                self.assertFalse(self.journal.exists())
                self.validate.assert_not_called()

    def test_only_new_helper_input_may_be_missing_from_old_binding(self):
        variants = []
        owner = deepcopy(self.owner)
        owner['inputs'][resource.RESOURCE_INPUT] = 'c' * 64
        variants.append(owner)
        owner = deepcopy(self.owner)
        owner['inputs'].pop('wesnoth_client/engine/CMakeLists.txt')
        variants.append(owner)
        owner = deepcopy(self.owner)
        owner['inputs']['foreign/input.py'] = 'f' * 64
        variants.append(owner)
        for owner in variants:
            with self.subTest(inputs=sorted(owner['inputs'])):
                with self.assertRaises(BuildError): resource._legacy(owner, self.expected)

    def test_completed_legacy_stage_is_never_rebound(self):
        (self.stage / 'receipt.json').write_bytes(b'receipt must not be bypassed')
        before = recovery._inventory(self.stage)
        with self.assertRaisesRegex(BuildError, 'Completed workers'): self.resume()
        self.assertEqual(recovery._inventory(self.stage), before)
        self.assertFalse(self.journal.exists())
        self.validate.assert_not_called()

    def test_callback_rejection_preserves_original_stage(self):
        self.validate.side_effect = BuildError('source/toolchain rejected')
        with self.assertRaisesRegex(BuildError, 'source/toolchain rejected'): self.resume()
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.complete.exists())

    def test_callback_mutation_is_rejected_before_ownership_change(self):
        self.validate.side_effect = lambda: self.obj.write_bytes(b'unexpected callback mutation')
        with self.assertRaisesRegex(BuildError, 'changed during resource-stage validation'): self.resume()
        self.assertEqual((self.stage / 'owner.json').read_bytes(), self.original_owner)
        self.assertEqual(self.obj.read_bytes(), b'unexpected callback mutation')
        self.assertFalse(self.journal.exists())

    def test_pending_recovery_rejects_changed_expected_binding(self):
        self.interrupt_before_owner()
        self.expected['inputs'][resource.RESOURCE_INPUT] = 'f' * 64
        with self.assertRaisesRegex(BuildError, 'another corrected build'): self.resume()
        self.assertEqual(recovery._inventory(self.stage), self.initial)

    def test_pending_recovery_rejects_changed_owner_and_new_receipt(self):
        self.interrupt_before_owner()
        (self.stage / 'owner.json').write_bytes(self.original_owner + b' ')
        with self.assertRaisesRegex(BuildError, 'ownership changed'): self.resume()
        self.assertFalse(self.complete.exists())
        (self.stage / 'owner.json').write_bytes(self.original_owner)
        (self.stage / 'receipt.json').write_bytes(b'new receipt')
        with self.assertRaisesRegex(BuildError, 'Completed workers'): self.resume()
        self.assertFalse(self.complete.exists())

    def test_actual_held_lock_blocks_other_recovery(self):
        with resource._lock(self.lock):
            with self.assertRaisesRegex(BuildError, 'holds the lock'): self.resume()
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertFalse(self.journal.exists())

    def test_foreign_lock_is_preserved(self):
        self.lock.write_bytes(b'foreign lock')
        with self.assertRaisesRegex(BuildError, 'lock is foreign'): self.resume()
        self.assertEqual(self.lock.read_bytes(), b'foreign lock')
        self.assertEqual(recovery._inventory(self.stage), self.initial)

    def test_links_and_hardlinks_are_preserved_and_refused(self):
        target = self.root / 'outside'
        target.write_bytes(b'outside sentinel')
        link = self.stage / 'source' / 'linked'
        link.symlink_to(target)
        with self.assertRaises(BuildError): self.resume()
        self.assertTrue(link.is_symlink())
        link.unlink()
        os.link(self.obj, self.root / 'outside-object')
        with self.assertRaisesRegex(BuildError, 'single-link'): self.resume()
        self.assertEqual(target.read_bytes(), b'outside sentinel')
        self.assertFalse(self.journal.exists())

    def test_external_metadata_links_and_duplicate_fields_are_refused(self):
        target = self.root / 'outside-json'
        target.write_bytes(b'outside sentinel')
        for path in (self.journal, self.complete, self.lock):
            with self.subTest(path=path):
                path.symlink_to(target)
                with self.assertRaises(BuildError): self.resume()
                self.assertTrue(path.is_symlink())
                path.unlink()
        self.journal.write_bytes(b'{"format": 1, "format": 1}')
        with self.assertRaises(BuildError): self.resume()
        self.assertEqual(target.read_bytes(), b'outside sentinel')
        self.assertEqual(recovery._inventory(self.stage), self.initial)

    def test_tampered_completion_and_orphan_marker_are_refused(self):
        self.resume()
        self.complete.write_bytes(b'{}')
        with self.assertRaises(BuildError): self.resume()
        with self.assertRaises(BuildError): resource.resource_recovery_pending(self.stage)
        self.journal.unlink()
        with self.assertRaisesRegex(BuildError, 'no journal'): self.resume()
        with self.assertRaisesRegex(BuildError, 'no journal'): resource.resource_recovery_pending(self.stage)
        self.assertEqual(self.complete.read_bytes(), b'{}')

    def test_original_owner_journal_bytes_cannot_be_changed(self):
        self.interrupt_before_owner()
        record = recovery._read_json(self.journal)
        record['original_owner_hex'] = b'{}\n'.hex()
        self.journal.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaisesRegex(BuildError, 'original ownership differs'): self.resume()
        self.assertEqual(recovery._inventory(self.stage), self.initial)

    def test_existing_sysroot_journals_runtime_and_prefix_are_untouched(self):
        sentinels = []
        for suffix in ('.sysroot-recovery.json', '.sysroot-recovery-complete.json', '.sysroot-recovery.lock'):
            path = self.stage.with_name(self.stage.name + suffix)
            path.write_bytes(('preserve ' + suffix).encode())
            sentinels.append(path)
        for name in ('runtime-v2', 'world-worker-prefix', 'old-worker-stage'):
            directory = self.root / name
            directory.mkdir()
            path = directory / 'sentinel'
            path.write_bytes(name.encode())
            sentinels.append(path)
        before = {str(path): (path.read_bytes(), recovery._identity(path.stat())) for path in sentinels}
        self.resume()
        self.assertEqual({str(path): (path.read_bytes(), recovery._identity(path.stat()))
                          for path in sentinels}, before)
        self.assert_non_owner_preserved()

    @contextmanager
    def builder_dispatch(self):
        """Actual ownership continuation, with the native compiler boundaries simulated."""
        from tools import build_world_worker as builder
        from tools import world_worker_archive_prefix as archives
        prefix = self.root / 'isolated-prefix'
        prefix.mkdir(exist_ok=True)
        data = self.root / 'game-data'
        data.mkdir(exist_ok=True)
        msys = self.root / 'msys'
        (msys / 'ucrt64' / 'bin').mkdir(parents=True, exist_ok=True)
        (msys / 'ucrt64' / 'bin' / 'ninja.exe').write_bytes(b'simulated tool')
        cmake = self.root / 'cmake.exe'
        cmake.write_bytes(b'simulated tool')
        with ExitStack() as stack:
            for target, name, value in ((builder, 'ROOT', self.root), (builder, 'STAGE', self.stage),
                    (builder, 'DEPENDENCY_PREFIX', prefix), (builder, 'REQUIRED', {})):
                stack.enter_context(patch.object(target, name, value))
            stack.enter_context(patch.object(builder, 'check_host'))
            stack.enter_context(patch.object(archives, 'verify_locked_prefix'))
            stack.enter_context(patch.object(builder, 'data_inventory', return_value={}))
            stack.enter_context(patch.object(builder, 'compiler_environment', return_value={}))
            stack.enter_context(patch.object(builder, 'capture', side_effect=[
                'cmake version 4.3.0', '1.13.2', 'x86_64-w64-mingw32', '16.2.0']))
            stack.enter_context(patch.object(builder, 'compiler_preflight'))
            stack.enter_context(patch.object(builder, 'game_resource_preflight'))
            stack.enter_context(patch.object(builder, 'binding', return_value=self.expected))
            installed = stack.enter_context(patch.object(builder, 'installed_worker'))
            retained = stack.enter_context(patch.object(recovery, 'preserve_failed_stage'))

            def validate_overlay(*, validate_existing=False):
                self.assertIs(validate_existing, True)
                self.validate_source()

            overlay = stack.enter_context(patch.object(builder, 'prepare_worker_overlay',
                side_effect=validate_overlay))
            ready = stack.enter_context(patch.object(builder, 'prepare_toolchain',
                side_effect=BuildError('fixture reached resumed configuration')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            yield lambda preserve: builder.build(msys, cmake, data, preserve), ready, installed, retained, overlay

    def test_builder_rebinds_recognized_resource_stage_and_keeps_compiled_objects(self):
        with self.builder_dispatch() as (run, ready, installed, retained, overlay):
            with self.assertRaisesRegex(BuildError, 'fixture reached resumed configuration'):
                run(True)
            ready.assert_called_once()
            installed.assert_not_called()
            retained.assert_not_called()
            self.assertGreaterEqual(overlay.call_count, 1)
            self.assertTrue(all(call.kwargs == {'validate_existing': True}
                                for call in overlay.call_args_list))
        self.assert_non_owner_preserved()
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertTrue(self.complete.exists())
        journal = self.journal.read_bytes()
        complete = self.complete.read_bytes()
        with self.builder_dispatch() as (run, ready, installed, retained, overlay):
            with self.assertRaisesRegex(BuildError, 'fixture reached resumed configuration'):
                run(True)
            ready.assert_called_once()
            installed.assert_not_called()
            retained.assert_not_called()
            overlay.assert_not_called()
        self.assert_non_owner_preserved()
        self.assertEqual(self.journal.read_bytes(), journal)
        self.assertEqual(self.complete.read_bytes(), complete)

    def test_builder_requires_explicit_preservation_for_resource_transition(self):
        with self.builder_dispatch() as (run, ready, installed, retained, overlay):
            with self.assertRaisesRegex(BuildError, 'requires -PreservePreviousBuild'):
                run(False)
            ready.assert_not_called()
            installed.assert_not_called()
            retained.assert_not_called()
            overlay.assert_not_called()
        self.assertEqual(recovery._inventory(self.stage), self.initial)
        self.assertFalse(self.journal.exists())


if __name__ == '__main__':
    unittest.main()
