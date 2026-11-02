"""Court lifecycle verification in a disposable MongoDB replica set only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import unittest
from uuid import uuid4

import test_unified_product as fixture
from alliance.court.base import PRICES, LIMITS, public_command_receipt
from alliance.court.battles import DEFAULT_BATTLE_SETTINGS, settings, seeded_bracket, tournament_score
from alliance.court.schema import SCHEMAS
from alliance.court.wallet_schema import SCHEMAS as WALLETS, bootstrap_indexes as wallet_indexes
from alliance.court.battle_schema import SCHEMAS as BATTLES, bootstrap_indexes as battle_indexes
from alliance.court.service import CourtService
from alliance.domain import DomainError
from alliance.heroes import load_catalog


class CourtBattleRules(unittest.TestCase):
    def test_legacy_receipt_adapter_changes_only_battle_summary_line_breaks(self):
        saved = {'version': 1, 'actor_id': 'actor', 'data': {'match': {
            'id': 'battle', 'description': 'Cancelled.\r\nNo rewards.\rFee refunded.\nTrial retained.',
            'agreed_fee': 5, 'result': {'description': 'Unrelated\nfield', 'amount': 5}},
            'other_description': 'Unrelated\ntext'}}
        before = deepcopy(saved)
        expected = deepcopy(saved)
        expected['data']['match']['description'] = 'Cancelled. No rewards. Fee refunded. Trial retained.'
        self.assertEqual(public_command_receipt(saved), expected)
        self.assertEqual(saved, before)

    def test_exact_settings_and_boolean_types(self):
        self.assertEqual(settings(DEFAULT_BATTLE_SETTINGS), DEFAULT_BATTLE_SETTINGS)
        for change in ({'size': True}, {'gold': 101}, {'base_income': 21}, {'hero_cap': 10},
                       {'map_id': {}}, {'command_id': str(uuid4())}, {'fog': 1}):
            with self.assertRaises(DomainError):
                settings({**DEFAULT_BATTLE_SETTINGS, **change})

    def test_balanced_brackets_every_supported_capacity(self):
        for size in range(2, 33):
            teams = [str(uuid4()) for _ in range(size)]
            first = seeded_bracket(teams, 'a' * 64)
            self.assertEqual(first, seeded_bracket(list(reversed(teams)), 'a' * 64))
            self.assertEqual(sorted(team for pair in first for team in pair if team), sorted(teams))
            self.assertTrue(all(len(pair) == 2 and pair[0] for pair in first))
            self.assertEqual(sum(pair[1] is None for pair in first), (1 << (size - 1).bit_length()) - size)

    def test_tie_break_lexicographic_and_committed_draw(self):
        teams = ['a', 'b']
        scores = [{'team_id': t, 'leaders': 1, 'villages': 3, 'unit_value_hp': 100, 'gold': 9} for t in teams]
        first = tournament_score(scores, teams, seed='a' * 64, match_id='test')
        self.assertEqual(first, tournament_score(scores, teams, seed='a' * 64, match_id='test'))
        self.assertEqual(first[1], 'recorded_draw')
        scores[0]['leaders'] = 2
        scores[1]['gold'] = 99999
        self.assertEqual(tournament_score(scores, teams, seed='a' * 64, match_id='test'), ('a', 'objective_score'))


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable local replica set')
class CourtBattles(unittest.TestCase):
    setUpClass = classmethod(fixture.UnifiedProduct.setUpClass.__func__)
    tearDownClass = classmethod(fixture.UnifiedProduct.tearDownClass.__func__)
    code = fixture.UnifiedProduct.code

    def setUp(self):
        self.name = 'alliance_test_' + uuid4().hex
        self.db = self.client[self.name]
        for name, schema in {**SCHEMAS, **WALLETS, **BATTLES}.items():
            self.db.create_collection(name, validator=schema)
        wallet_indexes(self.db)
        battle_indexes(self.db)
        self.db.account_heroes.create_index([('account_id', 1), ('hero_id', 1)], unique=True)
        self.now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        self.generation = str(uuid4())
        self.db.schema_metadata.insert_one({'_id': 'alliance', 'version': 5,
            'database_generation': self.generation, 'court_initialized': True})
        self.db.court_settings.insert_one({'_id': 'rules', 'revision': 0,
            'prices': deepcopy(PRICES), 'limits': deepcopy(LIMITS)})
        self.db.court_settings.insert_one({'_id': 'population', 'revision': 0})
        self.db.court_areas.insert_one(dict(_id='A001', name='Area', number=1,
            enabled=True, mode='on', team_count=2, revision=0))
        for number, role in [(1, 'normal'), (2, 'normal'), (3, 'normal'), (4, 'normal'),
                             (10, 'plan'), (28, 'competition')]:
            self.db.court_castles.insert_one(dict(_id=f'A001-C{number:03}', area_id='A001',
                name=role, role=role, enabled=True, mode='on', owner_team_id=None,
                reservation_id=None, event_id=None, protected_until=None, revision=0))
        self.domain = CourtService(self.db, clock=lambda: self.now)
        self.catalog, _ = load_catalog()
        form = next(row for row in self.catalog['forms'] if row['native_level'] == 1 and row['source_type'] == 'Spearman')
        self.hero, self.form = form['hero_id'], form['id']
        self.a, self.b, self.admin = self.player(), self.player(), self.player(admin=True)
        self.ta, self.tb = self.team(self.a, 'First'), self.team(self.b, 'Second')

    def tearDown(self):
        self.client.drop_database(self.name)

    def player(self, admin=False):
        actor = str(uuid4())
        self.db.accounts.insert_one(dict(_id=actor, username=actor[:8], username_key=actor[:8],
            password_hash='$argon2id$test', role='admin' if admin else 'player', status='active',
            database_generation=self.generation, active_run_id=None, revision=0))
        if not admin:
            self.db.account_heroes.insert_one(dict(_id=str(uuid4()), account_id=actor,
                hero_id=self.hero, forms=[self.form], total_experience=0, revision=0))
        return actor

    def team(self, actor, name):
        tid = str(uuid4())
        self.db.court_teams.insert_one(dict(_id=tid, name=name, name_key=name.lower(),
            area_id='A001', captain_id=actor, members=[{'account_id': actor, 'joined_at': self.now}],
            status='active', experience=0, level=1, revision=0, allowances={}))
        self.domain._tx(lambda s: self.domain._wallet_credit('team', tid, 1000, 'fixture:' + tid, 'fixture', s))
        return tid

    def command(self, actor, op, **payload):
        payload.setdefault('command_id', str(uuid4()))
        if op in ('attack', 'create_plan', 'approve_plan', 'enter_competition', 'request_attack_approval'):
            payload.setdefault('price_revision', 0)
        if 'match_id' in payload:
            payload.setdefault('expected_revision', self.match(payload['match_id'])['revision'])
        if 'competition_id' in payload:
            payload.setdefault('expected_revision', self.db.court_competitions.find_one({'_id': payload['competition_id']})['revision'])
        fn = self.domain.court_admin_command if op.startswith('admin_') else self.domain.court_command
        if op.startswith('admin_'):
            payload.setdefault('reason', 'Disposable fixture review')
            payload.setdefault('confirmation', 'confirmed')
        return fn(actor, {'version': 1, 'operation': op, 'payload': payload})['data']

    def match(self, run):
        return self.db.court_matches.find_one({'_id': run})

    def attack(self, castle='A001-C001'):
        return self.command(self.a, 'attack', castle_id=castle,
            expected_revision=self.db.court_castles.find_one({'_id': castle})['revision'],
            hero_id=self.hero, form_id=self.form, faction='Loyalists')['match']['id']

    def plan(self, items=False):
        run = self.command(self.a, 'create_plan', castle_id='A001-C010', opponent_team_id=self.tb,
            settings={**deepcopy(DEFAULT_BATTLE_SETTINGS), 'items': items}, start_delay_minutes=5)['match']['id']
        self.command(self.b, 'approve_plan', match_id=run)
        return run

    def ready(self, actor, run):
        self.command(actor, 'join_match', match_id=run)
        self.command(actor, 'select_hero', match_id=run, hero_id=self.hero, form_id=self.form, faction='Loyalists')
        self.command(actor, 'ready', match_id=run, ready=True)

    def load(self, run):
        # Joining the second participant invalidates the first participant's
        # readiness. Both explicitly re-consent to the completed lineup.
        for seat in self.match(run)['seats']:
            if seat['controller'] == 'human' and seat.get('selection') and not seat['ready']:
                self.command(seat['account_id'], 'ready', match_id=run, ready=True)
        if self.match(run)['state'] == 'scheduled':
            self.now += timedelta(minutes=6)
            self.domain.court_tick()
        self.domain.court_capacity_available('native_worker_test')
        desc = self.domain.court_worker_acquire('native_worker_test')
        self.assertEqual(desc['run_id'], run)
        self.domain.court_worker_loaded(run, 'native_worker_test', desc['generation'], 'a' * 64)
        for actor in desc['required_humans']:
            self.domain.court_human_join(actor, run)
            result = self.domain.court_human_loaded(actor, run, desc['generation'], 'a' * 64)
        self.assertEqual(result['state'], 'running')
        return desc

    def evidence(self, desc, winner=None):
        return dict(scenario_sha256='a' * 64, replay_sha256='b' * 64, ledger_sha256='c' * 64,
            command_chain_sha256='d' * 64, event_count=3, terminal='victory', outcome='win',
            winner_team_id=winner or desc['sides'][0]['team_id'], units=[], sync_valid=True,
            combat_verified=True, completed_rounds=2)

    def finish(self, desc, evidence=None):
        return self.domain.court_worker_finish(desc['run_id'], 'native_worker_test', desc['generation'], evidence or self.evidence(desc))

    def test_attack_cost_held_until_all_native_load_then_settle_once(self):
        self.now += timedelta(microseconds=193)
        run = self.attack()
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 5)
        self.assertEqual(self.db.court_quotas.find_one()['reserved'], 1)
        desc = self.load(run)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 0)
        self.assertEqual(self.db.court_quotas.find_one()['used'], 1)
        before = self.db.account_heroes.find_one({'account_id': self.a})['total_experience']
        receipt = self.finish(desc)
        self.assertEqual(self.finish(desc), receipt)
        self.assertEqual(self.db.account_heroes.find_one({'account_id': self.a})['total_experience'], before + 20)
        castle = self.db.court_castles.find_one({'_id': 'A001-C001'})
        self.assertEqual(castle['owner_team_id'], self.ta)
        self.assertEqual(castle['protected_until'], (self.now + timedelta(hours=1)).replace(
            microsecond=self.now.microsecond // 1000 * 1000))
        self.assertEqual(self.db.network_battle_reservations.count_documents({}), 0)
        self.assertEqual(self.domain._wallet_public('personal', self.a)['available'], 10)

    def test_selected_item_requires_witness_owner_turn_and_once(self):
        run = self.plan(items=True)
        self.ready(self.a, run)
        self.ready(self.b, run)
        self.domain._tx(lambda s: self.domain._inventory_mutate(self.a, 'healing_draught', 2, 0, s))
        self.command(self.a, 'select_item', match_id=run, item_id='healing_draught')
        self.assertFalse(next(s for s in self.match(run)['seats'] if s['account_id'] == self.a)['ready'])
        desc = self.load(run)
        seat = next(s for s in desc['sides'] if s['account_id'] == self.a)
        self.assertEqual(seat['item_id'], 'healing_draught')
        proof = dict(account_id=self.a, side=seat['side'], turn_side=seat['side'],
            item_id='healing_draught', command_sha256='e' * 64, applied=True)
        call = lambda p: self.domain.court_worker_item(run, 'native_worker_test', desc['generation'], p)
        self.code('invalid_evidence', lambda: call({**proof, 'turn_side': 2}))
        self.code('invalid_evidence', lambda: call({**proof, 'account_id': self.b}))
        self.code('invalid_evidence', lambda: call({**proof, 'applied': False}))
        self.assertEqual(call(proof), call(proof))
        self.code('transaction_conflict', lambda: call({**proof, 'command_sha256': 'f' * 64}))
        self.finish(desc)
        item = self.db.court_inventory.find_one({'account_id': self.a, 'item_id': 'healing_draught'})
        self.assertEqual((item['available'], item['held']), (1, 0))

    def test_unused_item_cancel_and_technical_consumed_item_refund(self):
        run = self.plan(items=True)
        self.ready(self.a, run)
        self.ready(self.b, run)
        self.domain._tx(lambda s: self.domain._inventory_mutate(self.a, 'remedy', 1, 0, s))
        self.command(self.a, 'select_item', match_id=run, item_id='remedy')
        self.command(self.a, 'select_item', match_id=run, item_id='')
        self.assertEqual(self.db.court_inventory.find_one({'account_id': self.a})['available'], 1)
        self.command(self.a, 'select_item', match_id=run, item_id='remedy')
        desc = self.load(run)
        self.domain.court_worker_item(run, 'native_worker_test', desc['generation'], dict(
            account_id=self.a, side=1, turn_side=1, item_id='remedy', command_sha256='f' * 64, applied=True))
        self.domain._tx(lambda s: self.domain._battle_cancel(self.match(run), 'infrastructure_failure', s, technical=True))
        item = self.db.court_inventory.find_one({'account_id': self.a})
        self.assertEqual((item['available'], item['held']), (1, 0))
        self.assertEqual(self.db.court_item_holds.count_documents({'state': 'refunded'}), 1)

    def test_suspended_ready_player_does_not_stop_other_scheduler_work(self):
        run = self.plan()
        self.ready(self.a, run)
        self.ready(self.b, run)
        self.command(self.a, 'ready', match_id=run, ready=True)
        self.db.accounts.update_one({'_id': self.a}, {'$set': {'status': 'suspended'}})
        self.now += timedelta(minutes=6)
        self.domain.court_tick()
        self.domain.court_capacity_available('native_worker_test')
        self.assertIsNone(self.domain.court_worker_acquire('native_worker_test'))
        self.assertFalse(next(s for s in self.match(run)['seats'] if s['account_id'] == self.a)['ready'])

    def test_history_after_leaving_and_unrelated_replay_hidden(self):
        desc = self.load(self.attack())
        self.finish(desc)
        self.db.court_teams.update_one({'_id': self.ta}, {'$set': {'members': []}})
        rows = self.domain._court_history_matches(self.a)['matches']
        self.assertEqual([r['id'] for r in rows], [desc['run_id']])
        self.assertTrue(rows[0]['replay_available'])
        self.db.court_castles.update_one({'_id': 'A001-C001'}, {'$set': {'enabled': False}})
        historical = self.domain._court_matches_query(self.a, {'state': 'history', 'castle_id': 'A001-C001'})
        self.assertEqual([row['id'] for row in historical['matches']], [desc['run_id']])
        self.assertEqual(self.domain._court_history_matches(self.b)['matches'], [])
        self.assertFalse(self.domain._court_match_public(self.match(desc['run_id']), self.b)['replay_available'])

    def test_public_match_description_uses_actual_receipt_without_changing_contract(self):
        run = self.attack()
        active = self.domain._court_match_public(self.match(run), self.a)
        self.assertEqual(active['settings']['map_name'], 'Weldyn Channel')
        self.assertNotIn('map_name', self.match(run)['settings'])
        self.assertIn('Waiting for', active['description'])
        desc = self.load(run)
        self.assertNotIn('map_name', desc['settings'])
        self.finish(desc)
        completed = self.domain._court_match_public(self.match(run), self.a)
        for private_field in ('generation', 'evidence_digest', 'replay_sha256', 'scores'):
            self.assertNotIn(private_field, completed['result'])
        self.assertIn('replay_sha256', self.match(run)['result'])
        self.assertIn('First won.', completed['description'])
        self.assertIn('Your hero: +20 XP · +10 Crowns.', completed['description'])
        self.assertIn('First: +100 Team XP.', completed['description'])
        self.assertIn('normal captured by First.', completed['description'])
        for private in (run, self.a, self.ta, self.generation, 'b' * 64):
            self.assertNotIn(private, completed['description'])
        outsider = self.domain._court_match_public(self.match(run), self.b)
        self.assertNotIn('Your hero:', outsider['description'])
        self.assertFalse(outsider['replay_available'])
        history = self.domain.court_query(self.a, {'version': 1, 'query': 'history'})['data']
        self.assertEqual(history['items'][0]['description'], completed['description'])
        self.assertNotIn('data', history['items'][0])

    def test_public_draw_and_technical_cancellation_are_distinct(self):
        desc = self.load(self.attack())
        self.finish(desc, {**self.evidence(desc), 'terminal': 'draw', 'outcome': 'draw', 'winner_team_id': None})
        draw = self.domain._court_match_public(self.match(desc['run_id']), self.a)
        self.assertIn('Draw.', draw['description'])
        self.assertIn('Your hero: +10 XP · +5 Crowns.', draw['description'])
        self.assertIn('Castle ownership unchanged.', draw['description'])
        run = self.attack('A001-C002')
        result = self.command(self.admin, 'admin_cancel_match', match_id=run,
                              reason='Private operator diagnosis must remain in audit only')
        description = result['match']['description']
        self.assertIn('Technical cancellation.', description)
        self.assertIn('No rewards or Castle ownership change.', description)
        self.assertNotIn('Private operator', description)
        self.assertNotIn(run, description)
        self.assertNotIn('Your hero:', description)

    def test_settled_battles_remain_readable_in_all_mobile_projections(self):
        """Terminal descriptions must survive the strict native string boundary."""
        completed = self.attack()
        self.finish(self.load(completed))
        cancelled = self.attack('A001-C002')
        cancellation = self.command(self.admin, 'admin_cancel_match', match_id=cancelled)

        def assert_native_strings(value, path='response'):
            if isinstance(value, str):
                self.assertFalse(any(ord(char) < 32 or ord(char) == 127 for char in value), path)
            elif isinstance(value, dict):
                for key, item in value.items():
                    assert_native_strings(key, path + '.key')
                    assert_native_strings(item, path + '.' + key)
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    assert_native_strings(item, f'{path}[{index}]')

        assert_native_strings(cancellation)
        for query, payload in (
                ('plan', {'match_id': completed}),
                ('plan', {'match_id': cancelled}),
                ('castle', {'castle_id': 'A001-C001'}),
                ('castle', {'castle_id': 'A001-C002'}),
                ('plans', {'state': 'history'}),
                ('history', {}),
                ('notifications', {})):
            with self.subTest(query=query, payload=payload):
                response = self.domain.court_query(self.a, {'version': 1,
                    'query': query, 'payload': payload})
                assert_native_strings(response)
        won = self.domain._court_match_public(self.match(completed), self.a)
        self.assertIn('First won.', won['description'])
        self.assertIn('Your hero: +20 XP · +10 Crowns.', won['description'])
        self.assertIn('normal captured by First.', won['description'])
        self.assertTrue(won['replay_available'])
        self.assertIn('Technical cancellation.', cancellation['match']['description'])
        self.assertIn('No rewards or Castle ownership change.', cancellation['match']['description'])

    def test_legacy_command_receipt_status_and_retry_preserve_stored_result_and_balances(self):
        run = self.attack()
        command_id = str(uuid4())
        payload = {'command_id': command_id, 'match_id': run,
                   'expected_revision': self.match(run)['revision']}
        request = {'version': 1, 'operation': 'cancel_attack', 'payload': payload}
        original = self.domain.court_command(self.a, request)
        legacy = deepcopy(original)
        legacy['data']['match']['description'] = (
            'Cancelled by a participant.\n'
            'No rewards or Castle ownership change. Battle fees released or refunded.')
        key = self.generation + ':' + self.a + ':' + command_id
        self.db.court_commands.update_one({'_id': key}, {'$set': {'result': legacy}})
        before = {name: list(self.db[name].find().sort('_id', 1))
                  for name in self.db.list_collection_names() if not name.startswith('system.')}

        status = self.domain.court_query(self.a, {'version': 1, 'query': 'command_status',
            'payload': {'command_id': command_id}})['data']
        self.assertTrue(status['found'])
        self.assertEqual(status['receipt'], original)
        self.assertEqual(self.domain.court_command(self.a, request), original)
        self.assertEqual(self.db.court_commands.find_one({'_id': key})['result'], legacy)
        after = {name: list(self.db[name].find().sort('_id', 1))
                 for name in self.db.list_collection_names() if not name.startswith('system.')}
        self.assertEqual(after, before)

    def test_history_descriptions_resolve_changes_and_prizes_without_private_data(self):
        event = {'team_created': {'area_id': 'A001'},
                 'renamed': {'previous_name': 'Old name', 'name': 'New name'},
                 'member_joined': {'account_id': self.a},
                 'castle_abandoned': {'castle_id': 'A001-C001'},
                 'relocated': {'from_area': 'A001', 'area_id': 'A001'},
                 'competition': {'competition_id': str(uuid4()), 'winner_team_id': self.ta,
                                 'prizes': [{'team_id': self.ta, 'amount': 14}, {'team_id': self.tb, 'amount': 6}]}}
        for kind, data in event.items():
            self.domain._tx(lambda s, k=kind, d=data: self.domain._history(self.ta, k, 'Recorded change',
                {**d, 'private_note': 'never display this private diagnostic'}, s))
        rows = self.domain.court_query(self.a, {'version': 1, 'query': 'history'})['data']['items']
        for row in rows:
            self.assertNotIn('data', row)
            self.assertEqual(set(row), {'id', 'kind', 'title', 'description', 'created_at'})
        descriptions = {row['kind']: row['description'] for row in rows}
        self.assertEqual(descriptions['team_created'], 'Team created in Area.')
        self.assertEqual(descriptions['renamed'], 'Team renamed from Old name to New name.')
        self.assertIn('joined the Team.', descriptions['member_joined'])
        self.assertEqual(descriptions['castle_abandoned'], 'normal returned to neutral ownership.')
        self.assertEqual(descriptions['relocated'], 'Home moved from Area to Area.')
        self.assertEqual(descriptions['competition'], 'Competition: First won. Your Team prize: 14 Crowns from the entry pool.')
        for description in descriptions.values():
            for private in (self.a, self.ta, 'A001', 'never display this private diagnostic'):
                self.assertNotIn(private, description)
        self.code('forbidden', lambda: self.domain.court_query(self.b,
            {'version': 1, 'query': 'history', 'payload': {'team_id': self.ta}}))

    def test_concurrent_castle_claim_only_one_payment_and_claim(self):
        def attack(_):
            try: return self.attack()
            except DomainError as error: return error.code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attack, range(2)))
        self.assertEqual(self.db.court_matches.count_documents({}), 1)
        self.assertEqual(self.db.court_castle_claims.count_documents({}), 1)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 5)
        self.assertEqual(sum(len(result) == 36 for result in results), 1)

    def test_capacity_reserves_last_castle_slot(self):
        self.db.court_castles.update_many({'_id': {'$in': ['A001-C002', 'A001-C003']}},
            {'$set': {'owner_team_id': self.ta, 'owned_at': self.now}})
        self.attack()
        other = self.player()
        self.db.court_teams.update_one({'_id': self.ta}, {'$push': {'members': {'account_id': other, 'joined_at': self.now}}})
        self.code('castle_capacity', lambda: self.command(other, 'attack', castle_id='A001-C004', expected_revision=0,
            hero_id=self.hero, form_id=self.form, faction='Loyalists'))

    def test_protection_and_human_response_fallback(self):
        self.db.court_castles.update_one({'_id': 'A001-C001'}, {'$set': {
            'owner_team_id': self.tb, 'owned_at': self.now, 'protected_until': self.now + timedelta(hours=1)}})
        self.code('protected', self.attack)
        self.now += timedelta(hours=1)
        run = self.attack()
        self.assertEqual(self.match(run)['state'], 'response')
        self.now += timedelta(seconds=121)
        self.domain.court_tick()
        self.assertEqual(self.match(run)['seats'][1]['controller'], 'worker')
        self.assertEqual(self.match(run)['state'], 'queued')

    def test_defense_owner_consent_withdraw_does_not_change_committed_snapshot(self):
        offered = self.command(self.b, 'defense_consent', hero_id=self.hero, form_id=self.form,
                               faction='Rebels', confirmed=True)['defense']
        did = offered.get('id', offered.get('_id'))
        self.command(self.b, 'set_defense', defense_id=did, expected_revision=0, confirmed=True)
        self.db.court_castles.update_one({'_id': 'A001-C001'}, {'$set': {'owner_team_id': self.tb}})
        run = self.attack()
        saved = deepcopy(self.match(run)['defense_template'])
        self.command(self.b, 'withdraw_defense', defense_id=did, expected_revision=1)
        self.assertEqual(self.match(run)['defense_template'], saved)
        self.assertEqual(self.domain._tx(lambda s: self.domain._battle_defense(self.tb, s))['kind'], 'standard_garrison')

    def test_plan_acceptance_clock_fee_quota_and_future_seat(self):
        run = self.plan()
        self.assertEqual(self.match(run)['scheduled_at'], self.now + timedelta(minutes=5))
        self.assertEqual(self.db.court_quotas.find_one()['used'], 1)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 10)
        self.ready(self.a, run)
        second = self.plan()
        self.code('already_joined', lambda: self.command(self.a, 'join_match', match_id=second))
        self.command(self.a, 'cancel_plan', match_id=run)
        self.assertEqual(self.db.court_quotas.find_one()['used'], 2)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 10)

    def test_proposal_expiration_releases_money_without_trial(self):
        run = self.command(self.a, 'create_plan', castle_id='A001-C010', opponent_team_id=self.tb,
            settings=deepcopy(DEFAULT_BATTLE_SETTINGS), start_delay_minutes=5)['match']['id']
        self.now += timedelta(minutes=11)
        self.domain.court_tick()
        self.assertEqual(self.match(run)['state'], 'cancelled')
        self.assertEqual(self.domain._wallet_public('team', self.ta)['available'], 1000)
        self.assertEqual(self.db.court_quotas.count_documents({}), 0)

    def test_no_worker_capacity_cancels_plan_and_restores_used_trial(self):
        run = self.plan()
        self.now += timedelta(minutes=6)
        self.domain.court_tick()
        self.now += timedelta(minutes=11)
        self.domain.court_tick()
        self.assertEqual(self.match(run)['cancel_reason'], 'worker_capacity_timeout')
        self.assertEqual(self.db.court_quotas.find_one()['used'], 0)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['available'], 1000)

    def test_no_infrastructure_forfeit_on_lost_capacity(self):
        run = self.plan()
        self.now += timedelta(minutes=6)
        self.domain.court_tick()
        self.domain.court_capacity_available('native_worker_test')
        self.now += timedelta(hours=2)
        self.domain.court_tick()
        self.assertEqual(self.match(run)['state'], 'queued')
        self.assertEqual(self.db.court_battle_receipts.count_documents({}), 0)
        self.domain.court_capacity_available('native_worker_test')
        self.assertGreater(self.match(run)['attendance_until'], self.now)

    def test_story_increment_and_concurrent_terminal_preserve_both(self):
        run = self.plan()
        self.ready(self.a, run)
        self.ready(self.b, run)
        desc = self.load(run)
        self.db.account_heroes.update_one({'account_id': self.a}, {'$inc': {'total_experience': 17, 'revision': 1}})
        with ThreadPoolExecutor(2) as pool:
            receipts = list(pool.map(lambda _: self.finish(desc), range(2)))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.db.account_heroes.find_one({'account_id': self.a})['total_experience'], 37)
        self.assertEqual(self.db.account_heroes.find_one({'account_id': self.b})['total_experience'], 10)
        self.assertEqual(self.db.court_teams.find_one({'_id': self.ta})['experience'], 100)
        changed = self.evidence(desc, self.tb)
        self.code('result_conflict', lambda: self.finish(desc, changed))

    def test_mismatched_load_disputes_without_awards(self):
        run = self.attack()
        self.domain.court_capacity_available('native_worker_test')
        desc = self.domain.court_worker_acquire('native_worker_test')
        self.domain.court_worker_loaded(run, 'native_worker_test', desc['generation'], 'a' * 64)
        result = self.domain.court_human_loaded(self.a, run, desc['generation'], 'f' * 64)
        self.assertEqual(result['state'], 'disputed')
        self.assertEqual(self.domain._wallet_public('team', self.ta)['held'], 5)
        self.assertEqual(self.db.court_battle_receipts.count_documents({}), 0)

    def test_worker_failure_never_awards_and_reconnect_keeps_generation(self):
        run = self.attack()
        desc = self.load(run)
        self.domain.court_worker_pause(run, 'native_worker_test', desc['generation'])
        self.now += timedelta(hours=5)
        self.domain.court_tick()
        self.assertEqual(self.match(run)['state'], 'paused')
        resumed = self.domain.court_worker_acquire('native_worker_restarted')
        self.assertEqual(resumed['generation'], desc['generation'])
        self.assertEqual(resumed['descriptor_sha256'], desc['descriptor_sha256'])
        self.assertEqual(self.db.court_battle_receipts.count_documents({}), 0)

    def test_castle_income_current_day_exact_once_and_owner_change(self):
        self.db.court_castles.update_one({'_id': 'A001-C001'}, {'$set': {
            'owner_team_id': self.ta, 'owned_at': self.now - timedelta(hours=2)}})
        self.assertEqual(len(self.domain.court_castle_income()['payments']), 1)
        self.assertEqual(self.domain.court_castle_income()['payments'], [])
        self.db.court_castles.update_one({'_id': 'A001-C001'}, {'$set': {'owner_team_id': self.tb}})
        self.assertEqual(self.domain.court_castle_income()['payments'], [])
        self.now += timedelta(days=7)
        self.assertEqual(len(self.domain.court_castle_income()['payments']), 1)
        self.assertEqual(self.domain._wallet_public('team', self.tb)['available'], 1005)

    def test_replay_authorized_for_recorded_participant_after_departure(self):
        run = self.attack()
        desc = self.load(run)
        self.finish(desc)
        self.db.court_teams.update_one({'_id': self.ta}, {'$set': {'members': []}})
        self.assertEqual(self.domain.court_replay_authorize(self.a, run)['replay_sha256'], 'b' * 64)
        self.code('forbidden', lambda: self.domain.court_replay_authorize(self.b, run))

    def competition(self, count=2):
        event = self.command(self.admin, 'admin_create_competition', castle_id='A001-C028',
            expected_revision=self.db.court_castles.find_one({'_id': 'A001-C028'})['revision'], name='Cup',
            settings=deepcopy(DEFAULT_BATTLE_SETTINGS), entry_fee=11)['competition']['id']
        actors = [self.a, self.b]
        for number in range(count - 2):
            player = self.player()
            self.team(player, 'Extra' + str(number))
            actors.append(player)
        for actor in actors:
            self.command(actor, 'enter_competition', competition_id=event)
        return event, actors

    def test_competition_lock_round_native_final_pool_rounding(self):
        event, actors = self.competition()
        self.command(self.admin, 'admin_lock_competition', competition_id=event)
        row = self.db.court_competitions.find_one({'_id': event})
        run = row['rounds'][0]['matches'][0]['match_id']
        for actor in actors:
            self.ready(actor, run)
        self.assertIsNone(self.match(run)['scheduled_at'])
        self.command(self.admin, 'admin_start_round', competition_id=event)
        desc = self.load(run)
        self.finish(desc, self.evidence(desc, self.ta))
        row = self.db.court_competitions.find_one({'_id': event})
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['prizes'], [{'team_id': self.ta, 'amount': 15}, {'team_id': self.tb, 'amount': 7}])
        self.assertEqual(self.domain._wallet_public('team', self.ta)['available'], 1004)
        self.assertEqual(self.domain._wallet_public('team', self.tb)['available'], 996)

    def test_cancel_locked_competition_refunds_entries_no_mint(self):
        event, _ = self.competition(3)
        self.command(self.admin, 'admin_lock_competition', competition_id=event)
        self.command(self.admin, 'admin_cancel_competition', competition_id=event, reason='Host cancelled')
        self.assertEqual(self.domain._wallet_public('team', self.ta)['available'], 1000)
        self.assertEqual(self.db.court_competitions.find_one({'_id': event})['state'], 'cancelled')
        self.assertEqual(self.db.court_matches.count_documents({'state': 'cancelled'}), 1)

    def test_admin_cancel_started_match_refunds_and_fences_only_selected_run(self):
        first = self.attack()
        desc = self.load(first)
        other = self.player()
        self.db.court_teams.update_one({'_id': self.ta}, {'$push': {'members': {
            'account_id': other, 'joined_at': self.now}}})
        second = self.command(other, 'attack', castle_id='A001-C002', expected_revision=0,
            hero_id=self.hero, form_id=self.form, faction='Rebels')['match']['id']
        state = deepcopy(self.match(second))
        old_revision = self.match(first)['revision']
        self.code('forbidden', lambda: self.command(self.a, 'admin_cancel_match', match_id=first))
        self.code('stale_revision', lambda: self.command(self.admin, 'admin_cancel_match',
            match_id=first, expected_revision=old_revision - 1))
        cancelled = self.command(self.admin, 'admin_cancel_match', match_id=first)
        self.assertEqual(cancelled['match']['state'], 'cancelled')
        self.assertEqual(self.match(second), state)
        self.assertEqual(self.domain._wallet_public('team', self.ta)['available'], 995)
        self.assertEqual(self.db.court_quotas.find_one({'owner_id': self.a})['used'], 0)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': first}), 0)
        self.assertIsNotNone(self.db.court_seats.find_one({'_id': other, 'match_id': second}))
        self.assertEqual(self.db.court_battle_receipts.count_documents({}), 0)
        self.assertIsNone(self.db.court_castles.find_one({'_id': 'A001-C001'})['owner_team_id'])
        self.code('forbidden', lambda: self.domain.court_human_join(self.a, first))
        self.assertEqual(self.domain.court_worker_lease(first, 'native_worker_test', desc['generation'])['state'], 'cancelled')
        self.code('battle_locked', lambda: self.finish(desc))

    def test_competition_cancel_replaces_once_and_waits_for_manual_reschedule(self):
        event, _ = self.competition(4)
        self.command(self.admin, 'admin_lock_competition', competition_id=event)
        self.command(self.admin, 'admin_start_round', competition_id=event)
        row = self.db.court_competitions.find_one({'_id': event})
        first, other = [entry['match_id'] for entry in row['rounds'][0]['matches']]
        other_record = deepcopy(self.match(other))
        command_id, expected = str(uuid4()), self.match(first)['revision']
        with ThreadPoolExecutor(2) as pool:
            values = list(pool.map(lambda _: self.command(self.admin, 'admin_cancel_match', match_id=first,
                expected_revision=expected, command_id=command_id), range(2)))
        self.assertEqual(values[0], values[1])
        replacement = values[0]['replacement_match_id']
        self.assertEqual(self.match(first)['state'], 'cancelled')
        self.assertEqual(self.match(other), other_record)
        self.assertEqual(self.db.court_matches.count_documents({}), 3)
        self.assertEqual(self.match(replacement)['state'], 'scheduled')
        self.assertTrue(all(not seat['ready'] and not seat['account_id'] for seat in self.match(replacement)['seats']))
        self.domain._tx(lambda s: self.domain._battle_settle(self.match(other),
            other_record['team_ids'][0], False, 'attendance_forfeit', s))
        current = self.db.court_competitions.find_one({'_id': event})
        self.assertEqual((current['state'], current['round']), ('playing', 1))
        self.assertEqual(current['rounds'][0]['matches'][0]['cancelled_match_ids'], [first])
        other_final = deepcopy(self.match(other))
        self.command(self.admin, 'admin_start_round', competition_id=event)
        self.assertEqual(self.match(replacement)['state'], 'queued')
        self.assertEqual(self.match(other), other_final)
        self.assertTrue(all(self.domain._wallet_public('team', entry['team_id'])['available'] == 989
                            for entry in current['entries']))

    def test_player_cannot_send_worker_or_admin_commands(self):
        for op in ('worker_finish', 'worker_acquire', 'admin_create_competition'):
            self.code('unsupported_command', lambda: self.domain.court_command(self.a,
                {'version': 1, 'operation': op, 'payload': {'command_id': str(uuid4())}}))
        self.code('forbidden', lambda: self.command(self.a, 'admin_create_competition',
            castle_id='A001-C028', expected_revision=0, name='Invalid',
            settings=deepcopy(DEFAULT_BATTLE_SETTINGS), entry_fee=0))
