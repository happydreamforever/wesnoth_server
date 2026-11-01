"""Actual protocol5 bridge and paid native Rooms, disposable MongoDB and TLS peers.

This executes the native lobby but does not stand in for native combat or LDPlayer.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from uuid import uuid4

import test_unified_native as base
import test_individual_native as room_base
import test_admin_rooms_native as admin_fixture
from test_individual_native import node, serialize, descendants
from alliance.battle_wire import Node, parse
from alliance.court.schema import bootstrap_court_schema
from alliance.court.service import CourtService


class CourtPeer(base.Peer):
    def rpc(self, op, body, token=None, version=5):
        return super().rpc(op, body, token, version)


class CourtNative(room_base.Individual):
    connections_allowed = 160
    until_inventory = admin_fixture.NativeAdminRooms.until_inventory
    operator = admin_fixture.NativeAdminRooms.operator
    close_from_inventory = admin_fixture.NativeAdminRooms.close_from_inventory
    schema_bootstrap = staticmethod(bootstrap_court_schema)
    service_class = CourtService

    def peer(self, port=15001):
        peer = CourtPeer(port, self.profile)
        self.peers.append(peer)
        return peer

    def court(self, api, token, operation, payload):
        result = api.rpc('court_command', {'version': 1, 'operation': operation,
            'payload': {'command_id': str(uuid4()), **payload}}, token)
        self.assertTrue(result['ok'], result)
        return result['data']['data']

    def account(self, owned=True):
        api, token, account = super().account(owned)
        self.domain._tx(lambda session: self.domain._wallet_credit('personal', account['id'], 100,
            'fixture:' + account['id'], 'Explicit native test funding', session))
        return api, token, account

    def consent(self, api, token, kind, game=''):
        quote = api.rpc('court_query', {'version': 1, 'query': 'room_quote', 'payload': {}}, token)
        self.assertTrue(quote['ok'], quote)
        return self.court(api, token, 'room_consent', {'kind': kind, 'game_id': game,
            'price_revision': quote['data']['data']['price_revision'], 'confirmation': 'confirmed'})['ticket']

    def balance(self, account):
        return self.domain._wallet_public('personal', account['id'])

    def lobby(self, token, api, account):
        ticket = api.rpc('casual_ticket', {}, token)
        self.assertTrue(ticket['ok'], ticket)
        peer = self.peer(15000)
        greeting = peer.until('version')
        self.assertIn('alliance_protocol="5"', greeting)
        self.assertIn('implementation_release="1192626"', greeting)
        peer.send(base.wml('version', {'version': '1.19.26'})); peer.until('mustlogin')
        peer.send(base.wml('login', {'username': account['username'], 'alliance_ticket': ticket['data']['ticket']}))
        peer.until('join_lobby'); peer.until('gamelist')
        return peer, ticket['data']['ticket']

    def create_room(self, count=2, gold=100, turns=20, name='Global test room', map_name='Global fixture map'):
        api, token, actor = self.account()
        peer, _ = self.lobby(token, api, actor)
        fee = self.consent(api, token, 'create')
        peer.send(base.wml('create_game', {'name': name, 'individual_room': 'yes', 'court_fee_ticket': fee}))
        initial = parse(peer.until('alliance_game')).one('alliance_game')
        game = initial.attrs['id']
        level = Node()
        level.attrs['version'] = '1.19.26'
        level.children.append(node('multiplayer', mp_scenario='individual_test', mp_scenario_name=map_name,
            mp_era='era_default', shuffle_sides='no', observer='no', mp_fog='yes', mp_shroud='no',
            mp_countdown='no', mp_countdown_init_time=300, mp_countdown_reservoir_time=300,
            mp_countdown_turn_bonus=30, mp_countdown_action_bonus=0))
        scenario = node('scenario', id='individual_test', individual_room='yes', name=map_name,
            map_data='1 Gg,Gg,2 Gg\nGg,Gg,Gg\nGg,Gg,Gg', turns=turns)
        for index in range(1, count + 1):
            side = node('side', side=index, controller='human', player_id=actor['username'] if index == 1 else '',
                current_player=actor['username'] if index == 1 else '', team_name=index, allow_player='yes',
                gold=gold, income=2, village_gold=2, village_support=1, fog='yes', shroud='no')
            side.children.append(node('leader', type='Spearman', canrecruit='yes', random_traits='no'))
            scenario.children.append(side)
        level.children.append(scenario)
        peer.send(serialize(level))
        context = self.context(peer)
        return {'api': api, 'token': token, 'actor': actor, 'peer': peer, 'game': game,
                'id': int(context.attrs['room_id']), 'level': level, 'context': context, 'actors': {1: actor}, 'selected': {}}

    def join_room(self, room):
        api, token, actor = self.account()
        peer, _ = self.lobby(token, api, actor)
        listing = self.snapshot(peer, room['id'])
        self.assertIsNotNone(listing)
        fee = self.consent(api, token, 'join', room['game'])
        self.assertEqual(listing.attrs['court_game_id'], room['game'])
        peer.send(base.wml('join', {'id': room['id'], 'observe': 'no', 'room_revision': listing.attrs['room_revision'], 'court_fee_ticket': fee}))
        value = self.receive(peer, lambda value: bool(descendants(value, 'scenario')))
        scenario = descendants(value, 'scenario')[0]
        assigned = next(row for row in scenario.children if row.name == 'side' and row.attrs.get('player_id') == actor['username'])
        side = int(assigned.attrs['side'])
        room['actors'][side] = actor
        room['level'].children[1] = copy.deepcopy(scenario)
        context = self.context(room['peer'], int(room['context'].attrs['room_revision']) + 1)
        room['context'] = context
        return {'api': api, 'token': token, 'actor': actor, 'peer': peer, 'side': side}

    def test_court_bridge_current_protocol_and_old_version_refused(self):
        api, token, actor = self.account(False)
        result = api.rpc('court_query', {'version': 1, 'query': 'snapshot', 'payload': {}}, token)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['data']['data']['areas']), 128)
        self.assertEqual(result['data']['data']['heroes'], [])
        old = api.rpc('me', {}, token, version=4)
        self.assertFalse(old['ok'])
        self.assertEqual(old['status'], 426)
        with self.assertRaises(EOFError):
            api.rpc('court_command', {'version': 1, 'operation': 'set_rules',
                'payload': {'command_id': str(uuid4())}}, token)

    def test_room_waiting_creation_and_departure_release_all_fees(self):
        room = self.create_room(); guest = self.join_room(room)
        host_balance, guest_balance = self.balance(room['actor']), self.balance(guest['actor'])
        self.assertEqual(host_balance['held'], 5); self.assertEqual(guest_balance['held'], 2)
        guest['peer'].send(base.wml('leave_game'))
        self.receive(guest['peer'], lambda v: bool(descendants(v, 'gamelist')))
        self.assertEqual(self.balance(guest['actor'])['held'], 0)
        self.assertEqual(self.balance(guest['actor'])['available'], guest_balance['available'] + 2)
        room['peer'].send(base.wml('leave_game'))
        self.receive(room['peer'], lambda v: bool(descendants(v, 'gamelist')))
        self.assertEqual(self.balance(room['actor'])['held'], 0)
        self.assertEqual(self.balance(room['actor'])['available'], host_balance['available'] + 5)

    def test_room_full_ready_start_captures_exact_fees_without_rewards(self):
        room, host, guest = self.fully_selected()
        before = [self.balance(v['actor']) for v in (host, guest)]
        self.assertEqual(self.launch(room, host, guest).attrs['accepted'], 'yes')
        self.receive(guest['peer'], lambda v: bool(descendants(v, 'start_game')))
        for seat, balance in zip((host, guest), before):
            after = self.balance(seat['actor'])
            self.assertEqual(after['available'], balance['available'])
            self.assertEqual(after['held'], 0)
        game = self.db.casual_games.find_one({'_id': room['game']})
        self.assertEqual(len(game['players']), 2)
        self.assertEqual(self.db.court_room_admissions.count_documents({'game_id': room['game'], 'state': 'started'}), 2)
        self.assertIsNone(self.db.court_battle_receipts.find_one({'match_id': room['game']}))

    def test_room_missing_fee_is_refused_without_charging(self):
        api, token, actor = self.account()
        peer, _ = self.lobby(token, api, actor)
        before = self.balance(actor)
        peer.send(base.wml('create_game', {'name': 'No authorized fee', 'individual_room': 'yes'}))
        self.receive(peer, lambda v: any('fee' in row.attrs.get('message', '').lower()
            or 'refused' in row.attrs.get('message', '').lower() for row in descendants(v, 'message')))
        self.assertEqual(self.balance(actor), before)
        self.assertEqual(self.db.court_rooms.count_documents({'owner_id': actor['id']}), 0)

    def test_creator_departure_closes_waiting_room_and_refunds_guest(self):
        room = self.create_room(); guest = self.join_room(room)
        before = self.balance(guest['actor'])
        room['peer'].send(base.wml('leave_game'))
        self.receive(room['peer'], lambda v: bool(descendants(v, 'gamelist')))
        self.receive(guest['peer'], lambda v: bool(descendants(v, 'leave_game')))
        self.assertEqual(self.balance(guest['actor'])['held'], 0)
        self.assertEqual(self.balance(guest['actor'])['available'], before['available'] + 2)
        self.assertEqual(self.db.court_rooms.find_one({'_id': room['game']})['state'], 'closed')

    def test_current_error_is_specific_and_does_not_change_ownership(self):
        api, token, actor = self.account()
        before = self.db.account_heroes.find_one({'account_id': actor['id']})
        result = api.rpc('court_command', {'version': 1, 'operation': 'buy_hero', 'payload': {
            'command_id': str(uuid4()), 'hero_id': self.hero, 'price_revision': 0, 'confirmation': 'confirmed'}}, token)
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['data']['code'], 'hero_already_owned')
        self.assertEqual(self.db.account_heroes.find_one({'account_id': actor['id']}), before)
        self.assertTrue(api.rpc('me', {}, token)['ok'])

    def test_admin_running_room_close_refunds_only_selected_room(self):
        survivor = self.create_room(name='Retained waiting Room')
        room, host, guest = self.fully_selected()
        before = [self.balance(seat['actor']) for seat in (host, guest)]
        self.assertEqual(self.launch(room, host, guest).attrs['accepted'], 'yes')
        self.receive(guest['peer'], lambda v: bool(descendants(v, 'start_game')))
        self.close_from_inventory(self.operator(), room)
        self.assertEqual(self.balance(host['actor'])['available'], before[0]['available'] + 5)
        self.assertEqual(self.balance(guest['actor'])['available'], before[1]['available'] + 2)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': room['game']}), 0)
        self.assertEqual(self.balance(survivor['actor'])['held'], 5)
        self.assertIsNotNone(self.snapshot(survivor['peer'], survivor['id']))

    def test_actual_cpp_client_codec_snapshot_shop_and_command_receipt(self):
        binary = Path(os.environ['COURT_CLIENT_PROBE'])
        profile = self.root / 'court-public-profile.json'
        profile.write_text(json.dumps(self.profile))
        result = subprocess.run([str(binary), str(profile)], input=json.dumps({
            'username': 'Codec_' + uuid4().hex[:12], 'password': 'disposable-client-fixture-password'}),
            text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('COURT NATIVE CLIENT FLOW PASSED', result.stdout)

    def test_more_than_64_waiting_rooms_keep_running_room_and_all_leases(self):
        running, host, guest = self.fully_selected()
        self.assertEqual(self.launch(running, host, guest).attrs['accepted'], 'yes')
        self.receive(guest['peer'], lambda v: bool(descendants(v, 'start_game')))
        rooms = [self.create_room(name='Capacity fixture ' + str(index)) for index in range(65)]
        ids = [r['game'] for r in rooms] + [running['game']]
        before = {r['_id']: r['expires_at'] for r in self.db.court_rooms.find({'_id': {'$in': ids}})}
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            current = list(self.db.court_rooms.find({'_id': {'$in': ids}}))
            if len(current) == 66 and all(r['expires_at'] > before[r['_id']] for r in current):
                break
            time.sleep(.2)
        else:
            self.fail('Native Room heartbeat did not renew all 66 Rooms')
        self.assertEqual(sum(r['state'] == 'waiting' for r in current), 65)
        self.assertEqual(sum(r['state'] == 'playing' for r in current), 1)
        self.assertEqual(self.db.network_battle_reservations.count_documents({'run_id': running['game']}), 2)
        self.assertIsNotNone(self.snapshot(rooms[-1]['peer'], rooms[-1]['id']))


# Select only this release's tests; inherited helper tests describe archived protocol4.
def load_tests(loader, tests, pattern):
    selected = os.environ.get('COURT_NATIVE_TESTS', '').split(',')
    return unittest.TestSuite(CourtNative(name) for name in CourtNative.__dict__
        if name.startswith('test_') and (selected == [''] or name in selected))
