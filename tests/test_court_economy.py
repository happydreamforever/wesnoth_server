"""Real transactions for virtual Crowns in disposable, schema-5 fixture databases.

No existing game database, private runtime or external payment processor is used.
The complete production CourtService is exercised. The fixture initializes
strict production collection validators without geographical seed rows, since
these economy operations do not depend on world activation.
"""
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
from pymongo.errors import WriteError
from alliance.domain import DomainError
from alliance.heroes import load_catalog
from alliance.court.service import CourtService
from alliance.admin_management import admin_hero_grant_form
from alliance.court.base import PRICES, LIMITS
from alliance.court.schema import SCHEMAS as CORE_SCHEMAS
from alliance.court.wallet_schema import SCHEMAS, bootstrap_indexes, MAX_CROWNS


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set')
class CourtEconomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ['ALLIANCE_TEST_MONGO_URI']
        parsed = urlsplit(uri)
        if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or ',' in parsed.netloc:
            raise RuntimeError('Disposable loopback replica set required')
        cls.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        if not cls.client.admin.command('hello').get('isWritablePrimary'):
            raise RuntimeError('Writable replica set required')

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.name = 'court_economy_test_' + uuid4().hex
        self.db = self.client[self.name]
        self.now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        for name, validator in {**CORE_SCHEMAS, **SCHEMAS}.items():
            self.db.create_collection(name, validator=validator, validationLevel='strict')
        bootstrap_indexes(self.db)
        self.db.accounts.create_index('username_key', unique=True)
        self.db.account_heroes.create_index([('account_id', 1), ('hero_id', 1)], unique=True)
        self.db.court_commands.create_index([('account_id', 1), ('command_id', 1)], unique=True)
        self.db.schema_metadata.insert_one({'_id': 'alliance', 'version': 5,
            'database_generation': str(uuid4()), 'court_initialized': True})
        self.db.court_settings.insert_one({'_id': 'rules', 'revision': 0,
            'prices': deepcopy(PRICES), 'limits': deepcopy(LIMITS)})
        self.service = CourtService(self.db, clock=lambda: self.now)
        self.actor, self.member, self.outsider = self.player(), self.player(), self.player()
        self.admin = self.player(role='admin')
        self.team = self.make_team(self.actor, self.member)

    def tearDown(self):
        self.client.drop_database(self.name)

    def player(self, role='player'):
        actor = str(uuid4())
        self.db.accounts.insert_one({'_id': actor, 'username': 'P_' + actor[:8],
            'username_key': 'p_' + actor[:8], 'role': role, 'status': 'active',
            'password_hash': '$argon2id$disposable-not-used-for-auth',
            'database_generation': self.service._generation(), 'active_run_id': None, 'revision': 0})
        return actor

    def make_team(self, captain, *members):
        team = str(uuid4())
        self.db.court_teams.insert_one({'_id': team, 'name': 'Team_' + team[:8], 'name_key': team,
            'captain_id': captain, 'area_id': 'A001', 'status': 'active', 'level': 1,
            'experience': 0, 'allowances': {}, 'revision': 0,
            'members': [{'account_id': a, 'joined_at': self.now} for a in (captain, *members)]})
        return team

    def tx(self, name, *args, **kwargs):
        return self.service._tx(lambda s: getattr(self.service, name)(*args, session=s, **kwargs))

    def command(self, operation, actor=None, command_id=None, **payload):
        actor = actor or self.actor
        payload = {'command_id': command_id or str(uuid4()), **payload}
        dispatch = self.service.court_admin_command if operation in ('approve_cash', 'reject_cash') else self.service.court_command
        return dispatch(actor, {'version': 1, 'operation': operation, 'payload': payload})['data']

    def buy(self, operation, actor=None, **payload):
        return self.command(operation, actor=actor, price_revision=0, confirmation='confirmed', **payload)

    def credit(self, amount=100, actor=None, kind='personal', reference=None):
        return self.tx('_wallet_credit', kind, actor or self.actor, amount,
            reference or 'fixture:' + str(uuid4()), 'Disposable test grant')

    def wallet(self, actor=None, kind='personal'):
        return self.service._wallet_public(kind, actor or self.actor)

    def error(self, code, operation):
        with self.assertRaises(DomainError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)

    def review(self, request, approve=True, **overrides):
        payload = {'request_id': request['id'], 'revision': request['revision'],
            'reason': 'Reviewed virtual package', 'confirmation': 'confirmed', **overrides}
        return self.command('approve_cash' if approve else 'reject_cash', actor=self.admin, **payload)

    def snapshot(self):
        return {name: list(self.db[name].find().sort('_id', 1))
            for name in self.db.list_collection_names() if not name.startswith('system.')}

    def test_empty_wallet_is_zero_without_writing_and_cannot_read_another_wallet(self):
        self.assertEqual(self.wallet()['available'], 0)
        self.assertEqual(self.wallet()['held'], 0)
        self.assertEqual(self.db.court_wallets.count_documents({}), 0)
        self.error('invalid_input', lambda: self.service._court_wallet(self.actor, {'owner_id': self.outsider}))
        self.error('team_required', lambda: self.service._court_wallet(self.outsider, {'kind': 'team'}))

    def test_credit_exact_binding_and_balanced_ledger(self):
        self.credit(100, reference='credit:same')
        self.credit(100, reference='credit:same')
        self.assertEqual(self.wallet()['available'], 100)
        self.assertEqual(self.db.court_ledger.count_documents({}), 1)
        self.error('transaction_conflict', lambda: self.credit(101, reference='credit:same'))
        self.error('transaction_conflict', lambda: self.credit(100, self.outsider, reference='credit:same'))
        for row in self.db.court_ledger.find():
            self.assertEqual(sum(p['amount'] for p in row['postings']), 0)

    def test_hold_capture_and_technical_refund_idempotency(self):
        self.credit()
        for _ in range(2):
            self.tx('_wallet_hold', 'personal', self.actor, 70, 'hold:one', 'Battle seat')
        self.assertEqual((self.wallet()['available'], self.wallet()['held']), (30, 70))
        for _ in range(2): self.tx('_wallet_capture', 'hold:one')
        self.assertEqual((self.wallet()['available'], self.wallet()['held']), (30, 0))
        for _ in range(2): self.tx('_wallet_refund', 'hold:one', 'Verified technical cancellation')
        self.assertEqual((self.wallet()['available'], self.wallet()['held']), (100, 0))
        self.error('transaction_conflict', lambda: self.tx('_wallet_refund', 'hold:one', 'Different reason'))
        self.error('hold_finalized', lambda: self.tx('_wallet_capture', 'hold:one'))
        self.assertEqual(self.db.court_ledger.count_documents({}), 4)

    def test_release_unused_hold_and_reject_rebinding_or_double_spend(self):
        self.credit(20)
        self.tx('_wallet_hold', 'personal', self.actor, 20, 'hold:one', 'Planned battle')
        before = self.snapshot()
        self.error('transaction_conflict', lambda: self.tx('_wallet_hold', 'personal', self.actor, 19, 'hold:one', 'Planned battle'))
        self.error('insufficient_funds', lambda: self.tx('_wallet_hold', 'personal', self.actor, 1, 'hold:two', 'Another battle'))
        self.assertEqual(before, self.snapshot())
        for _ in range(2): self.tx('_wallet_release', 'hold:one')
        self.assertEqual(self.wallet()['available'], 20)
        self.error('hold_finalized', lambda: self.tx('_wallet_capture', 'hold:one'))

    def test_amounts_reject_boolean_float_negative_and_limit_includes_held(self):
        for value in (True, False, 1.2, -1, MAX_CROWNS + 1, '100', None):
            self.error('invalid_input', lambda: self.credit(value))
        self.credit(MAX_CROWNS)
        self.tx('_wallet_hold', 'personal', self.actor, 100, 'held:max', 'Full balance fixture')
        self.error('balance_limit', lambda: self.credit(1))
        self.assertEqual(self.wallet()['available'] + self.wallet()['held'], MAX_CROWNS)

    def test_transaction_abort_restores_money_and_metadata(self):
        self.credit(100)
        before = self.snapshot()
        def abort(session):
            self.service._wallet_hold('personal', self.actor, 80, 'abort:hold', 'Aborted fixture', session)
            raise DomainError('test_abort', 'Roll back this transaction')
        self.error('test_abort', lambda: self.service._tx(abort))
        self.assertEqual(before, self.snapshot())

    def test_simultaneous_holds_never_overdraw(self):
        self.credit(50)
        def reserve(index):
            try:
                return self.tx('_wallet_hold', 'personal', self.actor, 10, 'race:' + str(index), 'Concurrent fixture')['state']
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(reserve, range(8)))
        self.assertEqual(results.count('held'), 5)
        self.assertEqual(results.count('insufficient_funds'), 3)
        self.assertEqual((self.wallet()['available'], self.wallet()['held']), (0, 50))

    def test_cash_packages_are_pending_and_admin_review_exactly_once(self):
        request = self.command('request_cash', kind='personal', package=500)['request']
        self.assertEqual(self.wallet()['available'], 0)
        command_id = str(uuid4())
        first = self.review(request, command_id=command_id)
        self.assertEqual(self.review(request, command_id=command_id), first)
        self.assertEqual(first['request']['state'], 'approved')
        self.assertEqual(self.wallet()['available'], 500)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'approve_crowns'}), 1)
        self.error('stale_revision', lambda: self.review(request))

    def test_request_packages_are_fixed_and_pending_requests_bounded(self):
        for value in (0, 99, 101, 499, 1001, True, 100.0):
            self.error('invalid_input', lambda: self.command('request_cash', kind='personal', package=value))
        self.error('invalid_input', lambda: self.command('request_cash', kind='personal', package=100, amount=500))
        for value in (100, 500, 1000): self.command('request_cash', kind='personal', package=value)
        self.error('pending_limit', lambda: self.command('request_cash', kind='personal', package=100))
        self.assertEqual(self.wallet()['available'], 0)

    def test_cash_rejection_no_credit_and_review_guard(self):
        request = self.command('request_cash', kind='personal', package=100)['request']
        self.error('forbidden', lambda: self.command('approve_cash', request_id=request['id'], revision=0,
            reason='Unauthorized attempt', confirmation='confirmed'))
        self.error('confirmation_required', lambda: self.review(request, confirmation=False))
        self.error('invalid_input', lambda: self.review(request, reason='x'))
        self.review(request, approve=False)
        self.assertEqual(self.wallet()['available'], 0)
        self.assertEqual(self.db.court_ledger.count_documents({}), 0)

    def test_captain_only_team_packages_and_changed_captain_cannot_be_credited(self):
        self.error('forbidden', lambda: self.command('request_cash', actor=self.member,
            kind='team', package=100, team_id=self.team))
        request = self.command('request_cash', kind='team', package=100, team_id=self.team)['request']
        self.db.court_teams.update_one({'_id': self.team}, {'$set': {'captain_id': self.member}, '$inc': {'revision': 1}})
        self.error('request_changed', lambda: self.review(request))
        self.assertEqual(self.wallet(self.team, 'team')['available'], 0)
        self.review(request, approve=False)

    def test_suspended_admin_or_requester_cannot_approve(self):
        request = self.command('request_cash', kind='personal', package=100)['request']
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'suspended'}})
        self.error('forbidden', lambda: self.review(request))
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'active'}})
        self.db.accounts.update_one({'_id': self.actor}, {'$set': {'status': 'suspended'}})
        self.error('account_unavailable', lambda: self.review(request))
        self.assertEqual(self.wallet()['available'], 0)

    def test_two_admins_cannot_approve_same_request_twice(self):
        request = self.command('request_cash', kind='personal', package=1000)['request']
        other = self.player(role='admin')
        def review(admin):
            try:
                self.command('approve_cash', actor=admin, request_id=request['id'], revision=0,
                    reason='Concurrent review', confirmation='confirmed')
                return 'approved'
            except DomainError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(review, [self.admin, other]))
        self.assertEqual(sorted(results), ['approved', 'stale_revision'])
        self.assertEqual(self.wallet()['available'], 1000)

    def test_member_donation_is_atomic_nonwithdrawable_and_no_issuance(self):
        self.credit(100, self.member)
        result = self.buy('donate', actor=self.member, team_id=self.team, amount=60)
        self.assertEqual(result['personal']['available'], 40)
        self.assertEqual(result['team']['available'], 60)
        ledger = self.db.court_ledger.find_one({'operation': 'contribution'})
        self.assertEqual(sum(p['amount'] for p in ledger['postings']), 0)
        self.assertTrue(all(not p['account'].startswith('system:') for p in ledger['postings']))
        self.error('invalid_input', lambda: self.buy('donate', actor=self.member, team_id=self.team, amount=-1))
        self.error('team_required', lambda: self.buy('donate', actor=self.outsider, team_id=self.team, amount=1))
        self.assertEqual(self.wallet(self.team, 'team')['available'], 60)

    def test_concurrent_donations_cannot_lose_cash_or_overdraw(self):
        self.credit(100, self.member)
        def donate(_):
            try:
                self.buy('donate', actor=self.member, team_id=self.team, amount=30)
                return 'success'
            except DomainError as error: return error.code
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(donate, range(4)))
        self.assertEqual(results.count('success'), 3)
        self.assertEqual(results.count('insufficient_funds'), 1)
        self.assertEqual(self.wallet(self.member)['available'], 10)
        self.assertEqual(self.wallet(self.team, 'team')['available'], 90)

    def test_same_command_uuid_on_different_accounts_is_independent(self):
        self.credit(10)
        self.credit(10, self.member)
        command_id = str(uuid4())
        for actor in (self.actor, self.member):
            self.buy('buy_item', actor=actor, command_id=command_id, item_id='remedy', quantity=1)
            self.assertEqual(self.wallet(actor)['available'], 5)
        self.assertEqual(self.db.court_holds.count_documents({}), 2)

    def test_changed_body_reusing_command_id_is_rejected(self):
        self.credit(20)
        command_id = str(uuid4())
        result = self.buy('buy_item', command_id=command_id, item_id='remedy', quantity=1)
        self.assertEqual(self.buy('buy_item', command_id=command_id, item_id='remedy', quantity=1), result)
        self.error('command_conflict', lambda: self.buy('buy_item', command_id=command_id, item_id='remedy', quantity=2))
        self.assertEqual(self.wallet()['available'], 15)

    def test_hero_purchase_uses_lowest_real_form_and_no_campaign_fabrication(self):
        self.credit(200)
        result = self.buy('buy_hero', hero_id='abhai')
        form = admin_hero_grant_form('abhai')
        self.assertEqual(result['form_id'], form['id'])
        row = self.db.account_heroes.find_one({'account_id': self.actor, 'hero_id': 'abhai'})
        self.assertEqual(row['forms'], [form['id']])
        self.assertEqual(row['total_experience'], 0)
        self.assertEqual(row['unlock_source'], 'shop')
        self.assertEqual(self.db.story_checkpoints.count_documents({}), 0)
        self.assertEqual(self.db.game_runs.count_documents({}), 0)
        self.assertEqual(self.wallet()['available'], 100)
        before = self.snapshot()
        self.error('hero_already_owned', lambda: self.buy('buy_hero', hero_id='abhai'))
        self.assertEqual(before, self.snapshot())

    def test_hero_purchase_does_not_replace_existing_xp_or_accept_unknown_form(self):
        self.credit(200)
        self.buy('buy_hero', hero_id='abhai')
        self.db.account_heroes.update_one({'account_id': self.actor}, {'$set': {'total_experience': 200}, '$inc': {'revision': 1}})
        self.error('hero_already_owned', lambda: self.buy('buy_hero', hero_id='abhai'))
        self.error('invalid_input', lambda: self.buy('buy_hero', hero_id='fake_hero'))
        self.error('invalid_input', lambda: self.buy('buy_hero', hero_id='deoran', form_id='invented'))
        self.assertEqual(self.db.account_heroes.find_one()['total_experience'], 200)

    def test_stale_price_and_unconfirmed_purchase_do_not_spend(self):
        self.credit(200)
        self.db.court_settings.update_one({'_id': 'rules'}, {'$inc': {'revision': 1}})
        self.error('price_changed', lambda: self.buy('buy_hero', hero_id='abhai'))
        self.error('confirmation_required', lambda: self.command('buy_hero', hero_id='abhai', price_revision=1, confirmation=False))
        self.assertEqual(self.wallet()['available'], 200)
        self.assertEqual(self.db.account_heroes.count_documents({}), 0)

    def test_shop_pagination_filters_do_not_leak_other_players(self):
        self.credit(100)
        self.buy('buy_hero', hero_id='abhai')
        found, after = [], ''
        while True:
            result = self.service._court_shop(self.actor, {'after': after})
            found.extend(row['hero_id'] for row in result['heroes'])
            after = result['next']
            if not after: break
        self.assertEqual(len(found), 117)
        self.assertEqual(len(set(found)), 117)
        owned = self.service._court_shop(self.actor, {'filter': 'owned'})['heroes']
        self.assertEqual([r['hero_id'] for r in owned], ['abhai'])
        self.assertEqual(self.service._court_shop(self.outsider, {'filter': 'owned'})['heroes'], [])
        self.assertEqual(self.service._court_shop(self.actor, {'q': 'Abhai'})['heroes'][0]['hero_id'], 'abhai')

    def test_inventory_reserve_consume_and_refund_exactly_once(self):
        self.credit(20)
        self.buy('buy_item', item_id='healing_draught', quantity=2)
        for _ in range(2): self.tx('_inventory_hold', self.actor, 'healing_draught', 'battle:one', 'item:one')
        row = self.db.court_inventory.find_one()
        self.assertEqual((row['available'], row['held']), (1, 1))
        self.error('item_limit', lambda: self.tx('_inventory_hold', self.actor, 'healing_draught', 'battle:one', 'item:two'))
        for _ in range(2): self.tx('_inventory_consume', 'item:one', 'verified:stream:1')
        self.error('transaction_conflict', lambda: self.tx('_inventory_consume', 'item:one', 'other:evidence'))
        for _ in range(2): self.tx('_inventory_refund', 'item:one', 'Technical cancellation')
        row = self.db.court_inventory.find_one()
        self.assertEqual((row['available'], row['held']), (2, 0))

    def test_unused_item_release_allows_reselection_with_new_receipt(self):
        self.credit(20)
        for item in ('remedy', 'healing_draught'): self.buy('buy_item', item_id=item, quantity=1)
        self.tx('_inventory_hold', self.actor, 'remedy', 'battle:one', 'item:one')
        self.tx('_inventory_release', 'item:one')
        self.tx('_inventory_release', 'item:one')
        self.tx('_inventory_hold', self.actor, 'healing_draught', 'battle:one', 'item:two')
        self.tx('_inventory_consume', 'item:two', 'verified:stream:1')
        self.error('item_limit', lambda: self.tx('_inventory_hold', self.actor, 'remedy', 'battle:one', 'item:three'))

    def test_item_selection_rejects_unknown_item_and_cross_actor_receipt(self):
        self.credit(20)
        self.buy('buy_item', item_id='remedy', quantity=1)
        for item in (None, [], {}, 'unknown'):
            self.error('invalid_input', lambda: self.tx('_inventory_hold', self.actor, item, 'battle:one', 'item:invalid'))
        self.tx('_inventory_hold', self.actor, 'remedy', 'battle:one', 'item:one')
        self.error('transaction_conflict', lambda: self.tx('_inventory_hold', self.member, 'remedy', 'battle:one', 'item:one'))

    def test_quota_reserves_consumes_and_restores_original_utc_day(self):
        self.now = self.now.replace(hour=23, minute=59)
        original_day = self.now.date().isoformat()
        self.tx('_quota_reserve', 'attack', self.actor, 'trial:one')
        self.tx('_quota_reserve', 'attack', self.actor, 'trial:one')
        self.assertEqual(self.service._quota_public('attack', self.actor)['reserved'], 1)
        self.now += timedelta(minutes=2)
        for _ in range(2): self.tx('_quota_commit', 'trial:one')
        old = self.db.court_quotas.find_one({'day': original_day})
        self.assertEqual((old['reserved'], old['used']), (0, 1))
        self.assertEqual(self.service._quota_public('attack', self.actor)['remaining'], 3)
        for _ in range(2): self.tx('_quota_release', 'trial:one', restore_used=True)
        self.assertEqual(self.db.court_quotas.find_one({'day': original_day})['used'], 0)

    def test_competing_quota_reservations_never_exceed_daily_allowance(self):
        def reserve(index):
            try:
                self.tx('_quota_reserve', 'attack', self.actor, 'trial:' + str(index))
                return 'reserved'
            except DomainError as error: return error.code
        with ThreadPoolExecutor(max_workers=5) as workers: results = list(workers.map(reserve, range(5)))
        self.assertEqual(results.count('reserved'), 3)
        self.assertEqual(results.count('daily_limit'), 2)
        self.assertEqual(self.service._quota_public('attack', self.actor)['remaining'], 0)

    def test_extra_trials_captain_only_maximum_two_and_expire(self):
        self.credit(100, self.team, 'team')
        self.error('forbidden', lambda: self.buy('buy_trial', actor=self.member, kind='attack', account_id=self.member))
        self.error('forbidden', lambda: self.buy('buy_trial', kind='attack', account_id=self.outsider))
        for _ in range(2): self.buy('buy_trial', kind='attack', account_id=self.member)
        self.error('extra_trial_limit', lambda: self.buy('buy_trial', kind='attack', account_id=self.member))
        self.assertEqual(self.service._quota_public('attack', self.member)['remaining'], 5)
        self.assertEqual(self.wallet(self.team, 'team')['available'], 80)
        self.now += timedelta(days=1)
        self.assertEqual(self.service._quota_public('attack', self.member)['remaining'], 3)
        self.buy('buy_trial', kind='plan')
        self.assertEqual(self.service._quota_public('plan', self.team)['remaining'], 4)
        self.assertEqual(self.wallet(self.team, 'team')['available'], 60)

    def test_wallet_history_pages_are_bounded_and_owner_scoped(self):
        for i in range(32):
            self.credit(1, reference='history:' + str(i))
        self.credit(999, self.outsider)
        first = self.service._court_wallet(self.actor, {})
        self.assertEqual(len(first['transactions']), 25)
        second = self.service._court_wallet(self.actor, {'after': first['next']})
        self.assertEqual(len(second['transactions']), 7)
        self.assertEqual(second['next'], '')
        ids = [r['id'] for r in first['transactions'] + second['transactions']]
        self.assertEqual(len(set(ids)), 32)
        self.assertNotIn(self.outsider, str(first) + str(second))
        self.error('invalid_input', lambda: self.service._court_wallet(self.actor, {'after': 'malformed'}))

    def test_campaign_first_scenario_reward_once_across_duplicate_saves(self):
        first = self.tx('_campaign_cash', self.actor, 'campaign:a', 'scenario:1')
        second = self.tx('_campaign_cash', self.actor, 'campaign:a', 'scenario:1')
        self.assertEqual((first['amount'], first['already_awarded']), (25, False))
        self.assertEqual((second['amount'], second['already_awarded']), (25, True))
        self.tx('_campaign_cash', self.actor, 'campaign:a', 'scenario:2')
        self.assertEqual(self.wallet()['available'], 50)

    def test_battle_rewards_daily_cap_duplicate_and_opponent_limit(self):
        opponent = str(uuid4())
        result = self.tx('_battle_cash', self.actor, 'battle:one', 'win', mode='plan', opponent_team_id=opponent)
        self.assertEqual(result['amount'], 10)
        self.assertTrue(self.tx('_battle_cash', self.actor, 'battle:one', 'win', mode='plan', opponent_team_id=opponent)['already_awarded'])
        self.error('transaction_conflict', lambda: self.tx('_battle_cash', self.actor, 'battle:one', 'loss', mode='plan', opponent_team_id=opponent))
        self.assertEqual(self.tx('_battle_cash', self.actor, 'battle:two', 'win', mode='plan', opponent_team_id=opponent)['amount'], 0)
        self.assertEqual(self.tx('_battle_cash', self.actor, 'battle:draw', 'draw', mode='normal')['amount'], 5)
        for i in range(5): self.tx('_battle_cash', self.actor, 'battle:normal:' + str(i), 'win', mode='normal')
        self.assertEqual(self.wallet()['available'], 50)
        self.now += timedelta(days=1)
        self.assertEqual(self.tx('_battle_cash', self.actor, 'battle:newday', 'win', mode='plan', opponent_team_id=opponent)['amount'], 10)

    def test_simultaneous_battle_cash_and_story_cash_preserve_cap_and_total(self):
        self.credit(0)
        def award(index):
            if index == 8: return self.tx('_campaign_cash', self.actor, 'campaign:one', 'scenario:one')
            return self.tx('_battle_cash', self.actor, 'battle:concurrent:' + str(index), 'win', mode='normal')
        with ThreadPoolExecutor(max_workers=9) as workers: list(workers.map(award, range(9)))
        self.assertEqual(self.wallet()['available'], 75)
        total = sum(r['amount'] for r in self.db.court_reward_claims.find({'kind': 'battle'}))
        self.assertEqual(total, 50)

    def test_strict_record_validation_rejects_negative_balance_or_unknown_fields(self):
        self.credit(10)
        for update in ({'available': -1}, {'held': 0.5}, {'unexpected_private_field': 'x'}, {'available': MAX_CROWNS + 1}):
            with self.assertRaises(WriteError):
                self.db.court_wallets.update_one({'owner_id': self.actor}, {'$set': update})
        self.assertEqual(self.wallet()['available'], 10)

    def test_generation_mismatch_rejected_without_funds_or_inventory_change(self):
        self.credit(20)
        self.buy('buy_item', item_id='remedy', quantity=1)
        self.db.schema_metadata.update_one({'_id': 'alliance'}, {'$set': {'database_generation': str(uuid4())}})
        self.error('generation_changed', lambda: self.wallet())
        self.error('account_unavailable', lambda: self.buy('buy_item', item_id='remedy', quantity=1))
        self.assertEqual(self.db.court_wallets.find_one()['available'], 15)
        self.assertEqual(self.db.court_inventory.find_one()['available'], 1)

    def test_dispatch_allowlists_reject_credit_and_admin_review_on_player_path(self):
        for operation in ('credit', 'wallet_credit', 'approve_cash', 'refund', '_wallet_credit'):
            self.error('unsupported_command', lambda: self.service.court_command(self.actor,
                {'version': 1, 'operation': operation, 'payload': {'command_id': str(uuid4()), 'amount': 1000}}))
        self.error('unsupported_protocol', lambda: self.service.court_command(self.actor,
            {'version': True, 'operation': 'request_cash', 'payload': {'command_id': str(uuid4())}}))
        self.assertEqual(self.db.court_wallets.count_documents({}), 0)
        result = self.service.court_query(self.actor, {'version': 1, 'query': 'wallet'})
        self.assertEqual(result['actor_id'], self.actor)
        self.assertEqual(result['data']['wallet']['available'], 0)

    def test_simultaneous_initial_credits_create_one_wallet_without_losing_funds(self):
        def grant(index):
            return self.credit(10, reference='initial:race:' + str(index))
        with ThreadPoolExecutor(max_workers=6) as workers:
            list(workers.map(grant, range(6)))
        self.assertEqual(self.wallet()['available'], 60)
        self.assertEqual(self.db.court_wallets.count_documents({}), 1)
        self.assertEqual(self.db.court_ledger.count_documents({}), 6)

    def test_simultaneous_same_hero_purchase_charges_only_one(self):
        self.credit(200)
        def purchase(_):
            try:
                self.buy('buy_hero', hero_id='abhai')
                return 'purchased'
            except DomainError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(purchase, range(2)))
        self.assertEqual(sorted(results), ['hero_already_owned', 'purchased'])
        self.assertEqual(self.wallet()['available'], 100)
        self.assertEqual(self.db.account_heroes.count_documents({}), 1)

    def test_story_unlock_racing_shop_purchase_preserves_progress_and_no_duplicate(self):
        self.credit(200)
        catalog, catalog_hash = load_catalog()
        campaign = next(c for c in catalog['campaigns'] if c['aliases'])
        alias = campaign['aliases'][0]
        hero, form = alias['hero_id'], alias['forms'][0]['form_id']
        run = self.service.story_begin(self.actor, campaign['id'], catalog['version'], catalog_hash)
        checkpoint = {'run_id': run['run_id'], 'checkpoint_id': str(uuid4()), 'sequence': 0,
            'scenario_id': campaign['first_scenario'], 'next_scenario_id': '', 'outcome': 'win',
            'nonce': run['nonce'], 'replay_sha256': 'a' * 64,
            'heroes': [{'hero_id': hero, 'unit_id': alias['unit_id'], 'form_id': form,
                        'unlocked_forms': [form], 'earned_experience': 7}]}
        def action(kind):
            if kind == 'story':
                return self.service.story_checkpoint(self.actor, checkpoint)
            try:
                return self.buy('buy_hero', hero_id=hero)
            except DomainError as error:
                self.assertEqual(error.code, 'hero_already_owned')
                return None
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(action, ['story', 'shop']))
        row = self.db.account_heroes.find_one({'account_id': self.actor, 'hero_id': hero})
        self.assertEqual(row['total_experience'], 27)
        self.assertIn(form, row['forms'])
        self.assertEqual(self.db.account_heroes.count_documents({'account_id': self.actor, 'hero_id': hero}), 1)
        self.assertEqual(self.wallet()['available'], 225 - (100 if results[1] else 0))
        self.assertEqual(results[0]['cash_reward']['amount'], 25)
        self.assertEqual(self.service.story_checkpoint(self.actor, checkpoint), results[0])
