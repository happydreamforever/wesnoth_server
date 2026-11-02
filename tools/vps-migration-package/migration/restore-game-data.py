#!/usr/bin/env python3
"""Restore the exact public game-data tree from the retained deterministic OBB.

This does not build an APK, import server configuration or access a game runtime.
Existing destinations are verified only; mismatches are never overwritten.
Interrupted staging folders are retained for inspection, never reused silently.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4
import zipfile

TREE_SHA256 = 'd805fd055b263a5b09cd19576dc9df83c64e47bbcf7821cbb6550b686a74e53c'
INDEX_BYTES = 3577110
OBB_SHA256 = '338aa4fe13c6b1188270b81d76c232c5a1ec334d1926c1b4dc2a53bbe04fabc3'
OBB_BYTES = 731274164
FILE_COUNT = 26748
DATA_BYTES = 726207542
OBB_NAME = 'main.1192600.org.wesnoth.offline.obb'
OWNER = {'kind': 'wesnoth-offline-game-data', 'package': 'org.wesnoth.offline', 'schema': 1}


class RestoreError(ValueError):
    pass


def ordinary(path, directory=False, missing=False):
    path = Path(path)
    if not path.is_absolute():
        raise RestoreError('Use an absolute workspace path.')
    for parent in (*reversed(path.parents), path):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            if missing and parent == path:
                return None
            raise RestoreError('A required source directory or file is missing.') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RestoreError('Linked or redirected paths are not supported.')
        if parent != path and not stat.S_ISDIR(info.st_mode):
            raise RestoreError('A parent path is not an ordinary directory.')
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise RestoreError('Expected an ordinary directory.')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RestoreError('Expected an ordinary, single-link file.')
    return info


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns)


def fingerprint(path):
    before = ordinary(path)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags)
    try:
        if identity(os.fstat(fd)) != identity(before):
            raise RestoreError('A source file changed while opening.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
        if identity(os.fstat(fd)) != identity(before):
            raise RestoreError('A source file changed while reading.')
    finally:
        os.close(fd)
    if identity(ordinary(path)) != identity(before):
        raise RestoreError('A source file changed during verification.')
    return before.st_size, digest.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RestoreError('Duplicate metadata field.')
        result[key] = value
    return result


def metadata(path):
    if ordinary(path).st_size > 65536:
        raise RestoreError('Metadata exceeds its size bound.')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def safe_name(name):
    if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name:
        raise RestoreError('Unsafe asset path.')
    for part in name.split('/'):
        if (part in ('', '.', '..') or part.endswith(('.', ' '))
                or any(ord(char)<32 or char in '<>:"/\\|?*' for char in part)
                or re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3]',
                                part.split('.')[0], re.IGNORECASE)):
            raise RestoreError('Unsafe or Windows-incompatible asset path.')


def source_records(stage):
    ordinary(stage, directory=True)
    if metadata(stage/'.wesnoth-game-data-stage.json') != OWNER:
        raise RestoreError('The game-data stage owner differs.')
    index = stage/'gamedata-files.jsonl'
    before = ordinary(index)
    if before.st_size != INDEX_BYTES:
        raise RestoreError('The exact game-data index differs.')
    fd = os.open(index, os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    try:
        if identity(os.fstat(fd)) != identity(before):
            raise RestoreError('The game-data index changed while opening.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(INDEX_BYTES+1)
        if identity(os.fstat(fd)) != identity(before):
            raise RestoreError('The game-data index changed while reading.')
    finally:
        os.close(fd)
    if (identity(ordinary(index)) != identity(before) or len(raw) != INDEX_BYTES
            or hashlib.sha256(raw).hexdigest() != TREE_SHA256):
        raise RestoreError('The exact game-data index differs.')
    records = []
    seen = set()
    previous = ''
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if not isinstance(row, list) or len(row) != 3:
            raise RestoreError('Invalid game-data record.')
        name, size, digest = row
        safe_name(name)
        if (name <= previous or name.casefold() in seen or type(size) is not int or size < 0
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or line != (json.dumps(row, ensure_ascii=True, separators=(',', ':'))+'\n').encode('ascii')):
            raise RestoreError('Noncanonical game-data index.')
        seen.add(name.casefold()); previous = name; records.append(tuple(row))
    if len(records) != FILE_COUNT or sum(row[1] for row in records) != DATA_BYTES:
        raise RestoreError('Game-data totals differ.')
    receipt = metadata(stage/'receipt.json')
    if (receipt.get('tree_sha256') != TREE_SHA256 or receipt.get('files') != FILE_COUNT
            or receipt.get('bytes') != DATA_BYTES or receipt.get('manifest') !=
            {'path':'gamedata-files.jsonl', 'bytes':INDEX_BYTES, 'sha256':TREE_SHA256}
            or receipt.get('obb') != {'path':OBB_NAME, 'bytes':OBB_BYTES, 'sha256':OBB_SHA256}):
        raise RestoreError('Game-data receipt differs.')
    return records


def verify_tree(destination, records):
    ordinary(destination, directory=True)
    expected = {name:(size,digest) for name,size,digest in records}
    found = set()
    for parent, directories, files in os.walk(destination, followlinks=False):
        for name in directories:
            ordinary(Path(parent)/name, directory=True)
        for name in files:
            path = Path(parent)/name
            relative = path.relative_to(destination).as_posix()
            if relative not in expected or fingerprint(path) != expected[relative]:
                raise RestoreError('Existing or restored game data differs: '+relative)
            found.add(relative)
    if found != set(expected):
        raise RestoreError('Existing or restored game-data files are missing.')


def publish_without_replacement(source, destination):
    ordinary(source, directory=True)
    if ordinary(destination, directory=True, missing=True) is not None:
        raise RestoreError('Destination appeared during restoration; staged files are retained.')
    if os.name == 'nt':
        # Windows rename refuses an existing target.
        os.rename(source, destination)
    elif sys.platform.startswith('linux'):
        # Atomic RENAME_NOREPLACE also refuses a concurrently-created empty dir.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, 'renameat2', None)
        if rename is None:
            raise RestoreError('Atomic no-replace publication is unavailable; staging is retained.')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            value = ctypes.get_errno()
            raise OSError(value, os.strerror(value))
    else:
        raise RestoreError('Atomic publication supports Linux and Windows only; staging is retained.')


def restore(workspace, verify_only=False):
    workspace = Path(os.path.abspath(workspace))
    ordinary(workspace, directory=True)
    stage = workspace/'wesnoth_client/build/android-game-data'
    records = source_records(stage)
    archive_path = stage/OBB_NAME
    if fingerprint(archive_path) != (OBB_BYTES, OBB_SHA256):
        raise RestoreError('The retained game-data OBB differs.')
    destination = workspace/'gamedata-1.19.26'
    if ordinary(destination, directory=True, missing=True) is not None:
        verify_tree(destination, records)
        print('EXISTING GAME DATA VERIFIED; no files changed.')
        return
    if verify_only:
        raise RestoreError('Game-data destination is absent; verification changed no files.')
    retained = workspace/('.gamedata-restore-'+uuid4().hex)
    retained.mkdir(mode=0o700)
    print('Retained staging directory: '+str(retained), flush=True)
    (retained/'owner.json').write_text(json.dumps({'purpose':'wesnoth-migration-game-data',
        'tree_sha256':TREE_SHA256, 'destination':'gamedata-1.19.26'},sort_keys=True)+'\n',encoding='ascii')
    data = retained/'data'; data.mkdir()
    before = identity(ordinary(archive_path))
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) != FILE_COUNT or archive.comment:
            raise RestoreError('Unexpected archive members.')
        for index, (member, (name, size, digest)) in enumerate(zip(members, records), 1):
            if (member.filename != name or member.file_size != size or member.compress_size != size
                    or member.compress_type != zipfile.ZIP_STORED or member.flag_bits & 1
                    or member.create_system != 3 or member.external_attr != (stat.S_IFREG|0o644)<<16
                    or member.date_time != (1980,1,1,0,0,0) or member.comment or member.extra):
                raise RestoreError('Unexpected archive member metadata.')
            output = data/name
            output.parent.mkdir(parents=True, exist_ok=True)
            ordinary(output.parent, directory=True)
            total = 0; actual = hashlib.sha256()
            flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
            fd = os.open(output, flags, 0o644)
            with os.fdopen(fd,'wb') as target, archive.open(member) as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):
                    total += len(chunk)
                    if total > size:raise RestoreError('Archive member exceeds its declared size.')
                    target.write(chunk); actual.update(chunk)
            if total != size or actual.hexdigest() != digest:
                raise RestoreError('Archive member differs from pinned source.')
            if index % 4000 == 0 or index == FILE_COUNT:
                print(f'Restored verified files: {index}/{FILE_COUNT}',flush=True)
    if identity(ordinary(archive_path)) != before:
        raise RestoreError('Archive changed during restoration; staging is retained.')
    verify_tree(data, records)
    publish_without_replacement(data,destination)
    print(f'GAME DATA RESTORED AND VERIFIED: {FILE_COUNT} files; {DATA_BYTES} bytes; tree {TREE_SHA256}')
    print('The source archive and retained restoration record were preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    try:
        restore(args.workspace,args.verify_only)
        return 0
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
        print('GAME DATA RESTORATION STOPPED: '+str(error),file=sys.stderr)
        print('Existing source and destination files were not replaced. Retain any staging folder.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
