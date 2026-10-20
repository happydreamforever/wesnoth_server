"""Transactional Alliance persistence and rules, independent of HTTP or WML.

The bridge is trusted to identify a finished game. This service validates roster,
state and fixed rewards, but does not simulate or independently verify combat.
Every mutation runs in a replica-set transaction; clients never submit XP/stats.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import uuid4

from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .rules import (STARTERS, MAPS, MISSIONS, RULESET_VERSION, TEAM_CAPACITY, MAX_JOIN_REQUESTS,
                    LEADER_REWARDS, TEAM_REWARDS, new_leader, award_experience,
                    advance_leader, team_level, rating_delta)


class DomainError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now():
    return datetime.now(timezone.utc)


def _id():
    return str(uuid4())


def _name(value, label, username=False):
    if not isinstance(value, str):
        raise DomainError('invalid_input', f'{label} must be text.')
    value = value.strip()
    pattern = r'[A-Za-z0-9_]{3,24}' if username else r'[A-Za-z0-9][A-Za-z0-9 _-]{2,39}'
    if not re.fullmatch(pattern, value):
        raise DomainError('invalid_input', f'{label} has an unsupported length or characters.')
    return value, value.casefold()


def validate_username(value):
    """Return the normalized username and lookup key used for every account."""
    return _name(value, 'Username', username=True)


def _directory_id(value, *, empty=False, uuid=False):
    """Bound public directory selectors before using them in any database query."""
    if empty and value == '':
        return value
    pattern = (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
               if uuid else r'[A-Za-z0-9_-]{1,64}')
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise DomainError('invalid_input', 'The directory identifier is invalid.')
    return value


def _reason(value):
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 500:
        raise DomainError('invalid_input', 'A reason between 3 and 500 characters is required.')
    return value.strip()


def public_account(document):
    result = deepcopy(document)
    result.pop('password_hash', None)
    return result


class AllianceService:
    def __init__(self, db):
        self.db = db

    def _tx(self, callback):
        try:
            with self.db.client.start_session() as session:
                return session.with_transaction(callback, read_concern=ReadConcern('snapshot'),
                    write_concern=WriteConcern('majority'), read_preference=ReadPreference.PRIMARY,
                    max_commit_time_ms=10000)
        except DuplicateKeyError as error:
            raise DomainError('conflict', 'A name or team membership is already in use.') from error

    def _account(self, account_id, session=None, active=True):
        if not isinstance(account_id, str):
            raise DomainError('invalid_input', 'Account ID must be text.')
        account = self.db.accounts.find_one({'_id': account_id}, session=session)
        if account is None:
            raise DomainError('not_found', 'Account not found.')
        if active and account['status'] != 'active':
            raise DomainError('suspended', 'Account is suspended.')
        return account

    def _player(self, account_id, session):
        account = self._account(account_id, session)
        if account['role'] != 'player':
            raise DomainError('forbidden', 'Administrator accounts do not participate as players.')
        self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
        account['revision'] += 1
        return account

    def _team(self, team_id, session=None):
        if not isinstance(team_id, str):
            raise DomainError('invalid_input', 'Team ID must be text.')
        team = self.db.teams.find_one({'_id': team_id, 'status': 'active'}, session=session)
        if team is None:
            raise DomainError('not_found', 'Active team not found.')
        return team

    def _area(self, area_id, session=None):
        if not isinstance(area_id, str):
            raise DomainError('invalid_input', 'Area ID must be text.')
        area = self.db.areas.find_one({'_id': area_id, 'enabled': True}, session=session)
        if area is None:
            raise DomainError('not_found', 'Enabled area not found.')
        return area

    def _run(self, run_id, session=None):
        if not isinstance(run_id, str):
            raise DomainError('invalid_input', 'Run ID must be text.')
        run = self.db.game_runs.find_one({'_id': run_id}, session=session)
        if run is None:
            raise DomainError('not_found', 'Game run not found.')
        return run

    @staticmethod
    def _idle(document):
        if document.get('active_run_id') is not None:
            raise DomainError('busy', 'An active progression game must finish or be cancelled first.')

    def _captain(self, actor_id, team, session):
        self._player(actor_id, session)
        if team['captain_id'] != actor_id:
            raise DomainError('forbidden', 'Only the team captain can do this.')

    def _admin(self, actor_id, session):
        actor = self._account(actor_id, session)
        if actor['role'] != 'admin':
            raise DomainError('forbidden', 'Administrator access is required.')
        # Serialize privileged changes through the actor account, including
        # simultaneous attempts by two administrators to suspend each other.
        self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
        return actor

    def _audit(self, actor_id, action, target_id, reason, before, after, session):
        self.db.admin_audit.insert_one({'_id': _id(), 'actor_id': actor_id, 'action': action,
            'target_id': target_id, 'reason': reason, 'before': before, 'after': after,
            'created_at': _now()}, session=session)

    def register(self, username, password_hash, starter_id='spearman'):
        username, key = validate_username(username)
        if not isinstance(password_hash, str) or not password_hash.startswith('$argon2id$') or len(password_hash) > 512:
            raise DomainError('invalid_input', 'An Argon2id password hash is required.')
        if not isinstance(starter_id, str) or starter_id not in STARTERS:
            raise DomainError('invalid_input', 'Choose an approved starter leader.')
        account = {'_id': _id(), 'username': username, 'username_key': key,
            'password_hash': password_hash, 'role': 'player', 'status': 'active',
            'leader': new_leader(starter_id), 'campaign_completed': [],
            'active_run_id': None, 'revision': 0, 'created_at': _now()}
        def write(session):
            self.db.accounts.insert_one(account, session=session)
            return public_account(account)
        return self._tx(write)

    def bootstrap_admin(self, username, password_hash):
        """Create the first administrator once; called only by the local setup CLI."""
        username, key = validate_username(username)
        if not isinstance(password_hash, str) or not password_hash.startswith('$argon2id$') or len(password_hash) > 512:
            raise DomainError('invalid_input', 'An Argon2id password hash is required.')
        account = {'_id': _id(), 'username': username, 'username_key': key,
            'password_hash': password_hash, 'role': 'admin', 'status': 'active',
            'leader': new_leader('spearman'), 'campaign_completed': [],
            'active_run_id': None, 'revision': 0, 'created_at': _now()}
        def write(session):
            if self.db.accounts.find_one({'role': 'admin'}, session=session):
                raise DomainError('already_initialized', 'An administrator already exists.')
            self.db.schema_metadata.insert_one({'_id': 'admin-bootstrap', 'version': 1}, session=session)
            self.db.accounts.insert_one(account, session=session)
            self._audit(account['_id'], 'bootstrap_admin', account['_id'], 'First administrator setup',
                        None, {'username': username, 'role': 'admin'}, session)
            return public_account(account)
        return self._tx(write)

    def get_account(self, account_id):
        return public_account(self._account(account_id, active=False))

    def list_areas(self):
        return list(self.db.areas.find({'enabled': True}).sort('name_key', 1))

    def list_teams(self, area_id='area-1'):
        self._area(area_id)
        return list(self.db.teams.find({'area_id': area_id, 'status': 'active'},
                                      {'join_requests': 0}).sort([('rating', -1), ('name_key', 1)]).limit(500))

    def _directory_player(self, actor_id):
        account = self._account(actor_id)
        if account['role'] != 'player':
            raise DomainError('forbidden', 'Player access is required.')

    def directory_areas(self, actor_id, after=''):
        """Twenty public area names per request; no full-area or unbounded response."""
        self._directory_player(actor_id)
        _directory_id(after, empty=True)
        query = {'enabled': True}
        if after:
            query['_id'] = {'$gt': after}
        records = list(self.db.areas.find(query, {'_id': 1, 'name': 1}).sort('_id', 1).limit(21))
        return {'areas': [{'id': item['_id'], 'name': item['name']} for item in records[:20]],
                'next': records[19]['_id'] if len(records) > 20 else ''}

    def directory_teams(self, actor_id, area_id, after=''):
        self._directory_player(actor_id)
        _directory_id(area_id)
        _directory_id(after, empty=True, uuid=True)
        self._area(area_id)
        query = {'area_id': area_id, 'status': 'active'}
        if after:
            query['_id'] = {'$gt': after}
        projection = {name: 1 for name in ('_id', 'name', 'area_id', 'captain_id',
                                         'level', 'experience', 'rating', 'members.account_id')}
        records = list(self.db.teams.find(query, projection).sort('_id', 1).limit(21))
        return {'teams': [dict(id=item['_id'], name=item['name'], area_id=item['area_id'],
                              captain_id=item['captain_id'], level=item['level'],
                              experience=item['experience'], rating=item['rating'],
                              member_count=len(item['members'])) for item in records[:20]],
                'next': records[19]['_id'] if len(records) > 20 else ''}

    def _directory_team_record(self, team):
        """Explicit display fields only: never include pending applicants or account hashes."""
        area = self.db.areas.find_one({'_id': team['area_id']}, {'name': 1})
        if area is None:
            raise DomainError('not_found', 'The team area is unavailable.')
        ids = [member['account_id'] for member in team['members']]
        accounts = {item['_id']: item for item in self.db.accounts.find({'_id': {'$in': ids}},
                    {'_id': 1, 'username': 1, 'leader.unit_type': 1, 'leader.level': 1})}
        if any(member_id not in accounts for member_id in ids):
            raise DomainError('not_found', 'The team roster is unavailable.')
        return dict(id=team['_id'], name=team['name'], area_id=team['area_id'],
                    area_name=area['name'], captain_id=team['captain_id'], level=team['level'],
                    experience=team['experience'], rating=team['rating'], capacity=TEAM_CAPACITY,
                    members=[dict(id=member_id, username=accounts[member_id]['username'],
                                  unit_type=accounts[member_id]['leader']['unit_type'],
                                  level=accounts[member_id]['leader']['level']) for member_id in ids])

    def directory_team(self, actor_id, team_id):
        self._directory_player(actor_id)
        _directory_id(team_id, uuid=True)
        return self._directory_team_record(self._team(team_id))

    def directory_my_team(self, actor_id):
        self._directory_player(actor_id)
        team = self.db.teams.find_one({'members.account_id': actor_id, 'status': 'active'})
        return None if team is None else self._directory_team_record(team)

    def directory_create_team(self, actor_id, name, area_id):
        _directory_id(area_id)
        team = self.create_team(actor_id, name, area_id)
        return self.directory_team(actor_id, team['_id'])

    def get_team(self, actor_id, team_id):
        """Public roster and leader previews; application IDs only for its captain."""
        self._account(actor_id)
        team = self._team(team_id)
        requests = team.pop('join_requests')
        for member in team['members']:
            account = self._account(member['account_id'], active=False)
            member['username'] = account['username']
            member['leader'] = account['leader']
        if team['captain_id'] == actor_id:
            team['join_requests'] = requests
            team['applicants'] = [{'_id': a['_id'], 'username': a['username'], 'leader': a['leader']}
                for a in self.db.accounts.find({'_id': {'$in': requests}},
                    {'_id': 1, 'username': 1, 'leader': 1})]
        return team

    def get_run(self, run_id):
        return self._run(run_id)

    def get_settlement(self, run_id):
        self._run(run_id)
        return self.db.settlements.find_one({'_id': run_id})

    def list_runs(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError('invalid_input', 'Run limit must be between 1 and 100.')
        return list(self.db.game_runs.find({}).sort('created_at', -1).limit(limit))

    def create_team(self, actor_id, name, area_id='area-1'):
        name, name_key = _name(name, 'Team name')
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            self._area(area_id, session)
            if self.db.teams.find_one({'members.account_id': actor_id}, session=session):
                raise DomainError('already_member', 'Leave the existing team before creating another.')
            team = {'_id': _id(), 'name': name, 'name_key': name_key, 'area_id': area_id,
                'captain_id': actor_id, 'members': [{'account_id': actor_id, 'joined_at': _now()}],
                'join_requests': [], 'experience': 0, 'level': 1, 'rating': 1000,
                'active_run_id': None, 'status': 'active', 'revision': 0, 'created_at': _now()}
            self.db.teams.insert_one(team, session=session)
            # Conflict with a simultaneous campaign start or suspension.
            self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
            return team
        return self._tx(write)

    def request_join(self, actor_id, team_id):
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            team = self._team(team_id, session)
            self._idle(team)
            if self.db.teams.find_one({'members.account_id': actor_id}, session=session):
                raise DomainError('already_member', 'This account already belongs to a team.')
            if actor_id in team['join_requests']:
                return {'team_id': team_id, 'requested': True}
            if len(team['members']) >= TEAM_CAPACITY or len(team['join_requests']) >= MAX_JOIN_REQUESTS:
                raise DomainError('capacity', 'The team or its application list is full.')
            self.db.teams.update_one({'_id': team_id}, {'$addToSet': {'join_requests': actor_id},
                '$inc': {'revision': 1}}, session=session)
            self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
            return {'team_id': team_id, 'requested': True}
        return self._tx(write)

    def approve_member(self, captain_id, team_id, account_id):
        def write(session):
            team = self._team(team_id, session)
            self._captain(captain_id, team, session)
            self._idle(team)
            account = self._player(account_id, session)
            self._idle(account)
            if account_id not in team['join_requests']:
                raise DomainError('not_requested', 'The player must request to join first.')
            if len(team['members']) >= TEAM_CAPACITY:
                raise DomainError('capacity', 'A team can contain at most eight members.')
            if self.db.teams.find_one({'members.account_id': account_id}, session=session):
                raise DomainError('already_member', 'This account already belongs to a team.')
            self.db.teams.update_one({'_id': team_id}, {
                '$push': {'members': {'account_id': account_id, 'joined_at': _now()}},
                '$pull': {'join_requests': account_id}, '$inc': {'revision': 1}}, session=session)
            self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
            return self._team(team_id, session)
        return self._tx(write)

    def reject_member(self, captain_id, team_id, account_id):
        """Decline a pending application; this never removes an existing member."""
        if not isinstance(account_id, str):
            raise DomainError('invalid_input', 'Account ID must be text.')
        def write(session):
            team = self._team(team_id, session)
            self._captain(captain_id, team, session)
            self._idle(team)
            self.db.teams.update_one({'_id': team_id}, {'$pull': {'join_requests': account_id},
                                                     '$inc': {'revision': 1}}, session=session)
            return {'team_id': team_id, 'account_id': account_id, 'requested': False}
        return self._tx(write)

    def withdraw_join(self, actor_id, team_id):
        def write(session):
            self._player(actor_id, session)
            self._team(team_id, session)
            self.db.teams.update_one({'_id': team_id}, {'$pull': {'join_requests': actor_id},
                                                     '$inc': {'revision': 1}}, session=session)
            return {'team_id': team_id, 'requested': False}
        return self._tx(write)

    def leave_team(self, actor_id):
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            team = self.db.teams.find_one({'members.account_id': actor_id, 'status': 'active'}, session=session)
            if team is None:
                raise DomainError('not_found', 'This account has no team.')
            self._idle(team)
            if team['captain_id'] == actor_id and len(team['members']) > 1:
                raise DomainError('captain_transfer_required', 'Transfer captaincy before leaving the team.')
            update = {'$pull': {'members': {'account_id': actor_id}}, '$inc': {'revision': 1}}
            if len(team['members']) == 1:
                update['$set'] = {'status': 'archived', 'captain_id': None, 'join_requests': []}
            self.db.teams.update_one({'_id': team['_id']}, update, session=session)
            self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
            return {'team_id': team['_id'], 'left': True}
        return self._tx(write)

    def transfer_captain(self, actor_id, team_id, new_captain_id):
        def write(session):
            team = self._team(team_id, session)
            self._captain(actor_id, team, session)
            self._idle(team)
            self._player(new_captain_id, session)
            if new_captain_id not in [m['account_id'] for m in team['members']]:
                raise DomainError('not_member', 'The new captain must belong to this team.')
            self.db.teams.update_one({'_id': team_id}, {'$set': {'captain_id': new_captain_id},
                                                     '$inc': {'revision': 1}}, session=session)
            return self._team(team_id, session)
        return self._tx(write)

    def choose_advancement(self, actor_id, unit_type):
        if not isinstance(unit_type, str):
            raise DomainError('invalid_input', 'Unit type must be text.')
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            try:
                leader = advance_leader(actor['leader'], unit_type)
            except ValueError as error:
                raise DomainError('invalid_advancement', str(error)) from error
            self.db.accounts.update_one({'_id': actor_id}, {'$set': {'leader': leader},
                                                         '$inc': {'revision': 1}}, session=session)
            return public_account(self._account(actor_id, session))
        return self._tx(write)

    def _reserve_account(self, account_id, run_id, session):
        account = self._player(account_id, session)
        self._idle(account)
        if account['leader']['advancement_choices']:
            raise DomainError('advancement_required', 'Choose the pending leader advancement before starting.')
        self.db.accounts.update_one({'_id': account_id}, {'$set': {'active_run_id': run_id},
                                                        '$inc': {'revision': 1}}, session=session)
        return account

    def start_campaign(self, actor_id, mission_id):
        if not isinstance(mission_id, str) or mission_id not in MISSIONS:
            raise DomainError('invalid_mission', 'This campaign mission is not approved.')
        def write(session):
            actor = self._account(actor_id, session)
            position = MISSIONS.index(mission_id)
            if any(previous not in actor['campaign_completed'] for previous in MISSIONS[:position]):
                raise DomainError('mission_locked', 'Finish the previous campaign mission first.')
            run_id = _id()
            account = self._reserve_account(actor_id, run_id, session)
            run = {'_id': run_id, 'kind': 'campaign', 'state': 'running',
                'ruleset_version': RULESET_VERSION, 'mission_id': mission_id,
                'participants': [{'account_id': actor_id, 'leader': account['leader']}],
                'created_at': _now(), 'started_at': _now()}
            self.db.game_runs.insert_one(run, session=session)
            return run
        return self._tx(write)

    def create_battle(self, actor_id, opponent_team_id, map_id, lineups):
        if not isinstance(map_id, str) or map_id not in MAPS:
            raise DomainError('invalid_map', 'Choose an approved team map.')
        if not isinstance(lineups, dict) or len(lineups) != 2:
            raise DomainError('invalid_lineup', 'A battle needs exactly two fixed lineups.')
        for ids in lineups.values():
            if not isinstance(ids, list) or len(ids) != MAPS[map_id]['size'] or any(not isinstance(i, str) for i in ids):
                raise DomainError('invalid_lineup', 'The lineup size must match the map.')
            if len(ids) != len(set(ids)):
                raise DomainError('invalid_lineup', 'Each player can occupy only one slot.')
        def write(session):
            self._player(actor_id, session)
            first = self.db.teams.find_one({'captain_id': actor_id, 'status': 'active'}, session=session)
            if first is None:
                raise DomainError('forbidden', 'Only a team captain can propose a battle.')
            second = self._team(opponent_team_id, session)
            if first['_id'] == second['_id'] or set(lineups) != {first['_id'], second['_id']}:
                raise DomainError('invalid_lineup', 'Choose two different teams and their matching lineups.')
            teams = [first, second]
            self._validate_battle_teams(teams, map_id, lineups, session)
            participants = self._participants(teams, map_id, lineups)
            for participant in participants:
                participant['leader'] = self._account(participant['account_id'], session)['leader']
            run = {'_id': _id(), 'kind': 'alliance', 'state': 'draft',
                'ruleset_version': RULESET_VERSION, 'map_id': map_id, 'area_id': first['area_id'],
                'team_ids': [t['_id'] for t in teams], 'lineups': deepcopy(lineups),
                'approvals': {first['_id']: actor_id}, 'ready': [], 'participants': participants,
                'created_at': _now()}
            self.db.game_runs.insert_one(run, session=session)
            return run
        return self._tx(write)

    @staticmethod
    def _participants(teams, map_id, lineups):
        return [{'account_id': player, 'team_id': team['_id'], 'side': side}
                for team, sides in zip(teams, MAPS[map_id]['sides'])
                for player, side in zip(lineups[team['_id']], sides)]

    def _validate_battle_teams(self, teams, map_id, lineups, session):
        if teams[0]['area_id'] != teams[1]['area_id']:
            raise DomainError('different_area', 'Both teams must belong to the same area.')
        area = self._area(teams[0]['area_id'], session)
        if map_id not in area['approved_maps']:
            raise DomainError('invalid_map', 'This map is not enabled in the area.')
        all_players = []
        for team in teams:
            self._player(team['captain_id'], session)
            self._idle(team)
            members = {m['account_id'] for m in team['members']}
            if any(p not in members for p in lineups[team['_id']]):
                raise DomainError('not_member', 'Every selected player must belong to that team.')
            for player in lineups[team['_id']]:
                self._player(player, session)
                all_players.append(player)
        if len(all_players) != len(set(all_players)):
            raise DomainError('invalid_lineup', 'A player cannot fight on both teams.')

    def approve_battle(self, actor_id, run_id):
        def write(session):
            run = self._run(run_id, session)
            self._draft(run)
            teams = [self._team(t, session) for t in run['team_ids']]
            team = next((t for t in teams if t['captain_id'] == actor_id), None)
            if team is None:
                raise DomainError('forbidden', 'Only a participating team captain can approve.')
            self._captain(actor_id, team, session)
            self._validate_battle_teams(teams, run['map_id'], run['lineups'], session)
            self._check_preview(run, session)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {
                'approvals.' + team['_id']: actor_id}}, session=session)
            return self._run(run_id, session)
        return self._tx(write)

    def _check_preview(self, run, session):
        self._require_ruleset(run)
        for participant in run['participants']:
            current = self._account(participant['account_id'], session)
            if participant.get('leader') != current['leader']:
                raise DomainError('stale_proposal', 'A leader changed after this proposal. Create a new proposal.')

    @staticmethod
    def _require_ruleset(run):
        if run['ruleset_version'] != RULESET_VERSION:
            raise DomainError('unsupported_ruleset', 'This run requires its original versioned settlement rules.')

    @staticmethod
    def _draft(run):
        if run['kind'] != 'alliance' or run['state'] != 'draft':
            raise DomainError('invalid_state', 'Only a draft alliance battle can be prepared.')

    def set_ready(self, actor_id, run_id, ready=True):
        if type(ready) is not bool:
            raise DomainError('invalid_input', 'Readiness must be a boolean.')
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            self._draft(run)
            if actor_id not in [p['account_id'] for p in run['participants']]:
                raise DomainError('forbidden', 'Only a selected player can set readiness.')
            self.db.game_runs.update_one({'_id': run_id}, {
                '$addToSet' if ready else '$pull': {'ready': actor_id}}, session=session)
            return self._run(run_id, session)
        return self._tx(write)

    def start_battle(self, actor_id, run_id):
        def write(session):
            run = self._run(run_id, session)
            self._draft(run)
            teams = [self._team(t, session) for t in run['team_ids']]
            if actor_id not in [t['captain_id'] for t in teams]:
                raise DomainError('forbidden', 'A participating captain must start the battle.')
            self._player(actor_id, session)
            self._validate_battle_teams(teams, run['map_id'], run['lineups'], session)
            self._check_preview(run, session)
            if teams[0]['area_id'] != run['area_id']:
                raise DomainError('area_changed', 'The team area changed; create a new proposal.')
            if any(run['approvals'].get(t['_id']) != t['captain_id'] for t in teams):
                raise DomainError('approval_required', 'Both current captains must approve the map and lineups.')
            if set(run['ready']) != {p['account_id'] for p in run['participants']}:
                raise DomainError('not_ready', 'Every selected player must be ready.')
            participants = self._participants(teams, run['map_id'], run['lineups'])
            for participant in participants:
                account = self._reserve_account(participant['account_id'], run_id, session)
                participant['leader'] = account['leader']
            for team in teams:
                self.db.teams.update_one({'_id': team['_id']}, {'$set': {'active_run_id': run_id},
                                                              '$inc': {'revision': 1}}, session=session)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {
                'state': 'running', 'participants': participants, 'started_at': _now()}}, session=session)
            return self._run(run_id, session)
        return self._tx(write)

    def _existing_settlement(self, run_id, result, session):
        if not isinstance(run_id, str):
            raise DomainError('invalid_input', 'Run ID must be text.')
        receipt = self.db.settlements.find_one({'_id': run_id}, session=session)
        if receipt is not None and receipt['result'] != result:
            raise DomainError('result_conflict', 'This run already has a different final result.')
        return receipt

    def _reward_player(self, participant, run, amount, session, mission_complete=False):
        account = self._account(participant['account_id'], session, active=False)
        if account['active_run_id'] != run['_id']:
            raise DomainError('reservation_conflict', 'The player reservation does not match the run.')
        if account['leader'] != participant['leader']:
            raise DomainError('snapshot_conflict', 'The persistent leader changed during the run.')
        leader = award_experience(account['leader'], amount)
        update = {'$set': {'leader': leader, 'active_run_id': None}, '$inc': {'revision': 1}}
        if mission_complete:
            update['$addToSet'] = {'campaign_completed': run['mission_id']}
        self.db.accounts.update_one({'_id': account['_id']}, update, session=session)
        return {'account_id': account['_id'], 'experience': amount, 'leader': leader,
                'revision': account['revision'] + 1}

    def finish_campaign(self, run_id, outcome):
        """Trusted bridge only. Defeat gives no XP; a completed replay may earn XP."""
        if outcome not in ('win', 'loss'):
            raise DomainError('invalid_result', 'Campaign outcome must be win or loss.')
        result = {'kind': 'campaign', 'outcome': outcome}
        def write(session):
            previous = self._existing_settlement(run_id, result, session)
            if previous is not None:
                return previous
            run = self._run(run_id, session)
            self._require_ruleset(run)
            if run['kind'] != 'campaign' or run['state'] != 'running':
                raise DomainError('invalid_state', 'Only a running campaign can finish.')
            reward = self._reward_player(run['participants'][0], run, 20 if outcome == 'win' else 0,
                                         session, mission_complete=outcome == 'win')
            return self._record_settlement(run, result, {'players': [reward], 'teams': []}, session)
        return self._tx(write)

    def finish_battle(self, run_id, winner_team_id=None, draw=False):
        """Trusted bridge only; it must establish victory/surrender or mutual draw."""
        if type(draw) is not bool or (draw and winner_team_id is not None) or (not draw and not isinstance(winner_team_id, str)):
            raise DomainError('invalid_result', 'Provide one winning team or an agreed draw.')
        result = {'kind': 'alliance', 'winner_team_id': winner_team_id, 'draw': draw}
        def write(session):
            previous = self._existing_settlement(run_id, result, session)
            if previous is not None:
                return previous
            run = self._run(run_id, session)
            self._require_ruleset(run)
            if run['kind'] != 'alliance' or run['state'] != 'running':
                raise DomainError('invalid_state', 'Only a running alliance battle can finish.')
            if not draw and winner_team_id not in run['team_ids']:
                raise DomainError('invalid_result', 'The winner must be a participating team.')
            teams = [self._team(t, session) for t in run['team_ids']]
            if any(t['active_run_id'] != run_id for t in teams):
                raise DomainError('reservation_conflict', 'A team reservation does not match the run.')
            outcomes = {t['_id']: 'draw' if draw else ('win' if t['_id'] == winner_team_id else 'loss') for t in teams}
            player_rewards = [self._reward_player(p, run, LEADER_REWARDS[outcomes[p['team_id']]], session)
                              for p in run['participants']]
            delta = rating_delta(teams[0]['rating'], teams[1]['rating'],
                                 0.5 if draw else (1 if teams[0]['_id'] == winner_team_id else 0))
            team_rewards = []
            for team, change in zip(teams, (delta, -delta)):
                amount = TEAM_REWARDS[outcomes[team['_id']]]
                xp = team['experience'] + amount
                rating = team['rating'] + change
                self.db.teams.update_one({'_id': team['_id']}, {'$set': {'experience': xp,
                    'level': team_level(xp), 'rating': rating, 'active_run_id': None},
                    '$inc': {'revision': 1}}, session=session)
                team_rewards.append({'team_id': team['_id'], 'experience': amount, 'total_experience': xp,
                    'level': team_level(xp), 'rating': rating, 'rating_delta': change, 'revision': team['revision'] + 1})
            return self._record_settlement(run, result, {'players': player_rewards, 'teams': team_rewards}, session)
        return self._tx(write)

    def _record_settlement(self, run, result, rewards, session):
        receipt = {'_id': run['_id'], 'ruleset_version': run['ruleset_version'], 'result': result,
                   'rewards': rewards, 'created_at': _now()}
        self.db.settlements.insert_one(receipt, session=session)
        self.db.game_runs.update_one({'_id': run['_id']}, {'$set': {
            'state': 'completed', 'result': result, 'finished_at': _now()}}, session=session)
        return self.db.settlements.find_one({'_id': run['_id']}, session=session)

    def _cancel(self, run_id, reason, session):
        run = self._run(run_id, session)
        if run['state'] == 'completed':
            raise DomainError('invalid_state', 'A settled run cannot be cancelled.')
        if run['state'] == 'cancelled':
            return run
        if run['state'] == 'running':
            for participant in run['participants']:
                result = self.db.accounts.update_one({'_id': participant['account_id'], 'active_run_id': run_id},
                    {'$set': {'active_run_id': None}, '$inc': {'revision': 1}}, session=session)
                if result.matched_count != 1:
                    raise DomainError('reservation_conflict', 'A player reservation is missing.')
            for team_id in run.get('team_ids', []):
                result = self.db.teams.update_one({'_id': team_id, 'active_run_id': run_id},
                    {'$set': {'active_run_id': None}, '$inc': {'revision': 1}}, session=session)
                if result.matched_count != 1:
                    raise DomainError('reservation_conflict', 'A team reservation is missing.')
        self.db.game_runs.update_one({'_id': run_id}, {'$set': {
            'state': 'cancelled', 'cancel_reason': reason, 'finished_at': _now()}}, session=session)
        return self._run(run_id, session)

    def cancel_run(self, run_id, reason):
        """Trusted bridge recovery only. Cancellation never awards experience."""
        reason = _reason(reason)
        return self._tx(lambda session: self._cancel(run_id, reason, session))

    def admin_create_area(self, actor_id, name):
        name, key = _name(name, 'Area name')
        def write(session):
            self._admin(actor_id, session)
            area = {'_id': _id(), 'name': name, 'name_key': key, 'enabled': True,
                    'approved_maps': list(MAPS), 'created_at': _now()}
            self.db.areas.insert_one(area, session=session)
            self._audit(actor_id, 'create_area', area['_id'], 'Create an area', None,
                        {'name': name}, session)
            return area
        return self._tx(write)

    def admin_move_team(self, actor_id, team_id, area_id, reason):
        reason = _reason(reason)
        def write(session):
            self._admin(actor_id, session)
            team = self._team(team_id, session)
            self._idle(team)
            self._area(area_id, session)
            self.db.teams.update_one({'_id': team_id}, {'$set': {'area_id': area_id},
                                                     '$inc': {'revision': 1}}, session=session)
            self._audit(actor_id, 'move_team', team_id, reason, {'area_id': team['area_id']},
                        {'area_id': area_id}, session)
            return self._team(team_id, session)
        return self._tx(write)

    def admin_set_account_status(self, actor_id, account_id, status, reason):
        reason = _reason(reason)
        if status not in ('active', 'suspended'):
            raise DomainError('invalid_input', 'Account status must be active or suspended.')
        def write(session):
            self._admin(actor_id, session)
            account = self._account(account_id, session, active=False)
            self._idle(account)
            if actor_id == account_id and status == 'suspended':
                raise DomainError('forbidden', 'An administrator cannot suspend their own account.')
            if account['role'] == 'admin' and status == 'suspended':
                if self.db.accounts.count_documents({'role': 'admin', 'status': 'active'}, session=session) <= 1:
                    raise DomainError('last_admin', 'The last active administrator cannot be suspended.')
            self.db.accounts.update_one({'_id': account_id}, {'$set': {'status': status},
                                                        '$inc': {'revision': 1}}, session=session)
            if status == 'suspended':
                self.db.auth_sessions.delete_many({'account_id': account_id}, session=session)
            self._audit(actor_id, 'set_account_status', account_id, reason,
                        {'status': account['status']}, {'status': status}, session)
            return public_account(self._account(account_id, session, active=False))
        return self._tx(write)

    def admin_cancel_run(self, actor_id, run_id, reason):
        reason = _reason(reason)
        def write(session):
            self._admin(actor_id, session)
            before = self._run(run_id, session)
            result = self._cancel(run_id, reason, session)
            if before['state'] != 'cancelled':
                self._audit(actor_id, 'cancel_run', run_id, reason, {'state': before['state']},
                            {'state': 'cancelled'}, session)
            return result
        return self._tx(write)
