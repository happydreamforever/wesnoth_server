"""Explicit administrator hero unlocks on a disposable real replica set."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import threading
import unittest
from uuid import uuid4

import test_unified_product as fixture
from alliance.admin_management import admin_hero_grant_form
from alliance.auth import AuthService, hash_password
from alliance.domain import DomainError
from alliance.heroes import catalog_form, load_catalog
from alliance.world import bootstrap_world_schema


class GrantCatalogueTests(unittest.TestCase):
    def test_every_character_has_one_real_lowest_tier_grant_form(self):
        catalog, _ = load_catalog()
        self.assertEqual(len(catalog['heroes']), 117)
        for hero in catalog['heroes']:
            with self.subTest(hero=hero['id']):
                form = admin_hero_grant_form(hero['id'])
                self.assertEqual(catalog_form(hero['id'], form['id'])[1], form)
                self.assertFalse(any(other['native_level'] < form['native_level']
                                     for other in catalog['forms'] if other['hero_id'] == hero['id']))
        # The JSON's first Abhai form is Spectre, not the lower-tier Wraith.
        self.assertEqual(admin_hero_grant_form('abhai')['source_type'], 'Wraith')
        self.assertEqual(admin_hero_grant_form('abhai')['native_level'], 2)

    def test_invalid_identifiers_rejected_and_return_does_not_mutate_catalogue(self):
        for value in (None, {}, [], 4, '', 'not_a_canonical_hero', 'abhai '*20, '$ne', '../abhai'):
            with self.subTest(value=value), self.assertRaises(DomainError) as error:
                admin_hero_grant_form(value)
            self.assertEqual(error.exception.code, 'invalid_input')
        form = admin_hero_grant_form('abhai')
        form['attacks'].clear()
        self.assertTrue(admin_hero_grant_form('abhai')['attacks'])


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable local replica set')
class AdminHeroGrantTests(unittest.TestCase):
    setUpClass = classmethod(fixture.UnifiedProduct.setUpClass.__func__)
    tearDownClass = classmethod(fixture.UnifiedProduct.tearDownClass.__func__)
    tearDown = fixture.UnifiedProduct.tearDown
    player = fixture.UnifiedProduct.player
    seed = fixture.UnifiedProduct.seed
    begin = fixture.UnifiedProduct.begin
    checkpoint = fixture.UnifiedProduct.checkpoint
    code = fixture.UnifiedProduct.code

    def setUp(self):
        fixture.UnifiedProduct.setUp(self)
        bootstrap_world_schema(self.db)
        self.admin = self.domain.bootstrap_admin('Host', hash_password('private fixture password'))['_id']
        self.actor = self.player()

    def revision(self, account_id=None):
        return self.db.accounts.find_one({'_id': account_id or self.actor})['revision']

    def grant(self, *, actor=None, target=None, hero=None, reason='Host authorizes this hero', revision=None):
        target = target or self.actor
        return self.domain.admin_grant_hero(actor or self.admin, target, hero or self.hero,
            reason, self.revision(target) if revision is None else revision)

    def snapshot(self):
        return {name: list(self.db[name].find({}).sort('_id', 1))
                for name in self.db.list_collection_names() if not name.startswith('system.')}

    def test_unlock_without_campaign_has_zero_xp_exact_form_and_audit(self):
        before = self.snapshot()
        original = self.db.accounts.find_one({'_id': self.actor})
        result = self.grant()
        form = admin_hero_grant_form(self.hero)
        row = self.db.account_heroes.find_one({'account_id': self.actor})
        self.assertEqual(result['heroes'], [{
            'hero_id': self.hero, 'name': next(h['name'] for h in self.catalog['heroes'] if h['id'] == self.hero),
            'hero_level': 1, 'experience': 0, 'total_experience': 0, 'revision': 0, 'forms': [form['id']],
        }])
        self.assertEqual(row['unlock_source'], 'administrator')
        self.assertEqual(row['granted_by'], self.admin)
        self.assertEqual(self.domain._selection(self.actor, self.hero, form['id'])['hero_level'], 1)
        self.assertEqual(self.domain._selection(self.actor, self.hero, form['id'])['unit_type'], form['unit_type'])
        self.assertEqual(self.db.accounts.find_one({'_id': self.actor}), {**original, 'revision': original['revision']+1})
        audit = self.db.admin_audit.find_one({'action': 'grant_hero'})
        self.assertEqual(audit['actor_id'], self.admin)
        self.assertEqual(audit['target_id'], self.actor)
        self.assertEqual(audit['reason'], 'Host authorizes this hero')
        self.assertEqual(audit['before'], {'hero_id': self.hero, 'owned': False})
        self.assertEqual(audit['after'], {'hero_id': self.hero, 'owned': True, 'forms': [form['id']],
                                        'total_experience': 0, 'source': 'administrator'})
        self.assertNotIn('password', str(audit))
        after = self.snapshot()
        for name in before.keys() | after.keys():
            if name not in {'accounts', 'account_heroes', 'admin_audit'}:
                self.assertEqual(before.get(name, []), after.get(name, []), name)
        for name in ('game_runs','story_checkpoints','companies','company_soldiers','world_settlements','settlements'):
            self.assertEqual(self.db[name].count_documents({}), 0, name)

    def test_sessions_and_other_owned_progress_are_preserved(self):
        other_hero = next(h['id'] for h in self.catalog['heroes'] if h['id'] != self.hero)
        other_form = admin_hero_grant_form(other_hero)['id']
        self.seed(self.actor, hero=other_hero, forms=[other_form], total=463)
        previous = deepcopy(self.db.account_heroes.find_one({'account_id': self.actor}))
        login = AuthService(self.db).authenticate('Player_1', 'test player password 1', 'player')
        sessions = list(self.db.auth_sessions.find({}))
        self.grant()
        self.assertEqual(self.db.account_heroes.find_one({'_id': previous['_id']}), previous)
        self.assertEqual(list(self.db.auth_sessions.find({})), sessions)
        self.assertEqual(AuthService(self.db).validate_token(login['token'], 'player')['_id'], self.actor)
        self.assertEqual(len(self.domain.get_account(self.actor)['heroes']), 2)

    def test_duplicate_and_stale_submissions_are_nonmutating(self):
        revision = self.revision()
        self.grant(revision=revision)
        before = self.snapshot()
        self.code('stale_account', lambda: self.grant(revision=revision))
        self.assertEqual(self.snapshot(), before)
        self.code('hero_already_owned', lambda: self.grant())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'grant_hero'}), 1)
        self.assertEqual(self.db.account_heroes.count_documents({'account_id': self.actor}), 1)

    def test_existing_campaign_hero_keeps_forms_xp_identity_and_history(self):
        run = self.begin(self.actor)
        checkpoint = self.checkpoint(run)
        self.domain.story_checkpoint(self.actor, checkpoint)
        before = self.snapshot()
        self.code('hero_already_owned', lambda: self.grant())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.db.account_heroes.find_one({'account_id': self.actor})['total_experience'], 27)
        self.assertEqual(self.db.story_checkpoints.count_documents({}), 1)

    def test_ordinary_and_suspended_administrators_cannot_grant(self):
        outsider = self.player()
        before = self.snapshot()
        self.code('forbidden', lambda: self.grant(actor=outsider))
        self.assertEqual(before, self.snapshot())
        self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'suspended'}})
        before = self.snapshot()
        self.code('suspended', self.grant)
        self.assertEqual(before, self.snapshot())

    def test_admin_target_missing_target_invalid_id_and_bad_revision_rejected(self):
        before = self.snapshot()
        self.code('forbidden', lambda: self.grant(target=self.admin))
        self.assertEqual(before, self.snapshot())
        self.code('not_found', lambda: self.domain.admin_grant_hero(
            self.admin, str(uuid4()), self.hero, 'Reason', 0))
        for value in (-1, True, '0', None, 2**63, 1.2):
            self.code('invalid_input', lambda value=value: self.domain.admin_grant_hero(
                self.admin, self.actor, self.hero, 'Reason', value))
        for value in ('', {}, '$ne', 'not-an-account'):
            self.code('invalid_input', lambda value=value: self.domain.admin_grant_hero(
                self.admin, value, self.hero, 'Reason', self.revision()))
        for hero in ('', {}, 'not_a_canonical_hero'):
            self.code('invalid_input', lambda hero=hero: self.domain.admin_grant_hero(
                self.admin, self.actor, hero, 'Reason', self.revision()))
        for reason in ('', ' ', None, 'x'*501):
            self.code('invalid_input', lambda reason=reason: self.grant(reason=reason))
        self.code('stale_account', lambda: self.grant(revision=self.revision()+1))
        self.assertEqual(before, self.snapshot())

    def test_suspended_player_can_receive_hero_without_reactivation(self):
        self.db.accounts.update_one({'_id': self.actor}, {'$set': {'status': 'suspended'}})
        result = self.grant()
        self.assertEqual(result['status'], 'suspended')
        self.assertEqual(len(result['heroes']), 1)
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.actor}), 0)

    def test_additive_grant_does_not_release_or_rewrite_existing_commitments(self):
        active = str(uuid4())
        self.db.accounts.update_one({'_id': self.actor}, {'$set': {'active_run_id': active}})
        self.db.network_battle_reservations.insert_one({'_id': self.actor, 'kind': 'team',
            'run_id': active, 'generation': str(uuid4()), 'created_at': fixture._now()})
        reservation = self.db.network_battle_reservations.find_one({'_id': self.actor})
        result = self.grant()
        self.assertEqual(result['active_run_id'], active)
        self.assertEqual(self.db.network_battle_reservations.find_one({'_id': self.actor}), reservation)

    def test_granted_hero_supports_explicit_company_enlistment_without_auto_soldiers(self):
        self.grant()
        self.assertEqual(self.db.company_soldiers.count_documents({}), 0)
        self.domain.world_command(self.actor, 'company_initialize', {'command_id': str(uuid4())})
        self.assertEqual(self.db.company_soldiers.count_documents({'owner_id': self.actor}), 6)
        self.assertEqual(self.db.game_runs.count_documents({}), 0)
        self.assertEqual(self.db.story_checkpoints.count_documents({}), 0)

    def test_simultaneous_grants_accept_one_current_revision(self):
        revision = self.revision()
        barrier = threading.Barrier(2)
        def grant(_):
            barrier.wait(timeout=10)
            try:
                self.grant(revision=revision)
                return 'ok'
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(2) as pool:
            result = list(pool.map(grant, range(2)))
        self.assertEqual(sorted(result), ['ok', 'stale_account'])
        self.assertEqual(self.db.account_heroes.count_documents({'account_id': self.actor}), 1)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'grant_hero'}), 1)

    def test_story_reward_racing_grant_retains_every_earned_xp_and_form(self):
        for iteration in range(3):
            actor = self.player()
            run = self.begin(actor)
            checkpoint = self.checkpoint(run)
            revision = self.revision(actor)
            barrier = threading.Barrier(2)
            def grant():
                barrier.wait(timeout=10)
                try:
                    self.grant(target=actor, revision=revision)
                    return 'ok'
                except DomainError as error:
                    return error.code
            def story():
                barrier.wait(timeout=10)
                return self.domain.story_checkpoint(actor, checkpoint)
            with ThreadPoolExecutor(2) as pool:
                grant_future = pool.submit(grant)
                story_future = pool.submit(story)
                grant_result, story_result = grant_future.result(), story_future.result()
            self.assertIn(grant_result, ('ok', 'stale_account'))
            row = self.db.account_heroes.find_one({'account_id': actor, 'hero_id': self.hero})
            self.assertEqual(row['total_experience'], 27)
            self.assertIn(self.form, row['forms'])
            if grant_result == 'ok':
                self.assertIn(admin_hero_grant_form(self.hero)['id'], row['forms'])
            self.assertEqual(self.db.account_heroes.count_documents({'account_id': actor, 'hero_id': self.hero}), 1)
            self.assertEqual(self.db.admin_audit.count_documents({'action': 'grant_hero', 'target_id': actor}), int(grant_result == 'ok'))
            self.assertEqual(self.domain.story_checkpoint(actor, checkpoint), story_result)
            self.assertEqual(self.db.account_heroes.find_one({'_id': row['_id']}), row)


if __name__ == '__main__':
    unittest.main()
