"""Capture the stopped worker's fixed Ninja metadata without changing its build."""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path(os.path.abspath(__file__)).parents[1]
PURPOSE = 'wesnoth-world-worker-ninja-state'
MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_BYTES = 64 * 1024 * 1024
TEXT_NAMES = ('.ninja_log', '.ninja_log.restat', '.ninja_log.recompact')
FILE_NAMES = (*TEXT_NAMES, '.ninja_deps', '.ninja_deps.recompact', 'build.ninja')
SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
OPEN_REPARSE_POINT = 0x00200000
BACKUP_SEMANTICS = 0x02000000
FILE_ACCESS = {'metadata': 0, 'read': 0x80000000, 'write': 0x40000000, 'delete': 0x00010000}
DIRECTORY_ACCESS = {'metadata': 0, 'add_file': 0x2, 'delete_child': 0x40}
SOURCE_NAMES = ('build_world_worker.py', 'world_worker_recovery.py', 'world_worker_resource_recovery.py')


class InspectionError(Exception):
    pass


def _error(error):
    return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
            'winerror': getattr(error, 'winerror', None)}


def checked_path(value):
    path = Path(os.path.abspath(value))
    if str(path).startswith('\\\\'):
        raise InspectionError('Network or device paths are not allowed.')
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            return path, False
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise InspectionError('Linked or redirected paths are not inspected.')
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise InspectionError('A path ancestor is not a directory.')
    return path, True


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_nlink, getattr(info, 'st_file_attributes', 0))


def _metadata(info):
    return {'bytes': info.st_size, 'mode': info.st_mode, 'mtime_ns': info.st_mtime_ns,
            'links': info.st_nlink, 'attributes': getattr(info, 'st_file_attributes', 0),
            'device': info.st_dev, 'file_id': info.st_ino}


