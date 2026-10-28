"""Retain the one known incomplete pre-sysroot worker without reusing its output."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

from tools.build_alliance_bridge import BuildError
from tools import world_worker_packages as packages

PURPOSE = 'wesnoth-world-worker-sysroot-recovery'
BINDING_PURPOSE = 'wesnoth-full-native-world-worker'
BUILDER_INPUT = 'wesnoth_server/tools/build_world_worker.py'
RECOVERY_INPUT = 'wesnoth_server/tools/world_worker_recovery.py'
LEGACY_BUILDERS = frozenset({
    '1afb04004e3e1593d4f81150e6c8f4323ffcac34fd7bc58e2a9e441ea316dd05',
    '727dbb498fca33e947c85080bd2c50148a813d0637bcc7ec48c8dfce12178163',
})
MAX_FILES = 100000
MAX_BYTES = 32 * 1024**3
MAX_METADATA = 64 * 1024**2


def _path(value, *, directory=False):
    path = Path(value).absolute()
    if '..' in path.parts or str(path).startswith('\\\\'):
        raise BuildError('Worker recovery requires an ordinary local path.')
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise BuildError('Worker recovery paths cannot be linked or redirected.')
    if directory and not path.is_dir():
        raise BuildError('Worker recovery directory is missing.')
    return path


def _ordinary(path):
    info = _path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BuildError('Worker recovery files must be ordinary and single-link.')
    return info


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns,
            info.st_nlink, getattr(info, 'st_file_attributes', 0))


def _same_open_file(path, before, opened, *, windows=None):
    """Account only for CPython's Windows filename-derived execute bits."""
    expected = _identity(before)
    actual = _identity(opened)
    if expected == actual:
        return True
    if windows is None:
        windows = os.name == 'nt'
    # Windows path stat adds all execute bits for these suffixes. Descriptor
    # stat cannot inspect the name. Keep every other field, and all subsequent
    # path-to-path comparisons, exact; POSIX modes retain their full meaning.
    if not windows or Path(path).suffix.casefold() not in ('.exe', '.bat', '.cmd', '.com'):
        return False
    named = list(actual)
    named[2] |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return expected == tuple(named)


