"""Versioned Team plans: accounts own human seats; AI owns no account.

All launch consent and reservations are serialized in the Mongo transaction that
publishes the prepared generation. Legacy runs retain their original rules.
"""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
from .rules import MAPS, RULESET_VERSION, LEADER_REWARDS, TEAM_REWARDS, rating_delta, team_level

DEFAULT_SETTINGS = dict(gold=100, base_income=2, turns=-1, fog=True, shroud=False, observers=False)
# Pinned Wesnoth 1.19.26 Default-era faction leader choices.
AI_LEADERS = {
    'Loyalists': ('Lieutenant', 'Swordsman', 'Pikeman', 'Javelineer', 'Shock Trooper', 'Longbowman', 'White Mage', 'Red Mage'),
    'Rebels': ('Elvish Captain', 'Elvish Hero', 'Elvish Ranger', 'Elvish Marksman', 'Elvish Druid', 'Elvish Sorceress', 'White Mage', 'Red Mage', 'Elder Wose'),
    'Northerners': ('Orcish Warrior', 'Troll', 'Troll Rocklobber', 'Orcish Crossbowman', 'Orcish Slayer'),
    'Knalgan Alliance': ('Dwarvish Steelclad', 'Dwarvish Thunderguard', 'Dwarvish Stalwart', 'Rogue', 'Trapper'),
    'Undead': ('Dark Sorcerer', 'Revenant', 'Deathblade', 'Bone Shooter', 'Necrophage'),
    'Drakes': ('Drake Flare', 'Fire Drake', 'Drake Arbiter', 'Drake Thrasher', 'Drake Warrior', 'Saurian Oracle'),
    'Dunefolk': ('Dune Explorer', 'Dune Swordsman', 'Dune Spearguard', 'Dune Scorcher', 'Dune Apothecary'),
}
PLAN_FORMAT = 2
MAX_TEAM_PLANS = 32


def flexible(run):
    return run.get('plan_format') == PLAN_FORMAT


def validate_settings(value):
    from .domain import DomainError
    if not isinstance(value, dict) or set(value) != set(DEFAULT_SETTINGS):
        raise DomainError('invalid_input', 'All common battle settings are required.')
    if (type(value['gold']) is not int or not 0 <= value['gold'] <= 1000 or
        type(value['base_income']) is not int or not 0 <= value['base_income'] <= 20 or
        type(value['turns']) is not int or value['turns'] != -1 and not 1 <= value['turns'] <= 1000 or
        any(type(value[k]) is not bool for k in ('fog', 'shroud', 'observers'))):
        raise DomainError('invalid_input', 'A common battle setting is outside its supported range.')
    return deepcopy(value)


