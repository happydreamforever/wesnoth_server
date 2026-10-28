"""Materialize the reviewed MINGW64 archives in a private worker prefix.

This is not package installation: scripts and pacman hooks are never executed,
and the live MSYS tree is never changed. Archive hardlinks become independent
ordinary files. The package downloader verifies detached signatures separately;
this module rechecks both pinned archive and signature bytes before use.
"""
from __future__ import annotations

from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import threading
import uuid

from tools import world_worker_dependencies as deps
from tools import world_worker_packages as packages

MAX_MEMBERS = 150000
MAX_FILE = 512 * 1024 * 1024
MAX_EXPANDED = 4 * 1024 * 1024 * 1024
MAX_METADATA = 32 * 1024 * 1024
CHUNK = 1024 * 1024
SPACE_RESERVE = 64 * 1024 * 1024
DECODER_TIMEOUT = 300
MAX_TAR_STREAM = MAX_EXPANDED + MAX_MEMBERS * 1024 + MAX_METADATA
# Signed .MTREE payload pins from the unchanged 107-package snapshot. This
# already-installed MINGW64 package is the Python 3.12 decompression bootstrap.
# Its PE imports are only KERNEL32.dll, msvcrt.dll and this exact libzstd.dll.
ZSTD_PACKAGE = {'name': 'mingw-w64-x86_64-zstd', 'version': '1.5.7-2',
                'sha256': '1add6705b344664f6aca108c85f79ab5bdd9e1162662bb06a4cf40a34f6e0907'}
ZSTD_FILES = {
    'zstd.exe': {'size': 229865, 'sha256': 'd44f40274c8632f98fdc8bb89928fe8fb566f0fb6b4287bab98027c1cfa26d86'},
    'libzstd.dll': {'size': 1218273, 'sha256': 'b95c223a9548a9ecf51377c962e0bc8f0c51eb0c6f67a296dbc885996f0dd40d'},
}
METADATA = {'.PKGINFO', '.BUILDINFO', '.MTREE', '.INSTALL', '.CHANGELOG'}
HOOKS = {
    'usr/share/libalpm/hooks/mingw-w64-x86_64-fontconfig.hook',
    'usr/share/libalpm/hooks/mingw-w64-x86_64-gio-querymodules.hook',
    'usr/share/libalpm/hooks/mingw-w64-x86_64-glib-compile-schemas.hook',
}
HOOK_DIRS = {'usr', 'usr/share', 'usr/share/libalpm', 'usr/share/libalpm/hooks'}
RESERVED = re.compile(r'(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?')


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _path(name):
    if not isinstance(name, str) or not name or len(name) > 2048:
        raise deps.BuildError('Invalid archive path.')
    if name.startswith('./'):
        name = name[2:]
    name = name.rstrip('/')
    parts = name.split('/')
    if (not name or PurePosixPath(name).is_absolute() or any(x in ('', '.', '..') for x in parts)
            or any(ord(c) < 32 or c in '<>:"\\|?*' for c in name)
            or any(x.endswith((' ', '.')) or RESERVED.fullmatch(x) for x in parts)):
        raise deps.BuildError('Unsafe Windows archive path.')
    return name


def _allowed(name, directory):
    if name == 'mingw64' or name.startswith('mingw64/'):
        return
    if directory and name in HOOK_DIRS:
        return
    if not directory and (name in METADATA or name in HOOKS):
        return
    raise deps.BuildError('Archive contains an unreviewed path outside MINGW64.')


def _bounded(stream, size):
    raw = stream.read(size + 1)
    if len(raw) > size:
        raise deps.BuildError('Archive metadata exceeds its bound.')
    return raw


