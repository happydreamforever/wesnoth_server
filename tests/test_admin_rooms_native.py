"""Actual TLS native lobby inventory and close operations, no simulated Rooms."""
import time

from test_individual_native import Individual as Fixture, descendants
from alliance.admin_rooms import AdminRooms
from alliance.auth import hash_password
from alliance.domain import DomainError


class NativeAdminRooms(Fixture):
    def until_inventory(self, predicate, seconds=28):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            state = AdminRooms(self.domain).snapshot()
            if predicate(state):
                return state
            time.sleep(.1)
        self.fail('Native room inventory did not reach the expected state')

    def operator(self):
        actor = self.domain.register('RoomAdmin_' + str(type(self).counter), hash_password('Disposable-admin-password-123'))
        self.db.accounts.update_one({'_id': actor['_id']}, {'$set': {'role': 'admin'}})
        return actor['_id']

    def close_from_inventory(self, operator, room):
        state = self.until_inventory(lambda value: value['available'] and any(row['id'] == room['game'] for row in value['rooms']))
        row = next(row for row in state['rooms'] if row['id'] == room['game'])
        AdminRooms(self.domain).request_close(operator, row['id'], row['revision'], state['generation'], 'Close fixture room')
        room['peer'].sock.settimeout(25)
        self.receive(room['peer'], lambda value: bool(descendants(value, 'leave_game')))
        return self.until_inventory(lambda value: any(row['id'] == room['game'] and row['close_status'] == 'closed' for row in value['closed']))

    def test_waiting_and_running_native_rooms_close_exactly_target_without_rewards(self):
        waiting = self.create_room(gold=175, turns=40, name='Long Room ' + 'A' * 240,
                                   map_name='Castle\n' + '\U0001f3f0' * 300)
        survivor = self.create_room(gold=125, turns=25)
        operator = self.operator()
        state = self.until_inventory(lambda value: len(value['rooms']) == 2)
        record = next(row for row in state['rooms'] if row['id'] == waiting['game'])
        self.assertEqual((record['status'], record['members'], record['capacity'], record['gold'], record['turns']),
                         ('waiting', 1, 2, 175, 40))
        self.assertEqual(record['seats'][0]['account_id'], waiting['actor']['id'])
        self.assertEqual(record['name'], 'Long Room ' + 'A' * 240)
        self.assertEqual(record['map_name'], 'Castle ' + '\U0001f3f0' * 249)
        # A second native publication must cancel an operator's stale consent
        # if the host changed the rules before that command was delivered.
        AdminRooms(self.domain).request_close(operator, record['id'], record['revision'],
                                               state['generation'], 'Original rules reviewed')
        changed = self.finalized_scenario(waiting)
        for side in changed.children:
            if side.name == 'side':
                side.attrs['gold'] = '190'
        self.update_scenario(waiting, changed)
        waiting['context'] = self.context(waiting['peer'], int(waiting['context'].attrs['room_revision']) + 1)
        self.until_inventory(lambda value: any(row['id'] == waiting['game'] and row['close_status'] == 'changed'
                                               and row['gold'] == 190 for row in value['rooms']))
        self.assertIsNotNone(self.snapshot(survivor['peer'], waiting['id']))
        with self.assertRaises(DomainError) as stale:
            AdminRooms(self.domain).request_close(operator, record['id'], record['revision'],
                                                   state['generation'], 'Stale original rules')
        self.assertEqual(stale.exception.code, 'stale_revision')
        state = self.close_from_inventory(operator, waiting)
        self.assertEqual([row['id'] for row in state['rooms']], [survivor['game']])
        self.assertIsNotNone(self.snapshot(survivor['peer'], survivor['id']))
        running, host, guest = self.fully_selected()
        self.assertEqual(self.launch(running, host, guest).attrs['accepted'], 'yes')
        self.until_inventory(lambda value: any(row['id'] == running['game'] and row['status'] == 'playing' for row in value['rooms']))
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': running['game']}), 2)
        state = self.close_from_inventory(operator, running)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': running['game']}), 0)
        self.assertTrue(any(row['id'] == survivor['game'] for row in state['rooms']))
        self.assertIsNotNone(self.snapshot(survivor['peer'], survivor['id']))
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        for actor in (host['actor'], guest['actor']):
            self.assertEqual(self.db.account_heroes.find_one({'account_id': actor['id']})['total_experience'], 20)


for _name in dir(Fixture):
    if _name.startswith('test_') and _name not in NativeAdminRooms.__dict__:
        setattr(NativeAdminRooms, _name, None)
del Fixture
