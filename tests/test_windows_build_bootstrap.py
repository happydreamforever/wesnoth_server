#!/usr/bin/env python3
"""Exercise the actual MSYS2 helper without downloading or compiling anything.

Run on the VPS with Python's standard library and the already prepared image:
    python3 tests/test_windows_build_bootstrap.py

Only this file and the selected helper are mounted read-only. All fake tools and
source layouts live in a disposable, network-disabled container. The helper is
copied byte-for-byte: its /usr/bin and /mingw64 paths are not rewritten. This
checks Bash startup/path handling, not Windows/MSYS2 execution or compilation.
Use --script /path/to/old-helper.sh to demonstrate a regression in an old copy.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


MOCK_TOOL = r'''#!/usr/bin/python3
import json, os, posixpath, sys
from pathlib import Path
cfg = json.loads(Path(os.environ['WESNOTH_FIXTURE_CONFIG']).read_text())
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
with Path(cfg['log']).open('a') as output:
    output.write(json.dumps({'tool': tool, 'args': args,
        'msystem': os.environ.get('MSYSTEM'),
        'arg_conversion': os.environ.get('MSYS2_ARG_CONV_EXCL')}) + '\n')
if tool == 'cygpath':
    assert len(args) == 2, args
    mode, value = args
    if mode == '-u':
        translations = {cfg['cmake_windows']: cfg['cmake'], cfg['ninja_windows']: cfg['ninja']}
        print(translations.get(value, value))
    elif mode == '-am':
        value = posixpath.normpath(value)
        if value == cfg['repo'] or value.startswith(cfg['repo'] + '/'):
            print(cfg['repo_windows'] + value[len(cfg['repo']):])
        elif value == '/mingw64' or value.startswith('/mingw64/'):
            print(cfg['mingw_windows'] + value[len('/mingw64'):])
        elif value == cfg['ninja']:
            print(cfg['ninja_windows'].replace('\\', '/'))
        else:
            # Model MSYS2's root mapping. The original bug incorrectly uses
            # this installation directory as the source passed to CMake.
            print('D:/Test/msys64' + ('' if value == '/' else value))
    else:
        raise AssertionError(args)
elif tool == 'pacman':
    assert args and args[0] == '-Q', 'Only local package queries are permitted.'
    print('fixture installed package metadata')
elif tool == 'g++.exe':
    assert args in (['-dumpmachine'], ['--version']), args
    print('x86_64-w64-mingw32' if args == ['-dumpmachine'] else 'g++ fixture 16.2.0')
elif tool == 'ninja.exe':
    assert args == ['--version'], args
    print('1.13.2 fixture')
elif tool == 'cmake.exe':
    if args == ['--version']:
        print('cmake version 4.3.0 fixture')
    elif args and args[0] == '-S':
        sys.exit(cfg['configure_exit'])
    elif args and args[0] == '--build':
        binary = Path(cfg['repo']) / 'build/windows-mingw64/bin/wesnothd.exe'
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text(Path(__file__).read_text())
        binary.chmod(0o755)
    else:
        raise AssertionError(args)
elif tool == 'wesnothd.exe':
    assert args == ['--version'], args
    print('Wesnoth server 1.19.26 fixture')
else:
    raise AssertionError('Unexpected native tool invocation: ' + tool)
'''


class BuildBootstrapTests(unittest.TestCase):
    helper_source = b''

    @classmethod
    def setUpClass(cls):
        # Never install mock /usr/bin tools in a normal host invocation.
        if not Path('/.dockerenv').exists() or os.environ.get('WESNOTH_BUILD_TEST_CONTAINER') != '1':
            raise RuntimeError('These fixtures must run through the isolated Docker launcher.')
        for name in ('/usr/bin/cygpath', '/usr/bin/pacman', '/mingw64/bin/gcc.exe',
                     '/mingw64/bin/g++.exe', '/mingw64/bin/windres.exe'):
            path = Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(MOCK_TOOL)
            path.chmod(0o755)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='wesnoth-bootstrap-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repo = root / 'Wesnoth Server & Local'
        self.script = self.repo / 'tools/build-windows-server.sh'
        self.script.parent.mkdir(parents=True)
        self.script.write_bytes(self.helper_source)
        self.config = {
            'repo': str(self.repo), 'repo_windows': 'D:/Projects/Wesnoth Server & Local',
            'mingw_windows': 'D:/Tool Kit/msys64/mingw64',
            'cmake': str(root / 'CMake Tool/cmake.exe'),
            'cmake_windows': r'C:\Program Files\CMake\bin\cmake.exe',
            'ninja': str(root / 'Native Ninja Tool/ninja.exe'),
            'ninja_windows': r'D:\Tool Kit\msys64\ucrt64\bin\ninja.exe',
            'configure_exit': 0, 'log': str(root / 'calls.jsonl'),
        }
        self.config_path = root / 'config.json'
        self.cwd = root / 'unrelated working directory'
        self.cwd.mkdir()
        for name in ('cmake', 'ninja'):
            tool = Path(self.config[name])
            tool.parent.mkdir(parents=True)
            tool.write_text(MOCK_TOOL)
            tool.chmod(0o755)
        for name in ('CMakeLists.txt', 'engine/UPSTREAM.json', 'engine/config.h.cmake',
                     'engine/source_lists/libwesnoth_core', 'engine/source_lists/wesnothd',
                     'engine/src/server/wesnothd/server.cpp'):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('nonempty source fixture\n')

    def run_helper(self, path_value):
        self.config_path.write_text(json.dumps(self.config))
        Path(self.config['log']).write_text('')
        env = os.environ.copy()
        for name in ('PATH', 'BASH_ENV', 'ENV', 'SHELLOPTS', 'BASHOPTS', 'MSYS2_ARG_CONV_EXCL'):
            env.pop(name, None)
        if path_value is not None:
            env['PATH'] = path_value
        env['WESNOTH_FIXTURE_CONFIG'] = str(self.config_path)
        result = subprocess.run(
            ['/bin/bash', '--noprofile', '--norc', str(self.script),
             self.config['cmake_windows'], self.config['ninja_windows'], 'Release', '3'],
            cwd=self.cwd, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=20,
        )
        calls = [json.loads(line) for line in Path(self.config['log']).read_text().splitlines()]
        return result, calls

    def assert_successful_build(self, path_value):
        result, calls = self.run_helper(path_value)
        configure = [call for call in calls if call['tool'] == 'cmake.exe' and call['args'][:1] == ['-S']]
        detail = result.stdout + '\nRecorded configure calls: ' + json.dumps(configure)
        self.assertEqual(result.returncode, 0, detail)
        self.assertEqual(len(configure), 1, detail)
        args = configure[0]['args']
        build_windows = self.config['repo_windows'] + '/build/windows-mingw64'
        self.assertEqual(args[:6], ['-S', self.config['repo_windows'], '-B', build_windows, '-G', 'Ninja'])
        self.assertIn('-DCMAKE_CXX_COMPILER=' + self.config['mingw_windows'] + '/bin/g++.exe', args)
        self.assertIn('-DCMAKE_PREFIX_PATH=' + self.config['mingw_windows'], args)
        self.assertIn('-DCMAKE_MAKE_PROGRAM=' + self.config['ninja_windows'].replace('\\', '/'), args)
        self.assertEqual(configure[0]['arg_conversion'], '*')
        self.assertTrue(all(call['msystem'] == 'MINGW64' for call in calls if call['tool'] != 'cygpath'))
        build = [call['args'] for call in calls if call['tool'] == 'cmake.exe' and call['args'][:1] == ['--build']]
        self.assertEqual(build, [['--build', build_windows, '--parallel', '3']])
        self.assertEqual([call['args'] for call in calls if call['tool'] == 'wesnothd.exe'], [['--version']])
        self.assertIn('BUILD COMPLETE: ' + str(self.repo / 'build/windows-mingw64/bin/wesnothd.exe'), result.stdout)

    def test_windows_like_path_without_msys_utilities(self):
        self.assert_successful_build('/c/Windows/System32:/c/Program Files/Git/cmd')

    def test_empty_inherited_path(self):
        self.assert_successful_build('')

    def test_unset_inherited_path(self):
        self.assert_successful_build(None)

    def test_incomplete_source_layout_never_reaches_native_tools(self):
        for name in ('CMakeLists.txt', 'engine/UPSTREAM.json', 'engine/src/server/wesnothd/server.cpp'):
            for condition in ('missing', 'empty'):
                with self.subTest(file=name, condition=condition):
                    path = self.repo / name
                    saved = path.read_bytes()
                    if condition == 'missing':
                        path.unlink()
                    else:
                        path.write_bytes(b'')
                    try:
                        result, calls = self.run_helper('/c/Windows/System32')
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertFalse([call for call in calls if call['tool'] in ('cmake.exe', 'g++.exe', 'ninja.exe')], calls)
                        self.assertNotIn('BUILD COMPLETE', result.stdout)
                    finally:
                        path.write_bytes(saved)

    def test_configure_failure_propagates_without_build_or_success(self):
        self.config['configure_exit'] = 23
        result, calls = self.run_helper('/c/Windows/System32')
        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertEqual(sum(call['tool'] == 'cmake.exe' and call['args'][:1] == ['-S'] for call in calls), 1)
        self.assertFalse([call for call in calls if call['tool'] == 'cmake.exe' and call['args'][:1] == ['--build']], calls)
        self.assertFalse([call for call in calls if call['tool'] == 'wesnothd.exe'], calls)
        self.assertNotIn('BUILD COMPLETE', result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--script', type=Path, default=Path(__file__).resolve().parents[1] / 'tools/build-windows-server.sh')
    parser.add_argument('--image', default='wesnoth-server-verify:1.19.26', help='Already available local Docker image; never pulled.')
    parser.add_argument('--inside-container', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside_container:
        BuildBootstrapTests.helper_source = args.script.read_bytes()
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BuildBootstrapTests))
        return 0 if result.wasSuccessful() else 1
    docker = shutil.which('docker')
    if not docker:
        parser.error('Docker is required; this test does not install it or download an image.')
    helper = args.script.resolve(strict=True)
    command = [docker, 'run', '--rm', '--pull=never', '--network=none', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--user=0:0',
               '--env=WESNOTH_BUILD_TEST_CONTAINER=1',
               '--mount', 'type=bind,source=' + str(Path(__file__).resolve()) + ',target=/input/test.py,readonly',
               '--mount', 'type=bind,source=' + str(helper) + ',target=/input/build-windows-server.sh,readonly',
               '--entrypoint=/usr/bin/python3', args.image, '/input/test.py',
               '--inside-container', '--script=/input/build-windows-server.sh']
    return subprocess.run(command, check=False, timeout=120).returncode


if __name__ == '__main__':
    raise SystemExit(main())
