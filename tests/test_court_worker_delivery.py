"""Court worker release lifecycle with real files and controlled native outputs.

No fixture executable is claimed to be a compiled or executed Windows engine.
"""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import build_world_worker as worker
from tools import inspect_world_worker_ninja as inspection
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_ninja_recovery as ninja
from tools import world_worker_account_recovery as account
from tools import world_worker_version_completion as completion
from tools.build_alliance_bridge import BuildError


def row(path):
    return {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def owner(release):
    return {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': release,
            'inputs': {recovery.BUILDER_INPUT: 'a' * 64, recovery.RECOVERY_INPUT: 'b' * 64,
                       resource.RESOURCE_INPUT: 'c' * 64, ninja.INPUT: 'd' * 64,
                       account.INPUT: 'e' * 64, completion.INPUT: 'f' * 64}}


class ReleaseBindingTests(unittest.TestCase):
    def test_binding_accepts_only_current_and_retained_releases(self):
        for release in (1192624, 1192626):
            recovery._binding(owner(release))
            self.assertTrue(inspection._binding(owner(release)))
        for release in (1192623, 1192625, 1192627, 0, True, '1192626', None):
            with self.subTest(release=release):
                with self.assertRaises(BuildError): recovery._binding(owner(release))
                self.assertFalse(inspection._binding(owner(release)))

    def test_report_pinned_recoveries_cannot_upgrade_or_reinterpret_releases(self):
        for helper in (recovery, resource, ninja, account, completion):
            for old, new in ((1192624, 1192626), (1192626, 1192624), (1192626, 1192626)):
                with self.subTest(helper=helper.__name__, old=old, new=new):
                    with self.assertRaisesRegex(BuildError, 'original 1192624'):
                        helper._legacy(owner(old), owner(new))


class WorkerReleaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Court worker lifecycle ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'build/windows-world-worker'
        self.prefix = self.root / 'build/world-worker-prefix'
        self.prefix.mkdir(parents=True)
        self.msys = self.root / 'MSYS with spaces'
        self.cmake = self.root / 'CMake/bin/cmake.exe'
        self.ninja = self.msys / 'ucrt64/bin/ninja.exe'
        self.library = self.prefix / 'bin/runtime.dll'
        for path, raw in ((self.cmake, b'cmake fixture'), (self.ninja, b'ninja fixture'),
                          (self.library, b'private DLL fixture')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.data = self.root / 'game data'
        self.data.mkdir()
        (self.data / 'scenario.cfg').write_bytes(b'pinned game data fixture')
        self.release = 1192626
        self.configure_calls = 0
        self.compile_calls = 0
        self.fail_compile = False
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (('ROOT', self.root), ('STAGE', self.stage),
                            ('DEPENDENCY_PREFIX', self.prefix), ('REQUIRED', {})):
            self.stack.enter_context(patch.object(worker, name, value))
        self.stack.enter_context(patch.object(worker.sys, 'executable', str(Path(sys.executable).resolve())))
        self.stack.enter_context(patch.object(worker, 'check_host'))
        self.stack.enter_context(patch.object(worker, 'binding', side_effect=lambda: owner(self.release)))
        self.stack.enter_context(patch.object(worker, 'data_inventory', side_effect=self.data_inventory))
        self.stack.enter_context(patch.object(worker, 'compiler_environment', return_value={}))
        self.stack.enter_context(patch.object(worker, 'capture', side_effect=self.capture))
        self.stack.enter_context(patch.object(worker, 'compiler_preflight'))
        self.stack.enter_context(patch.object(worker, 'game_resource_preflight'))
        self.stack.enter_context(patch('tools.world_worker_archive_prefix.verify_locked_prefix'))
        self.stack.enter_context(patch.object(worker, 'prepare_worker_overlay', return_value=({}, 'fixture CMake')))
        self.stack.enter_context(patch.object(worker, 'prepare_source'))
        self.stack.enter_context(patch.object(worker, 'native', side_effect=self.native))
        self.stack.enter_context(patch.object(worker, 'dll_closure', side_effect=self.dll_closure))
        self.stack.enter_context(patch.object(completion, 'probe_version', return_value='1.19.26'))

    def data_inventory(self, directory):
        return {p.relative_to(directory).as_posix(): row(p) for p in sorted(directory.rglob('*')) if p.is_file()}

    def capture(self, arguments, environment):
        if arguments[0] == self.cmake: return 'cmake version 4.3.0\n'
        if arguments[0] == self.ninja: return '1.13.2'
        return 'x86_64-w64-mingw32' if '-dumpmachine' in arguments else '16.2.0'

    def native(self, command, environment):
        engine = self.stage / 'engine'
        if '--build' in command:
            self.compile_calls += 1
            # Simulate one completed object before an interrupted native build.
            (engine / 'retained.obj').write_bytes(b'compiled object fixture')
            if self.fail_compile: raise BuildError('controlled compile interruption')
            (engine / 'world-worker.exe').write_bytes(('MZ worker fixture %s' % self.release).encode())
            return
        self.configure_calls += 1
        self.assertIn('-DCMAKE_SUPPRESS_REGENERATION:BOOL=ON', command)
        self.assertFalse((engine / '.ninja_log').exists())
        self.assertFalse((engine / '.ninja_deps').exists())
        (engine / 'CMakeCache.txt').write_text(
            'CMAKE_SUPPRESS_REGENERATION:BOOL=ON\nCMAKE_USER_MAKE_RULES_OVERRIDE:FILEPATH=' +
            (self.stage / 'worker-resource-rules.cmake').as_posix() + '\n')
        (engine / 'build.ninja').write_bytes(b'build retained.obj: compiler source.cpp\n')

    def dll_closure(self, executable, prefix, output, environment, **kwargs):
        target = output / self.library.name
        if kwargs.get('copy_files', True): target.write_bytes(self.library.read_bytes())
        return {'private': {'runtime.dll': {'filename': 'runtime.dll', **row(target)}},
                'windows_system': ['kernel32.dll']}

    def build(self, preserve=True):
        return worker.build(self.msys, self.cmake, self.data, preserve)

    def test_fresh_current_worker_receipt_then_verified_no_rebuild(self):
        self.build()
        receipt = json.loads((self.stage / 'receipt.json').read_text())
        self.assertEqual(receipt['binding'], owner(1192626))
        self.assertEqual(receipt['version'], '1.19.26')
        before = recovery._inventory(self.stage)
        self.build()
        self.assertEqual(recovery._inventory(self.stage), before)
        self.assertEqual((self.configure_calls, self.compile_calls), (1, 1))
        self.assertFalse(list(self.stage.parent.glob(self.stage.name + '-before-*')))

    def test_current_interrupted_build_resumes_and_retains_ninja_history(self):
        self.fail_compile = True
        with self.assertRaisesRegex(BuildError, 'compile interruption'): self.build()
        self.assertFalse((self.stage / 'receipt.json').exists())
        log = self.stage / 'engine/.ninja_log'
        deps = self.stage / 'engine/.ninja_deps'
        log.write_bytes(b'# ninja log v7\n1\t2\t3\tretained.obj\tabcd\n')
        deps.write_bytes(b'# ninjadeps\ncontrolled original history')
        original = {p.name: ninja._row(p) for p in (log, deps)}
        self.fail_compile = False
        self.build()
        self.assertEqual({p.name: ninja._row(p) for p in (log, deps)}, original)
        self.assertTrue((self.stage / 'receipt.json').exists())
        self.assertEqual((self.configure_calls, self.compile_calls), (2, 2))
        self.assertFalse(list(self.stage.parent.glob(self.stage.name + '-before-*')))

    def test_completed_legacy_worker_verified_and_retained_before_fresh_current_build(self):
        self.release = 1192624
        self.build()
        before = recovery._inventory(self.stage)
        guards = {p.name: recovery._inventory(p) for p in self.stage.parent.glob(self.stage.name + '.ninja-configure-*')}
        self.release = 1192626
        output = io.StringIO()
        with redirect_stdout(output): self.build()
        archives = list(self.stage.parent.glob(self.stage.name + '-before-*'))
        self.assertEqual(len(archives), 1)
        self.assertIn('Completed worker build verified and preserved: ' + str(archives[0]), output.getvalue())
        self.assertEqual(recovery._inventory(archives[0]), before)
        for name, value in guards.items(): self.assertEqual(recovery._inventory(self.stage.parent / name), value)
        self.assertEqual(json.loads((self.stage / 'receipt.json').read_text())['binding']['release'], 1192626)
        self.assertEqual((self.configure_calls, self.compile_calls), (2, 2))
        self.build()
        self.assertEqual(len(list(self.stage.parent.glob(self.stage.name + '-before-*'))), 1)
        self.assertEqual(recovery._inventory(archives[0]), before)

    def test_legacy_retention_requires_preserve_and_rejects_modified_binary(self):
        self.release = 1192624
        self.build()
        self.release = 1192626
        before = recovery._inventory(self.stage)
        with self.assertRaisesRegex(BuildError, 'preserve it'): self.build(preserve=False)
        self.assertEqual(recovery._inventory(self.stage), before)
        executable = self.stage / 'bin/world-worker.exe'
        executable.write_bytes(b'changed completed executable')
        changed = recovery._inventory(self.stage)
        with self.assertRaisesRegex(BuildError, 'executable differs'): self.build()
        self.assertEqual(recovery._inventory(self.stage), changed)
        self.assertFalse(list(self.stage.parent.glob(self.stage.name + '-before-*')))
        self.assertEqual((self.configure_calls, self.compile_calls), (1, 1))

    def test_receipt_cannot_relabel_legacy_owner_or_accept_an_unknown_release(self):
        self.release = 1192624
        self.build()
        path = self.stage / 'receipt.json'
        original = json.loads(path.read_text())
        for release in (1192626, 1192627):
            changed = deepcopy(original)
            changed['binding']['release'] = release
            path.write_text(json.dumps(changed))
            with self.subTest(release=release), self.assertRaises(BuildError):
                worker.installed_worker(expected_binding=changed['binding'])
        self.assertEqual(self.compile_calls, 1)

    def test_current_configure_crash_restores_exact_metadata_before_resume(self):
        self.fail_compile = True
        with self.assertRaises(BuildError): self.build()
        log = self.stage / 'engine/.ninja_log'
        log.write_bytes(b'# ninja log v7\n1\t2\t3\tretained.obj\tabcd\n')
        before = ninja._row(log)
        # Simulate process death after the durable journal and removal, before
        # Python's normal finally restoration. Only this boundary is injected.
        with patch.object(ninja, '_restore_guard', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ninja.configure(self.stage, [self.cmake], {}, lambda *args: None)
        self.assertFalse(log.exists())
        self.assertTrue(ninja.configure_pending(self.stage))
        self.fail_compile = False
        self.build()
        self.assertEqual(ninja._row(log), before)
        self.assertFalse(ninja.configure_pending(self.stage))
        self.assertTrue((self.stage / 'receipt.json').exists())


if __name__ == '__main__': unittest.main()