class FlexibleProduct:
    def _network_reserve(self, actor_id, kind, run_id, generation, session, expires_at=None):
        from .domain import DomainError, _now
        self._generation(session)
        account = self._player(actor_id, session)
        if account.get('active_run_id') not in (None, run_id):
            active = self._run(account['active_run_id'], session)
            if active['kind'] == 'alliance' and active['state'] == 'running':
                raise DomainError('busy', 'This player occupies a retained running team battle.')
        if kind == 'individual' and self.db.game_runs.find_one({
                'kind': 'alliance', 'state': 'draft', 'plan_format': {'$exists': False},
                'participants.account_id': actor_id, 'shared_room.state': 'preparing',
                'shared_room.expires_at': {'$gt': _now()}}, {'_id': 1}, session=session):
            raise DomainError('busy', 'This player occupies a retained prepared team battle.')
        prior = self.db.network_battle_reservations.find_one({'_id': actor_id}, session=session)
        if prior and prior['kind'] == 'individual' and prior.get('expires_at', _now()) <= _now():
            self.db.network_battle_reservations.delete_one({'_id': actor_id}, session=session)
            prior = None
        if prior and (prior['kind'], prior['run_id'], prior['generation']) != (kind, run_id, generation):
            raise DomainError('busy', 'This player already occupies a prepared or running network battle.')
        record = {'_id': actor_id, 'kind': kind, 'run_id': run_id, 'generation': generation,
                  'created_at': prior['created_at'] if prior else _now()}
        if expires_at is not None: record['expires_at'] = expires_at
        self.db.network_battle_reservations.replace_one({'_id': actor_id}, record, upsert=True, session=session)

    def network_prepare(self, game_id, generation, account_ids):
        from .domain import DomainError, _directory_id, _now
        _directory_id(game_id, uuid=True); _directory_id(generation, uuid=True)
        if not isinstance(account_ids, list) or not 2 <= len(account_ids) <= 8 or any(not isinstance(a, str) for a in account_ids) or len(set(account_ids)) != len(account_ids):
            raise DomainError('invalid_input', 'An individual battle requires distinct human players.')
        for actor in account_ids: _directory_id(actor, uuid=True)
        def write(session):
            for actor in account_ids:
                self._network_reserve(actor, 'individual', game_id, generation, session, _now() + timedelta(seconds=120))
            return {'game_id': game_id, 'generation': generation, 'reserved': len(account_ids)}
        return self._tx(write)

    def network_heartbeat(self, generation, game_ids):
        from .domain import DomainError, _directory_id, _now
        _directory_id(generation, uuid=True)
        if not isinstance(game_ids, list) or len(game_ids) > 64 or any(not isinstance(g, str) for g in game_ids) or len(set(game_ids)) != len(game_ids):
            raise DomainError('invalid_input', 'Invalid native heartbeat rooms.')
        for game in game_ids: _directory_id(game, uuid=True)
        def write(session):
            renewed, expired = [], []
            for game in game_ids:
                query = {'kind': 'individual', 'run_id': game, 'generation': generation}
                rows = list(self.db.network_battle_reservations.find(query, session=session))
                accounts = list(self.db.accounts.find({'_id': {'$in': [r['_id'] for r in rows]},
                    'status': 'active', 'role': 'player'}, {'_id': 1}, session=session))
                if len(rows) < 2 or len(accounts) != len(rows) or any(r['expires_at'] <= _now() for r in rows):
                    # One lost room never cancels another room's valid lease.
                    self.db.network_battle_reservations.delete_many(query, session=session)
                    expired.append(game)
                    continue
                for row in rows: self._player(row['_id'], session)
                self.db.network_battle_reservations.update_many(query, {'$set': {'expires_at': _now() + timedelta(seconds=120)}}, session=session)
                renewed.append(game)
            return {'generation': generation, 'renewed': renewed, 'expired': expired}
        return self._tx(write)

    def network_release(self, game_id, generation):
        from .domain import _directory_id
        _directory_id(game_id, uuid=True); _directory_id(generation, uuid=True)
        def write(session):
            query = {'kind': 'individual', 'run_id': game_id, 'generation': generation}
            for row in self.db.network_battle_reservations.find(query, session=session): self._player(row['_id'], session)
            self.db.network_battle_reservations.delete_many(query, session=session)
            return {'game_id': game_id, 'released': True}
        return self._tx(write)

    def _flex_run(self, actor_id, battle_id, revision, session):
        from .domain import DomainError, _directory_id
        _directory_id(battle_id, uuid=True)
        self._player(actor_id, session)
        run = self._run(battle_id, session)
        if not flexible(run):
            raise DomainError('unsupported_ruleset', 'Use the legacy plan controls for this saved plan.')
        team = self._planning_access(actor_id, run, session)
        if type(revision) is not int or revision != run['revision']:
            raise DomainError('stale_proposal', 'The plan changed. Refresh before acting.')
        self._draft(run)
        return run, team

    def _flex_teams(self, run, session):
        from .domain import DomainError
        self._generation(session)
        teams = [self._team(t, session) for t in run['team_ids']]
        if teams[0]['area_id'] != teams[1]['area_id'] or teams[0]['area_id'] != run['area_id']:
            raise DomainError('different_area', 'Both teams must remain in the same area.')
        area = self._area(run['area_id'], session)
        if run['map_id'] not in area['approved_maps']:
            raise DomainError('invalid_map', 'This map is not approved in the team area.')
        for team in teams:
            self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        return teams

    def _flex_slots(self, map_id, slots, teams, *, retained_opponent_reservations=frozenset()):
        from .domain import DomainError, _directory_id
        if map_id not in MAPS or not isinstance(slots, list) or len(slots) != MAPS[map_id]['size'] * 2:
            raise DomainError('invalid_lineup', 'Provide each approved map side exactly once.')
        by_side = {side: t for t, sides in zip(teams, MAPS[map_id]['sides']) for side in sides}
        result, reserved, seen = [], set(), set()
        for slot in slots:
            if not isinstance(slot, dict) or set(slot) != {'side', 'kind', 'account_id', 'ai_faction', 'ai_leader'}:
                raise DomainError('invalid_lineup', 'The slot fields are invalid.')
            side, kind = slot['side'], slot['kind']
            if type(side) is not int or side not in by_side or side in seen or kind not in ('open', 'reserved', 'ai', 'closed'):
                raise DomainError('invalid_lineup', 'The slot side or kind is invalid.')
            seen.add(side)
            if any(not isinstance(slot[k], str) for k in ('account_id', 'ai_faction', 'ai_leader')):
                raise DomainError('invalid_lineup', 'Slot identities must be text.')
            if kind == 'reserved':
                account = _directory_id(slot['account_id'], uuid=True)
                if account in reserved or (account not in {m['account_id'] for m in by_side[side]['members']}
                        and (side, account) not in retained_opponent_reservations):
                    raise DomainError('not_member', 'Reserve a different current member of this side’s team.')
                reserved.add(account)
            elif slot['account_id']:
                raise DomainError('invalid_lineup', 'Only a reserved slot names a player before joining.')
            if kind == 'ai':
                if slot['ai_leader'] not in AI_LEADERS.get(slot['ai_faction'], ()):
                    raise DomainError('invalid_lineup', 'Choose a supported native AI faction and leader.')
            elif slot['ai_faction'] or slot['ai_leader']:
                raise DomainError('invalid_lineup', 'Human and closed slots cannot configure an AI.')
            result.append({**deepcopy(slot), 'team_id': by_side[side]['_id']})
        for team in teams:
            if not any(s['team_id'] == team['_id'] and s['kind'] in ('open', 'reserved') for s in result):
                raise DomainError('human_required', 'Each team needs at least one human slot.')
        return sorted(result, key=lambda s: s['side'])

    def directory_publish_plan(self, actor_id, team_id, opponent_team_id, map_id, settings, slots):
        from .domain import DomainError, _directory_id, _now
        _directory_id(team_id, uuid=True); _directory_id(opponent_team_id, uuid=True)
        settings = validate_settings(settings)
        def write(session):
            self._player(actor_id, session)
            teams = [self._team(team_id, session), self._team(opponent_team_id, session)]
            if teams[0]['captain_id'] != actor_id or team_id == opponent_team_id:
                raise DomainError('forbidden', 'Only your captain may publish a plan against another team.')
            run = {'_id': str(uuid4()), 'kind': 'alliance', 'state': 'draft', 'plan_format': PLAN_FORMAT,
                   'ruleset_version': RULESET_VERSION, 'revision': 1, 'map_id': map_id,
                   'area_id': teams[0]['area_id'], 'team_ids': [team_id, opponent_team_id],
                   'settings': settings, 'participants': [], 'approvals': {}, 'ready': [],
                   'recorded_captains': [t['captain_id'] for t in teams],
                   'created_at': _now(), 'planning_teams': [{'id': t['_id'], 'name': t['name']} for t in teams]}
            self._flex_teams(run, session)
            for team in teams:
                if self.db.game_runs.count_documents({'kind': 'alliance', 'state': 'draft', 'team_ids': team['_id']}, session=session) >= MAX_TEAM_PLANS:
                    raise DomainError('limit_reached', 'A team has reached its active plan limit.')
            run['slots'] = self._flex_slots(map_id, slots, teams)
            if any(s['team_id'] == opponent_team_id and s['kind'] != 'open' for s in run['slots']):
                raise DomainError('forbidden', 'Publish the opposing team with open slots; its captain configures them.')
            self.db.game_runs.insert_one(run, session=session)
            return self._planning_record(run, session)
        return self._tx(write)

    def _flex_unprepare(self, run, session):
        """Release only this exact preparation. A running game is immutable."""
        room = run.get('shared_room')
        if room and room.get('state') == 'preparing':
            self.db.network_battle_reservations.delete_many({'kind': 'team', 'run_id': run['_id'], 'generation': room['generation']}, session=session)
            for player in run['participants']:
                self.db.accounts.update_one({'_id': player['account_id'], 'active_run_id': run['_id']},
                    {'$set': {'active_run_id': None}, '$inc': {'revision': 1}}, session=session)
            room['state'] = 'cancelled'
            self.db.game_runs.update_one({'_id': run['_id']}, {'$set': {'shared_room.state': 'cancelled'}}, session=session)

    def _flex_changed(self, run, session):
        self._flex_unprepare(run, session)
        run['revision'] += 1
        run['approvals'] = {}; run['ready'] = []
        self.db.game_runs.replace_one({'_id': run['_id']}, run, session=session)

    def directory_edit_plan(self, actor_id, battle_id, revision, map_id, settings, slots):
        from .domain import DomainError
        settings = validate_settings(settings)
        def write(session):
            run, own_team = self._flex_run(actor_id, battle_id, revision, session)
            if own_team['captain_id'] != actor_id:
                raise DomainError('forbidden', 'Only a participating captain may edit this plan.')
            proposed = deepcopy(run); proposed['map_id'] = map_id
            teams = self._flex_teams(proposed, session)
            # Each captain can repair their own stale reservations even when
            # the opponent also has departed members. The unchanged opposing
            # slots remain invalid for preparation until that captain fixes them.
            retained = {(s['side'], s['account_id']) for s in run['slots']
                if map_id == run['map_id'] and s['team_id'] != own_team['_id'] and s['kind'] == 'reserved'}
            proposed_slots = self._flex_slots(map_id, slots, teams, retained_opponent_reservations=retained)
            old = {s['side']: s for s in run['slots']}
            for slot in proposed_slots:
                if slot['team_id'] != own_team['_id']:
                    previous = old.get(slot['side'])
                    # A new map resets both lineups to open; neither captain may
                    # choose another team's named players or AI configuration.
                    if map_id != run['map_id']:
                        if slot['kind'] != 'open':
                            raise DomainError('forbidden', 'New opponent map slots must be open.')
                    elif slot != previous:
                        raise DomainError('forbidden', 'Only the other captain can edit their slots.')
            if (map_id, settings, proposed_slots) != (run['map_id'], run['settings'], run['slots']):
                self._flex_unprepare(run, session)
                same_map = map_id == run['map_id']
                run.update(map_id=map_id, settings=settings, slots=proposed_slots)
                allowed = {s['side']: s for s in proposed_slots}
                run['participants'] = [p for p in run['participants'] if same_map and
                    p['side'] in allowed and allowed[p['side']]['team_id'] == p['team_id'] and
                    (allowed[p['side']]['kind'] == 'open' or allowed[p['side']]['kind'] == 'reserved' and
                     allowed[p['side']]['account_id'] == p['account_id'])]
                self._flex_changed(run, session)
            return self._planning_record(run, session)
        return self._tx(write)

    def directory_join_plan(self, actor_id, battle_id, revision, side):
        from .domain import DomainError
        def write(session):
            run, team = self._flex_run(actor_id, battle_id, revision, session)
            self._flex_teams(run, session)
            if type(side) is not int:
                raise DomainError('invalid_input', 'Choose a valid side.')
            slot = next((s for s in run['slots'] if s['side'] == side), None)
            if slot is None or slot['team_id'] != team['_id'] or not (slot['kind'] == 'open' or
                    slot['kind'] == 'reserved' and slot['account_id'] == actor_id):
                raise DomainError('forbidden', 'This team slot is not open to your account.')
            if any(p['side'] == side or p['account_id'] == actor_id for p in run['participants']):
                raise DomainError('conflict', 'This slot or your account is already in the plan.')
            account = self._player(actor_id, session); self._idle(account)
            run['participants'].append({'account_id': actor_id, 'team_id': team['_id'], 'side': side,
                                        'username': account['username'], 'selection': None})
            self._flex_changed(run, session)
            return self._planning_record(run, session)
        return self._tx(write)

    def directory_leave_plan(self, actor_id, battle_id, revision):
        from .domain import DomainError
        def write(session):
            run, _ = self._flex_run(actor_id, battle_id, revision, session)
            if not any(p['account_id'] == actor_id for p in run['participants']):
                raise DomainError('forbidden', 'Only an occupied human slot can leave this plan.')
            self._flex_unprepare(run, session)
            run['participants'] = [p for p in run['participants'] if p['account_id'] != actor_id]
            self._flex_changed(run, session)
            return self._planning_record(run, session)
        return self._tx(write)

    def directory_select_plan_hero(self, actor_id, battle_id, revision, hero_id, form_id):
        from .domain import DomainError
        def write(session):
            run, _ = self._flex_run(actor_id, battle_id, revision, session)
            own = next((p for p in run['participants'] if p['account_id'] == actor_id), None)
            if own is None:
                raise DomainError('forbidden', 'Join a human slot before choosing a hero.')
            selection = self._selection(actor_id, hero_id, form_id, session)
            if selection != own['selection']:
                own['selection'] = selection
                self._flex_changed(run, session)
            return self._planning_record(run, session)
        return self._tx(write)

    def directory_approve_plan(self, actor_id, battle_id, revision):
        from .domain import DomainError
        def write(session):
            run, team = self._flex_run(actor_id, battle_id, revision, session)
            if team['captain_id'] != actor_id:
                raise DomainError('forbidden', 'Only the current captain approves their team.')
            self._flex_teams(run, session)
            run['approvals'][team['_id']] = actor_id
            run['recorded_captains'] = sorted(set(run.get('recorded_captains', [])) | {actor_id})
            self.db.game_runs.replace_one({'_id': battle_id}, run, session=session)
            self._flex_prepare_if_ready(run, session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def directory_ready_plan(self, actor_id, battle_id, revision, ready):
        from .domain import DomainError
        if type(ready) is not bool:
            raise DomainError('invalid_input', 'Ready must be a boolean.')
        def write(session):
            run, _ = self._flex_run(actor_id, battle_id, revision, session)
            own = next((p for p in run['participants'] if p['account_id'] == actor_id), None)
            if own is None:
                raise DomainError('forbidden', 'Join a human slot before Ready.')
            if ready:
                if own['selection'] is None or own['selection'] != self._selection(actor_id, own['selection']['hero_id'], own['selection']['form_id'], session):
                    raise DomainError('hero_required', 'Choose a current owned hero before Ready.')
                account = self._account(actor_id, session)
                if account['active_run_id'] not in (None, battle_id):
                    raise DomainError('busy', 'Finish the active game before Ready.')
                if actor_id not in run['ready']: run['ready'].append(actor_id)
            else:
                self._flex_unprepare(run, session)
                run['ready'] = [p for p in run['ready'] if p != actor_id]
            self.db.game_runs.replace_one({'_id': battle_id}, run, session=session)
            self._flex_prepare_if_ready(run, session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def _flex_prepare_if_ready(self, run, session):
        from .domain import DomainError, _now
        teams = self._flex_teams(run, session)
        human_slots = {s['side'] for s in run['slots'] if s['kind'] in ('open', 'reserved')}
        humans = {p['account_id'] for p in run['participants']}
        if ({p['side'] for p in run['participants']} != human_slots or set(run['ready']) != humans or
            any(run['approvals'].get(t['_id']) != t['captain_id'] for t in teams)):
            return
        if run.get('shared_room', {}).get('state') == 'preparing':
            return
        enabled = [sum(s['team_id'] == team['_id'] and s['kind'] != 'closed' for s in run['slots']) for team in teams]
        if enabled[0] != enabled[1]:
            raise DomainError('unbalanced_sides', 'Both teams need the same number of enabled sides before preparation.')
        self._check_preview(run, session)
        generation = str(uuid4())
        for p in run['participants']:
            team = next(t for t in teams if t['_id'] == p['team_id'])
            if p['account_id'] not in {m['account_id'] for m in team['members']}:
                raise DomainError('not_member', 'A player left their team before preparation.')
            self._network_reserve(p['account_id'], 'team', run['_id'], generation, session)
            self._reserve_account(p['account_id'], run['_id'], session)
        # Reservation and withdrawal of consent elsewhere commit together. A
        # failed reservation leaves every competing plan unchanged. Never alter
        # a prepared generation or another participant's consent/configuration.
        self.db.game_runs.update_many({'_id': {'$ne': run['_id']}, 'kind': 'alliance', 'state': 'draft',
            'shared_room.state': {'$ne': 'preparing'}, 'ready': {'$in': list(humans)}},
            {'$pull': {'ready': {'$in': list(humans)}}}, session=session)
        host = min(run['participants'], key=lambda p: p['side'])['account_id']
        owner = {str(p['side']): p['account_id'] for p in run['participants']}
        owner.update({str(s['side']): host for s in run['slots'] if s['kind'] == 'ai'})
        room = {'generation': generation, 'state': 'preparing', 'expires_at': _now() + timedelta(minutes=5),
                'scenario_sha256': '', 'result_reports': {}, 'result_approvals': {}, 'revision': 0,
                'engine_host_account_id': host, 'controllers': owner,
                'captains': {t['_id']: t['captain_id'] for t in teams}}
        self.db.game_runs.update_one({'_id': run['_id']}, {'$set': {'shared_room': room}}, session=session)

    def _planning_summary(self, run, session=None):
        result = super()._planning_summary(run, session)
        return result

    def _planning_record(self, run, session=None):
        if not flexible(run): return super()._planning_record(run, session)
        result = super()._planning_summary(run, session); result.pop('map_id')
        room = run.get('shared_room', {})
        result.update(format=PLAN_FORMAT, revision=run['revision'], map=self._planning_map(run['map_id']),
            validity=self._flex_validity(run, session), settings=deepcopy(run['settings']),
            ranked=self._flex_ranked(run), room_state=room.get('state', ''), generation=room.get('generation', ''),
            engine_host_account_id=room.get('engine_host_account_id', ''))
        for display in result['teams']:
            current = self.db.teams.find_one({'_id': display['id']}, session=session)
            captain = room.get('captains', {}).get(display['id']) if run['state'] in ('running', 'completed') else (current or {}).get('captain_id')
            display.update(captain_id=captain or '', approved=bool(captain and run['approvals'].get(display['id']) == captain),
                players=[{'id': p['account_id'], 'username': p['username'], 'side': p['side'],
                          'ready': p['account_id'] in run['ready'], 'selection': deepcopy(p['selection'])}
                         for p in sorted(run['participants'], key=lambda p: p['side']) if p['team_id'] == display['id']],
                slots=[{k: deepcopy(v) for k, v in s.items() if k != 'team_id'}
                       for s in run['slots'] if s['team_id'] == display['id']])
        return result

    def _flex_validity(self, run, session=None):
        from .domain import DomainError
        if run['state'] in ('completed', 'cancelled'): return 'valid'
        enabled = [sum(s['team_id'] == team_id and s['kind'] != 'closed' for s in run['slots']) for team_id in run['team_ids']]
        if enabled[0] != enabled[1]: return 'unbalanced_sides'
        for team_id in run['team_ids']:
            team = self.db.teams.find_one({'_id': team_id, 'status': 'active'}, session=session)
            if team is None: return 'team_unavailable'
            if team['area_id'] != run['area_id']: return 'area_changed'
            members = {m['account_id'] for m in team['members']}
            if any(s['kind'] == 'reserved' and s['account_id'] not in members
                   for s in run['slots'] if s['team_id'] == team_id): return 'roster_changed'
            if any(p['account_id'] not in members for p in run['participants'] if p['team_id'] == team_id): return 'roster_changed'
        for p in run['participants']:
            account = self.db.accounts.find_one({'_id': p['account_id'], 'status': 'active'}, session=session)
            if account is None: return 'player_unavailable'
            if account['active_run_id'] not in (None, run['_id']): return 'busy'
            if p['selection'] is not None:
                try:
                    if p['selection'] != self._selection(p['account_id'], p['selection']['hero_id'], p['selection']['form_id'], session): return 'leader_changed'
                except DomainError: return 'leader_changed'
        return 'valid'

    @staticmethod
    def _flex_ranked(run):
        return run['settings'] == DEFAULT_SETTINGS and all(s['kind'] in ('open', 'reserved') for s in run['slots'])

    def _planning_validity(self, run, teams, accounts, area):
        if flexible(run): return self._flex_validity(run)
        return super()._planning_validity(run, teams, accounts, area)

    def expire_preparations(self):
        from .domain import _now
        expired = list(self.db.game_runs.find({'plan_format': PLAN_FORMAT, 'state': 'draft',
            'shared_room.state': 'preparing', 'shared_room.expires_at': {'$lte': _now()}}, {'_id': 1}).limit(256))
        for row in expired:
            def write(session):
                run = self._run(row['_id'], session)
                room = run.get('shared_room', {})
                if run['state'] == 'draft' and room.get('state') == 'preparing' and room['expires_at'] <= _now():
                    self._flex_unprepare(run, session)
                    self.db.game_runs.update_one({'_id': run['_id']}, {'$set': {'ready': []}}, session=session)
            self._tx(write)
        return len(expired)

    def shared_observer_admission(self, actor_id, run_id, generation):
        from .domain import DomainError, _directory_id
        self._directory_player(actor_id); _directory_id(run_id, uuid=True)
        run = self._run(run_id); room = self._shared_binding(run, generation)
        if not flexible(run) or run['state'] != 'running' or room['state'] != 'running' or not run['settings']['observers']:
            raise DomainError('forbidden', 'This running battle does not allow team observers.')
        self._planning_access(actor_id, run)
        return {'battle': self._planning_record(run), 'generation': generation, 'room_state': 'running',
                'assigned_side': 0, 'scenario_sha256': room['scenario_sha256'],
                'expires_at': self._time(room.get('expires_at')), 'controlled_sides': [], 'engine_host': False}

    def shared_prepare(self, actor_id, run_id, generation):
        run = self._run(run_id)
        if not flexible(run): return super().shared_prepare(actor_id, run_id, generation)
        return self.shared_admission(actor_id, run_id, generation)

    def _shared_record(self, actor_id, run, session=None):
        result = super()._shared_record(actor_id, run, session)
        if flexible(run):
            room = run.get('shared_room', {})
            result['controlled_sides'] = [int(side) for side, owner in room.get('controllers', {}).items() if owner == actor_id]
            result['engine_host'] = room.get('engine_host_account_id') == actor_id
        return result

    def shared_admission(self, actor_id, run_id, generation):
        from .domain import DomainError, _now
        if not flexible(self._run(run_id)): return super().shared_admission(actor_id, run_id, generation)
        def write(session):
            self._player(actor_id, session); run = self._run(run_id, session); room = self._shared_binding(run, generation)
            if run['state'] not in ('draft', 'running') or room['state'] not in ('preparing', 'running'):
                raise DomainError('invalid_state', 'This generation is not accepting gameplay.')
            if room['state'] == 'preparing' and room['expires_at'] <= _now():
                raise DomainError('room_expired', 'Preparation expired; set Ready again to retry.')
            if self._flex_validity(run, session) != 'valid':
                raise DomainError('stale_proposal', 'The bound battle changed.')
            if any(self._account(p['account_id'], session)['active_run_id'] != run_id for p in run['participants']):
                raise DomainError('reservation_conflict', 'The bound account reservation changed.')
            return self._shared_record(actor_id, run, session)
        return self._tx(write)

    def _reserve_account(self, account_id, run_id, session):
        # Training creates its run after the account reservation. It remains
        # outside the network-battle lease table.
        run = self.db.game_runs.find_one({'_id': run_id}, session=session)
        if run and run['kind'] == 'alliance' and not flexible(run):
            self._network_reserve(account_id, 'team', run_id,
                run.get('shared_room', {}).get('generation', run_id), session)
        return super()._reserve_account(account_id, run_id, session)

    def _record_settlement(self, run, result, rewards, session):
        if run['kind'] == 'alliance':
            self.db.network_battle_reservations.delete_many({'kind': 'team', 'run_id': run['_id']}, session=session)
        return super()._record_settlement(run, result, rewards, session)

    def _start_battle(self, actor_id, run_id, session, *, shared_authorized=False):
        from .domain import DomainError
        run = self._run(run_id, session)
        if not flexible(run): return super()._start_battle(actor_id, run_id, session, shared_authorized=shared_authorized)
        self._draft(run)
        if not shared_authorized or run.get('shared_room', {}).get('state') != 'preparing':
            raise DomainError('room_required', 'The automatic all-loaded barrier starts this battle.')
        if self._flex_validity(run, session) != 'valid': raise DomainError('stale_proposal', 'The prepared plan changed.')
        teams = self._flex_teams(run, session)
        if any(run['approvals'].get(t['_id']) != t['captain_id'] for t in teams) or set(run['ready']) != {p['account_id'] for p in run['participants']}:
            raise DomainError('not_ready', 'Current captain approval and every human Ready are required.')
        self._check_preview(run, session)
        from .domain import _now
        self.db.game_runs.update_one({'_id': run_id}, {'$set': {'state': 'running', 'started_at': _now(),
            'reward_policy': 'ranked-v1' if self._flex_ranked(run) else 'custom-xp-v1'}}, session=session)
        return self._run(run_id, session)

    def _finish_battle(self, run_id, winner_team_id, draw, session, *, shared_authorized=False):
        from .domain import DomainError
        run = self._run(run_id, session)
        if not flexible(run): return super()._finish_battle(run_id, winner_team_id, draw, session, shared_authorized=shared_authorized)
        result = {'kind': 'alliance', 'winner_team_id': winner_team_id, 'draw': draw}
        previous = self._existing_settlement(run_id, result, session)
        if previous is not None: return previous
        if run['state'] != 'running' or not shared_authorized or not draw and winner_team_id not in run['team_ids']:
            raise DomainError('invalid_state', 'Only an agreed running battle can settle.')
        teams = [self._team(t, session) for t in run['team_ids']]
        outcomes = {t['_id']: 'draw' if draw else 'win' if t['_id'] == winner_team_id else 'loss' for t in teams}
        players = [self._reward_player(p, run, LEADER_REWARDS[outcomes[p['team_id']]], session) for p in run['participants']]
        delta = rating_delta(teams[0]['rating'], teams[1]['rating'], .5 if draw else 1 if winner_team_id == teams[0]['_id'] else 0) if run['reward_policy'] == 'ranked-v1' else 0
        rewards = []
        for team, change in zip(teams, (delta, -delta)):
            xp = team['experience'] + TEAM_REWARDS[outcomes[team['_id']]]
            self.db.teams.update_one({'_id': team['_id']}, {'$set': {'experience': xp, 'level': team_level(xp),
                'rating': team['rating'] + change}, '$inc': {'revision': 1}}, session=session)
            rewards.append({'team_id': team['_id'], 'experience': TEAM_REWARDS[outcomes[team['_id']]],
                'total_experience': xp, 'level': team_level(xp), 'rating': team['rating'] + change,
                'rating_before': team['rating'], 'rating_delta': change, 'revision': team['revision'] + 1})
        self.db.network_battle_reservations.delete_many({'kind': 'team', 'run_id': run_id}, session=session)
        return self._record_settlement(run, result, {'players': players, 'teams': rewards}, session)

    def _cancel(self, run_id, reason, session):
        from .domain import DomainError, _now
        run = self._run(run_id, session)
        if not flexible(run):
            result = super()._cancel(run_id, reason, session)
            if run['kind'] == 'alliance':
                self.db.network_battle_reservations.delete_many({'kind': 'team', 'run_id': run_id}, session=session)
            return result
        if run['state'] == 'completed': raise DomainError('invalid_state', 'A settled run cannot be cancelled.')
        if run['state'] == 'cancelled': return run
        self.db.network_battle_reservations.delete_many({'kind': 'team', 'run_id': run_id}, session=session)
        for p in run['participants']:
            self.db.accounts.update_one({'_id': p['account_id'], 'active_run_id': run_id},
                {'$set': {'active_run_id': None}, '$inc': {'revision': 1}}, session=session)
        self.db.game_runs.update_one({'_id': run_id}, {'$set': {'state': 'cancelled', 'cancel_reason': reason,
            'finished_at': _now(), 'shared_room.state': 'cancelled'}}, session=session)
        return self._run(run_id, session)

    def shared_cancel(self, run_id, generation, reason):
        from .domain import _directory_id, _reason
        _directory_id(run_id, uuid=True); reason = _reason(reason)
        if not flexible(self._run(run_id)):
            return super().shared_cancel(run_id, generation, reason)
        def write(session):
            run = self._run(run_id, session)
            self._shared_binding(run, generation)
            if run['state'] == 'draft':
                self._flex_unprepare(run, session)
                self.db.game_runs.update_one({'_id': run_id}, {'$set': {'ready': [],
                    'shared_room.state': 'cancelled', 'shared_room.cancel_reason': reason},
                    '$inc': {'shared_room.revision': 1}}, session=session)
                return {'run_id': run_id, 'state': 'draft', 'room_state': 'cancelled'}
            result = self._cancel(run_id, reason, session)
            return {'run_id': run_id, 'state': result['state'], 'room_state': 'cancelled'}
        return self._tx(write)

    def _reject_unversioned_flexible_mutation(self, battle_id):
        from .domain import DomainError
        if flexible(self._run(battle_id)):
            raise DomainError('stale_proposal', 'Flexible plans require the current revision.')

    def directory_select_hero(self, actor_id, battle_id, hero_id, form_id):
        self._reject_unversioned_flexible_mutation(battle_id)
        return super().directory_select_hero(actor_id, battle_id, hero_id, form_id)

    def directory_approve_battle(self, actor_id, battle_id):
        self._reject_unversioned_flexible_mutation(battle_id)
        return super().directory_approve_battle(actor_id, battle_id)

    def directory_battle_ready(self, actor_id, battle_id, ready):
        self._reject_unversioned_flexible_mutation(battle_id)
        return super().directory_battle_ready(actor_id, battle_id, ready)

    def directory_my_battles(self, actor_id, after=''):
        from .domain import _directory_id
        self._directory_player(actor_id); _directory_id(after, empty=True, uuid=True)
        team = self.db.teams.find_one({'members.account_id': actor_id, 'status': 'active'}, {'_id': 1})
        branches = [{'participants.account_id': actor_id}, {'recorded_captains': actor_id},
                    {'$expr': {'$in': [actor_id, {'$map': {'input': {'$objectToArray': {'$ifNull': ['$approvals', {}]}}, 'as': 'approval', 'in': '$$approval.v'}}]}},
                    {'$expr': {'$in': [actor_id, {'$map': {'input': {'$objectToArray': {'$ifNull': ['$shared_room.captains', {}]}}, 'as': 'captain', 'in': '$$captain.v'}}]}}]
        if team: branches.append({'team_ids': team['_id']})
        query = {'kind': 'alliance', '$or': branches}
        if after: query['_id'] = {'$gt': after}
        rows = list(self.db.game_runs.find(query).sort('_id', 1).limit(21))
        return {'battles': [self._planning_summary(r) for r in rows[:20]], 'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def _history_access(self, actor_id, run, session=None):
        recorded = (set(run.get('recorded_captains', [])) | set(run.get('approvals', {}).values())
                    | set(run.get('shared_room', {}).get('captains', {}).values()))
        if actor_id in {p['account_id'] for p in run['participants']} | recorded: return
        self._planning_access(actor_id, run, session)

    def directory_battle_detail(self, actor_id, battle_id):
        from .domain import _directory_id
        self._directory_player(actor_id); _directory_id(battle_id, uuid=True)
        def read(session):
            run = self._run(battle_id, session)
            self._history_access(actor_id, run, session)
            return self._planning_record(run, session)
        return self._tx(read)

    def shared_result_review(self, actor_id, run_id):
        from .domain import DomainError, _directory_id
        self._directory_player(actor_id); run = self._run(_directory_id(run_id, uuid=True))
        if not run.get('shared_room'):
            raise DomainError('not_found', 'This plan has no shared result.')
        self._history_access(actor_id, run)
        return self._shared_review(run)

    def _governance_idle(self, team_id, session=None):
        from .domain import DomainError
        if self.db.game_runs.find_one({'kind': 'alliance', 'team_ids': team_id,
                '$or': [{'state': 'running'}, {'state': 'draft', 'shared_room.state': 'preparing'}]}, {'_id': 1}, session=session):
            raise DomainError('busy', 'Finish or cancel active team battles before changing team governance.')

    def transfer_captain(self, actor_id, team_id, new_captain_id):
        # The existing method writes this team's revision in the same transaction.
        # Read the running-run predicate from inside that transaction as well.
        from .domain import DomainError
        def write(session):
            team = self._team(team_id, session); self._captain(actor_id, team, session)
            self._governance_idle(team_id, session)
            if new_captain_id == actor_id or new_captain_id not in {m['account_id'] for m in team['members']}:
                raise DomainError('not_member', 'Choose another current member as captain.')
            # Validate and serialize the successor against account suspension.
            self._player(new_captain_id, session)
            self.db.teams.update_one({'_id': team_id}, {'$set': {'captain_id': new_captain_id}, '$inc': {'revision': 1}}, session=session)
            self.db.game_runs.update_many({'plan_format': PLAN_FORMAT, 'state': 'draft', 'team_ids': team_id},
                {'$set': {'approvals': {}, 'ready': []}, '$inc': {'revision': 1}}, session=session)
            return self._team(team_id, session)
        return self._tx(write)

    def admin_move_team(self, actor_id, team_id, area_id, reason):
        from .domain import _reason
        reason = _reason(reason)
        def write(session):
            self._admin(actor_id, session); team = self._team(team_id, session)
            self._governance_idle(team_id, session); self._area(area_id, session)
            self.db.teams.update_one({'_id': team_id}, {'$set': {'area_id': area_id}, '$inc': {'revision': 1}}, session=session)
            self._audit(actor_id, 'move_team', team_id, reason, {'area_id': team['area_id']}, {'area_id': area_id}, session)
            return self._team(team_id, session)
        return self._tx(write)

    def shared_replay_access(self, actor_id, run_id):
        from .domain import DomainError, _directory_id
        self._directory_player(actor_id); run = self._run(_directory_id(run_id, uuid=True))
        room = run.get('shared_room', {})
        if run['state'] != 'completed' or room.get('state') != 'completed':
            raise DomainError('invalid_state', 'A replay is available after settlement.')
        self._history_access(actor_id, run)
        reports = room.get('result_reports', {})
        source = actor_id if actor_id in reports else next((p['account_id'] for p in sorted(run['participants'], key=lambda p:p['side']) if p['account_id'] in reports), None)
        if source is None: raise DomainError('not_found', 'The completed recording is unavailable.')
        return {'run_id': run_id, 'account_id': source, 'generation': room['generation'], 'sha256': reports[source]['replay_sha256']}
