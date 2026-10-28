"""Relocated compiler setup and executable probes, not a full Windows build.

The optional CMake case executes the host's real C/C++ compiler.  PE compiler
execution is recorded separately in the worker compiler verification evidence.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import build_world_worker as worker


class WorkerToolchainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world toolchain ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = self.root / 'verified prefix'
        self.prefix.mkdir()
        self.stage = self.root / 'owned stage'
        self.stage.mkdir()

    def test_environment_removes_competing_compilers_without_mutating_parent(self):
        original = {
            'SystemRoot': str(self.root / 'Windows'), 'PATH': 'untrusted path',
            'CPATH': 'foreign includes', 'cplus_include_path': 'foreign C++',
            'CMAKE_TOOLCHAIN_FILE': 'foreign toolchain', 'cmake_prefix_path': 'other',
            'PKG_CONFIG_PATH': 'foreign pkg-config', 'pkg_config_libdir': 'other',
            'GCC_EXEC_PREFIX': 'foreign gcc', 'COMPILER_PATH': 'other compiler',
            'LIBRARY_PATH': 'foreign libs', 'CC': 'other c', 'CXX': 'other c++',
            'CPP': 'other preprocessor', 'CFLAGS': '-nostdinc', 'CXXFLAGS': '-nostdinc++',
            'CPPFLAGS': '-isystem foreign', 'LDFLAGS': 'foreign', 'RCFLAGS': '-I foreign',
            'SDKROOT': 'foreign SDK', 'LIB': 'other lib',
            'INCLUDE': 'other include', 'BOOST_ROOT': 'other boost',
            'BOOST_INCLUDEDIR': 'other include', 'BOOST_LIBRARYDIR': 'other lib',
            'TEMP': str(self.root / 'temp'), 'UNCHANGED': 'keep',
        }
        before = dict(original)
        cmake = self.root / 'cmake bin' / 'cmake.exe'
        result = worker.compiler_environment(self.prefix, cmake, original)
        self.assertEqual(original, before)
        self.assertEqual(result['UNCHANGED'], 'keep')
        self.assertEqual(result['TEMP'], original['TEMP'])
        self.assertEqual(result['PATH'].split(os.pathsep), [str(self.prefix / 'bin'),
            str(Path(original['SystemRoot']) / 'System32'), original['SystemRoot'], str(cmake.parent)])
        self.assertEqual(result['PKG_CONFIG_LIBDIR'].split(os.pathsep),
            [str(self.prefix / 'lib/pkgconfig'), str(self.prefix / 'share/pkgconfig')])
        remaining = {key.upper() for key in result}
        self.assertFalse(remaining & {key.upper() for key in original
            if key.upper().startswith(('CMAKE_', 'PKG_CONFIG_'))
            and key.upper() != 'PKG_CONFIG_LIBDIR'})
        for key in ('CPATH', 'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH',
                    'LIBRARY_PATH', 'CC', 'CXX', 'CPP', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS',
                    'LDFLAGS', 'RCFLAGS', 'SDKROOT', 'LIB', 'INCLUDE', 'BOOST_ROOT', 'BOOST_INCLUDEDIR', 'BOOST_LIBRARYDIR'):
            self.assertNotIn(key, remaining)

    def test_toolchain_binds_literal_sysroot_and_reuses_exact_file(self):
        prefix = self.root / 'verified $prefix with spaces'
        prefix.mkdir()
        expected = worker.toolchain_text(prefix)
        self.assertIn(prefix.as_posix().encode(), expected)
        self.assertIn(b'set(CMAKE_SYSROOT ', expected)
        self.assertIn(b'set(CMAKE_RC_FLAGS_INIT ', expected)
        self.assertIn(b'--use-temp-file', expected)
        self.assertIn(('"--preprocessor-arg=--sysroot=' + prefix.as_posix() + '"').encode(), expected)
        path = worker.prepare_toolchain(self.stage, prefix)
        self.assertEqual(path.read_bytes(), expected)
        before = (path.stat().st_mtime_ns, path.read_bytes())
        self.assertEqual(worker.prepare_toolchain(self.stage, prefix), path)
        self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), before)

    def test_toolchain_refuses_list_or_bracket_injection(self):
        for name in ('prefix;set(CMAKE_SYSROOT elsewhere)', 'prefix]==]injection',
                     'prefix\nnext', 'prefix"injection', 'prefix\x00tail'):
            with self.subTest(name=name), self.assertRaises(worker.BuildError):
                worker.toolchain_text(self.root / name)

    def test_existing_toolchain_conflict_is_preserved(self):
        path = worker.prepare_toolchain(self.stage, self.prefix)
        foreign = b'set(CMAKE_SYSROOT "/foreign")\n'
        path.write_bytes(foreign)
        with self.assertRaises(worker.BuildError):
            worker.prepare_toolchain(self.stage, self.prefix)
        self.assertEqual(path.read_bytes(), foreign)

    def test_symlink_toolchain_target_is_preserved(self):
        target = self.root / 'foreign.cmake'
        target.write_bytes(b'preserve foreign file')
        path = self.stage / 'worker-toolchain.cmake'
        path.symlink_to(target)
        with self.assertRaises(worker.BuildError):
            worker.prepare_toolchain(self.stage, self.prefix)
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_bytes(), b'preserve foreign file')

    def run_preflight(self, runner):
        output = io.StringIO()
        with patch.object(worker.subprocess, 'run', side_effect=runner), redirect_stdout(output):
            result = worker.compiler_preflight(self.prefix, {'PATH': 'controlled test'}, root=self.root)
        return result, output.getvalue()

    def controlled_compiler(self, command, **kwargs):
        """Test subprocess boundary only; never label these bytes as PE evidence."""
        self.assertEqual(kwargs['env'], {'PATH': 'controlled test'})
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(kwargs['timeout'], 120)
        if command[0].endswith('windres.exe'):
            self.assertIn('--use-temp-file', command)
            self.assertIn('--preprocessor-arg=--sysroot=' + self.prefix.as_posix(), command)
            source = Path(command[command.index('-i') + 1])
            self.assertIn('#include <windows.h>', source.read_text())
            Path(command[command.index('-o') + 1]).write_bytes(b'controlled resource object')
            return subprocess.CompletedProcess(command, 0, b'')
        if command[0].endswith('objdump.exe'):
            self.assertEqual(command[1], '-f')
            self.assertTrue(Path(command[2]).is_file())
            return subprocess.CompletedProcess(command, 0,
                b'probe-resource.o: file format pe-x86-64\narchitecture: i386:x86-64, flags 0x0\n')
        if '-o' in command:
            self.assertIn('--sysroot=' + self.prefix.as_posix(), command)
            self.assertIn('-pthread', command)
            source = Path(command[command.index('-o') - 1])
            text = source.read_text()
            if str(command[0]).endswith('g++.exe'):
                self.assertIn('-std=c++17', command)
                self.assertIn('#include <cstring>', text)
                self.assertIn('std::thread', text)
                self.assertIn('throw std::runtime_error', text)
            else:
                self.assertIn('#include <string.h>', text)
                self.assertIn('#include <windows.h>', text)
                self.assertIn('pthread_create', text)
            Path(command[command.index('-o') + 1]).write_bytes(b'controlled test executable')
            return subprocess.CompletedProcess(command, 0, b'')
        marker = 'WORLD_WORKER_CXX_RUNTIME_OK' if command[0].endswith('probe-cxx.exe') else 'WORLD_WORKER_C_RUNTIME_OK'
        return subprocess.CompletedProcess(command, 0, (marker + '\n').encode())

    def retained_report(self):
        folders = list(self.root.glob('world-worker-toolchain-check-*'))
        self.assertEqual(len(folders), 1)
        path = folders[0] / 'report.json'
        self.assertTrue((folders[0] / 'owner.json').is_file())
        return folders[0], json.loads(path.read_text())

    def test_compiler_preflight_requires_both_languages_compile_link_and_runtime(self):
        sentinel = self.stage / 'existing-build'
        sentinel.write_bytes(b'preserve previous stage')
        report, output = self.run_preflight(self.controlled_compiler)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual([row['phase'] for row in report['phases']],
                         ['c-compile', 'c-run', 'cxx-compile', 'cxx-run', 'rc-compile', 'rc-verify'])
        self.assertTrue(all(row['status'] == 'passed' and row['exit'] == 0 for row in report['phases']))
        self.assertIn('WORLD WORKER COMPILER CHECK PASSED', output)
        folder, retained = self.retained_report()
        self.assertEqual(retained, report)
        for name, (_, extension, _, _) in worker.COMPILER_PROBES.items():
            self.assertEqual(report[name]['source_sha256'],
                hashlib.sha256((folder / ('probe.' + extension)).read_bytes()).hexdigest())
            self.assertEqual(report[name]['executable_sha256'],
                hashlib.sha256((folder / ('probe-' + name + '.exe')).read_bytes()).hexdigest())
        self.assertEqual(sentinel.read_bytes(), b'preserve previous stage')
        self.assertEqual(list(self.prefix.iterdir()), [])
        self.assertEqual(report['rc']['object_sha256'],
            hashlib.sha256((folder / 'probe-resource.o').read_bytes()).hexdigest())

    def test_compiler_failure_retains_report_and_stops_before_execution(self):
        calls = []
        def failed(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1, b'fatal error: string.h: missing\n')
        output = io.StringIO()
        with patch.object(worker.subprocess, 'run', side_effect=failed), redirect_stdout(output):
            with self.assertRaisesRegex(worker.BuildError, 'c-compile'):
                worker.compiler_preflight(self.prefix, {}, root=self.root)
        folder, report = self.retained_report()
        self.assertEqual(len(calls), 1)
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'c-compile'))
        self.assertEqual((folder / 'c-compile.txt').read_bytes(), b'fatal error: string.h: missing\n')
        self.assertNotIn('WORLD WORKER COMPILER CHECK PASSED', output.getvalue())
        self.assertFalse((self.stage / 'worker-toolchain.cmake').exists())

    def test_runtime_failure_is_not_accepted_after_successful_compile(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            if '-o' in command:
                return self.controlled_compiler(command, **kwargs)
            return subprocess.CompletedProcess(command, -1073741515, b'')
        with self.assertRaisesRegex(worker.BuildError, 'c-run'):
            self.run_preflight(runner)
        folder, report = self.retained_report()
        self.assertEqual(len(calls), 2)
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'c-run'))
        self.assertTrue((folder / 'probe-c.exe').is_file())
        self.assertEqual(report['phases'][-1]['exit'], -1073741515)

    def test_success_exit_without_exact_runtime_marker_is_rejected(self):
        def runner(command, **kwargs):
            if '-o' in command:
                return self.controlled_compiler(command, **kwargs)
            return subprocess.CompletedProcess(command, 0, b'WORLD_WORKER_C_RUNTIME_OK extra\n')
        with self.assertRaisesRegex(worker.BuildError, 'did not confirm c-run'):
            self.run_preflight(runner)
        _, report = self.retained_report()
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'c-run'))
        self.assertNotIn('status', report['phases'][-1])

    def test_compiler_timeout_retains_failure_report(self):
        def timed_out(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        with self.assertRaisesRegex(worker.BuildError, 'timed out at c-compile'):
            self.run_preflight(timed_out)
        _, report = self.retained_report()
        self.assertEqual((report['status'], report['error'], report['failure_phase']),
                         ('failed', 'timeout', 'c-compile'))

    def test_launch_failure_retains_report_without_success(self):
        def missing(command, **kwargs):
            raise FileNotFoundError('controlled missing compiler')
        with self.assertRaises(FileNotFoundError):
            self.run_preflight(missing)
        _, report = self.retained_report()
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'c-compile'))

    def test_successful_c_probe_does_not_hide_cpp_runtime_failure(self):
        def runner(command, **kwargs):
            if command[0].endswith('probe-cxx.exe'):
                return subprocess.CompletedProcess(command, 0, b'')
            return self.controlled_compiler(command, **kwargs)
        with self.assertRaisesRegex(worker.BuildError, 'did not confirm cxx-run'):
            self.run_preflight(runner)
        _, report = self.retained_report()
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'cxx-run'))
        self.assertIn('c', report)
        self.assertNotIn('cxx', report)
        self.assertEqual(len(report['phases']), 4)

    def test_resource_header_failure_stops_after_c_and_cpp(self):
        def runner(command, **kwargs):
            if command[0].endswith('windres.exe'):
                return subprocess.CompletedProcess(command, 1, b'windows.h missing\n')
            return self.controlled_compiler(command, **kwargs)
        with self.assertRaisesRegex(worker.BuildError, 'rc-compile'):
            self.run_preflight(runner)
        folder, report = self.retained_report()
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'rc-compile'))
        self.assertEqual(len(report['phases']), 5)
        self.assertEqual((folder / 'rc-compile.txt').read_bytes(), b'windows.h missing\n')
        self.assertNotIn('rc', report)

    def test_success_exit_without_x64_resource_object_is_rejected(self):
        def runner(command, **kwargs):
            if command[0].endswith('objdump.exe'):
                return subprocess.CompletedProcess(command, 0,
                    b'probe-resource.o: file format pe-i386\narchitecture: i386, flags 0x0\n')
            return self.controlled_compiler(command, **kwargs)
        with self.assertRaisesRegex(worker.BuildError, 'x86_64 COFF object'):
            self.run_preflight(runner)
        _, report = self.retained_report()
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'rc-verify'))
        self.assertNotIn('status', report['phases'][-1])

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('ninja') and os.name == 'posix',
                         'requires host CMake/Ninja for real resource argv propagation')
    def test_actual_cmake_preserves_resource_sysroot_argument_with_spaces(self):
        # Genuine CMake/Ninja argument generation with a controlled resource
        # process; actual PE windres execution is separate Wine evidence.
        source = self.root / 'resource source'
        source.mkdir()
        calls = self.root / 'resource arguments.json'
        compiler = self.root / 'windres'
        compiler.write_text('#!' + sys.executable + '\n'
            'import json, sys\nfrom pathlib import Path\n'
            'Path(' + repr(str(calls)) + ').write_text(json.dumps(sys.argv[1:]))\n'
            'Path(sys.argv[-1]).write_bytes(b"controlled resource object")\n')
        compiler.chmod(0o700)
        toolchain = worker.prepare_toolchain(self.stage, self.prefix)
        (source / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\n'
            'project(resource_flags NONE)\nenable_language(RC)\n'
            'add_library(resource_probe OBJECT probe.rc)\n')
        (source / 'probe.rc').write_text(worker.RESOURCE_PROBE)
        build = self.root / 'resource build'
        commands = [['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
                     '-DCMAKE_SYSTEM_NAME=Windows', '-DCMAKE_RC_COMPILER=' + str(compiler),
                     '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain)],
                    ['cmake', '--build', str(build), '--verbose']]
        combined = ''
        for command in commands:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=90, check=False)
            combined += result.stdout
            self.assertEqual(result.returncode, 0, combined)
        arguments = json.loads(calls.read_text())
        self.assertIn('--use-temp-file', arguments)
        self.assertIn('--preprocessor-arg=--sysroot=' + self.prefix.as_posix(), arguments)
        self.assertEqual(sum(arg.startswith('--preprocessor-arg=--sysroot=') for arg in arguments), 1)

    def test_failed_preflight_cannot_modify_or_archive_full_worker_stage(self):
        from tools import world_worker_archive_prefix as archive
        original = self.stage / 'owner.json'
        original.write_bytes(b'{"purpose":"previous owned build"}\n')
        data = self.root / 'game data'
        data.mkdir()
        cmake = self.root / 'cmake.exe'
        cmake.write_bytes(b'controlled tool')
        msys = self.root / 'msys'
        ninja = msys / 'ucrt64/bin/ninja.exe'
        ninja.parent.mkdir(parents=True)
        ninja.write_bytes(b'controlled build runner')
        with patch.object(worker, 'check_host'), patch.object(archive, 'verify_locked_prefix'), \
             patch.object(worker, 'data_inventory', return_value={}), \
             patch.object(worker, 'compiler_environment', return_value={}), \
             patch.object(worker, 'REQUIRED', {}), patch.object(worker, 'DEPENDENCY_PREFIX', self.prefix), \
             patch.object(worker, 'STAGE', self.stage), patch.object(worker, 'ROOT', self.root), \
             patch.object(worker, 'capture', side_effect=['cmake version 4.3.0', '1.13.2',
                 'x86_64-w64-mingw32', '16.2.0']), \
             patch.object(worker, 'binding') as binding, \
             patch.object(worker, 'compiler_preflight', side_effect=worker.BuildError('preflight rejected')):
            with self.assertRaisesRegex(worker.BuildError, 'preflight rejected'):
                worker.build(msys, cmake, data, True)
        binding.assert_not_called()
        self.assertEqual(original.read_bytes(), b'{"purpose":"previous owned build"}\n')
        self.assertEqual(list(self.stage.iterdir()), [original])
        self.assertFalse(list(self.root.glob('owned stage-before-*')))

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('ninja')
                         and shutil.which('cc') and shutil.which('c++')
                         and os.name == 'posix', 'requires host CMake/Ninja/C/C++ for actual propagation')
    def test_actual_cmake_propagates_generated_sysroot_to_lua_style_target(self):
        source = self.root / 'cmake source'
        source.mkdir()
        # '/' is the real host sysroot here.  The compiler invocation and CMake
        # generated output are genuine; this is deliberately not a PE claim.
        toolchain = worker.prepare_toolchain(self.stage, Path('/'))
        original = toolchain.read_bytes()
        (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.20)
project(worker_sysroot_probe C CXX)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set_source_files_properties(lua_probe.c PROPERTIES LANGUAGE CXX)
set_source_files_properties(lua_probe.c PROPERTIES COMPILE_FLAGS "-include \\"${CMAKE_CURRENT_SOURCE_DIR}/forced.h\\" -x c++")
add_library(lua_probe STATIC lua_probe.c)
add_executable(c_probe c_probe.c)
find_package(Threads REQUIRED)
target_link_libraries(c_probe PRIVATE Threads::Threads)
''')
        (source / 'forced.h').write_text('#include <string.h>\n#include <stddef.h>\n')
        (source / 'lua_probe.c').write_text('#include <cstring>\n#include <string>\n'
            '#include <thread>\nstd::string check() { return std::string("x", std::strlen("x")); }\n')
        (source / 'c_probe.c').write_text('#include <string.h>\n#include <stdint.h>\n'
            '#include <pthread.h>\nint main(void) { pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER; '
            'pthread_mutex_lock(&m); pthread_mutex_unlock(&m); return strlen("x") != 1; }\n')
        build = self.root / 'cmake build'
        commands = [
            ['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
             '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain)],
            ['cmake', '--build', str(build), '--verbose'],
            [str(build / 'c_probe')],
        ]
        combined = ''
        for command in commands:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=90, check=False)
            combined += result.stdout
            self.assertEqual(result.returncode, 0, combined)
        rows = json.loads((build / 'compile_commands.json').read_text())
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn('--sysroot=/', row['command'])
        lua = next(row for row in rows if row['file'].endswith('lua_probe.c'))
        self.assertIn('-x c++', lua['command'])
        self.assertIn('-include', lua['command'])
        self.assertIn('--sysroot=/', combined)
        self.assertEqual(toolchain.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
