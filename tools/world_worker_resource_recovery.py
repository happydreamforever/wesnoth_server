"""Resume only the recorded resource-stage worker without discarding its objects."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from tools.build_alliance_bridge import BuildError
from tools import world_worker_recovery as recovery

PURPOSE = 'wesnoth-world-worker-resource-recovery'
RESOURCE_INPUT = 'wesnoth_server/tools/world_worker_resource_recovery.py'
LEGACY_PAIRS = frozenset({
    ('766a890b4d92690832ff325fc287573b11b8f0dbd25d0964c7965f010647bb44',
     '819f7a4368efd6561df1c918c5f5d22a887d9d9b6eabca7ab1642c8f02d263f0'),
    ('b09ec19031dbbed18aa0b25d95617da5695577a7e4eeeca3961eb78633c5d4d7',
     '335ce1918fbc88050f578a60782b32965ac1d4b887cf60c7a410d4f5b42840b2'),
})


def _paths(stage):
    stage = recovery._path(stage)
    recovery._path(stage.parent, directory=True)
    if stage.exists():
        recovery._path(stage, directory=True)
    return (stage,
            recovery._path(stage.with_name(stage.name + '.resource-recovery.json')),
            recovery._path(stage.with_name(stage.name + '.resource-recovery-complete.json')),
            recovery._path(stage.with_name(stage.name + '.resource-recovery.lock')))


def _legacy(owner, expected):
    recovery._binding(owner)
    recovery._binding(expected)
    prior = owner['inputs']
    current = expected['inputs']
    changed = {recovery.BUILDER_INPUT, recovery.RECOVERY_INPUT}
    if (RESOURCE_INPUT not in current or RESOURCE_INPUT in prior
            or not changed <= set(prior)
            or set(prior) != set(current) - {RESOURCE_INPUT}
            or (prior[recovery.BUILDER_INPUT], prior[recovery.RECOVERY_INPUT]) not in LEGACY_PAIRS
            or any(value != current[name] for name, value in prior.items() if name not in changed)):
        raise BuildError('Only the recognized resource-stage worker may resume with these corrected sources.')


def _bytes(path):
    before = recovery._ordinary(path)
    if not 0 < before.st_size <= recovery.MAX_METADATA:
        raise BuildError('Worker resource recovery metadata exceeds its bound.')
    with Path(path).open('rb') as stream:
        if not recovery._same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('Worker resource recovery metadata changed while opening.')
        raw = stream.read(recovery.MAX_METADATA + 1)
    if (len(raw) != before.st_size
            or recovery._identity(recovery._ordinary(path)) != recovery._identity(before)):
        raise BuildError('Worker resource recovery metadata changed while reading.')
    return raw


def _new_owner(expected):
    return (json.dumps(expected, sort_keys=True, indent=2) + '\n').encode()


def _relative(name):
    return (isinstance(name, str) and bool(name) and len(name) <= 2048
            and not name.startswith('/') and not any(c in name for c in ('\\', ':'))
            and not any(piece in ('', '.', '..') for piece in name.split('/'))
            and not any(ord(c) < 32 for c in name))


def _inventory_record(value):
    if (not isinstance(value, dict) or set(value) != {'files', 'directories'}
            or not isinstance(value['files'], dict) or not isinstance(value['directories'], list)
            or not value['files'] or len(value['files']) + len(value['directories']) > recovery.MAX_FILES
            or 'owner.json' not in value['files'] or 'receipt.json' in value['files']):
        raise BuildError('Worker resource recovery inventory is invalid; preserved.')
    for name, row in value['files'].items():
        if (not _relative(name) or not isinstance(row, dict)
                or set(row) != {'bytes', 'sha256', 'mtime_ns', 'mode', 'attributes'}
                or any(type(row[key]) is not int for key in ('bytes', 'mtime_ns', 'mode', 'attributes'))
                or row['bytes'] < 0 or row['mode'] < 0 or row['attributes'] < 0
                or not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise BuildError('Worker resource recovery inventory is invalid; preserved.')
    directories = value['directories']
    if (any(not _relative(name) for name in directories)
            or directories != sorted(set(directories)) or set(directories) & set(value['files'])
            or sum(row['bytes'] for row in value['files'].values()) > recovery.MAX_BYTES):
        raise BuildError('Worker resource recovery inventory is invalid; preserved.')


def _intent(path, stage, expected=None):
    record = recovery._read_json(path)
    if (not isinstance(record, dict) or set(record) != {
            'format', 'purpose', 'stage', 'original_owner', 'original_owner_hex',
            'expected_binding', 'inventory'}
            or type(record['format']) is not int or record['format'] != 1
            or record['purpose'] != PURPOSE or record['stage'] != str(stage)
            or not isinstance(record['original_owner_hex'], str)):
        raise BuildError('Worker resource recovery journal is invalid; preserved.')
    _legacy(record['original_owner'], record['expected_binding'])
    if expected is not None and record['expected_binding'] != expected:
        raise BuildError('Worker resource recovery belongs to another corrected build; preserved.')
    _inventory_record(record['inventory'])
    try:
        raw = bytes.fromhex(record['original_owner_hex'])
        original = json.loads(raw)
    except (ValueError, UnicodeError):
        raise BuildError('Worker resource recovery original ownership is invalid; preserved.') from None
    owner = record['inventory']['files']['owner.json']
    if (not raw or len(raw) != owner['bytes'] or hashlib.sha256(raw).hexdigest() != owner['sha256']
            or original != record['original_owner']):
        raise BuildError('Worker resource recovery original ownership differs; preserved.')
    return record


def _completion(record):
    return {'format': 1, 'purpose': PURPOSE, 'journal_sha256': recovery._hash(record),
            'inventory_sha256': recovery._hash(record['inventory']),
            'owner_sha256': hashlib.sha256(_new_owner(record['expected_binding'])).hexdigest(),
            'status': 'source_binding_updated_not_verified_build'}


def resource_recovery_pending(stage):
    stage, journal, complete, _ = _paths(stage)
    if not journal.exists():
        if complete.exists():
            raise BuildError('Worker resource recovery completion has no journal; preserved.')
        return False
    record = _intent(journal, stage)
    if complete.exists():
        if recovery._read_json(complete) != _completion(record):
            raise BuildError('Worker resource recovery completion differs; preserved.')
        return False
    recovery._path(stage, directory=True)
    return True


@contextmanager
def _lock(path):
    marker = (PURPOSE + '-lock\n').encode()
    if not path.exists():
        try:
            with path.open('xb') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    if _bytes(path) != marker:
        raise BuildError('Worker resource recovery lock is foreign; preserved.')
    with path.open('r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise BuildError('Another worker resource recovery holds the lock.') from None
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise BuildError('Another worker resource recovery holds the lock.') from None
        yield


def _unchanged(stage, record, *, upgraded):
    actual = recovery._inventory(stage)
    if upgraded:
        actual['files'].pop('owner.json', None)
        expected = {'files': {key: value for key, value in record['inventory']['files'].items()
                              if key != 'owner.json'}, 'directories': record['inventory']['directories']}
    else:
        expected = record['inventory']
    if actual != expected:
        raise BuildError('Worker files changed after resource recovery was recorded; preserved.')


def _replace_owner(stage, raw):
    temporary = recovery._path(stage.with_name('.' + stage.name + '.resource-owner-pending-' + uuid4().hex))
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _bytes(temporary) != raw:
        raise BuildError('Worker resource recovery replacement ownership differs; preserved.')
    os.replace(temporary, stage / 'owner.json')


def resume_resource_stage(stage, expected_binding, validate_stage):
    """Upgrade only its source binding; all existing compiled objects remain in place."""
    stage, journal, complete, lock = _paths(stage)
    recovery._path(stage, directory=True)
    recovery._binding(expected_binding)
    if (not journal.exists() and not complete.exists()
            and recovery._read_json(stage / 'owner.json') == expected_binding):
        return False
    with _lock(lock):
        owner_path = stage / 'owner.json'
        owner = recovery._read_json(owner_path)
        if complete.exists() and not journal.exists():
            raise BuildError('Worker resource recovery completion has no journal; preserved.')
        if journal.exists():
            record = _intent(journal, stage, expected_binding)
            if complete.exists():
                if (recovery._read_json(complete) != _completion(record)
                        or owner != expected_binding or _bytes(owner_path) != _new_owner(expected_binding)):
                    raise BuildError('Worker resource recovery completion or current ownership differs; preserved.')
                # Compilation after this committed transition legitimately changes objects.
                return True
        else:
            if owner == expected_binding:
                return False
            _legacy(owner, expected_binding)
            if (stage / 'receipt.json').exists():
                raise BuildError('Completed workers cannot use resource-stage recovery; preserved.')
            before = recovery._inventory(stage)
            raw = _bytes(owner_path)
            validate_stage()
            if recovery._inventory(stage) != before:
                raise BuildError('Worker files changed during resource-stage validation; preserved.')
            record = {'format': 1, 'purpose': PURPOSE, 'stage': str(stage),
                      'original_owner': owner, 'original_owner_hex': raw.hex(),
                      'expected_binding': expected_binding, 'inventory': before}
            recovery._publish(journal, record)
            record = _intent(journal, stage, expected_binding)
        if (stage / 'receipt.json').exists():
            raise BuildError('Completed workers cannot use pending resource-stage recovery; preserved.')
        raw = _bytes(owner_path)
        upgraded = raw == _new_owner(expected_binding)
        if not upgraded and raw != bytes.fromhex(record['original_owner_hex']):
            raise BuildError('Worker resource recovery ownership changed; preserved.')
        _unchanged(stage, record, upgraded=upgraded)
        validate_stage()
        _unchanged(stage, record, upgraded=upgraded)
        if not upgraded:
            _replace_owner(stage, _new_owner(expected_binding))
        if _bytes(owner_path) != _new_owner(expected_binding):
            raise BuildError('Worker resource recovery ownership update differs; preserved.')
        _unchanged(stage, record, upgraded=True)
        recovery._publish(complete, _completion(record))
        return True
