"""RC-only changes, real CMake incremental behavior and guarded stage reuse.

The CMake tests compile actual host C/C++ but substitute the resource compiler;
real pinned PE windres/link/runtime evidence is recorded separately.
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


class WorkerResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker resource ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        (self.root / 'build').mkdir()

    def test_resource_cache_requires_exact_rule_and_preserves_conflicts(self):
        rules = worker.prepare_resource_rules(self.stage)
        (self.stage/'engine').mkdir()
        cache = self.stage / 'engine/CMakeCache.txt'
        correct = 'CMAKE_USER_MAKE_RULES_OVERRIDE:FILEPATH=' + rules.as_posix() + '\n'
        cache.write_text(correct)
        worker.verify_resource_rule(self.stage)
        for wrong in ('', correct + correct, correct.replace('worker-resource-rules', 'foreign'),
                      correct.replace(':FILEPATH=', ':UNINITIALIZED=')):
            cache.write_text(wrong)
            with self.assertRaises(worker.BuildError):
                worker.verify_resource_rule(self.stage)
            self.assertEqual(cache.read_text(), wrong)

    def test_resource_rule_file_reuses_exact_bytes_and_refuses_changed_content(self):
        rules = worker.prepare_resource_rules(self.stage)
        before = (rules.read_bytes(), rules.stat().st_mtime_ns)
        self.assertEqual(worker.prepare_resource_rules(self.stage), rules)
        self.assertEqual((rules.read_bytes(), rules.stat().st_mtime_ns), before)
        rules.write_bytes(b'foreign CMake rule')
        with self.assertRaisesRegex(worker.BuildError, 'resource rule changed'):
            worker.prepare_resource_rules(self.stage)
        self.assertEqual(rules.read_bytes(), b'foreign CMake rule')

    def overlay_fixture(self, out):
        out.mkdir()
        (out / 'change.cpp').write_bytes(b'owned overlay')
        (out / 'shared.hpp').write_bytes(b'owned header')
        return {'change.cpp': 'src/change.cpp'}, 'owned CMake\n'

    def test_identical_overlay_headers_keep_timestamps_and_changed_files_refuse(self):
        with patch.object(worker, 'STAGE', self.stage), \
             patch.object(worker, 'worker_overlay_inputs', side_effect=self.overlay_fixture):
            worker.prepare_worker_overlay()
            header = self.stage / 'overlay/shared.hpp'
            before = (header.read_bytes(), header.stat().st_mtime_ns)
            worker.prepare_worker_overlay()
            self.assertEqual((header.read_bytes(), header.stat().st_mtime_ns), before)
            header.write_bytes(b'changed header')
            with self.assertRaisesRegex(worker.BuildError, 'overlay changed'):
                worker.prepare_worker_overlay()
            self.assertEqual(header.read_bytes(), b'changed header')

    def test_readonly_transition_validation_requires_exact_source_and_toolchain(self):
        client = self.root / 'client'
        (client / 'engine/src').mkdir(parents=True)
        (client / 'engine/src/change.cpp').write_bytes(b'original')
        (client / 'engine/CMakeLists.txt').write_bytes(b'original CMake')
        prefix = self.root / 'prefix'
        prefix.mkdir()
        with patch.object(worker, 'STAGE', self.stage), patch.object(worker, 'CLIENT', client), \
             patch.object(worker, 'DEPENDENCY_PREFIX', prefix), \
             patch.object(worker, 'worker_overlay_inputs', side_effect=self.overlay_fixture):
            with self.assertRaisesRegex(worker.BuildError, 'existing overlay'):
                worker.prepare_worker_overlay(validate_existing=True)
            mapping, cmake = worker.prepare_worker_overlay()
            worker.prepare_source(client, self.stage/'source', self.stage/'overlay', mapping, cmake)
            worker.prepare_toolchain(self.stage, prefix)
            before = {p.relative_to(self.stage): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.stage.rglob('*') if p.is_file()}
            worker.prepare_worker_overlay(validate_existing=True)
            self.assertEqual(before, {p.relative_to(self.stage): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.stage.rglob('*') if p.is_file()})
            (self.stage/'source/src/change.cpp').write_bytes(b'changed source')
            with self.assertRaisesRegex(worker.BuildError, 'source copy'):
                worker.prepare_worker_overlay(validate_existing=True)

    def test_real_resource_preflight_omits_unneeded_definitions_and_includes(self):
        prefix = self.root / 'prefix with spaces'
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            self.assertFalse(any(x.startswith(('-D', '-I')) for x in args[1:]))
            if args[0].endswith('windres.exe'):
                self.assertTrue(args[-2].endswith('packaging/windows/wesnoth.rc'))
                self.assertIn('--preprocessor-arg=--sysroot=' + prefix.as_posix(), args)
                Path(args[-1]).write_bytes(b'controlled resource object')
                return subprocess.CompletedProcess(args, 0, b'')
            return subprocess.CompletedProcess(args, 0,
                b'file format pe-x86-64\narchitecture: i386:x86-64, flags 0x0\n')
        with patch.object(worker, 'ROOT', self.root), patch.object(worker.subprocess, 'run', side_effect=run), \
             redirect_stdout(io.StringIO()):
            result = worker.game_resource_preflight(prefix, {})
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(calls), 2)

    def test_resource_failure_retains_report_without_touching_existing_stage(self):
        sentinel = self.stage / 'compiled.obj'
        sentinel.write_bytes(b'keep this completed object')
        with patch.object(worker, 'ROOT', self.root), patch.object(worker.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 1, b'Files: No such file or directory')), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(worker.BuildError, 'resource-compile'):
                worker.game_resource_preflight(self.root/'prefix', {})
        reports = list((self.root/'build').glob('world-worker-resource-check-*/report.json'))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text())
        self.assertEqual((report['status'], report['failure_phase']), ('failed', 'resource-compile'))
        self.assertEqual(sentinel.read_bytes(), b'keep this completed object')

    def test_windows_system_libraries_are_not_copied_but_unknown_dll_still_rejects(self):
        output = self.root/'bin'; output.mkdir()
        prefix = self.root/'prefix'; (prefix/'bin').mkdir(parents=True)
        exe = output/'worker.exe'; exe.write_bytes(b'fixture PE')
        with patch.object(worker, 'capture', return_value='DLL Name: USP10.dll\nDLL Name: WLDAP32.dll\n'):
            result = worker.dll_closure(exe, prefix, output, {})
        self.assertEqual(result, {'private': {}, 'windows_system': ['usp10.dll', 'wldap32.dll']})
        self.assertEqual(list(output.iterdir()), [exe])
        with patch.object(worker, 'capture', return_value='DLL Name: foreign-driver.dll\n'):
            with self.assertRaisesRegex(worker.BuildError, 'missing'):
                worker.dll_closure(exe, prefix, output, {})

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('ninja') and shutil.which('cc')
        and shutil.which('c++') and os.name == 'posix', 'requires actual host CMake/Ninja/C/C++')
    def test_actual_cmake_rc_fix_keeps_completed_c_and_cpp_objects(self):
        source = self.root / 'source'; source.mkdir()
        output = self.stage / 'engine'
        args_file = self.root/'rc-args.json'
        compiler = self.root/'windres'
        compiler.write_text('#!' + sys.executable + '\n'
            'import json, sys\nfrom pathlib import Path\n'
            'Path(' + repr(str(args_file)) + ').write_text(json.dumps(sys.argv[1:]))\n'
            'if any("Program Files" in x for x in sys.argv): sys.exit(1)\n'
            'Path(sys.argv[-1]).write_bytes(b"controlled resource")\n')
        compiler.chmod(0o700)
        (source/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\n'
            'project(resource_retry LANGUAGES C CXX)\n'
            # Load the real Windows RC platform rule while retaining host
            # C/C++ compilation. A cache-only override must still fail.
            'include(Platform/Windows-windres)\nenable_language(RC)\n'
            'add_compile_definitions([=[WESNOTH_PATH="C:/Program Files (x86)/wesnoth/share/wesnoth"]=])\n'
            'include_directories("C:/Program Files (x86)/unneeded/includes")\n'
            'add_library(language_probe OBJECT probe.c probe.cpp)\n'
            'add_library(resource_probe OBJECT probe.rc)\n')
        for suffix in ('c', 'cpp'):
            (source/('probe.'+suffix)).write_text('#ifndef WESNOTH_PATH\n#error lost macro\n#endif\n'
                'const char *path_' + suffix + ' = WESNOTH_PATH;\n')
        (source/'probe.rc').write_text(worker.RESOURCE_PROBE)
        base = ['cmake', '-S', str(source), '-B', str(output), '-G', 'Ninja',
                '-DCMAKE_RC_COMPILER=' + str(compiler)]
        def run(args, success=True):
            result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
            self.assertEqual(result.returncode == 0, success, result.stdout)
            return result.stdout
        run(base)
        run(['cmake', '--build', str(output), '--target', 'language_probe'])
        objects = list(output.rglob('*.o'))
        self.assertEqual(len(objects), 2)
        before = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in objects}
        commands_before = run(['ninja', '-C', str(output), '-t', 'commands', 'language_probe'])
        run(['cmake', '--build', str(output), '--target', 'resource_probe'], success=False)
        self.assertTrue(any('Program Files' in x for x in json.loads(args_file.read_text())))
        run(base + ['-DCMAKE_RC_COMPILE_OBJECT:STRING=' + worker.RESOURCE_COMPILE_RULE])
        run(['cmake', '--build', str(output), '--target', 'resource_probe'], success=False)
        rules = worker.prepare_resource_rules(self.stage)
        run(base + ['-DCMAKE_USER_MAKE_RULES_OVERRIDE:FILEPATH=' + rules.as_posix()])
        worker.verify_resource_rule(self.stage)
        run(['cmake', '--build', str(output)])
        commands_after = run(['ninja', '-C', str(output), '-t', 'commands', 'language_probe'])
        self.assertEqual(commands_after, commands_before)
        self.assertEqual({str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in objects}, before)
        self.assertFalse(any(x.startswith(('-D', '-I')) for x in json.loads(args_file.read_text())))


if __name__ == '__main__':
    unittest.main()
