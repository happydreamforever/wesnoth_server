"""Preserving Python transition tests; subprocess installation is simulated here."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import alliance_dependencies as deps

ORIGINAL_ASSERT_WINDOWS_PYTHON = deps.assert_windows_python


class Python312TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='python312 transition ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'; (self.cache / 'wheels').mkdir(parents=True)
        self.mongo = self.root / 'mongo'; (self.mongo / 'bin').mkdir(parents=True)
        self.legacy = self.root / 'alliance-venv'; self.legacy.mkdir()
        (self.legacy / 'keep-python314.txt').write_bytes(b'old interpreter and credentials-free package fixture')
        self.target = self.root / 'alliance-venv-py312'
        self.journal = self.root / 'transition'
        files = {}
        for name in deps.MONGO_FILES:
            raw = name.encode(); (self.mongo / name).write_bytes(raw)
            files[name] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        raw = b'fixture-wheel'
        wheel = {'name': 'fixture', 'version': '1.0', 'filename': 'fixture-py3-none-any.whl',
                 'url': 'https://files.pythonhosted.org/fixture.whl', 'size': len(raw),
                 'sha256': hashlib.sha256(raw).hexdigest()}
        (self.cache / 'wheels' / wheel['filename']).write_bytes(raw)
        self.manifest = {'schema': 1, 'python': '3.12.10', 'platform': 'win_amd64', 'wheels': [wheel],
                         'mongodb': {'version': '8.0.32', 'filename': 'mongo.zip', 'sha256': 'a' * 64,
                                     'size': 807312757, 'files': files}}
        (self.mongo / 'alliance-owned.json').write_text(json.dumps({'owner': deps.OWNER,
            'archive_sha256': 'a' * 64, 'files': files}))
        self.addCleanup(patch.stopall)
        patch.object(deps, 'assert_windows_python').start()

    @contextmanager
    def mocked_processes(self):
        @contextmanager
        def stopped():
            yield
        def install(manifest, cache, venv, mongodb, **options):
            self.assertTrue(options['existing_mongodb'])
            (venv / 'Scripts').mkdir(parents=True, exist_ok=True)
            (venv / 'Scripts/python.exe').write_bytes(b'new Python 3.12 fixture')
            (venv / 'pyvenv.cfg').write_text('version = 3.12.10\n')
            fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            (venv / 'alliance-owned.json').write_text(json.dumps({'owner': deps.OWNER, 'manifest_sha256': fingerprint}))
        with patch.object(deps, 'stopped_services', stopped), patch.object(deps, 'install', side_effect=install), \
                patch.object(deps.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            yield

    def run_transition(self):
        return deps.install_python312(self.manifest, self.cache, self.target, self.mongo,
                                      self.legacy, self.journal)

    def test_runtime_guard_requires_exact_cpython31210_on_x64_windows(self):
        base = {'platform': 'win32', 'version_info': (3, 12, 10), 'maxsize': 2**63 - 1,
                'implementation': SimpleNamespace(name='cpython')}
        with patch.multiple(deps.sys, **base), patch.object(deps.platform, 'machine', return_value='AMD64'):
            ORIGINAL_ASSERT_WINDOWS_PYTHON()
            for key, value in (('platform', 'linux'), ('version_info', (3, 14, 3)),
                               ('maxsize', 2**31 - 1), ('implementation', SimpleNamespace(name='pypy'))):
                with self.subTest(key=key), patch.object(deps.sys, key, value):
                    with self.assertRaises(deps.PreparationError):
                        ORIGINAL_ASSERT_WINDOWS_PYTHON()
            with patch.object(deps.platform, 'machine', return_value='ARM64'):
                with self.assertRaises(deps.PreparationError):
                    ORIGINAL_ASSERT_WINDOWS_PYTHON()

    def test_three_abi_wheels_change_without_package_or_mongodb_upgrade(self):
        current = deps.load_manifest()
        old = deps.load_manifest(deps.PINS / 'windows-python314.json')
        self.assertEqual(current['python'], '3.12.10')
        self.assertEqual(old['python'], '3.14.3')
        self.assertEqual(current['mongodb'], old['mongodb'])
        self.assertEqual({r['name']: r['version'] for r in current['wheels']}, {r['name']: r['version'] for r in old['wheels']})
        changed = [a['name'] for a, b in zip(current['wheels'], old['wheels']) if a != b]
        self.assertEqual(changed, ['cffi', 'MarkupSafe', 'pymongo'])
        self.assertTrue(all('cp314' not in row['filename'] for row in current['wheels']))
        requirements = (deps.PINS / 'requirements-windows.txt').read_text()
        for row in current['wheels']:
            self.assertIn(row['name'] + '==' + row['version'] + ' --hash=sha256:' + row['sha256'], requirements)
        self.assertNotEqual(deps.VENV, deps.LEGACY_VENV)

    def test_prepare_existing_mongodb_never_requests_or_extracts_archive(self):
        before = deps.preservation_inventory(self.mongo)
        with patch.object(deps.urllib.request, 'urlopen', side_effect=AssertionError('no network')), \
                patch.object(deps, 'extract_mongodb', side_effect=AssertionError('no extraction')):
            deps.prepare_python312(self.manifest, self.cache, self.mongo)
        self.assertEqual(deps.preservation_inventory(self.mongo), before)
        self.assertFalse((self.cache / 'mongo.zip').exists())

    def test_prepare_downloads_only_missing_python_wheel(self):
        row = self.manifest['wheels'][0]
        (self.cache / 'wheels' / row['filename']).unlink()
        with patch.object(deps.urllib.request, 'urlopen', return_value=io.BytesIO(b'fixture-wheel')) as network:
            deps.prepare_python312(self.manifest, self.cache, self.mongo, download=True)
        self.assertEqual(network.call_args.args[0], row['url'])
        self.assertFalse((self.cache / 'mongo.zip').exists())

    def test_interrupted_publication_resumes_offline_without_partial_canonical_wheel(self):
        row = self.manifest['wheels'][0]
        destination = self.cache / 'wheels' / row['filename']; destination.unlink()
        before_mongo = deps.preservation_inventory(self.mongo)
        with patch.object(deps.urllib.request, 'urlopen', return_value=io.BytesIO(b'fixture-wheel')), \
                patch.object(deps, '_publish_artifact', side_effect=OSError('publication interrupted')):
            with self.assertRaisesRegex(OSError, 'publication interrupted'):
                deps.prepare_python312(self.manifest, self.cache, self.mongo, download=True)
        self.assertFalse(destination.exists())
        retained = list(destination.parent.glob(destination.name + '.download-*'))
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), b'fixture-wheel')
        with patch.object(deps.urllib.request, 'urlopen', side_effect=AssertionError('must resume offline')):
            deps.prepare_python312(self.manifest, self.cache, self.mongo)
        self.assertEqual(destination.read_bytes(), b'fixture-wheel')
        self.assertFalse(retained[0].exists())
        self.assertEqual(deps.preservation_inventory(self.mongo), before_mongo)

    def test_competing_artifact_is_never_overwritten(self):
        row = self.manifest['wheels'][0]
        destination = self.cache / 'wheels' / row['filename']; destination.unlink()
        publication = deps._publish_artifact
        def competing(partial, target, item):
            target.write_bytes(b'competing evidence')
            publication(partial, target, item)
        with patch.object(deps.urllib.request, 'urlopen', return_value=io.BytesIO(b'fixture-wheel')), \
                patch.object(deps, '_publish_artifact', side_effect=competing):
            with self.assertRaisesRegex(deps.PreparationError, 'appeared during publication'):
                deps.prepare_python312(self.manifest, self.cache, self.mongo, download=True)
        self.assertEqual(destination.read_bytes(), b'competing evidence')
        self.assertEqual(len(list(destination.parent.glob(destination.name + '.download-*'))), 1)

    def test_windows_publication_sharing_retry_is_bounded_and_retains_verified_bytes(self):
        row = self.manifest['wheels'][0]
        destination = self.cache / 'wheels' / row['filename']; destination.unlink()
        failure = OSError('fixture sharing violation'); failure.winerror = 32
        with patch.object(deps.urllib.request, 'urlopen', return_value=io.BytesIO(b'fixture-wheel')) as network, \
                patch.object(deps.sys, 'platform', 'win32'), \
                patch.object(deps.os, 'rename', side_effect=failure) as rename, \
                patch.object(deps.time, 'sleep') as sleep:
            with self.assertRaisesRegex(deps.PreparationError, 'Verified download retained'):
                deps.prepare_python312(self.manifest, self.cache, self.mongo, download=True)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(rename.call_count, len(deps.ARTIFACT_RENAME_DELAYS) + 1)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], list(deps.ARTIFACT_RENAME_DELAYS))
        self.assertFalse(destination.exists())
        self.assertEqual(len(list(destination.parent.glob(destination.name + '.download-*'))), 1)

    def test_unverified_interrupted_download_is_preserved_but_not_published(self):
        row = self.manifest['wheels'][0]
        destination = self.cache / 'wheels' / row['filename']; destination.unlink()
        partial = destination.with_name(destination.name + '.download-' + 'a' * 32)
        partial.write_bytes(b'partial')
        with patch.object(deps.urllib.request, 'urlopen', side_effect=AssertionError('offline')):
            with self.assertRaisesRegex(deps.PreparationError, 'missing'):
                deps.prepare_python312(self.manifest, self.cache, self.mongo)
        self.assertEqual(partial.read_bytes(), b'partial')
        self.assertFalse(destination.exists())

    def test_tampered_mongo_stops_before_downloading(self):
        (self.mongo / 'bin/mongod.exe').write_bytes(b'changed')
        with patch.object(deps.urllib.request, 'urlopen', side_effect=AssertionError('no network')):
            with self.assertRaises(deps.PreparationError):
                deps.prepare_python312(self.manifest, self.cache, self.mongo, download=True)

    def test_separate_environment_and_preservation_receipt(self):
        before = deps.preservation_inventory(self.legacy)
        with self.mocked_processes():
            self.run_transition()
        self.assertEqual(deps.preservation_inventory(self.legacy), before)
        self.assertTrue((self.target / 'Scripts/python.exe').is_file())
        complete = list(self.journal.glob('attempt-*/complete.json'))
        self.assertEqual(len(complete), 1)
        receipt = json.loads(complete[0].read_text())
        self.assertTrue(receipt['legacy_venv_preserved'])
        self.assertTrue(receipt['mongodb_preserved'])
        self.assertFalse(receipt['runtime_accessed'])
        self.assertFalse((self.journal / 'operation.lock').exists())

    def test_interrupted_install_can_resume_without_losing_old_files(self):
        with self.mocked_processes(), patch.object(deps, 'install', side_effect=subprocess.CalledProcessError(1, 'fixture')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_transition()
        self.assertTrue((self.journal / 'preserved-before.json').is_file())
        with self.mocked_processes():
            self.run_transition()
        self.assertEqual(len(list(self.journal.glob('attempt-*'))), 2)
        self.assertEqual(len(list(self.journal.glob('attempt-*/complete.json'))), 1)

    def test_changed_legacy_or_mongodb_between_attempts_stops(self):
        with self.mocked_processes(), patch.object(deps, 'install', side_effect=subprocess.CalledProcessError(1, 'fixture')):
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_transition()
        (self.legacy / 'keep-python314.txt').write_bytes(b'changed externally')
        with self.mocked_processes(), patch.object(deps, 'install') as install:
            with self.assertRaisesRegex(deps.PreparationError, 'changed since'):
                self.run_transition()
        install.assert_not_called()

    def test_wrong_journal_and_existing_lock_are_retained(self):
        self.journal.mkdir()
        owner = self.journal / 'owner.json'; owner.write_text('{}')
        with self.assertRaisesRegex(deps.PreparationError, 'another configuration'):
            self.run_transition()
        owner.unlink()
        lock = self.journal / 'operation.lock'; lock.write_text('{"pid":123,"nonce":"retained"}')
        with self.assertRaisesRegex(deps.PreparationError, 'operation lock'):
            self.run_transition()
        self.assertTrue(lock.exists())
        self.assertFalse(self.target.exists())

    def test_new_environment_cannot_overlap_preserved_old_tree(self):
        for target in (self.legacy, self.legacy / 'nested', self.legacy.parent):
            with self.subTest(target=target), self.assertRaisesRegex(deps.PreparationError, 'separate'):
                deps.install_python312(self.manifest, self.cache, target, self.mongo, self.legacy, self.journal)

    def test_transition_refuses_live_service_before_creating_new_venv(self):
        with patch.object(deps.socket.socket, 'bind', side_effect=OSError('occupied')):
            with self.assertRaisesRegex(deps.PreparationError, 'Stop all five'):
                self.run_transition()
        self.assertFalse(self.target.exists())

    def test_native_abi_check_runs_after_installed_verification(self):
        with self.mocked_processes(), patch.object(deps.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as process:
            self.run_transition()
        self.assertEqual([call.args[0][-1] for call in process.call_args_list], ['check-installed', 'check-native'])
        self.assertTrue(all(call.args[0][0] == str(self.target / 'Scripts/python.exe') for call in process.call_args_list))
        self.assertTrue(all(call.kwargs['check'] for call in process.call_args_list))

    def test_native_import_failure_prevents_success_receipt(self):
        def command(arguments, **options):
            if arguments[-1] == 'check-native':
                raise subprocess.CalledProcessError(1, arguments)
            return subprocess.CompletedProcess(arguments, 0)
        with self.mocked_processes(), patch.object(deps.subprocess, 'run', side_effect=command):
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_transition()
        self.assertEqual(list(self.journal.glob('attempt-*/complete.json')), [])
        self.assertTrue((self.legacy / 'keep-python314.txt').exists())

    def test_completed_transition_rechecks_without_reinstalling(self):
        with self.mocked_processes():
            self.run_transition()
        with self.mocked_processes(), patch.object(deps, 'install') as reinstall:
            self.run_transition()
        reinstall.assert_not_called()
        self.assertEqual(len(list(self.journal.glob('attempt-*/complete.json'))), 2)

    def test_foreign_or_mismatched_partial_environment_is_not_reinitialized(self):
        self.target.mkdir()
        keep = self.target / 'keep.txt'; keep.write_bytes(b'unrelated files')
        with self.mocked_processes(), patch.object(deps, 'install') as install:
            with self.assertRaisesRegex(deps.PreparationError, 'another owner'):
                self.run_transition()
        install.assert_not_called()
        fingerprint = hashlib.sha256(json.dumps(self.manifest, sort_keys=True).encode()).hexdigest()
        (self.target / 'alliance-owned.json').write_text(json.dumps({'owner': deps.OWNER, 'manifest_sha256': fingerprint}))
        (self.target / 'pyvenv.cfg').write_text('version = 3.14.3\n')
        with self.mocked_processes(), patch.object(deps, 'install') as install:
            with self.assertRaisesRegex(deps.PreparationError, 'another interpreter'):
                self.run_transition()
        install.assert_not_called()
        self.assertEqual(keep.read_bytes(), b'unrelated files')


    def test_paths_refuse_redirected_wheel_cache(self):
        target = self.cache / 'wheels' / self.manifest['wheels'][0]['filename']
        target.unlink(); target.symlink_to(self.legacy / 'keep-python314.txt')
        with self.assertRaisesRegex(deps.PreparationError, 'links'):
            deps.prepare_python312(self.manifest, self.cache, self.mongo)


if __name__ == '__main__':
    unittest.main()
