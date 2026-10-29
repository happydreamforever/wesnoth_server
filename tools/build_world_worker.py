"""Build the pinned full native World engine in an isolated preserving stage."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
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
import tempfile
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT.parent / 'wesnoth_client'
STAGE = ROOT / 'build/windows-world-worker'
sys.path.insert(0, str(ROOT))
from tools.build_alliance_bridge import BuildError, write_new, capture, check_host
from tools.world_worker_dependencies import safe_path, digest, package_records, manifest as dependency_manifest, PREFIX as DEPENDENCY_PREFIX

REQUIRED = {
    'compiler': 'bin/g++.exe', 'C compiler':'bin/gcc.exe', 'resource compiler':'bin/windres.exe', 'linker': 'bin/ld.exe', 'objdump': 'bin/objdump.exe',
    'pkg-config': 'bin/pkg-config.exe', 'C headers': 'include/string.h',
    'Windows headers': 'include/windows.h', 'POSIX thread headers': 'include/pthread.h',
    'OpenSSL': 'include/openssl/ssl.h',
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
    'dwrite.dll','windowscodecs.dll','propsys.dll','rpcrt4.dll','userenv.dll','psapi.dll','msimg32.dll',
    'usp10.dll','wldap32.dll'}  # Windows Uniscribe (HarfBuzz) and Windows LDAP (curl).

# The pinned .rc reads its own relative wesconfig.h, icon and manifest. It does
# not need C/C++ target macros or include paths, whose nested quotes windres
# reparses incorrectly on Windows (notably WESNOTH_PATH="Program Files ...").
# Keep every C/C++ command unchanged so the interrupted engine can resume.
RESOURCE_COMPILE_RULE = '<CMAKE_RC_COMPILER> -O coff <FLAGS> <SOURCE> <OBJECT>'


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
             ROOT/'tools/world_worker_recovery.py',
             ROOT/'tools/world_worker_resource_recovery.py',
             ROOT/'tools/world_worker_ninja_recovery.py',
             ROOT/'tools/world_worker_account_recovery.py',
             ROOT/'tools/world_worker_version_completion.py',
             ROOT/'tools/world-worker-packages-1192624.json', DEPENDENCY_PREFIX/'receipt.json']
    paths += [CLIENT/'tools'/name for name in ('prepare_android_source.py','verify_game_data.py','gamedata-1.19.26.reference.json')]
    paths += [path for directory in ('engine', 'alliance_game', 'alliance_native')
              for path in sorted((CLIENT / directory).rglob('*')) if path.is_file() and path.suffix not in ('.pyc',)]
    return {'format': 1, 'purpose': 'wesnoth-full-native-world-worker', 'release': 1192624,
            'inputs': {str(path.relative_to(ROOT.parent)).replace('\\','/'): digest(safe_path(path)) for path in paths}}


def dll_closure(executable, prefix, output, environment, *, copy_files=True):
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
            if copy_files:
                shutil.copy2(source, destination)
            else:
                safe_path(destination)
                if (destination.stat().st_nlink != 1 or source.stat().st_nlink != 1
                        or destination.stat().st_size != source.stat().st_size
                        or digest(destination) != digest(source)):
                    raise BuildError('Existing worker DLL differs from the pinned prefix; preserved.')
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


def worker_overlay_inputs(output):
    sys.path.insert(0, str(CLIENT / 'alliance_game'))
    from world_worker_overlay import generate, WORLD_SOURCES
    replacements = generate(CLIENT, output)
    additions = [(CLIENT/'alliance_game'/(name+'.cpp')).as_posix()
        for name in (*WORLD_SOURCES, 'hero_catalog', 'hero_unit_config', 'practice_plan', 'practice_scenario')]
    additions += [(CLIENT/'alliance_native'/(name+'.cpp')).as_posix()
        for name in ('transport', 'account_client', 'account_protocol')]
    return replacements, worker_cmake(CLIENT, STAGE/'overlay', additions)


def overlay_inventory(directory):
    safe_path(directory, directory=True)
    result = {}
    for path in directory.rglob('*'):
        safe_path(path, directory=path.is_dir())
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = digest(path)
    return result


def prepare_worker_overlay(*, validate_existing=False):
    """Derive outside the stage; preserve identical overlay/header timestamps."""
    with tempfile.TemporaryDirectory(prefix='world-worker-source-check-', dir=STAGE.parent) as scratch:
        temporary = Path(scratch) / 'overlay'
        replacements, cmake_text = worker_overlay_inputs(temporary)
        generated = STAGE / 'overlay'
        if generated.exists():
            if overlay_inventory(generated) != overlay_inventory(temporary):
                raise BuildError('Owned worker overlay changed; preserve the stage for review.')
        elif validate_existing:
            raise BuildError('Worker resource retry requires its existing overlay; preserved.')
        else:
            shutil.copytree(temporary, generated)
        if validate_existing:
            safe_path(STAGE / 'source', directory=True)
            toolchain = safe_path(STAGE / 'worker-toolchain.cmake')
            if toolchain.stat().st_nlink != 1 or toolchain.read_bytes() != toolchain_text(DEPENDENCY_PREFIX):
                raise BuildError('Worker resource retry toolchain changed; preserved.')
            prepare_source(CLIENT, STAGE/'source', temporary, replacements, cmake_text)
        return replacements, cmake_text


def native(command, environment):
    result = subprocess.run([str(part) for part in command], env=environment, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise BuildError(f'Native World worker build failed with exit {result.returncode}. Keep the saved log.')


def compiler_environment(prefix, cmake, environ=None):
    """Use only the selected compiler closure and the Windows system tools."""
    # Windows os.environ normalizes names to uppercase. Its case-insensitive
    # lookup behavior is lost when copied into an ordinary dict.
    environment = {}
    for name, value in (os.environ if environ is None else environ).items():
        key = name.upper()
        if key in environment:
            raise BuildError('The compiler environment contains duplicate Windows variable names.')
        environment[key] = value
    for name in list(environment):
        if name.upper().startswith(('CMAKE_', 'PKG_CONFIG_')) or name.upper() in (
                'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH',
                'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CC', 'CXX', 'CPP', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS',
                'LDFLAGS', 'RCFLAGS', 'LIB', 'INCLUDE', 'BOOST_ROOT', 'BOOST_INCLUDEDIR', 'BOOST_LIBRARYDIR', 'SDKROOT'):
            environment.pop(name)
    system_root = environment.get('SYSTEMROOT')
    if not isinstance(system_root, str) or not system_root.strip():
        raise BuildError('SystemRoot is missing or empty. Keep the build files and report this error.')
    system = Path(system_root)
    environment['PATH'] = os.pathsep.join((str(prefix / 'bin'), str(system / 'System32'), str(system), str(Path(cmake).parent)))
    environment['PKG_CONFIG_LIBDIR'] = str(prefix / 'lib/pkgconfig') + os.pathsep + str(prefix / 'share/pkgconfig')
    return environment


@contextmanager
def build_step(name):
    """Identify startup failures without printing environment or metadata values."""
    print('RUN World worker ' + name, flush=True)
    try:
        yield
    except BuildError as error:
        raise BuildError('World worker stage=' + name + ': ' + str(error)) from None
    except subprocess.TimeoutExpired:
        raise BuildError('World worker stage=' + name + '; error=timeout. Retain the build log.') from None
    except (OSError, ValueError, KeyError) as error:
        details = type(error).__name__
        for key in ('errno', 'winerror'):
            number = getattr(error, key, None)
            if type(number) is int:
                details += '; ' + key + '=' + str(number)
        raise BuildError('World worker stage=' + name + '; error=' + details + '. Retain the build log.') from None


def toolchain_text(prefix):
    value = Path(prefix).absolute().as_posix()
    if any(token in value for token in (';','\n','\r','\x00','"',']==]')):
        raise BuildError('The isolated prefix path cannot be represented in the worker toolchain.')
    # Bracket arguments preserve spaces and literal dollar signs. CMAKE_SYSROOT
    # must be set by a toolchain file so it also reaches compiler try-compiles.
    # CMake does not forward CMAKE_SYSROOT to windres. A temp file avoids
    # windres's shell pipeline, which also mishandles compiler paths with spaces.
    return ('# Owned World worker compiler root; the signed prefix remains unchanged.\n'
            'set(CMAKE_SYSROOT [==[' + value + ']==])\n'
            'set(CMAKE_RC_FLAGS_INIT [==[--use-temp-file "--preprocessor-arg=--sysroot='
            + value + '"]==])\n').encode('utf-8')


def prepare_toolchain(stage, prefix):
    path = safe_path(Path(stage) / 'worker-toolchain.cmake')
    expected = toolchain_text(prefix)
    if path.exists():
        if path.stat().st_nlink != 1 or path.read_bytes() != expected:
            raise BuildError('Owned worker toolchain changed; preserve it for review.')
    else:
        with path.open('xb') as stream:
            stream.write(expected); stream.flush(); os.fsync(stream.fileno())
    return path


COMPILER_PROBES = {
    'c': ('gcc.exe', 'c', 'WORLD_WORKER_C_RUNTIME_OK', r'''#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <windows.h>
#include <pthread.h>
static void *run(void *value) { *(int *)value = 7; return NULL; }
int main(void) {
    int value = 0; pthread_t thread; char text[8];
    memcpy(text, "worker", 7);
    if (!GetCurrentProcessId() || strcmp(text, "worker") || sizeof(uint64_t) != 8) return 1;
    if (pthread_create(&thread, NULL, run, &value) || pthread_join(thread, NULL) || value != 7) return 2;
    puts("WORLD_WORKER_C_RUNTIME_OK"); return 0;
}
'''),
    'cxx': ('g++.exe', 'cpp', 'WORLD_WORKER_CXX_RUNTIME_OK', r'''#include <cstring>
#include <string>
#include <thread>
#include <mutex>
#include <vector>
#include <iostream>
#include <stdexcept>
int main() {
    std::vector<int> values(1, 0); std::mutex mutex;
    std::thread thread([&] { std::lock_guard<std::mutex> guard(mutex); values[0] = 7; }); thread.join();
    if (values[0] != 7 || std::strcmp(std::string("worker").c_str(), "worker")) return 1;
    try { throw std::runtime_error("probe"); } catch (const std::runtime_error&) {}
    std::cout << "WORLD_WORKER_CXX_RUNTIME_OK\n"; return 0;
}
'''),
}


RESOURCE_PROBE = '''#include <windows.h>
1 VERSIONINFO
 FILEVERSION 1,19,26,0
 PRODUCTVERSION 1,19,26,0
 FILEOS VOS_NT_WINDOWS32
 FILETYPE VFT_APP
BEGIN
 BLOCK "StringFileInfo"
 BEGIN
  BLOCK "040904b0"
  BEGIN
   VALUE "FileDescription", "World worker compiler check\\0"
  END
 END
END
'''


def compiler_preflight(prefix, environment, root=None):
    """Compile/link/run C/C++ and compile an actual Windows resource."""
    parent = safe_path(Path(root) if root is not None else ROOT / 'build', directory=True)
    prefix = safe_path(prefix, directory=True)
    toolchain_text(prefix)  # Apply the same path restrictions as the real build.
    directory = parent / ('world-worker-toolchain-check-' + uuid4().hex)
    directory.mkdir(mode=0o700)
    write_new(directory / 'owner.json', {'format': 1, 'purpose': 'world-worker-compiler-check', 'prefix': str(prefix)})
    report = {'format': 1, 'purpose': 'world-worker-compiler-check', 'status': 'failed',
              'prefix': str(prefix), 'sysroot': prefix.as_posix(), 'phases': []}
    phase = 'prepare'
    print('Checking isolated C/C++ headers, threads and runtime DLLs: ' + str(directory), flush=True)
    try:
        for name, (compiler, extension, marker, source) in COMPILER_PROBES.items():
            source_path = directory / ('probe.' + extension)
            source_path.write_bytes(source.encode('utf-8'))
            executable = directory / ('probe-' + name + '.exe')
            command = [str(prefix / 'bin' / compiler), '--sysroot=' + prefix.as_posix(), '-pthread']
            if name == 'cxx': command.append('-std=c++17')
            command += [str(source_path), '-o', str(executable)]
            for action, arguments in (('compile', command), ('run', [str(executable)])):
                phase = name + '-' + action
                completed = subprocess.run(arguments, env=environment, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
                (directory / (phase + '.txt')).write_bytes(completed.stdout)
                row = {'phase': phase, 'exit': completed.returncode}
                report['phases'].append(row)
                if completed.returncode:
                    print(completed.stdout.decode('utf-8', 'replace'), flush=True)
                    raise BuildError('Isolated compiler check failed at ' + phase + '; retain its folder and the build log.')
                if action == 'run' and completed.stdout.decode('utf-8', 'replace').strip() != marker:
                    raise BuildError('Isolated compiler runtime did not confirm ' + phase + '; retain its report.')
                row['status'] = 'passed'
            report[name] = {'source_sha256': digest(source_path), 'executable_sha256': digest(executable)}
            print('PASS isolated ' + name.upper() + ' headers, threads and runtime', flush=True)
        resource = directory / 'probe.rc'
        resource.write_bytes(RESOURCE_PROBE.encode('utf-8'))
        resource_object = directory / 'probe-resource.o'
        resource_command = [str(prefix / 'bin/windres.exe'), '--use-temp-file',
            '--preprocessor-arg=--sysroot=' + prefix.as_posix(), '-O', 'coff',
            '-i', str(resource), '-o', str(resource_object)]
        for phase, arguments in (
                ('rc-compile', resource_command),
                ('rc-verify', [str(prefix / 'bin/objdump.exe'), '-f', str(resource_object)])):
            completed = subprocess.run(arguments, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            (directory / (phase + '.txt')).write_bytes(completed.stdout)
            row = {'phase': phase, 'exit': completed.returncode}
            report['phases'].append(row)
            if completed.returncode:
                print(completed.stdout.decode('utf-8', 'replace'), flush=True)
                raise BuildError('Isolated compiler check failed at ' + phase + '; retain its folder and the build log.')
            if phase == 'rc-verify' and (b'file format pe-x86-64' not in completed.stdout
                    or b'architecture: i386:x86-64' not in completed.stdout):
                raise BuildError('Isolated resource compiler did not produce an x86_64 COFF object; retain its report.')
            row['status'] = 'passed'
        report['rc'] = {'source_sha256': digest(resource), 'object_sha256': digest(resource_object)}
        print('PASS isolated Windows resource headers and x86_64 object', flush=True)
        report['status'] = 'passed'
        print('WORLD WORKER COMPILER CHECK PASSED', flush=True)
        return report
    except subprocess.TimeoutExpired:
        report['failure_phase'] = phase
        report['error'] = 'timeout'
        raise BuildError('Isolated compiler check timed out at ' + phase + '; retain its folder.') from None
    except (BuildError, OSError):
        report['failure_phase'] = phase
        raise
    finally:
        write_new(directory / 'report.json', report)
        print('Compiler check report: ' + str(directory / 'report.json'), flush=True)


def installed_worker(required=True, expected_binding=None):
    receipt_path = STAGE / 'receipt.json'
    if not receipt_path.exists():
        if required: raise BuildError('Build the full native World worker before starting Company or Castle battles.')
        return None
    row = metadata(receipt_path)
    expected_binding = binding() if expected_binding is None else expected_binding
    if set(row)!={'binding','executable','dlls','version','game_data','game_data_files','build_tools'} or row['binding'] != expected_binding:
        raise BuildError('World worker sources differ from the verified build.')
    if ('wesnoth_server/tools/world_worker_version_completion.py' in expected_binding.get('inputs', {})
            and row['version'] != '1.19.26'):
        raise BuildError('World worker receipt has an unexpected native engine version.')
    if set(row['build_tools'])!={'cmake','ninja'}:raise BuildError('World worker build-tool receipt is incomplete.')
    for tool in row['build_tools'].values():
        if set(tool)!={'path','sha256','version'} or not isinstance(tool['version'],str) or not tool['version']:
            raise BuildError('World worker build-tool receipt is invalid.')
        if digest(safe_path(tool['path']))!=tool['sha256']:
            raise BuildError('A pinned native worker build tool changed. Preserve the completed worker stage.')
    if 'wesnoth_server/tools/world_worker_recovery.py' in expected_binding.get('inputs', {}):
        toolchain = safe_path(STAGE / 'worker-toolchain.cmake')
        if toolchain.read_bytes() != toolchain_text(DEPENDENCY_PREFIX):
            raise BuildError('Worker compiler sysroot differs from the verified isolated prefix.')
    if 'wesnoth_server/tools/world_worker_resource_recovery.py' in expected_binding.get('inputs', {}):
        verify_resource_rule(STAGE)
    if 'wesnoth_server/tools/world_worker_ninja_recovery.py' in expected_binding.get('inputs', {}):
        verify_ninja_configuration(STAGE)
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


def resource_rules_text():
    # CMakeRCInformation includes the user rules AFTER Windows-windres, which
    # overwrites a plain CMAKE_RC_COMPILE_OBJECT cache value. This rule affects
    # only RC even when the same override file is loaded for C and C++.
    return ('# Owned World worker resource rule; C/C++ settings stay unchanged.\n'
            'set(CMAKE_RC_COMPILE_OBJECT [==[' + RESOURCE_COMPILE_RULE + ']==])\n').encode()


def prepare_resource_rules(stage):
    path = safe_path(Path(stage) / 'worker-resource-rules.cmake')
    raw = resource_rules_text()
    if path.exists():
        if path.stat().st_nlink != 1 or path.read_bytes() != raw:
            raise BuildError('Owned worker resource rule changed; preserve it for review.')
    else:
        with path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return path


def verify_resource_rule(stage):
    rules = safe_path(Path(stage) / 'worker-resource-rules.cmake')
    if rules.stat().st_nlink != 1 or rules.read_bytes() != resource_rules_text():
        raise BuildError('Worker resource rule differs from its verified recipe.')
    cache = safe_path(Path(stage) / 'engine/CMakeCache.txt')
    if cache.stat().st_nlink != 1:
        raise BuildError('Worker resource configuration cannot be linked.')
    rows = [line for line in cache.read_text(encoding='utf-8').splitlines()
            if line.startswith('CMAKE_USER_MAKE_RULES_OVERRIDE:')]
    if rows != ['CMAKE_USER_MAKE_RULES_OVERRIDE:FILEPATH=' + rules.as_posix()]:
        raise BuildError('Worker resource compile rule differs; preserve the stage for review.')


def verify_ninja_configuration(stage):
    """No implicit CMake invocation may bypass the metadata guard."""
    cache = safe_path(Path(stage) / 'engine/CMakeCache.txt')
    graph = safe_path(Path(stage) / 'engine/build.ninja')
    if cache.stat().st_nlink != 1 or graph.stat().st_nlink != 1:
        raise BuildError('Worker Ninja configuration cannot be linked.')
    rows = [line for line in cache.read_text(encoding='utf-8').splitlines()
            if line.startswith('CMAKE_SUPPRESS_REGENERATION:')]
    if rows != ['CMAKE_SUPPRESS_REGENERATION:BOOL=ON'] or re.search(
            r'^build [^\n]*: RERUN_CMAKE(?:\s|$)', graph.read_text(encoding='utf-8'), re.M):
        raise BuildError('Worker automatic regeneration is not disabled; preserve the guarded build.')


def game_resource_preflight(prefix, environment):
    """Exercise the actual pinned icon/version/manifest before resuming CMake."""
    directory = ROOT / 'build' / ('world-worker-resource-check-' + uuid4().hex)
    directory.mkdir()
    resource = safe_path(CLIENT / 'engine/packaging/windows/wesnoth.rc')
    output = directory / 'wesnoth-resource.o'
    report = {'format': 1, 'purpose': 'world-worker-game-resource-check', 'status': 'failed',
              'compile_rule': RESOURCE_COMPILE_RULE, 'source_sha256': digest(resource), 'phases': []}
    phase = 'resource-compile'
    try:
        for phase, command in (
                ('resource-compile', [prefix/'bin/windres.exe', '-O', 'coff', '--use-temp-file',
                    '--preprocessor-arg=--sysroot=' + prefix.as_posix(), resource, output]),
                ('resource-verify', [prefix/'bin/objdump.exe', '-f', output])):
            result = subprocess.run([str(part) for part in command], env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            (directory / (phase + '.txt')).write_bytes(result.stdout)
            row = {'phase': phase, 'exit': result.returncode}
            report['phases'].append(row)
            if result.returncode:
                print(result.stdout.decode('utf-8', 'replace'), flush=True)
                raise BuildError('Pinned game resource check failed at ' + phase + '; retain its report.')
            if phase == 'resource-verify' and (b'file format pe-x86-64' not in result.stdout
                    or b'architecture: i386:x86-64' not in result.stdout):
                raise BuildError('Pinned game resource is not an x86_64 COFF object; retain its report.')
            row['status'] = 'passed'
        report.update(status='passed', object_sha256=digest(output))
        print('WORLD WORKER GAME RESOURCE CHECK PASSED', flush=True)
        return report
    finally:
        if report['status'] != 'passed':
            report['failure_phase'] = phase
        write_new(directory / 'report.json', report)
        print('Game resource report: ' + str(directory / 'report.json'), flush=True)


def finish_linked_worker(msys, cmake, game_data, version_report):
    """Complete the reviewed linked stage without configuring or compiling it."""
    from tools import world_worker_version_completion as completion
    from tools.world_worker_archive_prefix import verify_locked_prefix
    with build_step('completion-source-binding'):
        expected = binding()

    def validate_stage():
        with build_step('completion-dependencies'):
            verify_locked_prefix()
            prefix = safe_path(DEPENDENCY_PREFIX, directory=True)
        with build_step('completion-game-data'):
            data = safe_path(game_data, directory=True)
            inventory = data_inventory(data)
        with build_step('completion-build-tools'):
            cmake_path = safe_path(cmake)
            ninja = safe_path(Path(msys) / 'ucrt64/bin/ninja.exe')
            environment = compiler_environment(prefix, cmake_path)
            cmake_lines = capture([cmake_path, '--version'], environment).splitlines()
            cmake_version = cmake_lines[0] if cmake_lines else ''
            ninja_version = capture([ninja, '--version'], environment)
            if cmake_version != 'cmake version 4.3.0' or ninja_version != '1.13.2':
                raise BuildError('Use the previously verified CMake 4.3.0 and Ninja 1.13.2.')
            build_tools = {name: {'path': str(path), 'sha256': digest(path), 'version': version}
                for name, path, version in (('cmake', cmake_path, cmake_version), ('ninja', ninja, ninja_version))}
        with build_step('completion-source-and-configuration'):
            prepare_worker_overlay(validate_existing=True)
            verify_resource_rule(STAGE)
            verify_ninja_configuration(STAGE)
        with build_step('completion-dll-closure'):
            output = safe_path(STAGE / 'bin', directory=True)
            executable = safe_path(output / 'world-worker.exe')
            closure = dll_closure(executable, prefix, output, environment, copy_files=False)
            expected_bin = {'world-worker.exe'} | {item['filename'].casefold() for item in closure['private'].values()}
            actual_bin = []
            for item in output.iterdir():
                safe_path(item)
                actual_bin.append(item.name.casefold())
            if len(actual_bin) != len(set(actual_bin)) or set(actual_bin) != expected_bin:
                raise BuildError('Existing worker bin differs from its DLL closure; preserved.')
        with build_step('completion-version'):
            version = completion.probe_version(executable, environment, STAGE.parent)
        with build_step('completion-input-stability'):
            if binding() != expected or data_inventory(data) != inventory:
                raise BuildError('Worker inputs changed during completion; preserved.')
            if any(digest(safe_path(item['path'])) != item['sha256'] for item in build_tools.values()):
                raise BuildError('Worker build tools changed during completion; preserved.')
        return {'binding': expected,
                'executable': {'sha256': digest(executable), 'bytes': executable.stat().st_size},
                'dlls': closure, 'version': version, 'game_data': str(data),
                'game_data_files': inventory, 'build_tools': build_tools}

    with build_step('reviewed-version-completion'):
        completion.finalize_reviewed(STAGE, expected, version_report, validate_stage)
    with build_step('completed-artifact-verification'):
        installed_worker()
    print('WORLD WORKER VERSION COMPLETION VERIFIED; existing compilation retained', flush=True)
    print('FULL NATIVE WORLD WORKER BUILD PASSED', flush=True)


def build(msys, cmake, game_data, preserve, ninja_report=None, version_report=None):
    with build_step('host'):
        check_host()
    if ninja_report is not None and not preserve:
        raise BuildError('Ninja recovery requires -PreservePreviousBuild and its reviewed report.')
    if version_report is not None and (not preserve or ninja_report is not None):
        raise BuildError('Version completion requires -PreservePreviousBuild and cannot use -NinjaReportPath.')
    from tools import world_worker_ninja_recovery as ninja_state
    from tools import world_worker_version_completion as completion
    STAGE.parent.mkdir(exist_ok=True)
    with ninja_state.build_lock(STAGE):
        # Match and retain the accepted stage before any historical recovery,
        # configuration, copy or compile operation can touch it.
        if version_report is not None or completion.pending(STAGE):
            if not preserve or ninja_report is not None:
                raise BuildError('Pending version completion requires -PreservePreviousBuild alone; preserve its journals.')
            return finish_linked_worker(msys, cmake, game_data, version_report)
        if STAGE.exists() and not (STAGE/'receipt.json').exists():
            owner = metadata(STAGE/'owner.json')
            if owner.get('inputs', {}).get('wesnoth_server/tools/build_world_worker.py') in completion.LEGACY_BUILDERS:
                raise BuildError('The linked worker requires -VersionReportPath with the accepted version JSON; preserve all files.')
        # A killed configure can leave the logs safely in its durable backup.
        # Restore them before source transitions or any subsequent CMake/Ninja.
        ninja_state.resume_configure(STAGE)
        return build_locked(msys, cmake, game_data, preserve, ninja_report)


def build_locked(msys, cmake, game_data, preserve, ninja_report=None):
    from tools import world_worker_ninja_recovery as ninja_state
    from tools.world_worker_archive_prefix import verify_locked_prefix
    with build_step('isolated-dependencies'):
        verify_locked_prefix()
        prefix = safe_path(DEPENDENCY_PREFIX, directory=True)
    with build_step('game-data'):
        data=safe_path(game_data,directory=True)
        initial_inventory=data_inventory(data)
    with build_step('compiler-environment'):
        environment = compiler_environment(prefix, cmake)
    with build_step('build-tools'):
        cmake=safe_path(cmake);ninja=safe_path(Path(msys)/'ucrt64/bin/ninja.exe')
        cmake_lines=capture([cmake,'--version'],environment).splitlines()
        cmake_version=cmake_lines[0] if cmake_lines else ''
        ninja_version=capture([ninja,'--version'],environment)
        if cmake_version!='cmake version 4.3.0' or ninja_version!='1.13.2':
            raise BuildError('Use the previously verified CMake 4.3.0 and Ninja 1.13.2; do not upgrade unrelated tools.')
        build_tools={name:{'path':str(path),'sha256':digest(path),'version':version}
            for name,path,version in (('cmake',cmake,cmake_version),('ninja',ninja,ninja_version))}
        diagnostics = ROOT / 'diagnostics'; diagnostics.mkdir(exist_ok=True)
    with build_step('compiler-identity'):
        for relative in REQUIRED.values():
            if not (prefix/relative).is_file() or not (prefix/relative).stat().st_size:raise BuildError('Prepared worker prefix is incomplete.')
        if (capture([prefix/'bin/g++.exe','-dumpmachine'],environment) != 'x86_64-w64-mingw32'
                or capture([prefix/'bin/g++.exe','-dumpfullversion','-dumpversion'],environment) != '16.2.0'):
            raise BuildError('Use the previously verified MINGW64 GCC 16.2.0 toolchain.')
    with build_step('compiler-check'):
        compiler_preflight(prefix, environment)
    with build_step('source-binding'):
        expected = binding()
    STAGE.parent.mkdir(exist_ok=True)
    with build_step('game-resource-check'):
        game_resource_preflight(prefix, environment)
    from tools import world_worker_account_recovery as account_source
    account_pending = account_source.account_recovery_pending(STAGE)
    account_owner = metadata(STAGE/'owner.json') if STAGE.exists() else None
    account_revision = (account_owner is not None and not (STAGE/'receipt.json').exists()
        and account_owner.get('inputs', {}).get('wesnoth_server/tools/build_world_worker.py')
            in account_source.LEGACY_BUILDERS and account_owner != expected)
    if ninja_report is not None and (account_pending or account_revision
            or account_owner is not None and account_source.INPUT in account_owner.get('inputs', {})):
        raise BuildError('Ninja history recovery is already complete. Omit -NinjaReportPath for this account-source continuation; retain the original report.')
    if account_pending or account_revision:
        if not preserve:
            raise BuildError('Account-source continuation requires -PreservePreviousBuild; retain all existing files.')
        def validate_account_source():
            prepare_worker_overlay(validate_existing=True)
            verify_resource_rule(STAGE)
            verify_ninja_configuration(STAGE)
        account_source.resume_account_stage(STAGE, expected, validate_account_source)
        print('WORLD WORKER ACCOUNT SOURCE RETRY PREPARED; existing compilation retained', flush=True)
    if ninja_report is not None or ninja_state.pending(STAGE):
        if not preserve:
            raise BuildError('Pending Ninja recovery requires -PreservePreviousBuild; retain all files.')
        ninja_state.recover_reviewed(STAGE, expected, ninja_report,
            lambda: prepare_worker_overlay(validate_existing=True))
        print('WORLD WORKER NINJA HISTORY RECOVERED; existing compilation retained', flush=True)
    elif (STAGE.exists() and not (STAGE/'receipt.json').exists()
            and metadata(STAGE/'owner.json').get('inputs', {}).get(
                'wesnoth_server/tools/build_world_worker.py') == ninja_state.REVIEWED_BUILDER):
        raise BuildError('This interrupted worker requires -NinjaReportPath with the reviewed JSON; preserve all files.')
    from tools.world_worker_resource_recovery import resource_recovery_pending, resume_resource_stage
    if resource_recovery_pending(STAGE) or (STAGE.exists()
            and not (STAGE/'receipt.json').exists()
            and metadata(STAGE/'owner.json') != expected
            and 'wesnoth_server/tools/world_worker_recovery.py' in metadata(STAGE/'owner.json').get('inputs', {})):
        if not preserve:
            raise BuildError('Worker resource retry requires -PreservePreviousBuild. Keep all existing files.')
        resume_resource_stage(STAGE, expected, lambda: prepare_worker_overlay(validate_existing=True))
        print('WORLD WORKER RESOURCE RETRY PREPARED; existing compilation retained', flush=True)
    from tools.world_worker_recovery import recovery_pending, preserve_failed_stage
    if recovery_pending(STAGE):
        if not preserve:
            raise BuildError('Worker recovery is pending. Preserve all files and use the documented preservation command.')
        retained = preserve_failed_stage(STAGE, expected)
        print('Incomplete worker build preserved: ' + str(retained), flush=True)
    if STAGE.exists():
        owner = metadata(STAGE/'owner.json')
        if owner != expected:
            if not preserve:
                raise BuildError('Existing worker stage differs; preserve it for review.')
            if not (STAGE/'receipt.json').exists():
                retained = preserve_failed_stage(STAGE, expected)
                print('Incomplete worker build preserved: ' + str(retained), flush=True)
            else:
                installed_worker(expected_binding=owner)
                STAGE.rename(STAGE.with_name(STAGE.name+'-before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex))
        elif (STAGE/'receipt.json').exists():
            installed_worker(); print('WORLD NATIVE WORKER ARTIFACT VERIFIED'); return
    if not STAGE.exists(): STAGE.mkdir();write_new(STAGE/'owner.json',expected)
    toolchain = prepare_toolchain(STAGE, prefix)
    resource_rules = prepare_resource_rules(STAGE)
    generated = STAGE/'overlay'
    replacements, cmake_text = prepare_worker_overlay()
    source = STAGE/'source'
    prepare_source(CLIENT,source,generated,replacements,cmake_text)
    ninja_state.configure(STAGE, [cmake,'-S',source,'-B',STAGE/'engine','-G','Ninja',f'-DCMAKE_USER_MAKE_RULES_OVERRIDE:FILEPATH={resource_rules.as_posix()}',f'-DCMAKE_TOOLCHAIN_FILE={toolchain.as_posix()}',f'-DCMAKE_CXX_COMPILER={(prefix/"bin/g++.exe").as_posix()}',
        f'-DCMAKE_C_COMPILER={(prefix/"bin/gcc.exe").as_posix()}',f'-DCMAKE_RC_COMPILER={(prefix/"bin/windres.exe").as_posix()}',
        f'-DPython_EXECUTABLE={safe_path(sys.executable).as_posix()}',
        f'-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}',f'-DCMAKE_PREFIX_PATH={prefix.as_posix()}',f'-DBoost_ROOT={prefix.as_posix()}',
        f'-DCMAKE_FIND_ROOT_PATH={prefix.as_posix()}','-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY','-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY','-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY',
        '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF','-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF',
        '-DCMAKE_BUILD_TYPE=Release','-DENABLE_SERVER=OFF','-DENABLE_CAMPAIGN_SERVER=OFF','-DENABLE_TESTS=OFF',
        '-DENABLE_NLS=OFF','-DENABLE_STRICT_COMPILATION=OFF','-DENABLE_DISPLAY_REVISION=OFF'],environment,native)
    verify_resource_rule(STAGE)
    verify_ninja_configuration(STAGE)
    native([cmake,'--build',STAGE/'engine','--target','wesnoth','--parallel','2'],environment)
    prepare_source(CLIENT,source,generated,replacements,cmake_text)
    candidates=list((STAGE/'engine').rglob('world-worker.exe'))
    if len(candidates)!=1: raise BuildError('Full native worker executable is missing or ambiguous.')
    output=STAGE/'bin';output.mkdir(exist_ok=True)
    executable=output/'world-worker.exe';shutil.copy2(candidates[0],executable)
    closure=dll_closure(executable,prefix,output,environment)
    from tools.world_worker_version_completion import probe_version
    version=probe_version(executable,environment,STAGE.parent)
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
    parser.add_argument('--ninja-report', type=Path,
        help='Reviewed Ninja diagnostic for preserving recovery of the interrupted worker.')
    parser.add_argument('--version-report', type=Path,
        help='Reviewed version diagnostic for completing the linked worker without recompilation.')
    args=parser.parse_args()
    try:
        if (args.ninja_report is not None or args.version_report is not None) and (args.prepare_dependencies or args.audit or args.verify):
            raise BuildError('Worker recovery/completion cannot be combined with another operation.')
        if args.prepare_dependencies:
            check_host()
            from tools.world_worker_packages import execute, CACHE, MANIFEST
            from tools.world_worker_archive_prefix import prepare_archive_prefix
            execute(args.msys, download=False)
            prepare_archive_prefix(manifest_path=MANIFEST, cache=CACHE, prefix=DEPENDENCY_PREFIX, msys=args.msys)
            return 0
        if args.audit:return 0 if dependency_audit(args.msys,args.audit)['complete'] else 1
        if args.verify:installed_worker();print('WORLD NATIVE WORKER ARTIFACT VERIFIED');return 0
        build(args.msys,args.cmake,args.game_data,args.preserve_previous,args.ninja_report,args.version_report);return 0
    except BuildError as error:
        print('ERROR: '+str(error),flush=True);return 1
    except (OSError,ValueError,KeyError):
        print('ERROR: World native worker preparation stopped. Retain the dependency report and build log.',flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
