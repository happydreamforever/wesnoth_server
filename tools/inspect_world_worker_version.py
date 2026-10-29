"""Inspect one existing worker version invocation using disposable user directories."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(os.path.abspath(__file__)).parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_alliance_bridge import BuildError
from tools import world_worker_recovery as recovery
from tools import world_worker_ninja_recovery as ninja

PURPOSE = 'wesnoth-world-worker-version-diagnostic'
VERSION = '1.19.26'
MAX_FILE = 512 * 1024 * 1024
MAX_OUTPUT = 65536
TIMEOUT = 30


def _error(error):
    return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
            'winerror': getattr(error, 'winerror', None)}


def _file(path):
    before = recovery._ordinary(path)
    if not 0 < before.st_size <= MAX_FILE:
        raise BuildError('A version diagnostic input has an unexpected size.')
    with Path(path).open('rb') as stream:
        if not recovery._same_open_file(path, before, os.fstat(stream.fileno())):
            raise BuildError('A version diagnostic input changed while opening.')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        opened = os.fstat(stream.fileno())
    after = recovery._ordinary(path)
    if (recovery._identity(before) != recovery._identity(after)
            or not recovery._same_open_file(path, after, opened)):
        raise BuildError('A version diagnostic input changed while hashing.')
    return {'bytes': before.st_size, 'sha256': digest, 'mtime_ns': before.st_mtime_ns,
            'mode': before.st_mode, 'attributes': getattr(before, 'st_file_attributes', 0),
            'device': before.st_dev, 'file_id': before.st_ino, 'links': before.st_nlink}


def _bin(directory):
    recovery._path(directory, directory=True)
    names = set()
    rows = {}
    for path in sorted(directory.iterdir()):
        name = path.name
        if name.casefold() in names or (name != 'world-worker.exe' and not re.fullmatch(r'[A-Za-z0-9_.+\-]+\.dll', name, re.I)):
            raise BuildError('Worker bin contains unexpected or duplicate files; preserved.')
        names.add(name.casefold())
        rows[name] = _file(path)
    if 'world-worker.exe' not in rows or len(rows) > 256:
        raise BuildError('Worker executable or bounded DLL inventory is missing.')
    return rows


def _header(stage):
    path = stage / 'source/src/wesconfig.h'
    row = _file(path)
    if row['bytes'] > 1024 * 1024:
        raise BuildError('Worker version header is oversized.')
    raw = ninja._raw(path)
    matches = re.findall(rb'^\s*#define\s+VERSION\s+"([0-9A-Za-z.+_-]{1,64})"\s*$', raw, re.M)
    if len(matches) != 1:
        raise BuildError('Worker source version header is ambiguous.')
    return {'file': row, 'declared_version': matches[0].decode('ascii')}


def _default_binding():
    from tools.build_world_worker import binding
    return binding()


def _environment(binary, scratch, environ):
    normalized = {}
    for key, value in environ.items():
        upper = key.upper()
        if upper in normalized:
            raise BuildError('Duplicate Windows environment aliases; no executable was run.')
        normalized[upper] = value
    system = normalized.get('SYSTEMROOT')
    if not system or not str(system).strip():
        raise BuildError('Windows SystemRoot is missing.')
    system = recovery._path(system, directory=True)
    system32 = recovery._path(system / 'System32', directory=True)
    folders = {}
    for name in ('userdata', 'cache', 'temp', 'profile', 'appdata', 'localappdata'):
        path = scratch / name
        path.mkdir()
        folders[name] = path
    return {'SYSTEMROOT': str(system), 'WINDIR': str(system),
            'PATH': str(binary) + os.pathsep + str(system32),
            'TEMP': str(folders['temp']), 'TMP': str(folders['temp']),
            'USERPROFILE': str(folders['profile']), 'APPDATA': str(folders['appdata']),
            'LOCALAPPDATA': str(folders['localappdata'])}, folders


def run_bounded(command, environment, cwd, *, timeout=TIMEOUT, max_bytes=MAX_OUTPUT):
    """Drain both pipes concurrently, keeping at most max_bytes per stream."""
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    overflow = threading.Event()
    limits = {'stdout': False, 'stderr': False}
    read_errors = []
    started = time.monotonic()
    try:
        process = subprocess.Popen([str(value) for value in command], cwd=cwd, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=0x08000000 if os.name == 'nt' else 0)
    except OSError as error:
        return {'status': 'launch_error', 'exit_code': None, 'timed_out': False, 'output_limited': False,
                'stdout': b'', 'stderr': b'', 'error': _error(error), 'capture_complete': True}
    def consume(name, pipe):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                available = max(0, max_bytes - len(streams[name]))
                streams[name].extend(chunk[:available])
                if len(chunk) > available:
                    limits[name] = True
                    overflow.set()
        except (OSError, ValueError) as error:
            read_errors.append(_error(error))
        finally:
            pipe.close()
    threads = [threading.Thread(target=consume, args=(name, pipe), daemon=True)
               for name, pipe in (('stdout', process.stdout), ('stderr', process.stderr))]
    for thread in threads: thread.start()
    timed_out = False
    cleanup_error = None
    while process.poll() is None:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0 or overflow.is_set():
            timed_out = remaining <= 0
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_error = _error(error)
            break
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            pass
    for thread in threads: thread.join(timeout=5)
    complete = not cleanup_error and not read_errors and not any(thread.is_alive() for thread in threads)
    return {'status': 'timeout' if timed_out else 'output_limit' if overflow.is_set() else 'exited',
            'exit_code': process.poll(), 'timed_out': timed_out, 'output_limited': overflow.is_set(),
            'stdout': bytes(streams['stdout']), 'stderr': bytes(streams['stderr']),
            'stdout_limited': limits['stdout'], 'stderr_limited': limits['stderr'],
            'capture_complete': bool(complete), 'error': cleanup_error,
            'read_errors': read_errors, 'elapsed_seconds': round(time.monotonic() - started, 3)}


def _stream(raw, *, limited):
    # Unknown output may include paths or arbitrary data. Retain its bounded hash
    # and count, exposing bytes only for a concise version-string grammar.
    trimmed = raw.strip()
    version = trimmed.decode('ascii') if re.fullmatch(rb'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[-+][A-Za-z0-9._-]{1,32})?', trimmed) else None
    return {'captured_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'limited': limited, 'version_text': version,
            'version_bytes_base64': base64.b64encode(raw).decode('ascii') if version else None,
            'unrecognized_text_omitted': bool(raw and not version)}


def collect(repo, *, binding_function=None, run_process=None, environ=None):
    repo = recovery._path(repo, directory=True)
    stage = repo / 'build/windows-world-worker'
    report = {'format': 1, 'purpose': PURPOSE, 'release': 1192624,
              'collected_at_utc': datetime.now(timezone.utc).isoformat(),
              'collection': {'complete': False}, 'scope': 'existing-worker-version-only',
              'receipt_written': False, 'build_performed': False, 'result': {'outcome': 'not_run'},
              'preservation': {}}
    phase = 'ownership'
    before = None
    try:
        recovery._path(stage, directory=True)
        if (stage / 'receipt.json').exists():
            raise BuildError('This diagnostic requires the existing incomplete worker stage.')
        current_binding = binding_function or _default_binding
        # The completed build attempt already created this mutex; the diagnostic
        # may acquire it but does not create a new ownership/recovery file.
        lock = stage.with_name(stage.name + '.build.lock')
        recovery._ordinary(lock)
        with ninja.build_lock(stage):
            owner = recovery._read_json(stage / 'owner.json')
            recovery._binding(owner)
            if current_binding() != owner:
                raise BuildError('Worker source binding differs; do not run or rebuild it.')
            phase = 'artifacts'
            binary = recovery._path(stage / 'bin', directory=True)
            before_bin = _bin(binary)
            compiled = _file(stage / 'engine/src/world-worker.exe')
            if any(compiled[key] != before_bin['world-worker.exe'][key] for key in ('bytes', 'sha256')):
                raise BuildError('The copied worker differs from its linked engine executable.')
            prefix_receipt = repo / 'build/world-worker-prefix/receipt.json'
            prefix_row = _file(prefix_receipt)
            if owner['inputs'].get('wesnoth_server/build/world-worker-prefix/receipt.json') != prefix_row['sha256']:
                raise BuildError('Worker dependency receipt differs from its source binding.')
            dependencies = recovery._read_json(prefix_receipt)
            if (dependencies.get('format') != 1 or dependencies.get('purpose') != 'wesnoth-world-worker-mingw64-prefix'
                    or not isinstance(dependencies.get('files'), dict)):
                raise BuildError('Worker dependency receipt is invalid.')
            for name, row in before_bin.items():
                if name == 'world-worker.exe': continue
                pinned = dependencies['files'].get('bin/' + name)
                if pinned != {key: row[key] for key in ('bytes', 'sha256')}:
                    raise BuildError('A local worker DLL differs from its pinned dependency receipt.')
            before = {'owner': _file(stage / 'owner.json'), 'bin': before_bin,
                      'linked_executable': compiled, 'version_header': _header(stage),
                      'prefix_receipt': prefix_row, 'binding_sha256': recovery._hash(owner)}
            report['artifacts'] = before
            report['binding_input_count'] = len(owner['inputs'])
            phase = 'scratch'
            scratch = stage.parent / ('world-worker-version-check-' + uuid4().hex)
            scratch.mkdir()
            report['retained_scratch'] = str(scratch)
            environment, folders = _environment(binary, scratch, os.environ if environ is None else environ)
            command = [binary / 'world-worker.exe', '--simple-version', '--no-log-to-file', '--wnoconsole',
                       '--userdata-dir', folders['userdata'], '--usercache-dir', folders['cache']]
            report['arguments'] = ['--simple-version', '--no-log-to-file', '--wnoconsole',
                                   '--userdata-dir', '<retained-scratch>/userdata', '--usercache-dir', '<retained-scratch>/cache']
            phase = 'version'
            result = (run_process or run_bounded)(command, environment, scratch)
            stdout, stderr = result.pop('stdout'), result.pop('stderr')
            matched = (result['status'] == 'exited' and result['exit_code'] == 0
                       and stdout.strip() == VERSION.encode('ascii'))
            outcome = ('version_match' if matched else result['status'] if result['status'] != 'exited'
                       else 'nonzero_exit' if result['exit_code'] != 0
                       else 'empty_stdout' if not stdout.strip() else 'version_mismatch')
            report['result'] = {**result, 'outcome': outcome, 'version_matches': matched,
                'stdout': _stream(stdout, limited=result.get('stdout_limited', result['output_limited'])),
                'stderr': _stream(stderr, limited=result.get('stderr_limited', result['output_limited']))}
            phase = 'preservation'
            report['preservation'] = {
                'bin_unchanged': _bin(binary) == before_bin,
                'owner_unchanged': _file(stage / 'owner.json') == before['owner'],
                'linked_executable_unchanged': _file(stage / 'engine/src/world-worker.exe') == compiled,
                'version_header_unchanged': _header(stage) == before['version_header'],
                'dependency_receipt_unchanged': _file(prefix_receipt) == prefix_row,
                'source_binding_unchanged': current_binding() == owner,
                'no_receipt_created': not (stage / 'receipt.json').exists(),
            }
            report['collection']['complete'] = bool(result['capture_complete'] and all(report['preservation'].values()))
    except (OSError, BuildError, ValueError, KeyError, TypeError) as error:
        report['failure'] = {'phase': phase, **_error(error)}
    return report


def write_report(repo, destination, report):
    diagnostics = recovery._path(Path(repo) / 'diagnostics', directory=True)
    destination = recovery._path(destination)
    if destination.parent != diagnostics or destination.suffix != '.json':
        raise BuildError('Use a new report directly inside diagnostics.')
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if sys.platform != 'win32' or sys.version_info[:3] != (3, 12, 10) or sys.maxsize <= 2**32:
            raise BuildError('Use the verified Windows Python 3.12.10 x64 interpreter.')
        destination = recovery._path(args.report)
        diagnostics = recovery._path(ROOT / 'diagnostics', directory=True)
        if destination.exists() or destination.parent != diagnostics or destination.suffix != '.json':
            raise BuildError('Use a new JSON report directly inside diagnostics.')
        report = collect(ROOT)
        write_report(ROOT, destination, report)
        result = report['result']
        print('WORLD WORKER VERSION STATE ' + ('COLLECTED' if report['collection']['complete'] else 'COLLECTION INCOMPLETE'))
        print('outcome=' + result['outcome'] + '; exit_code=' + str(result.get('exit_code')))
        version = result.get('stdout', {}).get('version_text')
        if version: print('Captured version: ' + version)
        print('JSON report: ' + str(destination))
        return 0 if report['collection']['complete'] else 1
    except (OSError, BuildError, ValueError) as error:
        print('ERROR: Worker version diagnostic stopped; error_type=' + type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
