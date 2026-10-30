"""Native Room inventory/closure uses real Mongo transactions, not game edits."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from test_alliance_web import AllianceWebTests as Fixture
from alliance.admin_rooms import AdminRooms, KEY, LEASE_SECONDS
from alliance.domain import DomainError, _now


class AdminRoomTests(Fixture):
    def setUp(self):
        super().setUp()
        self.db.schema_metadata.delete_one({'_id': KEY})
        self.rooms = AdminRooms(self.domain)
        self.generation = str(uuid4())
        self.room = {'id': str(uuid4()), 'native_id': 1, 'revision': 1,
                     'name': 'Native test room', 'map_id': 'test', 'map_name': 'Test map',
                     'status': 'waiting', 'capacity': 2, 'members': 1, 'ready': 0,
                     'gold': 100, 'base_income': 2, 'turns': -1, 'fog': True,
                     'shroud': False, 'observers': True,
                     'seats': [{'side': 1, 'account_id': self.player['_id'],
                                'username': 'PlayerOne', 'ready': False, 'unit_type': ''},
                               {'side': 2, 'account_id': '', 'username': '', 'ready': False, 'unit_type': ''}]}

    def publish(self, rows=None, *, generation=None, register=False):
        return self.rooms.publish({'generation': generation or self.generation,
                                  'register': register, 'rooms': [self.room] if rows is None else rows})

    def error(self, code, fn):
        with self.assertRaises(DomainError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def close(self, room=None, revision=None):
        room = room or self.room
        detail = self.rooms.detail(room['id'])
        return self.rooms.request_close(self.admin['_id'], room['id'],
             detail['revision'] if revision is None else revision, self.generation, 'Operator closed abandoned room')

    def test_native_snapshot_closure_acknowledgement_and_other_room_preserved(self):
        other = deepcopy(self.room)
        other.update(id=str(uuid4()), native_id=2, name='Keep this room')
        self.publish([self.room, other], register=True)
        before = {name: list(self.db[name].find({})) for name in
                  ('accounts', 'account_heroes', 'game_runs', 'network_battle_reservations', 'settlements')}
        reply = self.close()
        self.assertEqual(reply['state'], 'pending')
        self.assertEqual(self.rooms.detail(self.room['id'])['close_status'], 'pending')
        self.assertEqual(self.publish([self.room, other])['close'], [self.room['id']])
        # Until native acknowledgement, no account/game/reservation is mutated.
        for name, rows in before.items():
            current = list(self.db[name].find({}))
            if name == 'accounts':
                for row in current:
                    if row['_id'] == self.admin['_id']:
                        row['revision'] -= 1
            self.assertEqual(current, rows)
        self.publish([other])
        detail = self.rooms.detail(self.room['id'])
        self.assertEqual((detail['status'], detail['close_status'], detail['available']), ('closed', 'closed', False))
        self.assertEqual(self.rooms.detail(other['id'])['status'], 'waiting')
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'request_room_close'}), 1)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'room_close_acknowledged'}), 1)
        self.publish([other])
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'room_close_acknowledged'}), 1)

    def test_room_changes_invalidate_pending_close_and_stale_form(self):
        self.publish(register=True)
        original = self.rooms.detail(self.room['id'])['revision']
        self.close()
        self.room.update(status='playing')
        self.assertEqual(self.publish()['close'], [])
        changed = self.rooms.detail(self.room['id'])
        self.assertGreater(changed['revision'], original)
        self.assertEqual(changed['close_status'], 'changed')
        self.error('stale_revision', lambda: self.close(revision=original))
        self.close(revision=changed['revision'])
        self.assertEqual(self.publish()['close'], [self.room['id']])

    def test_generation_takeover_requires_expiry_and_rejects_prior_instance(self):
        self.publish(register=True)
        next_generation = str(uuid4())
        self.error('stale_generation', lambda: self.publish(generation=next_generation, register=True))
        self.db.schema_metadata.update_one({'_id': KEY}, {'$set': {'expires_at': _now() - timedelta(seconds=1)}})
        self.assertFalse(self.rooms.snapshot()['available'])
        self.error('stale_generation', self.close)
        self.publish([], generation=next_generation, register=True)
        self.error('stale_generation', lambda: self.publish(register=False))
        self.assertEqual(self.rooms.snapshot()['generation'], next_generation)
        self.assertEqual(self.rooms.snapshot()['rooms'], [])

    def test_same_snapshot_preserves_revision_and_duplicate_close_is_idempotent(self):
        self.publish(register=True)
        original = self.rooms.detail(self.room['id'])['revision']
        self.publish()
        self.assertEqual(self.rooms.detail(self.room['id'])['revision'], original)
        self.close()
        self.close()
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'request_room_close'}), 1)
        self.assertEqual(self.rooms.detail(self.room['id'])['revision'], original)

    def test_auth_rejected_and_secrets_never_exposed(self):
        self.publish(register=True)
        self.error('forbidden', lambda: self.rooms.request_close(self.player['_id'], self.room['id'],
                   1, self.generation, 'Unauthorized attempt'))
        self.assertNotIn('fingerprint', self.rooms.detail(self.room['id']))
        self.assertNotIn('password', str(self.rooms.snapshot()))
        self.assertEqual(self.db.admin_audit.count_documents({}), 0)

    def test_inventory_bounded_and_unknown_fields_rejected(self):
        self.error('invalid_input', lambda: self.publish([self.room] * 257, register=True))
        self.error('invalid_input', lambda: self.publish([self.room, self.room], register=True))
        for key, value in [('gold', True), ('turns', 0), ('capacity', 9), ('name', '<valid>\nno')]:
            row = deepcopy(self.room)
            row[key] = value
            self.error('invalid_input', lambda: self.publish([row], register=True))
        row = {**self.room, 'password': 'must never be reflected'}
        self.error('invalid_input', lambda: self.publish([row], register=True))
        self.assertIsNone(self.db.schema_metadata.find_one({'_id': KEY}))

    def test_running_disconnect_retains_frozen_ready_inventory(self):
        self.room.update(status='playing', members=1, ready=2)
        self.publish(register=True)
        row = self.rooms.detail(self.room['id'])
        self.assertEqual((row['members'], row['ready']), (1, 2))

    def test_maximum_unicode_inventory_fits_native_request_bound(self):
        import json
        rows = []
        for index in range(256):
            row = deepcopy(self.room)
            row.update(id=str(uuid4()), native_id=index + 1, name='\U0001f3f0' * 256,
                       map_id='\U0001f3f0' * 128, map_name='\U0001f3f0' * 256,
                       capacity=8, members=8, ready=0)
            row['seats'] = [{'side': side, 'account_id': str(uuid4()),
                            'username': '\U0001f3f0' * 64, 'unit_type': '\U0001f3f0' * 128,
                            'ready': False} for side in range(1, 9)]
            rows.append(row)
        payload = {'generation': self.generation, 'register': True, 'rooms': rows}
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.assertGreater(len(raw), 256 * 1024)
        self.assertLess(len(raw), 4 * 1024 * 1024)
        response = self.client.post('/internal/v1/casual/admin_rooms', headers={**self.bridge, 'Content-Type': 'application/json'}, data=raw)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(len(self.rooms.snapshot()['rooms']), 256)
        bad = deepcopy(self.room)
        bad['name'] = '\ud800'
        self.error('invalid_input', lambda: self.publish([bad]))

    def test_internal_route_is_service_only_and_browser_close_requires_csrf(self):
        request = {'generation': self.generation, 'register': True, 'rooms': [self.room]}
        route = '/internal/v1/casual/admin_rooms'
        self.assertEqual(self.client.post(route, json=request).status_code, 401)
        self.assertEqual(self.client.post(route, headers={**self.bridge, 'Origin': 'http://127.0.0.1:18765'}, json=request).status_code, 403)
        response = self.client.post(route, headers=self.bridge, json=request)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(self.client.get('/rooms').status_code, 302)
        self.login_admin()
        detail = self.rooms.detail(self.room['id'])
        form = {'generation': self.generation, 'revision': detail['revision'], 'reason': 'Close abandoned room'}
        self.assertEqual(self.client.post('/rooms/' + self.room['id'] + '/close', data=form).status_code, 400)


for _name in dir(Fixture):
    if _name.startswith('test_') and _name not in AdminRoomTests.__dict__:
        setattr(AdminRoomTests, _name, None)
del Fixture
