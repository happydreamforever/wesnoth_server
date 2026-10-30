"""Real replica-set administration transactions; disposable databases only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import unittest
from uuid import uuid4

import test_company_product as fixture
from alliance.admin_management import admin_record_revision
from alliance.auth import AuthService, AuthError, hash_password
from alliance.domain import DomainError, _now
from alliance.flexible import DEFAULT_SETTINGS


class RecordVersionTests(unittest.TestCase):
    def test_fence_binds_identity_state_generation_and_all_revisions(self):
        row = {'_id': 'first', 'kind': 'alliance', 'state': 'draft', 'revision': 2,
               'next_checkpoint': 0, 'generation': 'one',
               'shared_room': {'state': 'preparing', 'revision': 3, 'generation': 'two'}}
        original = admin_record_revision(row)
        self.assertEqual(len(original), 64)
        self.assertEqual(original, admin_record_revision(deepcopy(row)))
        for field in ('_id', 'kind', 'state', 'revision', 'next_checkpoint', 'generation'):
            changed = deepcopy(row)
            changed[field] = 'changed'
            self.assertNotEqual(original, admin_record_revision(changed))
        for field in ('state', 'revision', 'generation'):
            changed = deepcopy(row)
            changed['shared_room'][field] = 'changed'
            self.assertNotEqual(original, admin_record_revision(changed))


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable local replica set')
class AdminManagementTests(unittest.TestCase):
    setUpClass = classmethod(fixture.CompanyTests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.CompanyTests.tearDownClass.__func__)
    tearDown = fixture.CompanyTests.tearDown
    player = fixture.CompanyTests.player
    seed = fixture.CompanyTests.seed
    code = fixture.CompanyTests.code
    command = fixture.CompanyTests.command
    company = fixture.CompanyTests.company
    expedition = fixture.CompanyTests.expedition
    load = fixture.CompanyTests.load
    evidence = fixture.CompanyTests.evidence

    def setUp(self):
        fixture.CompanyTests.setUp(self)
        self.admin = self.domain.bootstrap_admin('Host', hash_password('private fixture password'))['_id']
        self.actor = self.company()
        self.member = self.player(True)
        self.team = self.domain.create_team(self.actor, 'First Team')['_id']
        self.domain.request_join(self.member, self.team)
        self.domain.approve_member(self.actor, self.team, self.member)

    def manage(self, operation, value, revision=None, actor=None):
        if revision is None:
            revision = self.db.teams.find_one({'_id': self.team})['revision']
        return self.domain.admin_manage_team(actor or self.admin, self.team, operation,
                                             value, 'Host correction', revision)

    def plan(self):
        rival = self.player(True)
        other = self.domain.create_team(rival, 'Other Team')['_id']
        slots = [dict(side=i, kind='open', account_id='', ai_faction='', ai_leader='') for i in range(1, 5)]
        row = self.domain.directory_publish_plan(self.actor, self.team, other, 'isars-cross', DEFAULT_SETTINGS, slots)
        return row['id']

    def cancel(self, kind, key, actor=None, version=None):
        collection = self.db.world_contracts if kind == 'world' else self.db.game_runs
        row = collection.find_one({'_id': key})
        return self.domain.admin_cancel_record(actor or self.admin, kind, key, 'Host cancellation',
                                              version or admin_record_revision(row))

    def test_nonadministrator_cannot_manage_team(self):
        original = self.db.teams.find_one({'_id': self.team})
        self.code('forbidden', lambda: self.manage('rename', 'Bad change', actor=self.actor))
        self.assertEqual(original, self.db.teams.find_one({'_id': self.team}))

    def test_rename_retains_identity_roster_experience_and_stale_form_rejected(self):
        original = self.db.teams.find_one({'_id': self.team})
        changed = self.manage('rename', 'Renamed Team')
        current = self.db.teams.find_one({'_id': self.team})
        self.assertEqual(changed['name'], 'Renamed Team')
        for key in ('_id', 'members', 'captain_id', 'experience', 'rating', 'area_id'):
            self.assertEqual(original[key], current[key])
        self.code('stale_revision', lambda: self.manage('rename', 'Stale edit', original['revision']))
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'manage_team_rename'}), 1)

    def test_rename_conflict_rolls_back_audit_and_revision(self):
        rival = self.player()
        self.domain.create_team(rival, 'Taken Team')
        original = self.db.teams.find_one({'_id': self.team})
        self.code('conflict', lambda: self.manage('rename', 'taken team'))
        self.assertEqual(original, self.db.teams.find_one({'_id': self.team}))
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'manage_team_rename'}), 0)

    def test_transfer_clears_draft_consent_retains_plan_and_membership(self):
        plan = self.plan()
        self.db.game_runs.update_one({'_id': plan}, {'$set': {'approvals': {self.team: self.actor}, 'ready': [self.actor]}})
        before = self.db.game_runs.find_one({'_id': plan})
        changed = self.manage('captain', self.member)
        after = self.db.game_runs.find_one({'_id': plan})
        self.assertEqual(changed['captain_id'], self.member)
        self.assertEqual(after['ready'], [])
        self.assertEqual(after['approvals'], {})
        self.assertEqual(after['revision'], before['revision'] + 1)
        self.assertEqual(after['slots'], before['slots'])
        self.assertEqual(len(changed['members']), 2)

    def test_transfer_requires_current_active_member(self):
        outsider = self.player()
        self.code('not_member', lambda: self.manage('captain', outsider))
        self.db.accounts.update_one({'_id': self.member}, {'$set': {'status': 'suspended'}})
        self.code('forbidden', lambda: self.manage('captain', self.member))
        self.assertEqual(self.db.teams.find_one({'_id': self.team})['captain_id'], self.actor)

    def test_area_move_has_revision_fence_and_invalidates_plan_consent(self):
        plan = self.plan()
        self.db.game_runs.update_one({'_id': plan}, {'$set': {'approvals': {self.team: self.actor}, 'ready': [self.actor]}})
        old = self.db.teams.find_one({'_id': self.team})
        area = self.domain.admin_create_area(self.admin, 'Other Area')['_id']
        changed = self.manage('move_area', area)
        self.assertEqual(changed['area_id'], area)
        self.assertEqual(changed['members'], old['members'])
        row = self.db.game_runs.find_one({'_id': plan})
        self.assertEqual(row['ready'], [])
        self.assertEqual(row['approvals'], {})
        self.code('stale_revision', lambda: self.manage('move_area', old['area_id'], old['revision']))
        self.db.areas.update_one({'_id': area}, {'$set': {'enabled': False}})
        self.code('not_found', lambda: self.manage('move_area', area))
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'manage_team_move_area'}), 1)

    def test_remove_member_retains_account_and_hero_and_rejects_captain(self):
        account = self.domain.get_account(self.member)
        self.code('captain_transfer_required', lambda: self.manage('remove_member', self.actor))
        changed = self.manage('remove_member', self.member)
        self.assertEqual([m['account_id'] for m in changed['members']], [self.actor])
        current = self.domain.get_account(self.member)
        for key in ('_id', 'heroes', 'username', 'status', 'database_generation'):
            self.assertEqual(account[key], current[key])

    def test_active_company_contract_blocks_governance(self):
        run = self.expedition(self.actor)
        self.code('busy', lambda: self.manage('captain', self.member))
        self.assertNotEqual(self.db.world_contracts.find_one({'_id': run})['state'], 'cancelled')

    def test_removal_preserves_world_enrollment_and_round_history(self):
        rival = self.company()
        other = self.domain.create_team(rival, 'World Rival')['_id']
        self.domain.world_admin_command(self.admin, 'bootstrap', {'command_id': str(uuid4()), 'team_ids': [self.team, other]})
        self.command(self.member, 'company_initialize')
        self.command(self.member, 'enroll')
        enrolled = self.db.world_enrollments.find_one({'_id': self.member})
        self.manage('remove_member', self.member)
        self.assertEqual(len(self.db.teams.find_one({'_id': self.team})['members']), 1)
        self.assertEqual(enrolled, self.db.world_enrollments.find_one({'_id': self.member}))

    def test_concurrent_team_edits_have_only_one_winner(self):
        revision = self.db.teams.find_one({'_id': self.team})['revision']
        def change(index):
            try:
                self.manage('rename', 'Concurrent ' + str(index), revision)
                return 'ok'
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(change, range(2)))
        self.assertEqual(sorted(results), ['ok', 'stale_revision'])

    def test_cancel_plan_preserves_record_and_no_rewards(self):
        run = self.plan()
        original = self.db.game_runs.find_one({'_id': run})
        self.code('forbidden', lambda: self.cancel('plan', run, actor=self.actor))
        result = self.cancel('plan', run)
        current = self.db.game_runs.find_one({'_id': run})
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(original['slots'], current['slots'])
        self.assertEqual(self.db.settlements.count_documents({}), 0)
        self.assertEqual(self.cancel('plan', run), result)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'cancel_plan'}), 1)

    def test_cancel_fence_rejects_changed_generation_and_state(self):
        run = self.plan()
        version = admin_record_revision(self.db.game_runs.find_one({'_id': run}))
        self.db.game_runs.update_one({'_id': run}, {'$set': {'shared_room': {'state': 'preparing', 'generation': str(uuid4()), 'revision': 0}}})
        self.code('stale_revision', lambda: self.cancel('plan', run, version=version))
        self.assertEqual(self.db.game_runs.find_one({'_id': run})['state'], 'draft')

    def test_prepared_plan_cancel_preserves_disjoint_team_preparation(self):
        import test_flexible_product as flexible_fixture
        # Reuse the real public publish/join/hero/approve/ready operations.
        rival = self.player(True)
        reserve = self.player(True)
        other = self.domain.create_team(rival, 'Prepared Rival')['_id']
        self.domain.request_join(reserve, other)
        self.domain.approve_member(rival, other, reserve)
        players, teams = [[self.actor, self.member], [rival, reserve]], [self.team, other]
        self.slots = flexible_fixture.FlexibleProduct.slots.__get__(self)
        first = flexible_fixture.FlexibleProduct.publish(self, players, teams)
        first, first_players = flexible_fixture.FlexibleProduct.fill(self, players, first)
        second = flexible_fixture.FlexibleProduct.publish(self, players, teams)
        second, second_players = flexible_fixture.FlexibleProduct.fill(self, players, second, offset=1)
        protected = list(self.db.network_battle_reservations.find({'run_id': second['id']}).sort('_id', 1))
        self.code('busy', lambda: self.manage('captain', self.member))
        self.cancel('plan', first['id'])
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': first['id']}), 0)
        self.assertEqual(protected, list(self.db.network_battle_reservations.find({'run_id': second['id']}).sort('_id', 1)))
        for actor in first_players:
            self.assertIsNone(self.db.accounts.find_one({'_id': actor})['active_run_id'])
        for actor in second_players:
            self.assertEqual(self.db.accounts.find_one({'_id': actor})['active_run_id'], second['id'])
        self.assertEqual(self.db.game_runs.find_one({'_id': second['id']})['shared_room']['state'], 'preparing')

    def test_story_cancel_retains_checkpoint_history_and_hides_nonce(self):
        run = self.domain.story_begin(self.actor, self.campaign['id'], self.catalog['version'], self.digest)
        before = self.db.game_runs.find_one({'_id': run['run_id']})
        result = self.cancel('run', run['run_id'])
        current = self.db.game_runs.find_one({'_id': run['run_id']})
        for key in ('nonce', 'catalog_sha256', 'completed_scenarios', 'participants', 'database_generation'):
            self.assertEqual(current[key], before[key])
        self.assertEqual(result['state'], 'cancelled')
        self.assertNotIn(before['nonce'], repr(result))
        self.assertEqual(self.db.story_checkpoints.count_documents({}), 0)

    def test_world_cancel_releases_only_selected_contract_assets(self):
        first = self.expedition(self.actor)
        other = self.company()
        second = self.expedition(other)
        protected = list(self.db.company_asset_locks.find({'run_id': second}).sort('_id', 1))
        self.cancel('world', first)
        self.assertEqual(self.db.company_asset_locks.count_documents({'run_id': first}), 0)
        self.assertEqual(protected, list(self.db.company_asset_locks.find({'run_id': second}).sort('_id', 1)))
        self.assertEqual(self.db.world_contracts.find_one({'_id': second})['state'], 'queued')
        self.assertEqual(self.db.world_settlements.count_documents({}), 0)

    def test_completed_world_cannot_cancel_or_award_again(self):
        run = self.expedition(self.actor)
        desc = self.load(run)
        receipt = self.domain.world_worker_finish(run, 'test_worker_123', desc['generation'], self.evidence(desc))
        retained = self.db.world_settlements.find_one({'_id': run})
        self.code('invalid_state', lambda: self.cancel('world', run))
        self.assertEqual(retained, self.db.world_settlements.find_one({'_id': run}))
        self.assertEqual(receipt, self.domain.world_worker_finish(run, 'test_worker_123', desc['generation'], self.evidence(desc)))

    def test_revoke_sessions_preserves_password_progress_and_reservations(self):
        auth = AuthService(self.db)
        username = self.db.accounts.find_one({'_id': self.actor})['username']
        token = auth.authenticate(username, 'test player password 1', 'player')['token']
        run = self.expedition(self.actor)
        before = self.db.accounts.find_one({'_id': self.actor})
        locks = list(self.db.company_asset_locks.find({'run_id': run}).sort('_id', 1))
        result = self.domain.admin_revoke_sessions(self.admin, self.actor, 'End prior sessions', before['revision'])
        self.assertEqual(result['sessions_revoked'], 1)
        with self.assertRaises(AuthError):
            auth.validate_token(token, 'player')
        after = self.db.accounts.find_one({'_id': self.actor})
        self.assertEqual(before['password_hash'], after['password_hash'])
        self.assertEqual(locks, list(self.db.company_asset_locks.find({'run_id': run}).sort('_id', 1)))
        self.code('stale_account', lambda: self.domain.admin_revoke_sessions(self.admin, self.actor, 'Old form retry', before['revision']))

    def test_admin_self_session_revocation_uses_original_revision(self):
        auth = AuthService(self.db)
        token = auth.authenticate('Host', 'private fixture password', 'admin')['token']
        row = self.db.accounts.find_one({'_id': self.admin})
        result = self.domain.admin_revoke_sessions(self.admin, self.admin, 'End host sessions', row['revision'])
        self.assertEqual(result['sessions_revoked'], 1)
        with self.assertRaises(AuthError):
            auth.validate_token(token, 'admin')

    def test_company_rest_keeps_territorial_and_locked_wounds(self):
        company = self.db.companies.find_one({'_id': self.actor})
        soldiers = list(self.db.company_soldiers.find({'owner_id': self.actor}).sort('_id', 1))
        for index, soldier in enumerate(soldiers[:3]):
            self.db.company_wounds.insert_one({'_id': str(uuid4()), 'owner_id': self.actor,
                'asset_kind': 'soldier', 'asset_id': soldier['_id'],
                'kind': 'world_wounded' if index == 0 else 'rest_wounded',
                'run_id': str(uuid4()), 'created_at': _now()})
        self.db.company_asset_locks.insert_one({'_id': 'soldier:' + soldiers[1]['_id'],
            'owner_id': self.actor, 'run_id': str(uuid4()), 'assignment_id': None, 'created_at': _now()})
        result = self.domain.admin_rest_company(self.admin, self.actor, 'Rest safe wounds', company['revision'])
        self.assertEqual(result['healed'], 1)
        self.assertEqual(result['territorial_wounds'], 1)
        self.assertEqual(self.db.company_wounds.count_documents({'owner_id': self.actor}), 2)
        self.assertEqual(soldiers, list(self.db.company_soldiers.find({'owner_id': self.actor}).sort('_id', 1)))
        self.code('stale_revision', lambda: self.domain.admin_rest_company(self.admin, self.actor, 'Old rest retry', company['revision']))

    def test_player_creation_is_ordinary_empty_and_audit_has_no_password(self):
        password = 'New player password 123'
        self.code('forbidden', lambda: self.domain.admin_create_player(self.actor, 'NewPlayer', password, password, 'Create test player'))
        account = self.domain.admin_create_player(self.admin, 'NewPlayer', password, password, 'Create test player')
        self.assertEqual(account['heroes'], [])
        self.assertEqual(account['role'], 'player')
        self.assertEqual(self.db.company_soldiers.count_documents({'owner_id': account['_id']}), 0)
        audit = self.db.admin_audit.find_one({'action': 'create_player'})
        self.assertNotIn(password, repr(audit))
        self.assertNotIn('password_hash', repr(audit))
        auth = AuthService(self.db)
        self.assertEqual(auth.authenticate('NewPlayer', password, 'player')['account']['_id'], account['_id'])

    def test_bad_confirmation_and_duplicate_create_do_not_write(self):
        password = 'New player password 123'
        count = self.db.accounts.count_documents({})
        self.code('invalid_input', lambda: self.domain.admin_create_player(self.admin, 'Another', password, password + 'x', 'Create test player'))
        self.assertEqual(self.db.accounts.count_documents({}), count)
        self.domain.admin_create_player(self.admin, 'Another', password, password, 'Create test player')
        self.code('conflict', lambda: self.domain.admin_create_player(self.admin, 'Another', password, password, 'Create test player'))
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'create_player'}), 1)

    def test_invalid_revision_reason_and_operation_have_no_audit(self):
        before = self.db.admin_audit.count_documents({})
        self.code('invalid_input', lambda: self.manage('rename', 'Invalid Revision', revision=True))
        self.code('invalid_input', lambda: self.manage('drop_team', self.member))
        row = self.db.companies.find_one({'_id': self.actor})
        self.code('invalid_input', lambda: self.domain.admin_rest_company(self.admin, self.actor, '', row['revision']))
        self.assertEqual(self.db.admin_audit.count_documents({}), before)

    def test_rest_and_session_actions_require_active_administrator(self):
        company = self.db.companies.find_one({'_id': self.actor})
        account = self.db.accounts.find_one({'_id': self.actor})
        self.code('forbidden', lambda: self.domain.admin_rest_company(self.member, self.actor, 'Denied rest', company['revision']))
        self.code('forbidden', lambda: self.domain.admin_revoke_sessions(self.member, self.actor, 'Denied sessions', account['revision']))
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'suspended'}})
        self.code('suspended', lambda: self.manage('rename', 'Denied rename'))

    def test_defense_withdrawal_keeps_frozen_engagement_then_releases(self):
        rival = self.company()
        other = self.domain.create_team(rival, 'Defense Rival')['_id']
        self.domain.world_admin_command(self.admin, 'bootstrap', {'command_id': str(uuid4()), 'team_ids': [self.team, other]})
        self.command(self.actor, 'enroll')
        castle = self.db.world_teams.find_one({'_id': self.team})['capital_id']
        offered = self.command(self.actor, 'defense_offer', castle_id=castle, bracket='scout')['defense']
        assignment = offered['id']
        row = self.db.world_defenses.find_one({'_id': assignment})
        self.code('forbidden', lambda: self.domain.admin_withdraw_defense(self.member, assignment, 'Denied withdrawal', row['revision']))
        # Frozen-contract representation: existing permission stays tied to its
        # run until the actual settlement/cancellation release routine executes.
        run_id = str(uuid4())
        self.db.world_defenses.update_one({'_id': assignment}, {'$set': {'run_id': run_id}})
        self.db.company_asset_locks.update_many({'assignment_id': assignment}, {'$set': {'run_id': run_id}})
        retained = list(self.db.company_asset_locks.find({'assignment_id': assignment}).sort('_id', 1))
        result = self.domain.admin_withdraw_defense(self.admin, assignment, 'Stop future defense', row['revision'])
        self.assertEqual(result['status'], 'withdraw_pending')
        self.assertEqual(retained, list(self.db.company_asset_locks.find({'assignment_id': assignment}).sort('_id', 1)))
        self.domain._tx(lambda session: self.domain._world_release({'_id': run_id, 'generation': str(uuid4()),
            'armies': [{'account_id': self.actor, 'assignment_id': assignment}]}, session))
        self.assertEqual(self.db.world_defenses.find_one({'_id': assignment})['status'], 'withdrawn')
        self.assertEqual(self.db.company_asset_locks.count_documents({'assignment_id': assignment}), 0)

    def test_unlocked_defense_withdrawal_is_immediate(self):
        rival = self.company()
        other = self.domain.create_team(rival, 'Defense Rival')['_id']
        self.domain.world_admin_command(self.admin, 'bootstrap', {'command_id': str(uuid4()), 'team_ids': [self.team, other]})
        self.command(self.actor, 'enroll')
        castle = self.db.world_teams.find_one({'_id': self.team})['capital_id']
        offered = self.command(self.actor, 'defense_offer', castle_id=castle, bracket='scout')['defense']
        self.code('busy', lambda: self.manage('captain', self.member))
        result = self.domain.admin_withdraw_defense(self.admin, offered['id'], 'Withdraw idle defense', offered['revision'])
        self.assertEqual(result['status'], 'withdrawn')
        self.assertEqual(self.db.company_asset_locks.count_documents({'assignment_id': offered['id']}), 0)
        self.assertEqual(self.manage('captain', self.member)['captain_id'], self.member)


if __name__ == '__main__':
    unittest.main()
