"""Diagnose one pinned archive in a new retained directory, without preparation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_alliance_bridge import BuildError, check_host
from tools import world_worker_archive_prefix as archive
from tools import world_worker_dependencies as deps
from tools import world_worker_packages as packages

PURPOSE = 'wesnoth-world-worker-archive-diagnostic'
SCOPE = 'one-pinned-package'
PACKAGE = 'mingw-w64-x86_64-aom'
CLASSIFICATIONS = {
    'category': {'decoder_timeout', 'decoder_exit', 'decoder_wait_timeout', 'tar_read_error', 'io_error'},
    'tar_reason': {'empty_tar', 'truncated_header', 'truncated_payload', 'invalid_header', 'invalid_checksum', 'invalid_tar'},
    'phase': {'preflight', 'extract'},
    'decoder_stage': {'launch', 'parse', 'drain', 'wait', 'cleanup'},
}


def _error_details(error):
    """Only fixed classifications, numeric errors and public archive members."""
    result = {'exception': type(error).__name__ if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', type(error).__name__) else 'Error'}
    details = getattr(error, 'details', {})
    if not isinstance(details, dict):
        details = {}
    for key, allowed in CLASSIFICATIONS.items():
        value = details.get(key)
        if isinstance(value, str) and value in allowed:
            result[key] = value
    for key in ('decoded_bytes', 'elapsed_ms', 'decoder_exit', 'cleanup_exit', 'errno', 'winerror'):
        value = details.get(key, getattr(error, key, None) if key in ('errno', 'winerror') else None)
        if value is None or type(value) is int and -(2**63) <= value < 2**63:
            result[key] = value
    for key in ('timed_out', 'forced_cleanup'):
        if type(details.get(key)) is bool:
            result[key] = details[key]
    value = details.get('decoder_exit_hex')
    if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{8}', value):
        result['decoder_exit_hex'] = value
    if details.get('package') == PACKAGE:
        result['package'] = PACKAGE
    value = details.get('member')
    if isinstance(value, str):
        name = None
        try:
            name = archive._path(value)
            archive._allowed(name, True)
        except BuildError:
            if value not in archive.METADATA and value not in archive.HOOKS:
                name = None
        if name is not None:
            result['member'] = name
    return result


def _verify_payload(destination, expected):
    files = {}
    directories = set()
    for name in expected:
        path = Path(name)
        directories.update(parent.as_posix() for parent in path.parents if parent.as_posix() != '.')
    for path in destination.rglob('*'):
        name = path.relative_to(destination).as_posix()
        if path.is_dir():
            deps.safe_path(path, directory=True)
            if name not in directories:
                raise BuildError('Unexpected diagnostic payload directory.')
        else:
            deps.safe_path(path)
            files[name] = {'bytes': path.stat().st_size, 'sha256': deps.digest(path)}
    if files != expected:
        raise BuildError('Diagnostic extraction differs from verified archive contents.')


def diagnose(msys, report):
    report = deps.safe_path(report)
    deps.safe_path(report.parent, directory=True)
    if report.exists():
        raise BuildError('Diagnostic report already exists; it was preserved.')
    result = {'format': 1, 'purpose': PURPOSE, 'release': 1192624, 'scope': SCOPE,
              'status': 'failed', 'created_at': datetime.now(timezone.utc).isoformat(),
              'package': None, 'scratch': None, 'phases': [],
              'whole_prefix_prepared': False, 'native_worker_tested': False}
    phase = 'host'
    started = time.monotonic()

    def completed(identifier, **fields):
        nonlocal started
        result['phases'].append({'id': identifier, 'status': 'passed',
            'elapsed_ms': round((time.monotonic() - started) * 1000), **fields})
        print('PASS ' + identifier, flush=True)
        started = time.monotonic()

    try:
        check_host()
        completed(phase)
        phase = 'manifest'
        manifest_path = deps.safe_path(packages.MANIFEST)
        manifest_hash = deps.digest(manifest_path)
        manifest = packages.load_manifest(manifest_path)
        pin = manifest['packages'][0]
        if pin['name'] != PACKAGE:
            raise BuildError('The approved first diagnostic package changed.')
        cache = deps.safe_path(packages.CACHE, directory=True)
        result['manifest_sha256'] = manifest_hash
        result['package'] = {key: pin[key] for key in ('name', 'version', 'filename', 'size', 'sha256')}
        completed(phase)
        phase = 'decoder'
        decoder = archive._decoder(manifest, deps.safe_path(msys, directory=True))
        completed(phase)
        phase = 'preflight'
        print('RUN preflight: ' + pin['name'], flush=True)
        expected = archive._scan(pin, cache, decoder=decoder)
        summary = {'file_count': len(expected), 'bytes': sum(row['bytes'] for row in expected.values())}
        completed(phase, **summary)
        phase = 'scratch'
        build = deps.safe_path(ROOT / 'build', directory=True)
        scratch = build / ('world-worker-archive-check-' + uuid4().hex)
        deps.safe_path(scratch)
        scratch.mkdir(mode=0o700)
        result['scratch'] = str(scratch)
        archive._publish_json(scratch / 'owner.json', {
            'format': 1, 'purpose': PURPOSE, 'manifest_sha256': manifest_hash,
            'package': result['package'], 'scope': SCOPE})
        destination = scratch / 'payload'
        destination.mkdir(mode=0o700)
        print('Retained diagnostic folder: ' + str(scratch), flush=True)
        completed(phase)
        phase = 'extract'
        print('RUN extract: ' + pin['name'], flush=True)
        actual = archive._scan(pin, cache, destination=destination, decoder=decoder)
        completed(phase, file_count=len(actual), bytes=sum(row['bytes'] for row in actual.values()))
        phase = 'verify'
        if actual != expected or deps.digest(manifest_path) != manifest_hash:
            raise BuildError('Diagnostic package or manifest changed.')
        _verify_payload(destination, expected)
        completed(phase, **summary)
        result['status'] = 'passed'
    except Exception as error:
        result['phases'].append({'id': phase, 'status': 'failed',
            'elapsed_ms': round((time.monotonic() - started) * 1000), 'error': _error_details(error)})
    archive._publish_json(report, result)
    print('WORLD WORKER ARCHIVE DIAGNOSTIC ' + result['status'].upper(), flush=True)
    print('One pinned package only. The complete worker prefix and native worker readiness are not verified.', flush=True)
    print('Existing prefix, preparation journal, cache and runtime were not changed.', flush=True)
    print('JSON report: ' + str(report), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msys', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return 0 if diagnose(args.msys, args.report)['status'] == 'passed' else 1
    except Exception as error:
        print('WORLD WORKER ARCHIVE DIAGNOSTIC FAILED', flush=True)
        print('Diagnostic report could not be published; preserve the saved transcript.', flush=True)
        print(json.dumps(_error_details(error), sort_keys=True), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
