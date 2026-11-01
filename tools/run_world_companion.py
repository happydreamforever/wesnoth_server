"""Run an explicitly selected player's side through the verified native engine.

This is acceptance tooling for one LDPlayer. It does not impersonate another
player, choose readiness, or submit results: the independent Court witness owns
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

# The coordinated shared helper supplies protocol 5 pinned-IP TLS framing.
if account_transport.WIRE_VERSION != 5:
    raise RuntimeError('The coordinated client companion helper is required.')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def court_query(profile, token, actor, query, payload):
    envelope = account_transport.account_request(profile, 'court_query',
        {'version': 1, 'query': query, 'payload': payload}, token)
    if envelope.get('version') != 1 or envelope.get('actor_id') != actor or not isinstance(envelope.get('data'), dict):
        raise ValueError('battle_list_identity')
    return envelope['data']


def eligible(row, actor):
    if not isinstance(row, dict) or not UUID.fullmatch(row.get('id', '')):
        raise ValueError('battle_identity')
    seats = row.get('seats')
    if not isinstance(seats, list) or len(seats) > 8:
        raise ValueError('battle_seat_bounds')
    return (row.get('state') in ('preparing', 'running', 'paused') and row.get('can_enter') is True
        and any(seat.get('account_id') == actor and seat.get('controller') == 'human' for seat in seats))


def validate_battle(profile, token, actor, battle_id):
    row = court_query(profile, token, actor, 'plan', {'match_id': battle_id}).get('match')
    if not eligible(row, actor) or row['id'] != battle_id:
        raise ValueError('battle_not_assigned')
    return battle_id


def select_battle(profile, token, actor):
    choices, after, seen = [], '', set()
    for page in range(50):
        payload = {'state': 'active', **({'after': after} if after else {})}
        data = court_query(profile, token, actor, 'plans', payload)
        rows = data.get('items')
        if not isinstance(rows, list) or len(rows) > 20:
            raise ValueError('battle_list_bounds')
        for row in rows:
            if row.get('id') in seen:
                raise ValueError('battle_list_duplicate')
            seen.add(row.get('id'))
            if eligible(row, actor):
                choices.append(row)
        after = data.get('next', '')
        if not after:
            break
        if not UUID.fullmatch(after):
            raise ValueError('battle_cursor')
    else:
        raise ValueError('battle_list_bounds')
    if not choices:
        print('No prepared Court battle is assigned to this player. Join a seat, choose a hero and Ready in the game first.', flush=True)
        return None
    names = {'weldyn-channel': 'Weldyn Channel', 'isars-cross': "Isar's Cross",
        'hexcake': 'Hexcake', 'mokena-prairie': 'Mokena Prairie'}
    for number, row in enumerate(choices, 1):
        place = names.get(row.get('settings', {}).get('map_id'), 'Court battle')
        print(f"{number}. {place} — {row['state']}", flush=True)
    choice = input('Battle number, or Enter to cancel: ').strip()
    if not choice:
        return None
    if not choice.isascii() or not choice.isdigit() or not 1 <= int(choice) <= len(choices):
        raise ValueError('invalid_battle_choice')
    return choices[int(choice) - 1]['id']


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
            print('COURT COMPANION CANCELLED. No battle or readiness was changed.', flush=True)
            return 0
        validate_battle(profile, token, account['id'], battle_id)
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
            print('COURT COMPANION RUNNING. Keep this window open. Ctrl+C stops only this companion.', flush=True)
            report['engine_exit'] = child.wait()
        if report['engine_exit'] != 0: raise ValueError('native_companion_interrupted')
        print('COURT COMPANION FINISHED. Check the battle result in the game; this helper does not award rewards.', flush=True)
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
        print('COURT COMPANION STOPPED. Reconnect the same player to continue the retained battle.', flush=True)
        return 2
    except Exception as error:
        print('COURT COMPANION STOPPED: ' + type(error).__name__ + '. Check the selected player, battle and saved report.', flush=True)
        return 1


if __name__ == '__main__': raise SystemExit(main())
