"""Filesystem recovery fixtures; these do not compile or run a Windows engine."""
from copy import deepcopy
from contextlib import ExitStack, contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import world_worker_recovery as recovery
from tools.build_alliance_bridge import BuildError


def stat_copy(info, **changes):
    """Keep the identity fields while modelling one Win32 stat API result."""
    values = {name: getattr(info, name) for name in (
        'st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_nlink')}
    values['st_file_attributes'] = getattr(info, 'st_file_attributes', 0)
    values.update(changes)
    return SimpleNamespace(**values)


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / 'windows-world-worker'
        self.stage.mkdir()
        self.expected = {
            'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
            'inputs': {
                recovery.BUILDER_INPUT: 'b' * 64,
                recovery.RECOVERY_INPUT: 'c' * 64,
                'wesnoth_client/engine/CMakeLists.txt': 'a' * 64,
                'wesnoth_server/build/world-worker-prefix/receipt.json': 'd' * 64,
            },
        }
        self.owner = deepcopy(self.expected)
        self.owner['inputs'].pop(recovery.RECOVERY_INPUT)
        self.owner['inputs'][recovery.BUILDER_INPUT] = sorted(recovery.LEGACY_BUILDERS)[0]
        self.write_owner(self.owner)
        (self.stage / 'source' / 'empty').mkdir(parents=True)
        (self.stage / 'source' / 'CMakeLists.txt').write_bytes(b'original generated CMake\r\n')
        (self.stage / 'CMakeCache.txt').write_bytes(b'FAILED_COMPILE:BOOL=TRUE\r\n')
        (self.stage / 'partial.obj').write_bytes(bytes(range(256)))
        os.utime(self.stage / 'partial.obj', ns=(1234567890000000000, 1234567890000000000))
        self.initial = recovery._inventory(self.stage)
        _, self.journal, self.complete = recovery._paths(self.stage)

    def write_owner(self, owner):
        (self.stage / 'owner.json').write_text(json.dumps(owner), encoding='utf-8')

    def preserve(self):
        return recovery.preserve_failed_stage(self.stage, self.expected)

    def interrupted_before_rename(self):
        with patch.object(recovery, '_rename', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.preserve()
        self.assertTrue(recovery.recovery_pending(self.stage))
        self.assertTrue(self.stage.is_dir())
        return recovery._read_json(self.journal)

    def assert_stage_preserved(self, original=None):
        self.assertEqual(recovery._inventory(self.stage), original or self.initial)
        self.assertFalse(self.complete.exists())

    @contextmanager
    def windows_executable_stats(self):
        """Linux fixture only: filename stat adds execute bits; fstat does not."""
        original_lstat = Path.lstat
        original_comparison = recovery._same_open_file

        def filename_stat(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if (stat.S_ISREG(info.st_mode)
                    and path.suffix.lower() in ('.exe', '.bat', '.cmd', '.com')):
                return stat_copy(info, st_mode=info.st_mode | 0o111)
            return info

        def compare(path, before, opened):
            return original_comparison(path, before, opened, windows=True)

        with patch.object(Path, 'lstat', filename_stat), patch.object(
                recovery, '_same_open_file', side_effect=compare):
            yield

    def add_executable_files(self):
        for suffix in ('.exe', '.EXE', '.bat', '.cmd', '.com'):
            path = self.stage / ('CMake-compiler-check' + suffix)
            path.write_bytes(b'not executed; retained compiler output\0' + suffix.encode())
            path.chmod(0o600)

    def test_open_identity_allows_only_windows_filename_execute_bits(self):
        opened = stat_copy((self.stage / 'partial.obj').stat(), st_mode=stat.S_IFREG | 0o666)
        before = stat_copy(opened, st_mode=opened.st_mode | 0o111)
        for suffix in ('.exe', '.EXE', '.bat', '.cmd', '.com'):
            with self.subTest(suffix=suffix):
                path = self.stage / ('probe' + suffix)
                self.assertTrue(recovery._same_open_file(path, before, opened, windows=True))
                self.assertFalse(recovery._same_open_file(path, before, opened, windows=False))
                self.assertFalse(recovery._same_open_file(path, opened, before, windows=True))
        for suffix in ('.json', '.txt', '.dll', '.exe.txt', ''):
            with self.subTest(suffix=suffix):
                self.assertFalse(recovery._same_open_file(
                    self.stage / ('probe' + suffix), before, opened, windows=True))
        for value in (0o100, 0o010, 0o001, 0o110):
            with self.subTest(partial_execute=value):
                self.assertFalse(recovery._same_open_file(self.stage / 'probe.exe',
                    stat_copy(opened, st_mode=opened.st_mode | value), opened, windows=True))
        self.assertTrue(recovery._same_open_file(
            self.stage / 'unchanged.exe', opened, opened, windows=True))
        self.assertTrue(recovery._same_open_file(
            self.stage / 'unchanged.txt', before, before, windows=False))
        readonly = stat_copy(opened, st_mode=stat.S_IFREG | 0o444, st_file_attributes=1)
        self.assertTrue(recovery._same_open_file(self.stage / 'readonly.EXE',
            stat_copy(readonly, st_mode=readonly.st_mode | 0o111), readonly, windows=True))

    def test_windows_mode_exception_retains_all_other_identity_checks(self):
        opened = stat_copy((self.stage / 'partial.obj').stat(), st_mode=stat.S_IFREG | 0o666)
        before = stat_copy(opened, st_mode=opened.st_mode | 0o111)
        mutations = {
            'device': {'st_dev': opened.st_dev + 1},
            'inode': {'st_ino': opened.st_ino + 1},
            'file_type': {'st_mode': stat.S_IFDIR | 0o666},
            'read_only': {'st_mode': opened.st_mode & ~0o222},
            'size': {'st_size': opened.st_size + 1},
            'mtime': {'st_mtime_ns': opened.st_mtime_ns + 1},
            'hardlink': {'st_nlink': 2},
            'reparse': {'st_file_attributes': 0x400},
            'archive_attribute': {'st_file_attributes': 0x20},
        }
        for name, change in mutations.items():
            with self.subTest(field=name):
                self.assertFalse(recovery._same_open_file(
                    self.stage / 'probe.exe', before, stat_copy(opened, **change), windows=True))

    def test_changed_descriptor_metadata_rejects_json_and_inventory(self):
        original_fstat = os.fstat
        for check in ('metadata', 'inventory'):
            for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_nlink',
                          'st_mode', 'st_file_attributes'):
                with self.subTest(check=check, field=field):
                    def changed(fd):
                        info = original_fstat(fd)
                        value = getattr(info, field, 0)
                        change = value ^ stat.S_IWUSR if field == 'st_mode' else value + 1
                        return stat_copy(info, **{field: change})
                    with patch.object(os, 'fstat', side_effect=changed):
                        with self.assertRaisesRegex(BuildError, 'changed while opening'):
                            if check == 'metadata': recovery._read_json(self.stage / 'owner.json')
                            else: recovery._inventory(self.stage)
                    self.assert_stage_preserved()
                    self.assertFalse(self.journal.exists())

    def test_executable_tree_is_preserved_with_original_path_metadata(self):
        self.add_executable_files()
        with self.windows_executable_stats():
            before = recovery._inventory(self.stage)
            for name, entry in before['files'].items():
                if Path(name).suffix.lower() in ('.exe', '.bat', '.cmd', '.com'):
                    self.assertEqual(entry['mode'] & 0o111, 0o111)
            retained = self.preserve()
            self.assertEqual(recovery._inventory(retained), before)
            self.assertEqual(recovery._read_json(self.journal)['inventory'], before)
            self.assertFalse(recovery.recovery_pending(self.stage))
            self.assertFalse((retained / 'receipt.json').exists())

    def test_executable_recovery_resumes_before_and_after_rename(self):
        self.add_executable_files()
        with self.windows_executable_stats():
            before = recovery._inventory(self.stage)
            record = self.interrupted_before_rename()
            self.assertEqual(record['inventory'], before)
            publish = recovery._publish

            def interrupt_completion(path, value):
                if path == self.complete:
                    raise KeyboardInterrupt
                return publish(path, value)

            with patch.object(recovery, '_publish', side_effect=interrupt_completion):
                with self.assertRaises(KeyboardInterrupt): self.preserve()
            self.assertFalse(self.stage.exists())
            self.assertTrue(recovery.recovery_pending(self.stage))
            retained = Path(record['retained'])
            self.assertEqual(recovery._inventory(retained), before)
            self.assertEqual(self.preserve(), retained)
            self.assertEqual(recovery._inventory(retained), before)
            self.assertFalse(recovery.recovery_pending(self.stage))

    def test_executable_content_replacement_during_hash_is_not_normalized_away(self):
        path = self.stage / 'probe.exe'
        path.write_bytes(b'same bytes; different file identity')
        path.chmod(0o600)
        original_digest = recovery.hashlib.file_digest

        def replace_after_hash(stream, algorithm):
            digest = original_digest(stream, algorithm)
            if Path(stream.name) == path:
                before = path.stat()
                replacement = self.root / 'replacement.exe'
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(stat.S_IMODE(before.st_mode))
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                os.replace(replacement, path)
            return digest

        with self.windows_executable_stats(), patch.object(
                recovery.hashlib, 'file_digest', side_effect=replace_after_hash):
            with self.assertRaisesRegex(BuildError, 'changed while hashing'):
                self.preserve()
        self.assertTrue(self.stage.exists())
        self.assertEqual(path.read_bytes(), b'same bytes; different file identity')
        self.assertFalse(self.journal.exists())

    def test_executable_path_permission_change_after_hash_is_rejected(self):
        path = self.stage / 'probe.exe'
        path.write_bytes(b'retained file')
        path.chmod(0o600)
        original_digest = recovery.hashlib.file_digest

        def chmod_after_hash(stream, algorithm):
            digest = original_digest(stream, algorithm)
            if Path(stream.name) == path:
                path.chmod(0o400)
            return digest

        with self.windows_executable_stats(), patch.object(
                recovery.hashlib, 'file_digest', side_effect=chmod_after_hash):
            with self.assertRaisesRegex(BuildError, 'changed while hashing'):
                self.preserve()
        self.assertTrue(self.stage.exists())
        self.assertEqual(path.read_bytes(), b'retained file')
        self.assertFalse(self.journal.exists())

    def test_exact_legacy_tree_is_retained_without_blessing_outputs(self):
        retained = self.preserve()
        self.assertFalse(self.stage.exists())
        self.assertRegex(retained.name, r'^windows-world-worker-before-sysroot-\d{8}T\d{6}Z-[0-9a-f]{32}$')
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertFalse((retained / 'receipt.json').exists())
        self.assertEqual(recovery._read_json(retained / 'owner.json'), self.owner)
        self.assertEqual(recovery._read_json(self.complete)['status'], 'retained_incomplete_not_verified_build')
        self.assertFalse(recovery.recovery_pending(self.stage))

    def test_both_recorded_builder_line_endings_are_accepted(self):
        self.assertEqual(len(recovery.LEGACY_BUILDERS), 2)
        for digest in recovery.LEGACY_BUILDERS:
            with self.subTest(digest=digest):
                owner = deepcopy(self.owner)
                owner['inputs'][recovery.BUILDER_INPUT] = digest
                recovery._legacy(owner, self.expected)

    def test_repeat_returns_same_artifact_and_preserves_new_current_stage(self):
        retained = self.preserve()
        journal = self.journal.read_bytes()
        completion = self.complete.read_bytes()
        self.assertEqual(self.preserve(), retained)
        self.stage.mkdir()
        self.write_owner(self.expected)
        (self.stage / 'corrected-work.obj').write_bytes(b'new incomplete output')
        new_inventory = recovery._inventory(self.stage)
        self.assertEqual(self.preserve(), retained)
        self.assertEqual(recovery._inventory(self.stage), new_inventory)
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(self.journal.read_bytes(), journal)
        self.assertEqual(self.complete.read_bytes(), completion)

    def test_unknown_builder_and_other_binding_changes_are_refused(self):
        for change in ('builder', 'input_changed', 'input_missing', 'input_added', 'helper_present'):
            with self.subTest(change=change):
                owner = deepcopy(self.owner)
                if change == 'builder': owner['inputs'][recovery.BUILDER_INPUT] = '0' * 64
                elif change == 'input_changed': owner['inputs']['wesnoth_client/engine/CMakeLists.txt'] = 'f' * 64
                elif change == 'input_missing': del owner['inputs']['wesnoth_client/engine/CMakeLists.txt']
                elif change == 'input_added': owner['inputs']['unrecorded.py'] = 'a' * 64
                else: owner['inputs'][recovery.RECOVERY_INPUT] = 'c' * 64
                self.write_owner(owner)
                before = recovery._inventory(self.stage)
                with self.assertRaises(BuildError): self.preserve()
                self.assert_stage_preserved(before)
                self.assertFalse(self.journal.exists())

    def test_invalid_ownership_shape_values_and_paths_are_refused(self):
        mutations = [
            ('format', True), ('format', 2), ('release', 1192623), ('release', True),
            ('purpose', 'other-stage'), ('inputs', []),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                owner = deepcopy(self.owner)
                owner[key] = value
                self.write_owner(owner)
                before = recovery._inventory(self.stage)
                with self.assertRaises(BuildError): self.preserve()
                self.assert_stage_preserved(before)
        for name in ('../outside', '/absolute', 'C:/absolute', 'nested\\file', 'bad\nname'):
            with self.subTest(name=name):
                owner = deepcopy(self.owner)
                owner['inputs'][name] = 'a' * 64
                self.write_owner(owner)
                with self.assertRaises(BuildError): self.preserve()
                self.assertFalse(self.journal.exists())

    def test_missing_current_helper_binding_is_refused(self):
        self.expected['inputs'].pop(recovery.RECOVERY_INPUT)
        with self.assertRaises(BuildError): self.preserve()
        self.assert_stage_preserved()

    def test_duplicate_owner_fields_are_refused(self):
        owner_path = self.stage / 'owner.json'
        owner_path.write_text('{"format": 1, "format": 1}', encoding='utf-8')
        original = owner_path.read_bytes()
        with self.assertRaises(BuildError): self.preserve()
        self.assertEqual(owner_path.read_bytes(), original)
        self.assertFalse(self.journal.exists())

    def test_completed_stage_is_never_reclassified_as_failed(self):
        receipt = self.stage / 'receipt.json'
        receipt.write_bytes(b'not even a valid completion receipt')
        before = recovery._inventory(self.stage)
        with self.assertRaisesRegex(BuildError, 'Completed workers'): self.preserve()
        self.assert_stage_preserved(before)

    def test_missing_owner_preserves_foreign_stage(self):
        (self.stage / 'owner.json').unlink()
        before = recovery._inventory(self.stage)
        with self.assertRaises(OSError): self.preserve()
        self.assert_stage_preserved(before)

    def test_linked_files_and_directories_are_refused_without_reading_targets(self):
        secret = self.root / 'private-runtime'
        secret.mkdir()
        (secret / 'secrets.json').write_bytes(b'private sentinel')
        for relative, directory in (('linked-file', False), ('linked-directory', True)):
            link = self.stage / relative
            link.symlink_to(secret if directory else secret / 'secrets.json', target_is_directory=directory)
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(BuildError, 'linked or redirected'): self.preserve()
                self.assertTrue(link.is_symlink())
                self.assertEqual((secret / 'secrets.json').read_bytes(), b'private sentinel')
                self.assertFalse(self.journal.exists())
            link.unlink()
        self.assert_stage_preserved()

    def test_linked_parent_is_refused(self):
        alias = self.root / 'redirected'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(BuildError):
            recovery.preserve_failed_stage(alias / self.stage.name, self.expected)
        self.assert_stage_preserved()

    def test_hardlinked_file_is_refused(self):
        duplicate = self.root / 'external-object'
        os.link(self.stage / 'partial.obj', duplicate)
        with self.assertRaisesRegex(BuildError, 'single-link'): self.preserve()
        self.assertEqual(duplicate.read_bytes(), bytes(range(256)))
        self.assertTrue(self.stage.exists())
        self.assertFalse(self.journal.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX fixture of forbidden special-file semantics')
    def test_special_file_is_refused_without_blocking(self):
        os.mkfifo(self.stage / 'pipe')
        with self.assertRaisesRegex(BuildError, 'ordinary'): self.preserve()
        self.assertFalse(self.journal.exists())

    def test_inventory_bounds_stop_before_renaming(self):
        for limit, value in (('MAX_FILES', 5), ('MAX_BYTES', 1), ('MAX_METADATA', 1)):
            with self.subTest(limit=limit), patch.object(recovery, limit, value):
                with self.assertRaises(BuildError): self.preserve()
            self.assert_stage_preserved()
            self.assertFalse(self.journal.exists())

    def test_interrupted_before_rename_resumes_same_recorded_destination(self):
        record = self.interrupted_before_rename()
        self.assert_stage_preserved()
        retained = self.preserve()
        self.assertEqual(str(retained), record['retained'])
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertFalse(recovery.recovery_pending(self.stage))

    def test_interrupted_after_rename_resumes_when_original_stage_is_absent(self):
        publish = recovery._publish
        def interrupted(path, value):
            if path == self.complete: raise KeyboardInterrupt
            return publish(path, value)
        with patch.object(recovery, '_publish', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.preserve()
        self.assertFalse(self.stage.exists())
        self.assertTrue(recovery.recovery_pending(self.stage))
        retained = Path(recovery._read_json(self.journal)['retained'])
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(self.preserve(), retained)
        self.assertFalse(recovery.recovery_pending(self.stage))

    def test_pending_recovery_rejects_changed_stage(self):
        self.interrupted_before_rename()
        (self.stage / 'partial.obj').write_bytes(b'changed since intent')
        changed = recovery._inventory(self.stage)
        with self.assertRaisesRegex(BuildError, 'changed after recovery'): self.preserve()
        self.assert_stage_preserved(changed)

    def test_pending_recovery_rejects_receipt_that_appeared(self):
        self.interrupted_before_rename()
        (self.stage / 'receipt.json').write_bytes(b'completion raced recovery')
        changed = recovery._inventory(self.stage)
        with self.assertRaises(BuildError): self.preserve()
        self.assert_stage_preserved(changed)

    def test_pending_recovery_rejects_changed_corrected_binding(self):
        self.interrupted_before_rename()
        self.expected['inputs'][recovery.RECOVERY_INPUT] = 'f' * 64
        with self.assertRaisesRegex(BuildError, 'another corrected build'): self.preserve()
        self.assert_stage_preserved()

    def test_pending_recovery_does_not_overwrite_existing_destination(self):
        record = self.interrupted_before_rename()
        retained = Path(record['retained'])
        retained.mkdir()
        (retained / 'foreign').write_bytes(b'preserve me')
        with self.assertRaises(BuildError): self.preserve()
        self.assert_stage_preserved()
        self.assertEqual((retained / 'foreign').read_bytes(), b'preserve me')

    def test_atomic_rename_refuses_existing_empty_destination(self):
        retained = self.root / 'occupied'
        retained.mkdir()
        with self.assertRaises((BuildError, OSError)):
            recovery._rename(self.stage, retained)
        self.assert_stage_preserved()
        self.assertTrue(retained.is_dir())

    def test_completed_recovery_rejects_changed_retained_file(self):
        retained = self.preserve()
        (retained / 'partial.obj').write_bytes(b'changed retained object')
        with self.assertRaisesRegex(BuildError, 'artifact changed'): self.preserve()
        self.assertEqual((retained / 'partial.obj').read_bytes(), b'changed retained object')
        self.assertFalse(self.stage.exists())

    def test_completed_recovery_rejects_foreign_replacement_stage(self):
        retained = self.preserve()
        self.stage.mkdir()
        self.write_owner(self.owner)
        with self.assertRaisesRegex(BuildError, 'unexpected worker'): self.preserve()
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.owner)

    def test_completion_tampering_and_orphan_completion_are_rejected(self):
        self.preserve()
        self.complete.write_text('{}', encoding='utf-8')
        with self.assertRaises(BuildError): recovery.recovery_pending(self.stage)
        with self.assertRaises(BuildError): self.preserve()
        self.journal.unlink()
        with self.assertRaisesRegex(BuildError, 'no journal'): recovery.recovery_pending(self.stage)
        with self.assertRaisesRegex(BuildError, 'no journal'): self.preserve()
        self.assertEqual(self.complete.read_bytes(), b'{}')

    def test_malformed_journal_destination_is_refused(self):
        record = self.interrupted_before_rename()
        for value in (None, 17, '', str(self.root / 'outside')):
            with self.subTest(value=value):
                altered = deepcopy(record)
                altered['retained'] = value
                self.journal.write_text(json.dumps(altered), encoding='utf-8')
                with self.assertRaises(BuildError): recovery.recovery_pending(self.stage)
                with self.assertRaises(BuildError): self.preserve()
                self.assert_stage_preserved()

    def test_linked_external_metadata_paths_are_refused_before_mutation(self):
        outside = self.root / 'never-created'
        for path in (self.journal, self.complete):
            with self.subTest(path=path):
                path.symlink_to(outside)
                with self.assertRaises(BuildError): self.preserve()
                self.assertTrue(path.is_symlink())
                self.assert_stage_preserved()
                self.assertFalse(outside.exists())
                path.unlink()

    def test_foreign_lock_is_preserved(self):
        lock = self.stage.with_name(self.stage.name + '.sysroot-recovery.lock')
        lock.write_bytes(b'foreign lock')
        with self.assertRaisesRegex(BuildError, 'lock is foreign'): self.preserve()
        self.assertEqual(lock.read_bytes(), b'foreign lock')
        self.assert_stage_preserved()

    def test_held_recovery_lock_stops_competing_attempt(self):
        with recovery._lock(self.stage):
            with self.assertRaisesRegex(BuildError, 'holds the lock'): self.preserve()
        self.assert_stage_preserved()
        self.assertFalse(self.journal.exists())

    def test_interrupted_journal_publication_leaves_original_and_owned_temporary(self):
        with patch.object(recovery.packages, 'publish_artifact', side_effect=OSError('fixture interruption')):
            with self.assertRaises(OSError): self.preserve()
        self.assert_stage_preserved()
        self.assertFalse(self.journal.exists())
        temporary = list(self.root.glob('.*.pending-*'))
        self.assertEqual(len(temporary), 1)
        bytes_before = temporary[0].read_bytes()
        self.assertFalse(recovery.recovery_pending(self.stage))
        retained = self.preserve()
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(temporary[0].read_bytes(), bytes_before)

    def test_unrelated_runtime_prefix_and_previous_build_remain_unchanged(self):
        preserved = {}
        for name in ('runtime-v2', 'world-worker-prefix', 'windows-world-worker-before-old'):
            directory = self.root / name
            directory.mkdir()
            (directory / 'sentinel').write_bytes(name.encode())
            preserved[name] = recovery._inventory(directory)
        self.preserve()
        for name, inventory in preserved.items():
            self.assertEqual(recovery._inventory(self.root / name), inventory)

    def test_no_journal_means_no_recovery_is_pending(self):
        self.assertFalse(recovery.recovery_pending(self.stage))
        self.assert_stage_preserved()

    @contextmanager
    def builder_dispatch(self):
        """Real recovery dispatch only; no compiler, package or engine validation claim."""
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
            for target, name, value in (
                    (builder, 'ROOT', self.root), (builder, 'STAGE', self.stage),
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
            ready = stack.enter_context(patch.object(builder, 'prepare_toolchain',
                side_effect=BuildError('fixture reached corrected stage')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            yield lambda preserve: builder.build(msys, cmake, data, preserve), ready, installed

    def test_builder_preserves_legacy_then_creates_current_stage_before_compile(self):
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'fixture reached corrected stage'): run(True)
            ready.assert_called_once()
            installed.assert_not_called()
        retained = Path(recovery._read_json(self.journal)['retained'])
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertEqual({item.name for item in self.stage.iterdir()}, {'owner.json'})
        self.assertFalse(recovery.recovery_pending(self.stage))

    def test_builder_resumes_external_intent_when_original_stage_is_absent(self):
        publish = recovery._publish
        def interrupt(path, value):
            if path == self.complete: raise KeyboardInterrupt
            publish(path, value)
        with patch.object(recovery, '_publish', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.preserve()
        self.assertFalse(self.stage.exists())
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'fixture reached corrected stage'): run(True)
            ready.assert_called_once()
            installed.assert_not_called()
        retained = Path(recovery._read_json(self.journal)['retained'])
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertFalse(recovery.recovery_pending(self.stage))

    def test_builder_requires_preserve_switch_for_pending_recovery(self):
        self.interrupted_before_rename()
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'recovery is pending'): run(False)
            ready.assert_not_called()
            installed.assert_not_called()
        self.assert_stage_preserved()

    def test_builder_resumes_corrected_incomplete_stage_without_renaming(self):
        self.write_owner(self.expected)
        before = recovery._inventory(self.stage)
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'fixture reached corrected stage'): run(True)
            ready.assert_called_once()
            installed.assert_not_called()
        self.assertEqual(recovery._inventory(self.stage), before)
        self.assertFalse(self.journal.exists())
        self.assertFalse(list(self.root.glob('windows-world-worker-before-*')))

    def test_builder_creates_fresh_stage_without_recovery_journals(self):
        import shutil
        shutil.rmtree(self.stage)  # This test's disposable fixture only.
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'fixture reached corrected stage'):
                run(True)
            ready.assert_called_once()
            installed.assert_not_called()
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.stage.with_name(self.stage.name + '.resource-recovery.json').exists())

    def test_original_sysroot_stage_can_be_preserved_with_new_resource_helper_bound(self):
        self.expected['inputs'][recovery.RESOURCE_RECOVERY_INPUT] = 'f' * 64
        with self.builder_dispatch() as (run, ready, installed):
            with self.assertRaisesRegex(BuildError, 'fixture reached corrected stage'):
                run(True)
            ready.assert_called_once()
        retained = Path(recovery._read_json(self.journal)['retained'])
        self.assertEqual(recovery._inventory(retained), self.initial)
        self.assertEqual(recovery._read_json(self.stage / 'owner.json'), self.expected)

    def test_builder_reuses_verified_completed_current_stage(self):
        self.write_owner(self.expected)
        (self.stage / 'receipt.json').write_bytes(b'simulated verified receipt')
        before = recovery._inventory(self.stage)
        with self.builder_dispatch() as (run, ready, installed):
            run(True)
            ready.assert_not_called()
            installed.assert_called_once_with()
        self.assertEqual(recovery._inventory(self.stage), before)
        self.assertFalse(self.journal.exists())


if __name__ == '__main__':
    unittest.main()
