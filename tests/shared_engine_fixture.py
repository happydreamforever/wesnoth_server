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
        actors = [domain.register('EnginePlayer' + str(n), encoded)['_id'] for n in range(1, args.size * 2 + 1)]
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
            lineup = actors[team_number * args.size:(team_number + 1) * args.size]
            team = domain.create_team(lineup[0], 'EngineTeam' + str(team_number))['_id']
            teams.append(team); lineups.append(lineup)
            for actor in lineup[1:]:
                domain.request_join(actor, team)
                domain.approve_member(lineup[0], team, actor)
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
        fixture_daemon.CAPTAIN_COMMANDS_ENABLED = True
        context, _ = tls_context(root / 'identity')
        daemon = BattleDaemon(db, root / 'battles', context)
        room = await daemon.room(actors[0], run_id)
        current = room.record['battle']
        assert current['map']['id'] == map_id and current['map']['size'] == args.size
        assert all(team['approved'] and all(player['ready'] for player in team['players']) for team in current['teams'])
        assert [[p['side'] for p in team['players']] for team in current['teams']] == expected_sides
        fixture = {'purpose': 'disposable-shared-engine-fixture', 'database': name, 'run_id': run_id,
                   'teams': teams, 'profile': profile, 'players': entries, 'battle': current,
                   'seed': room.record['seed'], 'generation': room.generation,
                   'size': args.size, 'map_id': map_id, 'captain_indices': [0, args.size],
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
    finally:
        if settlement:
            settlement.cancel(); await asyncio.gather(settlement, return_exceptions=True)
        if server:
            server.close(); await server.wait_closed()
        if run_id and domain:
            (root / 'database-result.json').write_text(json.dumps({'run': domain.get_run(run_id), 'settlement': db.settlements.find_one({'_id': run_id})}, default=str, indent=2))
        client.drop_database(name); client.close()

asyncio.run(main())