def _mtree(compressed):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = _bounded(stream, MAX_METADATA)
        text = raw.decode('utf-8')
    except (OSError, EOFError, UnicodeError):
        raise deps.BuildError('Archive integrity metadata is unreadable.') from None
    defaults = {}; files = {}; kinds = {}; names = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.split(); attrs = {}
        for item in parts[1:]:
            if '=' not in item:
                if parts[0] == '/unset':
                    continue
                raise deps.BuildError('Malformed archive integrity attributes.')
            key, value = item.split('=', 1)
            if key in attrs:
                raise deps.BuildError('Duplicate archive integrity attribute.')
            attrs[key] = deps.unescape(value)
        if parts[0] == '/set':
            defaults.update(attrs); continue
        if parts[0] == '/unset':
            for key in parts[1:]:
                defaults.pop(key, None)
            continue
        name = _path(deps.unescape(parts[0])); value = {**defaults, **attrs}
        kind = value.get('type')
        if kind not in ('dir', 'file'):
            raise deps.BuildError('Archive integrity metadata permits only ordinary files and directories.')
        _allowed(name, kind == 'dir')
        if name in kinds or name.casefold() in names:
            raise deps.BuildError('Duplicate or case-colliding archive integrity path.')
        kinds[name] = kind; names[name.casefold()] = name
        if kind == 'file':
            size = value.get('size', '')
            if not re.fullmatch(r'[0-9]+', size) or int(size) > MAX_FILE or not re.fullmatch(r'[0-9a-f]{64}', value.get('sha256digest', '')):
                raise deps.BuildError('Archive file lacks bounded SHA256 integrity metadata.')
            files[name] = {'bytes': int(size), 'sha256': value['sha256digest']}
        if len(kinds) > MAX_MEMBERS:
            raise deps.BuildError('Archive integrity member count exceeds its bound.')
    return files, kinds


def _pkginfo(raw, pin):
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise deps.BuildError('Package identity is not UTF-8.') from None
    fields = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        if ' = ' not in line:
            raise deps.BuildError('Malformed package identity metadata.')
        key, value = line.split(' = ', 1)
        fields.setdefault(key, []).append(value)
    for key, expected in (('pkgname', [pin['name']]), ('pkgver', [pin['version']]), ('arch', ['any'])):
        if fields.get(key) != expected:
            raise deps.BuildError('Archive package identity differs from the approved pin.')
    for key, field in (('depend', 'depends'), ('provides', 'provides'), ('conflict', 'conflicts'), ('replaces', 'replaces')):
        if sorted(fields.get(key, [])) != sorted(pin[field]):
            raise deps.BuildError('Archive dependency metadata differs from the approved pin.')


def _check_cache(pin, cache):
    archive = deps.safe_path(Path(cache) / pin['filename'])
    packages.verify_artifact(archive, pin)
    packages.verify_artifact(Path(str(archive) + '.sig'), {'filename': pin['filename'] + '.sig', **pin['signature']})
    return archive


def _verify_decoder(decoder):
    for path, spec in decoder['files']:
        packages.verify_artifact(path, {'filename': path.name, **spec})


def _windows_decoder(manifest, msys):
    if msys is None:
        raise deps.BuildError('MsysRoot is required to verify the pinned archive decoder.')
    matches = [row for row in manifest['packages'] if row['name'] == ZSTD_PACKAGE['name']]
    if len(matches) != 1 or any(matches[0].get(key) != value for key, value in ZSTD_PACKAGE.items()):
        raise deps.BuildError('The archive decoder is not part of the approved package snapshot.')
    binary = deps.safe_path(Path(msys) / 'mingw64/bin', directory=True)
    system = os.environ.get('SystemRoot')
    if not system:
        raise deps.BuildError('SystemRoot is required for the native archive decoder.')
    system = deps.safe_path(system, directory=True)
    system32 = deps.safe_path(system / 'System32', directory=True)
    decoder = {'executable': binary / 'zstd.exe', 'cwd': system32,
               'environment': {'SystemRoot': str(system), 'WINDIR': str(system),
                               'PATH': os.pathsep.join(map(str, (binary, system32, system)))},
               'files': [(binary / name, spec) for name, spec in ZSTD_FILES.items()]}
    _verify_decoder(decoder)
    return decoder


