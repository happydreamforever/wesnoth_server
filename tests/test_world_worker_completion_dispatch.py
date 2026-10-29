"""Builder completion routing and read-only verification with controlled native tools."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import build_world_worker as worker
from tools import world_worker_ninja_recovery as ninja
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_account_recovery as account
from tools import world_worker_version_completion as completion
from tools.build_alliance_bridge import BuildError


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CompletionDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker completion dispatch ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'build/windows-world-worker'
        self.stage.mkdir(parents=True)
        self.owner = {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
                      'inputs': {recovery.BUILDER_INPUT: next(iter(completion.LEGACY_BUILDERS))}}
        (self.stage / 'owner.json').write_text(json.dumps(self.owner))
        (self.stage / 'retained.obj').write_bytes(b'previous successful compilation')
        self.before = recovery._inventory(self.stage)
        self.report = self.root / "accepted $ & ' report.json"
        self.report.write_bytes(b'controlled report boundary')

    def dispatch(self, *, preserve=True, report=True, pending=False, ninja_report=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(worker, 'STAGE', self.stage))
            stack.enter_context(patch.object(worker, 'check_host'))
            stack.enter_context(patch.object(completion, 'pending', return_value=pending))
            finish = stack.enter_context(patch.object(worker, 'finish_linked_worker', return_value='completed'))
            restore = stack.enter_context(patch.object(ninja, 'resume_configure', side_effect=AssertionError('no metadata restoration')))
            build = stack.enter_context(patch.object(worker, 'build_locked', side_effect=AssertionError('no configuration/build')))
            result = worker.build('msys', 'cmake', 'data', preserve, ninja_report,
                                  self.report if report else None)
            restore.assert_not_called()
            build.assert_not_called()
        self.assertEqual(recovery._inventory(self.stage), self.before)
        return result, finish

    def test_explicit_report_dispatches_before_any_configuration_or_build(self):
        result, finish = self.dispatch()
        self.assertEqual(result, 'completed')
        finish.assert_called_once_with('msys', 'cmake', 'data', self.report)

    def test_pending_completion_resumes_without_resupplying_report(self):
        result, finish = self.dispatch(report=False, pending=True)
        self.assertEqual(result, 'completed')
        finish.assert_called_once_with('msys', 'cmake', 'data', None)

    def test_report_and_pending_completion_require_preservation(self):
        for kwargs in ({'preserve': False}, {'preserve': False, 'report': False, 'pending': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(BuildError): self.dispatch(**kwargs)
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_version_and_old_ninja_report_are_rejected_before_mutation(self):
        with self.assertRaises(BuildError): self.dispatch(ninja_report=self.report)
        with self.assertRaises(BuildError): self.dispatch(report=False, pending=True, ninja_report=self.report)
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_known_linked_stage_requires_accepted_report_before_old_recovery(self):
        with self.assertRaisesRegex(BuildError, 'VersionReportPath'): self.dispatch(report=False)
        self.assertEqual(recovery._inventory(self.stage), self.before)

    def test_fresh_stage_still_uses_normal_build_path(self):
        fresh = self.root / 'fresh/windows-world-worker'
        with patch.object(worker, 'STAGE', fresh), patch.object(worker, 'check_host'), \
                patch.object(completion, 'pending', return_value=False), \
                patch.object(ninja, 'resume_configure') as restore, \
                patch.object(worker, 'build_locked', return_value='fresh') as build, \
                patch.object(worker, 'finish_linked_worker', side_effect=AssertionError('not completion')):
            self.assertEqual(worker.build('msys', 'cmake', 'data', False), 'fresh')
            restore.assert_called_once_with(fresh)
            build.assert_called_once_with('msys', 'cmake', 'data', False, None)


class CompletionValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker completion verification ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'build/windows-world-worker'
        self.prefix = self.root / 'build/world-worker-prefix'
        self.data = self.root / 'game data'
        self.msys = self.root / 'msys'
        self.cmake = self.root / 'Program Files/CMake/bin/cmake.exe'
        self.ninja = self.msys / 'ucrt64/bin/ninja.exe'
        self.exe = self.stage / 'bin/world-worker.exe'
        for path, raw in ((self.cmake, b'cmake'), (self.ninja, b'ninja'), (self.exe, b'worker')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.prefix.mkdir()
        self.data.mkdir()
        self.environment = {'SYSTEMROOT': str(self.root / 'Windows')}
        self.expected = {'format': 1, 'purpose': recovery.BINDING_PURPOSE, 'release': 1192624,
                         'inputs': {completion.INPUT: 'a' * 64, recovery.BUILDER_INPUT: 'b' * 64}}
        self.inventory = {'data/_main.cfg': {'bytes': 4, 'sha256': 'd' * 64}}
        self.closure = {'private': {}, 'windows_system': ['kernel32.dll']}
        self.report = self.root / 'report.json'

    def validate(self, *, binding_values=None, data_values=None, probe_effect=None):
        receipts = []
        with ExitStack() as stack:
            def mocked(name, **kw): return stack.enter_context(patch.object(worker, name, **kw))
            mocked('STAGE', new=self.stage)
            mocked('DEPENDENCY_PREFIX', new=self.prefix)
            binding = mocked('binding', side_effect=binding_values or [self.expected, self.expected])
            data = mocked('data_inventory', side_effect=data_values or [self.inventory, self.inventory])
            mocked('compiler_environment', return_value=self.environment)
            mocked('capture', side_effect=['cmake version 4.3.0', '1.13.2'])
            prefix = stack.enter_context(patch('tools.world_worker_archive_prefix.verify_locked_prefix'))
            overlay = mocked('prepare_worker_overlay')
            rules = mocked('verify_resource_rule')
            regeneration = mocked('verify_ninja_configuration')
            closure = mocked('dll_closure', return_value=self.closure)
            probe = stack.enter_context(patch.object(completion, 'probe_version',
                side_effect=probe_effect, return_value='1.19.26'))
            installed = mocked('installed_worker')
            mocked('native', side_effect=AssertionError('must not compile'))
            mocked('compiler_preflight', side_effect=AssertionError('must not run compiler preflight'))
            mocked('game_resource_preflight', side_effect=AssertionError('must not compile resource'))
            stack.enter_context(patch.object(ninja, 'configure', side_effect=AssertionError('must not configure')))
            def finish(stage, expected, report, callback):
                self.assertEqual((stage, expected, report), (self.stage, self.expected, self.report))
                receipts.append(callback())
            stack.enter_context(patch.object(completion, 'finalize_reviewed', side_effect=finish))
            before = recovery._inventory(self.stage)
            worker.finish_linked_worker(self.msys, self.cmake, self.data, self.report)
            self.assertEqual(recovery._inventory(self.stage), before)
            prefix.assert_called_once_with()
            overlay.assert_called_once_with(validate_existing=True)
            rules.assert_called_once_with(self.stage)
            regeneration.assert_called_once_with(self.stage)
            closure.assert_called_once_with(self.exe, self.prefix, self.stage / 'bin', self.environment, copy_files=False)
            probe.assert_called_once_with(self.exe, self.environment, self.stage.parent)
            installed.assert_called_once_with()
            self.assertEqual(binding.call_count, 2)
            self.assertEqual(data.call_count, 2)
        return receipts[0]

    def test_completion_verifies_existing_artifacts_without_compilation_or_copy(self):
        receipt = self.validate()
        self.assertEqual(set(receipt), {'binding', 'executable', 'dlls', 'version', 'game_data', 'game_data_files', 'build_tools'})
        self.assertEqual(receipt['version'], '1.19.26')
        self.assertEqual(receipt['binding'], self.expected)
        self.assertEqual(receipt['executable'], {'sha256': digest(self.exe), 'bytes': 6})
        self.assertEqual(receipt['dlls'], self.closure)
        self.assertEqual(receipt['game_data_files'], self.inventory)
        self.assertEqual(receipt['build_tools']['ninja']['sha256'], digest(self.ninja))

    def test_changed_source_or_data_cannot_publish_a_receipt(self):
        changed = deepcopy(self.expected)
        changed['inputs'][completion.INPUT] = 'c' * 64
        with self.assertRaisesRegex(BuildError, 'inputs changed'):
            self.validate(binding_values=[self.expected, changed])
        with self.assertRaisesRegex(BuildError, 'inputs changed'):
            self.validate(data_values=[self.inventory, {}])

    def test_changed_build_tool_cannot_publish_a_receipt(self):
        def change_tool(*args):
            self.ninja.write_bytes(b'changed native tool')
            return '1.19.26'
        with self.assertRaisesRegex(BuildError, 'tools changed'):
            self.validate(probe_effect=change_tool)

    def test_probe_failure_prevents_completion_and_acceptance(self):
        with self.assertRaisesRegex(BuildError, 'probe rejected'):
            self.validate(probe_effect=BuildError('probe rejected'))

    def normal_build(self, probe_effect=None):
        (self.stage / 'owner.json').write_text(json.dumps(self.expected))
        linked = self.stage / 'engine/world-worker.exe'
        linked.parent.mkdir()
        linked.write_bytes(b'fresh linked executable')
        with ExitStack() as stack:
            def mocked(name, **kw): return stack.enter_context(patch.object(worker, name, **kw))
            stack.enter_context(patch.object(worker.sys, 'executable', str(Path(sys.executable).resolve())))
            mocked('STAGE', new=self.stage)
            mocked('ROOT', new=self.root)
            mocked('DEPENDENCY_PREFIX', new=self.prefix)
            mocked('REQUIRED', new={})
            mocked('binding', return_value=self.expected)
            mocked('data_inventory', return_value=self.inventory)
            mocked('compiler_environment', return_value=self.environment)
            mocked('capture', side_effect=['cmake version 4.3.0', '1.13.2', 'x86_64-w64-mingw32', '16.2.0'])
            mocked('compiler_preflight')
            mocked('game_resource_preflight')
            mocked('prepare_toolchain', return_value=self.stage / 'worker-toolchain.cmake')
            mocked('prepare_resource_rules', return_value=self.stage / 'worker-resource-rules.cmake')
            mocked('prepare_worker_overlay', return_value=({}, 'controlled CMake text'))
            mocked('prepare_source')
            mocked('verify_resource_rule')
            mocked('verify_ninja_configuration')
            mocked('dll_closure', return_value=self.closure)
            installed = mocked('installed_worker')
            native = mocked('native')
            stack.enter_context(patch('tools.world_worker_archive_prefix.verify_locked_prefix'))
            stack.enter_context(patch.object(account, 'account_recovery_pending', return_value=False))
            stack.enter_context(patch.object(resource, 'resource_recovery_pending', return_value=False))
            stack.enter_context(patch.object(recovery, 'recovery_pending', return_value=False))
            stack.enter_context(patch.object(ninja, 'pending', return_value=False))
            stack.enter_context(patch.object(ninja, 'configure'))
            probe = stack.enter_context(patch.object(completion, 'probe_version',
                return_value='1.19.26', side_effect=probe_effect))
            worker.build_locked(self.msys, self.cmake, self.data, True)
            probe.assert_called_once_with(self.exe, self.environment, self.stage.parent)
            self.assertEqual(native.call_count, 1)
            installed.assert_called_once_with()
        return json.loads((self.stage / 'receipt.json').read_text())

    def test_normal_build_also_uses_strict_isolated_version_probe(self):
        receipt = self.normal_build()
        self.assertEqual(receipt['version'], '1.19.26')
        self.assertEqual(receipt['executable']['sha256'], digest(self.exe))

    def test_normal_build_probe_failure_does_not_write_a_receipt(self):
        with self.assertRaisesRegex(BuildError, 'exact version required'):
            self.normal_build(BuildError('exact version required'))
        self.assertFalse((self.stage / 'receipt.json').exists())


class ReadOnlyDllClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='worker closure ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'prefix'
        self.output = self.root / 'bin'
        (self.prefix / 'bin').mkdir(parents=True)
        self.output.mkdir()
        self.exe = self.output / 'world-worker.exe'
        self.exe.write_bytes(b'linked worker')
        for name in ('A.dll', 'b.dll'):
            (self.prefix / 'bin' / name).write_bytes(name.encode())
            (self.output / name).write_bytes(name.encode())
        self.imports = {'world-worker.exe': 'DLL Name: A.dll\nDLL Name: KERNEL32.dll\n',
                        'A.dll': 'DLL Name: b.dll\n', 'b.dll': 'DLL Name: A.dll\n'}

    def closure(self):
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
                  for path in self.output.iterdir()}
        try:
            with patch.object(worker, 'capture', side_effect=lambda cmd, env: self.imports[Path(cmd[-1]).name]), \
                    patch.object(worker.shutil, 'copy2', side_effect=AssertionError('read-only closure must not recopy DLLs')):
                result = worker.dll_closure(self.exe, self.prefix, self.output, {}, copy_files=False)
        finally:
            self.assertEqual(before, {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
                                     for path in self.output.iterdir()})
        return result

    def test_recursive_closure_validates_without_recopying(self):
        closure = self.closure()
        self.assertEqual(set(closure['private']), {'a.dll', 'b.dll'})
        self.assertEqual(closure['windows_system'], ['kernel32.dll'])
        self.assertEqual(closure['private']['a.dll']['filename'], 'A.dll')

    def test_changed_or_missing_dll_is_refused_without_repair(self):
        target = self.output / 'b.dll'
        target.write_bytes(b'changed DLL')
        with self.assertRaises(BuildError): self.closure()
        self.assertEqual(target.read_bytes(), b'changed DLL')
        target.unlink()
        with self.assertRaises(FileNotFoundError): self.closure()
        self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main()
