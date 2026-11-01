"""Court item authority at the command relay and native evidence boundary.

These are rejection/format tests, not evidence of executed native effects.
"""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import test_world_worker as fixture
from alliance.battle_wire import Node, WireError
from alliance.world_execution import WorldRoom, WorldPeer
from alliance.world_worker import canonical, validate_item_checkpoints


class CourtItemAuthority(unittest.TestCase):
    setUp = fixture.WorkerAuthorityTests.setUp
    tearDown = fixture.WorkerAuthorityTests.tearDown

    def descriptor(self):
        descriptor = deepcopy(self.descriptor)
        descriptor['mode'] = 'court'
        descriptor['settings'] = {'turns': 30, 'items': True}
        descriptor['sides'][0]['item_id'] = 'healing_draught'
        return descriptor

    def test_native_item_missing_tampered_and_generation_bound(self):
        descriptor = CourtItemAuthority.descriptor(self)
        self.assertEqual(validate_item_checkpoints(self.root, descriptor, 'a' * 64), [])
        proof = dict(format=1, run_id=self.run, generation=self.generation,
            scenario_sha256='a' * 64, side=1, turn=3, account_id=self.actor,
            unit_id='h', item_id='healing_draught', applied=True)
        path = self.root / 'item-1.json'
        path.write_bytes(canonical(proof))
        evidence = validate_item_checkpoints(self.root, descriptor, 'a' * 64)
        self.assertEqual((evidence[0]['account_id'], evidence[0]['turn_side']), (self.actor, 1))
        for changed in ({'turn': 0}, {'turn': True}, {'applied': False}, {'side': 2},
                        {'unit_id': 'another unit'}, {'generation': 'other'}, {'extra': 1}):
            path.write_bytes(canonical({**proof, **changed}))
            with self.assertRaises(ValueError):
                validate_item_checkpoints(self.root, descriptor, 'a' * 64)

    def test_only_selected_owner_can_send_one_fixed_item_menu_event(self):
        async def run():
            descriptor = CourtItemAuthority.descriptor(self)
            room = WorldRoom(self.supervisor, descriptor, self.root)
            room.started = True
            room.authorize = AsyncMock()
            peer = WorldPeer(None, None, self.actor, 'x' * 43)
            peer.loaded = True
            peer.sides = [1]
            room.peers[self.actor] = peer
            room.peers['worker'] = SimpleNamespace(loaded=True, send=AsyncMock())
            room.update_availability()
            packet = lambda name: Node(children=[Node('turn', children=[Node('command',
                {'from_side': '1'}, [Node('fire_event', {'raise': name})])])])
            with self.assertRaises(WireError):
                await room.command(peer, packet('debug_arbitrary_event'))
            with self.assertRaises(WireError):
                await room.command(peer, packet('menu item court_item_2'))
            await room.command(peer, packet('menu item court_item_1'))
            self.assertEqual(room.count, 1)
            with self.assertRaises(WireError):
                await room.command(peer, packet('menu item court_item_1'))
            restored = WorldRoom(self.supervisor, descriptor, self.root)
            self.assertEqual(restored.item_commands, {1})
        asyncio.run(run())

    def test_disconnect_between_availability_and_room_lock_retains_packet(self):
        async def run():
            room = WorldRoom(self.supervisor, self.descriptor, self.root)
            room.started = True
            room.authorize = AsyncMock()
            peer = WorldPeer(None, None, self.actor, 'x' * 43)
            peer.loaded, peer.sides = True, [1]
            room.peers[self.actor] = peer
            room.peers['worker'] = SimpleNamespace(loaded=True, send=AsyncMock())
            room.update_availability()
            await room.lock.acquire()
            packet = Node(children=[Node('turn', children=[Node('command', {'from_side': '1'}, [Node('end_turn')])])])
            pending = asyncio.create_task(room.command(peer, packet))
            await asyncio.sleep(.01)
            room.available.clear()
            room.lock.release()
            await asyncio.sleep(.01)
            self.assertFalse(pending.done())
            self.assertEqual(room.count, 0)
            room.update_availability()
            await asyncio.wait_for(pending, 1)
            self.assertEqual(room.count, 1)
        asyncio.run(run())

    def test_cancelled_worker_lease_cannot_append_native_commands(self):
        async def run():
            room = WorldRoom(self.supervisor, self.descriptor, self.root)
            room.started = True
            room.available.set()
            self.daemon.domain.world_worker_lease = lambda *args: {'state': 'cancelled'}
            worker = WorldPeer(None, None, 'worker-scoped', 't' * 43, worker=True)
            worker.loaded, worker.sides = True, [2]
            room.current_side = 2
            packet = Node(children=[Node('turn', children=[Node('command', {'from_side': '2'}, [Node('end_turn')])])])
            with self.assertRaises(WireError):
                await room.command(worker, packet)
            self.assertEqual(room.count, 0)
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
