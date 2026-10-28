"""Bounded read-only metadata fixtures; native Win32 access execution is separate."""
import base64
from copy import deepcopy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import inspect_world_worker_ninja as inspector


class FileAPI:
    def __init__(self, denied=None, close_error=0):
        self.denied = denied or {}
        self.close_error = close_error
        self.calls = []
        self.closed = []
        self.last_error = 0

    def create(self, *arguments):
        self.calls.append(arguments)
        self.last_error = self.denied.get(arguments[1], 0)
        return ctypes.c_void_p(-1).value if self.last_error else len(self.calls) + 100

    def close(self, handle):
        self.closed.append(handle)
        self.last_error = self.close_error
        return not self.close_error

    def error(self):
        return self.last_error


class NinjaInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        (self.repo / 'tools').mkdir()
        (self.repo / 'diagnostics').mkdir()
        self.stage = self.repo / 'build' / 'windows-world-worker'
        self.engine = self.stage / 'engine'
        self.engine.mkdir(parents=True)
        self.log = self.engine / '.ninja_log'
        self.log.write_bytes(b'# ninja log v7\n0\t4\t123\tCMakeFiles/wesnoth.dir/main.cpp.obj\t0123456789abcdef\n')
        (self.engine / '.ninja_log.restat').write_bytes(self.log.read_bytes())
        (self.engine / '.ninja_deps').write_bytes(b'# ninjadeps\n\x04\x00\x00\x00')
        (self.engine / 'build.ninja').write_bytes(b'build world-worker.exe: link main.obj\n')
        self.owner = {'format': 1, 'purpose': 'wesnoth-full-native-world-worker', 'release': 1192624,
                      'inputs': {}}
        for name in inspector.SOURCE_NAMES:
            raw = ('source sentinel ' + name).encode()
            (self.repo / 'tools' / name).write_bytes(raw)
            self.owner['inputs']['wesnoth_server/tools/' + name] = hashlib.sha256(raw).hexdigest()
        (self.stage / 'owner.json').write_text(json.dumps(self.owner), encoding='utf-8')
        self.journal = self.stage.with_name(self.stage.name + '.resource-recovery.json')
        rows = {}
        for name in inspector.FILE_NAMES:
            path = self.engine / name
            if path.exists():
                info = path.stat()
                rows['engine/' + name] = {'bytes': info.st_size,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mtime_ns': info.st_mtime_ns,
                    'mode': info.st_mode, 'attributes': getattr(info, 'st_file_attributes', 0)}
        self.record = {'format': 1, 'purpose': 'wesnoth-world-worker-resource-recovery',
                       'stage': str(self.stage), 'expected_binding': self.owner,
                       'inventory': {'files': rows}}
        self.journal.write_text(json.dumps(self.record), encoding='utf-8')

    def probe(self, path, *, directory=False):
        return inspector.probe_access(path, directory=directory, _api=FileAPI())

    def collect(self):
        return inspector.collect(self.repo, access_probe=self.probe)

    def snapshot(self):
        result = {}
        for path in self.repo.rglob('*'):
            if path.is_file():
                info = path.stat()
                result[path.relative_to(self.repo).as_posix()] = (path.read_bytes(), info.st_mtime_ns,
                    info.st_mode, info.st_nlink, getattr(info, 'st_file_attributes', 0))
        return result

    def test_capture_is_repeatable_and_preserves_all_existing_bytes_and_metadata(self):
        before = self.snapshot()
        first = self.collect()
        second = self.collect()
        self.assertTrue(first['collection']['complete'])
        self.assertEqual(first['format'], 1)
        self.assertEqual(first['purpose'], 'wesnoth-world-worker-ninja-state')
        self.assertEqual(first['files'], second['files'])
        self.assertEqual(first['checks'], second['checks'])
        self.assertEqual(self.snapshot(), before)
        captured = first['files']['.ninja_log']
        self.assertEqual(base64.b64decode(captured['raw']['data']), self.log.read_bytes())
        self.assertEqual(captured['sha256'], hashlib.sha256(self.log.read_bytes()).hexdigest())
        self.assertTrue(captured['matches_before_configuration'])
        self.assertEqual(first['files']['.ninja_log.recompact']['status'], 'missing')
        self.assertNotIn('raw', first['files']['.ninja_deps'])
        self.assertNotIn('raw', first['files']['build.ninja'])
        self.assertTrue(first['checks']['resource_journal']['expected_binding_matches_owner'])
        self.assertTrue(all(row['matches'] for row in first['checks']['ownership']['sources'].values()))

    def test_access_opens_are_existing_non_inherited_share_all_and_immediately_closed(self):
        api = FileAPI()
        before = self.snapshot()
        row = inspector.probe_access(self.log, _api=api)
        self.assertEqual(row['status'], 'observed')
        self.assertEqual(len(api.calls), 4)
        self.assertEqual(api.closed, [101, 102, 103, 104])
        for call, access in zip(api.calls, inspector.FILE_ACCESS.values()):
            self.assertEqual(call, (str(self.log), access, 7, None, 3, inspector.OPEN_REPARSE_POINT, None))
            self.assertFalse(call[5] & 0x04000000)  # FILE_FLAG_DELETE_ON_CLOSE is forbidden.
        self.assertEqual(self.snapshot(), before)

    def test_directory_access_uses_existing_directory_handle_without_creating_child(self):
        api = FileAPI()
        before = self.snapshot()
        row = inspector.probe_access(self.engine, directory=True, _api=api)
        self.assertEqual(row['status'], 'observed')
        self.assertEqual([call[1] for call in api.calls], [0, 2, 0x40])
        self.assertTrue(all(call[4] == 3 and call[5] == (
            inspector.OPEN_REPARSE_POINT | inspector.BACKUP_SEMANTICS) for call in api.calls))
        self.assertEqual(len(api.closed), 3)
        self.assertEqual(self.snapshot(), before)

    def test_native_error_codes_are_observations_not_build_health(self):
        for code in (5, 32, 33, 19, 9999):
            with self.subTest(winerror=code):
                api = FileAPI({0x40000000: code, 0x10000: code})
                row = inspector.probe_access(self.log, _api=api)
                self.assertEqual(row['status'], 'observed')
                self.assertFalse(row['probes']['write']['opened'])
                self.assertEqual(row['probes']['write']['winerror'], code)
                self.assertEqual(row['probes']['delete']['winerror'], code)
                self.assertEqual(len(api.closed), 2)
        def blocked(path, *, directory=False):
            return inspector.probe_access(path, directory=directory,
                _api=FileAPI({0x40000000: 32, 0x10000: 32, 2: 5, 0x40: 5}))
        report = inspector.collect(self.repo, access_probe=blocked)
        self.assertTrue(report['collection']['complete'])
        self.assertNotIn('build_passed', report)

    def test_close_failure_is_reported_separately_and_collection_incomplete(self):
        def cannot_close(path, *, directory=False):
            return inspector.probe_access(path, directory=directory, _api=FileAPI(close_error=6))
        report = inspector.collect(self.repo, access_probe=cannot_close)
        self.assertFalse(report['collection']['complete'])
        row = report['files']['.ninja_log']['access']
        self.assertEqual(row['status'], 'close_error')
        self.assertEqual(row['probes']['read']['close_error'], 6)

    def test_missing_log_remains_valid_observation_and_is_never_created(self):
        self.log.unlink()
        before = self.snapshot()
        report = self.collect()
        self.assertTrue(report['collection']['complete'])
        self.assertEqual(report['files']['.ninja_log'], {'status': 'missing'})
        api = FileAPI()
        self.assertEqual(inspector.probe_access(self.log, _api=api), {'status': 'missing'})
        self.assertEqual(api.calls, [])
        self.assertEqual(self.snapshot(), before)

    def test_missing_stage_is_incomplete_without_created_stage(self):
        new_repo = self.repo / 'new-repo'
        new_repo.mkdir()
        report = inspector.collect(new_repo, access_probe=self.probe)
        self.assertFalse(report['collection']['complete'])
        self.assertFalse((new_repo / 'build').exists())

    def test_raw_size_bound_omits_only_raw_but_full_file_bound_stops_read(self):
        before = self.snapshot()
        with patch.object(inspector, 'MAX_RAW_BYTES', 8):
            row = inspector.inspect_file(self.log, include_raw=True, access_probe=self.probe)
            self.assertEqual(row['status'], 'present')
            self.assertEqual(row['raw']['status'], 'omitted_size_limit')
            self.assertEqual(row['sha256'], hashlib.sha256(self.log.read_bytes()).hexdigest())
            self.assertFalse(self.collect()['collection']['complete'])
        with patch.object(inspector, 'MAX_BYTES', 8), patch.object(os, 'open') as opened:
            row = inspector.inspect_file(self.log, include_raw=True, access_probe=self.probe)
            self.assertEqual(row['status'], 'too_large')
            opened.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_read_access_failure_retains_metadata_and_native_probe_codes(self):
        error = PermissionError(13, 'sensitive exception text must not be reported')
        error.winerror = 5
        with patch.object(os, 'open', side_effect=error):
            row = inspector.inspect_file(self.log, include_raw=True, access_probe=self.probe)
        self.assertEqual(row['status'], 'read_error')
        self.assertEqual(row['error']['winerror'], 5)
        self.assertEqual(row['bytes'], self.log.stat().st_size)
        self.assertEqual(row['access']['status'], 'observed')
        self.assertNotIn('sensitive', json.dumps(row))

    def test_symbolic_links_hardlinks_and_redirected_ancestors_are_rejected(self):
        outside = self.repo / 'outside'
        outside.write_bytes(b'private sentinel')
        self.log.unlink()
        self.log.symlink_to(outside)
        row = inspector.inspect_file(self.log, include_raw=True, access_probe=self.probe)
        self.assertEqual(row['status'], 'read_error')
        self.assertNotIn('raw', row)
        self.log.unlink()
        os.link(outside, self.log)
        self.assertEqual(inspector.inspect_file(self.log, access_probe=self.probe)['status'], 'rejected')
        alias = self.repo / 'redirected'
        alias.symlink_to(self.engine, target_is_directory=True)
        with self.assertRaises(inspector.InspectionError): inspector.checked_path(alias / 'build.ninja')
        self.assertEqual(outside.read_bytes(), b'private sentinel')

    def test_windows_reparse_attributes_stop_before_open(self):
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.log:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, 'lstat', reparse), patch.object(os, 'open') as opened:
            row = inspector.inspect_file(self.log, include_raw=True, access_probe=self.probe)
            self.assertEqual(row['status'], 'read_error')
            opened.assert_not_called()

    def test_file_changed_during_probe_is_not_a_stable_snapshot(self):
        api = FileAPI()
        original = api.close
        def changed(handle):
            os.utime(self.log, ns=(1, self.log.stat().st_mtime_ns + 1))
            return original(handle)
        api.close = changed
        self.assertEqual(inspector.probe_access(self.log, _api=api)['status'], 'changed')

    def test_duplicate_or_invalid_owned_metadata_is_incomplete(self):
        for raw in (b'{"format":1,"format":1}', b'[]', b'{bad json'):
            with self.subTest(raw=raw):
                (self.stage / 'owner.json').write_bytes(raw)
                report = self.collect()
                self.assertFalse(report['collection']['complete'])
                self.assertIn(report['checks']['ownership']['status'], ('invalid_json', 'invalid_binding'))

    def test_changed_sources_are_recorded_without_claiming_build_corruption(self):
        (self.repo / 'tools' / inspector.SOURCE_NAMES[0]).write_bytes(b'current changed source')
        report = self.collect()
        self.assertTrue(report['collection']['complete'])
        self.assertFalse(report['checks']['ownership']['sources'][inspector.SOURCE_NAMES[0]]['matches'])
        self.assertNotIn('raw', report['checks']['ownership'])

    def test_journal_reports_only_selected_engine_rows_and_comparison(self):
        self.record['inventory']['files']['private/path'] = {'password': 'not-to-be-reported'}
        self.journal.write_text(json.dumps(self.record), encoding='utf-8')
        (self.engine / '.ninja_log.restat').write_bytes(b'new restat contents')
        report = self.collect()
        self.assertTrue(report['collection']['complete'])
        self.assertEqual(set(report['checks']['resource_journal']['files']), set(inspector.FILE_NAMES))
        self.assertFalse(report['files']['.ninja_log.restat']['matches_before_configuration'])
        self.assertNotIn('not-to-be-reported', json.dumps(report))
        self.assertNotIn('original_owner_hex', json.dumps(report))

    def test_malformed_journal_is_incomplete_and_missing_journal_is_observation(self):
        self.journal.write_text(json.dumps({'format': 1}), encoding='utf-8')
        self.assertFalse(self.collect()['collection']['complete'])
        self.journal.unlink()
        report = self.collect()
        self.assertTrue(report['collection']['complete'])
        self.assertEqual(report['checks']['resource_journal']['status'], 'missing')

    def test_report_creation_is_exclusive_and_only_inside_diagnostics(self):
        report = self.collect()
        destination = self.repo / 'diagnostics' / 'new.json'
        before = self.snapshot()
        inspector.write_report(self.repo, destination, report)
        self.assertEqual(json.loads(destination.read_text()), report)
        after = self.snapshot()
        after.pop('diagnostics/new.json')
        self.assertEqual(after, before)
        original = destination.read_bytes()
        with self.assertRaises(FileExistsError): inspector.write_report(self.repo, destination, {})
        self.assertEqual(destination.read_bytes(), original)
        for path in (self.stage / 'report.json', self.repo / 'diagnostics' / 'report.txt'):
            with self.subTest(path=path), self.assertRaises(inspector.InspectionError):
                inspector.write_report(self.repo, path, report)
            self.assertFalse(path.exists())

    def test_report_symlink_is_never_followed_or_overwritten(self):
        target = self.repo / 'outside-report'
        target.write_bytes(b'preserved')
        destination = self.repo / 'diagnostics' / 'linked.json'
        destination.symlink_to(target)
        with self.assertRaises(inspector.InspectionError): inspector.write_report(self.repo, destination, {})
        self.assertEqual(target.read_bytes(), b'preserved')
        self.assertTrue(destination.is_symlink())

    def test_main_reports_complete_collection_and_incomplete_without_build_tools(self):
        import contextlib
        import io
        for complete in (True, False):
            destination = self.repo / 'diagnostics' / ('status-' + str(complete) + '.json')
            report = {'format': 1, 'purpose': inspector.PURPOSE, 'collection': {'complete': complete}}
            output = io.StringIO()
            with patch.object(inspector, 'ROOT', self.repo), patch.object(inspector.sys, 'platform', 'win32'), \
                    patch.object(inspector.sys, 'version_info', (3, 12, 10)), \
                    patch.object(inspector.sys, 'argv', ['inspect', '--report', str(destination)]), \
                    patch.object(inspector, 'collect', return_value=report), contextlib.redirect_stdout(output):
                self.assertEqual(inspector.main(), 0 if complete else 1)
            self.assertEqual(json.loads(destination.read_text()), report)
            self.assertIn('No build or recovery was performed', output.getvalue())
            self.assertIn('STATE COLLECTED' if complete else 'COLLECTION INCOMPLETE', output.getvalue())


if __name__ == '__main__':
    unittest.main()
