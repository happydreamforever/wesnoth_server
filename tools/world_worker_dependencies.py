"""Verify installed MINGW64 package files and freeze an isolated worker prefix.

No package installation, tool upgrade or network request occurs here. Missing
packages require a separately reviewed pinned offline preparation batch.
"""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.build_alliance_bridge import BuildError, write_new

ROOT=Path(__file__).resolve().parents[1]
PREFIX=ROOT/'build/world-worker-prefix'
PURPOSE='wesnoth-world-worker-mingw64-prefix'
MAX_METADATA=32*1024*1024


def safe_path(value, *, directory=False):
    path=Path(value).absolute()
    for part in (*reversed(path.parents),path):
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise BuildError('Dependency paths cannot traverse links or junctions.')
    if directory and not path.is_dir():raise BuildError('Dependency directory is missing.')
    if path.exists() and not directory and not path.is_file():raise BuildError('Dependency file is not ordinary.')
    return path


def digest(value):
    path=safe_path(value)
    if path.stat().st_nlink!=1:raise BuildError('Dependency files cannot use hard links.')
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path, limit=MAX_METADATA):
    path=safe_path(path)
    if path.stat().st_nlink!=1 or path.stat().st_size>limit:raise BuildError('Dependency metadata is linked or oversized.')
    raw=path.read_bytes()
    if len(raw)>limit:raise BuildError('Dependency metadata changed size.')
    return raw


def fields(path):
    result={};key=None
    for line in read(path).decode('utf-8').splitlines():
        if line.startswith('%') and line.endswith('%'):
            key=line[1:-1]
            if key in result:raise BuildError('Duplicate installed package metadata field.')
            result[key]=[]
        elif line and key:result[key].append(line)
    return result


def package_records(msys):
    database=safe_path(Path(msys)/'var/lib/pacman/local',directory=True)
    result={}
    for directory in sorted(database.glob('mingw-w64-x86_64-*')):
        safe_path(directory,directory=True);meta=fields(directory/'desc')
        name=meta.get('NAME',[]);version=meta.get('VERSION',[])
        if len(name)!=1 or len(version)!=1 or not re.fullmatch(r'mingw-w64-x86_64-[A-Za-z0-9+_.-]+',name[0]):
            raise BuildError('Installed MINGW64 package identity is incomplete.')
        if name[0] in result:raise BuildError('Duplicate installed MINGW64 package.')
        files=fields(directory/'files').get('FILES',[])
        result[name[0]]={'name':name[0],'version':version[0],'directory':directory,
            'files':files,'depends':meta.get('DEPENDS',[]),'provides':meta.get('PROVIDES',[])}
    return result


def unescape(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),value)


def package_hashes(record):
    compressed=read(record['directory']/'mtree')
    try:
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(MAX_METADATA+1)
    except (OSError,EOFError):raise BuildError('Installed package integrity metadata is unreadable.') from None
    if len(raw)>MAX_METADATA:raise BuildError('Installed package integrity metadata exceeds its bound.')
    rows={};defaults={}
    for line in raw.decode('utf-8').splitlines():
        if not line or line.startswith('#'):continue
        parts=line.split();values={item.split('=',1)[0]:unescape(item.split('=',1)[1]) for item in parts[1:] if '=' in item}
        if parts[0]=='/set':defaults.update(values);continue
        if parts[0]=='/unset':
            for key in parts[1:]:defaults.pop(key,None)
            continue
        name=unescape(parts[0]).removeprefix('./')
        if not name.startswith('mingw64/'):continue
        relative=name[len('mingw64/'):]
        if not relative:continue
        if relative.startswith('/') or '\\' in relative or ':' in relative or '..' in Path(relative).parts:
            raise BuildError('Unsafe installed package path.')
        attrs={**defaults,**values}
        if attrs.get('type')=='dir':continue
        if attrs.get('type')!='file' or not re.fullmatch(r'[0-9a-f]{64}',attrs.get('sha256digest','')):
            raise BuildError('The isolated prefix requires regular package files with SHA256 integrity records.')
        if relative in rows:raise BuildError('Duplicate package integrity path.')
        rows[relative]={'sha256':attrs['sha256digest'],'bytes':int(attrs['size'])}
    expected={name[len('mingw64/'):] for name in record['files'] if name.startswith('mingw64/') and not name.endswith('/')}
    if expected!=set(rows):raise BuildError('Installed package file list and integrity records disagree.')
    return rows,hashlib.sha256(compressed).hexdigest()


def selection(msys, required):
    records=package_records(msys);providers={}
    for name,record in records.items():
        for alias in [name,*record['provides']]:providers.setdefault(re.split(r'[<>=]',alias,1)[0],[]).append(name)
    chosen=set();pending=[]
    for relative in required:
        owners=[name for name,row in records.items() if 'mingw64/'+relative in row['files']]
        if len(owners)!=1:raise BuildError('A required worker file lacks one installed MINGW64 package owner: '+relative)
        pending.extend(owners)
    while pending:
        name=pending.pop()
        if name in chosen:continue
        chosen.add(name)
        for dependency in records[name]['depends']:
            dep=re.split(r'[<>=]',dependency,1)[0]
            options=sorted(set(providers.get(dep,[])))
            if len(options)!=1:raise BuildError('An installed MINGW64 dependency is missing or ambiguous: '+dep)
            pending.append(options[0])
    return [records[name] for name in sorted(chosen)]


