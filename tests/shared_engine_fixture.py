"""Disposable-only 2v2/3v3/4v4 shared daemon fixture.

Start with tests/start_shared_engine_fixture.py inside a network-disabled
container. Its fresh test-only MongoDB must already be a primary on27019.
This helper never discovers the game runtime or .env. The private fixture
contains disposable session tokens and must not be printed or published.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from pymongo import MongoClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.auth import AuthService, bootstrap_auth_schema, hash_password
from alliance.domain import AllianceService
from alliance.heroes import load_catalog
from alliance.rules import MAPS
from alliance.schema import bootstrap_schema
from alliance.battle_daemon import BattleDaemon, tls_context
import alliance.battle_daemon as fixture_daemon
from tools.alliance_transport import prepare_identity

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--flexible', action='store_true')
    parser.add_argument('--observers', action='store_true')
    parser.add_argument('--turns', type=int, default=-1)
    parser.add_argument('--size', type=int, choices=(2, 3, 4), required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    uri = os.environ['ALLIANCE_TEST_MONGO_URI']
    target = urlsplit(uri)
    if target.hostname != '127.0.0.1' or target.port != 27019 or parse_qs(target.query).get('replicaSet') != ['shared_fixture']:
        raise RuntimeError('Only the disposable local replica-set fixture is accepted')
    root = args.root
    if not root.is_absolute() or root.exists():
        raise RuntimeError('A new absolute fixture directory is required')
    os.umask(0o077)
    root.mkdir(parents=True)
    map_id = {2: 'isars-cross', 3: 'hexcake', 4: 'mokena-prairie'}[args.size]
    expected_sides = [list(sides) for sides in MAPS[map_id]['sides']]
    if MAPS[map_id]['size'] != args.size:
        raise RuntimeError('Fixture map size differs from current production rules')
    profile, _ = prepare_identity(root / 'identity', '127.0.0.1', 15001, Path('/usr/bin/openssl'))
    client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    name = 'alliance_test_shared_engine_' + uuid4().hex
    db = client[name]
    server = None
    settlement = None
    domain = None
    run_id = None
    try:
        bootstrap_schema(db); bootstrap_auth_schema(db)
        domain = AllianceService(db); auth = AuthService(db)
        password = 'Disposable-engine-fixture-password-123'
        encoded = hash_password(password)
        actors = [domain.register('EnginePlayer' + str(n), encoded)['_id'] for n in range(1, (2 if args.flexible else args.size * 2) + 1)]
        catalogue, digest = load_catalog()
        campaign = next(row for row in catalogue['campaigns'] if row['id'] == 'Heir_To_The_Throne_Classic')
        alias = next(row for row in campaign['aliases'] if row['hero_id'] == 'konrad')
        form = next(row['form_id'] for row in alias['forms'] if row['source_type'] == 'Fighter' and row['source_variation'] == '')
        other_alias = next(row for row in campaign['aliases'] if row['hero_id'] == 'delfador')
        other_form = other_alias['forms'][0]['form_id']
        # Exercise the actual story checkpoint transaction instead of inserting
        # account_heroes or retaining the removed generic starter leader.
        for actor in actors:
            assert domain.get_account(actor)['heroes'] == []
            story = domain.story_begin(actor, campaign['id'], catalogue['version'], digest)
            checkpoint = {'run_id': story['run_id'], 'checkpoint_id': str(uuid4()), 'sequence': 0,
                'scenario_id': campaign['first_scenario'], 'next_scenario_id': '', 'outcome': 'win',
                'nonce': story['nonce'], 'replay_sha256': 'a' * 64,
                'heroes': [{'hero_id': 'konrad', 'unit_id': alias['unit_id'], 'form_id': form,
                            'unlocked_forms': [form], 'earned_experience': 7},
                           {'hero_id': 'delfador', 'unit_id': other_alias['unit_id'], 'form_id': other_form,
                            'unlocked_forms': [other_form], 'earned_experience': 7}]}
            unlocked = domain.story_checkpoint(actor, checkpoint)
            assert len(unlocked['heroes']) == 2 and all(row['hero_level'] == 2 for row in unlocked['heroes'])
            assert domain.story_checkpoint(actor, checkpoint) == unlocked
        teams = []
        lineups = []
        for team_number in range(2):
            lineup = [actors[team_number]] if args.flexible else actors[team_number * args.size:(team_number + 1) * args.size]
            team = domain.create_team(lineup[0], 'EngineTeam' + str(team_number))['_id']
            teams.append(team); lineups.append(lineup)
            for actor in lineup[1:]:
                domain.request_join(actor, team)
                domain.approve_member(lineup[0], team, actor)
        observers=[]
        if args.observers:
            if not args.flexible: raise RuntimeError('Observer fixture requires flexible plan')
            observer=domain.register('EngineObserver',encoded)['_id']
            domain.request_join(observer,teams[0]);domain.approve_member(actors[0],teams[0],observer)
            login=auth.authenticate('EngineObserver',password,'player')
            observers.append({'account_id':observer,'username':'EngineObserver','token':login['token'],'side':0})
        if args.flexible:
            if args.size != 3: raise RuntimeError('Flexible engine fixture uses Hexcake')
            from alliance.flexible import DEFAULT_SETTINGS
            settings = {**DEFAULT_SETTINGS, 'gold': 125, 'base_income': 4, 'observers': args.observers, 'turns': args.turns}
            slots = [dict(side=n, kind='open', account_id='', ai_faction='', ai_leader='') for n in range(1,7)]
            slots[0]['kind'] = 'closed'
            slots[4].update(kind='ai', ai_faction='Loyalists', ai_leader='Lieutenant')
            view = domain.directory_publish_plan(actors[0], teams[0], teams[1], map_id, settings, slots)
            slots[5]['kind'] = 'closed'
            slots[2].update(kind='ai', ai_faction='Rebels', ai_leader='Elvish Captain')
            view = domain.directory_edit_plan(actors[1], view['id'], view['revision'], map_id, settings, slots)
            for actor, side in zip(actors, (4,2)):
                view = domain.directory_join_plan(actor, view['id'], view['revision'], side)
                view = domain.directory_select_plan_hero(actor, view['id'], view['revision'], 'konrad', form)
            for actor in actors: view = domain.directory_approve_plan(actor, view['id'], view['revision'])
            for actor in actors: view = domain.directory_ready_plan(actor, view['id'], view['revision'], True)
            run_id = view['id']; battle = domain.get_run(run_id)
        else:
            battle = domain.create_battle(actors[0], teams[1], map_id, dict(zip(teams, lineups)))
            run_id = battle['_id']
            for actor in actors:
                domain.directory_select_hero(actor, run_id, 'konrad', form)
            for captain in (actors[0], actors[args.size]):
                domain.directory_approve_battle(captain, run_id)
            for actor in actors:
                domain.directory_battle_ready(actor, run_id, True)
        entries = []
        for actor in actors:
            account = domain.get_account(actor)
            session = auth.authenticate(account['username'], password, 'player')
            entries.append({'account_id': actor, 'username': account['username'], 'token': session['token'],
                            'side': next(p['side'] for p in battle['participants'] if p['account_id'] == actor)})
        if args.observers:
            original_command = fixture_daemon.Room.command
            async def trace_observer_command(room, peer, packet):
                if peer.observer:
                    def tag_paths(node, prefix=''):
                        path=prefix + '/' + node.name
                        return [path, *(child_path for child in node.children for child_path in tag_paths(child,path))]
                    print('FIXTURE OBSERVER PACKET ' + ','.join(tag_paths(packet))[:4096], flush=True)
                return await original_command(room, peer, packet)
            fixture_daemon.Room.command = trace_observer_command
        fixture_daemon.CAPTAIN_COMMANDS_ENABLED = True
        context, _ = tls_context(root / 'identity')
        daemon = BattleDaemon(db, root / 'battles', context)
        room = await daemon.room(actors[0], run_id)
        current = room.record['battle']
        assert current['map']['id'] == map_id and current['map']['size'] == args.size
        assert all(team['approved'] and all(player['ready'] for player in team['players']) for team in current['teams'])
        assert [[p['side'] for p in team['players']] for team in current['teams']] == ([[4],[2]] if args.flexible else expected_sides)
        fixture = {'purpose': 'disposable-shared-engine-fixture', 'database': name, 'run_id': run_id,
                   'teams': teams, 'profile': profile, 'players': entries, 'observers': observers, 'battle': current,
                   'seed': room.record['seed'], 'generation': room.generation,
                   'size': args.size, 'map_id': map_id, 'captain_indices': [0, 1 if args.flexible else args.size], 'flexible': args.flexible,
                   'catalog_version': catalogue['version'], 'catalog_sha256': digest}
        fixture['hero'] = {'hero_id': 'konrad', 'form_id': form, 'hero_level': 2, 'total_experience': 27, 'unselected_hero_id': 'delfador'}
        with (root / 'private-fixture.json').open('x') as output:
            json.dump(fixture, output, indent=2)
        server = await asyncio.start_server(daemon.handle, '127.0.0.1', 15002)
        settlement = asyncio.create_task(daemon.settle_ready())
        print('DISPOSABLE SHARED ENGINE FIXTURE READY size=' + str(args.size) + ' map=' + map_id, flush=True)
        async with server:
            while not (root / 'stop').exists():
                await asyncio.sleep(.25)
            # Python 3.14 waits for accepted connections when leaving the
            # server context. Close only this fixture's owned room sockets.
            for owned_room in daemon.rooms.values():
                owned_room.freeze()
    finally:
        if settlement:
            settlement.cancel(); await asyncio.gather(settlement, return_exceptions=True)
        if server:
            server.close(); await server.wait_closed()
        if run_id and domain:
            (root / 'database-result.json').write_text(json.dumps({'run': domain.get_run(run_id), 'settlement': db.settlements.find_one({'_id': run_id})}, default=str, indent=2))
        client.drop_database(name); client.close()

asyncio.run(main())
