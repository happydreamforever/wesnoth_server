"""Native-only Room fee lifecycle; disposable real MongoDB transactions."""
from copy import deepcopy
from datetime import timedelta
import os
import unittest
from uuid import uuid4

import test_court_teams as fixtures
from alliance.admin_management import admin_hero_grant_form


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set')
class CourtRooms(unittest.TestCase):
    setUpClass = classmethod(fixtures.CourtTeams.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.CourtTeams.tearDownClass.__func__)
    tearDown = fixtures.CourtTeams.tearDown
    player = fixtures.CourtTeams.player
    command = fixtures.CourtTeams.command
    query = fixtures.CourtTeams.query
    paid = fixtures.CourtTeams.paid
    credit = fixtures.CourtTeams.credit
    error = fixtures.CourtTeams.error

    def setUp(self):
        fixtures.CourtTeams.setUp(self)
        self.credit(); self.credit(self.member)
        self.game, self.generation = str(uuid4()), str(uuid4())

    def consent(self, kind, actor=None, game=None, command_id=None):
        return self.paid('room_consent', actor=actor, kind=kind,
            game_id=game if game is not None else (self.game if kind == 'join' else ''), command_id=command_id)

    def admit(self, actor, kind, consent):
        return self.service.court_room_admit(consent['ticket'], actor, self.game, self.generation, kind)

    def waiting(self):
        self.admit(self.actor, 'create', self.consent('create'))
        self.admit(self.member, 'join', self.consent('join', self.member))

    def hero(self, actor, side):
        form = admin_hero_grant_form('deoran')
        self.db.account_heroes.insert_one({'_id': str(uuid4()), 'account_id': actor, 'hero_id': 'deoran',
            'forms': [form['id']], 'total_experience': 0, 'revision': 0, 'unlocked_at': self.now})
        selected = self.service._tx(lambda s: self.service._selection(actor, 'deoran', form['id'], s))
        return {'account_id': actor, 'username': self.db.accounts.find_one({'_id': actor})['username'],
                'side': side, 'selection': selected}

    def playing(self):
        self.waiting()
        players = [self.hero(self.actor, 1), self.hero(self.member, 2)]
        self.service.network_prepare(self.game, self.generation, [self.actor, self.member])
        result = self.service.casual_freeze(self.game, players)
        return players, result

    def test_quote_and_consent_hold_create_once_without_join_charge(self):
        quote = self.query('room_quote')
        self.assertEqual((quote['create_fee'], quote['join_fee']), (5, 2))
        command = str(uuid4())
        first = self.consent('create', command_id=command)
        self.assertEqual(first, self.consent('create', command_id=command))
        self.assertEqual((first['wallet']['available'], first['wallet']['held']), (995, 5))
        self.admit(self.actor, 'create', first)
        self.assertEqual(self.admit(self.actor, 'create', first)['admitted'], True)

    def test_other_actor_room_kind_and_generation_cannot_reuse_consent(self):
        ticket = self.consent('create')
        self.error('invalid_ticket', lambda: self.admit(self.member, 'create', ticket))
        self.error('invalid_ticket', lambda: self.admit(self.actor, 'join', ticket))
        self.admit(self.actor, 'create', ticket)
        self.error('invalid_ticket', lambda: self.service.court_room_admit(ticket['ticket'], self.actor,
            self.game, str(uuid4()), 'create'))

    def test_departure_before_start_refunds_and_new_consent_is_needed(self):
        self.waiting()
        self.service.court_room_leave(self.member, self.game, self.generation)
        wallet = self.query('wallet', actor=self.member)['wallet']
        self.assertEqual((wallet['available'], wallet['held']), (1000, 0))
        self.error('admission_required', lambda: self.service.network_prepare(self.game, self.generation, [self.actor, self.member]))

    def test_native_start_captures_fees_exactly_once_no_rewards(self):
        players, result = self.playing()
        before = list(self.db.account_heroes.find().sort('account_id', 1))
        self.assertEqual(self.service.casual_freeze(self.game, players), result)
        a = self.query('wallet')['wallet']; b = self.query('wallet', actor=self.member)['wallet']
        self.assertEqual((a['available'], a['held'], b['available'], b['held']), (995, 0, 998, 0))
        self.assertEqual(list(self.db.account_heroes.find().sort('account_id', 1)), before)
        self.assertEqual(self.db.court_reward_claims.count_documents({}), 0)
        self.service.court_room_close(self.game, self.generation)
        self.assertEqual(self.query('wallet')['wallet']['available'], 995)

    def test_technical_native_close_refunds_started_fees_once(self):
        self.playing()
        self.service.court_room_close(self.game, self.generation, technical=True)
        self.service.court_room_close(self.game, self.generation, technical=True)
        self.assertEqual(self.query('wallet')['wallet']['available'], 1000)
        self.assertEqual(self.query('wallet', actor=self.member)['wallet']['available'], 1000)
        self.assertEqual(self.db.network_battle_reservations.count_documents({}), 0)

    def test_abandoned_consent_and_dead_native_lease_release_cash(self):
        self.consent('create')
        self.now += timedelta(minutes=2)
        self.service._tx(self.service._expire_room_holds)
        self.assertEqual(self.query('wallet')['wallet']['available'], 1000)
        self.playing()
        self.now += timedelta(minutes=2)
        self.service._tx(self.service._expire_room_holds)
        self.assertEqual(self.query('wallet')['wallet']['available'], 1000)
        self.assertEqual(self.db.court_rooms.find_one({'_id': self.game})['state'], 'closed')

    def test_heartbeat_cannot_revive_expired_room(self):
        self.waiting()
        self.now += timedelta(minutes=2)
        result = self.service.court_rooms_heartbeat(self.generation, [self.game])
        self.assertEqual(result['expired'], [self.game])
        self.assertEqual(self.query('wallet')['wallet']['available'], 1000)

    def test_wrong_generation_close_and_release_preserve_other_room(self):
        self.waiting()
        self.service.court_room_close(self.game, str(uuid4()), technical=True)
        self.assertEqual(self.query('wallet')['wallet']['held'], 5)
        self.assertEqual(self.db.court_rooms.find_one({'_id': self.game})['state'], 'waiting')

    def test_court_prepared_player_cannot_reserve_room(self):
        self.db.network_battle_reservations.insert_one({'_id': self.actor, 'kind': 'court',
            'run_id': str(uuid4()), 'generation': str(uuid4()), 'created_at': self.now})
        self.error('player_committed', lambda: self.consent('create'))
        self.assertEqual(self.query('wallet')['wallet']['available'], 1000)

    def test_price_change_requires_new_consent(self):
        self.db.court_settings.update_one({'_id': 'rules'}, {'$inc': {'revision': 1}})
        self.error('price_changed', lambda: self.consent('create'))
        self.assertEqual(self.query('wallet')['wallet']['held'], 0)

    def test_old_room_save_cannot_resume_on_network(self):
        self.error('unsupported_ruleset', lambda: self.service.casual_restore(self.game))
