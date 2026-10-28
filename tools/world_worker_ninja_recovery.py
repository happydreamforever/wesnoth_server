"""Preserve reviewed Ninja history and isolate metadata during CMake generation."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import uuid4

from tools.build_alliance_bridge import BuildError
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource

PURPOSE = 'wesnoth-world-worker-ninja-recovery'
GUARD_PURPOSE = 'wesnoth-world-worker-ninja-configure'
INPUT = 'wesnoth_server/tools/world_worker_ninja_recovery.py'
REVIEWED_REPORT_SHA256 = 'ec2ad389eaf2c256b80665d3c0433d6f4a02fb7f8bdb77f7489348b97db930ee'
REVIEWED_SOURCES = {
    recovery.BUILDER_INPUT: 'd51726b6008da84483e4a680ee7178903e6941134483e491088170e6ebaac12d',
    recovery.RECOVERY_INPUT: '0c940d30ec4e6efa1d95571491f1fa687134d7c8a0ce3b75cc2e3b1187514645',
    resource.RESOURCE_INPUT: '2e76df6c3c5b59e4f6291ec3989c3c1b739a11a3a95dd176b203e330c42c08e3',
}
REVIEWED_LOG_SHA256 = '5dcaf12944cd883d3b801a2140e42e09357ce3f5310f9d8e453e8adae5710ace'
REVIEWED_LOG_BYTES = 64517
REVIEWED_BUILDER = REVIEWED_SOURCES[recovery.BUILDER_INPUT]
NAMES = ('.ninja_log', '.ninja_deps')
VARIANTS = ('.ninja_log.restat', '.ninja_log.recompact', '.ninja_deps.recompact')


def _paths(stage):
    stage = recovery._path(stage)
    recovery._path(stage.parent, directory=True)
    if stage.exists():
        recovery._path(stage, directory=True)
    return (stage, stage.with_name(stage.name + '.ninja-recovery.json'),
            stage.with_name(stage.name + '.ninja-recovery-complete.json'))


def _row(path):
    before = recovery._ordinary(path)
    if before.st_size > recovery.MAX_METADATA:
        raise BuildError('Ninja metadata exceeds its bound; preserved.')
    raw = _raw(path)
    if recovery._identity(recovery._ordinary(path)) != recovery._identity(before):
        raise BuildError('Ninja metadata changed while recording; preserved.')
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'mtime_ns': before.st_mtime_ns, 'mode': before.st_mode,
            'attributes': getattr(before, 'st_file_attributes', 0)}


def _raw(path):
    before = recovery._ordinary(path)
    if before.st_size > recovery.MAX_METADATA:
        raise BuildError('Ninja metadata exceeds its bound; preserved.')
    with Path(path).open('rb') as stream:
        if not recovery._same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('Ninja metadata changed while opening; preserved.')
        raw = stream.read(recovery.MAX_METADATA + 1)
    if len(raw) != before.st_size or recovery._identity(recovery._ordinary(path)) != recovery._identity(before):
        raise BuildError('Ninja metadata changed while reading; preserved.')
    return raw


def _equal(path, row):
    if _row(path) != row:
        raise BuildError('Ninja history or its metadata changed; preserved.')


def _metadata(path, row):
    # Only new, owned copies receive the original metadata. Existing source files
    # and their ACLs/attributes are never modified to make deletion succeed.
    recovery._ordinary(path)
    os.chmod(path, stat.S_IMODE(row['mode']))
    os.utime(path, ns=(row['mtime_ns'], row['mtime_ns']))
    if os.name == 'nt':
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.SetFileAttributesW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong)
        api.SetFileAttributesW.restype = ctypes.c_int
        if not api.SetFileAttributesW(str(path), row['attributes'] or 0x80):
            raise OSError(ctypes.get_last_error(), 'New Ninja copy attributes could not be retained.')
    _equal(path, row)


def _copy(source, destination, row, *, resume=False):
    """Exclusive first copy; an interrupted owned copy may append verified bytes."""
    _equal(source, row)
    raw = _raw(source)
    destination = recovery._path(destination)
    if destination.exists():
        if not resume:
            raise BuildError('Ninja restore destination already exists; preserved.')
        before = recovery._ordinary(destination)
        existing = _raw(destination)
        if recovery._identity(recovery._ordinary(destination)) != recovery._identity(before):
            raise BuildError('Ninja restore file changed while inspecting; preserved.')
        if len(existing) > len(raw) or existing != raw[:len(existing)]:
            raise BuildError('Interrupted Ninja restore contains changed bytes; preserved.')
        with destination.open('r+b') as stream:
            if not recovery._same_open_file(destination, before, os.fstat(stream.fileno())):
                raise BuildError('Ninja restore file changed while opening; preserved.')
            stream.seek(0, 2)
            stream.write(raw[len(existing):])
            stream.flush()
            os.fsync(stream.fileno())
            written = os.fstat(stream.fileno())
    else:
        with destination.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            written = os.fstat(stream.fileno())
    _equal(source, row)
    if not recovery._same_open_file(destination, recovery._ordinary(destination), written):
        raise BuildError('Ninja restore destination changed before metadata retention; preserved.')
    _metadata(destination, row)


@contextmanager
def build_lock(stage):
    stage, _, _ = _paths(stage)
    path = recovery._path(stage.with_name(stage.name + '.build.lock'))
    marker = (PURPOSE + '-build-lock\n').encode()
    if not path.exists():
        try:
            with path.open('xb') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    if _raw(path) != marker:
        raise BuildError('World worker build lock is foreign; preserved.')
    before = recovery._ordinary(path)
    with path.open('r+b') as stream:
        if not recovery._same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('World worker build lock changed; preserved.')
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BuildError('Another World worker operation holds the build lock.') from None
        yield


def _legacy(owner, expected):
    recovery._binding(owner)
    recovery._binding(expected)
    prior, current = owner['inputs'], expected['inputs']
    if (INPUT not in current or set(prior) != set(current) - {INPUT} or INPUT in prior
            or any(prior.get(name) != value for name, value in REVIEWED_SOURCES.items())
            or any(value != current[name] for name, value in prior.items() if name != recovery.BUILDER_INPUT)):
        raise BuildError('Only the reviewed incomplete Ninja-stage binding may be recovered.')


def _decoded_report(raw):
    if hashlib.sha256(raw).hexdigest() != REVIEWED_REPORT_SHA256:
        raise BuildError('Use the exact reviewed Ninja diagnostic report; preserved.')
    try:
        report = json.loads(raw)
        if (report['format'] != 1 or report['purpose'] != 'wesnoth-world-worker-ninja-state'
                or report['collection']['complete'] is not True):
            raise ValueError
        contents = base64.b64decode(report['files']['.ninja_log.restat']['raw']['data'], validate=True)
        if len(contents) != REVIEWED_LOG_BYTES or hashlib.sha256(contents).hexdigest() != REVIEWED_LOG_SHA256:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BuildError('Reviewed Ninja diagnostic contents are invalid; preserved.') from None
    return report


def _report_file(path, recorded):
    if recorded['status'] == 'missing':
        if recovery._path(path).exists():
            raise BuildError('A missing Ninja diagnostic file has reappeared; preserved.')
        return
    row = _row(path)
    if recorded.get('status') != 'present' or any(row[key] != recorded[key] for key in row):
        raise BuildError('Ninja metadata no longer matches the reviewed diagnostic; preserved.')
    info = recovery._ordinary(path)
    if any(getattr(info, attr) != recorded[key] for key, attr in (
            ('device', 'st_dev'), ('file_id', 'st_ino'), ('links', 'st_nlink'))):
        raise BuildError('Ninja diagnostic file identity changed; preserved.')


def _log_outputs(raw):
    try:
        lines = raw.decode('utf-8').splitlines()
        if not lines or lines[0] != '# ninja log v7':
            raise ValueError
        paths = []
        for line in lines[1:]:
            start, end, modified, name, command = line.split('\t')
            if (not all(re.fullmatch(r'[0-9]+', value) for value in (start, end, modified))
                    or not re.fullmatch(r'[0-9a-f]+', command) or not resource._relative(name)
                    or PurePosixPath(name).suffix not in ('.obj', '.a')):
                raise ValueError
            paths.append(name)
        if len(paths) != 575 or len(set(paths)) != 575 or sum(x.endswith('.obj') for x in paths) != 571:
            raise ValueError
        return paths
    except (UnicodeError, ValueError):
        raise BuildError('The reviewed Ninja output history is invalid; preserved.') from None


def _verified_report(stage, expected, report_path, validate_stage):
    if report_path is None:
        raise BuildError('First Ninja recovery requires the reviewed -NinjaReport. Preserve every file.')
    raw_report = _raw(report_path)
    report = _decoded_report(raw_report)
    owner_path = stage / 'owner.json'
    owner_raw = _raw(owner_path)
    owner = recovery._read_json(owner_path)
    _legacy(owner, expected)
    if (stage / 'receipt.json').exists():
        raise BuildError('Completed workers cannot use reviewed Ninja recovery; preserved.')
    _report_file(owner_path, report['checks']['ownership'])
    for name, row in report['files'].items():
        if name not in (*NAMES, *VARIANTS, 'build.ninja'):
            raise BuildError('Unexpected Ninja report file; preserved.')
        _report_file(stage / 'engine' / name, row)
    _, prior_path, complete, _ = resource._paths(stage)
    _report_file(prior_path, report['checks']['resource_journal'])
    prior = resource._intent(prior_path, stage, owner)
    if not complete.exists() or recovery._read_json(complete) != resource._completion(prior):
        raise BuildError('Resource continuation was not completed; preserved.')
    inventory = recovery._inventory(stage)
    log_row = prior['inventory']['files']['engine/.ninja_log']
    if log_row['sha256'] != REVIEWED_LOG_SHA256 or log_row['bytes'] != REVIEWED_LOG_BYTES:
        raise BuildError('Original Ninja log proof differs; preserved.')
    if inventory['files']['engine/.ninja_deps'] != prior['inventory']['files']['engine/.ninja_deps']:
        raise BuildError('Original Ninja dependency history changed; preserved.')
    for name in _log_outputs(_raw(stage / 'engine/.ninja_log.restat')):
        key = 'engine/' + name
        if inventory['files'].get(key) != prior['inventory']['files'].get(key) or key not in prior['inventory']['files']:
            raise BuildError('A recorded compiled output changed; preserved.')
    validate_stage()
    if recovery._inventory(stage) != inventory:
        raise BuildError('Worker files changed during Ninja validation; preserved.')
    return {'format': 1, 'purpose': PURPOSE, 'stage': str(stage), 'report_hex': raw_report.hex(),
            'original_owner_hex': owner_raw.hex(), 'original_owner': owner,
            'expected_binding': expected, 'inventory': inventory,
            'resource_journal_sha256': hashlib.sha256(_raw(prior_path)).hexdigest(),
            'log_row': log_row}


def _intent(path, stage, expected=None):
    record = recovery._read_json(path)
    if (not isinstance(record, dict) or set(record) != {'format', 'purpose', 'stage', 'report_hex',
            'original_owner_hex', 'original_owner', 'expected_binding', 'inventory',
            'resource_journal_sha256', 'log_row'} or record['format'] != 1
            or record['purpose'] != PURPOSE or record['stage'] != str(stage)):
        raise BuildError('Ninja recovery journal is invalid; preserved.')
    _legacy(record['original_owner'], record['expected_binding'])
    if expected is not None and record['expected_binding'] != expected:
        raise BuildError('Ninja recovery belongs to different inputs; preserved.')
    resource._inventory_record(record['inventory'])
    try:
        report = _decoded_report(bytes.fromhex(record['report_hex']))
        raw = bytes.fromhex(record['original_owner_hex'])
        if (json.loads(raw) != record['original_owner']
                or hashlib.sha256(raw).hexdigest() != record['inventory']['files']['owner.json']['sha256']
                or len(raw) != record['inventory']['files']['owner.json']['bytes']
                or record['resource_journal_sha256'] != report['checks']['resource_journal']['sha256']
                or record['log_row'] != {key: report['checks']['resource_journal']['files']['.ninja_log'][key]
                                        for key in ('bytes', 'sha256', 'mtime_ns', 'mode', 'attributes')}):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BuildError('Ninja recovery provenance differs; preserved.') from None
    return record


def _completion(record):
    return {'format': 1, 'purpose': PURPOSE, 'journal_sha256': recovery._hash(record),
            'status': 'history_restored_not_verified_build'}


def pending(stage):
    stage, journal, complete = _paths(stage)
    if not journal.exists():
        if complete.exists():
            raise BuildError('Ninja completion has no journal; preserved.')
        return False
    record = _intent(journal, stage)
    if complete.exists():
        if recovery._read_json(complete) != _completion(record):
            raise BuildError('Ninja recovery completion differs; preserved.')
        return False
    recovery._path(stage, directory=True)
    return True


def _repair_unchanged(stage, record):
    actual = recovery._inventory(stage)
    original = record['inventory']
    actual['files'].pop('engine/.ninja_log', None)
    actual['files'].pop('owner.json', None)
    expected = {'directories': original['directories'],
                'files': {k: v for k, v in original['files'].items() if k != 'owner.json'}}
    if actual != expected:
        raise BuildError('Worker files changed during pending Ninja recovery; preserved.')
    prior = stage.with_name(stage.name + '.resource-recovery.json')
    if hashlib.sha256(_raw(prior)).hexdigest() != record['resource_journal_sha256']:
        raise BuildError('Original resource journal changed; preserved.')


def recover_reviewed(stage, expected_binding, report_path, validate_stage):
    """Restore exactly the reviewed missing log, retaining its temporary source."""
    stage, journal, complete = _paths(stage)
    recovery._path(stage, directory=True)
    recovery._binding(expected_binding)
    if journal.exists():
        record = _intent(journal, stage, expected_binding)
        if complete.exists():
            if (recovery._read_json(complete) != _completion(record)
                    or recovery._read_json(stage / 'owner.json') != expected_binding):
                raise BuildError('Ninja recovery completion or ownership differs; preserved.')
            return True
        if report_path is not None and _raw(report_path).hex() != record['report_hex']:
            raise BuildError('The supplied Ninja report differs from the retained report; preserved.')
    else:
        if complete.exists():
            raise BuildError('Ninja completion has no journal; preserved.')
        if report_path is None and recovery._read_json(stage / 'owner.json') == expected_binding:
            return False
        record = _verified_report(stage, expected_binding, report_path, validate_stage)
        recovery._publish(journal, record)
        record = _intent(journal, stage, expected_binding)
    if (stage / 'receipt.json').exists():
        raise BuildError('Completed workers cannot resume pending Ninja recovery; preserved.')
    owner_raw = _raw(stage / 'owner.json')
    if owner_raw not in (bytes.fromhex(record['original_owner_hex']), resource._new_owner(expected_binding)):
        raise BuildError('Ninja recovery ownership changed; preserved.')
    _repair_unchanged(stage, record)
    validate_stage()
    _repair_unchanged(stage, record)
    source = stage / 'engine/.ninja_log.restat'
    source_row = record['inventory']['files']['engine/.ninja_log.restat']
    _copy(source, stage / 'engine/.ninja_log', source_row, resume=True)
    _metadata(stage / 'engine/.ninja_log', record['log_row'])
    _repair_unchanged(stage, record)
    _equal(stage / 'engine/.ninja_log', record['log_row'])
    if _raw(stage / 'owner.json') != owner_raw:
        raise BuildError('Ninja recovery ownership changed before publication; preserved.')
    if owner_raw != resource._new_owner(expected_binding):
        resource._replace_owner(stage, resource._new_owner(expected_binding))
    if _raw(stage / 'owner.json') != resource._new_owner(expected_binding):
        raise BuildError('Ninja recovery owner update differs; preserved.')
    _repair_unchanged(stage, record)
    recovery._publish(complete, _completion(record))
    return True


def _guard_record(directory, stage):
    record = recovery._read_json(directory / 'journal.json')
    if (not isinstance(record, dict) or set(record) != {'format', 'purpose', 'stage', 'owner_sha256', 'files', 'variants'}
            or record['format'] != 1 or record['purpose'] != GUARD_PURPOSE or record['stage'] != str(stage)
            or set(record['files']) != set(NAMES) or set(record['variants']) != set(VARIANTS)
            or not isinstance(record['owner_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['owner_sha256'])):
        raise BuildError('Ninja configure journal is invalid; preserved.')
    # Reuse the strict inventory-row validator, without requiring live files.
    rows = {name: row for name, row in {**record['files'], **record['variants']}.items() if row is not None}
    resource._inventory_record({'files': {'owner.json': {'bytes': 0, 'sha256': '0' * 64,
                                'mode': 0, 'mtime_ns': 0, 'attributes': 0}, **rows}, 'directories': []})
    return record


def _guard_complete(record):
    return {'format': 1, 'purpose': GUARD_PURPOSE, 'journal_sha256': recovery._hash(record),
            'status': 'original_ninja_metadata_restored'}


def _guards(stage):
    stage, _, _ = _paths(stage)
    active = []
    for path in sorted(stage.parent.glob(stage.name + '.ninja-configure-*')):
        if not re.fullmatch(re.escape(stage.name) + r'\.ninja-configure-[0-9a-f]{32}', path.name):
            raise BuildError('Unknown Ninja configure recovery folder; preserved.')
        recovery._path(path, directory=True)
        if not (path / 'journal.json').exists():
            # Backups are written before the journal; no live file can yet have
            # been removed. Retain incomplete pre-journal attempts as evidence.
            continue
        record = _guard_record(path, stage)
        complete = path / 'complete.json'
        if complete.exists():
            if recovery._read_json(complete) != _guard_complete(record):
                raise BuildError('Ninja configure completion differs; preserved.')
        else:
            active.append((path, record))
    if len(active) > 1:
        raise BuildError('Multiple pending Ninja configure transactions; preserved.')
    return active


def configure_pending(stage):
    return bool(_guards(stage))


def _unchanged_variants(engine, record):
    for name, row in record['variants'].items():
        path = recovery._path(engine / name)
        if row is None:
            if path.exists():
                raise BuildError('Unexpected Ninja temporary appeared during configure; preserved.')
        else:
            _equal(path, row)


def _restore_guard(stage, directory, record):
    engine = recovery._path(stage / 'engine', directory=True)
    if hashlib.sha256(_raw(stage / 'owner.json')).hexdigest() != record['owner_sha256']:
        raise BuildError('Worker ownership changed during configure; preserved.')
    _unchanged_variants(engine, record)
    for name, row in record['files'].items():
        if row is not None:
            _equal(directory / name, row)
    restoring = directory / 'restoring.json'
    marker = {'format': 1, 'purpose': GUARD_PURPOSE, 'journal_sha256': recovery._hash(record)}
    is_restoring = restoring.exists()
    if is_restoring and recovery._read_json(restoring) != marker:
        raise BuildError('Ninja restore marker differs; preserved.')
    # Before restore is authorized, an original may be intact or absent only.
    # CMake must not create replacement history while the originals are held.
    for name, row in record['files'].items():
        path = recovery._path(engine / name)
        if path.exists():
            if row is None:
                raise BuildError('Unexpected Ninja history appeared during configure; preserved.')
            if not is_restoring:
                _equal(path, row)
    if not is_restoring:
        recovery._publish(restoring, marker)
    for name, row in record['files'].items():
        if row is not None:
            path = engine / name
            if path.exists() and _row(path) == row:
                continue
            _copy(directory / name, path, row, resume=True)
    _unchanged_variants(engine, record)
    for name, row in record['files'].items():
        if row is not None:
            _equal(engine / name, row)
    recovery._publish(directory / 'complete.json', _guard_complete(record))


def resume_configure(stage):
    """Restore an interrupted configure before inspecting or changing the stage."""
    stage, _, _ = _paths(stage)
    guards = _guards(stage)
    if not guards:
        return False
    directory, record = guards[0]
    _restore_guard(stage, directory, record)
    return True


def configure(stage, command, environment, run):
    """Call CMake with checked logs held aside; always restore their history."""
    stage, _, _ = _paths(stage)
    recovery._path(stage, directory=True)
    resume_configure(stage)
    engine = recovery._path(stage / 'engine')
    if not engine.exists():
        engine.mkdir()
    recovery._path(engine, directory=True)
    owner_sha256 = hashlib.sha256(_raw(stage / 'owner.json')).hexdigest()
    files = {name: _row(engine / name) if recovery._path(engine / name).exists() else None for name in NAMES}
    variants = {name: _row(engine / name) if recovery._path(engine / name).exists() else None for name in VARIANTS}
    if files['.ninja_log'] is None and (files['.ninja_deps'] is not None or any(row is not None for row in variants.values())):
        raise BuildError('Missing Ninja history needs reviewed recovery before configuration.')
    directory = stage.with_name(stage.name + '.ninja-configure-' + uuid4().hex)
    directory.mkdir()
    for name, row in files.items():
        if row is not None:
            _copy(engine / name, directory / name, row)
    record = {'format': 1, 'purpose': GUARD_PURPOSE, 'stage': str(stage),
              'owner_sha256': owner_sha256, 'files': files, 'variants': variants}
    recovery._publish(directory / 'journal.json', record)
    try:
        for name, row in files.items():
            if row is not None:
                _equal(engine / name, row)
                (engine / name).unlink()
        _unchanged_variants(engine, record)
        configured = list(command)
        regeneration = [str(value) for value in configured if str(value).startswith('-DCMAKE_SUPPRESS_REGENERATION')]
        if regeneration:
            if regeneration != ['-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON']:
                raise BuildError('CMake regeneration must remain suppressed.')
        else:
            configured.append('-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON')
        return run(configured, environment)
    finally:
        _restore_guard(stage, directory, record)
        print('WORLD WORKER NINJA CONFIGURE GUARDED; original history restored', flush=True)
