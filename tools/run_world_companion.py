"""Run an explicitly selected player's side through the verified native engine.

This is acceptance tooling for one LDPlayer. It does not impersonate another
player, choose readiness, or submit results: the independent World witness owns
settlement. The player's password and session travel only over pinned TLS and a
private child stdin pipe, never in arguments or diagnostic files.
"""
from __future__ import annotations
import argparse
import contextlib
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'wesnoth_client' / 'tools'))
from alliance.world_worker import bounded, canonical, native_engine_command, ordinary, write_json
from tools.build_world_worker import installed_worker
import run_android_alliance_companion as account_transport

# The coordinated shared helper supplies protocol 4 pinned-IP TLS framing.
if account_transport.WIRE_VERSION != 4:
    raise RuntimeError('The coordinated client companion helper is required.')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def select_battle(profile, token, actor):
    envelope = account_transport.account_request(profile, 'world_query',
        {'operation': 'battles', 'payload': {}}, token)
    if envelope.get('version') != 1 or envelope.get('actor_id') != actor:
        raise ValueError('battle_list_identity')
    rows = envelope['data']['items']
    if not isinstance(rows, list) or len(rows) > 30: raise ValueError('battle_list_bounds')
    eligible = [row for row in rows if row.get('state') in ('preparing', 'running', 'paused') and
        any(army.get('account_id') == actor and army.get('controller') == 'human' for army in row.get('armies', []))]
    if not eligible:
        print('No prepared battle is assigned to this player. Ready the army in the game first.', flush=True)
        return None
    names = {'company_border_patrol': 'Border Patrol', 'company_river_crossing': 'The River Crossing',
        'company_old_fortress': 'The Old Fortress', 'isars-cross': "Isar's Cross", 'hexcake': 'Hexcake',
        'mokena-prairie': 'Mokena Prairie'}
    for number, row in enumerate(eligible, 1):
        if not UUID.fullmatch(row.get('id', '')): raise ValueError('battle_identity')
        place = names.get(row.get('mission_id')) or names.get(row.get('map_id'), 'Team battle')
        print(f"{number}. {place} — {row['state']}", flush=True)
    choice = input('Battle number, or Enter to cancel: ').strip()
    if not choice: return None
    if not choice.isascii() or not choice.isdigit() or not 1 <= int(choice) <= len(eligible):
        raise ValueError('invalid_battle_choice')
    return eligible[int(choice) - 1]['id']


def run(args):
    if (args.battle_id and not UUID.fullmatch(args.battle_id)) or not re.fullmatch(r'[A-Za-z0-9_]{3,24}', args.username):
        raise ValueError('invalid_selection')
    worker = installed_worker()
    public = ordinary(args.profile)
    profile = account_transport.public_profile(bounded(public, 32768))
    if not sys.stdin.isatty(): raise ValueError('interactive_password_prompt_required')
    directory = ordinary(ROOT / 'diagnostics' / ('world-companion-' + uuid4().hex))
    directory.mkdir(mode=0o700)
    userdata = directory / 'userdata'
    userdata.mkdir(mode=0o700)
    token, child = None, None
    report = {'format': 1, 'mode': 'authenticated_native_ai_companion',
              'battle_id': args.battle_id, 'engine_exit': None, 'session_logout': 'not_issued'}
    try:
        print('Enter this player\'s password privately. The native companion controls only that player\'s assigned side.', flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Player password: ')
        try:
            token, account = account_transport.login(profile, args.username, password)
        finally:
            password = None
        battle_id = args.battle_id or select_battle(profile, token, account['id'])
        report['battle_id'] = battle_id
        if battle_id is None:
            report['selection_cancelled'] = True
            print('WORLD COMPANION CANCELLED. No battle or readiness was changed.', flush=True)
            return 0
        environment = os.environ.copy()
        environment.pop('WESNOTH_WORLD_WORKER_PROFILE', None)
        environment.pop('WESNOTH_WORLD_WORKER_OUTPUT', None)
        environment.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
            WESNOTH_WORLD_COMPANION_PROFILE=str(public))
        if os.name == 'nt':
            environment['PATH'] = str(Path(worker['executable']).parent) + os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32')
        command = native_engine_command(worker['executable'], worker['game_data'], userdata)
        with (directory / 'native.log').open('xb') as log:
            child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=environment)
            child.stdin.write(canonical({'run_id': battle_id, 'account_id': account['id'], 'token': token}) + b'\n')
            child.stdin.close()
            print('WORLD COMPANION RUNNING. Keep this window open. Ctrl+C stops only this companion.', flush=True)
            report['engine_exit'] = child.wait()
        if report['engine_exit'] != 0: raise ValueError('native_companion_interrupted')
        print('WORLD COMPANION FINISHED. Check the battle result in the game; this helper does not award rewards.', flush=True)
    finally:
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=10)
        if token:
            report['session_logout'] = 'unconfirmed'
            with contextlib.suppress(Exception):
                account_transport.account_request(profile, 'logout', {}, token)
                report['session_logout'] = 'confirmed'
            token = None
        write_json(directory / 'report.json', report)
        print('Saved companion report: ' + str(directory / 'report.json'), flush=True)
    return 0 if report['session_logout'] == 'confirmed' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--battle-id')
    parser.add_argument('--username', required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'runtime/alliance-transport/public-profile.json')
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print('WORLD COMPANION STOPPED. Reconnect the same player to continue the retained battle.', flush=True)
        return 2
    except Exception as error:
        print('WORLD COMPANION STOPPED: ' + type(error).__name__ + '. Check the selected player, battle and saved report.', flush=True)
        return 1


if __name__ == '__main__': raise SystemExit(main())
