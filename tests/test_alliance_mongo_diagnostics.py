"""MongoDB diagnostic retention; native Windows subprocesses are simulated.

Dump payloads are synthetic. P2 tests prohibit opening them, while P3 verifies
the complete retained installation inventory, including those private bytes.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import alliance_dependencies as deps
from tests import test_alliance_python312 as fixtures


DUMPS = (('mongod.2026-10-19T19-37-33.mdmp', 517241),
         ('mongod.2026-10-20T04-02-35.mdmp', 523111))


class MongoDiagnosticRetentionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.Python312TransitionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for name in ('root', 'cache', 'mongo', 'manifest', 'legacy', 'target', 'journal'):
            setattr(self, name, getattr(self.fixture, name))
        self.dump_paths = []
        for name, size in DUMPS:
            path = self.mongo / 'bin' / name
            path.write_bytes(b'X' * size)
            self.dump_paths.append(path)

    def snapshot(self, **options):
        return deps._mongodb_tree_snapshot(self.mongo, self.manifest['mongodb'], **options)

    @contextmanager
    def no_dump_reads(self):
        original = Path.open; unlink = Path.unlink; rename = Path.rename
        def guarded(path, *args, **kwargs):
            if path.suffix == '.mdmp':
                raise AssertionError('P2 must not open crash-dump contents')
            return original(path, *args, **kwargs)
        def no_unlink(path, *args, **kwargs):
            if path.suffix == '.mdmp':
                raise AssertionError('P2 must not delete crash dumps')
            return unlink(path, *args, **kwargs)
        def no_rename(path, *args, **kwargs):
            if path.suffix == '.mdmp':
                raise AssertionError('P2 must not rename crash dumps')
            return rename(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded), patch.object(Path, 'unlink', no_unlink), \
                patch.object(Path, 'rename', no_rename):
            yield

    @contextmanager
    def native_process_boundary(self, *, fail_pip_check=False):
        """Execute production install control flow; simulate external binaries only."""
        def run(arguments, **options):
            if arguments == [str(self.mongo / 'bin/mongod.exe'), '--version']:
                return subprocess.CompletedProcess(arguments, 0, stdout='db version v8.0.32\n', stderr='')
            if '-m' in arguments and arguments[arguments.index('-m') + 1] == 'venv':
                scripts = self.target / 'Scripts'; scripts.mkdir(exist_ok=True)
                (scripts / 'python.exe').write_bytes(b'new Python 3.12 fixture executable')
                (self.target / 'pyvenv.cfg').write_text('version = 3.12.10\n')
            if fail_pip_check and arguments[-2:] == ['pip', 'check']:
                raise subprocess.CalledProcessError(1, arguments)
            return subprocess.CompletedProcess(arguments, 0, stdout='', stderr='')
        @contextmanager
        def stopped():
            yield
        with patch.object(deps, 'stopped_services', stopped), \
                patch.object(deps.subprocess, 'run', side_effect=run) as calls:
            yield calls

    def transition(self):
        deps.install_python312(self.manifest, self.cache, self.target, self.mongo,
                               self.legacy, self.journal)

    def test_p2_accepts_both_reported_dumps_without_reading_or_mutating_them(self):
        before = deps.preservation_inventory(self.mongo)
        with self.no_dump_reads(), \
                patch.object(deps.urllib.request, 'urlopen', side_effect=AssertionError('P2 is offline')), \
                patch.object(deps, 'extract_mongodb', side_effect=AssertionError('must retain installed MongoDB')):
            deps.prepare_python312(self.manifest, self.cache, self.mongo)
            snapshot = self.snapshot(allow_crash_dumps=True)
        self.assertEqual(deps.preservation_inventory(self.mongo), before)
        for name, _ in DUMPS:
            self.assertIn('bin/' + name, snapshot)
        self.assertFalse((self.cache / self.manifest['mongodb']['filename']).exists())

    def test_actual_install_reuses_dump_bearing_mongodb(self):
        before = deps.preservation_inventory(self.mongo)
        with self.native_process_boundary() as calls, \
                patch.object(deps, 'extract_mongodb', side_effect=AssertionError('no extraction')):
            deps.install(self.manifest, self.cache, self.target, self.mongo, existing_mongodb=True)
        self.assertEqual(calls.call_args_list[0].args[0], [str(self.mongo / 'bin/mongod.exe'), '--version'])
        self.assertTrue(any(call.args[0][-2:] == ['pip', 'check'] for call in calls.call_args_list))
        self.assertEqual(deps.preservation_inventory(self.mongo), before)
        self.assertTrue((self.target / 'alliance-owned.json').is_file())

    def test_existing_extraction_reuse_accepts_dumps_without_opening_zip(self):
        archive = self.cache / self.manifest['mongodb']['filename']
        raw = b'archive fixture is not opened on existing-install reuse'
        archive.write_bytes(raw)
        item = self.manifest['mongodb']
        item.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        marker = self.mongo / 'alliance-owned.json'
        receipt = json.loads(marker.read_text()); receipt['archive_sha256'] = item['sha256']
        marker.write_text(json.dumps(receipt))
        before = deps.preservation_inventory(self.mongo)
        with self.no_dump_reads(), patch.object(deps.zipfile, 'ZipFile', side_effect=AssertionError('no extraction')):
            self.assertEqual(deps.extract_mongodb(self.manifest, self.cache, self.mongo), self.mongo / 'bin/mongod.exe')
        self.assertEqual(deps.preservation_inventory(self.mongo), before)

    def test_fresh_snapshot_and_publication_still_reject_dumps(self):
        before = deps.preservation_inventory(self.mongo)
        with self.assertRaises(deps.PreparationError):
            self.snapshot()
        with patch.object(Path, 'rename', side_effect=AssertionError('must not publish')):
            with self.assertRaises(deps.PreparationError):
                deps._publish_mongodb(self.mongo, self.root / 'fresh', self.manifest['mongodb'])
        self.assertFalse((self.root / 'fresh').exists())
        self.assertEqual(deps.preservation_inventory(self.mongo), before)

    def test_unknown_executable_dll_arbitrary_dump_and_top_level_dump_are_rejected(self):
        additions = ('bin/unexpected.dll', 'bin/unexpected.exe', 'bin/arbitrary.mdmp',
                     'mongod.2026-10-19T19-37-33.mdmp')
        for relative in additions:
            with self.subTest(relative=relative):
                path = self.mongo / relative; path.write_bytes(b'preserve unexpected evidence')
                try:
                    with self.assertRaises(deps.PreparationError):
                        self.snapshot(allow_crash_dumps=True)
                    self.assertEqual(path.read_bytes(), b'preserve unexpected evidence')
                finally:
                    path.unlink()

    def test_dump_filename_requires_ascii_exact_shape_and_valid_calendar(self):
        invalid = ('mongod.2026-02-29T00-00-00.mdmp', 'mongod.2024-02-30T00-00-00.mdmp',
                   'mongod.2026-13-01T00-00-00.mdmp', 'mongod.2026-10-19T24-00-00.mdmp',
                   'mongod.2026-10-19T00-60-00.mdmp', 'mongod.2026-10-19T00-00-60.mdmp',
                   'mongod.２０２６-10-19T19-37-33.mdmp', 'mongod.2026-1-19T19-37-33.mdmp',
                   'mongod.2026-10-19T19-37-33.MDMP', 'mongod.2026-10-19T19-37-33.mdmp.exe')
        for name in invalid:
            with self.subTest(name=name):
                path = self.mongo / 'bin' / name; path.write_bytes(b'invalid diagnostic fixture')
                try:
                    with self.assertRaises(deps.PreparationError):
                        self.snapshot(allow_crash_dumps=True)
                finally:
                    path.unlink()
        leap = self.mongo / 'bin/mongod.2024-02-29T23-59-59.mdmp'
        leap.write_bytes(b'valid leap day fixture')
        self.snapshot(allow_crash_dumps=True)

    def test_dump_named_directory_is_rejected(self):
        path = self.mongo / 'bin/mongod.2026-10-21T00-00-00.mdmp'; path.mkdir()
        with self.assertRaises(deps.PreparationError):
            self.snapshot(allow_crash_dumps=True)
        self.assertTrue(path.is_dir())

    def test_dump_symlink_and_hardlink_are_rejected_and_preserved(self):
        for kind in ('symlink', 'hardlink'):
            with self.subTest(kind=kind):
                path = self.mongo / 'bin/mongod.2026-10-21T00-00-00.mdmp'
                if kind == 'symlink':
                    path.symlink_to(self.dump_paths[0])
                else:
                    os.link(self.dump_paths[0], path)
                try:
                    with self.assertRaises(deps.PreparationError):
                        self.snapshot(allow_crash_dumps=True)
                    self.assertTrue(path.exists())
                finally:
                    path.unlink()

    def test_windows_reparse_dump_is_rejected_without_reading_it(self):
        original = Path.lstat
        def reparse(path):
            value = original(path)
            if path == self.dump_paths[0]:
                fields = {key: getattr(value, key) for key in dir(value) if key.startswith('st_')}
                fields['st_file_attributes'] = 0x400
                return SimpleNamespace(**fields)
            return value
        with patch.object(Path, 'lstat', reparse), self.no_dump_reads():
            with self.assertRaises(deps.PreparationError):
                self.snapshot(allow_crash_dumps=True)

    def test_required_file_hash_is_still_verified_with_diagnostics_present(self):
        target = self.mongo / 'bin/mongod.exe'; target.write_bytes(b'changed native executable')
        with self.assertRaises(deps.PreparationError):
            self.snapshot(allow_crash_dumps=True)
        self.assertEqual(target.read_bytes(), b'changed native executable')

    def test_ownership_receipt_changes_are_still_rejected(self):
        target = self.mongo / 'alliance-owned.json'
        receipt = json.loads(target.read_text()); receipt['unapproved'] = True
        target.write_text(json.dumps(receipt))
        with self.assertRaises(deps.PreparationError):
            self.snapshot(allow_crash_dumps=True)
        self.assertTrue(json.loads(target.read_text())['unapproved'])

    def test_dump_change_during_pinned_file_verification_is_detected(self):
        original = deps.verify; changed = False
        def changing(path, item):
            nonlocal changed
            result = original(path, item)
            if not changed:
                self.dump_paths[0].write_bytes(b'changed while snapshot was in progress'); changed = True
            return result
        with patch.object(deps, 'verify', side_effect=changing):
            with self.assertRaises(deps.PreparationError):
                self.snapshot(allow_crash_dumps=True)
        self.assertTrue(changed)

    def test_directory_set_change_during_verification_is_detected(self):
        original = deps.verify
        for action in ('add', 'remove'):
            with self.subTest(action=action):
                created = self.mongo / 'bin/mongod.2026-10-21T00-00-00.mdmp'
                removed = self.dump_paths[1]; original_bytes = removed.read_bytes(); changed = False
                def changing(path, item):
                    nonlocal changed
                    result = original(path, item)
                    if not changed:
                        if action == 'add':
                            created.write_bytes(b'new dump during verification')
                        else:
                            removed.unlink()
                        changed = True
                    return result
                try:
                    with patch.object(deps, 'verify', side_effect=changing):
                        with self.assertRaises((deps.PreparationError, FileNotFoundError)):
                            self.snapshot(allow_crash_dumps=True)
                    self.assertTrue(changed)
                finally:
                    created.unlink(missing_ok=True)
                    if not removed.exists():
                        removed.write_bytes(original_bytes)

    def test_p3_preservation_receipts_include_dumps_and_completed_reuse_skips_install(self):
        before = deps.preservation_inventory(self.mongo)
        with self.native_process_boundary(), patch.object(deps, 'extract_mongodb', side_effect=AssertionError('no extraction')):
            self.transition()
        saved = json.loads((self.journal / 'preserved-before.json').read_text())['mongodb']
        self.assertEqual(saved, before)
        for name, size in DUMPS:
            self.assertEqual(saved['files']['bin/' + name]['size'], size)
            self.assertEqual(saved['files']['bin/' + name]['sha256'], hashlib.sha256(b'X' * size).hexdigest())
        with self.native_process_boundary() as calls:
            self.transition()
        self.assertEqual([call.args[0][-1] for call in calls.call_args_list], ['check-installed', 'check-native'])
        self.assertEqual(len(list(self.journal.glob('attempt-*/complete.json'))), 2)
        self.assertEqual(deps.preservation_inventory(self.mongo), before)

    def test_p3_interruption_resumes_with_original_diagnostic_bytes(self):
        before = deps.preservation_inventory(self.mongo)
        with self.native_process_boundary(fail_pip_check=True):
            with self.assertRaises(subprocess.CalledProcessError):
                self.transition()
        self.assertEqual(list(self.journal.glob('attempt-*/complete.json')), [])
        with self.native_process_boundary():
            self.transition()
        self.assertEqual(len(list(self.journal.glob('attempt-*/complete.json'))), 1)
        self.assertEqual(deps.preservation_inventory(self.mongo), before)

    def test_p3_changed_diagnostic_after_interruption_blocks_resume(self):
        with self.native_process_boundary(fail_pip_check=True):
            with self.assertRaises(subprocess.CalledProcessError):
                self.transition()
        self.dump_paths[0].write_bytes(b'changed after interrupted transition')
        with self.native_process_boundary() as calls:
            with self.assertRaisesRegex(deps.PreparationError, 'changed since'):
                self.transition()
        calls.assert_not_called()
        self.assertEqual(list(self.journal.glob('attempt-*/complete.json')), [])


if __name__ == '__main__':
    unittest.main()
