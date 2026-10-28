"""Build the pinned full native World engine in an isolated preserving stage."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT.parent / 'wesnoth_client'
STAGE = ROOT / 'build/windows-world-worker'
sys.path.insert(0, str(ROOT))
from tools.build_alliance_bridge import BuildError, write_new, native, capture, check_host
from tools.world_worker_dependencies import safe_path, digest, package_records, manifest as dependency_manifest, PREFIX as DEPENDENCY_PREFIX

REQUIRED = {
    'compiler': 'bin/g++.exe', 'C compiler':'bin/gcc.exe', 'resource compiler':'bin/windres.exe', 'linker': 'bin/ld.exe', 'objdump': 'bin/objdump.exe',
    'pkg-config': 'bin/pkg-config.exe', 'OpenSSL': 'include/openssl/ssl.h',
    'Boost': 'include/boost/json.hpp', 'ICU': 'include/unicode/ucnv.h',
    'SDL3': 'include/SDL3/SDL.h', 'SDL3_image': 'include/SDL3_image/SDL_image.h',
    'SDL3_mixer': 'include/SDL3_mixer/SDL_mixer.h', 'Pango': 'include/pango-1.0/pango/pangocairo.h',
    'Cairo': 'include/cairo/cairo.h', 'Fontconfig': 'include/fontconfig/fontconfig.h',
    'Vorbis': 'include/vorbis/vorbisfile.h', 'Curl': 'include/curl/curl.h',
    'gettext': 'bin/msgfmt.exe', 'zlib': 'include/zlib.h',
}
SYSTEM_DLLS = {'kernel32.dll','user32.dll','gdi32.dll','advapi32.dll','shell32.dll','ole32.dll','oleaut32.dll',
    'ws2_32.dll','wsock32.dll','shlwapi.dll','winmm.dll','comdlg32.dll','comctl32.dll','version.dll','imm32.dll',
    'setupapi.dll','uuid.dll','msvcrt.dll','ucrtbase.dll','bcrypt.dll','crypt32.dll','secur32.dll','dwmapi.dll',
    'ntdll.dll','cfgmgr32.dll','iphlpapi.dll','winhttp.dll','dnsapi.dll','normaliz.dll','powrprof.dll','hid.dll',
    'wtsapi32.dll','winspool.drv','d3d11.dll','dxgi.dll','dinput8.dll','opengl32.dll','avrt.dll','d3d12.dll',
    'dwrite.dll','windowscodecs.dll','propsys.dll','rpcrt4.dll','userenv.dll','psapi.dll','msimg32.dll'}


def dependency_audit(msys, report):
    prefix = safe_path(Path(msys) / 'mingw64', directory=True)
    rows = []
    for name, relative in REQUIRED.items():
        path = prefix / relative
        present = path.is_file() and path.stat().st_size > 0
        if present: safe_path(path)
        rows.append({'name': name, 'relative_path': relative, 'present': present,
                     'sha256': digest(path) if present else None})
    result = {'format': 1, 'purpose': 'world-native-worker-dependency-audit', 'prefix': str(prefix),
              'files': rows, 'complete': all(row['present'] for row in rows),
              'runtime_tested': False, 'build_tested': False, 'package_integrity_verified': False,
              'installed_packages': [], 'cached_archives': []}
    try:
        records=package_records(msys)
        result['installed_packages']=[{'name':row['name'],'version':row['version'],'depends':row['depends']}
            for row in records.values()]
        if result['complete']:
            verified=dependency_manifest(msys,REQUIRED.values())
            result['verified_packages']=verified['packages']
            result['verified_file_count']=len(verified['files'])
            result['package_integrity_verified']=True
    except (BuildError,OSError,ValueError,KeyError) as error:
        result['package_integrity_error']=str(error) if isinstance(error,BuildError) else type(error).__name__
    cache=Path(msys)/'var/cache/pacman/pkg'
    if cache.is_dir():
        safe_path(cache,directory=True)
        for path in sorted(cache.glob('mingw-w64-x86_64-*.pkg.tar.*')):
            if not path.name.endswith('.sig') and path.is_file():
                safe_path(path)
                result['cached_archives'].append({'filename':path.name,'bytes':path.stat().st_size})
    result['complete']=result['complete'] and result['package_integrity_verified']
    write_new(safe_path(report), result)
    for row in rows: print(('PRESENT ' if row['present'] else 'MISSING ') + row['name'], flush=True)
    print('WORLD WORKER DEPENDENCY AUDIT ' + ('COMPLETE' if result['complete'] else 'INCOMPLETE'), flush=True)
    print('Installed package integrity: '+('verified' if result['package_integrity_verified'] else 'incomplete'), flush=True)
    print('Native compilation and DLL execution are not proven by this audit.', flush=True)
    return result


def verify_engine():
    path=CLIENT/'tools/prepare_android_source.py'
    spec=importlib.util.spec_from_file_location('world_pinned_source',safe_path(path))
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    try:
        sources,_=verifier.verified_source(CLIENT/'engine')
    except verifier.PreparationError as error:
        raise BuildError(str(error)) from error
    expected=set(sources)-{verifier.ORIGINAL_MANIFEST}|{'source-manifest.json'}
    actual={path.relative_to(CLIENT/'engine').as_posix() for path in (CLIENT/'engine').rglob('*') if path.is_file()}
    if actual!=expected:raise BuildError('Pinned engine contains unrecorded files. Preserve the source tree for review.')


def binding():
    verify_engine()
    paths = [ROOT / 'tools/build_world_worker.py', ROOT/'tools/world_worker_dependencies.py',
             ROOT/'tools/world_worker_packages.py', ROOT/'tools/world_worker_archive_prefix.py',
             ROOT/'tools/world-worker-packages-1192624.json', DEPENDENCY_PREFIX/'receipt.json']
    paths += [CLIENT/'tools'/name for name in ('prepare_android_source.py','verify_game_data.py','gamedata-1.19.26.reference.json')]
    paths += [path for directory in ('engine', 'alliance_game', 'alliance_native')
              for path in sorted((CLIENT / directory).rglob('*')) if path.is_file() and path.suffix not in ('.pyc',)]
    return {'format': 1, 'purpose': 'wesnoth-full-native-world-worker', 'release': 1192624,
            'inputs': {str(path.relative_to(ROOT.parent)).replace('\\','/'): digest(safe_path(path)) for path in paths}}


def dll_closure(executable, prefix, output, environment):
    queue, copied, system = [executable], {}, set()
    names = {path.name.casefold(): path for path in (prefix / 'bin').glob('*.dll')}
    while queue:
        target = queue.pop()
        text = capture([prefix / 'bin/objdump.exe', '-p', target], environment)
        for name in re.findall(r'DLL Name:\s*(\S+)', text):
            lower = name.casefold()
            if lower.startswith(('api-ms-win-', 'ext-ms-win-')) or lower in SYSTEM_DLLS:
                system.add(lower); continue
            if lower in copied: continue
            source = names.get(lower)
            if source is None: raise BuildError('Native worker DLL is missing from the selected MINGW64 prefix: ' + name)
            safe_path(source)
            destination = output / source.name
            shutil.copy2(source, destination)
            copied[lower] = {'filename': source.name, 'bytes': destination.stat().st_size, 'sha256': digest(destination)}
            queue.append(destination)
    return {'private': copied, 'windows_system': sorted(system)}


def metadata(path):
    path = safe_path(path)
    if path.stat().st_nlink != 1 or path.stat().st_size > 16*1024*1024:
        raise BuildError('World worker metadata is oversized or linked.')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise BuildError('World worker metadata has duplicate fields.')
            result[key]=value
        return result
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)


def verify_pinned_data(rows):
    """Never bless an arbitrary first-build game-data tree into a receipt."""
    expected = {'files':26748,'bytes':726207542,
        'tree_sha256':'d805fd055b263a5b09cd19576dc9df83c64e47bbcf7821cbb6550b686a74e53c'}
    reference=metadata(CLIENT/'tools/gamedata-1.19.26.reference.json')
    if any(reference.get(key)!=value for key,value in expected.items()):
        raise BuildError('Existing game-data reference differs from the selected 1.19.26 pin.')
    tree=hashlib.sha256()
    for name,item in sorted(rows.items()):
        tree.update((json.dumps([name,item['bytes'],item['sha256']],ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii'))
    actual={'files':len(rows),'bytes':sum(item['bytes'] for item in rows.values()),'tree_sha256':tree.hexdigest()}
    if actual!=expected:
        raise BuildError('Game data differs from the pinned 1.19.26 tree. Preserve it and run tools/verify_game_data.py from the client.')


def data_inventory(path):
    path=safe_path(path,directory=True)
    if not (path/'data/_main.cfg').is_file(): raise BuildError('Pinned game data is missing.')
    rows={}
    for entry in sorted(path.rglob('*')):
        safe_path(entry,directory=entry.is_dir())
        if entry.is_file():
            if entry.stat().st_nlink != 1: raise BuildError('Game data must not use hard links.')
            rows[entry.relative_to(path).as_posix()]={'bytes':entry.stat().st_size,'sha256':digest(entry)}
    if not rows or len(rows)>100000: raise BuildError('Game data inventory exceeds its bound.')
    verify_pinned_data(rows)
    return rows


def worker_cmake(client, generated, additions):
    """Adapt the pinned, flattened engine without changing its source tree."""
    text=(client/'engine/CMakeLists.txt').read_text()
    old='if(NOT EXISTS "${CMAKE_SOURCE_DIR}/src/modules/lua/.git")'
    new='if(NOT EXISTS "${CMAKE_SOURCE_DIR}/src/modules/lua/lua.h" OR NOT EXISTS "${CMAKE_SOURCE_DIR}/src/modules/lua/lapi.c")'
    boost='set(BOOST_REQ_COMPONENTS iostreams program_options regex thread random coroutine locale filesystem graph)'
    if text.count(old)!=1 or text.count(boost)!=1:
        raise BuildError('Pinned native CMake layout differs; retain the previous build.')
    for name in ('lua.h','lapi.c'):
        if not (client/'engine/src/modules/lua'/name).is_file():
            raise BuildError('Pinned flattened Lua sources are missing.')
    text=text.replace(old,new).replace(boost,boost[:-1]+' container)')
    text+='\nforeach(t wesnoth wesnoth-client wesnoth-common wesnoth-widgets)\nif(TARGET ${t})\ntarget_include_directories(${t} PRIVATE "'+client.as_posix()+'" "'+generated.as_posix()+'")\n'
    text+='target_link_libraries(${t} Boost::headers SDL3::SDL3 SDL3_image::SDL3_image SDL3_mixer::SDL3_mixer Fontconfig::Fontconfig OpenSSL::SSL OpenSSL::Crypto CURL::libcurl)\nendif()\nendforeach()\n'
    text+='target_sources(wesnoth PRIVATE\n'+''.join('"'+path+'"\n' for path in additions)+')\nset_target_properties(wesnoth PROPERTIES WIN32_EXECUTABLE FALSE OUTPUT_NAME world-worker)\n'
    # The pinned engine uses the plain target_link_libraries signature.
    text+='target_link_libraries(wesnoth OpenSSL::SSL OpenSSL::Crypto Boost::container)\n'
    return text


def prepare_source(client, source, generated, replacements, cmake_text):
    """An interrupted owned copy is never trusted merely because it exists."""
    original=client/'engine'
    expected={path.relative_to(original).as_posix():{'bytes':path.stat().st_size,'sha256':digest(path)}
        for path in original.rglob('*') if path.is_file()}
    for name,relative in replacements.items():
        path=generated/name
        expected[relative]={'bytes':path.stat().st_size,'sha256':digest(path)}
    raw=cmake_text.encode('utf-8')
    expected['CMakeLists.txt']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    if not source.exists():
        shutil.copytree(original,source)
        for name,relative in replacements.items():shutil.copy2(generated/name,source/relative)
        (source/'CMakeLists.txt').write_bytes(raw)
    actual={}
    for path in source.rglob('*'):
        safe_path(path,directory=path.is_dir())
        if path.is_file():actual[path.relative_to(source).as_posix()]={'bytes':path.stat().st_size,'sha256':digest(path)}
    if actual!=expected:
        raise BuildError('Owned worker source copy is incomplete or changed. Retain it for review; original sources were not changed.')
    return expected


def installed_worker(required=True, expected_binding=None):
    receipt_path = STAGE / 'receipt.json'
    if not receipt_path.exists():
        if required: raise BuildError('Build the full native World worker before starting Company or Castle battles.')
        return None
    row = metadata(receipt_path)
    expected_binding = binding() if expected_binding is None else expected_binding
    if set(row)!={'binding','executable','dlls','version','game_data','game_data_files','build_tools'} or row['binding'] != expected_binding:
        raise BuildError('World worker sources differ from the verified build.')
    if set(row['build_tools'])!={'cmake','ninja'}:raise BuildError('World worker build-tool receipt is incomplete.')
    for tool in row['build_tools'].values():
        if set(tool)!={'path','sha256','version'} or not isinstance(tool['version'],str) or not tool['version']:
            raise BuildError('World worker build-tool receipt is invalid.')
        if digest(safe_path(tool['path']))!=tool['sha256']:
            raise BuildError('A pinned native worker build tool changed. Preserve the completed worker stage.')
    executable = safe_path(STAGE / 'bin/world-worker.exe')
    if row['executable'] != {'sha256':digest(executable),'bytes':executable.stat().st_size}:
        raise BuildError('World worker executable differs from its receipt.')
    expected_bin={'world-worker.exe'}
    for item in row['dlls']['private'].values():
        if (set(item)!={'filename','bytes','sha256'} or not re.fullmatch(r'[A-Za-z0-9_.+\-]+\.dll',item['filename'],re.I)
                or item['filename'] in ('.','..') or not re.fullmatch(r'[0-9a-f]{64}',item['sha256'])):
            raise BuildError('World worker DLL receipt is invalid.')
        if item['filename'].casefold() in expected_bin:
            raise BuildError('World worker DLL receipt repeats a filename.')
        expected_bin.add(item['filename'].casefold())
        path = safe_path(STAGE / 'bin' / item['filename'])
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise BuildError('World worker private DLL differs from its receipt.')
    actual_bin=[]
    for path in (STAGE/'bin').iterdir():
        safe_path(path)
        actual_bin.append(path.name.casefold())
    if len(actual_bin)!=len(set(actual_bin)) or set(actual_bin)!=expected_bin:
        raise BuildError('World worker bin contains missing or unrecorded files.')
    data = safe_path(Path(row['game_data']), directory=True)
    if data_inventory(data) != row['game_data_files']: raise BuildError('Pinned game data differs from the worker receipt.')
    return {'executable': executable, 'game_data': data}


def build(msys, cmake, game_data, preserve):
    check_host()
    from tools.world_worker_archive_prefix import verify_locked_prefix
    verify_locked_prefix()
    data=safe_path(game_data,directory=True)
    initial_inventory=data_inventory(data)
    prefix = safe_path(DEPENDENCY_PREFIX, directory=True)
    environment = os.environ.copy()
    for name in list(environment):
        if name.upper().startswith(('CMAKE_','PKG_CONFIG_')) or name.upper() in (
                'CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH','LIBRARY_PATH',
                'GCC_EXEC_PREFIX','COMPILER_PATH','CC','CXX','CPP','CFLAGS','CXXFLAGS','CPPFLAGS',
                'LDFLAGS','LIB','INCLUDE','BOOST_ROOT','BOOST_INCLUDEDIR','BOOST_LIBRARYDIR'):
            environment.pop(name)
    environment['PATH'] = os.pathsep.join((str(prefix/'bin'),str(Path(os.environ['SystemRoot'])/'System32'),str(Path(os.environ['SystemRoot'])),str(Path(cmake).parent)))
    environment['PKG_CONFIG_LIBDIR'] = str(prefix / 'lib/pkgconfig') + os.pathsep + str(prefix / 'share/pkgconfig')
    environment.pop('PKG_CONFIG_PATH', None)
    cmake=safe_path(cmake);ninja=safe_path(Path(msys)/'ucrt64/bin/ninja.exe')
    cmake_version=capture([cmake,'--version'],environment).splitlines()[0]
    ninja_version=capture([ninja,'--version'],environment)
    if cmake_version!='cmake version 4.3.0' or ninja_version!='1.13.2':
        raise BuildError('Use the previously verified CMake 4.3.0 and Ninja 1.13.2; do not upgrade unrelated tools.')
    build_tools={name:{'path':str(path),'sha256':digest(path),'version':version}
        for name,path,version in (('cmake',cmake,cmake_version),('ninja',ninja,ninja_version))}
    diagnostics = ROOT / 'diagnostics'; diagnostics.mkdir(exist_ok=True)
    for relative in REQUIRED.values():
        if not (prefix/relative).is_file() or not (prefix/relative).stat().st_size:raise BuildError('Prepared worker prefix is incomplete.')
    if (capture([prefix/'bin/g++.exe','-dumpmachine'],environment) != 'x86_64-w64-mingw32'
            or capture([prefix/'bin/g++.exe','-dumpfullversion','-dumpversion'],environment) != '16.2.0'):
        raise BuildError('Use the previously verified MINGW64 GCC 16.2.0 toolchain.')
    expected = binding()
    STAGE.parent.mkdir(exist_ok=True)
    if STAGE.exists():
        owner = metadata(STAGE/'owner.json')
        if owner != expected:
            if not preserve or not (STAGE/'receipt.json').is_file():
                raise BuildError('Existing worker stage differs or is incomplete; preserve it for review.')
            installed_worker(expected_binding=owner)
            STAGE.rename(STAGE.with_name(STAGE.name+'-before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex))
        elif (STAGE/'receipt.json').exists():
            installed_worker(); print('WORLD NATIVE WORKER ARTIFACT VERIFIED'); return
    if not STAGE.exists(): STAGE.mkdir();write_new(STAGE/'owner.json',expected)
    sys.path.insert(0, str(CLIENT/'alliance_game'))
    from world_worker_overlay import generate, WORLD_SOURCES
    generated = STAGE/'overlay'
    replacements = generate(CLIENT, generated)
    source = STAGE/'source'
    additions = [(CLIENT/'alliance_game'/(name+'.cpp')).as_posix() for name in (*WORLD_SOURCES,'hero_catalog','hero_unit_config','practice_plan','practice_scenario')]
    additions += [(CLIENT/'alliance_native'/(name+'.cpp')).as_posix() for name in ('transport','account_client','account_protocol')]
    cmake_text = worker_cmake(CLIENT, generated, additions)
    prepare_source(CLIENT,source,generated,replacements,cmake_text)
    native([cmake,'-S',source,'-B',STAGE/'engine','-G','Ninja',f'-DCMAKE_CXX_COMPILER={(prefix/"bin/g++.exe").as_posix()}',
        f'-DCMAKE_C_COMPILER={(prefix/"bin/gcc.exe").as_posix()}',f'-DCMAKE_RC_COMPILER={(prefix/"bin/windres.exe").as_posix()}',
        f'-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}',f'-DCMAKE_PREFIX_PATH={prefix.as_posix()}',f'-DBoost_ROOT={prefix.as_posix()}',
        f'-DCMAKE_FIND_ROOT_PATH={prefix.as_posix()}','-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY','-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY','-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY',
        '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF','-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF',
        '-DCMAKE_BUILD_TYPE=Release','-DENABLE_SERVER=OFF','-DENABLE_CAMPAIGN_SERVER=OFF','-DENABLE_TESTS=OFF',
        '-DENABLE_NLS=OFF','-DENABLE_STRICT_COMPILATION=OFF','-DENABLE_DISPLAY_REVISION=OFF'],environment)
    native([cmake,'--build',STAGE/'engine','--target','wesnoth','--parallel','2'],environment)
    prepare_source(CLIENT,source,generated,replacements,cmake_text)
    candidates=list((STAGE/'engine').rglob('world-worker.exe'))
    if len(candidates)!=1: raise BuildError('Full native worker executable is missing or ambiguous.')
    output=STAGE/'bin';output.mkdir(exist_ok=True)
    executable=output/'world-worker.exe';shutil.copy2(candidates[0],executable)
    closure=dll_closure(executable,prefix,output,environment)
    clean=environment.copy();clean['PATH']=str(output)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
    version=capture([executable,'--version'],clean)
    if '1.19.26' not in version: raise BuildError('Full native engine version differs.')
    data=safe_path(game_data,directory=True)
    inventory=data_inventory(data)
    if inventory!=initial_inventory:raise BuildError('Pinned game data changed during the native worker build.')
    if binding()!=expected: raise BuildError('Native worker inputs changed during build.')
    if any(digest(item['path'])!=item['sha256'] for item in build_tools.values()):
        raise BuildError('Native worker build tools changed during compilation.')
    write_new(STAGE/'receipt.json',{'binding':expected,'executable':{'sha256':digest(executable),'bytes':executable.stat().st_size},
        'dlls':closure,'version':version,'game_data':str(data),'game_data_files':inventory,'build_tools':build_tools})
    installed_worker();print('FULL NATIVE WORLD WORKER BUILD PASSED',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msys',type=Path,default=Path(r'D:\Test\wesnoth-setup\msys64'))
    parser.add_argument('--cmake',type=Path,default=Path(r'C:\Program Files\CMake\bin\cmake.exe'))
    parser.add_argument('--game-data',type=Path,default=ROOT.parent/'gamedata-1.19.26')
    parser.add_argument('--prepare-dependencies',action='store_true');parser.add_argument('--audit',type=Path);parser.add_argument('--verify',action='store_true');parser.add_argument('--preserve-previous',action='store_true')
    args=parser.parse_args()
    try:
        if args.prepare_dependencies:
            check_host()
            from tools.world_worker_packages import execute, CACHE, MANIFEST
            from tools.world_worker_archive_prefix import prepare_archive_prefix
            execute(args.msys, download=False)
            prepare_archive_prefix(manifest_path=MANIFEST, cache=CACHE, prefix=DEPENDENCY_PREFIX)
            return 0
        if args.audit:return 0 if dependency_audit(args.msys,args.audit)['complete'] else 1
        if args.verify:installed_worker();print('WORLD NATIVE WORKER ARTIFACT VERIFIED');return 0
        build(args.msys,args.cmake,args.game_data,args.preserve_previous);return 0
    except BuildError as error:
        print('ERROR: '+str(error),flush=True);return 1
    except (OSError,ValueError,KeyError):
        print('ERROR: World native worker preparation stopped. Retain the dependency report and build log.',flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
