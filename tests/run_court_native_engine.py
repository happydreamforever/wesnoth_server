"""Actual Court native encounter, production MongoDB/auth and retained replay.

Run in the cached host-engine container with networking disabled. Mount /client,
/server and /gamedata read-only; /out is the fresh Court worker output. Companion
human seats run native AI explicitly, so this is not multiple-human usability.
"""
from __future__ import annotations
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, '/server')
from pymongo import MongoClient
from alliance.auth import AuthService, hash_password
from alliance.court.schema import bootstrap_court_schema
from alliance.court.service import CourtService
from alliance.court.battles import DEFAULT_BATTLE_SETTINGS
from alliance.domain import DomainError
from alliance.heroes import spent_experience
from alliance.world_worker import WorldWorkerSupervisor, canonical
from alliance.world_execution import handle_world
from alliance.battle_wire import receive, send, message
from tools.alliance_transport import prepare_identity


class Fixture:
    def __init__(self, output, case):
        self.finished = self.receipt = None
        self.shift = timedelta()
        self.output, self.case = output, case
        directory = output / 'mongodb'
        directory.mkdir()
        self.process = subprocess.Popen(['mongod', '--dbpath', str(directory), '--bind_ip', '127.0.0.1',
            '--port', '27019', '--replSet', 'court_native_fixture', '--wiredTigerCacheSizeGB', '0.25',
            '--logpath', str(directory / 'mongodb.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.client = MongoClient('mongodb://127.0.0.1:27019/?directConnection=true',
            tz_aware=True, serverSelectionTimeoutMS=500)
        try:
            for _ in range(80):
                try:
                    self.client.admin.command('ping')
                    break
                except Exception:
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable MongoDB did not start.')
            self.client.admin.command('replSetInitiate', {'_id': 'court_native_fixture',
                'members': [{'_id': 0, 'host': '127.0.0.1:27019'}]})
            for _ in range(100):
                if self.client.admin.command('hello').get('isWritablePrimary'):
                    break
                time.sleep(.1)
            self.client.close()
            self.client = MongoClient('mongodb://127.0.0.1:27019/?replicaSet=court_native_fixture',
                tz_aware=True, serverSelectionTimeoutMS=5000)
            self.db = self.client['alliance_court_native_' + uuid4().hex]
            bootstrap_court_schema(self.db)
            self.domain = CourtService(self.db, clock=lambda: datetime.now(timezone.utc) + self.shift)
            self.auth = AuthService(self.db)
            self.actors, self.tokens, self.teams = [], {}, []
            for index in range(2):
                password = secrets.token_urlsafe(32)
                actor = self.domain.register('CourtNative' + str(index), hash_password(password))['_id']
                self.actors.append(actor)
                self.tokens[actor] = self.auth.authenticate('CourtNative' + str(index), password, 'player')['token']
                self.db.account_heroes.insert_one(dict(_id=str(uuid4()), account_id=actor, hero_id='konrad',
                    forms=['konrad_05f7156385b9'], total_experience=spent_experience(5), revision=0))
                team = str(uuid4())
                self.db.court_teams.insert_one(dict(_id=team, name='Native Team ' + str(index),
                    name_key='native team ' + str(index), area_id='A001', captain_id=actor,
                    members=[{'account_id': actor, 'joined_at': self.domain._now()}], status='active',
                    experience=0, level=1, revision=0, allowances={}))
                self.domain._tx(lambda session, team=team: self.domain._wallet_credit(
                    'team', team, 1000, 'fixture:' + team, 'fixture_setup', session))
                self.teams.append(team)
            self.castle = self.db.court_castles.find_one({'area_id': 'A001', 'role': 'normal', 'enabled': True})['_id']
            if case == 'standing':
                offer = self.command(self.actors[1], 'defense_consent', hero_id='konrad',
                    form_id='konrad_05f7156385b9', faction='Rebels', confirmed=True)['defense']
                self.command(self.actors[1], 'set_defense', defense_id=offer.get('id', offer.get('_id')),
                             expected_revision=0, confirmed=True)
                self.db.court_castles.update_one({'_id': self.castle}, {'$set': {'owner_team_id': self.teams[1]}})
            if case in ('neutral', 'standing'):
                self.run = self.command(self.actors[0], 'attack', castle_id=self.castle, expected_revision=0,
                    hero_id='konrad', form_id='konrad_05f7156385b9', faction='Loyalists', price_revision=0)['match']['id']
                if case == 'standing':
                    self.shift = timedelta(seconds=121)
                    self.domain.court_tick()
            else:
                castle = self.db.court_castles.find_one({'area_id': 'A001', 'role': 'plan'})['_id']
                self.db.court_castles.update_one({'_id': castle}, {'$set': {'enabled': True}})
                self.run = self.command(self.actors[0], 'create_plan', castle_id=castle, opponent_team_id=self.teams[1],
                    settings={**deepcopy(DEFAULT_BATTLE_SETTINGS), 'items': case == 'items'}, start_delay_minutes=5, price_revision=0)['match']['id']
                self.command(self.actors[1], 'approve_plan', match_id=self.run, price_revision=0)
                for actor in self.actors:
                    self.command(actor, 'join_match', match_id=self.run)
                    self.command(actor, 'select_hero', match_id=self.run,
                        hero_id='konrad', form_id='konrad_05f7156385b9', faction='Loyalists')
                if case == 'items':
                    for actor, item in zip(self.actors, ('healing_draught', 'remedy')):
                        self.domain._tx(lambda session, actor=actor, item=item:
                            self.domain._inventory_mutate(actor, item, 1, 0, session))
                        self.command(actor, 'select_item', match_id=self.run, item_id=item)
                for actor in self.actors:
                    self.command(actor, 'ready', match_id=self.run, ready=True)
                self.shift = timedelta(minutes=6)
                self.domain.court_tick()
            self.worker_id = str(uuid4())
            self.domain.court_capacity_available(self.worker_id)
            self.descriptor = self.domain.court_worker_acquire(self.worker_id)
            assert self.descriptor and self.descriptor['run_id'] == self.run
            self.generation = self.descriptor['generation']
            self.initial_xp = {actor: self.db.account_heroes.find_one({'account_id': actor})['total_experience']
                               for actor in self.actors}
        except BaseException:
            self.close()
            raise

    def command(self, actor, operation, **payload):
        payload['command_id'] = str(uuid4())
        if 'match_id' in payload:
            payload['expected_revision'] = self.db.court_matches.find_one({'_id': payload['match_id']})['revision']
        return self.domain.court_command(actor, {'version': 1, 'operation': operation, 'payload': payload})['data']

    def __getattr__(self, name):
        return getattr(self.domain, name)

    def world_worker_finish(self, run, worker, generation, evidence):
        receipt = self.domain.court_worker_finish(run, worker, generation, evidence)
        if self.db.court_matches.find_one({'_id': run})['state'] == 'completed':
            self.finished, self.receipt = deepcopy(evidence), deepcopy(receipt)
        return receipt

    def verify(self):
        assert self.finished and self.receipt
        assert self.receipt['native_verified'] and self.receipt['genuine_combat']
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.domain.court_worker_finish(self.run, self.worker_id,
                self.generation, self.finished), range(2)))
        assert results == [self.receipt, self.receipt]
        changed = {**self.finished, 'replay_sha256': 'f' * 64}
        try:
            self.domain.court_worker_finish(self.run, self.worker_id, self.generation, changed)
        except DomainError as error:
            assert error.code == 'result_conflict'
        else:
            raise AssertionError('Conflicting native result accepted.')
        rewards = {row['account_id']: row['experience'] for row in self.receipt['hero_rewards']}
        for actor in self.actors:
            after = self.db.account_heroes.find_one({'account_id': actor})['total_experience']
            assert after == self.initial_xp[actor] + rewards.get(actor, 0)
        if self.case == 'standing':
            assert self.actors[1] not in rewards, 'Offline template granted personal XP.'
        if self.case == 'items':
            assert self.db.court_item_holds.count_documents({'run_id': self.run, 'state': 'consumed'}) == 2
            assert all(row['available'] == 0 and row['held'] == 0 for row in self.db.court_inventory.find({}))
        assert self.db.court_battle_receipts.count_documents({}) == 1
        assert self.db.network_battle_reservations.count_documents({'run_id': self.run}) == 0
        replay = self.domain.court_replay_authorize(self.actors[0], self.run)
        assert replay['replay_sha256'] == self.finished['replay_sha256']
        return dict(actual_replica_set=True, production_auth=True, production_contract=True,
            native_settlement=True, duplicate_receipts_identical=True, conflicting_duplicate_rejected=True,
            hero_rewards=self.receipt['hero_rewards'], team_rewards=self.receipt['team_rewards'],
            captured_castle_id=self.receipt['captured_castle_id'], reservations_released=True)

    def close(self):
        if getattr(self, 'client', None):
            self.client.close()
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=30)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=('neutral', 'standing', 'witness', 'items'), default='neutral')
    parser.add_argument('--engine', type=Path, default=Path('/out/world-worker'))
    parser.add_argument('--reconnect', action='store_true')
    parser.add_argument('--worker-restart', action='store_true')
    args = parser.parse_args()
    output = Path('/out') / ('court-native-' + args.case + '-' + uuid4().hex)
    output.mkdir()
    fixture = Fixture(output, args.case)
    identity = output / 'identity'
    prepare_identity(identity, '127.0.0.1', 15001, Path('/usr/bin/openssl'))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(identity / 'server-cert.pem', identity / 'server-key.pem')
    daemon = SimpleNamespace(storage=output / 'battles', domain=fixture, auth=fixture.auth, court=True)
    supervisor = WorldWorkerSupervisor(daemon, identity, args.engine, Path('/gamedata'))
    errors, children, logs = [], [], []
    async def handle(reader, writer):
        try:
            assert await reader.readexactly(4) == b'\0\0\0\1'
            writer.write(b'\0' * 4)
            await writer.drain()
            await writer.start_tls(context)
            root = await receive(reader, 20)
            await handle_world(supervisor, reader, writer, root.one('world_join'))
        except asyncio.IncompleteReadError:
            pass
        except Exception as error:
            errors.append(type(error).__name__ + ': ' + str(error))
            print('COURT FIXTURE WIRE ERROR', errors[-1], flush=True)
        finally:
            writer.close()
    server = await asyncio.start_server(handle, '127.0.0.1', 15002)
    worker = asyncio.create_task(supervisor.launch(fixture.descriptor, fixture.worker_id))
    while fixture.run not in supervisor.rooms:
        await asyncio.sleep(.05)
    async def companion(actor, replay=False):
        own = output / ('companion-' + str(len(children)))
        own.mkdir()
        (own / 'userdata').mkdir()
        environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
            WESNOTH_WORLD_COMPANION_PROFILE=str(identity / 'public-profile.json'))
        log = (own / 'engine.log').open('wb')
        logs.append(log)
        child = await asyncio.create_subprocess_exec(str(args.engine), '/gamedata', '--userdata-dir',
            str(own / 'userdata'), '--nogui', '--multiplayer', '--nosound', '--noaddons',
            '--no-log-to-file', '--log-none=audio', stdin=asyncio.subprocess.PIPE,
            stdout=log, stderr=asyncio.subprocess.STDOUT, env=environment)
        children.append(child)
        admission = dict(run_id=fixture.run, account_id=actor, token=fixture.tokens[actor])
        if replay:
            admission['intent'] = 'replay'
        child.stdin.write(canonical(admission) + b'\n')
        await child.stdin.drain()
        child.stdin.close()
        return child
    try:
        for actor in fixture.descriptor['required_humans']:
            await companion(actor)
        retired = 0
        if args.reconnect:
            room = supervisor.rooms[fixture.run]
            async def reconnect():
                while room.count < 24 and not worker.done():
                    await asyncio.sleep(.02)
                assert not worker.done()
                actor = fixture.descriptor['required_humans'][0]
                children[0].kill()
                await children[0].wait()
                while actor in room.peers:
                    await asyncio.sleep(.02)
                count = room.count
                await asyncio.sleep(.4)
                assert room.count == count
                await companion(actor)
            await asyncio.wait_for(reconnect(), 120)
            retired = 1
        if args.worker_restart:
            room = supervisor.rooms[fixture.run]
            while room.count < 24 and not worker.done():
                await asyncio.sleep(.02)
            assert not worker.done()
            original_generation = fixture.generation
            supervisor.children[fixture.run].kill()
            await asyncio.wait_for(worker, 30)
            paused = fixture.db.court_matches.find_one({'_id': fixture.run})
            assert paused['state'] == 'paused' and paused['pause_reason'] == 'worker_unavailable'
            assert not fixture.finished and fixture.db.court_battle_receipts.count_documents({}) == 0
            for child in children:
                if child.returncode is None:
                    child.kill()
                await child.wait()
            retired = len(children)
            while room.peers:
                await asyncio.sleep(.02)
            fixture.shift += timedelta(seconds=91)
            fixture.domain.court_tick()
            resumed = fixture.domain.court_worker_acquire(fixture.worker_id)
            assert resumed['generation'] == original_generation
            supervisor.rooms.clear()  # Reconstruct the actual durable command journal.
            worker = asyncio.create_task(supervisor.launch(resumed, fixture.worker_id))
            while fixture.run not in supervisor.rooms:
                await asyncio.sleep(.02)
            for actor in fixture.descriptor['required_humans']:
                await companion(actor)
        await asyncio.wait_for(asyncio.gather(worker, *(child.wait() for child in children)), 300)
        assert all(child.returncode == 0 for child in children[retired:])
        assert fixture.finished, errors
        room = supervisor.rooms[fixture.run]
        assert room.count > 10 and any('attack' in str(packet) for packet in room.history)
        verified = fixture.verify()
        supervisor.rooms.clear()
        playback = await companion(fixture.actors[0], True)
        await asyncio.wait_for(playback.wait(), 120)
        assert playback.returncode == 0
        result = dict(scope='Actual native Court combat with separately authenticated AI companions; not multiple-human usability',
            case=args.case, native_combat=True, replay_after_cache_loss=True, human_reconnect=args.reconnect,
            worker_crash_recovery=args.worker_restart,
            item_fixture=args.case == 'items',
            command_count=room.count, wire_errors=errors, native_evidence=fixture.finished, verification=verified)
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('ACTUAL NATIVE COURT COMBAT, SETTLEMENT AND REPLAY PASSED', output, flush=True)
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
                await child.wait()
        for log in logs:
            log.close()
        await supervisor.close()
        server.close()
        await server.wait_closed()
        fixture.close()


if __name__ == '__main__':
    asyncio.run(main())
