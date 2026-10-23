"""Admin account changes against a disposable loopback MongoDB replica set only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from pymongo import MongoClient

from alliance import auth, domain
from alliance.auth import AuthError, AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService, DomainError
from alliance.schema import bootstrap_schema


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Isolated test MongoDB URI required')
class AccountAdministrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ['ALLIANCE_TEST_MONGO_URI']
        if urlsplit(uri).scheme != 'mongodb' or urlsplit(uri).hostname != '127.0.0.1':
            raise RuntimeError('Tests require an isolated loopback database.')
        cls.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        if not cls.client.admin.command('hello').get('setName'):
            raise RuntimeError('Tests require a disposable replica set.')
        cls.password = 'Original fixture password'
        cls.replacement = '  New fixture É界😀 secret  '
        cls.encoded = hash_password(cls.password)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.db = self.client['alliance_test_account_admin_' + uuid4().hex]
        bootstrap_schema(self.db)
        bootstrap_auth_schema(self.db)
        self.service = AllianceService(self.db)
        self.auth = AuthService(self.db)
        self.admin = self.service.bootstrap_admin('Operator', self.encoded)['_id']
        self.player = self.service.register('PlayerOne', self.encoded)['_id']
        self.other = self.service.register('PlayerTwo', self.encoded)['_id']
        self.db.admin_audit.delete_many({})

    def tearDown(self):
        self.client.drop_database(self.db.name)

    def account(self, target=None):
        return self.db.accounts.find_one({'_id': target or self.player})

    def edit(self, target=None, username=None, status='active', revision=None, actor=None):
        target = target or self.player
        account = self.account(target)
        return self.service.admin_edit_account(actor or self.admin, target,
            username or account['username'], status, 'Fixture account correction',
            account['revision'] if revision is None else revision)

    def reset(self, target=None, revision=None, actor=None, password=None):
        target = target or self.player
        password = self.replacement if password is None else password
        return self.service.admin_reset_password(actor or self.admin, target, password, password,
            'Fixture credential recovery', self.account(target)['revision'] if revision is None else revision)

    def assert_domain(self, code, function, *args, **kwargs):
        with self.assertRaises(DomainError) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def sessions(self, target):
        now = datetime.now(timezone.utc)
        for scope in ('admin', 'player'):
            self.db.auth_sessions.insert_one({'_id': uuid4().hex, 'account_id': target,
                'scope': scope, 'revoked': False, 'expires_at': now + timedelta(hours=1)})

    def snapshot(self):
        return {name: list(self.db[name].find().sort('_id', 1))
                for name in self.db.list_collection_names()}

    def seed_attempts(self, now, keys):
        bucket = int(now.timestamp()) // 900
        ids = {}
        for scope, name in keys:
            for number in (bucket - 2, bucket - 1, bucket, bucket + 1):
                identifier = hashlib.sha256(f'{scope}:{name}:{number}'.encode()).hexdigest()
                self.db.auth_attempts.insert_one({'_id': identifier, 'count': 10,
                    'expires_at': now + timedelta(days=1)})
                ids[(scope, name, number)] = identifier
        return bucket, ids

    def test_rename_preserves_identity_game_fields_team_and_history(self):
        team = self.service.create_team(self.player, 'Stable Team')
        self.service.request_join(self.other, team['_id'])
        self.service.approve_member(self.player, team['_id'], self.other)
        before = self.account()
        team_before = self.db.teams.find_one({'_id': team['_id']})
        result = self.edit(username='NewPlayer')
        expected = deepcopy(before)
        expected.update(username='NewPlayer', username_key='newplayer', revision=before['revision'] + 1)
        self.assertEqual(self.account(), expected)
        self.assertEqual(self.db.teams.find_one({'_id': team['_id']}), team_before)
        self.assertNotIn('password_hash', result)
        self.assertEqual(result['_id'], self.player)
        self.assertEqual(self.service.directory_team(self.other, team['_id'])['members'][0]['username'], 'NewPlayer')
        audit = self.db.admin_audit.find_one({'action': 'edit_account'})
        self.assertEqual(audit['before'], {'username': 'PlayerOne', 'status': 'active'})
        self.assertEqual(audit['after'], {'username': 'NewPlayer', 'status': 'active'})
        self.assertNotIn(self.encoded, str(audit))

    def test_casefold_collision_rolls_back_actor_revision_and_sessions(self):
        self.sessions(self.player)
        before = self.snapshot()
        self.assert_domain('conflict', self.edit, username='pLaYeRtWo')
        self.assertEqual(self.snapshot(), before)

    def test_case_only_rename_revokes_target_sessions_only(self):
        self.sessions(self.player)
        self.sessions(self.other)
        result = self.edit(username='PLAYERONE')
        self.assertEqual(result['username_key'], 'playerone')
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.player}), 0)
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.other}), 2)

    def test_noop_save_consumes_revision_and_audits_without_revoking(self):
        self.sessions(self.player)
        previous = self.account()['revision']
        result = self.edit()
        self.assertEqual(result['revision'], previous + 1)
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.player}), 2)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'edit_account'}), 1)
        self.assert_domain('stale_account', self.edit, revision=previous)

    def test_suspend_and_reactivate_preserve_role_and_revoke_sessions(self):
        for status in ('suspended', 'active'):
            self.sessions(self.player)
            result = self.edit(status=status)
            self.assertEqual(result['status'], status)
            self.assertEqual(result['role'], 'player')
            self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.player}), 0)

    def test_self_edit_and_reset_consume_exactly_one_revision(self):
        self.sessions(self.admin)
        before = self.account(self.admin)['revision']
        result = self.edit(target=self.admin, username='NewOperator')
        self.assertEqual(result['revision'], before + 1)
        self.assertEqual(result['role'], 'admin')
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.admin}), 0)
        self.sessions(self.admin)
        result = self.reset(target=self.admin)
        self.assertEqual(result['revision'], before + 2)
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.admin}), 0)
        login = self.auth.authenticate('NewOperator', self.replacement, 'admin')
        self.assertEqual(login['account']['_id'], self.admin)

    def test_self_suspension_and_player_actor_are_rejected(self):
        self.assert_domain('forbidden', self.edit, target=self.admin, status='suspended')
        with patch.object(auth, 'hash_password', side_effect=AssertionError('Unauthorized hash')):
            self.assert_domain('forbidden', self.reset, actor=self.other)
        self.assert_domain('forbidden', self.edit, actor=self.other)
        self.assertEqual(self.account(self.admin)['status'], 'active')

    def test_stale_forms_invalid_revisions_names_status_and_reason_do_not_mutate(self):
        before = self.snapshot()
        for revision in (-1, True, None, '0', 1.5, 2**63):
            self.assert_domain('invalid_input', self.service.admin_edit_account,
                self.admin, self.player, 'PlayerOne', 'active', 'Fixture reason', revision)
            self.assert_domain('invalid_input', self.service.admin_reset_password,
                self.admin, self.player, self.replacement, self.replacement, 'Fixture reason', revision)
        self.assert_domain('stale_account', self.edit, revision=1000)
        self.assert_domain('stale_account', self.reset, revision=1000)
        for name, status, reason in [('x', 'active', 'Reason'), ('Name', 'owner', 'Reason'),
                                    ('Name', 'active', ''), ('Name', 'active', 'x'*501)]:
            self.assert_domain('invalid_input', self.service.admin_edit_account,
                self.admin, self.player, name, status, reason, self.account()['revision'])
        self.assertEqual(self.snapshot(), before)

    def test_password_reset_exact_unicode_spaces_new_hash_and_session_revoke(self):
        self.sessions(self.player)
        self.sessions(self.other)
        before = self.account()
        result = self.reset()
        after = self.account()
        expected = deepcopy(before)
        expected.update(password_hash=after['password_hash'], revision=before['revision'] + 1)
        self.assertEqual(after, expected)
        self.assertTrue(after['password_hash'].startswith('$argon2id$'))
        self.assertNotEqual(after['password_hash'], before['password_hash'])
        self.assertTrue(auth._HASHER.verify(after['password_hash'], self.replacement))
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.player}), 0)
        self.assertEqual(self.db.auth_sessions.count_documents({'account_id': self.other}), 2)
        self.assertNotIn('password_hash', result)
        audit = self.db.admin_audit.find_one({'action': 'reset_password'})
        self.assertIsNone(audit['before'])
        self.assertEqual(audit['after'], {'password_reset': True, 'sessions_revoked': True})
        for secret in (self.password, self.replacement, before['password_hash'], after['password_hash']):
            self.assertNotIn(secret, str(audit))
            self.assertNotIn(secret, str(result))
        for password in (self.password, self.replacement.strip()):
            with self.assertRaises(AuthError):
                self.auth.authenticate('PlayerOne', password, 'player')
        self.assertEqual(self.auth.authenticate('PlayerOne', self.replacement, 'player')['account']['_id'], self.player)

    def test_reset_accepts_exact_12_and_128_unicode_codepoints(self):
        for password in ('界' * 12, '😀' * 128):
            self.reset(password=password)
            self.assertTrue(auth._HASHER.verify(self.account()['password_hash'], password))

    def test_invalid_passwords_and_confirmation_never_hash_or_mutate(self):
        before = self.snapshot()
        cases = [(None, None), (b'password bytes', b'password bytes'), ('x'*11, 'x'*11),
                 ('x'*129, 'x'*129), ('a'*12 + '\x00', 'a'*12 + '\x00'),
                 ('a'*12 + '\ud800', 'a'*12 + '\ud800'), ('a'*12 + '\udfff', 'a'*12 + '\udfff'),
                 (self.replacement, self.replacement.strip()), (self.replacement, None)]
        with patch.object(auth, 'hash_password', side_effect=AssertionError('Invalid input hashed')):
            for password, confirmation in cases:
                self.assert_domain('invalid_input', self.service.admin_reset_password,
                    self.admin, self.player, password, confirmation, 'Fixture recovery', self.account()['revision'])
        self.assertEqual(self.snapshot(), before)

    def test_reset_suspended_account_keeps_suspension(self):
        self.edit(status='suspended')
        result = self.reset()
        self.assertEqual(result['status'], 'suspended')
        with self.assertRaises(AuthError):
            self.auth.authenticate('PlayerOne', self.replacement, 'player')
        self.edit(status='active')
        self.assertEqual(self.auth.authenticate('PlayerOne', self.replacement, 'player')['account']['_id'], self.player)

    def test_active_run_blocks_edit_but_allows_password_recovery_without_unlock(self):
        from alliance.heroes import load_catalog
        catalog,digest=load_catalog();campaign=next(c for c in catalog['campaigns'] if c['aliases']);alias=campaign['aliases'][0]
        hero,form=alias['hero_id'],alias['forms'][0]['form_id'];story=self.service.story_begin(self.player,campaign['id'],catalog['version'],digest)
        self.service.story_checkpoint(self.player,{'run_id':story['run_id'],'checkpoint_id':str(uuid4()),'sequence':0,
            'scenario_id':campaign['first_scenario'],'next_scenario_id':'','outcome':'win','nonce':story['nonce'],
            'replay_sha256':'a'*64,'heroes':[{'hero_id':hero,'unit_id':alias['unit_id'],'form_id':form,'unlocked_forms':[form],'earned_experience':0}]})
        run=self.service.get_run(self.service.progression_start(self.player,'alliance_training_1',hero,form)['run']['id'])
        before = self.account()
        run_before = self.db.game_runs.find_one({'_id': run['_id']})
        hero_before = list(self.db.account_heroes.find({'account_id': self.player}))
        self.assert_domain('busy', self.edit, username='BusyPlayer')
        self.reset()
        after = self.account()
        self.assertEqual(after['active_run_id'], run['_id'])
        self.assertEqual(list(self.db.account_heroes.find({'account_id': self.player})), hero_before)
        self.assertEqual(after['training_completed'], before['training_completed'])
        self.assertEqual(self.db.game_runs.find_one({'_id': run['_id']}), run_before)
        self.assertEqual(self.db.settlements.count_documents({}), 0)

    def test_reset_clears_only_target_role_current_previous_attempt_buckets(self):
        now = datetime(2026, 10, 21, 12, 7, tzinfo=timezone.utc)
        bucket, ids = self.seed_attempts(now, [('player', 'playerone'), ('admin', 'playerone'), ('player', 'playertwo')])
        with patch.object(domain, '_now', return_value=now):
            self.reset()
        remaining = {item['_id'] for item in self.db.auth_attempts.find()}
        removed = {ids[('player', 'playerone', n)] for n in (bucket - 1, bucket)}
        self.assertEqual(remaining, set(ids.values()) - removed)

    def test_rename_clears_only_old_new_role_buckets(self):
        now = datetime(2026, 10, 21, 12, 7, tzinfo=timezone.utc)
        bucket, ids = self.seed_attempts(now, [('player', 'playerone'), ('player', 'newplayer'),
                                            ('admin', 'newplayer'), ('player', 'playertwo')])
        with patch.object(domain, '_now', return_value=now):
            self.edit(username='NewPlayer')
        remaining = {item['_id'] for item in self.db.auth_attempts.find()}
        removed = {ids[('player', name, n)] for name in ('playerone', 'newplayer') for n in (bucket - 1, bucket)}
        self.assertEqual(remaining, set(ids.values()) - removed)

    def test_audit_failure_rolls_back_hash_sessions_attempts_and_actor_revision(self):
        self.sessions(self.player)
        now = datetime.now(timezone.utc)
        self.seed_attempts(now, [('player', 'playerone'), ('player', 'newplayer')])
        before = self.snapshot()
        for action in (lambda: self.edit(username='NewPlayer'), self.reset):
            with patch.object(self.service, '_audit', side_effect=RuntimeError('Fixture rollback')):
                with self.assertRaisesRegex(RuntimeError, 'Fixture rollback'):
                    action()
            self.assertEqual(self.snapshot(), before)

    def test_rename_during_password_verification_cannot_issue_old_name_session(self):
        original = auth._HASHER.verify
        def rename_then_return(encoded, password):
            result = original(encoded, password)
            self.edit(username='NewPlayer')
            return result
        with patch.object(auth, '_HASHER', wraps=auth._HASHER) as mocked:
            mocked.verify.side_effect = rename_then_return
            with self.assertRaises(AuthError):
                self.auth.authenticate('PlayerOne', self.password, 'player')
        self.assertEqual(self.db.auth_sessions.count_documents({}), 0)
        with self.assertRaises(AuthError):
            self.auth.authenticate('PlayerOne', self.password, 'player')
        self.assertEqual(self.auth.authenticate('NewPlayer', self.password, 'player')['account']['_id'], self.player)

    def test_reset_during_password_verification_blocks_rehash_and_old_session(self):
        original = auth._HASHER.verify
        def reset_then_return(encoded, password):
            result = original(encoded, password)
            self.reset()
            return result
        with patch.object(auth, '_HASHER', wraps=auth._HASHER) as mocked:
            mocked.verify.side_effect = reset_then_return
            mocked.check_needs_rehash.return_value = True
            with self.assertRaises(AuthError):
                self.auth.authenticate('PlayerOne', self.password, 'player')
        self.assertEqual(self.db.auth_sessions.count_documents({}), 0)
        self.assertTrue(auth._HASHER.verify(self.account()['password_hash'], self.replacement))

    def test_actor_authorization_is_rechecked_after_hashing(self):
        original = auth.hash_password
        def suspend_then_hash(password):
            encoded = original(password)
            self.db.accounts.update_one({'_id': self.admin}, {'$set': {'status': 'suspended'}})
            return encoded
        before = self.account()
        with patch.object(auth, 'hash_password', side_effect=suspend_then_hash):
            self.assert_domain('suspended', self.reset)
        self.assertEqual(self.account(), before)
        self.assertEqual(self.db.admin_audit.count_documents({}), 0)

    def test_concurrent_forms_have_one_winner_and_one_stale_result(self):
        revision = self.account()['revision']
        def save(name):
            try:
                self.edit(username=name, revision=revision)
                return 'success'
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ('FirstName', 'SecondName')))
        self.assertCountEqual(results, ['success', 'stale_account'])
        self.assertEqual(self.account()['revision'], revision + 1)
        self.assertEqual(self.db.admin_audit.count_documents({'action': 'edit_account'}), 1)

    def test_concurrent_admin_suspensions_cannot_remove_last_active_admin(self):
        self.db.accounts.update_one({'_id': self.other}, {'$set': {'role': 'admin'}})
        expected = {a: self.account(a)['revision'] for a in (self.admin, self.other)}
        def suspend(pair):
            actor, target = pair
            try:
                self.edit(target=target, actor=actor, status='suspended', revision=expected[target])
                return 'success'
            except DomainError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(suspend, ((self.admin, self.other), (self.other, self.admin))))
        self.assertEqual(results.count('success'), 1)
        self.assertEqual(self.db.accounts.count_documents({'role': 'admin', 'status': 'active'}), 1)


if __name__ == '__main__':
    unittest.main()
