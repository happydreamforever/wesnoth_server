"""Unified account/hero product rules. All durable mutations use transactions.

The v2 database is created explicitly; no v1 account or saved game is converted
by starting a service. Story combat remains the trusted local-client model.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import hmac
import json
import re
import secrets

from .domain import DomainError, _id, _now, _directory_id, validate_username, public_account
from .heroes import hero_progress, load_catalog, catalog_hero, catalog_form, MAX_XP
from .rules import RULESET_VERSION, MAPS, TEAM_CAPACITY, MISSIONS, MISSION_NAMES, MISSION_VERSION


def owned_heroes(db, account_id, session=None):
    rows = list(db.account_heroes.find({'account_id': account_id}, session=session).sort('hero_id', 1))
    return [{'hero_id': row['hero_id'], 'name': catalog_hero(row['hero_id'])['name'],
             **hero_progress(row['total_experience']), 'revision': row['revision'],
             'forms': list(row['forms'])} for row in rows]


def account_profile(db, account, session=None):
    result = public_account(account)
    result['heroes'] = owned_heroes(db, account['_id'], session)
    return result


class UnifiedProduct:
    def _generation(self, session=None):
        record = self.db.schema_metadata.find_one({'_id': 'alliance', 'version': 2}, session=session)
        if record is None or not isinstance(record.get('database_generation'), str):
            raise DomainError('unsupported_ruleset', 'This product requires a new version 2 database.')
        return record['database_generation']

    def register(self, username, password_hash):
        username, key = validate_username(username)
        if not isinstance(password_hash, str) or not password_hash.startswith('$argon2id$') or len(password_hash) > 512:
            raise DomainError('invalid_input', 'An Argon2id password hash is required.')
        def write(session):
            account = {'_id': _id(), 'username': username, 'username_key': key,
                'password_hash': password_hash, 'role': 'player', 'status': 'active',
                'database_generation': self._generation(session), 'active_run_id': None,
                'revision': 0, 'training_completed': [], 'created_at': _now()}
            self.db.accounts.insert_one(account, session=session)
            return account_profile(self.db, account, session)
        return self._tx(write)

    def bootstrap_admin(self, username, password_hash):
        username, key = validate_username(username)
        if not isinstance(password_hash, str) or not password_hash.startswith('$argon2id$') or len(password_hash) > 512:
            raise DomainError('invalid_input', 'An Argon2id password hash is required.')
        def write(session):
            if self.db.accounts.find_one({'role': 'admin'}, session=session):
                raise DomainError('already_initialized', 'An administrator already exists.')
            account = {'_id': _id(), 'username': username, 'username_key': key,
                'password_hash': password_hash, 'role': 'admin', 'status': 'active',
                'database_generation': self._generation(session), 'active_run_id': None,
                'revision': 0, 'training_completed': [], 'created_at': _now()}
            self.db.schema_metadata.insert_one({'_id': 'admin-bootstrap', 'version': 2}, session=session)
            self.db.accounts.insert_one(account, session=session)
            self._audit(account['_id'], 'bootstrap_admin', account['_id'], 'First administrator setup',
                        None, {'username': username, 'role': 'admin'}, session)
            return account_profile(self.db, account, session)
        return self._tx(write)

    def get_account(self, account_id):
        return account_profile(self.db, self._account(account_id, active=False))

    def hero_catalog(self, actor_id):
        self._directory_player(actor_id)
        data, digest = load_catalog()
        return {'catalog_version': data['version'], 'catalog_sha256': digest,
                **{key: data[key] for key in ('heroes', 'forms', 'campaigns')}}

    def _member(self, account):
        return {'id': account['_id'], 'username': account['username'],
                'hero_count': self.db.account_heroes.count_documents({'account_id': account['_id']})}

    def _directory_team_record(self, team):
        area = self.db.areas.find_one({'_id': team['area_id']}, {'name': 1})
        if area is None:
            raise DomainError('not_found', 'The team area is unavailable.')
        return dict(id=team['_id'], name=team['name'], area_id=team['area_id'], area_name=area['name'],
            captain_id=team['captain_id'], level=team['level'], experience=team['experience'],
            rating=team['rating'], capacity=TEAM_CAPACITY,
            members=[self._member(self._account(m['account_id'], active=False)) for m in team['members']])

    def directory_team_applicants(self, actor_id, team_id, after=''):
        self._directory_player(actor_id)
        team = self._team(_directory_id(team_id, uuid=True))
        _directory_id(after, empty=True, uuid=True)
        if team['captain_id'] != actor_id:
            raise DomainError('forbidden', 'Only the team captain can view applications.')
        query = {'_id': {'$in': team['join_requests']}}
        if after:
            query['_id']['$gt'] = after
        rows = list(self.db.accounts.find(query, {'username': 1}).sort('_id', 1).limit(21))
        return {'team_id': team_id, 'applicants': [self._member(row) for row in rows[:20]],
                'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def get_team(self, actor_id, team_id):
        self._account(actor_id)
        team = self._team(team_id)
        requests = team.pop('join_requests')
        for member in team['members']:
            account = self._account(member['account_id'], active=False)
            member.update(username=account['username'], heroes=owned_heroes(self.db, account['_id']))
        if team['captain_id'] == actor_id:
            team['join_requests'] = requests
            team['applicants'] = [self._member(a) for a in self.db.accounts.find({'_id': {'$in': requests}})]
        return team

    def _hero(self, actor_id, hero_id, session=None):
        if not isinstance(hero_id, str) or not re.fullmatch(r'[a-z0-9_-]{1,80}', hero_id):
            raise DomainError('invalid_input', 'The hero identifier is invalid.')
        row = self.db.account_heroes.find_one({'account_id': actor_id, 'hero_id': hero_id}, session=session)
        if row is None:
            raise DomainError('hero_locked', 'Complete a campaign scenario controlling this hero to unlock it.')
        return row

    def _selection(self, actor_id, hero_id, form_id, session=None):
        row = self._hero(actor_id, hero_id, session)
        if not isinstance(form_id, str) or form_id not in row['forms']:
            raise DomainError('form_locked', 'This hero form has not been earned.')
        try:
            _, form = catalog_form(hero_id, form_id)
        except ValueError as error:
            raise DomainError('invalid_input', str(error)) from error
        return {'hero_id': hero_id, 'form_id': form_id,
                'hero_level': hero_progress(row['total_experience'])['hero_level'],
                'hero_revision': row['revision'], 'unit_type': form['unit_type'],
                'unit_level': form['native_level']}

    def _planning_context(self, run, session=None):
        teams = [self.db.teams.find_one({'_id': key}, session=session) for key in run['team_ids']]
        ids = {p['account_id'] for p in run['participants']}
        ids.update(team['captain_id'] for team in teams if team and team['captain_id'])
        accounts = {a['_id']: a for a in self.db.accounts.find({'_id': {'$in': list(ids)}}, session=session)}
        for account in accounts.values():
            account['_hero_rows'] = {row['hero_id']: row for row in self.db.account_heroes.find({'account_id': account['_id']}, session=session)}
        area = self.db.areas.find_one({'_id': run['area_id']}, session=session)
        return teams, accounts, area

    def _planning_validity(self, run, teams, accounts, area):
        if run['ruleset_version'] != RULESET_VERSION:
            return 'rules_changed'
        if any(team is None or team['status'] != 'active' for team in teams):
            return 'team_unavailable'
        if any(team['area_id'] != run['area_id'] for team in teams):
            return 'area_changed'
        if area is None or not area['enabled'] or run['map_id'] not in area['approved_maps']:
            return 'map_unavailable'
        if any(not set(run['lineups'][team['_id']]).issubset({m['account_id'] for m in team['members']}) for team in teams):
            return 'roster_changed'
        if any(a not in accounts or accounts[a]['status'] != 'active' or accounts[a]['role'] != 'player'
               for a in {p['account_id'] for p in run['participants']} | {t['captain_id'] for t in teams}):
            return 'player_unavailable'
        for player in run['participants']:
            selected = player.get('selection')
            if selected is not None:
                try:
                    row = accounts[player['account_id']]['_hero_rows'].get(selected['hero_id'])
                    if row is None or selected['form_id'] not in row['forms']:
                        return 'leader_changed'
                    _, form = catalog_form(selected['hero_id'], selected['form_id'])
                    current = {'hero_id': row['hero_id'], 'form_id': selected['form_id'], 'hero_revision': row['revision'],
                        'hero_level': hero_progress(row['total_experience'])['hero_level'], 'unit_type': form['unit_type'], 'unit_level': form['native_level']}
                except (DomainError, ValueError):
                    return 'leader_changed'
                if current != selected and run['state'] not in ('completed', 'cancelled'):
                    return 'leader_changed'
        allowed = run['_id'] if run['state'] == 'running' else None
        ids = {p['account_id'] for p in run['participants']}
        if run['state'] != 'running':
            ids.update(t['captain_id'] for t in teams)
        if any(t['active_run_id'] not in (None, allowed) for t in teams) or any(accounts[a]['active_run_id'] not in (None, allowed) for a in ids):
            return 'busy'
        return 'valid'

    def _planning_record(self, run, session=None):
        teams, accounts, area = self._planning_context(run, session)
        result = self._planning_summary(run, session)
        result.pop('map_id')
        result.update(map=self._planning_map(run['map_id']), validity=self._planning_validity(run, teams, accounts, area))
        for display, current in zip(result['teams'], teams):
            historic = run['state'] == 'completed' and run.get('shared_room', {}).get('state') == 'completed'
            captain = (run['shared_room']['captains'].get(display['id'], '') if historic else
                       current['captain_id'] if current and current['status'] == 'active' else '')
            display.update(captain_id=captain, approved=bool(captain and run['approvals'].get(display['id']) == captain),
                players=[{'id': p['account_id'], 'username': p.get('username') or accounts[p['account_id']]['username'],
                    'side': p['side'], 'ready': p['account_id'] in run['ready'], 'selection': deepcopy(p.get('selection'))}
                    for p in run['participants'] if p['team_id'] == display['id']])
        return result

    def _validate_battle_teams(self, teams, map_id, lineups, session):
        if teams[0]['area_id'] != teams[1]['area_id']:
            raise DomainError('different_area', 'Both teams must belong to the same area.')
        area = self._area(teams[0]['area_id'], session)
        if map_id not in area['approved_maps']:
            raise DomainError('invalid_map', 'This map is not enabled in the area.')
        ids = []
        for team in teams:
            self._idle(team)
            self._idle(self._player(team['captain_id'], session))
            self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
            if not set(lineups[team['_id']]).issubset({m['account_id'] for m in team['members']}):
                raise DomainError('not_member', 'Every selected player must belong to that team.')
            for actor in lineups[team['_id']]:
                self._idle(self._player(actor, session))
                ids.append(actor)
        if len(ids) != len(set(ids)):
            raise DomainError('invalid_lineup', 'A player cannot fight on both teams.')

    def create_battle(self, actor_id, opponent_team_id, map_id, lineups, *, expected_team_id=None, native_plan=False):
        if not isinstance(map_id, str) or map_id not in MAPS:
            raise DomainError('invalid_map', 'Choose an approved team map.')
        if (not isinstance(lineups, dict) or len(lineups) != 2 or any(not isinstance(ids, list) or
                len(ids) != MAPS[map_id]['size'] or any(not isinstance(a, str) for a in ids) or len(set(ids)) != len(ids)
                for ids in lineups.values())):
            raise DomainError('invalid_lineup', 'Choose distinct accounts for both complete lineups.')
        def write(session):
            self._player(actor_id, session)
            first = self.db.teams.find_one({'captain_id': actor_id, 'status': 'active'}, session=session)
            if first is None:
                raise DomainError('forbidden', 'Only a captain may propose a battle.')
            second = self._team(opponent_team_id, session)
            if expected_team_id is not None and first['_id'] != expected_team_id:
                raise DomainError('conflict', 'Your team changed after this proposal was opened.')
            if first['_id'] == second['_id'] or set(lineups) != {first['_id'], second['_id']}:
                raise DomainError('invalid_lineup', 'The current teams differ from this proposal.')
            teams = [first, second]
            self._validate_battle_teams(teams, map_id, lineups, session)
            if self.db.game_runs.find_one({'kind': 'alliance', 'state': 'draft', 'team_ids': {'$in': [t['_id'] for t in teams]}}, session=session):
                raise DomainError('planning_exists', 'A participating team already has a draft.')
            participants = self._participants(teams, map_id, lineups)
            for p in participants:
                p.update(username=self._account(p['account_id'], session)['username'], selection=None)
            run = {'_id': _id(), 'kind': 'alliance', 'state': 'draft', 'ruleset_version': RULESET_VERSION,
                'map_id': map_id, 'area_id': first['area_id'], 'team_ids': [t['_id'] for t in teams],
                'lineups': deepcopy(lineups), 'approvals': {}, 'ready': [], 'participants': participants,
                'created_at': _now(), 'planning_teams': [{'id': t['_id'], 'name': t['name']} for t in teams]}
            self.db.game_runs.insert_one(run, session=session)
            return self._planning_record(run, session) if native_plan else run
        return self._tx(write)

    def directory_select_hero(self, actor_id, battle_id, hero_id, form_id):
        _directory_id(battle_id, uuid=True)
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            run = self._run(battle_id, session)
            self._draft(run)
            self._planning_access(actor_id, run, session)
            if run.get('shared_room') and run['shared_room'].get('state') not in ('expired', 'cancelled'):
                raise DomainError('room_conflict', 'Leave the prepared room before changing its heroes.')
            selected = self._selection(actor_id, hero_id, form_id, session)
            own = next((p for p in run['participants'] if p['account_id'] == actor_id), None)
            if own is None:
                raise DomainError('forbidden', 'Only a selected player may choose this hero.')
            if own.get('selection') != selected:
                own['selection'] = selected
                self.db.game_runs.update_one({'_id': battle_id}, {'$set': {
                    'participants': run['participants'], 'ready': [], 'approvals': {}}}, session=session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def _check_preview(self, run, session):
        self._require_ruleset(run)
        for player in run['participants']:
            selected = player.get('selection')
            if selected is None:
                raise DomainError('hero_required', 'Every selected player must choose a hero before approval and Ready.')
            if selected != self._selection(player['account_id'], selected['hero_id'], selected['form_id'], session):
                raise DomainError('stale_proposal', 'A selected hero changed. Choose it again before approval.')

    def _planning_validate_mutation(self, run, session):
        teams, accounts, area = self._planning_context(run, session)
        validity = self._planning_validity(run, teams, accounts, area)
        if validity != 'valid':
            raise DomainError('busy' if validity == 'busy' else 'stale_proposal', 'This plan changed. Refresh its details.')
        self._check_preview(run, session)
        for team in teams:
            self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        for actor_id in accounts:
            self._player(actor_id, session)
        return teams

    def directory_battle_ready(self, actor_id, battle_id, ready):
        _directory_id(battle_id, uuid=True)
        if type(ready) is not bool:
            raise DomainError('invalid_input', 'Readiness must be a boolean.')
        def write(session):
            self._player(actor_id, session)
            run = self._run(battle_id, session)
            self._planning_access(actor_id, run, session)
            self._draft(run)
            own = next((p for p in run['participants'] if p['account_id'] == actor_id), None)
            if own is None:
                raise DomainError('forbidden', 'Only a selected player can change readiness.')
            teams, accounts, area = self._planning_context(run, session)
            if ready and self._planning_validity(run, teams, accounts, area) != 'valid':
                raise DomainError('stale_proposal', 'This plan changed. Refresh its details.')
            if ready and own.get('selection') is None:
                raise DomainError('hero_required', 'Choose an owned hero before Ready.')
            for team in teams:
                self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
            self.db.game_runs.update_one({'_id': battle_id},
                {'$addToSet' if ready else '$pull': {'ready': actor_id}}, session=session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def _cancel(self, run_id, reason, session):
        run = self._run(run_id, session)
        if 'campaign_id' not in run:
            return super()._cancel(run_id, reason, session)
        if run['state'] == 'completed':
            raise DomainError('invalid_state', 'A completed story cannot be cancelled.')
        self.db.game_runs.update_one({'_id': run_id}, {'$set': {
            'state': 'cancelled', 'cancel_reason': reason, 'finished_at': _now()}}, session=session)
        return self._run(run_id, session)

    def _reserve_account(self, account_id, run_id, session):
        account = self._player(account_id, session)
        self._idle(account)
        self.db.accounts.update_one({'_id': account_id}, {'$set': {'active_run_id': run_id}, '$inc': {'revision': 1}}, session=session)
        return account

    def _start_battle(self, actor_id, run_id, session, *, shared_authorized=False):
        run = self._run(run_id, session)
        self._draft(run)
        if run.get('shared_room') and not shared_authorized:
            raise DomainError('room_required', 'Start this room through its all-loaded barrier.')
        teams = [self._team(t, session) for t in run['team_ids']]
        if actor_id not in [t['captain_id'] for t in teams]:
            raise DomainError('forbidden', 'A participating captain must start this battle.')
        self._validate_battle_teams(teams, run['map_id'], run['lineups'], session)
        self._check_preview(run, session)
        if teams[0]['area_id'] != run['area_id']:
            raise DomainError('area_changed', 'The team area changed.')
        if any(run['approvals'].get(t['_id']) != t['captain_id'] for t in teams):
            raise DomainError('approval_required', 'Both captains must approve the selected heroes and lineups.')
        if set(run['ready']) != {p['account_id'] for p in run['participants']}:
            raise DomainError('not_ready', 'Every selected player must be ready.')
        for player in run['participants']:
            self._reserve_account(player['account_id'], run_id, session)
        for team in teams:
            self.db.teams.update_one({'_id': team['_id']}, {'$set': {'active_run_id': run_id}, '$inc': {'revision': 1}}, session=session)
        self.db.game_runs.update_one({'_id': run_id}, {'$set': {'state': 'running', 'started_at': _now()}}, session=session)
        return self._run(run_id, session)

    def _reward_player(self, participant, run, amount, session, mission_complete=False):
        account = self._account(participant['account_id'], session, active=False)
        if account['active_run_id'] != run['_id']:
            raise DomainError('reservation_conflict', 'The account is not reserved by this game.')
        selected = participant['selection']
        if selected != self._selection(account['_id'], selected['hero_id'], selected['form_id'], session):
            raise DomainError('snapshot_conflict', 'The selected hero changed during this game.')
        if self._hero(account['_id'], selected['hero_id'], session)['total_experience'] + amount > MAX_XP:
            raise DomainError('invalid_result', 'The hero experience storage limit was reached.')
        if amount:
            self.db.account_heroes.update_one({'account_id': account['_id'], 'hero_id': selected['hero_id']},
                {'$inc': {'total_experience': amount, 'revision': 1}}, session=session)
        self.db.accounts.update_one({'_id': account['_id']}, {'$set': {'active_run_id': None}, '$inc': {'revision': 1}}, session=session)
        hero = self._hero(account['_id'], selected['hero_id'], session)
        if mission_complete:
            self.db.accounts.update_one({'_id': account['_id']}, {'$addToSet': {'training_completed': run['mission_id']}}, session=session)
        return {'account_id': account['_id'], 'hero_id': selected['hero_id'], 'experience': amount,
                'hero': {**hero_progress(hero['total_experience']), 'revision': hero['revision']}}

    def choose_advancement(self, *args, **kwargs):
        raise DomainError('unsupported_ruleset', 'Hero forms are earned in story campaigns.')

    def start_campaign(self, *args, **kwargs):
        raise DomainError('unsupported_ruleset', 'Start a story from the Campaigns menu.')

    def _finish_campaign(self, run_id, outcome, session):
        run = self._run(run_id, session)
        if not run.get('native_campaign'):
            raise DomainError('invalid_state', 'Story campaigns use their bound scenario checkpoints.')
        return super()._finish_campaign(run_id, outcome, session)

    def _progression_profile(self, account, session=None):
        return {'id': account['_id'], 'username': account['username'],
                'database_generation': account['database_generation'],
                'heroes': owned_heroes(self.db, account['_id'], session)}

    def progression_catalog(self, actor_id):
        actor = self._directory_player(actor_id)
        completed = actor.get('training_completed', [])
        missions = [{'id': mission, 'name': MISSION_NAMES[mission], 'version': MISSION_VERSION,
            'unlocked': all(previous in completed for previous in MISSIONS[:index]),
            'completed': mission in completed, 'victory_experience': 20}
            for index, mission in enumerate(MISSIONS)]
        active = None
        if actor['active_run_id']:
            run = self._run(actor['active_run_id'])
            if run.get('native_campaign'):
                active = self._campaign_record(actor_id, run, nonce=True)
        return {'profile': self._progression_profile(actor), 'missions': missions, 'active_run': active}

    def progression_start(self, actor_id, mission_id, hero_id, form_id):
        if mission_id not in MISSIONS:
            raise DomainError('invalid_mission', 'Choose an approved training mission.')
        def write(session):
            actor = self._player(actor_id, session)
            if any(m not in actor.get('training_completed', []) for m in MISSIONS[:MISSIONS.index(mission_id)]):
                raise DomainError('mission_locked', 'Complete the previous training mission first.')
            selection = self._selection(actor_id, hero_id, form_id, session)
            run_id = _id()
            self._reserve_account(actor_id, run_id, session)
            run = {'_id': run_id, 'kind': 'campaign', 'state': 'running',
                'ruleset_version': RULESET_VERSION, 'mission_id': mission_id,
                'database_generation': self._generation(session),
                'participants': [{'account_id': actor_id, 'selection': selection}],
                'created_at': _now(), 'started_at': _now(),
                'native_campaign': {'mission_version': MISSION_VERSION, 'nonce': secrets.token_hex(32), 'username': actor['username']}}
            self.db.game_runs.insert_one(run, session=session)
            return {'run': self._campaign_record(actor_id, run, nonce=True, session=session)}
        return self._tx(write)

    def _campaign_record(self, actor_id, run, *, nonce=False, session=None):
        if (run['kind'] != 'campaign' or len(run['participants']) != 1 or
                run['participants'][0]['account_id'] != actor_id or not run.get('native_campaign')):
            raise DomainError('forbidden', 'Only the owner can access this training run.')
        selected = run['participants'][0]['selection']
        native = run['native_campaign']
        receipt = self.db.settlements.find_one({'_id': run['_id']}, session=session)
        return {'id': run['_id'], 'account_id': actor_id, 'username': native['username'],
            'database_generation': run['database_generation'],
            'hero_id': selected['hero_id'], 'form_id': selected['form_id'], 'hero_level': selected['hero_level'],
            'mission_id': run['mission_id'], 'mission_name': MISSION_NAMES[run['mission_id']],
            'mission_version': native['mission_version'], 'ruleset_version': run['ruleset_version'],
            'state': run['state'], 'unit_type': selected['unit_type'], 'leader_level': selected['unit_level'],
            'nonce': native['nonce'] if nonce and run['state'] == 'running' else '',
            'created_at': self._time(run['created_at']), 'finished_at': self._time(run.get('finished_at')),
            'outcome': run.get('result', {}).get('outcome', ''),
            'experience_awarded': receipt['rewards']['players'][0]['experience'] if receipt else 0}

    def progression_history(self, actor_id):
        self._directory_player(actor_id)
        rows = list(self.db.game_runs.find({'kind': 'campaign', 'native_campaign': {'$exists': True},
            'participants.account_id': actor_id}).sort([('created_at', -1), ('_id', 1)]).limit(21))
        return {'runs': [self._campaign_record(actor_id, row) for row in rows[:20]], 'has_more': len(rows) > 20}

    def story_begin(self, actor_id, campaign_id, catalog_version, catalog_sha256):
        catalog, digest = load_catalog()
        campaign = next((c for c in catalog['campaigns'] if c['id'] == campaign_id), None)
        if campaign is None or catalog_version != catalog['version'] or catalog_sha256 != digest:
            raise DomainError('catalog_mismatch', 'The campaign catalogue differs from this server.')
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            run = {'_id': _id(), 'kind': 'campaign', 'state': 'running',
                'ruleset_version': RULESET_VERSION, 'participants': [{'account_id': actor_id}],
                'database_generation': self._generation(session), 'campaign_id': campaign_id,
                'catalog_version': catalog_version, 'catalog_sha256': digest,
                'nonce': secrets.token_hex(32), 'next_checkpoint': 0,
                'next_scenario_id': campaign['first_scenario'], 'completed_scenarios': [],
                'created_at': _now()}
            self.db.game_runs.insert_one(run, session=session)
            return self._story_record(actor_id, run)
        return self._tx(write)

    @staticmethod
    def _story_record(actor_id, run):
        if run['kind'] != 'campaign' or run['participants'] != [{'account_id': actor_id}] or 'campaign_id' not in run:
            raise DomainError('forbidden', 'This campaign belongs to another account.')
        return {'run_id': run['_id'], 'account_id': actor_id,
            **{key: run[key] for key in ('database_generation', 'campaign_id', 'catalog_version',
                'catalog_sha256', 'next_checkpoint', 'nonce')}}

    def story_status(self, actor_id, run_id):
        self._directory_player(actor_id)
        _directory_id(run_id, uuid=True)
        return self._story_record(actor_id, self._run(run_id))

    def story_checkpoint(self, actor_id, data):
        expected = {'run_id', 'checkpoint_id', 'sequence', 'scenario_id', 'next_scenario_id',
                    'outcome', 'heroes', 'replay_sha256', 'nonce'}
        if not isinstance(data, dict) or set(data) != expected:
            raise DomainError('invalid_result', 'The campaign checkpoint fields are invalid.')
        for key in ('run_id', 'checkpoint_id'):
            _directory_id(data[key], uuid=True)
        if (any(not isinstance(data[key], str) or len(data[key]) > 200 for key in ('scenario_id', 'next_scenario_id', 'outcome')) or
                type(data['sequence']) is not int or not 0 <= data['sequence'] <= 2147483647 or
                data['outcome'] not in ('win', 'loss') or not isinstance(data['heroes'], list) or
                len(data['heroes']) > 128 or any(not isinstance(data[key], str) or
                not re.fullmatch('[0-9a-f]{64}', data[key]) for key in ('nonce', 'replay_sha256'))):
            raise DomainError('invalid_result', 'The campaign checkpoint is invalid.')
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        catalog, catalog_digest = load_catalog()
        def write(session):
            actor = self._player(actor_id, session)
            run = self._run(data['run_id'], session)
            self._story_record(actor_id, run)
            if (run['database_generation'] != self._generation(session) or
                    not hmac.compare_digest(data['nonce'], run['nonce'])):
                raise DomainError('invalid_result', 'The campaign belongs to another database or run.')
            previous = self.db.story_checkpoints.find_one({'_id': data['checkpoint_id']}, session=session)
            if previous is not None:
                if previous['account_id'] != actor_id or previous['run_id'] != run['_id'] or previous['digest'] != digest:
                    raise DomainError('result_conflict', 'This checkpoint already has a different result.')
                return previous['result']
            self._idle(actor)
            if run['state'] != 'running' or data['sequence'] != run['next_checkpoint']:
                raise DomainError('checkpoint_conflict', 'Restore the latest campaign checkpoint before continuing.')
            if catalog['version'] != run['catalog_version'] or catalog_digest != run['catalog_sha256']:
                raise DomainError('catalog_mismatch', 'The saved campaign requires its original catalogue.')
            campaign = next(c for c in catalog['campaigns'] if c['id'] == run['campaign_id'])
            if (data['scenario_id'] not in campaign['scenario_ids'] or
                    data['scenario_id'] != run['next_scenario_id'] or
                    (data['next_scenario_id'] and data['next_scenario_id'] not in campaign['scenario_ids'])):
                raise DomainError('invalid_result', 'The campaign scenario sequence does not match this run.')
            seen, earned = set(), []
            for row in data['heroes']:
                if not isinstance(row, dict) or set(row) != {'hero_id', 'unit_id', 'form_id', 'unlocked_forms', 'earned_experience'}:
                    raise DomainError('invalid_result', 'The hero earning record is invalid.')
                if any(not isinstance(row[key], str) for key in ('hero_id', 'unit_id', 'form_id')):
                    raise DomainError('invalid_result', 'Hero identifiers must be text.')
                if row['hero_id'] in seen:
                    raise DomainError('invalid_result', 'A hero may appear only once per checkpoint.')
                seen.add(row['hero_id'])
                alias = next((a for a in campaign['aliases'] if a['unit_id'] == row['unit_id'] and a['hero_id'] == row['hero_id']), None)
                forms = row['unlocked_forms']
                if (alias is None or type(row['earned_experience']) is not int or
                        not 0 <= row['earned_experience'] <= 1000000 or not isinstance(forms, list) or
                        any(not isinstance(f, str) for f in forms) or len(forms) != len(set(forms)) or
                        not forms or row['form_id'] not in forms or
                        not set(forms).issubset({f['form_id'] for a in campaign['aliases'] if a['hero_id'] == row['hero_id'] for f in a['forms']})):
                    raise DomainError('invalid_result', 'The reported hero or form is not in this campaign.')
                amount = 0
                if data['outcome'] == 'win' and data['scenario_id'] not in run['completed_scenarios']:
                    amount = row['earned_experience'] + 20
                    current = self.db.account_heroes.find_one({'account_id': actor_id, 'hero_id': row['hero_id']}, session=session)
                    if current is not None and current['total_experience'] + amount > MAX_XP:
                        raise DomainError('invalid_result', 'The hero experience storage limit was reached.')
                    self.db.account_heroes.update_one({'account_id': actor_id, 'hero_id': row['hero_id']}, {
                        '$setOnInsert': {'_id': _id(), 'unlocked_at': _now()},
                        '$inc': {'total_experience': amount, 'revision': 1},
                        '$addToSet': {'forms': {'$each': forms}}}, upsert=True, session=session)
                earned.append({'hero_id': row['hero_id'], 'experience_awarded': amount})
            update = {'$inc': {'next_checkpoint': 1}}
            if data['outcome'] == 'win':
                update['$addToSet'] = {'completed_scenarios': data['scenario_id']}
                update['$set'] = {'next_scenario_id': data['next_scenario_id']}
                if not data['next_scenario_id']:
                    update['$set'].update(state='completed', finished_at=_now())
            self.db.game_runs.update_one({'_id': run['_id']}, update, session=session)
            result = {'run_id': run['_id'], 'checkpoint_id': data['checkpoint_id'],
                      'next_checkpoint': data['sequence'] + 1, 'outcome': data['outcome'], 'rewards': earned,
                      'heroes': owned_heroes(self.db, actor_id, session)}
            self.db.story_checkpoints.insert_one({'_id': data['checkpoint_id'], 'run_id': run['_id'],
                'account_id': actor_id, 'sequence': data['sequence'], 'digest': digest,
                'result': result, 'created_at': _now()}, session=session)
            return result
        return self._tx(write)

    def _casual_session(self, actor_id, token, session, *, digest=False):
        if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}' if digest else r'[A-Za-z0-9_-]{43}', token):
            raise DomainError('invalid_ticket', 'Please sign in again before joining multiplayer.')
        session_id = token if digest else hashlib.sha256(token.encode('ascii')).hexdigest()
        result = self.db.auth_sessions.update_one({'_id': session_id, 'account_id': actor_id,
            'scope': 'player', 'revoked': False, 'expires_at': {'$gt': _now()}},
            {'$inc': {'ticket_uses': 1}}, session=session)
        if result.matched_count != 1:
            raise DomainError('invalid_ticket', 'Please sign in again before joining multiplayer.')
        return session_id

    def casual_ticket(self, actor_id, session_token):
        def write(session):
            actor = self._player(actor_id, session)
            session_id = self._casual_session(actor_id, session_token, session)
            token = secrets.token_urlsafe(32)
            expires = _now() + timedelta(seconds=60)
            self.db.casual_tickets.insert_one({'_id': hashlib.sha256(token.encode()).hexdigest(),
                'account_id': actor_id, 'session_digest': session_id, 'username': actor['username'], 'purpose': 'lobby',
                'database_generation': self._generation(session), 'expires_at': expires, 'consumed': False}, session=session)
            return {'ticket': token, 'username': actor['username'], 'account_id': actor_id,
                    'database_generation': actor['database_generation'], 'expires_at': self._time(expires)}
        return self._tx(write)

    def _consume_ticket(self, token, purpose, session):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise DomainError('invalid_ticket', 'This admission ticket is invalid or expired.')
        row = self.db.casual_tickets.find_one({'_id': hashlib.sha256(token.encode()).hexdigest(),
            'purpose': purpose, 'consumed': False, 'expires_at': {'$gt': _now()},
            'database_generation': self._generation(session)}, session=session)
        if row is None:
            raise DomainError('invalid_ticket', 'This admission ticket is invalid or expired.')
        self._player(row['account_id'], session)
        self._casual_session(row['account_id'], row.get('session_digest'), session, digest=True)
        self.db.casual_tickets.update_one({'_id': row['_id']}, {'$set': {'consumed': True}}, session=session)
        return row

    def casual_admit(self, ticket, username):
        def write(session):
            row = self._consume_ticket(ticket, 'lobby', session)
            actor = self._account(row['account_id'], session)
            if username != row['username'] or actor['username'] != username:
                raise DomainError('invalid_ticket', 'This ticket belongs to another account name.')
            return {'account_id': row['account_id'], 'username': username,
                    'database_generation': row['database_generation']}
        return self._tx(write)

    def casual_select(self, actor_id, game_id, side, hero_id, form_id, session_token):
        if not isinstance(game_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', game_id) or type(side) is not int or not 1 <= side <= 99:
            raise DomainError('invalid_input', 'Choose a valid game side.')
        def write(session):
            self._player(actor_id, session)
            snapshot = self._selection(actor_id, hero_id, form_id, session)
            session_id = self._casual_session(actor_id, session_token, session)
            token = secrets.token_urlsafe(32)
            self.db.casual_tickets.insert_one({'_id': hashlib.sha256(token.encode()).hexdigest(),
                'account_id': actor_id, 'session_digest': session_id, 'purpose': 'hero', 'game_id': game_id, 'side': side,
                'selection': snapshot, 'database_generation': self._generation(session),
                'expires_at': _now() + timedelta(seconds=60), 'consumed': False}, session=session)
            return {'selection_ticket': token, 'selection': snapshot}
        return self._tx(write)

    def casual_consume_hero(self, ticket, account_id, game_id, side):
        def write(session):
            row = self._consume_ticket(ticket, 'hero', session)
            if (row['account_id'], row['game_id'], row['side']) != (account_id, game_id, side):
                raise DomainError('invalid_ticket', 'This hero choice belongs to another player or side.')
            selected = row['selection']
            if selected != self._selection(account_id, selected['hero_id'], selected['form_id'], session):
                raise DomainError('stale_proposal', 'This hero changed after selection.')
            return {'selection': selected}
        return self._tx(write)

    def casual_freeze(self, game_id, players):
        _directory_id(game_id, uuid=True)
        if not isinstance(players, list) or not 1 <= len(players) <= 99:
            raise DomainError('invalid_input', 'A casual game needs authenticated human seats.')
        def write(session):
            seen_accounts, seen_sides = set(), set()
            for row in players:
                if not isinstance(row, dict) or set(row) != {'account_id', 'username', 'side', 'selection'}:
                    raise DomainError('invalid_input', 'Invalid casual side record.')
                if (not isinstance(row['account_id'], str) or row['account_id'] in seen_accounts or
                        type(row['side']) is not int or not 1 <= row['side'] <= 99 or row['side'] in seen_sides):
                    raise DomainError('invalid_input', 'Each human controls exactly one authenticated side.')
                seen_accounts.add(row['account_id']); seen_sides.add(row['side'])
                actor = self._player(row['account_id'], session)
                selected = row['selection']
                if (actor['username'] != row['username'] or not isinstance(selected, dict) or
                        set(selected) != {'hero_id', 'form_id', 'hero_level', 'hero_revision', 'unit_type', 'unit_level'}):
                    raise DomainError('invalid_input', 'The casual selection is malformed.')
                previous = self.db.casual_games.find_one({'_id': game_id}, session=session)
                if previous is None and selected != self._selection(actor['_id'], selected['hero_id'], selected['form_id'], session):
                    raise DomainError('stale_proposal', 'A selected hero changed before the game started.')
            document = {'_id': game_id, 'database_generation': self._generation(session),
                'players': sorted(players, key=lambda p: p['side'])}
            previous = self.db.casual_games.find_one({'_id': game_id}, session=session)
            if previous:
                if any(previous[key] != document[key] for key in document):
                    raise DomainError('snapshot_conflict', 'A saved casual game keeps its original players and heroes.')
            else:
                self.db.casual_games.insert_one({**document, 'created_at': _now()}, session=session)
            return {'game_id': game_id, 'database_generation': document['database_generation'], 'players': document['players']}
        return self._tx(write)

    def casual_restore(self, game_id):
        _directory_id(game_id, uuid=True)
        record = self.db.casual_games.find_one({'_id': game_id, 'database_generation': self._generation()})
        if record is None:
            raise DomainError('not_found', 'The saved multiplayer game belongs to another database or is unavailable.')
        return {'game_id': game_id, 'database_generation': record['database_generation'], 'players': record['players']}

    def admin_correct_hero_experience(self, actor_id, account_id, hero_id, delta, reason, expected_revision):
        from .domain import _reason
        reason = _reason(reason)
        if type(delta) is not int or delta == 0 or not -1000000 <= delta <= 1000000 or type(expected_revision) is not int:
            raise DomainError('invalid_input', 'Choose a nonzero experience correction and current hero revision.')
        def write(session):
            self._admin(actor_id, session)
            self._idle(self._player(account_id, session))
            row = self._hero(account_id, hero_id, session)
            if row['revision'] != expected_revision:
                raise DomainError('stale_account', 'This hero changed. Refresh before saving.')
            total = row['total_experience'] + delta
            if not 0 <= total <= MAX_XP:
                raise DomainError('invalid_correction', 'The correction would produce invalid experience.')
            self.db.account_heroes.update_one({'_id': row['_id']}, {'$set': {'total_experience': total}, '$inc': {'revision': 1}}, session=session)
            self._audit(actor_id, 'correct_hero_experience', account_id, reason,
                {'hero_id': hero_id, 'total_experience': row['total_experience']},
                {'hero_id': hero_id, 'total_experience': total}, session)
            return account_profile(self.db, self._account(account_id, session), session)
        return self._tx(write)
