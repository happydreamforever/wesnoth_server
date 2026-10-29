"""Finalize the reviewed linked worker without configuring or compiling it again."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from uuid import uuid4

from tools.build_alliance_bridge import BuildError
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_ninja_recovery as ninja
from tools import world_worker_account_recovery as account

PURPOSE = 'wesnoth-world-worker-version-completion'
INPUT = 'wesnoth_server/tools/world_worker_version_completion.py'
VERSION = '1.19.26'
REVIEWED_REPORT_SHA256 = '5127d2a83fd5ada52cd3200414f741846f4e4b532f3d3407319fa0e240f9a729'
REVIEWED_BINDING_SHA256 = 'e229a8f72b9cf544182a9313e63f88771bbb0426f4d4749adebe320187be6126'
LEGACY_BUILDERS = frozenset({
    '03c1c609e7dbf78903f8bd4f7064bc5440d107b7c59d0d65ccdba3b7ba5e7867',
    '88d10ca21b29b7406306ea760fb689510af369f6d33593c2aa441ae4733fc27f',
})
MAX_FILE = 512 * 1024 * 1024


def _file(path):
    before = recovery._ordinary(path)
    if not 0 < before.st_size <= MAX_FILE:
        raise BuildError('Worker completion input has an unexpected size; preserved.')
    with Path(path).open('rb') as stream:
        if not recovery._same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('Worker completion input changed while opening; preserved.')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        opened = os.fstat(stream.fileno())
    after = recovery._ordinary(path)
    if (recovery._identity(before) != recovery._identity(after)
            or not recovery._same_open_file(path, after, opened)):
        raise BuildError('Worker completion input changed while hashing; preserved.')
    return {'bytes': before.st_size, 'sha256': digest, 'mtime_ns': before.st_mtime_ns,
            'mode': before.st_mode, 'attributes': getattr(before, 'st_file_attributes', 0),
            'device': before.st_dev, 'file_id': before.st_ino, 'links': before.st_nlink}


def _report(raw):
    if hashlib.sha256(raw).hexdigest() != REVIEWED_REPORT_SHA256:
        raise BuildError('Use only the reviewed successful worker version JSON; preserve all reports.')
    value = json.loads(raw)
    if (value.get('format') != 1 or value.get('purpose') != 'wesnoth-world-worker-version-diagnostic'
            or value.get('release') != 1192624 or value.get('collection') != {'complete': True}
            or value.get('binding_input_count') != 1707 or value.get('build_performed') is not False
            or value.get('receipt_written') is not False or value.get('scope') != 'existing-worker-version-only'
            or value.get('artifacts', {}).get('binding_sha256') != REVIEWED_BINDING_SHA256
            or len(value.get('artifacts', {}).get('bin', {})) != 54
            or value.get('result', {}).get('outcome') != 'version_match'
            or value['result'].get('version_matches') is not True
            or value['result'].get('exit_code') != 0
            or value['result'].get('stdout', {}).get('version_text') != VERSION
            or value['artifacts'].get('version_header', {}).get('declared_version') != VERSION
            or value.get('preservation') != {name: True for name in (
                'bin_unchanged', 'dependency_receipt_unchanged', 'linked_executable_unchanged',
                'no_receipt_created', 'owner_unchanged', 'source_binding_unchanged', 'version_header_unchanged')}):
        raise BuildError('Reviewed worker version evidence is incomplete; preserved.')
    return value


def _legacy(owner, expected):
    recovery._binding(owner)
    recovery._binding(expected)
    prior, current = owner['inputs'], expected['inputs']
    if (recovery._hash(owner) != REVIEWED_BINDING_SHA256 or len(prior) != 1707
            or prior.get(recovery.BUILDER_INPUT) not in LEGACY_BUILDERS
            or INPUT not in current or INPUT in prior or set(prior) != set(current) - {INPUT}
            or any(value != current[name] for name, value in prior.items() if name != recovery.BUILDER_INPUT)):
        raise BuildError('Only the reviewed linked worker may receive this version-verification update.')


def _paths(stage):
    stage = recovery._path(stage)
    recovery._path(stage.parent, directory=True)
    if stage.exists(): recovery._path(stage, directory=True)
    return (stage, stage.with_name(stage.name + '.version-completion.json'),
            stage.with_name(stage.name + '.version-completion-complete.json'),
            stage.with_name(stage.name + '.version-completion.lock'))


def _history(stage):
    if account.account_recovery_pending(stage):
        raise BuildError('Earlier account-source recovery is incomplete; preserve its journals.')
    rows = account._history(stage)
    for suffix in ('.account-recovery.json', '.account-recovery-complete.json',
                   '.ninja-recovery.json', '.ninja-recovery-complete.json',
                   '.resource-recovery.json', '.resource-recovery-complete.json'):
        path = stage.with_name(stage.name + suffix)
        rows[path.name] = ninja._row(path)
    return rows


def _artifacts(stage, report, *, owner_required):
    expected = report['artifacts']
    binary = recovery._path(stage / 'bin', directory=True)
    names = sorted(path.name for path in binary.iterdir())
    if names != sorted(expected['bin']):
        raise BuildError('Reviewed worker bin inventory changed; preserved.')
    for name in names:
        if name != 'world-worker.exe' and not re.fullmatch(r'[A-Za-z0-9_.+\-]+\.dll', name, re.I):
            raise BuildError('Reviewed worker binary name is invalid; preserved.')
        if _file(binary / name) != expected['bin'][name]:
            raise BuildError('A reviewed worker binary changed; preserved.')
    for path, row in (
            (stage / 'engine/world-worker.exe', expected['linked_executable']),
            (stage / 'source/src/wesconfig.h', expected['version_header']['file']),
            (stage.parent / 'world-worker-prefix/receipt.json', expected['prefix_receipt'])):
        if _file(path) != row:
            raise BuildError('A reviewed worker artifact changed; preserved.')
    if owner_required and _file(stage / 'owner.json') != expected['owner']:
        raise BuildError('Reviewed worker ownership changed; preserved.')


def _receipt(value, expected, report):
    if (not isinstance(value, dict) or set(value) != {'binding', 'executable', 'dlls', 'version',
            'game_data', 'game_data_files', 'build_tools'} or value['binding'] != expected
            or value['version'] != VERSION
            or value['executable'] != {key: report['artifacts']['bin']['world-worker.exe'][key]
                                      for key in ('bytes', 'sha256')}
            or not isinstance(value['game_data'], str) or not value['game_data']
            or not isinstance(value['game_data_files'], dict) or not value['game_data_files']
            or not isinstance(value['build_tools'], dict) or set(value['build_tools']) != {'cmake', 'ninja'}
            or not isinstance(value['dlls'], dict) or set(value['dlls']) != {'private', 'windows_system'}
            or not isinstance(value['dlls']['windows_system'], list)):
        raise BuildError('Worker completion receipt is invalid; preserved.')
    expected_dlls = {name.casefold(): {'filename': name, **{key: row[key] for key in ('bytes', 'sha256')}}
                     for name, row in report['artifacts']['bin'].items() if name != 'world-worker.exe'}
    if value['dlls']['private'] != expected_dlls:
        raise BuildError('Worker completion DLL closure differs from reviewed binaries; preserved.')
    return value


def _record(path, stage, expected=None):
    value = recovery._read_json(path)
    if (not isinstance(value, dict) or set(value) != {'format', 'purpose', 'stage', 'report_hex',
            'original_owner', 'original_owner_hex', 'expected_binding', 'inventory', 'history', 'receipt'}
            or type(value['format']) is not int or value['format'] != 1
            or value['purpose'] != PURPOSE or value['stage'] != str(stage)
            or not isinstance(value['history'], dict)):
        raise BuildError('Worker version completion journal is invalid; preserved.')
    try:
        report = _report(bytes.fromhex(value['report_hex']))
        raw = bytes.fromhex(value['original_owner_hex'])
        if (json.loads(raw) != value['original_owner'] or len(raw) != report['artifacts']['owner']['bytes']
                or hashlib.sha256(raw).hexdigest() != report['artifacts']['owner']['sha256']):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise BuildError('Worker version completion evidence differs; preserved.') from None
    _legacy(value['original_owner'], value['expected_binding'])
    if expected is not None and value['expected_binding'] != expected:
        raise BuildError('Worker version completion belongs to another source revision; preserved.')
    resource._inventory_record(value['inventory'])
    resource._inventory_record({'files': {'owner.json': value['inventory']['files'].get('owner.json'),
                                         **value['history']}, 'directories': []})
    if ('owner.json' not in value['inventory']['files'] or 'receipt.json' in value['inventory']['files']
            or value['inventory']['files']['owner.json'] != {
                key: report['artifacts']['owner'][key] for key in ('bytes', 'sha256', 'mtime_ns', 'mode', 'attributes')}
            or any(not name.startswith(stage.name + '.') for name in value['history'])):
        raise BuildError('Worker version completion inventory is invalid; preserved.')
    _receipt(value['receipt'], value['expected_binding'], report)
    return value


def _completion(record):
    return {'format': 1, 'purpose': PURPOSE, 'journal_sha256': recovery._hash(record),
            'receipt_sha256': recovery._hash(record['receipt']), 'status': 'verified_worker_completed'}


def pending(stage):
    stage, journal, complete, _ = _paths(stage)
    if not journal.exists():
        if complete.exists(): raise BuildError('Worker version completion has no journal; preserved.')
        return False
    record = _record(journal, stage)
    if complete.exists():
        if recovery._read_json(complete) != _completion(record):
            raise BuildError('Worker version completion marker differs; preserved.')
        return False
    recovery._path(stage, directory=True)
    return True


def _unchanged(stage, record):
    actual = recovery._inventory(stage)
    for name in ('owner.json', 'receipt.json'): actual['files'].pop(name, None)
    expected = {'directories': record['inventory']['directories'],
                'files': {name: row for name, row in record['inventory']['files'].items() if name != 'owner.json'}}
    if actual != expected or _history(stage) != record['history']:
        raise BuildError('Worker files or prior recovery history changed during completion; preserved.')


def _publish_receipt(stage, value):
    """Keep any interrupted partial publication outside the owned build stage."""
    raw = resource._new_owner(value)
    temporary = recovery._path(stage.with_name('.' + stage.name + '.version-receipt-pending-' + uuid4().hex))
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    recovery.packages.publish_artifact(temporary, stage / 'receipt.json', {
        'filename': 'receipt.json', 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})


def finalize_reviewed(stage, expected_binding, report_path, validate_stage):
    """The caller holds the full-operation build lock; no CMake/Ninja is run here."""
    stage, journal, complete, lock = _paths(stage)
    recovery._path(stage, directory=True)
    recovery._binding(expected_binding)
    with resource._lock(lock):
        owner_path = stage / 'owner.json'
        owner = recovery._read_json(owner_path)
        if complete.exists() and not journal.exists():
            raise BuildError('Worker version completion has no journal; preserved.')
        new_intent = not journal.exists()
        if not new_intent:
            record = _record(journal, stage, expected_binding)
            if report_path is not None and ninja._raw(report_path).hex() != record['report_hex']:
                raise BuildError('Supplied worker version report differs from retained evidence; preserved.')
            report = _report(bytes.fromhex(record['report_hex']))
        else:
            if report_path is None:
                raise BuildError('Use -VersionReportPath with the reviewed successful worker version JSON.')
            raw_report = ninja._raw(report_path)
            report = _report(raw_report)
            _legacy(owner, expected_binding)
            if (stage / 'receipt.json').exists():
                raise BuildError('An existing completed worker cannot use this incomplete-stage finalization.')
            _artifacts(stage, report, owner_required=True)
            inventory = recovery._inventory(stage)
            history = _history(stage)
            receipt = _receipt(validate_stage(), expected_binding, report)
            _artifacts(stage, report, owner_required=True)
            record = {'format': 1, 'purpose': PURPOSE, 'stage': str(stage), 'report_hex': raw_report.hex(),
                      'original_owner': owner, 'original_owner_hex': ninja._raw(owner_path).hex(),
                      'expected_binding': expected_binding, 'inventory': inventory,
                      'history': history, 'receipt': receipt}
            _unchanged(stage, record)
            recovery._publish(journal, record)
            record = _record(journal, stage, expected_binding)
        if complete.exists():
            if (recovery._read_json(complete) != _completion(record)
                    or owner != expected_binding
                    or ninja._raw(owner_path) != resource._new_owner(expected_binding)
                    or ninja._raw(stage / 'receipt.json') != resource._new_owner(record['receipt'])):
                raise BuildError('Completed worker version publication differs; preserved.')
            _artifacts(stage, report, owner_required=False)
            if _history(stage) != record['history']:
                raise BuildError('Completed worker recovery history changed; preserved.')
            return record['receipt']
        raw_owner = ninja._raw(owner_path)
        if raw_owner not in (bytes.fromhex(record['original_owner_hex']), resource._new_owner(expected_binding)):
            raise BuildError('Worker ownership changed during version completion; preserved.')
        receipt_path = stage / 'receipt.json'
        if receipt_path.exists() and ninja._raw(receipt_path) != resource._new_owner(record['receipt']):
            raise BuildError('Worker receipt changed during version completion; preserved.')
        # Every resumption revalidates live data/tools and the version. This does
        # not rewrite any artifact, source overlay or former recovery journal.
        if not new_intent:
            _artifacts(stage, report, owner_required=raw_owner == bytes.fromhex(record['original_owner_hex']))
            _unchanged(stage, record)
            if _receipt(validate_stage(), expected_binding, report) != record['receipt']:
                raise BuildError('Worker validation changed during version completion; preserved.')
            _artifacts(stage, report, owner_required=raw_owner == bytes.fromhex(record['original_owner_hex']))
            _unchanged(stage, record)
        if ninja._raw(owner_path) != raw_owner:
            raise BuildError('Worker ownership changed before completion publication; preserved.')
        if raw_owner != resource._new_owner(expected_binding):
            resource._replace_owner(stage, resource._new_owner(expected_binding))
        if ninja._raw(owner_path) != resource._new_owner(expected_binding):
            raise BuildError('Worker completion ownership update differs; preserved.')
        if not receipt_path.exists(): _publish_receipt(stage, record['receipt'])
        if ninja._raw(receipt_path) != resource._new_owner(record['receipt']):
            raise BuildError('Worker completion receipt publication differs; preserved.')
        _unchanged(stage, record)
        _artifacts(stage, report, owner_required=False)
        recovery._publish(complete, _completion(record))
        return record['receipt']


def _capture(command, environment, cwd, *, timeout=30, limit=65536):
    """Bound stdout/stderr and process lifetime; never emit arbitrary child text."""
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    overflow = threading.Event()
    errors = []
    started = time.monotonic()
    try:
        process = subprocess.Popen([str(part) for part in command], env=environment, cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=0x08000000 if os.name == 'nt' else 0)
    except OSError:
        raise BuildError('Full native engine version probe could not start; preserve its artifacts.') from None
    def consume(name, pipe):
        try:
            while chunk := pipe.read(4096):
                available = max(0, limit - len(streams[name]))
                streams[name].extend(chunk[:available])
                if len(chunk) > available: overflow.set()
        except (OSError, ValueError): errors.append(name)
        finally: pipe.close()
    threads = [threading.Thread(target=consume, args=(name, pipe), daemon=True)
               for name, pipe in (('stdout', process.stdout), ('stderr', process.stderr))]
    for thread in threads: thread.start()
    timed_out = False
    while process.poll() is None:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0 or overflow.is_set():
            timed_out = remaining <= 0
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired): errors.append('cleanup')
            break
        try: process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired: pass
    for thread in threads: thread.join(timeout=5)
    if (timed_out or overflow.is_set() or errors or process.returncode != 0
            or any(thread.is_alive() for thread in threads)):
        raise BuildError('Full native engine version probe failed or exceeded its bound; artifacts preserved.')
    return bytes(streams['stdout'])


def probe_version(executable, environment, scratch_parent):
    executable = recovery._path(executable)
    before = _file(executable)
    parent = recovery._path(scratch_parent, directory=True)
    normalized = {}
    for key, value in environment.items():
        if key.upper() in normalized:
            raise BuildError('Duplicate Windows environment aliases; no version probe was run.')
        normalized[key.upper()] = value
    system = normalized.get('SYSTEMROOT')
    if not isinstance(system, str) or not system.strip():
        raise BuildError('Windows SystemRoot is missing; no version probe was run.')
    system = recovery._path(system, directory=True)
    system32 = recovery._path(system / 'System32', directory=True)
    scratch = parent / ('world-worker-version-verify-' + uuid4().hex)
    scratch.mkdir()
    folders = {}
    for name in ('userdata', 'cache', 'temp', 'profile', 'appdata', 'localappdata'):
        folders[name] = scratch / name
        folders[name].mkdir()
    clean = {'SYSTEMROOT': str(system), 'WINDIR': str(system),
             'PATH': str(executable.parent) + os.pathsep + str(system32),
             'TEMP': str(folders['temp']), 'TMP': str(folders['temp']),
             'USERPROFILE': str(folders['profile']), 'APPDATA': str(folders['appdata']),
             'LOCALAPPDATA': str(folders['localappdata'])}
    raw = _capture([executable, '--simple-version', '--no-log-to-file', '--wnoconsole',
                    '--userdata-dir', folders['userdata'], '--usercache-dir', folders['cache']], clean, scratch)
    if _file(executable) != before:
        raise BuildError('Full native engine changed during its version probe; artifacts preserved.')
    if raw.strip() != VERSION.encode('ascii'):
        raise BuildError('Full native engine version differs; required version is 1.19.26.')
    return VERSION
