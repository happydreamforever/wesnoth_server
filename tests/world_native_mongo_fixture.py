"""Disposable real Mongo domain used by the actual native engine audit.

Only account/campaign ownership and one pre-battle soldier XP value are fixture
setup. The descriptor, permissions, native battle, proof and settlement all use
production paths. No existing runtime or external database is opened.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4
from pymongo import MongoClient
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService, DomainError
from alliance.heroes import spent_experience
from alliance.schema import bootstrap_schema
from alliance.world import bootstrap_world_schema


class MongoNativeFixture:
    def __init__(self, output, mission):
        self.finished = None
        self.receipt = None
        self.output = Path(output)
        directory = self.output / 'mongodb'
        directory.mkdir()
        self.process = subprocess.Popen(['mongod', '--dbpath', str(directory),
            '--bind_ip', '127.0.0.1', '--port', '27019', '--replSet', 'native_world_fixture',
            '--wiredTigerCacheSizeGB', '0.25', '--logpath', str(directory / 'mongodb.log')],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.client = MongoClient('mongodb://127.0.0.1:27019/?directConnection=true',
            tz_aware=True, serverSelectionTimeoutMS=500)
        try:
            for attempt in range(80):
                try:
                    self.client.admin.command('ping')
                    break
                except Exception:
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable native database did not start.')
            self.client.admin.command('replSetInitiate', {'_id': 'native_world_fixture',
                'members': [{'_id': 0, 'host': '127.0.0.1:27019'}]})
            for attempt in range(100):
                if self.client.admin.command('hello').get('isWritablePrimary'):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Disposable native replica set did not become primary.')
            self.client.close()
            self.client = MongoClient('mongodb://127.0.0.1:27019/?replicaSet=native_world_fixture',
                tz_aware=True, serverSelectionTimeoutMS=5000)
            assert self.client.admin.command('hello')['isWritablePrimary']
            self.db = self.client['alliance_native_' + uuid4().hex]
            bootstrap_schema(self.db)
            bootstrap_auth_schema(self.db)
            bootstrap_world_schema(self.db)
            self.domain = AllianceService(self.db)
            self.auth = AuthService(self.db)
            password = secrets.token_urlsafe(32)
            self.actor = self.domain.register('NativePlayer', hash_password(password))['_id']
            self.hero_id, self.form_id = 'konrad', 'konrad_05f7156385b9'
            self.initial_hero_xp = spent_experience(5)
            self.db.account_heroes.insert_one({'_id': str(uuid4()), 'account_id': self.actor,
                'hero_id': self.hero_id, 'forms': [self.form_id],
                'total_experience': self.initial_hero_xp, 'revision': 0})
            self.command('company_initialize')
            spear = self.db.company_soldiers.find_one({'owner_id': self.actor, 'unit_type': 'Spearman'})
            self.db.company_soldiers.update_one({'_id': spear['_id']}, {'$set': {'xp': 41}})
            soldiers = list(self.db.company_soldiers.find({'owner_id': self.actor,
                'unit_type': {'$in': ['Spearman', 'Bowman', 'Dwarvish Fighter', 'Elvish Shaman']}}).sort('unit_type', 1))
            self.command('company_select', hero_id=self.hero_id, form_id=self.form_id,
                soldier_ids=[s['_id'] for s in soldiers], bracket='scout')
            self.run = self.command('company_expedition', mission_id=mission)['battle']['id']
            self.worker_id = str(uuid4())
            self.descriptor = self.domain.world_worker_acquire(self.worker_id)
            assert self.descriptor['run_id'] == self.run
            self.generation = self.descriptor['generation']
            self.token = self.auth.authenticate('NativePlayer', password, 'player')['token']
            self.before_soldiers = {s['_id']: s for s in self.db.company_soldiers.find({'owner_id': self.actor})}
            assert self.db.network_battle_reservations.count_documents({'run_id': self.run}) == 1
            assert self.db.world_settlements.count_documents({}) == 0
        except BaseException:
            self.close()
            raise

    def __getattr__(self, name):
        return getattr(self.domain, name)

    def command(self, operation, **payload):
        if operation != 'company_initialize':
            payload['expected_revision'] = self.db.companies.find_one({'_id': self.actor})['revision']
        payload['command_id'] = str(uuid4())
        return self.domain.world_command(self.actor, operation, payload)['data']

    def world_worker_finish(self, run, worker, generation, evidence):
        receipt = self.domain.world_worker_finish(run, worker, generation, evidence)
        if self.db.world_contracts.find_one({'_id': run})['state'] == 'completed':
            self.finished = deepcopy(evidence)
            self.receipt = deepcopy(receipt)
        return receipt

    def verify(self):
        assert self.finished is not None and self.receipt is not None
        assert self.db.world_contracts.find_one({'_id': self.run})['state'] == 'completed'
        def repeat(_):
            return self.domain.world_worker_finish(self.run, self.worker_id, self.generation, self.finished)
        with ThreadPoolExecutor(2) as pool:
            receipts = list(pool.map(repeat, range(2)))
        assert all(receipt == self.receipt for receipt in receipts)
        conflicting = deepcopy(self.finished)
        conflicting['ledger_sha256'] = 'f' * 64
        try:
            self.domain.world_worker_finish(self.run, self.worker_id, self.generation, conflicting)
        except DomainError as error:
            assert error.code == 'result_conflict'
        else:
            raise AssertionError('Conflicting duplicate native proof was accepted.')
        assert self.db.world_settlements.count_documents({}) == 1
        assert self.db.network_battle_reservations.count_documents({'run_id': self.run}) == 0
        assert self.db.company_asset_locks.count_documents({'run_id': self.run}) == 0
        expected_xp = 20 if self.finished['winner_team_id'] == self.actor else 10
        after_hero = self.db.account_heroes.find_one({'account_id': self.actor, 'hero_id': self.hero_id})
        assert after_hero['total_experience'] == self.initial_hero_xp + expected_xp
        soldier_values = []
        for entry in self.finished['units']:
            if entry['instance_id'].startswith('hero:'):
                continue
            before = self.before_soldiers[entry['instance_id']]
            after = self.db.company_soldiers.find_one({'_id': entry['instance_id']})
            assert (after['unit_type'], after['xp'], after['total_earned']) == (
                entry['final_type'], entry['final_xp'], before['total_earned'] + entry['earned_xp'])
            soldier_values.append({k: entry[k] for k in ('final_type', 'earned_xp', 'final_xp', 'dead', 'deployed')})
        replay = self.domain.world_replay_authorize(self.actor, self.run)
        assert replay['replay_sha256'] == self.finished['replay_sha256']
        outsider = self.domain.register('NativeOutsider', hash_password(secrets.token_urlsafe(32)))['_id']
        try:
            self.domain.world_replay_authorize(outsider, self.run)
        except DomainError as error:
            assert error.code == 'forbidden'
        else:
            raise AssertionError('Unrelated account received the native replay.')
        wounds = self.db.company_wounds.count_documents({'owner_id': self.actor})
        self.command('company_rest')
        assert self.db.company_wounds.count_documents({'owner_id': self.actor}) == 0
        assert self.db.account_heroes.find_one({'account_id': self.actor})['total_experience'] == after_hero['total_experience']
        return {'database': 'actual MongoDB replica set', 'account_authentication': 'production AuthService',
            'fixture_setup': 'Disposable account with earned Konrad form at permanent level 5; one starter Spearman begins at 41 XP. No battle result or post-battle XP was fabricated.',
            'production_descriptor': True, 'production_worker_lease': True, 'production_atomic_settlement': True,
            'settlements': 1, 'concurrent_matching_duplicates': 2, 'conflicting_duplicate_rejected': True,
            'hero_xp_before': self.initial_hero_xp, 'hero_xp_awarded': expected_xp,
            'hero_xp_after': after_hero['total_experience'], 'soldiers': soldier_values,
            'reservations_released': True, 'asset_locks_released': True,
            'unrelated_replay_rejected': True, 'company_rest_wounds_cleared': wounds}

    def close(self):
        if getattr(self, 'client', None) is not None:
            self.client.close()
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=30)
