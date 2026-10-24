"""Real workflow health check against the capability-advertising native server.

Uses the existing disposable MongoDB/account/TLS fixture without rebuilding the
native binary. Windows process launching and Android acceptance are separate.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import unittest

from alliance.battle_wire import parse
from tools import alliance_workflow as workflow
import test_unified_native as base


class WorkflowNative(base.Native):
    def test_production_workflow_accepts_native_individual_capability(self):
        # Native.setUpClass observes setup_fifo(), which load_config() executes
        # before start_server() schedules the actual bind/listen. Unlike the
        # other native cases, this check performs no account RPCs first.
        # Wait only for connection refusal while the owned child is alive;
        # malformed greetings, TLS failures and health refusal are not retried.
        deadline = time.monotonic() + 5
        refused = 0
        while True:
            self.assertIsNone(self.processes[-1].poll(), 'Native child exited before listening')
            try:
                peer = self.peer(15000)
                break
            except ConnectionRefusedError:
                refused += 1
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        greeting = peer.receive()
        fields = parse(greeting).one('version').attrs
        self.assertEqual(fields, {'alliance_protocol': '2',
                                 'implementation_release': '1192617',
                                 'individual_rooms': '1'})
        account_health = workflow.bridge_check(self.profile)
        multiplayer_health = workflow.bridge_check(self.profile, multiplayer=True)
        wrong_pin = dict(self.profile, certificate_sha256='0' * 64)
        wrong_pin_health = workflow.bridge_check(wrong_pin, multiplayer=True)
        binary = Path(os.environ.get('ALLIANCE_TEST_SERVER_BINARY',
                                     base.ROOT / 'build/unified-server-vps/bin/wesnothd'))
        result = {
            'greeting': fields,
            'account_health': account_health,
            'multiplayer_health': multiplayer_health,
            'wrong_pin_rejected': not wrong_pin_health,
            'native_process_still_running': self.processes[-1].poll() is None,
            'listener_startup_refusals': refused,
            'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'workflow_source_sha256': hashlib.sha256(Path(workflow.__file__).read_bytes()).hexdigest(),
            'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': __doc__,
        }
        if directory := os.environ.get('ALLIANCE_WORKFLOW_NATIVE_AUDIT'):
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            with (output / 'observation.json').open('x') as target:
                json.dump(result, target, indent=2)
                target.write('\n')
        self.assertTrue(account_health, result)
        self.assertFalse(wrong_pin_health, result)
        self.assertIsNone(self.processes[-1].poll(), result)
        self.assertTrue(multiplayer_health, result)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([WorkflowNative(
        'test_production_workflow_accepts_native_individual_capability')])
