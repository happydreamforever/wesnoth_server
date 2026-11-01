"""Paid Room admission, fenced to the authenticated native lobby generation.

Players review a current quote and reserve a fee before requesting admission.
Only the native Room server may admit, start, renew or close the resulting Room.
Room play never awards collection XP, Crown rewards or territory.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import re
import secrets

from .base import exact, fail, identifier, integer


class RoomMixin:
    def _query_room_quote(self, actor, payload, session):
        exact(payload)
        settings = self._settings(session)
        return {'price_revision': settings['revision'], 'create_fee': settings['prices']['create_room'],
            'join_fee': settings['prices']['join_room'], 'wallet': self._wallet_public('personal', actor, session)}

    def _court_room_consent(self, actor, payload, session):
        exact(payload, ('kind', 'game_id', 'price_revision', 'confirmation'))
        self._confirmed(payload)
        settings = self._price_revision(payload, session)
        kind, game_id = payload['kind'], payload['game_id']
        if kind not in ('create', 'join') or (kind == 'create' and game_id != ''):
            fail('invalid_input', 'Review the Room admission fee.')
        if kind == 'join':
            identifier(game_id)
        self._expire_room_holds(session)
        if self.db.court_room_admissions.find_one({'account_id': actor, 'state': {'$in': ['reserved', 'admitted', 'started']}}, session=session):
            fail('player_committed', 'Leave or finish your current Room admission first.')
        reservation = self.db.network_battle_reservations.find_one({'_id': actor}, session=session)
        if reservation:
            fail('player_committed', 'Finish the current network battle first.')
        token = secrets.token_urlsafe(32)
        key = sha256(token.encode('ascii')).hexdigest()
        hold = 'room:' + actor + ':' + payload['command_id']
        fee = settings['prices'][kind + '_room']
        self._wallet_hold('personal', actor, fee, hold, kind + '_room', session)
        expiry = self._now() + timedelta(minutes=2)
        self.db.court_room_admissions.insert_one({'_id': key, 'account_id': actor, 'kind': kind,
            'game_id': game_id, 'database_generation': self._generation(session), 'native_generation': None,
            'hold_id': hold, 'state': 'reserved', 'fee': fee, 'created_at': self._now(), 'expires_at': expiry}, session=session)
        return {'ticket': token, 'fee': fee, 'expires_at': expiry,
                'wallet': self._wallet_public('personal', actor, session)}

    def court_room_admit(self, ticket, account_id, game_id, generation, kind):
        identifier(account_id); identifier(game_id); identifier(generation)
        if not isinstance(ticket, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket) or kind not in ('create', 'join'):
            fail('invalid_ticket', 'Review the Room admission fee again.')
        key = sha256(ticket.encode('ascii')).hexdigest()
        def write(session):
            self._actor(account_id, session)
            admission = self.db.court_room_admissions.find_one({'_id': key}, session=session)
            if (not admission or admission['database_generation'] != self._generation(session)
                    or admission['account_id'] != account_id or admission['kind'] != kind):
                fail('invalid_ticket', 'This admission belongs to another player or action.')
            if admission['state'] in ('admitted', 'started'):
                if admission['game_id'] != game_id or admission['native_generation'] != generation:
                    fail('invalid_ticket', 'This admission already belongs to another Room.')
                return {'game_id': game_id, 'account_id': account_id, 'admitted': True}
            if admission['state'] != 'reserved' or admission['expires_at'] <= self._now():
                fail('invalid_ticket', 'The admission expired. Review the Room fee again.')
            if kind == 'join' and admission['game_id'] != game_id:
                fail('invalid_ticket', 'This admission belongs to another Room.')
            room = self.db.court_rooms.find_one({'_id': game_id}, session=session)
            if kind == 'create':
                if room:
                    fail('room_conflict', 'A different admission already created this Room.')
                room = {'_id': game_id, 'generation': generation, 'owner_id': account_id,
                    'state': 'waiting', 'revision': 0, 'created_at': self._now(),
                    'expires_at': self._now() + timedelta(minutes=2)}
                self.db.court_rooms.insert_one(room, session=session)
            elif not room or room['generation'] != generation or room['state'] != 'waiting' or room['expires_at'] <= self._now():
                fail('room_unavailable', 'This Room is no longer waiting for players.')
            self.db.court_rooms.update_one({'_id': game_id}, {'$inc': {'revision': 1}}, session=session)
            self.db.court_room_admissions.update_one({'_id': key}, {'$set': {'state': 'admitted',
                'game_id': game_id, 'native_generation': generation,
                'expires_at': self._now() + timedelta(minutes=2)}}, session=session)
            return {'game_id': game_id, 'account_id': account_id, 'admitted': True}
        return self._tx(write)

    def _room_release_admission(self, row, session, *, technical=False):
        if row['state'] in ('reserved', 'admitted'):
            self._wallet_release(row['hold_id'], session)
        elif row['state'] == 'started' and technical:
            self._wallet_refund(row['hold_id'], 'Native Room interrupted', session)
        self.db.court_room_admissions.update_one({'_id': row['_id']}, {'$set': {'state': 'closed',
            'closed_at': self._now(), 'technical': technical}}, session=session)

    def court_room_leave(self, account_id, game_id, generation):
        identifier(account_id); identifier(game_id); identifier(generation)
        def write(session):
            room = self.db.court_rooms.find_one({'_id': game_id, 'generation': generation}, session=session)
            if room:
                self.db.court_rooms.update_one({'_id': game_id}, {'$inc': {'revision': 1}}, session=session)
            row = self.db.court_room_admissions.find_one({'account_id': account_id,
                'game_id': game_id, 'native_generation': generation,
                'state': {'$in': ['admitted', 'started']}}, session=session)
            if row:
                self._room_release_admission(row, session)
            return {'released': True}
        return self._tx(write)

    def court_room_close(self, game_id, generation, technical=False):
        identifier(game_id); identifier(generation)
        if type(technical) is not bool:
            fail('invalid_input', 'Invalid Room closure.')
        def write(session):
            room = self.db.court_rooms.find_one({'_id': game_id, 'generation': generation}, session=session)
            if room and room['state'] != 'closed':
                self.db.court_rooms.update_one({'_id': game_id}, {'$set': {'state': 'closed',
                    'closed_at': self._now()}, '$inc': {'revision': 1}}, session=session)
                for row in self.db.court_room_admissions.find({'game_id': game_id,
                        'native_generation': generation, 'state': {'$in': ['admitted', 'started']}}, session=session):
                    self._room_release_admission(row, session, technical=technical)
                self.db.network_battle_reservations.delete_many({'kind': 'individual',
                    'run_id': game_id, 'generation': generation}, session=session)
            return {'closed': True}
        return self._tx(write)

    def court_rooms_heartbeat(self, generation, game_ids):
        identifier(generation)
        if not isinstance(game_ids, list) or len(game_ids) > 64 or len(set(game_ids)) != len(game_ids):
            fail('invalid_input', 'Invalid native Room heartbeat.')
        for game in game_ids:
            identifier(game)
        def write(session):
            self._expire_room_holds(session)
            renewed = []
            for game in game_ids:
                room = self.db.court_rooms.find_one({'_id': game, 'generation': generation,
                    'state': {'$in': ['waiting', 'playing']}}, session=session)
                if not room:
                    continue
                expiry = self._now() + timedelta(minutes=2)
                self.db.court_rooms.update_one({'_id': game}, {'$set': {'expires_at': expiry}}, session=session)
                self.db.court_room_admissions.update_many({'game_id': game, 'native_generation': generation,
                    'state': {'$in': ['admitted', 'started']}}, {'$set': {'expires_at': expiry}}, session=session)
                renewed.append(game)
            return {'generation': generation, 'renewed': renewed,
                    'expired': [game for game in game_ids if game not in renewed]}
        return self._tx(write)

    def _expire_room_holds(self, session):
        for row in self.db.court_room_admissions.find({'state': {'$in': ['reserved', 'admitted', 'started']},
                'expires_at': {'$lte': self._now()}}, session=session).limit(256):
            self._room_release_admission(row, session, technical=row['state'] == 'started')
        for room in self.db.court_rooms.find({'state': {'$in': ['waiting', 'playing']},
                'expires_at': {'$lte': self._now()}}, session=session).limit(64):
            self.db.court_rooms.update_one({'_id': room['_id']}, {'$set': {'state': 'closed',
                'closed_at': self._now()}, '$inc': {'revision': 1}}, session=session)
            self.db.network_battle_reservations.delete_many({'kind': 'individual',
                'run_id': room['_id'], 'generation': room['generation']}, session=session)

    def _network_reserve(self, actor_id, kind, run_id, generation, session, expires_at=None):
        self._actor(actor_id, session)
        prior = self.db.network_battle_reservations.find_one({'_id': actor_id}, session=session)
        if prior and prior['kind'] == 'individual' and prior.get('expires_at', self._now()) <= self._now():
            self.db.network_battle_reservations.delete_one({'_id': actor_id}, session=session)
            prior = None
        if prior and (prior['kind'], prior['run_id'], prior['generation']) != (kind, run_id, generation):
            fail('player_committed', 'This player already occupies a network battle.')
        self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
        record = {'_id': actor_id, 'kind': kind, 'run_id': run_id, 'generation': generation,
            'created_at': prior['created_at'] if prior else self._now()}
        if expires_at is not None:
            record['expires_at'] = expires_at
        self.db.network_battle_reservations.replace_one({'_id': actor_id}, record, upsert=True, session=session)

    def network_prepare(self, game_id, generation, account_ids):
        identifier(game_id); identifier(generation)
        if not isinstance(account_ids, list) or not 2 <= len(account_ids) <= 8:
            fail('invalid_input', 'A Room needs two to eight distinct human players.')
        for account in account_ids:
            identifier(account)
        if len(set(account_ids)) != len(account_ids):
            fail('invalid_input', 'Every human needs a distinct seat.')
        def write(session):
            room = self.db.court_rooms.find_one({'_id': game_id, 'generation': generation,
                'state': {'$in': ['waiting', 'playing']}, 'expires_at': {'$gt': self._now()}}, session=session)
            if not room:
                fail('room_unavailable', 'This Room has no current admission lease.')
            for account in account_ids:
                if not self.db.court_room_admissions.find_one({'account_id': account, 'game_id': game_id,
                    'native_generation': generation, 'state': {'$in': ['admitted', 'started']}}, session=session):
                    fail('admission_required', 'Every player must approve the Room fee.')
                self._network_reserve(account, 'individual', game_id, generation, session,
                    self._now() + timedelta(minutes=2))
            return {'game_id': game_id, 'generation': generation, 'reserved': len(account_ids)}
        return self._tx(write)

    def network_heartbeat(self, generation, game_ids):
        identifier(generation)
        if not isinstance(game_ids, list) or len(game_ids) > 64:
            fail('invalid_input', 'Invalid native heartbeat.')
        for game in game_ids: identifier(game)
        if len(set(game_ids)) != len(game_ids): fail('invalid_input', 'Repeated Room identifier.')
        def write(session):
            renewed, expired = [], []
            for game in game_ids:
                query = {'kind': 'individual', 'run_id': game, 'generation': generation}
                rows = list(self.db.network_battle_reservations.find(query, session=session))
                accounts = self.db.accounts.count_documents({'_id': {'$in': [r['_id'] for r in rows]},
                    'status': 'active', 'role': 'player'}, session=session)
                if len(rows) < 2 or accounts != len(rows) or any(r['expires_at'] <= self._now() for r in rows):
                    self.db.network_battle_reservations.delete_many(query, session=session)
                    expired.append(game)
                else:
                    for row in rows:
                        self.db.accounts.update_one({'_id': row['_id']}, {'$inc': {'revision': 1}}, session=session)
                    self.db.network_battle_reservations.update_many(query,
                        {'$set': {'expires_at': self._now() + timedelta(minutes=2)}}, session=session)
                    renewed.append(game)
            return {'generation': generation, 'renewed': renewed, 'expired': expired}
        return self._tx(write)

    def network_release(self, game_id, generation):
        identifier(game_id); identifier(generation)
        def write(session):
            self.db.network_battle_reservations.delete_many({'kind': 'individual',
                'run_id': game_id, 'generation': generation}, session=session)
            return {'game_id': game_id, 'released': True}
        return self._tx(write)

    def casual_freeze(self, game_id, players):
        identifier(game_id)
        if not isinstance(players, list) or not 2 <= len(players) <= 8:
            fail('invalid_input', 'A Room needs two to eight human players.')
        def write(session):
            room = self.db.court_rooms.find_one({'_id': game_id}, session=session)
            if not room or room['state'] not in ('waiting', 'playing') or room['expires_at'] <= self._now():
                fail('room_unavailable', 'The Room admission lease expired.')
            seen, sides, admissions = set(), set(), []
            for row in players:
                exact(row, ('account_id', 'username', 'side', 'selection'))
                account_id = identifier(row['account_id'])
                side = integer(row['side'], 1, 8)
                if account_id in seen or side in sides:
                    fail('invalid_input', 'Every Room seat needs a distinct human player.')
                seen.add(account_id); sides.add(side)
                account = self._actor(account_id, session)
                if account['username'] != row['username']:
                    fail('invalid_input', 'The player name differs from the authenticated account.')
                admission = self.db.court_room_admissions.find_one({'account_id': account_id, 'game_id': game_id,
                    'native_generation': room['generation'], 'state': {'$in': ['admitted', 'started']}}, session=session)
                reservation = self.db.network_battle_reservations.find_one({'_id': account_id, 'run_id': game_id,
                    'kind': 'individual', 'generation': room['generation'], 'expires_at': {'$gt': self._now()}}, session=session)
                if not admission or admission['expires_at'] <= self._now() or not reservation:
                    fail('admission_required', 'Every player must approve the Room fee before Ready.')
                selected = row['selection']
                if (not isinstance(selected, dict) or 'hero_id' not in selected or 'form_id' not in selected
                        or selected != self._selection(account_id, selected['hero_id'], selected['form_id'], session)):
                    fail('stale_proposal', 'A selected hero changed. Review it before Ready.')
                admissions.append(admission)
            if room['owner_id'] not in seen:
                fail('admission_required', 'The Room creator must participate.')
            document = {'_id': game_id, 'database_generation': self._generation(session),
                'players': sorted(deepcopy(players), key=lambda row: row['side'])}
            previous = self.db.casual_games.find_one({'_id': game_id}, session=session)
            if previous:
                if any(previous[key] != document[key] for key in document):
                    fail('snapshot_conflict', 'This Room already started with a different lineup.')
            else:
                self.db.casual_games.insert_one({**document, 'created_at': self._now()}, session=session)
                for admission in admissions:
                    self._wallet_capture(admission['hold_id'], session)
                    self.db.court_room_admissions.update_one({'_id': admission['_id']}, {'$set': {'state': 'started'}}, session=session)
                self.db.court_rooms.update_one({'_id': game_id}, {'$set': {'state': 'playing'}, '$inc': {'revision': 1}}, session=session)
            return {'game_id': game_id, 'database_generation': document['database_generation'], 'players': document['players']}
        return self._tx(write)

    def casual_restore(self, game_id):
        fail('unsupported_ruleset', 'Recorded Rooms can be viewed locally; create a new Room to play.')
