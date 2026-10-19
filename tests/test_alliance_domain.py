"""Alliance rules plus opt-in real MongoDB transaction integration.

Run from the server checkout with its pinned Python environment:
  python -m unittest discover -s tests -p test_alliance_domain.py -v
Set ALLIANCE_TEST_MONGO_URI to a loopback-only disposable replica set for MongoDB
checks. Each test owns a fresh alliance_test_<uuid> database and drops only it.
No .env is loaded and no existing game database is read or modified.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance import rules
try:
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure, DuplicateKeyError
    from alliance.domain import AllianceService, DomainError
    from alliance.schema import bootstrap_schema
except ImportError:
    MongoClient = None


class RulesTests(unittest.TestCase):
    def test_all_starters_have_finite_valid_paths(self):
        self.assertEqual(len(rules.STARTERS), 6)
        def walk(unit, ancestors):
            self.assertNotIn(unit, ancestors)
            level, threshold, children = rules.UNIT_TYPES[unit]
            self.assertGreater(threshold, 0)
            for child in children:
                self.assertEqual(rules.UNIT_TYPES[child][0], level + 1)
                walk(child, ancestors + [unit])
        for starter in rules.STARTERS.values():
            walk(starter['unit_type'], [])

    def test_advancement_preserves_overflow_and_caps_terminal_stats(self):
        leader = rules.award_experience(rules.new_leader('spearman'), 60)
        self.assertEqual(leader['unit_type'], 'Spearman')
        self.assertEqual(leader['advancement_choices'], ['Swordsman', 'Pikeman', 'Javelineer'])
        promoted = rules.advance_leader(leader, 'Swordsman')
        self.assertEqual(promoted['experience'], 18)
        promoted = rules.advance_leader(rules.award_experience(promoted, 80), 'Royal Guard')
        self.assertEqual(promoted['level'], 3)
        self.assertEqual(promoted['experience'], 0)
        self.assertEqual(promoted['total_experience'], 140)
        self.assertEqual(rules.award_experience(promoted, 100)['advancement_choices'], [])
        self.assertEqual(leader['unit_type'], 'Spearman')

    def test_no_unearned_or_arbitrary_advancement(self):
        for unit in ('Swordsman', 'Ancient Lich', 'Drake Warrior'):
            with self.assertRaises(ValueError):
                rules.advance_leader(rules.new_leader('spearman'), unit)
        for amount in (-1, 0.5, True):
            with self.assertRaises(ValueError):
                rules.award_experience(rules.new_leader('spearman'), amount)

    def test_elo_and_team_levels(self):
        self.assertEqual(rules.rating_delta(1000, 1000, 1), 12)
        self.assertEqual(rules.rating_delta(1000, 1000, 0), -12)
        self.assertEqual(rules.rating_delta(1000, 1000, 0.5), 0)
        self.assertGreater(rules.rating_delta(800, 1400, 1), 12)
        self.assertEqual([rules.team_level(x) for x in (0, 499, 500, 1000)], [1, 1, 2, 3])

    def test_rules_match_actual_supplied_unit_files_and_map_alliances(self):
        root = Path(__file__).resolve().parents[2] / 'gamedata-1.19.26' / 'data'
        if not root.is_dir():
            self.skipTest('The supplied game-data reference is not mounted in this test environment.')
        found = {}
        for file in (root / 'core' / 'units').rglob('*.cfg'):
            text = file.read_text(encoding='utf-8')
            match = re.search(r'^    id=(.+)$', text, re.M)
            if match and match[1] in rules.UNIT_TYPES:
                values = {key: re.search(r'^    '+key+r'=(.*)$', text, re.M)[1]
                          for key in ('level', 'experience', 'advances_to')}
                found[match[1]] = (int(values['level']), int(values['experience']),
                    tuple(values['advances_to'].split(',')) if values['advances_to'] != 'null' else ())
        self.assertEqual(found, rules.UNIT_TYPES)
        for map_id, filename in (('isars-cross', '4p_Isars_Cross.cfg'), ('hexcake', '6p_Hexcake.cfg'),
                                 ('mokena-prairie', '8p_Mokena_Prairie.cfg')):
            text = (root / 'multiplayer' / 'scenarios' / filename).read_text(encoding='utf-8')
            self.assertEqual(re.search(r'^    id=(.+)$', text, re.M)[1], rules.MAPS[map_id]['scenario_id'])
            teams = {}
            for side in re.findall(r'\[side\](.*?)\[/side\]', text, re.S):
                number = int(re.search(r'^        side=(\d+)$', side, re.M)[1])
                team = re.search(r'^        team_name=(.+)$', side, re.M)[1]
                teams.setdefault(team, []).append(number)
            self.assertEqual(tuple(tuple(v) for v in teams.values()), rules.MAPS[map_id]['sides'])


@unittest.skipUnless(MongoClient is not None and os.environ.get('ALLIANCE_TEST_MONGO_URI'),
                     'Set a disposable loopback ALLIANCE_TEST_MONGO_URI with pinned PyMongo installed.')
class MongoDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ['ALLIANCE_TEST_MONGO_URI']
        parsed = urlsplit(uri)
        if parsed.scheme != 'mongodb' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or ',' in parsed.netloc:
            raise RuntimeError('Integration tests refuse non-loopback or multiple MongoDB hosts.')
        cls.client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        hello = cls.client.admin.command('hello')
        if not hello.get('setName') or not hello.get('isWritablePrimary'):
            raise RuntimeError('Integration tests require a writable disposable replica-set primary.')

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.database_name = 'alliance_test_' + uuid4().hex
        self.db = self.client[self.database_name]
        bootstrap_schema(self.db)
        self.service = AllianceService(self.db)
        self.counter = 0

    def tearDown(self):
        if re.fullmatch(r'alliance_test_[0-9a-f]{32}', self.database_name):
            self.client.drop_database(self.database_name)

    def player(self, starter='spearman'):
        self.counter += 1
        return self.service.register(f'Player_{self.counter}', '$argon2id$test-only-not-a-login-hash', starter)['_id']

    def admin(self):
        return self.service.bootstrap_admin('Operator', '$argon2id$test-only-not-a-login-hash')['_id']

    def teams(self, size=2):
        members = [[self.player() for _ in range(size)] for _ in range(2)]
        teams = []
        for i, players in enumerate(members):
            team = self.service.create_team(players[0], f'Team_{i}')
            for player in players[1:]:
                self.service.request_join(player, team['_id'])
                self.service.approve_member(players[0], team['_id'], player)
            teams.append(team['_id'])
        return teams, members

    def battle(self, size=2, start=True):
        teams, members = self.teams(size)
        map_id = {2: 'isars-cross', 3: 'hexcake', 4: 'mokena-prairie'}[size]
        run = self.service.create_battle(members[0][0], teams[1], map_id, dict(zip(teams, members)))
        self.service.approve_battle(members[1][0], run['_id'])
        for player in sum(members, []):
            self.service.set_ready(player, run['_id'])
        if start:
            run = self.service.start_battle(members[0][0], run['_id'])
        return run, teams, members

    def assertDomain(self, code, callable_, *args, **kwargs):
        with self.assertRaises(DomainError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_registration_unique_casefold_and_safe_public_view(self):
        account = self.service.register('Alice_1', '$argon2id$test-hash', 'skeleton')
        self.assertNotIn('password_hash', account)
        self.assertNotIn('password_hash', self.service.get_account(account['_id']))
        self.assertEqual(account['leader']['unit_type'], 'Skeleton')
        self.assertDomain('conflict', self.service.register, 'ALICE_1', '$argon2id$test-hash')
        for name in ('ab', '$where', {'$ne': None}, 'User with space'):
            self.assertDomain('invalid_input', self.service.register, name, '$argon2id$test-hash')
        self.assertDomain('invalid_input', self.service.register, 'ValidUser', 'plaintext')

    def test_first_admin_guard_and_no_admin_play(self):
        admin = self.admin()
        self.assertDomain('already_initialized', self.service.bootstrap_admin, 'Operator2', '$argon2id$hash')
        self.assertDomain('forbidden', self.service.create_team, admin, 'AdminTeam')
        self.assertDomain('forbidden', self.service.start_campaign, admin, rules.MISSIONS[0])
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'bootstrap_admin'}), 1)

    def test_team_join_requires_request_captain_and_capacity(self):
        captain, outsider, applicant = self.player(), self.player(), self.player()
        team = self.service.create_team(captain, 'Wolves')['_id']
        self.assertDomain('not_requested', self.service.approve_member, captain, team, applicant)
        self.service.request_join(applicant, team)
        self.assertDomain('forbidden', self.service.approve_member, outsider, team, applicant)
        self.service.approve_member(captain, team, applicant)
        for _ in range(6):
            player = self.player()
            self.service.request_join(player, team)
            self.service.approve_member(captain, team, player)
        self.assertDomain('capacity', self.service.request_join, outsider, team)
        self.assertEqual(len(self.db.teams.find_one({'_id': team})['members']), 8)

    def test_captain_transfer_and_archive(self):
        teams, members = self.teams()
        team, (captain, teammate) = teams[0], members[0]
        self.assertDomain('captain_transfer_required', self.service.leave_team, captain)
        self.service.transfer_captain(captain, team, teammate)
        self.service.leave_team(captain)
        self.service.leave_team(teammate)
        self.assertEqual(self.db.teams.find_one({'_id': team})['status'], 'archived')
        self.service.create_team(captain, 'New Team')

    def test_unique_member_index_and_same_array_validator(self):
        teams, members = self.teams()
        with self.assertRaises(DuplicateKeyError):
            self.db.teams.update_one({'_id': teams[1]}, {'$push': {'members': {
                'account_id': members[0][0], 'joined_at': datetime.now(timezone.utc)}}})
        with self.assertRaises(OperationFailure):
            self.db.teams.update_one({'_id': teams[0]}, {'$push': {'members': {
                'account_id': members[0][0], 'joined_at': datetime.now(timezone.utc)}}})

    def test_campaign_order_progression_choice_and_duplicate_completion(self):
        player = self.player()
        self.assertDomain('mission_locked', self.service.start_campaign, player, rules.MISSIONS[1])
        first = self.service.start_campaign(player, rules.MISSIONS[0])
        self.assertDomain('busy', self.service.start_campaign, player, rules.MISSIONS[0])
        receipt = self.service.finish_campaign(first['_id'], 'win')
        self.assertEqual(receipt, self.service.finish_campaign(first['_id'], 'win'))
        self.assertDomain('result_conflict', self.service.finish_campaign, first['_id'], 'loss')
        for mission in rules.MISSIONS[1:]:
            run = self.service.start_campaign(player, mission)
            self.service.finish_campaign(run['_id'], 'win')
        account = self.service.get_account(player)
        self.assertEqual(account['leader']['total_experience'], 60)
        self.assertEqual(account['campaign_completed'], list(rules.MISSIONS))
        self.assertDomain('advancement_required', self.service.start_campaign, player, rules.MISSIONS[0])
        self.service.choose_advancement(player, 'Swordsman')
        self.assertEqual(self.service.get_account(player)['leader']['experience'], 18)
        self.service.start_campaign(player, rules.MISSIONS[0])

    def test_loss_and_cancellation_never_award_campaign_xp(self):
        player = self.player()
        run = self.service.start_campaign(player, rules.MISSIONS[0])
        self.service.finish_campaign(run['_id'], 'loss')
        run = self.service.start_campaign(player, rules.MISSIONS[0])
        self.service.cancel_run(run['_id'], 'Lost connection before completion')
        account = self.service.get_account(player)
        self.assertEqual(account['leader']['total_experience'], 0)
        self.assertEqual(account['campaign_completed'], [])
        self.assertIsNone(account['active_run_id'])
        self.assertDomain('invalid_state', self.service.finish_campaign, run['_id'], 'win')

    def test_approval_readiness_and_exact_alliances(self):
        for size in (2, 3, 4):
            # Fresh unique team names for each subcase.
            teams, members = self.teams(size) if size == 2 else self._extra_teams(size)
            map_id = {2: 'isars-cross', 3: 'hexcake', 4: 'mokena-prairie'}[size]
            run = self.service.create_battle(members[0][0], teams[1], map_id, dict(zip(teams, members)))
            self.assertDomain('approval_required', self.service.start_battle, members[0][0], run['_id'])
            self.service.approve_battle(members[1][0], run['_id'])
            self.assertDomain('not_ready', self.service.start_battle, members[0][0], run['_id'])
            for player in sum(members, []):
                self.service.set_ready(player, run['_id'])
            started = self.service.start_battle(members[0][0], run['_id'])
            for i, team in enumerate(teams):
                self.assertEqual(tuple(p['side'] for p in started['participants'] if p['team_id'] == team),
                                 rules.MAPS[map_id]['sides'][i])
            self.assertEqual(len(started['participants']), size * 2)
            self.service.cancel_run(run['_id'], 'Completed fixture check')

    def _extra_teams(self, size):
        members = [[self.player() for _ in range(size)] for _ in range(2)]
        ids = []
        for i, players in enumerate(members):
            team = self.service.create_team(players[0], f'Size_{size}_Team_{i}')['_id']
            for player in players[1:]:
                self.service.request_join(player, team)
                self.service.approve_member(players[0], team, player)
            ids.append(team)
        return ids, members

    def test_same_area_and_membership_validation(self):
        admin = self.admin()
        teams, members = self.teams()
        area = self.service.admin_create_area(admin, 'Area Two')['_id']
        self.service.admin_move_team(admin, teams[1], area, 'Move for area isolation test')
        self.assertDomain('different_area', self.service.create_battle, members[0][0], teams[1],
                          'isars-cross', dict(zip(teams, members)))
        self.service.admin_move_team(admin, teams[1], 'area-1', 'Return to default area')
        bad = deepcopy(members)
        bad[0][1] = self.player()
        self.assertDomain('not_member', self.service.create_battle, members[0][0], teams[1],
                          'isars-cross', dict(zip(teams, bad)))

    def test_active_locks_and_frozen_leader(self):
        admin = self.admin()
        run, teams, members = self.battle()
        captain = members[0][0]
        for method, args in ((self.service.leave_team, (captain,)),
                             (self.service.transfer_captain, (captain, teams[0], members[0][1])),
                             (self.service.admin_move_team, (admin, teams[0], 'area-1', 'Move during game')),
                             (self.service.choose_advancement, (captain, 'Swordsman')),
                             (self.service.start_campaign, (captain, rules.MISSIONS[0]))):
            self.assertDomain('busy', method, *args)
        self.assertDomain('invalid_state', self.service.set_ready, captain, run['_id'], False)
        self.assertEqual(self.service.get_account(captain)['leader']['experience'], 0)

    def test_settlement_awards_fixed_rewards_once_and_clears_locks(self):
        run, teams, members = self.battle()
        result = self.service.finish_battle(run['_id'], teams[0])
        self.assertEqual(self.service.finish_battle(run['_id'], teams[0]), result)
        self.assertDomain('result_conflict', self.service.finish_battle, run['_id'], teams[1])
        for i, team in enumerate(teams):
            stored = self.db.teams.find_one({'_id': team})
            self.assertEqual(stored['experience'], (100, 25)[i])
            self.assertEqual(stored['rating'], (1012, 988)[i])
            self.assertIsNone(stored['active_run_id'])
            for player in members[i]:
                account = self.service.get_account(player)
                self.assertEqual(account['leader']['experience'], (20, 10)[i])
                self.assertIsNone(account['active_run_id'])
        self.assertEqual(self.db.settlements.count_documents({}), 1)

    def test_draw_rewards_and_equal_rating(self):
        run, teams, members = self.battle()
        self.service.finish_battle(run['_id'], draw=True)
        for team in teams:
            stored = self.db.teams.find_one({'_id': team})
            self.assertEqual((stored['experience'], stored['rating']), (50, 1000))
        self.assertEqual(self.service.get_account(members[0][0])['leader']['experience'], 10)

    def test_concurrent_duplicate_settlement(self):
        run, teams, members = self.battle()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.service.finish_battle(run['_id'], teams[0]), range(6)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(self.db.settlements.count_documents({}), 1)
        self.assertEqual(self.service.get_account(members[0][0])['leader']['total_experience'], 20)

    def test_transaction_failure_rolls_back_partial_rewards(self):
        run, teams, members = self.battle()
        accounts_before = list(self.db.accounts.find({}).sort('_id', 1))
        teams_before = list(self.db.teams.find({}).sort('_id', 1))
        original = self.service._reward_player
        count = 0
        def failing(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Injected process-side settlement failure')
            return original(*args, **kwargs)
        self.service._reward_player = failing
        with self.assertRaises(RuntimeError):
            self.service.finish_battle(run['_id'], teams[0])
        self.service._reward_player = original
        self.assertEqual(list(self.db.accounts.find({}).sort('_id', 1)), accounts_before)
        self.assertEqual(list(self.db.teams.find({}).sort('_id', 1)), teams_before)
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        self.service.finish_battle(run['_id'], teams[0])

    def test_concurrent_player_reservation_allows_one_campaign(self):
        player = self.player()
        def start(_):
            try:
                return self.service.start_campaign(player, rules.MISSIONS[0])['_id']
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(start, range(4)))
        self.assertEqual(results.count('busy'), 3)
        self.assertEqual(self.db.game_runs.count_documents({'state': 'running'}), 1)

    def test_competing_membership_approvals_allow_only_one_team(self):
        first, second, member = self.player(), self.player(), self.player()
        teams = [self.service.create_team(first, 'First Team')['_id'],
                 self.service.create_team(second, 'Second Team')['_id']]
        for team in teams:
            self.service.request_join(member, team)
        def approve(pair):
            captain, team = pair
            try:
                self.service.approve_member(captain, team, member)
                return 'approved'
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, zip((first, second), teams)))
        self.assertEqual(results.count('approved'), 1)
        self.assertEqual(self.db.teams.count_documents({'members.account_id': member}), 1)

    def test_admin_changes_audited_revoke_sessions_and_cancel(self):
        admin = self.admin()
        player = self.player()
        self.db.auth_sessions.insert_one({'_id': 'test-session', 'account_id': player})
        self.service.admin_set_account_status(admin, player, 'suspended', 'Operator review requested')
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': player}), 0)
        self.assertDomain('suspended', self.service.start_campaign, player, rules.MISSIONS[0])
        self.assertDomain('forbidden', self.service.admin_set_account_status, admin, admin, 'suspended', 'Self lockout attempt')
        self.service.admin_set_account_status(admin, player, 'active', 'Operator review complete')
        run = self.service.start_campaign(player, rules.MISSIONS[0])
        self.service.admin_cancel_run(admin, run['_id'], 'Cancelled after connection loss')
        self.service.admin_cancel_run(admin, run['_id'], 'Duplicate cancellation retry')
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'cancel_run'}), 1)
        self.assertEqual(self.service.get_account(player)['leader']['total_experience'], 0)

    def test_leader_preview_change_requires_a_new_proposal(self):
        run, teams, members = self.battle(start=False)
        player = members[0][0]
        self.assertIn('leader', run['participants'][0])
        campaign = self.service.start_campaign(player, rules.MISSIONS[0])
        self.service.finish_campaign(campaign['_id'], 'win')
        self.assertDomain('stale_proposal', self.service.approve_battle, members[1][0], run['_id'])
        self.assertDomain('stale_proposal', self.service.start_battle, player, run['_id'])
        self.assertIsNone(self.service.get_account(player)['active_run_id'])
        self.assertEqual(self.service.get_run(run['_id'])['state'], 'draft')

    def test_new_captain_must_approve_existing_proposal(self):
        run, teams, members = self.battle(start=False)
        self.service.transfer_captain(members[1][0], teams[1], members[1][1])
        self.assertDomain('approval_required', self.service.start_battle, members[0][0], run['_id'])
        self.service.approve_battle(members[1][1], run['_id'])
        self.service.start_battle(members[0][0], run['_id'])

    def test_team_roster_request_privacy_and_decline_withdraw(self):
        captain, applicant, outsider = self.player(), self.player(), self.player()
        team = self.service.create_team(captain, 'Application Team')['_id']
        self.service.request_join(applicant, team)
        public = self.service.get_team(outsider, team)
        self.assertNotIn('join_requests', public)
        self.assertNotIn('applicants', public)
        self.assertEqual(public['members'][0]['username'], 'Player_1')
        self.assertNotIn('password_hash', repr(public))
        private = self.service.get_team(captain, team)
        self.assertEqual(private['join_requests'], [applicant])
        self.assertEqual(private['applicants'][0]['_id'], applicant)
        self.assertDomain('forbidden', self.service.reject_member, outsider, team, applicant)
        self.service.reject_member(captain, team, applicant)
        self.assertEqual(self.service.get_team(captain, team)['join_requests'], [])
        self.service.request_join(applicant, team)
        self.service.withdraw_join(applicant, team)
        self.assertEqual(self.service.get_team(captain, team)['join_requests'], [])

    def test_unknown_ruleset_cannot_use_current_rewards(self):
        run, teams, members = self.battle()
        self.db.game_runs.update_one({'_id': run['_id']}, {'$set': {'ruleset_version': 'future-v99'}})
        self.assertDomain('unsupported_ruleset', self.service.finish_battle, run['_id'], teams[0])
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        self.assertEqual(self.service.get_account(members[0][0])['leader']['total_experience'], 0)
        self.service.cancel_run(run['_id'], 'Version unavailable; release reservations')

    def test_schema_rejects_unknown_version_and_is_repeatable(self):
        bootstrap_schema(self.db)
        self.db.schema_metadata.update_one({'_id': 'alliance'}, {'$set': {'version': 999}})
        with self.assertRaises(RuntimeError):
            bootstrap_schema(self.db)

    def test_settlement_rejects_query_objects(self):
        self.assertDomain('invalid_input', self.service.finish_campaign, {'$ne': None}, 'win')
        self.assertDomain('invalid_input', self.service.finish_battle, {'$ne': None}, draw=True)


if __name__ == '__main__':
    unittest.main()