def _read_file(path, *, raw_limit=0):
    path, exists = checked_path(path)
    if not exists:
        return {'status': 'missing'}, None
    before = path.lstat()
    metadata = _metadata(before)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        return {'status': 'rejected', 'reason': 'ordinary_single_link_file_required', **metadata}, None
    if before.st_size > MAX_BYTES:
        return {'status': 'too_large', 'limit': MAX_BYTES, **metadata}, None
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        return {'status': 'read_error', 'error': _error(error), **metadata}, None
    digest = hashlib.sha256()
    data = bytearray() if raw_limit and before.st_size <= raw_limit else None
    total = 0
    with os.fdopen(descriptor, 'rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            return {'status': 'changed', 'phase': 'open', **metadata}, None
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                return {'status': 'too_large', 'phase': 'read', 'limit': MAX_BYTES, **metadata}, None
            digest.update(chunk)
            if data is not None:
                if total > raw_limit:
                    data = None
                else:
                    data.extend(chunk)
        opened_after = os.fstat(stream.fileno())
    checked_path(path)
    after = path.lstat()
    if (_identity(before) != _identity(opened_after) or _identity(before) != _identity(after)
            or total != before.st_size):
        return {'status': 'changed', 'phase': 'read', **metadata}, None
    return {'status': 'present', 'sha256': digest.hexdigest(), **metadata}, bytes(data) if data is not None else None


class _WindowsAPI:
    def __init__(self):
        library = ctypes.WinDLL('kernel32', use_last_error=True)
        self.create = library.CreateFileW
        self.create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        self.create.restype = wintypes.HANDLE
        self.close = library.CloseHandle
        self.close.argtypes = (wintypes.HANDLE,)
        self.close.restype = wintypes.BOOL
        self.error = ctypes.get_last_error


def probe_access(path, *, directory=False, _api=None):
    """Request access and close immediately; never read/write/delete through these handles."""
    path, exists = checked_path(path)
    if not exists:
        return {'status': 'missing'}
    info = path.lstat()
    if (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and (
            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
        return {'status': 'rejected', 'reason': 'unexpected_file_type'}
    api = _api if _api is not None else _WindowsAPI()
    flags = OPEN_REPARSE_POINT | (BACKUP_SEMANTICS if directory else 0)
    result = {'status': 'observed', 'sharing': SHARE_ALL, 'disposition': OPEN_EXISTING,
              'flags': flags, 'probes': {}}
    for name, access in (DIRECTORY_ACCESS if directory else FILE_ACCESS).items():
        handle = api.create(str(path), access, SHARE_ALL, None, OPEN_EXISTING, flags, None)
        if handle == ctypes.c_void_p(-1).value:
            result['probes'][name] = {'access': access, 'opened': False,
                                     'winerror': api.error(), 'close_error': 0}
        else:
            row = {'access': access, 'opened': True, 'winerror': 0, 'close_error': 0}
            if not api.close(handle):
                row['close_error'] = api.error()
                result['status'] = 'close_error'
            result['probes'][name] = row
    checked_path(path)
    if _identity(path.lstat()) != _identity(info):
        result['status'] = 'changed'
    return result


def inspect_file(path, *, include_raw=False, access_probe=None):
    try:
        result, raw = _read_file(path, raw_limit=MAX_RAW_BYTES if include_raw else 0)
        if include_raw and result['status'] == 'present':
            result['raw'] = ({'status': 'captured', 'encoding': 'base64',
                              'data': base64.b64encode(raw).decode('ascii')}
                             if raw is not None else {'status': 'omitted_size_limit', 'limit': MAX_RAW_BYTES})
        if result['status'] in ('present', 'read_error', 'too_large'):
            result['access'] = (access_probe or probe_access)(path)
        return result
    except (OSError, InspectionError) as error:
        return {'status': 'read_error', 'error': _error(error)}


def _json_record(path):
    result, raw = _read_file(path, raw_limit=MAX_BYTES)
    if result['status'] != 'present':
        return result, None
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise InspectionError('Repeated metadata field.')
            value[key] = item
        return value
    try:
        return result, json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, InspectionError, RecursionError):
        return {'status': 'invalid_json', **{key: value for key, value in result.items() if key != 'status'}}, None


def _binding(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'purpose', 'release', 'inputs'}
            or type(value['format']) is not int or value['format'] != 1
            or value['purpose'] != 'wesnoth-full-native-world-worker'
            or type(value['release']) is not int or value['release'] != 1192624
            or not isinstance(value['inputs'], dict) or not 0 < len(value['inputs']) <= 100000):
        return False
    for name, digest in value['inputs'].items():
        if (not isinstance(name, str) or not name or len(name) > 2048
                or name.startswith('/') or any(c in name for c in ('\\', ':'))
                or any(part in ('', '.', '..') for part in name.split('/'))
                or any(ord(c) < 32 for c in name)
                or not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            return False
    return True


def _collect_ownership(repo, stage):
    result, owner = _json_record(stage / 'owner.json')
    if not _binding(owner):
        if result['status'] == 'present': result['status'] = 'invalid_binding'
        return result, None
    result.update(format=owner['format'], purpose=owner['purpose'], release=owner['release'],
                  input_count=len(owner['inputs']), sources={})
    for name in SOURCE_NAMES:
        source, _ = _read_file(repo / 'tools' / name)
        recorded = owner['inputs'].get('wesnoth_server/tools/' + name)
        result['sources'][name] = {'status': source['status'], 'recorded_sha256': recorded,
                                  'current_sha256': source.get('sha256'),
                                  'matches': source['status'] == 'present' and recorded == source['sha256']}
    return result, owner


def _collect_prior(stage, owner):
    path = stage.with_name(stage.name + '.resource-recovery.json')
    result, record = _json_record(path)
    if record is None:
        return result
    if (not isinstance(record, dict) or record.get('format') != 1
            or record.get('purpose') != 'wesnoth-world-worker-resource-recovery'
            or record.get('stage') != str(stage)
            or not _binding(record.get('expected_binding'))
            or not isinstance(record.get('inventory'), dict)
            or not isinstance(record['inventory'].get('files'), dict)):
        result['status'] = 'invalid_journal'
        return result
    result['expected_binding_matches_owner'] = owner is not None and record['expected_binding'] == owner
    result['files'] = {}
    for name in FILE_NAMES:
        row = record['inventory']['files'].get('engine/' + name)
        if row is None:
            result['files'][name] = {'status': 'not_recorded'}
        elif (not isinstance(row, dict) or set(row) != {'bytes', 'sha256', 'mtime_ns', 'mode', 'attributes'}
                or any(type(row.get(key)) is not int for key in ('bytes', 'mtime_ns', 'mode', 'attributes'))
                or row['bytes'] < 0 or not isinstance(row['sha256'], str) or len(row['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['sha256'])):
            result['status'] = 'invalid_journal'
            return result
        else:
            result['files'][name] = {'status': 'recorded', **row}
    return result


def collect(repo, *, access_probe=None):
    repo = Path(os.path.abspath(repo))
    stage = repo / 'build' / 'windows-world-worker'
    engine = stage / 'engine'
    probe = access_probe or probe_access
    report = {'format': 1, 'purpose': PURPOSE, 'collected_at_utc': datetime.now(timezone.utc).isoformat(),
              'collection': {'complete': True}, 'files': {}, 'checks': {},
              'scope': 'Existing worker metadata only. No compiler, build, repair or runtime operation is performed.',
              'access_note': 'Access opens are momentary observations; success does not prove a rename or deletion would succeed.'}
    try:
        _, exists = checked_path(engine)
        if not exists or not engine.is_dir():
            raise InspectionError('The existing engine directory is missing.')
        report['checks']['engine_directory'] = {'status': 'present', **_metadata(engine.lstat()),
                                                 'access': probe(engine, directory=True)}
    except (OSError, InspectionError) as error:
        report['checks']['engine_directory'] = {'status': 'unavailable', 'error': _error(error)}
        report['collection']['complete'] = False
    for name in FILE_NAMES:
        row = inspect_file(engine / name, include_raw=name in TEXT_NAMES, access_probe=probe)
        report['files'][name] = row
        if row['status'] not in ('present', 'missing') or row.get('access', {}).get('status', 'observed') != 'observed':
            report['collection']['complete'] = False
        if name in TEXT_NAMES and row['status'] == 'present' and row.get('raw', {}).get('status') != 'captured':
            report['collection']['complete'] = False
    try:
        ownership, owner = _collect_ownership(repo, stage)
        report['checks']['ownership'] = ownership
        if ownership['status'] != 'present' or any(row['status'] != 'present'
                for row in ownership.get('sources', {}).values()):
            report['collection']['complete'] = False
        prior = _collect_prior(stage, owner)
        report['checks']['resource_journal'] = prior
        if prior['status'] not in ('present', 'missing'):
            report['collection']['complete'] = False
        for name, row in report['files'].items():
            earlier = prior.get('files', {}).get(name, {})
            if row['status'] == 'present' and earlier.get('status') == 'recorded':
                row['matches_before_configuration'] = row.get('sha256') == earlier['sha256'] and row['bytes'] == earlier['bytes']
    except (OSError, InspectionError) as error:
        report['checks']['ownership_collection_error'] = _error(error)
        report['collection']['complete'] = False
    if report['checks'].get('engine_directory', {}).get('access', {}).get('status', 'observed') != 'observed':
        report['collection']['complete'] = False
    return report


def write_report(repo, destination, report):
    repo, _ = checked_path(repo)
    diagnostics, exists = checked_path(repo / 'diagnostics')
    destination, _ = checked_path(destination)
    if not exists or not diagnostics.is_dir() or destination.parent != diagnostics or destination.suffix != '.json':
        raise InspectionError('Write a new JSON report directly in the existing diagnostics directory.')
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if sys.platform != 'win32' or sys.version_info[:3] != (3, 12, 10) or sys.maxsize <= 2**32:
            raise InspectionError('Use the verified Windows Python 3.12.10 x64 interpreter.')
        report = collect(ROOT)
        write_report(ROOT, arguments.report, report)
        print('WORLD WORKER NINJA STATE ' + ('COLLECTED' if report['collection']['complete'] else 'COLLECTION INCOMPLETE'))
        print('No build or recovery was performed. Access checks do not establish build readiness.')
        print('JSON report: ' + str(arguments.report))
        return 0 if report['collection']['complete'] else 1
    except (OSError, InspectionError) as error:
        print('ERROR: Ninja state collection stopped; preserve the build. Error type: ' + type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
