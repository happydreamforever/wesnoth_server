"""Battle startup keeps full verification ahead of listeners under one lock."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from alliance import battle_daemon as battle


class Progress:
    def __init__(self, events, fail=None):
        self.events, self.fail = events, fail
        self.current_phase = 'preflight'

    def phase(self, name):
        self.current_phase = name
        self.events.append(('phase', name))
        if self.fail == name:
            raise ValueError('fixture publication failure')


class BattleStartup(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = Path(self.temporary.name) / 'runtime'
        self.runtime.mkdir()
        self.identity = Path(self.temporary.name) / 'identity'
        self.events = []
        self.progress = Progress(self.events)
        self.guard = self.runtime / 'battles' / 'daemon.lock'
        self.worker = {'executable': Path('/fixture/worker'), 'game_data': Path('/fixture/data')}
        events = self.events

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                events.append(('database', 'closed'))

            def get_default_database(self):
                return SimpleNamespace(command=lambda command: events.append(('database', command)))

        class Daemon:
            def __init__(self, db, storage, context):
                self.storage = storage
                storage.mkdir(exist_ok=True)
                self.world = None

            async def handle(self, *args):
                raise AssertionError('No network connection belongs in this fixture')

            async def settle_ready(self):
                await asyncio.Future()

        class Supervisor:
            def __init__(self, daemon, identity, *, executable, game_data, workers):
                self.executable = executable
                self.limit = workers
                events.append(('supervisor', executable, game_data, workers))

            async def serve(self):
                await asyncio.Future()

            async def close(self):
                events.append(('supervisor', 'closed'))

        class Server:
            async def __aenter__(self):
                events.append(('server', 'entered'))
                return self

            async def __aexit__(self, *args):
                events.append(('server', 'closed'))

            async def serve_forever(self):
                events.append(('server', 'serving'))
                await asyncio.sleep(0)

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(battle, 'owned_runtime', side_effect=lambda path: path))
        self.stack.enter_context(patch.object(battle.Settings, 'load', return_value=SimpleNamespace(mongo_uri='fixture')))
        self.stack.enter_context(patch.object(battle, 'tls_context', return_value=(object(), '127.0.0.1')))
        self.stack.enter_context(patch.object(battle, 'MongoClient', return_value=Client()))
        self.stack.enter_context(patch.object(battle, 'BattleDaemon', Daemon))
        self.stack.enter_context(patch('alliance.world_worker.WorldWorkerSupervisor', Supervisor))
        self.verify = self.stack.enter_context(patch('tools.build_world_worker.installed_worker', side_effect=self.full_verify))

        async def listen(*args, **kwargs):
            events.append(('listener', args[1], args[2], kwargs))
            return Server()

        self.listen = self.stack.enter_context(patch.object(battle.asyncio, 'start_server', side_effect=listen))

    def full_verify(self, *, required):
        self.assertFalse(required)
        # A second descriptor must already be excluded before scanning inputs.
        with self.assertRaises(OSError):
            with battle.process_lock(self.guard):
                self.fail('Another startup obtained the daemon lock during verification')
        self.events.append(('verify', 'full'))
        return self.worker

    def run_fixture(self):
        with redirect_stdout(io.StringIO()):
            asyncio.run(battle.run(self.runtime, self.identity, 2, progress=self.progress))

    def assert_guard_released(self):
        with battle.process_lock(self.guard):
            pass

    def test_full_verification_once_under_lock_before_listener_and_health(self):
        self.run_fixture()
        self.verify.assert_called_once_with(required=False)
        self.assertEqual([event[1] for event in self.events if event[0] == 'phase'],
                         ['runtime', 'worker_verification', 'listener', 'serving'])
        self.assertLess(self.events.index(('verify', 'full')), next(i for i, row in enumerate(self.events) if row[0] == 'listener'))
        self.listen.assert_awaited_once()
        self.assertIn(('supervisor', self.worker['executable'], self.worker['game_data'], 2), self.events)
        self.assertIn(('server', 'closed'), self.events)
        self.assertIn(('supervisor', 'closed'), self.events)
        self.assert_guard_released()

    def test_failed_verification_never_binds_or_reports_serving_and_releases_lock(self):
        self.verify.side_effect = ValueError('fixture artifact rejected')
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.listen.assert_not_called()
        self.assertEqual(self.progress.current_phase, 'worker_verification')
        self.assertNotIn(('phase', 'serving'), self.events)
        self.assert_guard_released()

    def test_existing_daemon_lock_prevents_a_second_verification(self):
        self.guard.parent.mkdir()
        with battle.process_lock(self.guard):
            with self.assertRaises(OSError):
                self.run_fixture()
        self.verify.assert_not_called()
        self.listen.assert_not_called()
        self.assertEqual(self.progress.current_phase, 'runtime')
        self.assert_guard_released()

    def test_progress_publication_failure_after_bind_closes_listener(self):
        self.progress.fail = 'serving'
        with self.assertRaises(ValueError):
            self.run_fixture()
        self.assertIn(('server', 'closed'), self.events)
        self.assertIn(('supervisor', 'closed'), self.events)
        self.assertNotIn(('server', 'serving'), self.events)
        self.assert_guard_released()

    def test_absent_optional_worker_does_not_skip_existing_verification_call(self):
        self.worker = None
        self.run_fixture()
        self.verify.assert_called_once_with(required=False)
        self.assertIn(('supervisor', None, None, 2), self.events)

    def test_cli_passes_paired_progress_arguments_to_single_publisher(self):
        marker = Path(self.temporary.name) / 'progress.jsonl'
        with patch.object(battle, 'StartupProgress', return_value=self.progress) as publisher, \
                patch.object(battle, 'run', new_callable=AsyncMock) as runner:
            self.assertEqual(battle.main(['--runtime', str(self.runtime), '--identity', str(self.identity),
                                         '--workers', '2', '--startup-progress', str(marker),
                                         '--startup-launch-id', 'a' * 32]), 0)
        publisher.assert_called_once_with(marker, 'a' * 32)
        runner.assert_awaited_once_with(self.runtime, self.identity, 2, progress=self.progress)

    def test_cli_failure_prints_phase_and_exception_type_only(self):
        self.progress.current_phase = 'worker_verification'
        with patch.object(battle, 'StartupProgress', return_value=self.progress), \
                patch.object(battle, 'run', new_callable=AsyncMock, side_effect=ValueError('private fixture detail')), \
                redirect_stderr(io.StringIO()) as output:
            self.assertEqual(battle.main(['--runtime', str(self.runtime), '--identity', str(self.identity)]), 1)
        self.assertIn('ValueError; phase=worker_verification', output.getvalue())
        self.assertNotIn('private fixture detail', output.getvalue())

    def test_windows_wrapper_forwards_pair_as_arguments_without_evaluation(self):
        text = (Path(__file__).resolve().parents[1] / 'tools/Run-WindowsAllianceBattles.ps1').read_text()
        self.assertIn("$PSBoundParameters.ContainsKey('StartupProgressPath')", text)
        self.assertIn("$PSBoundParameters.ContainsKey('StartupLaunchId')", text)
        self.assertIn('$hasStartupPath -ne $hasStartupId', text)
        self.assertIn("@('--startup-progress', $StartupProgressPath, '--startup-launch-id', $StartupLaunchId)", text)
        self.assertIn('& $python @arguments | Out-Host', text)
        self.assertNotIn('Invoke-Expression', text)


if __name__ == '__main__':
    unittest.main()
