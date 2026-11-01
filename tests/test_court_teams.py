"""Replacement Team transactions and map identities against a disposable replica set."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from alliance.court.service import CourtService
from alliance.court.schema import bootstrap_court_schema
from alliance.court.geography import catalogue
from alliance.domain import DomainError


class GeographyCatalogue(unittest.TestCase):
    def test_distinct_identities_and_role_counts(self):
        data = catalogue()
        self.assertEqual(len({a['id'] for a in data['areas']}), 128)
        self.assertEqual({r['id'] for r in data['castle_template'] if r['role'] == 'competition'}, {'C028', 'C015'})
        self.assertEqual({r['id'] for r in data['castle_template'] if r['role'] == 'plan'}, {'C010', 'C055'})
        self.assertEqual(sum(r['role'] == 'normal' for r in data['castle_template']), 60)
        self.assertEqual(len({a['id'] + '-' + c['id'] for a in data['areas'] for c in data['castle_template']}), 8192)


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set')
class CourtTeams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ['ALLIANCE_TEST_MONGO_URI']
        if urlsplit(uri).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('Disposable loopback only')
        cls.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.name = 'court_team_test_' + uuid4().hex
        self.db = self.client[self.name]
        bootstrap_court_schema(self.db)
        self.now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        self.service = CourtService(self.db, clock=lambda: self.now)
        self.actor = self.player('Captain')
        self.member = self.player('Member')
        self.admin = self.player('Host', role='admin')

    def tearDown(self):
        self.client.drop_database(self.name)

    def player(self, name=None, role='player'):
        name = name or 'P_' + uuid4().hex[:12]
        method = self.service.bootstrap_admin if role == 'admin' else self.service.register
        return method(name, '$argon2id$disposable-test-not-authenticated')['_id']

    def command(self, operation, actor=None, command_id=None, **payload):
        body = {'version': 1, 'operation': operation,
                'payload': {'command_id': command_id or str(uuid4()), **payload}}
        return self.service.court_command(actor or self.actor, body)['data']

    def query(self, query, actor=None, **payload):
        return self.service.court_query(actor or self.actor, {'version': 1, 'query': query, 'payload': payload})['data']

    def paid(self, operation, **payload):
        return self.command(operation, price_revision=0, confirmation='confirmed', **payload)

    def credit(self, actor=None, amount=1000, kind='personal'):
        self.service._tx(lambda s: self.service._wallet_credit(kind, actor or self.actor, amount,
            'fixture:' + str(uuid4()), 'Disposable fixture grant', s))

    def team(self, name='First Team', actor=None):
        self.credit(actor)
        return self.paid('create_team', actor=actor, name=name, area_id='A001')['team']

    def error(self, code, action):
        with self.assertRaises(DomainError) as result:
            action()
        self.assertEqual(result.exception.code, code)

    def test_fresh_map_resumable_and_old_database_refused(self):
        generation = self.service._generation()
        self.assertEqual(self.db.court_areas.count_documents({}), 128)
        self.assertEqual(self.db.court_castles.count_documents({}), 8192)
        self.assertEqual(self.db.court_castles.count_documents({'owner_team_id': {'$ne': None}}), 0)
        self.assertEqual(self.db.court_castles.count_documents({'enabled': True}), 4)
        bootstrap_court_schema(self.db)
        self.assertEqual(self.service._generation(), generation)
        self.assertEqual(self.db.accounts.count_documents({}), 3)
        self.db.schema_metadata.update_one({'_id': 'alliance'}, {'$set': {'version': 4}})
        with self.assertRaises(RuntimeError):
            bootstrap_court_schema(self.db)
        self.assertEqual(self.db.accounts.count_documents({}), 3)

    def test_zero_wallet_world_browse_and_member_gate(self):
        snapshot = self.query('snapshot')
        self.assertIsNone(snapshot['team'])
        self.assertEqual(snapshot['wallet']['available'], 0)
        self.assertEqual(snapshot['heroes'], [])
        self.assertEqual(len(snapshot['areas']), 128)
        self.error('team_required', lambda: self.query('area', area_id='A001'))

    def test_paid_creation_and_exact_retry_no_free_treasury(self):
        self.credit()
        command = str(uuid4())
        first = self.paid('create_team', command_id=command, name='Court Team', area_id='A001')
        second = self.paid('create_team', command_id=command, name='Court Team', area_id='A001')
        self.assertEqual(first, second)
        self.assertEqual(self.query('wallet')['wallet']['available'], 950)
        self.assertEqual(first['team']['wallet']['available'], 0)
        self.assertEqual(self.db.court_teams.count_documents({}), 1)
        self.error('command_conflict', lambda: self.paid('create_team', command_id=command, name='Different', area_id='A001'))

    def test_command_id_scope_does_not_cross_accounts(self):
        command = str(uuid4())
        self.credit(); self.credit(self.member)
        a = self.paid('create_team', command_id=command, name='Alpha Team', area_id='A001')['team']
        b = self.paid('create_team', actor=self.member, command_id=command, name='Bravo Team', area_id='A001')['team']
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(self.query('wallet', actor=self.member)['wallet']['available'], 950)

    def test_insufficient_funds_does_not_create_team_or_receipt(self):
        self.error('insufficient_funds', lambda: self.paid('create_team', name='Empty Team', area_id='A001'))
        self.assertEqual(self.db.court_teams.count_documents({}), 0)
        self.assertEqual(self.db.court_commands.count_documents({}), 0)

    def test_join_fee_held_until_captain_accepts_and_retry_is_exact(self):
        team = self.team(); self.credit(self.member)
        application = self.paid('apply_team', actor=self.member, team_id=team['id'], revision=team['revision'])['application']
        wallet = self.query('wallet', actor=self.member)['wallet']
        self.assertEqual((wallet['available'], wallet['held']), (995, 5))
        self.assertIsNone(self.query('my_team', actor=self.member)['team'])
        self.command('approve_member', application_id=application['id'], revision=application['revision'])
        self.assertEqual(self.query('my_team', actor=self.member)['team']['member_count'], 2)
        self.assertEqual(self.query('wallet', actor=self.member)['wallet']['held'], 0)
        self.assertEqual(self.db.court_applications.find_one({'_id': application['id']})['state'], 'approved')

    def test_withdrawal_and_expiry_release_held_join_cash(self):
        team = self.team(); self.credit(self.member)
        app = self.paid('apply_team', actor=self.member, team_id=team['id'], revision=team['revision'])['application']
        self.command('withdraw_application', actor=self.member, application_id=app['id'], revision=app['revision'])
        self.assertEqual(self.query('wallet', actor=self.member)['wallet']['available'], 1000)
        team = self.query('my_team')['team']
        app = self.paid('apply_team', actor=self.member, team_id=team['id'], revision=team['revision'])['application']
        self.now += timedelta(days=1)
        self.service._tx(self.service._expire_applications)
        self.assertEqual(self.db.court_applications.find_one({'_id': app['id']})['state'], 'expired')
        self.assertEqual(self.query('wallet', actor=self.member)['wallet']['available'], 1000)

    def test_member_only_cannot_approve_or_inspect_team_wallet(self):
        team = self.team(); self.credit(self.member)
        public = self.query('team', actor=self.member, team_id=team['id'])['team']
        self.assertNotIn('wallet', public)
        self.assertNotIn('applications', public)
        app = self.paid('apply_team', actor=self.member, team_id=team['id'], revision=team['revision'])['application']
        self.error('forbidden', lambda: self.command('approve_member', actor=self.member, application_id=app['id'], revision=app['revision']))

    def test_concurrent_team_creation_one_charge_one_membership(self):
        self.credit()
        def create(name):
            try:
                return self.paid('create_team', name=name, area_id='A001')
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create, ['One Team', 'Two Team']))
        self.assertEqual(sum(isinstance(row, dict) for row in results), 1)
        self.assertEqual(self.query('wallet')['wallet']['available'], 950)
        self.assertEqual(self.db.court_teams.count_documents({'members.account_id': self.actor}), 1)

    def test_member_commitment_prevents_leaving(self):
        team = self.team()
        self.db.court_seats.insert_one({'_id': self.actor, 'match_id': str(uuid4()), 'team_id': team['id'], 'created_at': self.now})
        self.error('player_committed', lambda: self.command('leave_team', team_id=team['id'], revision=team['revision'], confirmation='confirmed'))

    def test_other_account_cannot_read_receipt_or_notification(self):
        self.credit(); command = str(uuid4())
        self.paid('create_team', command_id=command, name='Receipt Team', area_id='A001')
        self.assertTrue(self.query('command_status', command_id=command)['found'])
        self.assertFalse(self.query('command_status', actor=self.member, command_id=command)['found'])
        self.service._tx(lambda s: self.service._notify(self.actor, 'test', 'Notice', 'Fixture', {}, s))
        notice = self.query('notifications')['items'][0]
        self.error('not_found', lambda: self.command('read_notification', actor=self.member, notification_id=notice['id']))
        self.command('read_notification', notification_id=notice['id'])
        self.assertEqual(self.query('snapshot')['notifications_unread'], 0)

    def test_admin_and_native_actions_cannot_be_dispatched_by_player(self):
        for operation in ('approve_cash', 'set_activation', 'admin_create_competition', 'worker_finish', '_wallet_credit'):
            self.error('unsupported_command', lambda: self.command(operation))

    def join(self, team, member=None):
        member = member or self.member
        self.credit(member)
        application = self.paid('apply_team', actor=member, team_id=team['id'], revision=team['revision'])['application']
        return self.command('approve_member', application_id=application['id'],
            revision=application['revision'])['team']

    def test_captain_remove_and_rename_preserve_wallets_and_guard_membership(self):
        team = self.join(self.team())
        before = self.service._wallet_public('personal', self.member)
        self.error('forbidden', lambda: self.command('remove_member', actor=self.member,
            team_id=team['id'], revision=team['revision'], account_id=self.actor, confirmation='confirmed'))
        renamed = self.command('rename_team', team_id=team['id'], revision=team['revision'],
            name='Emerald Company', confirmation='confirmed')['team']
        self.assertEqual(renamed['name'], 'Emerald Company')
        removed = self.command('remove_member', team_id=team['id'], revision=renamed['revision'],
            account_id=self.member, confirmation='confirmed')['team']
        self.assertEqual(removed['member_count'], 1)
        self.assertIsNone(self.query('my_team', actor=self.member)['team'])
        self.assertEqual(self.service._wallet_public('personal', self.member), before)
        self.assertTrue(self.query('notifications', actor=self.member)['items'])

    def test_leaving_and_rejoining_never_reactivates_saved_defense(self):
        team = self.join(self.team())
        defense_id = str(uuid4())
        self.db.court_defenses.insert_one({'_id': defense_id, 'team_id': team['id'],
            'owner_id': self.member, 'selection': {}, 'status': 'approved', 'revision': 0})
        self.db.court_teams.update_one({'_id': team['id']}, {'$set': {'defense_id': defense_id}})
        self.command('leave_team', actor=self.member, team_id=team['id'], revision=team['revision'], confirmation='confirmed')
        self.assertEqual(self.db.court_defenses.find_one({'_id': defense_id})['status'], 'withdrawn')
        self.join(self.query('my_team')['team'])
        self.assertEqual(self.query('my_team')['team']['defenses'], [])

    def test_inbox_and_team_history_are_newest_first_and_owner_scoped(self):
        team = self.team()
        for n in range(25):
            self.now += timedelta(seconds=1)
            self.service._tx(lambda session: self.service._notify(self.actor, 'fixture', str(n),
                'History fixture', {}, session))
            self.service._tx(lambda session: self.service._history(team['id'], 'fixture', str(n), {}, session))
        for query in ('notifications', 'history'):
            first = self.query(query)
            self.assertEqual([row['title'] for row in first['items']], [str(n) for n in range(24, 4, -1)])
            second = self.query(query, after=first['next'])
            self.assertEqual([row['title'] for row in second['items']][:5], [str(n) for n in range(4, -1, -1)])
            self.assertFalse(set(row['id'] for row in first['items']) & set(row['id'] for row in second['items']))
        self.error('invalid_input', lambda: self.query('notifications', actor=self.member,
            after=self.query('notifications')['next']))

    def test_activation_delay_keeps_owned_castle_visible(self):
        team = self.team()
        castle_id = 'A001-C064'
        self.db.court_castles.update_one({'_id': castle_id}, {'$set': {'enabled': True,
            'owner_team_id': team['id'], 'below_since': self.now - timedelta(days=2)}})
        self.service._tx(self.service._refresh_population)
        self.assertTrue(self.db.court_castles.find_one({'_id': castle_id})['enabled'])
        self.db.court_castles.update_one({'_id': castle_id}, {'$set': {'owner_team_id': None}})
        self.service._tx(self.service._refresh_population)
        self.now += timedelta(hours=23)
        self.service._tx(self.service._refresh_population)
        self.assertTrue(self.db.court_castles.find_one({'_id': castle_id})['enabled'])
        self.now += timedelta(hours=1)
        self.service._tx(self.service._refresh_population)
        self.assertFalse(self.db.court_castles.find_one({'_id': castle_id})['enabled'])
