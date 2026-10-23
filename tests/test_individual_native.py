"""Actual global individual-room protocol against disposable MongoDB and wesnothd.

These peers execute the real TLS/account/server implementation. They do not
render Android controls or simulate native combat; that has a separate engine
integration fixture. Existing Native tests are reused as helpers, not counted
again by discovery.
"""
import copy
import socket
import time
import unittest

import test_unified_native as base
from alliance.battle_wire import Node, parse, serialize as raw_serialize


def serialize(value):
    value = copy.deepcopy(value)
    def ordered(row):
        row.attrs = dict(sorted(row.attrs.items()))
        for child in row.children: ordered(child)
    ordered(value)
    return raw_serialize(value)


def node(tag, **attrs):
    return Node(tag, {key: str(value) for key, value in attrs.items()})


def descendants(value, name):
    found = [value] if value.name == name else []
    for child in value.children:
        found.extend(descendants(child, name))
    return found


class Individual(base.Native):
    def receive(self, peer, predicate, limit=100):
        for _ in range(limit):
            value = parse(peer.receive())
            if predicate(value):
                return value
        self.fail('Expected individual-room packet missing')

    def context(self, peer, minimum=1):
        value = self.receive(peer, lambda value: any(
            row.attrs.get('individual_room') == 'yes' and int(row.attrs.get('room_revision', 0)) >= minimum
            and 'room_capacity' in row.attrs for row in descendants(value, 'alliance_game')))
        return next(row for row in descendants(value, 'alliance_game') if 'room_capacity' in row.attrs)

    def snapshot(self, peer, native_id):
        peer.send(base.wml('refresh_lobby'))
        value = self.receive(peer, lambda value: any(child.name == 'gamelist' for child in value.children))
        rooms = descendants(value, 'game')
        return next((row for row in rooms if row.attrs.get('id') == str(native_id)), None)

    def create_room(self, count=2, gold=100, turns=20):
        api, token, actor = self.account()
        peer, _ = self.lobby(token, api, actor)
        peer.send(base.wml('create_game', {'name': 'Global test room', 'individual_room': 'yes'}))
        initial = parse(peer.until('alliance_game')).one('alliance_game')
        game = initial.attrs['id']
        level = Node()
        level.attrs['version'] = '1.19.26'
        level.children.append(node('multiplayer', mp_scenario='individual_test', mp_scenario_name='Global fixture map',
            mp_era='era_default', shuffle_sides='no', observer='no', mp_fog='yes', mp_shroud='no',
            mp_countdown='no', mp_countdown_init_time=300, mp_countdown_reservoir_time=300,
            mp_countdown_turn_bonus=30, mp_countdown_action_bonus=0))
        scenario = node('scenario', id='individual_test', individual_room='yes', name='Global fixture map',
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
        peer.send(base.wml('join', {'id': room['id'], 'observe': 'no', 'room_revision': listing.attrs['room_revision']}))
        value = self.receive(peer, lambda value: bool(descendants(value, 'scenario')))
        scenario = descendants(value, 'scenario')[0]
        assigned = next(row for row in scenario.children if row.name == 'side' and row.attrs.get('player_id') == actor['username'])
        side = int(assigned.attrs['side'])
        room['actors'][side] = actor
        room['level'].children[1] = copy.deepcopy(scenario)
        context = self.context(room['peer'], int(room['context'].attrs['room_revision']) + 1)
        room['context'] = context
        return {'api': api, 'token': token, 'actor': actor, 'peer': peer, 'side': side}

    def select(self, room, seat):
        response = seat['api'].rpc('casual_select', {'game_id': room['game'], 'side': seat['side'],
            'hero_id': self.hero, 'form_id': self.form['id']}, seat['token'])
        self.assertTrue(response['ok'], response)
        selected = response['data']
        seat['peer'].send(base.wml('alliance_hero', {'side': seat['side'], 'ticket': selected['selection_ticket']}))
        room['context'] = self.context(room['peer'], int(room['context'].attrs['room_revision']) + 1)
        room['selected'][seat['side']] = selected['selection']
        return selected

    def host_seat(self, room):
        return {key: room[key] for key in ('api', 'token', 'actor', 'peer')} | {'side': 1}

    def finalized_scenario(self, room):
        scenario = copy.deepcopy(room['level'].children[1])
        for side in scenario.children:
            if side.name != 'side': continue
            number = int(side.attrs['side'])
            actor = room['actors'].get(number)
            if actor:
                side.attrs.update(player_id=actor['username'], current_player=actor['username'])
            selected = room['selected'].get(number)
            if selected:
                side.attrs.update(alliance_account_id=actor['id'], alliance_hero_id=selected['hero_id'],
                    alliance_form_id=selected['form_id'], alliance_hero_level=str(selected['hero_level']),
                    alliance_hero_revision=str(selected['hero_revision']))
                side.children = [item for item in side.children if item.name != 'leader']
                side.children.append(parse(self.leader(selected)).one('leader'))
        return scenario

    def update_scenario(self, room, scenario):
        diff = Node('scenario_diff')
        change = node('change_child', index=0)
        changed = Node('scenario')
        changed.children.append(Node('insert', dict(scenario.attrs)))
        for index, side in enumerate(row for row in scenario.children if row.name == 'side'):
            side_change = node('change_child', index=index)
            replacement = Node('side')
            replacement.children.append(Node('insert', dict(side.attrs)))
            # simple_wml applies insertion before deletion; old leader moves to 1.
            delete = node('delete_child', index=1); delete.children.append(Node('leader'))
            insert = node('insert_child', index=0); insert.children.append(copy.deepcopy(next(x for x in side.children if x.name == 'leader')))
            replacement.children.extend((delete, insert)); side_change.children.append(replacement)
            changed.children.append(side_change)
        change.children.append(changed); diff.children.append(change)
        room['peer'].send(serialize(diff))
        room['level'].children[1] = copy.deepcopy(scenario)

    def ready(self, room, seat, value=True):
        current = int(room['context'].attrs['room_revision'])
        seat['peer'].send(base.wml('alliance_ready', {'side': seat['side'], 'ready': 'yes' if value else 'no', 'room_revision': current}))
        # Every accepted readiness request broadcasts authoritative state.
        room['context'] = self.context(room['peer'], current if value else current + 1)
        return room['context']

    def fully_selected(self):
        room = self.create_room(); other = self.join_room(room); host = self.host_seat(room)
        self.select(room, host); self.select(room, other)
        self.update_scenario(room, self.finalized_scenario(room))
        # A harmless diff emits no new context. The following Ready command
        # carries this same revision and serves as the ordered server barrier.
        return room, host, other

    def test_individual_live_global_room_settings_and_occupancy(self):
        room = self.create_room(gold=150, turns=30)
        api, token, actor = self.account(False); watcher, _ = self.lobby(token, api, actor)
        row = self.snapshot(watcher, room['id'])
        self.assertEqual(row.attrs['individual_room'], 'yes')
        self.assertEqual(row.attrs['room_status'], 'waiting')
        self.assertEqual((row.attrs['room_members'], row.attrs['room_capacity'], row.attrs['room_ready']), ('1', '2', '0'))
        self.assertEqual((row.attrs['room_gold'], row.attrs['room_turns']), ('150', '30'))
        self.assertEqual((row.attrs['mp_fog'], row.attrs['mp_shroud']), ('yes', 'no'))
        self.assertEqual(len(descendants(row, 'room_side')), 2)
        self.assertNotIn('area_id', row.attrs)
        other = self.join_room(room)
        pushed = self.receive(watcher, lambda value: any(x.attrs.get('room_status') == 'full' for x in descendants(value, 'game')))
        row = next(x for x in descendants(pushed, 'game') if x.attrs.get('room_status') == 'full')
        self.assertEqual(row.attrs['room_members'], '2')
        self.assertTrue(any(x.attrs.get('player_id') == other['actor']['username'] for x in descendants(row, 'room_side')))

    def test_individual_stale_join_and_full_room_are_refused(self):
        room = self.create_room()
        api, token, actor = self.account(); stale, _ = self.lobby(token, api, actor)
        old = self.snapshot(stale, room['id'])
        self.join_room(room)
        stale.send(base.wml('join', {'id': room['id'], 'observe': 'no', 'room_revision': old.attrs['room_revision']}))
        self.receive(stale, lambda value: bool(descendants(value, 'leave_game')))
        current = self.snapshot(stale, room['id'])
        self.assertEqual(current.attrs['room_members'], '2')
        stale.send(base.wml('join', {'id': room['id'], 'observe': 'no', 'room_revision': current.attrs['room_revision']}))
        self.receive(stale, lambda value: bool(descendants(value, 'leave_game')))
        self.assertEqual(self.snapshot(stale, room['id']).attrs['room_members'], '2')

    def test_individual_all_ready_owner_hint_and_actual_start_without_rewards(self):
        room, host, other = self.fully_selected()
        self.ready(room, host)
        self.assertEqual(room['context'].attrs['room_ready'], '1')
        self.ready(room, other)
        hint = self.receive(room['peer'], lambda value: bool(descendants(value, 'individual_start'))).one('individual_start')
        self.assertEqual(hint.attrs['game_id'], room['game'])
        self.assertEqual(hint.attrs['room_revision'], room['context'].attrs['room_revision'])
        room['peer'].send(base.wml('start_game', {'room_revision': hint.attrs['room_revision']}))
        ack = self.receive(room['peer'], lambda value: bool(descendants(value, 'alliance_start'))).one('alliance_start')
        self.assertEqual(ack.attrs['accepted'], 'yes')
        self.receive(other['peer'], lambda value: bool(descendants(value, 'start_game')))
        frozen = self.domain.casual_restore(room['game'])
        self.assertEqual({x['account_id'] for x in frozen['players']}, {host['actor']['id'], other['actor']['id']})
        for actor in (host['actor'], other['actor']):
            self.assertEqual(self.db.account_heroes.find_one({'account_id': actor['id']})['total_experience'], 20)
        self.assertEqual(self.db.settlements.count_documents({'_id': room['game']}), 0)

    def test_individual_settings_change_clears_all_ready_and_rejects_old_revision(self):
        room, host, other = self.fully_selected(); self.ready(room, host)
        old = room['context'].attrs['room_revision']
        changed = self.finalized_scenario(room)
        for side in changed.children:
            if side.name == 'side': side.attrs['gold'] = '200'
        self.update_scenario(room, changed)
        room['context'] = self.context(room['peer'], int(old) + 1)
        self.assertEqual(room['context'].attrs['room_ready'], '0')
        self.assertEqual(room['context'].attrs['room_gold'], '200')
        other['peer'].send(base.wml('alliance_ready', {'side': other['side'], 'ready': 'yes', 'room_revision': old}))
        self.receive(other['peer'], lambda value: any('refused' in row.attrs.get('message', '').lower() for row in descendants(value, 'message')))
        self.assertIsNone(self.db.casual_games.find_one({'_id': room['game']}))

    def test_individual_departure_and_host_close_update_dashboard(self):
        room, host, other = self.fully_selected(); self.ready(room, host)
        api, token, actor = self.account(False); watcher, _ = self.lobby(token, api, actor)
        old = int(room['context'].attrs['room_revision'])
        other['peer'].send(base.wml('leave_game'))
        room['context'] = self.context(room['peer'], old + 1)
        row = self.snapshot(watcher, room['id'])
        self.assertEqual((row.attrs['room_members'], row.attrs['room_ready'], row.attrs['room_status']), ('1', '0', 'waiting'))
        room['peer'].send(base.wml('leave_game'))
        self.receive(room['peer'], lambda value: any(child.name == 'gamelist' for child in value.children))
        self.assertIsNone(self.snapshot(watcher, room['id']))

    def test_individual_not_ready_cancels_pending_start(self):
        room, host, other = self.fully_selected(); self.ready(room, host); self.ready(room, other)
        hint = self.receive(room['peer'], lambda value: bool(descendants(value, 'individual_start'))).one('individual_start')
        self.ready(room, other, False)
        self.assertEqual(room['context'].attrs['room_ready'], '1')
        room['peer'].send(base.wml('start_game', {'room_revision': hint.attrs['room_revision']}))
        ack = self.receive(room['peer'], lambda value: bool(descendants(value, 'alliance_start'))).one('alliance_start')
        self.assertEqual(ack.attrs['accepted'], 'no')
        self.assertIsNone(self.db.casual_games.find_one({'_id': room['game']}))


    def test_individual_socket_disconnect_reopens_seat_and_revokes_consent(self):
        room, host, other = self.fully_selected(); self.ready(room, host)
        old = int(room['context'].attrs['room_revision'])
        other['peer'].close()
        room['context'] = self.context(room['peer'], old + 1)
        self.assertEqual((room['context'].attrs['room_members'], room['context'].attrs['room_ready']), ('1', '0'))
        seats = [item for item in room['context'].children if item.name == 'room_side']
        departed = next(item for item in seats if item.attrs['side'] == str(other['side']))
        self.assertEqual(departed.attrs['player_id'], '')
        self.assertEqual(departed.attrs['ready'], 'no')

    def test_individual_another_player_cannot_withdraw_host_ready(self):
        room, host, other = self.fully_selected(); self.ready(room, host)
        previous = dict(room['context'].attrs)
        other['peer'].send(base.wml('alliance_ready', {'side': 1, 'ready': 'no', 'room_revision': previous['room_revision']}))
        self.receive(other['peer'], lambda value: any('refused' in x.attrs.get('message', '').lower() for x in descendants(value, 'message')))
        api, token, actor = self.account(False); watcher, _ = self.lobby(token, api, actor)
        row = self.snapshot(watcher, room['id'])
        self.assertEqual(row.attrs['room_revision'], previous['room_revision'])
        self.assertEqual(row.attrs['room_ready'], '1')

    def test_individual_four_and_eight_seat_capacity_requires_all_seats(self):
        for count in (4, 8):
            with self.subTest(capacity=count):
                room = self.create_room(count=count)
                host = self.host_seat(room); self.select(room, host)
                self.ready(room, host)
                self.assertEqual(room['context'].attrs['room_capacity'], str(count))
                self.assertEqual(room['context'].attrs['room_status'], 'waiting')
                room['peer'].send(base.wml('start_game', {'room_revision': room['context'].attrs['room_revision']}))
                ack = self.receive(room['peer'], lambda value: bool(descendants(value, 'alliance_start'))).one('alliance_start')
                self.assertEqual(ack.attrs['accepted'], 'no')
                self.assertIsNone(self.db.casual_games.find_one({'_id': room['game']}))

    def test_individual_two_clients_race_for_last_seat_without_observer_fallback(self):
        room = self.create_room(); contenders = []
        for _ in range(2):
            api, token, actor = self.account(); peer, _ = self.lobby(token, api, actor)
            snapshot = self.snapshot(peer, room['id'])
            self.assertEqual(snapshot.attrs['room_members'], '1')
            contenders.append((peer, actor, snapshot.attrs['room_revision']))
        # Send both previously reviewed admissions before waiting for either reply.
        for peer, actor, rev in contenders:
            peer.send(base.wml('join', {'id': room['id'], 'observe': 'no', 'room_revision': rev}))
        outcomes = []
        for peer, actor, rev in contenders:
            reply = self.receive(peer, lambda value: bool(descendants(value, 'scenario') or descendants(value, 'leave_game')))
            levels = descendants(reply, 'scenario')
            if levels:
                owned = [side for side in descendants(levels[0], 'side') if side.attrs.get('player_id') == actor['username']]
                self.assertEqual(len(owned), 1); outcomes.append('seated')
            else: outcomes.append('refused')
        self.assertCountEqual(outcomes, ['seated', 'refused'])
        room['context'] = self.context(room['peer'], int(room['context'].attrs['room_revision']) + 1)
        self.assertEqual(room['context'].attrs['room_members'], '2')
        loser = contenders[outcomes.index('refused')][0]
        current = self.snapshot(loser, room['id'])
        self.assertEqual(current.attrs['room_members'], '2')
        self.assertEqual(current.one('slot_data').attrs, {'max': '2', 'vacant': '0'})


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Individual(name) for name in sorted(Individual.__dict__) if name.startswith('test_individual_'))


if __name__ == '__main__':
    unittest.main()