def _decoder(manifest, msys):
    if os.name == 'nt':
        return _windows_decoder(manifest, msys)
    # Linux is used for the real archive fixtures, never claimed as Windows
    # execution. Record and recheck the local decoder rather than using a shell.
    executable = shutil.which('zstd')
    if executable is None:
        raise deps.BuildError('Local archive verification requires the zstd executable.')
    executable = deps.safe_path(executable)
    return {'executable': executable, 'cwd': executable.parent,
            'environment': {'PATH': str(executable.parent), 'LC_ALL': 'C'},
            'files': [(executable, {'size': executable.stat().st_size, 'sha256': deps.digest(executable)})]}


class _BoundedDecoderStream:
    def __init__(self, stream):
        self.stream = stream
        self.total = 0

    def read(self, size=-1):
        remaining = MAX_TAR_STREAM - self.total
        requested = min(CHUNK if size < 0 else size, remaining + 1)
        value = self.stream.read(requested)
        self.total += len(value)
        if self.total > MAX_TAR_STREAM:
            raise deps.BuildError('Decompressed package stream exceeds its bound.')
        return value


@contextmanager
def _open_archive(archive, decoder):
    """Stream zstd into Python 3.12 tarfile, with bounded lifetime and output."""
    _verify_decoder(decoder)
    process = subprocess.Popen([str(decoder['executable']), '-q', '-d', '-c', '--memory=128MB', '--', str(archive)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               cwd=decoder['cwd'], env=decoder['environment'], shell=False)
    expired = threading.Event()
    def timeout():
        expired.set()
        try:
            process.kill()
        except OSError:
            pass
    timer = threading.Timer(DECODER_TIMEOUT, timeout)
    timer.daemon = True
    timer.start()
    stream = _BoundedDecoderStream(process.stdout)
    try:
        with tarfile.open(fileobj=stream, mode='r|') as tar:
            yield tar
        # tarfile stops at the tar terminator; drain to establish decompressor
        # success, including the compressed frame checksum and trailing frames.
        while stream.read(CHUNK):
            pass
        status = process.wait(timeout=10)
        if expired.is_set() or status != 0:
            raise deps.BuildError('The archive decoder timed out or rejected the compressed package.')
        _verify_decoder(decoder)
    except subprocess.TimeoutExpired:
        raise deps.BuildError('The archive decoder did not stop within its time bound.') from None
    finally:
        timer.cancel()
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        process.stdout.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            raise deps.BuildError('The archive decoder could not be stopped; preserve the preparation log.') from None


def _file_bytes(stream, size, destination=None):
    """Verify or resume an interrupted, owned output without replacing bytes."""
    existing = None; writer = None; existing_size = 0; count = 0; digest = hashlib.sha256()
    try:
        if destination is not None:
            destination = deps.safe_path(destination)
            if destination.exists():
                stat = destination.stat()
                if stat.st_nlink != 1 or stat.st_size > size:
                    raise deps.BuildError('Prepared file is linked or larger than its approved archive payload.')
                existing_size = stat.st_size
                existing = destination.open('rb')
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                writer = destination.open('xb')
        while count < size:
            chunk = stream.read(min(CHUNK, size - count))
            if not chunk:
                raise deps.BuildError('Archive file is truncated.')
            digest.update(chunk)
            consumed = min(len(chunk), max(0, existing_size - count))
            if consumed and existing.read(consumed) != chunk[:consumed]:
                raise deps.BuildError('An interrupted prepared file was changed; preserve it for review.')
            if destination is not None and consumed < len(chunk):
                if writer is None:
                    writer = destination.open('ab')
                writer.write(chunk[consumed:])
            count += len(chunk)
        if stream.read(1):
            raise deps.BuildError('Archive file exceeds its declared size.')
        if writer is not None:
            writer.flush(); os.fsync(writer.fileno())
    finally:
        if existing is not None:
            existing.close()
        if writer is not None:
            writer.close()
    result = {'bytes': count, 'sha256': digest.hexdigest()}
    if destination is not None and (destination.stat().st_size != count or deps.digest(destination) != result['sha256']):
        raise deps.BuildError('Prepared file changed during archive extraction.')
    return result


def _scan(pin, cache, destination=None, decoder=None):
    archive = _check_cache(pin, cache)
    seen = {}; names = {}; actual = {}; regular = {}; links = {}; metadata = {}; expanded = 0
    try:
        with _open_archive(archive, decoder) as tar:
            for member in tar:
                name = _path(member.name)
                if name in seen or name.casefold() in names:
                    raise deps.BuildError('Archive has duplicate or case-colliding paths.')
                names[name.casefold()] = name
                if member.isdir():
                    kind = 'dir'
                elif member.isfile() or member.islnk():
                    kind = 'file'
                else:
                    raise deps.BuildError('Archive symlinks and special files are not permitted.')
                _allowed(name, kind == 'dir'); seen[name] = kind
                if len(seen) > MAX_MEMBERS or member.size < 0 or member.size > MAX_FILE:
                    raise deps.BuildError('Archive exceeds its file or member bounds.')
                if member.isdir():
                    continue
                if member.islnk():
                    target = _path(member.linkname)
                    if not name.startswith('mingw64/') or not target.startswith('mingw64/') or target == name or member.size:
                        raise deps.BuildError('Archive hardlink is not an internal ordinary payload alias.')
                    links[name] = target
                    continue
                expanded += member.size
                if expanded > MAX_EXPANDED:
                    raise deps.BuildError('Archive expanded bytes exceed their bound.')
                source = tar.extractfile(member)
                if name in METADATA:
                    if member.size > MAX_METADATA:
                        raise deps.BuildError('Archive metadata exceeds its bound.')
                    raw = _bounded(source, MAX_METADATA)
                    if len(raw) != member.size:
                        raise deps.BuildError('Archive metadata is truncated.')
                    metadata[name] = raw
                    value = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                else:
                    output = Path(destination) / name[len('mingw64/'):] if destination is not None and name.startswith('mingw64/') else None
                    value = _file_bytes(source, member.size, output)
                actual[name] = value; regular[name] = value
    except (tarfile.TarError, EOFError, OSError) as error:
        raise deps.BuildError('Pinned package archive could not be read: ' + type(error).__name__) from None
    if not {'.MTREE', '.PKGINFO'}.issubset(metadata):
        raise deps.BuildError('Archive lacks its package identity or integrity metadata.')
    if hashlib.sha256(metadata['.MTREE']).hexdigest() != pin['mtree_sha256']:
        raise deps.BuildError('Archive integrity metadata differs from its approved pin.')
    _pkginfo(metadata['.PKGINFO'], pin)
    expected, kinds = _mtree(metadata['.MTREE'])
    for name, target in links.items():
        if target not in regular or target in METADATA or not target.startswith('mingw64/'):
            raise deps.BuildError('Archive hardlink target must be an ordinary file in the same archive.')
        actual[name] = regular[target]
        if expected.get(name) != regular[target]:
            raise deps.BuildError('Archive hardlink integrity differs from its target.')
        if destination is not None:
            source = deps.safe_path(Path(destination) / target[len('mingw64/'):])
            output = Path(destination) / name[len('mingw64/'):]
            with source.open('rb') as stream:
                _file_bytes(stream, regular[target]['bytes'], output)
    actual.pop('.MTREE', None); seen.pop('.MTREE', None)
    if kinds != seen or expected != actual:
        raise deps.BuildError('Archive contents differ from the pinned integrity metadata.')
    _check_cache(pin, cache)
    return {name[len('mingw64/'):]: row for name, row in actual.items() if name.startswith('mingw64/')}


def _package_receipts(manifest, manifest_hash):
    return [{'name': row['name'], 'version': row['version'], 'mtree_sha256': row['mtree_sha256'],
             'archive_sha256': row['sha256'], 'signature_sha256': row['signature']['sha256'],
             'manifest_sha256': manifest_hash} for row in manifest['packages']]


def _receipt(manifest, manifest_hash, cache, destination=None, decoder=None):
    files = {}; names = {}; directories = set()
    total = len(manifest['packages'])
    for index, pin in enumerate(manifest['packages'], 1):
        if destination is not None and (index == 1 or index % 5 == 0 or index == total):
            print(f'Preparing worker package {index}/{total}: {pin["name"]}', flush=True)
        rows = _scan(pin, cache, destination, decoder)
        for name, value in rows.items():
            if name.casefold() in directories:
                raise deps.BuildError('Packages use the same path for a file and a directory.')
            for parent in PurePosixPath(name).parents:
                if parent.as_posix() == '.':
                    continue
                parent_name = parent.as_posix()
                if parent_name.casefold() in names and names[parent_name.casefold()] in files:
                    raise deps.BuildError('Packages use a file as a parent directory.')
                previous_parent = names.get(parent_name.casefold())
                if previous_parent is not None and previous_parent != parent_name:
                    raise deps.BuildError('Packages contain case-colliding directory paths.')
                names[parent_name.casefold()] = parent_name
                directories.add(parent_name.casefold())
            previous = names.get(name.casefold())
            if previous is not None and previous != name:
                raise deps.BuildError('Packages contain case-colliding payload paths.')
            if name in files and files[name] != value:
                raise deps.BuildError('Packages contain conflicting payload files.')
            names[name.casefold()] = name; files[name] = value
        if len(files) > MAX_MEMBERS or sum(row['bytes'] for row in files.values()) > MAX_EXPANDED:
            raise deps.BuildError('Combined worker prefix exceeds its bounds.')
    if canonical_hash(files) != manifest['source'].get('prefix_files_sha256'):
        raise deps.BuildError('Materialized prefix differs from the approved file manifest.')
    return {'format': 1, 'purpose': deps.PURPOSE, 'packages': _package_receipts(manifest, manifest_hash), 'files': files}


def verify_archive_inputs(manifest_path=packages.MANIFEST, cache=packages.CACHE, *, msys=None):
    """Validate all pinned tar contents without creating a prefix."""
    manifest = packages.load_manifest(manifest_path)
    return _receipt(manifest, deps.digest(manifest_path), cache, decoder=_decoder(manifest, msys))


def verify_locked_prefix(prefix=deps.PREFIX, manifest_path=packages.MANIFEST):
    manifest = packages.load_manifest(manifest_path)
    receipt = deps.verify(prefix)
    if (receipt['packages'] != _package_receipts(manifest, deps.digest(manifest_path))
            or canonical_hash(receipt['files']) != manifest['source'].get('prefix_files_sha256')):
        raise deps.BuildError('Worker prefix does not match the approved package lock.')
    return receipt


def _publish_json(path, value, *, temporary_parent=None):
    """Publish complete metadata only; an interrupted sidecar stays for review."""
    path = deps.safe_path(path)
    parent = Path(temporary_parent) if temporary_parent is not None else path.parent
    deps.safe_path(parent, directory=True)
    temporary = parent / ('.' + path.name + '.pending-' + uuid.uuid4().hex)
    deps.write_new(temporary, value)
    if path.exists():
        raise deps.BuildError('Worker preparation metadata appeared during publication; preserve it.')
    packages.publish_artifact(temporary, path, {'filename': path.name,
                             'size': temporary.stat().st_size, 'sha256': deps.digest(temporary)})


def _remaining_space(staging, expected):
    """Count only validated owned bytes; reject foreign or oversized partials."""
    existing_bytes = 0
    if staging.exists():
        deps.safe_path(staging, directory=True)
        for path in staging.rglob('*'):
            deps.safe_path(path, directory=path.is_dir())
            if path.is_file():
                name = path.relative_to(staging).as_posix()
                if name == 'receipt.json':
                    if packages.read_json(path) != expected:
                        raise deps.BuildError('Incomplete worker prefix receipt was changed.')
                elif (name not in expected['files'] or path.stat().st_nlink != 1
                      or path.stat().st_size > expected['files'][name]['bytes']):
                    raise deps.BuildError('Incomplete worker prefix contains an unrecorded, oversized or linked file.')
                else:
                    existing_bytes += path.stat().st_size
    needed = sum(row['bytes'] for row in expected['files'].values()) - existing_bytes + SPACE_RESERVE
    if shutil.disk_usage(staging.parent).free < needed:
        raise deps.BuildError(f'Insufficient space for the isolated worker prefix: {needed} free bytes required. Existing preparation is preserved.')
    return needed


@contextmanager
def _lock(path):
    """The operating system releases this lock after an interrupted process."""
    path = deps.safe_path(path)
    marker = b'wesnoth-world-worker-archive-prefix-lock\n'
    if path.exists() and deps.read(path) != marker:
        raise deps.BuildError('Foreign worker preparation lock; preserve it.')
    if not path.exists():
        try:
            with path.open('xb') as stream:
                stream.write(marker)
        except FileExistsError:
            if deps.read(path) != marker:
                raise deps.BuildError('Worker preparation lock changed.') from None
    stream = path.open('r+b')
    try:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise deps.BuildError('Another worker prefix preparation is running.') from None
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise deps.BuildError('Another worker prefix preparation is running.') from None
        yield
    finally:
        stream.close()


def prepare_archive_prefix(manifest_path=packages.MANIFEST, cache=packages.CACHE, prefix=deps.PREFIX, *, msys=None):
    manifest = packages.load_manifest(manifest_path); manifest_hash = deps.digest(manifest_path)
    prefix = Path(prefix).absolute()
    deps.safe_path(prefix, directory=True) if prefix.exists() else deps.safe_path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with _lock(prefix.with_name(prefix.name + '.archive.lock')):
        if prefix.exists():
            verify_locked_prefix(prefix, manifest_path)
            print('WORLD WORKER ISOLATED DEPENDENCIES VERIFIED', flush=True)
            return prefix
        decoder = _decoder(manifest, msys)
        expected = _receipt(manifest, manifest_hash, cache, decoder=decoder)
        staging = prefix.with_name(prefix.name + '.archive-preparing')
        journal = prefix.with_name(prefix.name + '.archive-preparation.json')
        ownership = {'format': 1, 'purpose': 'wesnoth-world-worker-archive-preparation',
                     'manifest_sha256': manifest_hash, 'prefix': str(prefix), 'staging': str(staging),
                     'source': manifest['source'], 'packages': expected['packages']}
        if journal.exists():
            if packages.read_json(journal) != ownership:
                raise deps.BuildError('Worker prefix preparation belongs to another package lock.')
        else:
            if staging.exists():
                raise deps.BuildError('An unowned incomplete worker prefix exists; preserve it.')
        _remaining_space(staging, expected)
        if not journal.exists():
            _publish_json(journal, ownership)
        if not staging.exists():
            staging.mkdir()
        extracted = _receipt(manifest, manifest_hash, cache, staging, decoder)
        if extracted != expected or deps.digest(manifest_path) != manifest_hash:
            raise deps.BuildError('Worker package lock changed during preparation.')
        receipt = staging / 'receipt.json'
        if not receipt.exists():
            _publish_json(receipt, expected, temporary_parent=staging.parent)
        verify_locked_prefix(staging, manifest_path)
        staging.rename(prefix)
        verify_locked_prefix(prefix, manifest_path)
        print('WORLD WORKER ISOLATED DEPENDENCIES PREPARED', flush=True)
        return prefix
