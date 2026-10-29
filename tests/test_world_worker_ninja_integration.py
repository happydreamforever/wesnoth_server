"""Builder boundaries for guarded World worker configuration."""
from contextlib import contextmanager
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import build_world_worker as worker
from tools.build_alliance_bridge import BuildError


class NinjaBuilderIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name) / 'build/windows-world-worker'
        (self.stage / 'engine').mkdir(parents=True)
        self.cache = self.stage / 'engine/CMakeCache.txt'
        self.graph = self.stage / 'engine/build.ninja'
        self.cache.write_text('CMAKE_SUPPRESS_REGENERATION:BOOL=ON\n')
        self.graph.write_text('build engine.obj: CXX_COMPILER source.cpp\n')
        # Configured stages retain ownership even while a configure guard holds
        # their Ninja metadata. This fixture represents an earlier build, not
        # the reviewed linked stage that now requires version finalization.
        (self.stage / 'owner.json').write_text(json.dumps({
            'format': 1, 'purpose': 'wesnoth-full-native-world-worker', 'release': 1192624,
            'inputs': {'wesnoth_server/tools/build_world_worker.py': 'd' * 64},
        }) + '\n')

    def test_explicit_configure_has_no_automatic_regeneration(self):
        worker.verify_ninja_configuration(self.stage)

    def test_missing_duplicate_off_or_untyped_suppression_is_rejected(self):
        for value in ('', 'CMAKE_SUPPRESS_REGENERATION:BOOL=OFF\n',
                'CMAKE_SUPPRESS_REGENERATION:UNINITIALIZED=ON\n',
                'CMAKE_SUPPRESS_REGENERATION:BOOL=ON\n' * 2):
            with self.subTest(value=value):
                self.cache.write_text(value)
                with self.assertRaises(BuildError):
                    worker.verify_ninja_configuration(self.stage)

    def test_generated_regeneration_edge_is_rejected(self):
        self.graph.write_text('build build.ninja: RERUN_CMAKE | CMakeLists.txt\n')
        with self.assertRaises(BuildError):
            worker.verify_ninja_configuration(self.stage)

    def test_interrupted_guard_is_restored_under_lock_before_build(self):
        from tools import world_worker_ninja_recovery as ninja
        order = []
        @contextmanager
        def lock(stage):
            self.assertEqual(stage, self.stage)
            order.append('lock')
            try: yield
            finally: order.append('unlock')
        with patch.object(worker, 'STAGE', self.stage), patch.object(worker, 'check_host'), \
             patch.object(ninja, 'build_lock', side_effect=lock), \
             patch.object(ninja, 'resume_configure', side_effect=lambda stage: order.append('restore')), \
             patch.object(worker, 'build_locked', side_effect=lambda *args: order.append('build')):
            worker.build('msys', 'cmake', 'data', True, Path('report.json'))
        self.assertEqual(order, ['lock', 'restore', 'build', 'unlock'])

    def test_recovery_requires_preserve_before_mutating_anything(self):
        from tools import world_worker_ninja_recovery as ninja
        with patch.object(worker, 'check_host'), patch.object(ninja, 'build_lock') as lock:
            with self.assertRaisesRegex(BuildError, 'requires -PreservePreviousBuild'):
                worker.build('msys', 'cmake', 'data', False, Path('report.json'))
        lock.assert_not_called()

    def test_restoration_failure_prevents_configure_or_native_build(self):
        from tools import world_worker_ninja_recovery as ninja
        @contextmanager
        def lock(stage): yield
        with patch.object(worker, 'STAGE', self.stage), patch.object(worker, 'check_host'), \
             patch.object(ninja, 'build_lock', side_effect=lock), \
             patch.object(ninja, 'resume_configure', side_effect=BuildError('retained backup differs')), \
             patch.object(worker, 'build_locked') as build:
            with self.assertRaisesRegex(BuildError, 'retained backup differs'):
                worker.build('msys', 'cmake', 'data', True)
        build.assert_not_called()

    def test_cli_passes_report_as_path(self):
        with patch.object(worker.sys, 'argv', ['build_world_worker.py', '--preserve-previous',
                '--ninja-report', 'with spaces.json']), patch.object(worker, 'build') as build:
            self.assertEqual(worker.main(), 0)
        self.assertIs(build.call_args.args[3], True)
        self.assertEqual(build.call_args.args[4], Path('with spaces.json'))

    def test_cli_refuses_other_operations_with_recovery(self):
        for operation in (['--verify'], ['--audit', 'report.json'], ['--prepare-dependencies']):
            with self.subTest(operation=operation), patch.object(worker.sys, 'argv',
                    ['build_world_worker.py', '--ninja-report', 'report.json', *operation]), \
                 patch.object(worker, 'build') as build, redirect_stdout(io.StringIO()):
                self.assertEqual(worker.main(), 1)
                build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
