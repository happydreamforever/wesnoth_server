#!/usr/bin/env python3
"""Pinned MINGW64 package cache for an isolated native worker prefix.

This helper never installs packages, executes package scripts, refreshes a
repository, changes the MSYS keyring or upgrades the existing toolchain.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import world_worker_dependencies as dependencies
from tools.alliance_dependencies import assert_windows_python, ensure_artifact, PreparationError
from tools.build_alliance_bridge import BuildError, write_new

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tools/world-worker-packages-1192624.json'
CACHE = ROOT / 'build/world-worker-packages-1192624'
PURPOSE = 'wesnoth-world-worker-packages'
REPOSITORY = 'https://repo.msys2.org/mingw/mingw64/'
NAME = re.compile(r'mingw-w64-x86_64-[A-Za-z0-9+_.-]+')
VERSION = re.compile(r'[A-Za-z0-9+_.:~\-]+')
SHA = re.compile(r'[0-9a-f]{64}')
CONSTRAINT = re.compile(r'mingw-w64-x86_64-[A-Za-z0-9+_.-]+(?:(?:>=|<=|=|>|<)[A-Za-z0-9+_.:~\-]+)?')


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BuildError('Duplicate package manifest or journal key.')
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(dependencies.read(path).decode('utf-8'), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(BuildError('Non-finite JSON values are not allowed.')))
    except (ValueError, UnicodeError):
        raise BuildError('Package manifest or journal is not valid UTF-8 JSON.') from None


def load_manifest(path=MANIFEST):
    data = read_json(path)
    if (not isinstance(data, dict) or set(data) != {'format', 'purpose', 'release', 'source', 'roots', 'baseline', 'packages'}
            or type(data['format']) is not int or data['format'] != 1
            or data['purpose'] != PURPOSE or type(data['release']) is not int or data['release'] != 1192624):
        raise BuildError('Unsupported worker package manifest.')
    if not isinstance(data['source'], dict) or data['source'].get('repository') != REPOSITORY:
        raise BuildError('Worker packages must use the pinned official MINGW64 repository.')
    if len(json.dumps(data['source'])) > 32768:
        raise BuildError('Package provenance exceeds its bound.')
    if not isinstance(data['packages'], list) or not 1 <= len(data['packages']) <= 200:
        raise BuildError('Invalid pinned package inventory.')
    names = set(); filenames = set()
    for package in data['packages']:
        if not isinstance(package, dict) or set(package) != {'name', 'version', 'filename', 'size', 'sha256', 'mtree_sha256', 'signature', 'depends', 'provides', 'conflicts', 'replaces'}:
            raise BuildError('Invalid pinned package fields.')
        name, version = package['name'], package['version']
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(version, str) or not VERSION.fullmatch(version):
            raise BuildError('Invalid pinned package identity.')
        expected = name + '-' + version.split(':')[-1] + '-any.pkg.tar.zst'
        if package['filename'] != expected or name in names or expected in filenames:
            raise BuildError('Unsafe, repeated or inconsistent pinned package filename.')
        names.add(name); filenames.add(expected)
        if not isinstance(package['mtree_sha256'], str) or not SHA.fullmatch(package['mtree_sha256']):
            raise BuildError('Invalid package integrity-metadata hash.')
        if not isinstance(package['signature'], dict) or set(package['signature']) != {'size', 'sha256'}:
            raise BuildError('Invalid signature pin.')
        for artifact, maximum in ((package, 1024**3), (package['signature'], 65536)):
            if type(artifact.get('size')) is not int or not 1 <= artifact['size'] <= maximum or not isinstance(artifact.get('sha256'), str) or not SHA.fullmatch(artifact['sha256']):
                raise BuildError('Invalid pinned artifact size or SHA256.')
        for field in ('depends', 'provides', 'conflicts', 'replaces'):
            entries = package[field]
            if (not isinstance(entries, list) or len(entries) > 100
                    or any(not isinstance(value, str) or not CONSTRAINT.fullmatch(value) for value in entries)
                    or len(entries) != len(set(entries))):
                raise BuildError('Invalid pinned package dependency metadata.')
    if (not isinstance(data['roots'], list) or not data['roots']
            or any(not isinstance(name, str) or name not in names for name in data['roots'])
            or len(data['roots']) != len(set(data['roots']))):
        raise BuildError('Invalid worker package roots.')
    if not isinstance(data['baseline'], list) or not 1 <= len(data['baseline']) <= 100:
        raise BuildError('Invalid installed-toolchain baseline.')
    baseline_names = set(); lookup = {row['name']: row for row in data['packages']}
    for row in data['baseline']:
        if (not isinstance(row, dict) or set(row) != {'name', 'version'} or not isinstance(row.get('name'), str) or row.get('name') not in names
                or row['name'] in baseline_names or row['version'] != lookup[row['name']]['version']):
            raise BuildError('Installed-toolchain baseline differs from package pins.')
        baseline_names.add(row['name'])
    providers = {}
    for row in data['packages']:
        for alias in [row['name'], *row['provides']]:
            providers.setdefault(re.split(r'[<>=]', alias, 1)[0], set()).add(row['name'])
    for row in data['packages']:
        for dep in row['depends']:
            if len(providers.get(re.split(r'[<>=]', dep, 1)[0], set())) != 1:
                raise BuildError('Pinned dependency closure is incomplete or ambiguous.')
    return data


def installed_snapshot(msys):
    database = dependencies.safe_path(Path(msys) / 'var/lib/pacman/local', directory=True)
    result = {}
    for directory in sorted(database.iterdir()):
        dependencies.safe_path(directory, directory=directory.is_dir())
        if directory.name == 'ALPM_DB_VERSION' and directory.is_file():
            continue
        if not directory.is_dir():
            raise BuildError('Unexpected entry in installed package database.')
        fields = dependencies.fields(directory / 'desc')
        names, versions = fields.get('NAME', []), fields.get('VERSION', [])
        if (len(names) != 1 or len(versions) != 1 or not re.fullmatch(r'[A-Za-z0-9+_.-]+', names[0])
                or not VERSION.fullmatch(versions[0]) or names[0] in result):
            raise BuildError('Installed package database contains an invalid identity.')
        metadata = {}
        for entry in sorted(directory.iterdir()):
            dependencies.safe_path(entry)
            metadata[entry.name] = dependencies.digest(entry)
        result[names[0]] = {'version': versions[0], 'provides': fields.get('PROVIDES', []),
                           'metadata': metadata, 'directory': directory.name}
    if not result:
        raise BuildError('Installed package database is empty.')
    return result


def check_installed(manifest, snapshot):
    for row in manifest['baseline']:
        if snapshot.get(row['name'], {}).get('version') != row['version']:
            raise BuildError('Installed toolchain differs from the reviewed baseline: ' + row['name'])
    aliases = {}
    for name, row in snapshot.items():
        for alias in [name, *row['provides']]:
            aliases.setdefault(re.split(r'[<>=]', alias, 1)[0], set()).add(name)
    missing = []
    for row in manifest['packages']:
        if row['name'] in snapshot:
            if snapshot[row['name']]['version'] != row['version']:
                raise BuildError('An installed worker package has another version; no upgrade is allowed: ' + row['name'])
        else:
            missing.append(row)
        for constraint in [*row['conflicts'], *row['replaces']]:
            matches = aliases.get(re.split(r'[<>=]', constraint, 1)[0], set()) - {row['name']}
            if matches:
                raise BuildError('A pinned package could remove or replace an installed package: ' + row['name'])
    return missing


def owned_cache(cache, manifest_hash):
    cache = dependencies.safe_path(cache, directory=Path(cache).exists())
    marker = {'format': 1, 'purpose': PURPOSE, 'release': 1192624, 'manifest_sha256': manifest_hash}
    if cache.exists():
        dependencies.safe_path(cache, directory=True)
        if not (cache / 'owned.json').is_file() or read_json(cache / 'owned.json') != marker:
            raise BuildError('The package cache belongs to another manifest; preserve it.')
    else:
        cache.mkdir(parents=True)
        write_new(cache / 'owned.json', marker)
    return cache


def artifact_specs(manifest):
    for package in manifest['packages']:
        yield {'filename': package['filename'], 'size': package['size'], 'sha256': package['sha256'], 'url': REPOSITORY + package['filename']}
        yield {'filename': package['filename'] + '.sig', **package['signature'], 'url': REPOSITORY + package['filename'] + '.sig'}


def verify_artifact(path, spec):
    path = dependencies.safe_path(path)
    if not path.is_file() or path.stat().st_size != spec['size'] or dependencies.digest(path) != spec['sha256']:
        raise BuildError('Cached package or signature is missing or differs from its pin: ' + spec['filename'])


def publish_artifact(staging, destination, spec):
    verify_artifact(staging, spec)
    dependencies.safe_path(destination)
    if os.name == 'nt':
        # Windows rename fails if the destination exists. No replace is used.
        os.rename(staging, destination)
    else:
        # POSIX rename would replace: create the final directory entry
        # exclusively instead, then remove the owned staging link.
        os.link(staging, destination)
        staging.unlink()
    verify_artifact(destination, spec)


def copy_artifact(source, destination, spec):
    verify_artifact(source, spec)
    staging = destination.with_name(destination.name + '.copying-' + uuid4().hex)
    with source.open('rb') as incoming, staging.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush(); os.fsync(outgoing.fileno())
    verify_artifact(source, spec)
    publish_artifact(staging, destination, spec)


def prepare_download(destination, spec, download):
    if destination.exists():
        verify_artifact(destination, spec)
        return
    if not download:
        verify_artifact(destination, spec)
    staging = destination.with_name(destination.name + '.prepared-' + uuid4().hex)
    ensure_artifact(staging, spec, download=True)
    publish_artifact(staging, destination, spec)


def prepare_cache(manifest, msys, cache, download=False):
    source = dependencies.safe_path(Path(msys) / 'var/cache/pacman/pkg', directory=True)
    for spec in artifact_specs(manifest):
        destination = dependencies.safe_path(Path(cache) / spec['filename'])
        if destination.exists():
            verify_artifact(destination, spec)
            continue
        original = dependencies.safe_path(source / spec['filename'])
        if original.exists():
            copy_artifact(original, destination, spec)
        else:
            prepare_download(destination, spec, download)
    key = keyring_spec(manifest)
    key_path = dependencies.safe_path(Path(cache) / key['filename'])
    prepare_download(key_path, key, download)
    verify_cache(manifest, msys, cache)
    print('WORLD WORKER PACKAGE CACHE VERIFIED', flush=True)


def cygpath(msys, path):
    executable = dependencies.safe_path(Path(msys) / 'usr/bin/cygpath.exe')
    result = subprocess.run([str(executable), '-u', str(Path(path).absolute())],
                            env=command_environment(msys), capture_output=True, timeout=30, check=False)
    value = result.stdout.decode('utf-8').strip()
    if result.returncode or not value.startswith('/') or any(character in value for character in '\r\n\t#'):
        raise BuildError('Cannot convert an owned package path for MSYS2.')
    return value


def command_environment(msys):
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE'}}
    environment['PATH'] = str(Path(msys) / 'usr/bin')
    environment['LANG'] = 'C'; environment['LC_ALL'] = 'C'
    return environment


def no_pacman_lock(msys):
    path = dependencies.safe_path(Path(msys) / 'var/lib/pacman/db.lck')
    if path.exists():
        raise BuildError('Pacman already holds its database lock. Preserve the lock and stop.')


def keyring_spec(manifest):
    source = manifest['source'].get('official_keyring', {})
    if not isinstance(source, dict) or not isinstance(source.get('commit'), str):
        raise BuildError('The official package signing-key pin is incomplete.')
    commit = source['commit']
    expected_url = 'https://raw.githubusercontent.com/msys2/MSYS2-keyring/' + commit + '/msys2.gpg'
    if (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)
            or source.get('repository') != 'https://github.com/msys2/MSYS2-keyring'
            or source.get('url') != expected_url
            or type(source.get('bytes')) is not int or not 1 <= source['bytes'] <= 1024 * 1024
            or not isinstance(source.get('sha256'), str) or not SHA.fullmatch(source['sha256'])
            or type(source.get('binary_bytes')) is not int or not 1 <= source['binary_bytes'] <= 1024 * 1024
            or not isinstance(source.get('binary_sha256'), str) or not SHA.fullmatch(source['binary_sha256'])
            or not isinstance(source.get('snapshot_signer'), str)
            or not re.fullmatch(r'[0-9A-F]{40}', source['snapshot_signer'])):
        raise BuildError('The official package signing-key pin is incomplete.')
    return {'filename': 'msys2-keyring-' + commit + '.gpg', 'size': source['bytes'],
            'sha256': source['sha256'], 'url': expected_url}


def run_dearmor(msys, keyring, home):
    executable = dependencies.safe_path(Path(msys) / 'usr/bin/gpg.exe')
    if not executable.is_file() or executable.stat().st_size == 0:
        raise BuildError('The existing MSYS2 gpg executable is missing. Preserve the cache and send this report.')
    arguments = [str(executable), '--no-options', '--homedir', cygpath(msys, home),
                 '--batch', '--no-tty', '--dearmor']
    # Read the pinned public armor from stdin and capture binary stdout. No
    # import, existing keyring, network access or output overwrite is involved.
    return subprocess.run(arguments, input=dependencies.read(keyring, 1024 * 1024),
                          env=command_environment(msys), capture_output=True,
                          timeout=30, check=False)


def binary_keyring(manifest, msys, cache, home):
    key = keyring_spec(manifest)
    source = manifest['source']['official_keyring']
    spec = {'filename': key['filename'].replace('.gpg', '-binary.gpg'),
            'size': source['binary_bytes'], 'sha256': source['binary_sha256']}
    destination = dependencies.safe_path(cache / spec['filename'])
    if not destination.exists():
        result = run_dearmor(msys, cache / key['filename'], home)
        if (result.returncode or len(result.stdout) != spec['size']
                or hashlib.sha256(result.stdout).hexdigest() != spec['sha256']):
            raise BuildError('The pinned official public keyring did not decode to its reviewed binary hash.')
        staging = destination.with_name(destination.name + '.prepared-' + uuid4().hex)
        with staging.open('xb') as stream:
            stream.write(result.stdout); stream.flush(); os.fsync(stream.fileno())
        publish_artifact(staging, destination, spec)
    verify_artifact(destination, spec)
    return destination


def run_gpgv(msys, keyring, signature, archive, home):
    executable = dependencies.safe_path(Path(msys) / 'usr/bin/gpgv.exe')
    if not executable.is_file() or executable.stat().st_size == 0:
        raise BuildError('The existing MSYS2 gpgv executable is missing. Preserve the cache and send this report.')
    arguments = [str(executable), '--homedir', cygpath(msys, home),
                 '--keyring', cygpath(msys, keyring), '--status-fd', '1',
                 cygpath(msys, signature), cygpath(msys, archive)]
    # gpgv has no keyserver retrieval or trust-database maintenance. The
    # temporary home contains no configuration or private keys.
    return subprocess.run(arguments, env=command_environment(msys),
                          capture_output=True, timeout=120, check=False)


def validate_signature_status(result, expected_fingerprint):
    if result.returncode:
        raise BuildError('An offline package signature could not be verified with the pinned official signing key.')
    try:
        lines = result.stdout.decode('utf-8').splitlines()
    except UnicodeError:
        raise BuildError('Package signature verifier returned invalid status data.') from None
    valid = []
    denied = {'BADSIG', 'ERRSIG', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG', 'NO_PUBKEY', 'FAILURE'}
    for line in lines:
        if not line.startswith('[GNUPG:] '):
            continue
        fields = line[len('[GNUPG:] '):].split()
        if not fields:
            continue
        if fields[0] in denied:
            raise BuildError('Package signature verification reported a rejected key or signature.')
        if fields[0] == 'VALIDSIG':
            # VALIDSIG fingerprint date timestamp expire version reserved
            # pubkey-algorithm hash-algorithm signature-class [primary-key].
            if len(fields) not in (10, 11) or fields[8] not in {'8', '9', '10', '11'}:
                raise BuildError('Package signature uses unexpected status data or a weak digest.')
            primary = fields[10] if len(fields) == 11 else fields[1]
            if primary != expected_fingerprint:
                raise BuildError('Package signature belongs to an unpinned signer.')
            valid.append(fields[1])
    if len(valid) != 1:
        raise BuildError('Expected exactly one valid pinned package signature.')


def verify_cache(manifest, msys, cache, verification_home=None):
    cache = dependencies.safe_path(cache, directory=True)
    for spec in artifact_specs(manifest):
        verify_artifact(cache / spec['filename'], spec)
    key = keyring_spec(manifest)
    verify_artifact(cache / key['filename'], key)
    if verification_home is None:
        verification_home = cache / ('signature-check-' + uuid4().hex)
        verification_home.mkdir()
    else:
        verification_home = dependencies.safe_path(verification_home, directory=True)
        if any(verification_home.iterdir()):
            raise BuildError('Signature verification requires an empty owned home directory.')
    binary = binary_keyring(manifest, msys, cache, verification_home)
    signer = manifest['source']['official_keyring']['snapshot_signer']
    for package in manifest['packages']:
        result = run_gpgv(msys, binary, cache / (package['filename'] + '.sig'),
                          cache / package['filename'], verification_home)
        try:
            validate_signature_status(result, signer)
        except BuildError as error:
            raise BuildError(package['name'] + ': ' + str(error)) from None
    return {'packages': len(manifest['packages']), 'signer': signer, 'signatures_verified': True}


def execute(msys, manifest_path=MANIFEST, cache=CACHE, *, download=False, report_path=None):
    msys = dependencies.safe_path(msys, directory=True)
    manifest = load_manifest(manifest_path)
    keyring_spec(manifest)
    manifest_hash = dependencies.digest(manifest_path)
    cache = owned_cache(cache, manifest_hash)
    operation = cache / 'operation.lock'
    owner = {'pid': os.getpid(), 'nonce': uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat()}
    try:
        write_new(operation, owner)
    except FileExistsError:
        raise BuildError('Another package operation holds the cache lock. Do not delete it; retain the log for review.') from None
    attempt = cache / ('attempt-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + owner['nonce'])
    attempt.mkdir()
    report = {'format': 1, 'purpose': PURPOSE, 'manifest_sha256': manifest_hash,
              'operation': 'download' if download else 'verify', 'status': 'stopped',
              'packages_installed': 0, 'services_started': False,
              'repository_refreshed': False, 'keyring_changed': False, 'journal': str(attempt)}
    try:
        no_pacman_lock(msys)
        before = installed_snapshot(msys)
        missing = check_installed(manifest, before)
        write_new(attempt / 'before.json', before)
        write_new(attempt / 'plan.json', {'manifest_sha256': manifest_hash,
                  'not_installed_in_original_msys': [{'name': row['name'], 'version': row['version']} for row in missing]})
        prepare_cache(manifest, msys, cache, download=download)
        if installed_snapshot(msys) != before:
            raise BuildError('Installed package metadata changed during cache preparation.')
        report.update(status='cache_verified', cache_verified=True, signatures_verified=True,
                      package_count=len(manifest['packages']), original_package_inventory_preserved=True)
        print('Original MSYS2 packages are unchanged. This cache is for the separate worker prefix.', flush=True)
        return report
    except (BuildError, PreparationError, OSError, ValueError, subprocess.SubprocessError) as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        write_new(attempt / 'result.json', report)
        if report_path is not None:
            target = dependencies.safe_path(report_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new(target, report)
        if read_json(operation) == owner:
            operation.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msys', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    try:
        assert_windows_python()
        print('Python 3.12.10; Windows x86_64 runtime verified.', flush=True)
        execute(args.msys, download=args.download, report_path=args.report)
        return 0
    except (BuildError, PreparationError) as error:
        print('ERROR: ' + str(error), flush=True)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('ERROR: Worker package operation stopped (' + type(error).__name__ + '). Preserve the cache and journal.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
