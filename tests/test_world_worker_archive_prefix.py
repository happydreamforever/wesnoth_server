"""Real zstd/tar extraction fixtures; no simulated Windows package install."""
from contextlib import redirect_stdout
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import world_worker_archive_prefix as archive
from tools import world_worker_dependencies as deps
from tools import world_worker_packages as packages


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ArchivePrefix(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='world archive prefix ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'; self.cache.mkdir()
        self.prefix = self.root / 'prefix'
        self.lock = self.root / 'packages.json'
        self.pins = []; self.files = {}
        self.add_package('compiler', {'bin/c++.exe': b'MZ fixture compiler', 'share/empty': b''},
                         links={'bin/g++.exe': 'bin/c++.exe'})
        self.write_manifest()

    def add_package(self, short, files, *, links=None, extras=None, pkginfo_change=None,
                    mtree_change=None, special=None):
        name = 'mingw-w64-x86_64-' + short; links = links or {}; extras = extras or {}
        info = f'pkgname = {name}\npkgver = 1-1\narch = any\n'.encode()
        if pkginfo_change:
            info = pkginfo_change(info)
        data = {'.BUILDINFO': b'fixture build metadata\n', '.PKGINFO': info,
                **{'mingw64/' + k: v for k, v in files.items()}, **extras}
        aliases = {'mingw64/' + k: 'mingw64/' + v for k, v in links.items()}
        directories = set()
        for path in [*data, *aliases]:
            directories.update(x.as_posix() for x in Path(path).parents if x.as_posix() != '.')
        mtree = ['#mtree', '/set type=file uid=0 gid=0 mode=644']
        for path in sorted(directories):
            mtree.append('./' + path + ' type=dir')
        for path, raw in sorted(data.items()):
            mtree.append(f'./{path} size={len(raw)} sha256digest={sha(raw)}')
        for path, target in sorted(aliases.items()):
            raw = data.get(target, b'absent')
            mtree.append(f'./{path} size={len(raw)} sha256digest={sha(raw)}')
        if mtree_change:
            mtree = mtree_change(mtree)
        compressed = gzip.compress(('\n'.join(mtree) + '\n').encode(), mtime=0)
        filename = name + '-1-1-any.pkg.tar.zst'; path = self.cache / filename
        with tarfile.open(path, 'w:zst') as output:
            for key, raw in [('.BUILDINFO', data.pop('.BUILDINFO')), ('.MTREE', compressed), *sorted(data.items())]:
                entry = tarfile.TarInfo(key); entry.size = len(raw)
                output.addfile(entry, io.BytesIO(raw))
            for key in sorted(directories):
                entry = tarfile.TarInfo(key); entry.type = tarfile.DIRTYPE
                output.addfile(entry)
            for key, target in aliases.items():
                entry = tarfile.TarInfo(key); entry.type = tarfile.LNKTYPE; entry.linkname = target
                output.addfile(entry)
            if special:
                output.addfile(special)
        signature = b'fixture detached signature; cryptographic verification belongs to cache helper'
        Path(str(path) + '.sig').write_bytes(signature)
        pin = {'name': name, 'version': '1-1', 'filename': filename, 'size': path.stat().st_size,
               'sha256': sha(path.read_bytes()), 'mtree_sha256': sha(compressed),
               'signature': {'size': len(signature), 'sha256': sha(signature)},
               'depends': [], 'provides': [], 'conflicts': [], 'replaces': []}
        self.pins.append(pin)
        for key, raw in files.items():
            self.files[key] = {'bytes': len(raw), 'sha256': sha(raw)}
        for key, target in links.items():
            raw = files.get(target, b'absent')
            self.files[key] = {'bytes': len(raw), 'sha256': sha(raw)}
        return pin

    def write_manifest(self):
        value = {'format': 1, 'purpose': packages.PURPOSE, 'release': 1192624,
                 'source': {'repository': packages.REPOSITORY, 'prefix_files_sha256': archive.canonical_hash(self.files)},
                 'roots': [x['name'] for x in self.pins],
                 'baseline': [{'name': self.pins[0]['name'], 'version': '1-1'}], 'packages': self.pins}
        self.lock.write_text(json.dumps(value))

    def prepare(self):
        with redirect_stdout(io.StringIO()):
            return archive.prepare_archive_prefix(self.lock, self.cache, self.prefix)

    def verify(self):
        return archive.verify_archive_inputs(self.lock, self.cache)

    def test_real_zstd_exact_files_hardlinks_become_independent_and_reuse(self):
        expected = self.verify()
        self.assertEqual(self.prepare(), self.prefix)
        self.assertEqual(archive.verify_locked_prefix(self.prefix, self.lock), expected)
        self.assertEqual(self.prepare(), self.prefix)
        for path in self.prefix.rglob('*'):
            if path.is_file():
                self.assertEqual(path.stat().st_nlink, 1)
        one = self.prefix / 'bin/c++.exe'; two = self.prefix / 'bin/g++.exe'
        self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertNotEqual(one.stat().st_ino, two.stat().st_ino)
        self.assertEqual((self.prefix / 'share/empty').stat().st_size, 0)

    def test_scripts_and_reviewed_hooks_are_validated_but_not_extracted_or_run(self):
        self.add_package('fontconfig', {'bin/fc-cache.exe': b'fixture'}, extras={
            '.INSTALL': b'NEVER EXECUTE THIS',
            'usr/share/libalpm/hooks/mingw-w64-x86_64-fontconfig.hook': b'fixture hook'})
        self.write_manifest(); self.prepare()
        self.assertFalse((self.prefix / '.INSTALL').exists())
        self.assertFalse((self.prefix / 'usr').exists())
        self.assertTrue((self.prefix / 'bin/fc-cache.exe').exists())

    def test_archive_and_signature_tampering_stop_before_prefix_creation(self):
        path = self.cache / self.pins[0]['filename']; original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(deps.BuildError):
            self.prepare()
        self.assertFalse(self.prefix.exists())
        path.write_bytes(original); Path(str(path) + '.sig').write_bytes(b'changed signature')
        with self.assertRaises(deps.BuildError):
            self.prepare()
        self.assertFalse(self.prefix.exists())

    def test_pkginfo_and_pinned_mtree_disagreement_rejected(self):
        self.add_package('bad-identity', {'bin/example': b'x'}, pkginfo_change=lambda b: b.replace(b'arch = any', b'arch = other'))
        self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'identity'):
            self.verify()
        self.pins.pop(); self.write_manifest(); self.pins[0]['mtree_sha256'] = '0' * 64; self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'integrity metadata differs'):
            self.verify()

    def test_real_tar_payload_must_match_declared_mtree(self):
        self.add_package('bad-payload', {'bin/a': b'payload'},
                         mtree_change=lambda lines: [line.replace(sha(b'payload'), '1' * 64) for line in lines])
        self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'contents differ'):
            self.verify()

    def test_path_traversal_symlink_special_and_unreviewed_hook_rejected(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('mingw64/link', tarfile.SYMTYPE),
                           ('mingw64/device', tarfile.CHRTYPE), ('usr/share/libalpm/hooks/new.hook', tarfile.REGTYPE)]:
            with self.subTest(name=name):
                entry = tarfile.TarInfo(name); entry.type = kind; entry.linkname = 'mingw64/bin/c++.exe'
                self.add_package('bad-path-' + str(len(self.pins)), {'bin/example': b'x'}, special=entry)
                self.write_manifest()
                with self.assertRaises(deps.BuildError):
                    self.verify()
                self.pins.pop(); self.files.pop('bin/example', None)

    def test_hardlink_target_must_be_regular_and_in_same_archive(self):
        self.add_package('bad-link', {'bin/plain': b'x'}, links={'bin/alias': 'bin/not-in-package'})
        self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'same archive'):
            self.verify()

    def test_case_collisions_between_packages_rejected(self):
        self.add_package('case', {'Bin/new.exe': b'x'}); self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'case-colliding'):
            self.verify()

    def test_conflicting_shared_payload_rejected(self):
        self.add_package('conflict', {'bin/c++.exe': b'different'}); self.write_manifest()
        with self.assertRaisesRegex(deps.BuildError, 'conflicting'):
            self.verify()

    def test_interruption_resumes_only_matching_partial_content(self):
        original = archive._file_bytes; interrupted = False
        def stop_once(stream, size, destination=None):
            nonlocal interrupted
            if destination is not None and not interrupted:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(stream.read(5)); interrupted = True
                raise KeyboardInterrupt()
            return original(stream, size, destination)
        with patch.object(archive, '_file_bytes', side_effect=stop_once), self.assertRaises(KeyboardInterrupt):
            self.prepare()
        self.assertFalse(self.prefix.exists())
        self.prepare(); archive.verify_locked_prefix(self.prefix, self.lock)

    def test_changed_interrupted_prefix_and_foreign_prefix_are_preserved(self):
        original = archive._file_bytes
        def stop(stream, size, destination=None):
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(b'WRONG')
                raise KeyboardInterrupt()
            return original(stream, size, destination)
        with patch.object(archive, '_file_bytes', side_effect=stop), self.assertRaises(KeyboardInterrupt):
            self.prepare()
        with self.assertRaisesRegex(deps.BuildError, 'changed'):
            self.prepare()
        self.assertFalse(self.prefix.exists())
        self.prefix.mkdir(); (self.prefix / 'foreign').write_text('keep')
        with self.assertRaises((deps.BuildError, FileNotFoundError)):
            self.prepare()
        self.assertEqual((self.prefix / 'foreign').read_text(), 'keep')

    def test_forged_receipt_cannot_bless_changed_prefix(self):
        self.prepare(); path = self.prefix / 'bin/c++.exe'; path.write_bytes(b'changed')
        receipt_path = self.prefix / 'receipt.json'; receipt = json.loads(receipt_path.read_text())
        receipt['files']['bin/c++.exe'] = {'bytes': 7, 'sha256': sha(b'changed')}
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(deps.BuildError, 'approved package lock'):
            archive.verify_locked_prefix(self.prefix, self.lock)

    def test_preparation_lock_prevents_simultaneous_writers(self):
        path = self.prefix.with_name(self.prefix.name + '.archive.lock')
        with archive._lock(path), self.assertRaisesRegex(deps.BuildError, 'Another'):
            self.prepare()

    def test_insufficient_space_stops_before_new_stage_or_journal(self):
        with patch.object(archive.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), self.assertRaisesRegex(deps.BuildError, 'Insufficient space'):
            self.prepare()
        self.assertFalse(self.prefix.exists())
        self.assertFalse(self.prefix.with_name(self.prefix.name + '.archive-preparing').exists())
        self.assertFalse(self.prefix.with_name(self.prefix.name + '.archive-preparation.json').exists())

    def test_insufficient_resume_space_preserves_stage_and_counts_existing_bytes(self):
        original = archive._file_bytes
        def stop(stream, size, destination=None):
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(stream.read(5))
                raise KeyboardInterrupt()
            return original(stream, size, destination)
        with patch.object(archive, '_file_bytes', side_effect=stop), self.assertRaises(KeyboardInterrupt):
            self.prepare()
        staging = self.prefix.with_name(self.prefix.name + '.archive-preparing')
        journal = self.prefix.with_name(self.prefix.name + '.archive-preparation.json')
        before = {str(path): path.read_bytes() for path in staging.rglob('*') if path.is_file()}
        before[str(journal)] = journal.read_bytes()
        expected_space = sum(row['bytes'] for row in self.files.values()) - 5 + archive.SPACE_RESERVE
        with patch.object(archive.shutil, 'disk_usage', return_value=SimpleNamespace(free=expected_space - 1)), self.assertRaisesRegex(deps.BuildError, 'Insufficient space'):
            self.prepare()
        self.assertEqual({name: Path(name).read_bytes() for name in before}, before)
        with patch.object(archive.shutil, 'disk_usage', return_value=SimpleNamespace(free=expected_space)):
            self.prepare()
        archive.verify_locked_prefix(self.prefix, self.lock)

    def test_interrupted_metadata_publication_keeps_sidecar_and_resumes(self):
        publish = packages.publish_artifact
        for target in ('journal', 'receipt'):
            with self.subTest(target=target):
                self.prefix = self.root / ('prefix-' + target)
                expected_target = self.prefix.with_name(self.prefix.name + '.archive-preparation.json') if target == 'journal' else self.prefix.with_name(self.prefix.name + '.archive-preparing') / 'receipt.json'
                def stop_once(source, destination, spec):
                    if Path(destination) == expected_target:
                        raise KeyboardInterrupt()
                    return publish(source, destination, spec)
                with patch.object(packages, 'publish_artifact', stop_once), self.assertRaises(KeyboardInterrupt):
                    self.prepare()
                self.assertFalse(expected_target.exists())
                sidecars = list(self.root.glob('.' + expected_target.name + '.pending-*'))
                self.assertTrue(sidecars)
                before = {path: path.read_bytes() for path in sidecars}
                self.prepare(); archive.verify_locked_prefix(self.prefix, self.lock)
                self.assertEqual({path: path.read_bytes() for path in sidecars}, before)

    def test_metadata_publication_does_not_clobber_a_racing_foreign_file(self):
        destination = self.root / 'metadata.json'
        publish = packages.publish_artifact
        def race(source, target, spec):
            Path(target).write_bytes(b'foreign data')
            return publish(source, target, spec)
        with patch.object(packages, 'publish_artifact', race), self.assertRaises(FileExistsError):
            archive._publish_json(destination, {'owned': True})
        self.assertEqual(destination.read_bytes(), b'foreign data')
        self.assertTrue(list(self.root.glob('.metadata.json.pending-*')))

    def test_extraction_reports_package_progress(self):
        output = io.StringIO()
        with redirect_stdout(output):
            archive.prepare_archive_prefix(self.lock, self.cache, self.prefix)
        self.assertIn('Preparing worker package 1/1:', output.getvalue())
        self.assertIn('WORLD WORKER ISOLATED DEPENDENCIES PREPARED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
