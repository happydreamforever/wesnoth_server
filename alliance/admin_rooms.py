"""Bounded native Room inventory and acknowledged operator closure requests.

The native lobby owns Rooms. This registry never creates a room, releases a
player reservation or awards rewards. The lobby acknowledges closure by removing
the requested room through its normal disconnect path and publishing again.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from uuid import UUID

from .domain import DomainError, _now, _reason

KEY = 'admin-native-rooms-v1'
LEASE_SECONDS = 35
MAX_ROOMS = 256
ROOM_KEYS = {'id', 'native_id', 'revision', 'name', 'map_id', 'map_name', 'status',
             'capacity', 'members', 'ready', 'gold', 'base_income', 'turns', 'fog',
             'shroud', 'observers', 'seats'}
SEAT_KEYS = {'side', 'account_id', 'username', 'ready', 'unit_type'}


def _error(code, message):
    raise DomainError(code, message)


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        _error('invalid_input', 'A valid room or lobby identifier is required.')
    return value


def _text(value, maximum, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or
            (not empty and not value) or any(ord(c) < 32 or ord(c) == 127 or
                                           0xD800 <= ord(c) <= 0xDFFF for c in value)):
        _error('invalid_input', 'Invalid native room text.')
    return value


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _error('invalid_input', 'Invalid native room number.')
    return value


def _digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class AdminRooms:
    def __init__(self, domain):
        self.domain = domain
        self.db = domain.db

    def _valid_room(self, row):
        if not isinstance(row, dict) or set(row) != ROOM_KEYS:
            _error('invalid_input', 'Invalid native room inventory.')
        _uuid(row['id'])
        _int(row['native_id'], 1, 2**31 - 1)
        _int(row['revision'], 1, 2**63 - 1)
        for key, limit in (('name', 256), ('map_id', 128), ('map_name', 256)):
            _text(row[key], limit, empty=key != 'name')
        if row['status'] not in ('waiting', 'full', 'ready', 'playing'):
            _error('invalid_input', 'Invalid native room status.')
        capacity = _int(row['capacity'], 2, 8)
        members = _int(row['members'], 0, capacity)
        # A running game's ready flags are frozen even if a participant loses
        # their connection; connected membership may then be smaller.
        _int(row['ready'], 0, capacity)
        _int(row['gold'], 0, 1000)
        _int(row['base_income'], 0, 20)
        if row['turns'] != -1:
            _int(row['turns'], 1, 1000)
        for key in ('fog', 'shroud', 'observers'):
            if type(row[key]) is not bool:
                _error('invalid_input', 'Invalid native room option.')
        if not isinstance(row['seats'], list) or len(row['seats']) != capacity:
            _error('invalid_input', 'Invalid native room seats.')
        sides, accounts = set(), set()
        for seat in row['seats']:
            if not isinstance(seat, dict) or set(seat) != SEAT_KEYS:
                _error('invalid_input', 'Invalid native room seat.')
            side = _int(seat['side'], 1, capacity)
            if side in sides:
                _error('invalid_input', 'Duplicate native room side.')
            sides.add(side)
            _text(seat['username'], 64, empty=True)
            _text(seat['unit_type'], 128, empty=True)
            if seat['account_id']:
                _uuid(seat['account_id'])
                if seat['account_id'] in accounts:
                    _error('invalid_input', 'Duplicate native room player.')
                accounts.add(seat['account_id'])
            elif seat['account_id'] != '':
                _error('invalid_input', 'Invalid native room player.')
            if type(seat['ready']) is not bool:
                _error('invalid_input', 'Invalid native room readiness.')
        return deepcopy(row)

    def publish(self, payload):
        """Service-authenticated native heartbeat. Caller must guard the route."""
        if not isinstance(payload, dict) or set(payload) != {'generation', 'register', 'rooms'}:
            _error('invalid_input', 'Invalid native lobby inventory.')
        generation = _uuid(payload['generation'])
        if type(payload['register']) is not bool or not isinstance(payload['rooms'], list) or len(payload['rooms']) > MAX_ROOMS:
            _error('invalid_input', 'Invalid native lobby inventory.')
        incoming = [self._valid_room(row) for row in payload['rooms']]
        if len({row['id'] for row in incoming}) != len(incoming) or len({row['native_id'] for row in incoming}) != len(incoming):
            _error('invalid_input', 'Duplicate native room inventory.')

        def write(session):
            now = _now()
            database_generation = self.domain._generation(session)
            current = self.db.schema_metadata.find_one({'_id': KEY}, session=session)
            if current and current.get('database_generation') != database_generation:
                _error('stale_generation', 'The database generation changed.')
            if not current or current['generation'] != generation:
                if not payload['register'] or (current and current['expires_at'] > now):
                    _error('stale_generation', 'Another native lobby owns the room inventory.')
                current = {'_id': KEY, 'version': 1, 'database_generation': database_generation,
                           'generation': generation, 'rooms': [], 'closed': [], 'requests': {}, 'counter': 0}
            previous = {row['id']: row for row in current['rooms']}
            requests = current['requests']
            rooms, close = [], []
            for raw in incoming:
                fingerprint = _digest(raw)
                prior = previous.pop(raw['id'], None)
                if not prior or prior['fingerprint'] != fingerprint:
                    current['counter'] += 1
                revision = prior['revision'] if prior and prior['fingerprint'] == fingerprint else current['counter']
                row = {**raw, 'native_revision': raw['revision'], 'revision': revision,
                       'fingerprint': fingerprint, 'updated_at': now}
                pending = requests.get(row['id'])
                if pending and pending['state'] == 'pending':
                    if pending['fingerprint'] == fingerprint:
                        close.append(row['id'])
                    else:
                        pending['state'] = 'changed'
                row['close_status'] = pending['state'] if pending else ''
                rooms.append(row)
            for row in previous.values():
                pending = requests.get(row['id'])
                row.update(status='closed', closed_at=now,
                           close_status='closed' if pending and pending['state'] == 'pending' else '')
                if pending and pending['state'] == 'pending':
                    self.domain._audit(pending['actor_id'], 'room_close_acknowledged', row['id'],
                                       'Native lobby confirmed that the requested Room is no longer present.',
                                       {'state': 'pending', 'generation': generation}, {'state': 'closed'}, session)
                current['closed'].insert(0, row)
                requests.pop(row['id'], None)
            current['closed'] = current['closed'][:100]
            current.update(rooms=rooms, requests=requests, updated_at=now,
                           expires_at=now + timedelta(seconds=LEASE_SECONDS))
            self.db.schema_metadata.replace_one({'_id': KEY}, current, upsert=True, session=session)
            return {'generation': generation, 'close': close}
        return self.domain._tx(write)

    def snapshot(self):
        row = self.db.schema_metadata.find_one({'_id': KEY})
        if not row or row.get('database_generation') != self.domain._generation():
            return {'available': False, 'generation': '', 'updated_at': None, 'rooms': [], 'closed': []}
        result = {key: row.get(key) for key in ('generation', 'updated_at', 'rooms', 'closed')}
        result['available'] = row['expires_at'] > _now()
        for record in result['rooms'] + result['closed']:
            record.pop('fingerprint', None)
        return result

    def detail(self, room_id):
        _uuid(room_id)
        state = self.snapshot()
        for row in state['rooms'] + state['closed']:
            if row['id'] == room_id:
                return {**row, 'available': state['available'] and row['status'] != 'closed',
                        'generation': state['generation']}
        _error('not_found', 'Room not found in the retained native inventory.')

    def request_close(self, actor_id, room_id, expected_revision, generation, reason):
        _uuid(room_id)
        _uuid(generation)
        _int(expected_revision, 1, 2**63 - 1)
        reason = _reason(reason)
        def write(session):
            self.domain._admin(actor_id, session)
            state = self.db.schema_metadata.find_one({'_id': KEY}, session=session)
            if (not state or state['generation'] != generation or
                    state['database_generation'] != self.domain._generation(session) or state['expires_at'] <= _now()):
                _error('stale_generation', 'The native lobby is unavailable or restarted. Refresh first.')
            room = next((row for row in state['rooms'] if row['id'] == room_id), None)
            if not room or room['revision'] != expected_revision:
                _error('stale_revision', 'This room changed. Refresh before closing it.')
            prior = state['requests'].get(room_id)
            if prior and prior['state'] == 'pending':
                return {'room_id': room_id, 'state': 'pending'}
            state['requests'][room_id] = {'state': 'pending', 'fingerprint': room['fingerprint'],
                                         'requested_at': _now(), 'actor_id': actor_id}
            room['close_status'] = 'pending'
            self.db.schema_metadata.replace_one({'_id': KEY}, state, session=session)
            self.domain._audit(actor_id, 'request_room_close', room_id, reason,
                               {'state': room['status'], 'generation': generation}, {'state': 'pending'}, session)
            return {'room_id': room_id, 'state': 'pending'}
        return self.domain._tx(write)