def _read_json(path):
    before = _ordinary(path)
    if not 0 < before.st_size <= MAX_METADATA:
        raise BuildError('Worker recovery metadata exceeds its bound.')
    with Path(path).open('rb') as stream:
        if not _same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('Worker recovery metadata changed while opening.')
        raw = stream.read(MAX_METADATA + 1)
    if len(raw) != before.st_size or _identity(_ordinary(path)) != _identity(before):
        raise BuildError('Worker recovery metadata changed while reading.')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BuildError('Worker recovery metadata repeats a field.')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise BuildError('Worker recovery metadata is unreadable; preserved.') from None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _publish(path, value):
    path = _path(path)
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    if len(raw) > MAX_METADATA:
        raise BuildError('Worker recovery metadata exceeds its bound.')
    temporary = path.with_name('.' + path.name + '.pending-' + uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    packages.publish_artifact(temporary, path, {
        'filename': path.name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})


def _binding(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'purpose', 'release', 'inputs'}
            or type(value['format']) is not int or value['format'] != 1
            or value['purpose'] != BINDING_PURPOSE
            or type(value['release']) is not int or value['release'] != 1192624
            or not isinstance(value['inputs'], dict) or not value['inputs']
            or len(value['inputs']) > MAX_FILES):
        raise BuildError('Worker recovery ownership is invalid.')
    for name, digest in value['inputs'].items():
        if (not isinstance(name, str) or not name or len(name) > 2048
                or name.startswith('/') or any(x in name for x in ('\\', ':'))
                or any(x in ('', '.', '..') for x in name.split('/'))
                or any(ord(c) < 32 for c in name)
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise BuildError('Worker recovery input binding is invalid.')


def _legacy(owner, expected):
    _binding(owner)
    _binding(expected)
    if (RECOVERY_INPUT not in expected['inputs'] or BUILDER_INPUT not in expected['inputs']
            or RECOVERY_INPUT in owner['inputs']
            or set(owner['inputs']) != set(expected['inputs']) - {RECOVERY_INPUT}
            or owner['inputs'].get(BUILDER_INPUT) not in LEGACY_BUILDERS
            or any(value != expected['inputs'][name] for name, value in owner['inputs'].items()
                   if name != BUILDER_INPUT)):
        raise BuildError('Only the recognized incomplete worker may be retained by this recovery.')


def _inventory(directory):
    directory = _path(directory, directory=True)
    files = {}
    directories = []
    pending = [directory]
    total = 0
    while pending:
        parent = pending.pop()
        for entry in sorted(parent.iterdir()):
            _path(entry)
            info = entry.lstat()
            name = entry.relative_to(directory).as_posix()
            if len(name) > 2048 or any(ord(c) < 32 for c in name):
                raise BuildError('Worker recovery entry name is invalid.')
            if stat.S_ISDIR(info.st_mode):
                directories.append(name)
                pending.append(entry)
            else:
                before = _ordinary(entry)
                total += before.st_size
                if total > MAX_BYTES:
                    raise BuildError('Worker recovery inventory exceeds its byte bound.')
                with entry.open('rb') as stream:
                    if not _same_open_file(entry, before, os.fstat(stream.fileno())):
                        raise BuildError('Worker recovery file changed while opening.')
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if _identity(_ordinary(entry)) != _identity(before):
                    raise BuildError('Worker recovery file changed while hashing.')
                files[name] = {'bytes': before.st_size, 'sha256': digest,
                               'mtime_ns': before.st_mtime_ns, 'mode': before.st_mode,
                               'attributes': getattr(before, 'st_file_attributes', 0)}
            if len(files) + len(directories) > MAX_FILES:
                raise BuildError('Worker recovery inventory exceeds its entry bound.')
    return {'files': files, 'directories': sorted(directories)}


def _paths(stage):
    stage = _path(stage)
    _path(stage.parent, directory=True)
    return (stage, _path(stage.with_name(stage.name + '.sysroot-recovery.json')),
            _path(stage.with_name(stage.name + '.sysroot-recovery-complete.json')))


def _intent(path, stage, expected=None):
    record = _read_json(path)
    if (not isinstance(record, dict) or set(record) != {
            'format', 'purpose', 'stage', 'retained', 'legacy_owner', 'expected_binding', 'inventory'}
            or type(record['format']) is not int or record['format'] != 1
            or record['purpose'] != PURPOSE or record['stage'] != str(stage)
            or not isinstance(record['retained'], str) or not record['retained']):
        raise BuildError('Worker recovery journal is invalid; preserved.')
    retained = _path(record['retained'])
    if (retained.parent != stage.parent or not re.fullmatch(
            re.escape(stage.name) + r'-before-sysroot-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}', retained.name)):
        raise BuildError('Worker recovery destination is invalid; preserved.')
    _legacy(record['legacy_owner'], record['expected_binding'])
    if expected is not None and record['expected_binding'] != expected:
        raise BuildError('Worker recovery belongs to another corrected build; preserved.')
    inv = record['inventory']
    if (not isinstance(inv, dict) or set(inv) != {'files', 'directories'}
            or not isinstance(inv['files'], dict) or not isinstance(inv['directories'], list)
            or 'owner.json' not in inv['files'] or 'receipt.json' in inv['files']):
        raise BuildError('Worker recovery inventory is invalid; preserved.')
    return record, retained


def _completion(record):
    return {'format': 1, 'purpose': PURPOSE, 'journal_sha256': _hash(record),
            'retained': record['retained'], 'inventory_sha256': _hash(record['inventory']),
            'status': 'retained_incomplete_not_verified_build'}


def recovery_pending(stage):
    """Read-only gate; the caller must resume intent even if rename removed stage."""
    stage, journal, complete = _paths(stage)
    if not journal.exists():
        if complete.exists():
            raise BuildError('Worker recovery completion has no journal; preserved.')
        return False
    record, retained = _intent(journal, stage)
    if complete.exists():
        if _read_json(complete) != _completion(record) or not retained.is_dir():
            raise BuildError('Worker recovery completion differs; preserved.')
        return False
    return True


@contextmanager
def _lock(stage):
    path = _path(stage.with_name(stage.name + '.sysroot-recovery.lock'))
    marker = b'wesnoth-world-worker-sysroot-recovery-lock\n'
    if not path.exists():
        try:
            with path.open('xb') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    if _ordinary(path).st_size != len(marker) or path.read_bytes() != marker:
        raise BuildError('Worker recovery lock is foreign; preserved.')
    with path.open('r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise BuildError('Another worker recovery holds the lock.') from None
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise BuildError('Another worker recovery holds the lock.') from None
        yield


def _rename(source, destination):
    if destination.exists():
        raise BuildError('Worker recovery destination already exists; preserved.')
    if os.name == 'nt':
        os.rename(source, destination)  # Windows never replaces an existing directory.
    elif sys.platform.startswith('linux'):
        # Linux fixtures need the same no-overwrite guarantee as production Windows.
        libc = ctypes.CDLL(None, use_errno=True)
        operation = getattr(libc, 'renameat2', None)
        if operation is None:
            raise BuildError('No exclusive directory rename is available.')
        operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        operation.restype = ctypes.c_int
        if operation(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            raise OSError(ctypes.get_errno(), 'Exclusive worker recovery rename failed.')
    else:
        raise BuildError('Worker recovery requires Windows or the Linux verification host.')


def preserve_failed_stage(stage, expected_binding):
    """Retain the complete failed tree; never bless or resume its compiled output."""
    stage, journal, complete = _paths(stage)
    _binding(expected_binding)
    with _lock(stage):
        if journal.exists():
            record, retained = _intent(journal, stage, expected_binding)
        else:
            if complete.exists():
                raise BuildError('Worker recovery completion has no journal; preserved.')
            _path(stage, directory=True)
            if (stage / 'receipt.json').exists():
                raise BuildError('Completed workers use normal preservation, not failed-stage recovery.')
            owner = _read_json(stage / 'owner.json')
            _legacy(owner, expected_binding)
            inventory = _inventory(stage)
            retained = stage.with_name(stage.name + '-before-sysroot-' +
                datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex)
            record = {'format': 1, 'purpose': PURPOSE, 'stage': str(stage), 'retained': str(retained),
                      'legacy_owner': owner, 'expected_binding': expected_binding, 'inventory': inventory}
            _publish(journal, record)
        if complete.exists():
            if _read_json(complete) != _completion(record) or _inventory(retained) != record['inventory']:
                raise BuildError('Retained worker recovery artifact changed; preserved.')
            if stage.exists() and _read_json(stage / 'owner.json') != expected_binding:
                raise BuildError('An unexpected worker appeared after recovery; preserved.')
            return retained
        if stage.exists():
            if retained.exists() or _read_json(stage / 'owner.json') != record['legacy_owner']:
                raise BuildError('Worker recovery paths or ownership changed; preserved.')
            if (stage / 'receipt.json').exists() or _inventory(stage) != record['inventory']:
                raise BuildError('Incomplete worker changed after recovery was recorded; preserved.')
            _rename(stage, retained)
        if not retained.is_dir() or _inventory(retained) != record['inventory']:
            raise BuildError('Retained worker recovery artifact differs; preserved.')
        _publish(complete, _completion(record))
        return retained