def verify_dependency_versions(msys, records):
    constraints=sorted({value for row in records for value in row['depends'] if re.search(r'[<>=]',value)})
    if not constraints:return
    if any(not re.fullmatch(r'mingw-w64-x86_64-[A-Za-z0-9+_.-]+(?:>=|<=|=|>|<)[A-Za-z0-9+_.:\-]+',value) for value in constraints):
        raise BuildError('An installed package dependency constraint is invalid.')
    # Pacman's read-only dependency operation handles Arch epochs, pkgrel and
    # versioned virtual providers. It never downloads or changes packages.
    executable=safe_path(Path(msys)/'usr/bin/pacman.exe')
    environment=os.environ.copy()
    environment['PATH']=str(executable.parent)
    try:
        result=subprocess.run([str(executable),'--deptest','--',*constraints],env=environment,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise BuildError('The read-only installed-package dependency check could not finish.') from None
    if result.returncode!=0:
        raise BuildError('Installed MINGW64 package versions do not satisfy their recorded dependencies. Preserve installed tools and send the audit.')


def manifest(msys, required):
    source=safe_path(Path(msys)/'mingw64',directory=True);files={};packages=[]
    selected=selection(msys,required)
    verify_dependency_versions(msys,selected)
    for record in selected:
        rows,mtree_hash=package_hashes(record)
        packages.append({'name':record['name'],'version':record['version'],'mtree_sha256':mtree_hash})
        for relative,expected in rows.items():
            if relative in files and files[relative]!=expected:raise BuildError('Installed packages disagree about a shared file.')
            path=safe_path(source/relative)
            if path.stat().st_nlink!=1 or path.stat().st_size!=expected['bytes'] or digest(path)!=expected['sha256']:
                raise BuildError('Installed package file differs from its integrity record: '+relative)
            files[relative]=expected
    if not files or len(files)>150000:raise BuildError('Worker dependency inventory exceeds its bound.')
    return {'format':1,'purpose':PURPOSE,'packages':packages,'files':files}


def verify(prefix=PREFIX):
    prefix=safe_path(prefix,directory=True)
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise BuildError('Duplicate dependency receipt key.')
            out[key]=value
        return out
    receipt=json.loads(read(prefix/'receipt.json').decode('utf-8'),object_pairs_hook=unique)
    if set(receipt)!={'format','purpose','packages','files'} or receipt['format']!=1 or receipt['purpose']!=PURPOSE:
        raise BuildError('This is not an owned isolated worker dependency prefix.')
    if not isinstance(receipt['files'],dict) or not 1<=len(receipt['files'])<=150000:raise BuildError('Invalid dependency inventory.')
    actual=set()
    for entry in prefix.rglob('*'):
        safe_path(entry,directory=entry.is_dir())
        if entry.is_file():actual.add(entry.relative_to(prefix).as_posix())
    if actual!=set(receipt['files'])|{'receipt.json'}:raise BuildError('Isolated dependency prefix contains missing or unrecorded files.')
    for relative,expected in receipt['files'].items():
        if not relative or relative.startswith('/') or '\\' in relative or ':' in relative or '..' in Path(relative).parts:
            raise BuildError('Unsafe dependency inventory path.')
        path=safe_path(prefix/relative)
        if (set(expected)!={'bytes','sha256'} or path.stat().st_nlink!=1 or path.stat().st_size!=expected['bytes'] or digest(path)!=expected['sha256']):
            raise BuildError('Isolated worker dependency changed: '+relative)
    return receipt


def prepare(msys,required,prefix=PREFIX):
    prefix=safe_path(prefix,directory=True) if prefix.exists() else safe_path(prefix)
    expected=manifest(msys,required)
    if prefix.exists():
        if verify(prefix)!=expected:raise BuildError('The prepared dependency prefix differs. Preserve it for review; no installed tools were changed.')
        print('WORLD WORKER ISOLATED DEPENDENCIES VERIFIED',flush=True);return prefix
    prefix.parent.mkdir(parents=True,exist_ok=True)
    staging=prefix.with_name(prefix.name+'.preparing-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex)
    staging.mkdir();source=Path(msys)/'mingw64'
    # Any interruption retains its uniquely named scratch tree; it is never a
    # usable prefix until every original package file and final receipt match.
    for relative,record in expected['files'].items():
        src=safe_path(source/relative);dst=staging/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
        if dst.stat().st_size!=record['bytes'] or digest(dst)!=record['sha256'] or digest(src)!=record['sha256']:
            raise BuildError('A dependency changed while copying. Retain the incomplete preparation for review.')
    write_new(staging/'receipt.json',expected);verify(staging)
    staging.rename(prefix);verify(prefix)
    print('WORLD WORKER ISOLATED DEPENDENCIES PREPARED',flush=True)
    return prefix
