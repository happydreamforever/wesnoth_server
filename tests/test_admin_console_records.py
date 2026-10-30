"""Populated operator views against disposable MongoDB and Flask HTTP routes.

Completed battles/receipts below are controlled persisted read fixtures. They
prove projection, binding and rendering behavior, not native combat evidence.
"""
from copy import deepcopy
import os
import re
import unittest
from uuid import uuid4

from werkzeug.datastructures import MultiDict

import test_admin_console as fixture
from alliance.admin_management import admin_record_revision
from alliance.domain import _now
from alliance.flexible import DEFAULT_SETTINGS
from alliance.heroes import load_catalog


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable replica set')
class AdminConsoleRecordTests(unittest.TestCase):
    setUpClass = classmethod(fixture.AdminConsoleTests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.AdminConsoleTests.tearDownClass.__func__)
    setUp = fixture.AdminConsoleTests.setUp
    tearDown = fixture.AdminConsoleTests.tearDown
    csrf = fixture.AdminConsoleTests.csrf
    login = fixture.AdminConsoleTests.login
    form = fixture.AdminConsoleTests.form
    snapshot = fixture.AdminConsoleTests.snapshot
    export_render = fixture.AdminConsoleTests.export_render

    def render(self, path):
        before = self.snapshot()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        text = response.get_data(as_text=True)
        for secret in (self.hash, self.settings.bridge_secret, self.settings.secret_key,
                       'PRIVATE-RECORD-CANARY', 'PRIVATE-WORKER-TICKET', 'PRIVATE-REPLAY-BYTES'):
            self.assertNotIn(secret, text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(before, self.snapshot())
        self.export_render(path, response)
        return text

    def plan(self):
        opponent = self.domain.create_team(self.other['_id'], 'Opposing Team')
        slots = [dict(side=side, kind='open', account_id='', ai_faction='', ai_leader='')
                 for side in range(1, 5)]
        plan = self.domain.directory_publish_plan(self.player['_id'], self.team['_id'],
            opponent['_id'], 'isars-cross', DEFAULT_SETTINGS, slots)
        return self.db.game_runs.find_one({'_id': plan['id']}), opponent

    def review_fixture(self, *, completed=False):
        record, opponent = self.plan()
        participants = [{'account_id': self.player['_id'], 'side': 1, 'selection': {'name': 'Spearman'}},
                        {'account_id': self.other['_id'], 'side': 2, 'selection': {'name': 'Elvish Fighter'}}]
        room = {'state': 'completed' if completed else 'preparing', 'revision': 3,
                'generation': str(uuid4()), 'scenario_sha256': 'a' * 64,
                'captains': {self.team['_id']: self.player['_id'], opponent['_id']: self.other['_id']},
                'result_reports': {}, 'result_approvals': {}, 'admission_secret': 'PRIVATE-RECORD-CANARY'}
        change = {'participants': participants, 'shared_room': room}
        if completed:
            room['result_reports'] = {p['account_id']: {'winner_team_id': self.team['_id'],
                'draw': False, 'replay_sha256': 'b' * 64} for p in participants}
            change.update(state='completed', result={'winner_team_id': self.team['_id'], 'draw': False})
        self.db.game_runs.update_one({'_id': record['_id']}, {'$set': change})
        return self.db.game_runs.find_one({'_id': record['_id']})

    def defense(self, *, committed=False):
        catalog, _ = load_catalog()
        hero = next(form for form in catalog['forms']
                    if form['source_type'] == 'Spearman' and form['native_level'] == 1)
        owner = self.player['_id']
        self.db.account_heroes.insert_one({'_id': str(uuid4()), 'account_id': owner,
            'hero_id': hero['hero_id'], 'forms': [hero['id']], 'total_experience': 0, 'revision': 0})
        self.domain.world_command(owner, 'company_initialize', {'command_id': str(uuid4())})
        company = self.db.companies.find_one({'_id': owner})
        soldier = self.db.company_soldiers.find_one({'owner_id': owner})
        self.domain.world_command(owner, 'company_select', {'command_id': str(uuid4()),
            'expected_revision': company['revision'], 'hero_id': hero['hero_id'], 'form_id': hero['id'],
            'soldier_ids': [soldier['_id']], 'bracket': 'scout'})
        opponent = self.domain.create_team(self.other['_id'], 'World Opponent')
        self.domain.world_admin_command(self.admin['_id'], 'bootstrap', {'command_id': str(uuid4()),
            'team_ids': [self.team['_id'], opponent['_id']]})
        self.domain.world_command(owner, 'enroll', {'command_id': str(uuid4())})
        castle = self.db.world_teams.find_one({'_id': self.team['_id']})['capital_id']
        result = self.domain.world_command(owner, 'defense_offer', {'command_id': str(uuid4()),
            'castle_id': castle, 'bracket': 'scout'})['data']['defense']
        if committed:
            # Controlled frozen assignment representation, without starting an engine.
            run_id = str(uuid4())
            self.db.world_defenses.update_one({'_id': result['id']}, {'$set': {'run_id': run_id}})
            self.db.company_asset_locks.update_many({'assignment_id': result['id']}, {'$set': {'run_id': run_id}})
        self.db.world_defenses.update_one({'_id': result['id']}, {'$set': {'private_ticket': 'PRIVATE-WORKER-TICKET'}})
        return self.db.world_defenses.find_one({'_id': result['id']})

    def test_flexible_draft_and_preparing_review_render_without_writes(self):
        # A real incomplete plan can contain all four kinds before equal
        # enabled-side counts and full human consent permit preparation.
        rival=self.domain.register('MixedRival',self.hash)
        opposing=self.domain.create_team(rival['_id'],'Mixed Opponent')
        slots=[dict(side=side,kind='open',account_id='',ai_faction='',ai_leader='') for side in range(1,5)]
        slots[0].update(kind='reserved',account_id=self.player['_id'])
        slots[3].update(kind='ai',ai_faction='Loyalists',ai_leader='Lieutenant')
        mixed=self.domain.directory_publish_plan(self.player['_id'],self.team['_id'],opposing['_id'],
            'isars-cross',DEFAULT_SETTINGS,slots)
        slots[2].update(kind='closed')
        mixed=self.domain.directory_edit_plan(rival['_id'],mixed['id'],mixed['revision'],
            'isars-cross',DEFAULT_SETTINGS,slots)
        self.domain.directory_approve_plan(self.player['_id'],mixed['id'],mixed['revision'])
        text=self.render('/runs/'+mixed['id'])
        for expected in ('Plan slots','Open member','Reserved member','Computer','Closed','Unclaimed',
                         'Native AI','No units','Loyalists','Lieutenant','PlayerOne','MixedRival',
                         'Captain approvals','Approved','Awaiting approval','Not required'):
            self.assertIn(expected,text)
        self.assertIsNone(self.db.game_runs.find_one({'_id':mixed['id']}).get('shared_room'))
        record = self.review_fixture()
        text = self.render('/runs/' + record['_id'])
        for expected in ('Result evidence', 'waiting_for_players', '0 / 2', 'PlayerOne', 'PlayerTwo',
                         'Spearman', 'Elvish Fighter', 'Unlimited'):
            self.assertIn(expected, text)
        self.assertNotIn('Resolve and award fixed rewards', text)
        self.assertIn(admin_record_revision(record), text)
        self.assertEqual(self.client.get('/manage/plans/' + record['_id']).status_code, 302)

    def test_completed_flexible_history_renders_reports_without_mutation_controls(self):
        record = self.review_fixture(completed=True)
        text = self.render('/runs/' + record['_id'])
        for expected in ('settled', '2 / 2', 'Human result reports', 'Test Team', 'b' * 64):
            self.assertIn(expected, text)
        self.assertIn('Not approved (history)',text)
        self.assertIn('Historical consent does not authorize another battle.',text)
        self.assertNotIn('Cancel run without rewards', text)
        self.assertNotIn('Resolve and award fixed rewards', text)
        before = self.snapshot()
        response = self.client.post('/manage-cancel/run/' + record['_id'],
                                    data=self.form(admin_record_revision(record)))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(before, self.snapshot())

    def test_standing_defense_http_rejects_stale_then_withdraws_current_permission(self):
        record = self.defense()
        path = '/manage/defenses/' + record['_id']
        text = self.render(path)
        self.assertIn('Withdraw defense authorization', text)
        form = self.form(record['revision'])
        self.db.world_defenses.update_one({'_id': record['_id']}, {'$inc': {'revision': 1}})
        before = self.snapshot()
        stale = self.client.post(path + '/withdraw', data=form)
        self.assertEqual(stale.status_code, 409)
        self.assertNotIn('PRIVATE-WORKER-TICKET', stale.get_data(as_text=True))
        self.assertEqual(before, self.snapshot())
        current = self.db.world_defenses.find_one({'_id': record['_id']})
        self.assertEqual(self.client.post(path + '/withdraw', data=self.form(current['revision'])).status_code, 302)
        self.assertEqual(self.db.world_defenses.find_one({'_id': record['_id']})['status'], 'withdrawn')
        self.assertEqual(self.db.company_asset_locks.count_documents({'assignment_id': record['_id']}), 0)
        self.assertNotIn('Withdraw defense authorization', self.render(path))

    def test_committed_defense_withdrawal_keeps_locked_assets(self):
        record = self.defense(committed=True)
        path = '/manage/defenses/' + record['_id']
        locks = list(self.db.company_asset_locks.find({'assignment_id': record['_id']}).sort('_id', 1))
        self.assertGreater(len(locks), 0)
        self.assertEqual(self.client.post(path + '/withdraw', data=self.form(record['revision'])).status_code, 302)
        current = self.db.world_defenses.find_one({'_id': record['_id']})
        self.assertEqual(current['status'], 'withdraw_pending')
        self.assertEqual(current['run_id'], record['run_id'])
        self.assertEqual(locks, list(self.db.company_asset_locks.find({'assignment_id': record['_id']}).sort('_id', 1)))
        self.assertNotIn('Withdraw defense authorization', self.render(path))

    def test_world_receipt_renders_real_reward_field_shapes_and_no_private_bytes(self):
        identity, soldier = str(uuid4()), str(uuid4())
        record = {'_id': identity, 'kind': 'world', 'round': 4, 'generation': str(uuid4()),
            'proof_digest': 'c' * 64, 'outcome': 'victory', 'winner_team_id': self.team['_id'],
            'hero_rewards': [{'account_id': self.player['_id'], 'hero_id': 'fixture_hero', 'experience': 20}],
            'soldier_rewards': [{'soldier_id': soldier, 'earned_xp': 37, 'before_type': 'Spearman',
                'after_type': 'Pikeman', 'final_xp': 11, 'dead': True, 'deployed': True}],
            'team_rewards': [{'team_id': self.team['_id'], 'experience': 100}],
            'captured_castle_id': None, 'replay_sha256': 'd' * 64, 'ledger_sha256': 'e' * 64,
            'event_count': 23, 'combat_verified': True, 'completed_rounds': 2,
            'wounds': [{'owner_id': self.player['_id'], 'asset_kind': 'soldier', 'asset_id': soldier,
                        'kind': 'world_wounded', 'recover_at_round': 5}], 'created_at': _now(),
            'worker_ticket': 'PRIVATE-WORKER-TICKET', 'replay_bytes': b'PRIVATE-REPLAY-BYTES'}
        self.db.world_settlements.insert_one(record)
        text = self.render('/manage/history/' + identity)
        for expected in ('Earned Xp', 'Before Type', 'After Type', 'Final Xp', 'Recover At Round',
                         'Spearman', 'Pikeman', 'world_wounded', 'd' * 64, '37', '11', '5'):
            self.assertIn(expected, text)
        self.assertEqual(re.findall(r'<form\b[^>]*action="([^"]+)"', text), ['/logout'])

    def test_malformed_mutation_forms_do_not_reflect_input_or_change_records(self):
        record = self.defense()
        path = '/manage/defenses/' + record['_id'] + '/withdraw'
        base = self.form(record['revision'])
        variants = []
        missing = deepcopy(base); missing.pop('confirmation'); variants.append(missing)
        unknown = {**base, 'private_input': 'PRIVATE-RECORD-CANARY'}; variants.append(unknown)
        variants.append({**base, 'revision': 'true'})
        variants.append({**base, 'revision': '-1'})
        variants.append(MultiDict(list(base.items()) + [('reason', '<script>PRIVATE-RECORD-CANARY</script>')]))
        before = self.snapshot()
        for form in variants:
            response = self.client.post(path, data=form)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('PRIVATE-RECORD-CANARY', response.get_data(as_text=True))
        self.assertEqual(before, self.snapshot())

    def test_stale_cancel_form_from_rendered_page_preserves_current_preparation(self):
        record = self.review_fixture()
        text = self.render('/runs/' + record['_id'])
        binding = re.search(r'name="revision"[^>]*value="([0-9a-f]{64})"', text)
        self.assertIsNotNone(binding)
        self.db.game_runs.update_one({'_id': record['_id']},
                                    {'$set': {'shared_room.generation': str(uuid4())}})
        before = self.snapshot()
        response = self.client.post('/manage-cancel/run/' + record['_id'], data=self.form(binding.group(1)))
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('PRIVATE-RECORD-CANARY', response.get_data(as_text=True))
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
