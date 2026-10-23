"""Transactional Alliance persistence and rules, independent of HTTP or WML.

The bridge is trusted to identify a finished game. This service validates roster,
state and fixed rewards, but does not simulate or independently verify combat.
Every mutation runs in a replica-set transaction; clients never submit XP/stats.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from uuid import uuid4

from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .rules import (STARTERS, MAPS, MISSIONS, MISSION_VERSION, MISSION_NAMES, UNIT_TYPES,
                    RULESET_VERSION, TEAM_CAPACITY, MAX_JOIN_REQUESTS,
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
    # Decision history has its own owner-only, bounded response contract.
    result.pop('application_decisions', None)
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
        if session is not None:
            # Serialize game/team mutations against disabling an area or
            # changing its approved maps in an administrator transaction.
            self.db.areas.update_one({'_id': area_id}, {'$inc': {'revision': 1}}, session=session)
            area['revision'] = area.get('revision', 0) + 1
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
        actor = self._player(actor_id, session)
        if team['captain_id'] != actor_id:
            raise DomainError('forbidden', 'Only the team captain can do this.')
        return actor

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
        return account

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
        return self._directory_team_page(query, after)

    def directory_standings(self, actor_id, area_id):
        """A fixed top twenty, with stable UUID ordering for equal ratings."""
        self._directory_player(actor_id)
        _directory_id(area_id)
        self._area(area_id)
        projection = {name: 1 for name in ('_id', 'name', 'area_id', 'captain_id',
                                         'level', 'experience', 'rating', 'members.account_id')}
        records = list(self.db.teams.find({'area_id': area_id, 'status': 'active'}, projection)
                       .sort([('rating', -1), ('_id', 1)]).limit(21))
        return {'area_id': area_id, 'teams': [self._directory_summary(item) for item in records[:20]],
                'has_more': len(records) > 20}

    @staticmethod
    def _directory_summary(item):
        return dict(id=item['_id'], name=item['name'], area_id=item['area_id'],
                    captain_id=item['captain_id'], level=item['level'],
                    experience=item['experience'], rating=item['rating'],
                    member_count=len(item['members']))

    def _directory_team_page(self, query, after):
        if after:
            query['_id'] = {'$gt': after}
        projection = {name: 1 for name in ('_id', 'name', 'area_id', 'captain_id',
                                         'level', 'experience', 'rating', 'members.account_id')}
        records = list(self.db.teams.find(query, projection).sort('_id', 1).limit(21))
        return {'teams': [self._directory_summary(item) for item in records[:20]],
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

    def directory_my_applications(self, actor_id, after=''):
        self._directory_player(actor_id)
        _directory_id(after, empty=True, uuid=True)
        # Keep other pending requests visible after joining a team, so the
        # player can withdraw them without losing their application history.
        return self._directory_team_page({'join_requests': actor_id, 'status': 'active'}, after)

    def directory_team_applicants(self, actor_id, team_id, after=''):
        self._directory_player(actor_id)
        _directory_id(team_id, uuid=True)
        _directory_id(after, empty=True, uuid=True)
        team = self._team(team_id)
        if team['captain_id'] != actor_id:
            raise DomainError('forbidden', 'Only the team captain can view applications.')
        query = {'_id': {'$in': team['join_requests']}}
        if after:
            query['_id']['$gt'] = after
        records = list(self.db.accounts.find(query, {'_id': 1, 'username': 1,
            'leader.unit_type': 1, 'leader.level': 1}).sort('_id', 1).limit(21))
        return {'team_id': team_id,
                'applicants': [dict(id=item['_id'], username=item['username'],
                    unit_type=item['leader']['unit_type'], level=item['leader']['level'])
                    for item in records[:20]],
                'next': records[19]['_id'] if len(records) > 20 else ''}

    def directory_apply_team(self, actor_id, team_id):
        _directory_id(team_id, uuid=True)
        self.request_join(actor_id, team_id)
        return {'team_id': team_id, 'account_id': actor_id, 'status': 'applied'}

    def directory_withdraw_application(self, actor_id, team_id):
        _directory_id(team_id, uuid=True)
        self.withdraw_join(actor_id, team_id)
        return {'team_id': team_id, 'account_id': actor_id, 'status': 'withdrawn'}

    def directory_approve_application(self, actor_id, team_id, account_id):
        _directory_id(team_id, uuid=True)
        _directory_id(account_id, uuid=True)
        self.approve_member(actor_id, team_id, account_id)
        return {'team_id': team_id, 'account_id': account_id, 'status': 'approved'}

    def directory_reject_application(self, actor_id, team_id, account_id):
        _directory_id(team_id, uuid=True)
        _directory_id(account_id, uuid=True)
        self.reject_member(actor_id, team_id, account_id)
        return {'team_id': team_id, 'account_id': account_id, 'status': 'rejected'}

    def directory_leave_team(self, actor_id, team_id, allow_archive):
        _directory_id(team_id, uuid=True)
        if type(allow_archive) is not bool:
            raise DomainError('invalid_input', 'Archive consent must be a boolean.')
        return self._leave_team(actor_id, expected_team_id=team_id, allow_archive=allow_archive)

    def directory_transfer_captain(self, actor_id, team_id, account_id):
        _directory_id(team_id, uuid=True)
        _directory_id(account_id, uuid=True)
        try:
            self.transfer_captain(actor_id, team_id, account_id)
        except DomainError as error:
            if error.code == 'suspended':
                raise DomainError('forbidden', 'Captaincy cannot be transferred to that player.') from error
            raise
        return {'team_id': team_id, 'account_id': account_id, 'status': 'transferred'}

    @staticmethod
    def _planning_map(map_id):
        value = MAPS[map_id]
        return {'id': map_id, 'name': value['name'], 'scenario_id': value['scenario_id'],
                'size': value['size'], 'sides': [list(sides) for sides in value['sides']]}

    def directory_battle_maps(self, actor_id, area_id):
        self._directory_player(actor_id)
        _directory_id(area_id)
        area = self._area(area_id)
        return {'area_id': area_id, 'maps': [self._planning_map(key) for key in MAPS
                                           if key in area['approved_maps']]}

    def _planning_access(self, actor_id, run, session=None):
        if run['kind'] != 'alliance':
            raise DomainError('not_found', 'Battle plan not found.')
        team = self.db.teams.find_one({'_id': {'$in': run['team_ids']}, 'status': 'active',
                                       'members.account_id': actor_id}, session=session)
        if team is None:
            raise DomainError('forbidden', 'Only current members of the participating teams may view this plan.')
        return team

    def _planning_context(self, run, session=None):
        teams = [self.db.teams.find_one({'_id': team_id}, session=session) for team_id in run['team_ids']]
        ids = {player['account_id'] for player in run['participants']}
        ids.update(team['captain_id'] for team in teams if team and team['captain_id'])
        accounts = {item['_id']: item for item in self.db.accounts.find({'_id': {'$in': list(ids)}},
                    {'username': 1, 'leader': 1, 'role': 1, 'status': 1, 'active_run_id': 1}, session=session)}
        area = self.db.areas.find_one({'_id': run['area_id']}, session=session)
        return teams, accounts, area

    @staticmethod
    def _planning_validity(run, teams, accounts, area):
        if run['ruleset_version'] != RULESET_VERSION:
            return 'rules_changed'
        if any(team is None or team['status'] != 'active' for team in teams):
            return 'team_unavailable'
        if any(team['area_id'] != run['area_id'] for team in teams):
            return 'area_changed'
        if area is None or not area['enabled'] or run['map_id'] not in area['approved_maps']:
            return 'map_unavailable'
        if any(not set(run['lineups'][team['_id']]).issubset({m['account_id'] for m in team['members']})
               for team in teams):
            return 'roster_changed'
        ids = {player['account_id'] for player in run['participants']} | {team['captain_id'] for team in teams}
        if any(key not in accounts or accounts[key]['status'] != 'active' or accounts[key]['role'] != 'player'
               for key in ids):
            return 'player_unavailable'
        if any(accounts[player['account_id']]['leader'] != player.get('leader') for player in run['participants']):
            return 'leader_changed'
        allowed_run = run['_id'] if run['state'] == 'running' else None
        # Captains outside the fixed lineup approve and review the battle but
        # do not occupy a gameplay seat. Their separate campaign must not block
        # an already running team's authenticated players from reconnecting.
        busy_ids = {player['account_id'] for player in run['participants']} if run['state'] == 'running' else ids
        if any(item.get('active_run_id') not in (None, allowed_run) for item in teams) or any(
                accounts[key].get('active_run_id') not in (None, allowed_run) for key in busy_ids):
            return 'busy'
        return 'valid'

    def _planning_names(self, run, session=None):
        # Native plans retain names even after the selected roster changes.
        # Legacy plans are readable using existing names, without a migration.
        if 'planning_teams' in run:
            return [dict(id=item['id'], name=item['name']) for item in run['planning_teams']]
        return [{'id': team_id, 'name': self.db.teams.find_one({'_id': team_id}, {'name': 1},
                                                            session=session)['name']}
                for team_id in run['team_ids']]

    def _planning_summary(self, run, session=None):
        return {'id': run['_id'], 'area_id': run['area_id'], 'map_id': run['map_id'], 'state': run['state'],
                'created_at': run['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'),
                'teams': self._planning_names(run, session)}

    def _planning_record(self, run, session=None):
        teams, accounts, area = self._planning_context(run, session)
        result = self._planning_summary(run, session)
        result.pop('map_id')
        result['map'] = self._planning_map(run['map_id'])
        result['validity'] = self._planning_validity(run, teams, accounts, area)
        for display, current in zip(result['teams'], teams):
            historical = run['state'] == 'completed' and run.get('shared_room', {}).get('state') == 'completed'
            captain_id = (run['shared_room']['captains'].get(display['id'], '') if historical else
                          current['captain_id'] if current and current['status'] == 'active' else '')
            display.update(captain_id=captain_id,
                           approved=bool(captain_id and run['approvals'].get(display['id']) == captain_id),
                           players=[{'id': player['account_id'],
                             'username': player.get('username') or accounts[player['account_id']]['username'],
                             'unit_type': player['leader']['unit_type'], 'level': player['leader']['level'],
                             'side': player['side'], 'ready': player['account_id'] in run['ready']}
                             for player in run['participants'] if player['team_id'] == display['id']])
        return result

    def directory_my_battles(self, actor_id, after=''):
        self._directory_player(actor_id)
        _directory_id(after, empty=True, uuid=True)
        team = self.db.teams.find_one({'members.account_id': actor_id, 'status': 'active'}, {'_id': 1})
        history = {'state': 'completed', 'shared_room.state': 'completed', '$or': [
            {'participants.account_id': actor_id}, {'$expr': {'$in': [actor_id, {'$map': {
                'input': {'$objectToArray': {'$ifNull': ['$shared_room.captains', {}]}},
                'as': 'captain', 'in': '$$captain.v'}}]}}]}
        branches = [history]
        if team:
            branches.append({'team_ids': team['_id'], '$or': [
                {'state': {'$ne': 'completed'}}, {'shared_room': {'$exists': False}}]})
        query = {'kind': 'alliance', '$or': branches}
        if after:
            query['_id'] = {'$gt': after}
        records = list(self.db.game_runs.find(query, {'_id': 1, 'area_id': 1, 'map_id': 1, 'state': 1,
            'created_at': 1, 'team_ids': 1, 'planning_teams': 1}).sort('_id', 1).limit(21))
        return {'battles': [self._planning_summary(item) for item in records[:20]],
                'next': records[19]['_id'] if len(records) > 20 else ''}

    def directory_battle_detail(self, actor_id, battle_id):
        self._directory_player(actor_id)
        _directory_id(battle_id, uuid=True)
        def read(session):
            run = self._run(battle_id, session)
            if run['kind'] == 'alliance' and run['state'] == 'completed' and run.get('shared_room', {}).get('state') == 'completed':
                permitted = {item['account_id'] for item in run['participants']} | set(run['shared_room']['captains'].values())
                if actor_id not in permitted:
                    raise DomainError('forbidden', 'Only the recorded players and captains may view this completed shared battle.')
            else:
                self._planning_access(actor_id, run, session)
            return self._planning_record(run, session)
        return self._tx(read)

    def directory_propose_battle(self, actor_id, team_id, opponent_team_id, map_id, lineups):
        _directory_id(team_id, uuid=True)
        _directory_id(opponent_team_id, uuid=True)
        if not isinstance(lineups, list) or len(lineups) != 2:
            raise DomainError('invalid_lineup', 'Choose exactly two fixed lineups.')
        selected = {}
        for item in lineups:
            if not isinstance(item, dict) or set(item) != {'team_id', 'account_ids'}:
                raise DomainError('invalid_lineup', 'The lineup fields are invalid.')
            key = _directory_id(item['team_id'], uuid=True)
            if key in selected or not isinstance(item['account_ids'], list) or not 2 <= len(item['account_ids']) <= 4:
                raise DomainError('invalid_lineup', 'The fixed lineups are invalid.')
            selected[key] = [_directory_id(account, uuid=True) for account in item['account_ids']]
        try:
            return self.create_battle(actor_id, opponent_team_id, map_id, selected,
                                      expected_team_id=team_id, native_plan=True)
        except DomainError as error:
            if error.code == 'suspended':
                raise DomainError('forbidden', 'One of the selected players is unavailable.') from error
            raise

    def _planning_validate_mutation(self, run, session):
        teams, accounts, area = self._planning_context(run, session)
        validity = self._planning_validity(run, teams, accounts, area)
        if validity != 'valid':
            raise DomainError('busy' if validity == 'busy' else 'stale_proposal',
                              'This plan is unavailable or changed. Inspect it before creating another plan.')
        if any(accounts[player['account_id']]['leader']['advancement_choices'] for player in run['participants']):
            raise DomainError('advancement_required', 'A selected player must choose their available leader advancement before preparing this battle.')
        # Serialize validation with membership, captaincy, progression and status
        # changes. No active-run reservation is made for a proposal.
        for team in teams:
            self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        for account_id in accounts:
            self._player(account_id, session)
        return teams

    def directory_approve_battle(self, actor_id, battle_id):
        _directory_id(battle_id, uuid=True)
        def write(session):
            self._player(actor_id, session)
            run = self._run(battle_id, session)
            own_team = self._planning_access(actor_id, run, session)
            if own_team['captain_id'] != actor_id:
                raise DomainError('forbidden', 'Only a participating current captain can approve this plan.')
            self._draft(run)
            self._planning_validate_mutation(run, session)
            self.db.game_runs.update_one({'_id': battle_id}, {'$set': {
                'approvals.' + own_team['_id']: actor_id}}, session=session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def directory_battle_ready(self, actor_id, battle_id, ready):
        _directory_id(battle_id, uuid=True)
        if type(ready) is not bool:
            raise DomainError('invalid_input', 'Readiness must be a boolean.')
        def write(session):
            self._player(actor_id, session)
            run = self._run(battle_id, session)
            self._planning_access(actor_id, run, session)
            self._draft(run)
            if actor_id not in [player['account_id'] for player in run['participants']]:
                raise DomainError('forbidden', 'Only a selected current member can change readiness.')
            if ready:
                self._planning_validate_mutation(run, session)
                teams, _, _ = self._planning_context(run, session)
                if any(run['approvals'].get(team['_id']) != team['captain_id'] for team in teams):
                    raise DomainError('approval_required', 'Both current captains must approve this plan first.')
            self.db.game_runs.update_one({'_id': battle_id}, {
                '$addToSet' if ready else '$pull': {'ready': actor_id}}, session=session)
            return self._planning_record(self._run(battle_id, session), session)
        return self._tx(write)

    def directory_cancel_battle(self, actor_id, battle_id):
        _directory_id(battle_id, uuid=True)
        def write(session):
            self._player(actor_id, session)
            run = self._run(battle_id, session)
            own_team = self._planning_access(actor_id, run, session)
            if own_team['captain_id'] != actor_id:
                raise DomainError('forbidden', 'Only a participating current captain can cancel this plan.')
            if run['state'] not in ('draft', 'cancelled'):
                raise DomainError('invalid_state', 'Only a planned battle can be cancelled here.')
            self.db.teams.update_one({'_id': own_team['_id']}, {'$inc': {'revision': 1}}, session=session)
            run = self._cancel(battle_id, 'Cancelled by a team captain before gameplay.', session)
            return self._planning_record(run, session)
        return self._tx(write)

    def directory_application_decisions(self, actor_id):
        account = self._directory_player(actor_id)
        # Older accounts have no history. Never infer decisions from missing
        # applications or synthesize notices for changes made before this feature.
        return {'decisions': [{key: notice[key] for key in
            ('id', 'team_id', 'team_name', 'status', 'created_at', 'unread')}
            for notice in account.get('application_decisions', [])[:50]]}

    def directory_ack_decision(self, actor_id, decision_id):
        _directory_id(decision_id, uuid=True)
        def write(session):
            self._player(actor_id, session)
            result = self.db.accounts.update_one(
                {'_id': actor_id, 'application_decisions.id': decision_id},
                {'$set': {'application_decisions.$.unread': False}}, session=session)
            if result.matched_count != 1:
                raise DomainError('not_found', 'This application decision is no longer available.')
            return {'decision_id': decision_id, 'status': 'read'}
        return self._tx(write)

    def _record_application_decision(self, account_id, team, status, session):
        notice = {'id': _id(), 'team_id': team['_id'], 'team_name': team['name'],
                  'status': status, 'created_at': _now().strftime('%Y-%m-%dT%H:%M:%SZ'), 'unread': True}
        result = self.db.accounts.update_one({'_id': account_id}, {
            '$push': {'application_decisions': {'$each': [notice], '$position': 0, '$slice': 50}},
            '$inc': {'revision': 1}}, session=session)
        if result.matched_count != 1:
            raise DomainError('not_found', 'The applicant account is unavailable.')

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
            # A new membership cannot reuse consent from an earlier membership,
            # including a departure made before draft consent was revoked here.
            self._revoke_draft_readiness(account_id, session)
            self._record_application_decision(account_id, team, 'approved', session)
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
            if account_id not in team['join_requests']:
                return {'team_id': team_id, 'account_id': account_id, 'requested': False}
            self.db.teams.update_one({'_id': team_id}, {'$pull': {'join_requests': account_id},
                                                     '$inc': {'revision': 1}}, session=session)
            self._record_application_decision(account_id, team, 'rejected', session)
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
        result = self._leave_team(actor_id)
        return {'team_id': result['team_id'], 'left': True}

    def _revoke_draft_readiness(self, account_id, session):
        # Consent belongs to the selected player's continuous membership, not
        # merely to the saved lineup. Keep cancelled/completed history intact.
        # The caller changes membership in this same transaction; competing
        # readiness/start/cancel writes must serialize against that change.
        self.db.game_runs.update_many({'kind': 'alliance', 'state': 'draft',
            'participants.account_id': account_id, 'ready': account_id},
            {'$pull': {'ready': account_id}}, session=session)

    def _leave_team(self, actor_id, expected_team_id=None, allow_archive=True):
        def write(session):
            actor = self._player(actor_id, session)
            self._idle(actor)
            team = self.db.teams.find_one({'members.account_id': actor_id, 'status': 'active'}, session=session)
            if team is None:
                raise DomainError('not_found', 'This account has no team.')
            # The comparison belongs inside the transaction, including retries:
            # a stale confirmation must never remove a newly joined membership.
            if expected_team_id is not None and team['_id'] != expected_team_id:
                raise DomainError('conflict', 'The current team differs from the selected team.')
            self._idle(team)
            if team['captain_id'] == actor_id and len(team['members']) > 1:
                raise DomainError('captain_transfer_required', 'Transfer captaincy before leaving the team.')
            if len(team['members']) == 1 and not allow_archive:
                raise DomainError('conflict', 'The last member must explicitly confirm archiving the team.')
            update = {'$pull': {'members': {'account_id': actor_id}}, '$inc': {'revision': 1}}
            if len(team['members']) == 1:
                update['$set'] = {'status': 'archived', 'captain_id': None, 'join_requests': []}
            self.db.teams.update_one({'_id': team['_id']}, update, session=session)
            self.db.accounts.update_one({'_id': actor_id}, {'$inc': {'revision': 1}}, session=session)
            self._revoke_draft_readiness(actor_id, session)
            return {'team_id': team['_id'], 'account_id': actor_id, 'status': 'left',
                    'archived': len(team['members']) == 1}
        return self._tx(write)

    def transfer_captain(self, actor_id, team_id, new_captain_id):
        def write(session):
            team = self._team(team_id, session)
            self._idle(self._captain(actor_id, team, session))
            self._idle(team)
            if new_captain_id == actor_id:
                raise DomainError('invalid_input', 'Select another member as captain.')
            if new_captain_id not in [m['account_id'] for m in team['members']]:
                raise DomainError('not_member', 'The new captain must belong to this team.')
            self._idle(self._player(new_captain_id, session))
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

    def start_campaign(self, actor_id, mission_id, *, native=False):
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
            if native:
                run['native_campaign'] = {'mission_version': MISSION_VERSION,
                    'nonce': secrets.token_hex(32), 'username': account['username']}
            self.db.game_runs.insert_one(run, session=session)
            return run
        return self._tx(write)

    @staticmethod
    def _progression_profile(account):
        leader = account['leader']
        return {'id': account['_id'], 'username': account['username'],
                **{key: deepcopy(leader[key]) for key in ('starter_id', 'unit_type', 'level',
                    'experience', 'total_experience', 'advancement_choices')}}

    @staticmethod
    def _time(value):
        # MongoDB stores milliseconds; initial and later projections must match.
        return value.isoformat(timespec='milliseconds') if value is not None else ''

    def _campaign_record(self, actor_id, run, *, nonce=False, session=None):
        if run['kind'] != 'campaign' or len(run['participants']) != 1 or run['participants'][0]['account_id'] != actor_id:
            raise DomainError('forbidden', 'Only the owner can access this campaign run.')
        participant = run['participants'][0]
        native = run.get('native_campaign', {})
        receipt = self.db.settlements.find_one({'_id': run['_id']}, session=session)
        award = receipt['rewards']['players'][0]['experience'] if receipt else 0
        return {'id': run['_id'], 'account_id': actor_id, 'username': native.get('username', ''),
                'mission_id': run['mission_id'], 'mission_name': MISSION_NAMES.get(run['mission_id'], ''),
                'mission_version': native.get('mission_version', ''), 'ruleset_version': run['ruleset_version'],
                'state': run['state'], 'unit_type': participant['leader']['unit_type'],
                'leader_level': participant['leader']['level'],
                'nonce': native.get('nonce', '') if nonce and run['state'] == 'running' else '',
                'created_at': self._time(run['created_at']), 'finished_at': self._time(run.get('finished_at')),
                'outcome': run.get('result', {}).get('outcome', ''), 'experience_awarded': award}

    def progression_catalog(self, actor_id):
        actor = self._directory_player(actor_id)
        missions = [{'id': mission, 'name': MISSION_NAMES[mission], 'version': MISSION_VERSION,
                     'unlocked': all(previous in actor['campaign_completed'] for previous in MISSIONS[:index]),
                     'completed': mission in actor['campaign_completed'], 'victory_experience': 20}
                    for index, mission in enumerate(MISSIONS)]
        active = None
        if actor['active_run_id']:
            run = self._run(actor['active_run_id'])
            if run['kind'] == 'campaign':
                active = self._campaign_record(actor_id, run, nonce=True)
        return {'profile': self._progression_profile(actor), 'missions': missions, 'active_run': active}

    def progression_start(self, actor_id, mission_id):
        run = self.start_campaign(actor_id, mission_id, native=True)
        return {'run': self._campaign_record(actor_id, run, nonce=True)}

    def progression_status(self, actor_id, run_id):
        self._directory_player(actor_id)
        _directory_id(run_id, uuid=True)
        return {'run': self._campaign_record(actor_id, self._run(run_id), nonce=True)}

    def progression_history(self, actor_id):
        self._directory_player(actor_id)
        rows = list(self.db.game_runs.find({'kind': 'campaign', 'participants.account_id': actor_id})
                    .sort([('created_at', -1), ('_id', 1)]).limit(21))
        return {'runs': [self._campaign_record(actor_id, row) for row in rows[:20]], 'has_more': len(rows) > 20}

    def progression_advance(self, actor_id, unit_type):
        return {'profile': self._progression_profile(self.choose_advancement(actor_id, unit_type))}

    def progression_cancel(self, actor_id, run_id):
        _directory_id(run_id, uuid=True)
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            self._campaign_record(actor_id, run, session=session)
            if not run.get('native_campaign'):
                raise DomainError('invalid_state', 'This run was not created by the native campaign adapter.')
            run = self._cancel(run_id, 'Player cancelled the native campaign', session)
            return {'run': self._campaign_record(actor_id, run, session=session)}
        return self._tx(write)

    def progression_finish(self, actor_id, run_id, mission_id, mission_version, nonce, outcome, replay_sha256, format):
        """Owned native result under the trusted-LAN model, not combat simulation.

        A practice save cannot use this route: it has no native registered run
        and nonce. The authenticated owner reports only a fixed win/loss; the
        service chooses the reward. The replay hash identifies client evidence,
        not proof that a recording was uploaded or independently verified.
        """
        _directory_id(run_id, uuid=True)
        if (format != 'alliance-native-campaign-result-v1' or mission_version != MISSION_VERSION or
                mission_id not in MISSIONS or outcome not in ('win', 'loss') or
                not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{64}', nonce) or
                not isinstance(replay_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', replay_sha256)):
            raise DomainError('invalid_result', 'The native campaign result is invalid.')
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            self._campaign_record(actor_id, run, session=session)
            native = run.get('native_campaign', {})
            if (run['mission_id'] != mission_id or native.get('mission_version') != mission_version or
                    not hmac.compare_digest(native.get('nonce', ''), nonce)):
                raise DomainError('invalid_result', 'The native campaign binding does not match.')
            evidence = {'format': format, 'replay_sha256': replay_sha256, 'mission_version': mission_version,
                        'source': 'trusted_native_client'}
            if 'native_result' in run and run['native_result'] != evidence:
                raise DomainError('result_conflict', 'This run already has different result evidence.')
            receipt = self._finish_campaign(run_id, outcome, session)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'native_result': evidence}}, session=session)
            return {'run': self._campaign_record(actor_id, self._run(run_id, session), session=session),
                    'profile': self._progression_profile(self._account(actor_id, session)),
                    'experience_awarded': receipt['rewards']['players'][0]['experience']}
        return self._tx(write)

    def create_battle(self, actor_id, opponent_team_id, map_id, lineups, *, expected_team_id=None, native_plan=False):
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
            if expected_team_id is not None and first['_id'] != expected_team_id:
                raise DomainError('conflict', 'The current team differs from the selected team.')
            second = self._team(opponent_team_id, session)
            if first['_id'] == second['_id'] or set(lineups) != {first['_id'], second['_id']}:
                raise DomainError('invalid_lineup', 'Choose two different teams and their matching lineups.')
            teams = [first, second]
            self._validate_battle_teams(teams, map_id, lineups, session)
            if self.db.game_runs.find_one({'kind': 'alliance', 'state': 'draft',
                    'team_ids': {'$in': [team['_id'] for team in teams]}}, {'_id': 1}, session=session):
                raise DomainError('planning_exists', 'One of these teams already has a planned battle. Inspect or cancel it first.')
            participants = self._participants(teams, map_id, lineups)
            for participant in participants:
                account = self._account(participant['account_id'], session)
                participant['leader'] = account['leader']
                if native_plan:
                    participant['username'] = account['username']
            run = {'_id': _id(), 'kind': 'alliance', 'state': 'draft',
                'ruleset_version': RULESET_VERSION, 'map_id': map_id, 'area_id': first['area_id'],
                'team_ids': [t['_id'] for t in teams], 'lineups': deepcopy(lineups),
                'approvals': {} if native_plan else {first['_id']: actor_id}, 'ready': [], 'participants': participants,
                'created_at': _now()}
            if native_plan:
                run['planning_teams'] = [{'id': team['_id'], 'name': team['name']} for team in teams]
            self.db.game_runs.insert_one(run, session=session)
            return self._planning_record(run, session) if native_plan else run
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
            self._idle(self._player(team['captain_id'], session))
            self._idle(team)
            self.db.teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
            members = {m['account_id'] for m in team['members']}
            if any(p not in members for p in lineups[team['_id']]):
                raise DomainError('not_member', 'Every selected player must belong to that team.')
            for player in lineups[team['_id']]:
                account = self._player(player, session)
                self._idle(account)
                if account['leader']['advancement_choices']:
                    raise DomainError('advancement_required', 'A selected player must choose their available leader advancement before preparing this battle.')
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
            if ready:
                self._planning_access(actor_id, run, session)
                self._planning_validate_mutation(run, session)
            self.db.game_runs.update_one({'_id': run_id}, {
                '$addToSet' if ready else '$pull': {'ready': actor_id}}, session=session)
            return self._run(run_id, session)
        return self._tx(write)

    def start_battle(self, actor_id, run_id):
        return self._tx(lambda session: self._start_battle(actor_id, run_id, session))

    def _start_battle(self, actor_id, run_id, session, *, shared_authorized=False):
        run = self._run(run_id, session)
        self._draft(run)
        if run.get('shared_room') and not shared_authorized:
            raise DomainError('room_required', 'A prepared shared room must start through its all-loaded barrier.')
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

    @staticmethod
    def _shared_binding(run, generation):
        _directory_id(generation, uuid=True)
        room = run.get('shared_room')
        if run['kind'] != 'alliance' or not room or room.get('generation') != generation:
            raise DomainError('room_conflict', 'The shared room generation does not match.')
        return room

    def _shared_record(self, actor_id, run, session=None):
        selected = next((p for p in run['participants'] if p['account_id'] == actor_id), None)
        if selected is None:
            raise DomainError('forbidden', 'Only a selected player may enter this shared battle.')
        room = run.get('shared_room', {})
        return {'battle': self._planning_record(run, session), 'generation': room.get('generation', ''),
                'room_state': room.get('state', ''), 'assigned_side': selected['side'],
                'scenario_sha256': room.get('scenario_sha256', ''),
                'expires_at': self._time(room.get('expires_at'))}

    def shared_prepare(self, actor_id, run_id, generation):
        """Trusted daemon after socket authentication; preparation reserves nobody."""
        _directory_id(run_id, uuid=True)
        _directory_id(generation, uuid=True)
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            self._draft(run)
            self._shared_record(actor_id, run, session)
            teams = self._planning_validate_mutation(run, session)
            if any(run['approvals'].get(team['_id']) != team['captain_id'] for team in teams):
                raise DomainError('approval_required', 'Both current captains must approve the shared battle.')
            if set(run['ready']) != {p['account_id'] for p in run['participants']}:
                raise DomainError('not_ready', 'Every selected player must be ready for a shared battle.')
            room = run.get('shared_room')
            if room and room['state'] == 'preparing' and room['expires_at'] > _now():
                if room['generation'] != generation:
                    raise DomainError('room_conflict', 'Another daemon owns this prepared room.')
            else:
                if room and room['generation'] == generation:
                    raise DomainError('room_expired', 'Use a fresh room generation after an expired or closed preparation.')
                room = {'generation': generation, 'state': 'preparing',
                        'expires_at': _now() + timedelta(minutes=5), 'scenario_sha256': '',
                        'result_reports': {}, 'result_approvals': {}, 'revision': 0}
                self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room': room}}, session=session)
            return self._shared_record(actor_id, self._run(run_id, session), session)
        return self._tx(write)

    def shared_admission(self, actor_id, run_id, generation):
        """Validate initial entry or same-seat reconnect; never choose a new seat."""
        _directory_id(run_id, uuid=True)
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            room = self._shared_binding(run, generation)
            if run['state'] not in ('draft', 'running') or room['state'] not in ('preparing', 'running'):
                raise DomainError('invalid_state', 'This shared battle is not accepting players.')
            if run['state'] == 'draft' and room['expires_at'] <= _now():
                raise DomainError('room_expired', 'The prepared room expired before the battle started.')
            teams, accounts, area = self._planning_context(run, session)
            if self._planning_validity(run, teams, accounts, area) != 'valid':
                raise DomainError('stale_proposal', 'The saved shared-battle lineup is no longer valid.')
            if run['state'] == 'running' and (any(team['active_run_id'] != run_id for team in teams) or any(
                    accounts[player['account_id']]['active_run_id'] != run_id for player in run['participants'])):
                raise DomainError('reservation_conflict', 'The running battle reservations no longer match.')
            return self._shared_record(actor_id, run, session)
        return self._tx(write)

    def shared_start(self, run_id, generation, loaded_account_ids, scenario_sha256):
        """Trusted daemon's all-loaded barrier, fenced and atomic with reservations."""
        _directory_id(run_id, uuid=True)
        if (not isinstance(loaded_account_ids, list) or not 4 <= len(loaded_account_ids) <= 8 or
                not all(isinstance(p, str) for p in loaded_account_ids)
                or len(loaded_account_ids) != len(set(loaded_account_ids)) or
                not isinstance(scenario_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', scenario_sha256)):
            raise DomainError('invalid_input', 'The loaded-seat proof is invalid.')
        def write(session):
            run = self._run(run_id, session)
            room = self._shared_binding(run, generation)
            if set(loaded_account_ids) != {p['account_id'] for p in run['participants']}:
                raise DomainError('not_ready', 'All assigned seats must load the same scenario before start.')
            if run['state'] == 'running':
                if room['state'] != 'running' or room['scenario_sha256'] != scenario_sha256:
                    raise DomainError('room_conflict', 'The running room has a different scenario.')
                return {'run_id': run_id, 'state': 'running', 'generation': generation, 'scenario_sha256': scenario_sha256}
            if room['state'] != 'preparing' or room['expires_at'] <= _now():
                raise DomainError('room_expired', 'The prepared room expired before the battle started.')
            captain = self._team(run['team_ids'][0], session)['captain_id']
            self._start_battle(captain, run_id, session, shared_authorized=True)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.state': 'running',
                'shared_room.scenario_sha256': scenario_sha256, 'shared_room.captains': {team_id: self._team(team_id, session)['captain_id'] for team_id in run['team_ids']}}, '$inc': {'shared_room.revision': 1}}, session=session)
            return {'run_id': run_id, 'state': 'running', 'generation': generation, 'scenario_sha256': scenario_sha256}
        return self._tx(write)

    def shared_evidence_admission(self, actor_id, run_id, generation):
        """Allow an exact owner to retry an END receipt after settlement.

        This grants no gameplay admission or current team membership. A completed
        seat can only retransmit evidence matching its immutable saved report.
        """
        _directory_id(run_id, uuid=True)
        self._directory_player(actor_id)
        run = self._run(run_id)
        room = self._shared_binding(run, generation)
        if run['state'] == 'running':
            return self.shared_admission(actor_id, run_id, generation)
        if run['state'] != 'completed' or room['state'] != 'completed' or actor_id not in room.get('result_reports', {}):
            raise DomainError('invalid_state', 'Only an existing running or completed seat result can be retried.')
        return self._shared_record(actor_id, run)

    def shared_replay_access(self, actor_id, run_id):
        """Read one retained completed recording without granting a game seat."""
        self._directory_player(actor_id)
        run = self._run(_directory_id(run_id, uuid=True))
        room = run.get('shared_room', {})
        if run['state'] != 'completed' or room.get('state') != 'completed':
            raise DomainError('invalid_state', 'A replay is available only after the shared result is settled.')
        selected = {item['account_id']: item for item in run['participants']}
        if actor_id in selected:
            recording_actor = actor_id
        elif actor_id in room.get('captains', {}).values():
            recording_actor = min(run['participants'], key=lambda item: item['side'])['account_id']
        else:
            raise DomainError('forbidden', 'Only the recorded battle players and captains can retrieve its replay.')
        report = room.get('result_reports', {}).get(recording_actor)
        if not report:
            raise DomainError('not_found', 'The completed recording is unavailable.')
        return {'run_id': run['_id'], 'account_id': recording_actor,
                'generation': room['generation'], 'sha256': report['replay_sha256']}

    def shared_captain_command(self, actor_id, run_id, generation, command_id, event, replay):
        """Trusted daemon records an ordered, synchronized captain action.

        This is not a terminal HTTP route. The caller must first establish the
        native command's authenticated seat and replay ordering. Recording a
        directive never ends or settles a battle by itself.
        """
        _directory_id(run_id, uuid=True)
        if (event not in ('surrender', 'offer_draw', 'withdraw_draw') or
                not isinstance(command_id, str) or not re.fullmatch(r'[0-9a-f]{64}', command_id) or
                not isinstance(replay, dict) or set(replay) != {'previous', 'wml'} or
                not isinstance(replay['previous'], str) or not re.fullmatch(r'[0-9a-f]{64}', replay['previous']) or
                not isinstance(replay['wml'], str) or not 1 <= len(replay['wml'].encode('utf-8')) <= 65536 or
                '\0' in replay['wml'] or hashlib.sha256(json.dumps(replay, sort_keys=True,
                    separators=(',', ':')).encode()).hexdigest() != command_id):
            raise DomainError('invalid_input', 'A bounded captain command binding is required.')
        def write(session):
            account = self._account(actor_id, session)
            if account['role'] != 'player':
                raise DomainError('forbidden', 'Only a participating captain may act.')
            run = self._run(run_id, session)
            room = self._shared_binding(run, generation)
            previous = room.get('captain_commands', {}).get(command_id)
            if previous:
                if previous['actor_id'] != actor_id or previous['event'] != event or previous['replay'] != replay:
                    raise DomainError('result_conflict', 'A captain command binding cannot be reused.')
                return deepcopy(previous)
            if run['state'] != 'running' or room['state'] != 'running':
                raise DomainError('invalid_state', 'Captain commands require a running shared battle.')
            if actor_id not in {item['account_id'] for item in run['participants']}:
                raise DomainError('forbidden', 'Only a selected captain seat may emit a synchronized game command.')
            if room.get('result_reports') or room.get('terminal'):
                raise DomainError('invalid_state', 'This battle already has a terminal decision or result report.')
            teams = [self._team(team_id, session) for team_id in run['team_ids']]
            team = next((item for item in teams if item['captain_id'] == actor_id), None)
            if team is None or room.get('captains', {}).get(team['_id']) != actor_id:
                raise DomainError('forbidden', 'Only a recorded current captain may act.')
            self._captain(actor_id, team, session)
            if any(item['active_run_id'] != run_id for item in teams):
                raise DomainError('reservation_conflict', 'The shared team reservations changed.')
            if len(room.get('captain_commands', {})) >= 128:
                raise DomainError('limit_reached', 'This battle has reached its captain-command limit.')
            offers = set(room.get('draw_offers', []))
            terminal = None
            if event == 'offer_draw':
                offers.add(team['_id'])
                if offers == set(run['team_ids']):
                    terminal = {'kind': 'draw', 'winner_team_id': None, 'draw': True}
            elif event == 'withdraw_draw':
                offers.discard(team['_id'])
            else:
                terminal = {'kind': 'surrender', 'winner_team_id': next(item for item in run['team_ids'] if item != team['_id']), 'draw': False}
            if terminal:
                terminal.update({'command_id': command_id, 'actor_id': actor_id})
            receipt = {'actor_id': actor_id, 'team_id': team['_id'], 'event': event,
                       'command_id': command_id, 'draw_offers': sorted(offers), 'terminal': terminal,
                       'replay': deepcopy(replay)}
            update = {'shared_room.draw_offers': sorted(offers),
                      'shared_room.captain_commands.' + command_id: receipt}
            if terminal:
                update['shared_room.terminal'] = terminal
            self.db.game_runs.update_one({'_id': run_id}, {'$set': update,
                '$inc': {'shared_room.revision': 1}}, session=session)
            return deepcopy(receipt)
        return self._tx(write)

    def shared_cancel(self, run_id, generation, reason):
        """Fenced daemon shutdown/abort; never expire or settle a running room."""
        _directory_id(run_id, uuid=True)
        reason = _reason(reason)
        def write(session):
            run = self._run(run_id, session)
            self._shared_binding(run, generation)
            if run['state'] == 'draft':
                # No battle was started. Preserve the plan and consent for a
                # later explicit room attempt, while fencing this room closed.
                self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.state': 'cancelled',
                    'shared_room.cancel_reason': reason}, '$inc': {'shared_room.revision': 1}}, session=session)
                return {'run_id': run_id, 'state': 'draft', 'room_state': 'cancelled'}
            run = self._cancel(run_id, reason, session)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.state': 'cancelled'},
                                                          '$inc': {'shared_room.revision': 1}}, session=session)
            return {'run_id': run_id, 'state': run['state'], 'room_state': 'cancelled'}
        return self._tx(write)

    @staticmethod
    def _shared_candidate(run):
        room = run['shared_room']
        reports = room.get('result_reports', {})
        expected = {p['account_id'] for p in run['participants']}
        if set(reports) != expected:
            return 'waiting_for_players', '', None, False
        outcomes = {(value['winner_team_id'], value['draw']) for value in reports.values()}
        if len(outcomes) != 1:
            return 'disputed', '', None, False
        winner, draw = next(iter(outcomes))
        digest = hashlib.sha256(json.dumps({'run_id': run['_id'], 'generation': room['generation'],
            'scenario_sha256': room['scenario_sha256'], 'reports': reports},
            sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        return 'awaiting_captains', digest, winner, draw

    def _shared_review(self, run, session=None):
        room = run['shared_room']
        review, digest, winner, draw = self._shared_candidate(run)
        approvals = room.get('result_approvals', {})
        captains = room.get('captains', {})
        count = sum(1 for team, captain in captains.items()
                    if approvals.get(team) == {'captain_id': captain, 'digest': digest} and digest)
        if review == 'awaiting_captains' and count == 2:
            review = 'agreed'
        if run['state'] == 'completed':
            review = 'settled'
            winner, draw = run['result']['winner_team_id'], run['result']['draw']
        elif run['state'] == 'cancelled':
            review = 'cancelled'
        return {'run_id': run['_id'], 'state': run['state'], 'review_state': review,
                'candidate_digest': digest, 'winner_team_id': winner or '', 'draw': draw,
                'reports_received': len(room.get('result_reports', {})),
                'required_reports': len(run['participants']), 'captains_approved': count,
                'revision': room.get('revision', 0)}

    def shared_result_review(self, actor_id, run_id):
        self._directory_player(actor_id)
        run = self._run(_directory_id(run_id, uuid=True))
        if not run.get('shared_room'):
            raise DomainError('not_found', 'This plan has no shared result to review.')
        permitted = {p['account_id'] for p in run['participants']} | set(run['shared_room'].get('captains', {}).values())
        if actor_id not in permitted:
            raise DomainError('forbidden', 'Only battle players and captains can review its result.')
        return self._shared_review(run)

    def shared_report_result(self, actor_id, run_id, generation, winner_team_id, draw, replay_sha256):
        """Trusted daemon forwards an authenticated actual game END report.

        Reports are immutable and do not award XP. Every selected player must
        report the same result, followed by both current captains' agreement.
        A replay digest identifies evidence; it does not claim simulation proof.
        """
        _directory_id(run_id, uuid=True)
        if (type(draw) is not bool or (draw and winner_team_id is not None) or
                (not draw and not isinstance(winner_team_id, str)) or
                not isinstance(replay_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', replay_sha256)):
            raise DomainError('invalid_result', 'The shared result report is invalid.')
        report = {'winner_team_id': winner_team_id, 'draw': draw, 'replay_sha256': replay_sha256}
        def write(session):
            self._player(actor_id, session)
            run = self._run(run_id, session)
            room = self._shared_binding(run, generation)
            if actor_id not in {p['account_id'] for p in run['participants']}:
                raise DomainError('forbidden', 'Only selected players may report this game result.')
            if not draw and winner_team_id not in run['team_ids']:
                raise DomainError('invalid_result', 'The winner must be a participating team.')
            previous = room.get('result_reports', {}).get(actor_id)
            if previous is not None:
                if previous != report:
                    raise DomainError('result_conflict', 'This player already submitted different result evidence.')
                return self._shared_review(run, session)
            if run['state'] != 'running' or room['state'] != 'running':
                raise DomainError('invalid_state', 'Only a running shared game accepts result reports.')
            terminal = room.get('terminal')
            if terminal and (terminal['winner_team_id'] != winner_team_id or terminal['draw'] != draw):
                raise DomainError('result_conflict', 'The game END report differs from the synchronized captain decision.')
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.result_reports.' + actor_id: report},
                                                          '$inc': {'shared_room.revision': 1}}, session=session)
            return self._shared_review(self._run(run_id, session), session)
        return self._tx(write)

    def shared_confirm_result(self, actor_id, run_id, candidate_digest):
        _directory_id(run_id, uuid=True)
        if not isinstance(candidate_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', candidate_digest):
            raise DomainError('invalid_result', 'A current result digest is required.')
        def write(session):
            run = self._run(run_id, session)
            if not run.get('shared_room') or run['state'] != 'running':
                raise DomainError('invalid_state', 'Only a running shared game can receive result agreement.')
            teams = [self._team(team_id, session) for team_id in run['team_ids']]
            team = next((t for t in teams if t['captain_id'] == actor_id), None)
            if team is None:
                raise DomainError('forbidden', 'Only a participating current captain may agree to a result.')
            self._captain(actor_id, team, session)
            state, digest, _, _ = self._shared_candidate(run)
            if state != 'awaiting_captains' or digest != candidate_digest:
                raise DomainError('result_conflict', 'The result is incomplete, disputed or changed. Review it again.')
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.result_approvals.' + team['_id']:
                {'captain_id': actor_id, 'digest': digest}}, '$inc': {'shared_room.revision': 1}}, session=session)
            return self._shared_review(self._run(run_id, session), session)
        return self._tx(write)

    def shared_finish(self, run_id, generation):
        """Only the fenced game daemon can settle agreed actual END reports."""
        _directory_id(run_id, uuid=True)
        def write(session):
            run = self._run(run_id, session)
            self._shared_binding(run, generation)
            if run['state'] == 'completed':
                return self.db.settlements.find_one({'_id': run_id}, session=session)
            review = self._shared_review(run, session)
            if review['review_state'] != 'agreed':
                raise DomainError('result_agreement_required', 'All game reports and both captain agreements are required.')
            for team_id, captain in run['shared_room']['captains'].items():
                if self._team(team_id, session)['captain_id'] != captain:
                    raise DomainError('result_conflict', 'A team captain changed during result review.')
            receipt = self._finish_battle(run_id, review['winner_team_id'] or None, review['draw'], session,
                                          shared_authorized=True)
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.state': 'completed'}}, session=session)
            return receipt
        return self._tx(write)

    def admin_resolve_shared_result(self, actor_id, run_id, winner_team_id, draw, reason, expected_revision):
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        if type(draw) is not bool or (draw and winner_team_id is not None) or (not draw and not isinstance(winner_team_id, str)):
            raise DomainError('invalid_result', 'Choose a participating winner or a draw.')
        def write(session):
            self._admin(actor_id, session)
            run = self._run(_directory_id(run_id, uuid=True), session)
            room = run.get('shared_room')
            if not room or run['state'] != 'running' or room['state'] != 'running':
                raise DomainError('invalid_state', 'Only an unfinished shared battle can be reviewed.')
            if room.get('revision', 0) != expected_revision:
                raise DomainError('result_conflict', 'The result changed. Reload it before resolving.')
            if set(room.get('result_reports', {})) != {p['account_id'] for p in run['participants']}:
                raise DomainError('result_agreement_required', 'All player END reports must exist before operator resolution.')
            if not draw and winner_team_id not in run['team_ids']:
                raise DomainError('invalid_result', 'The winner must be a participating team.')
            terminal = room.get('terminal')
            if terminal and (terminal['winner_team_id'] != winner_team_id or terminal['draw'] != draw):
                raise DomainError('result_conflict', 'Operator resolution must retain the synchronized captain decision.')
            before = self._shared_review(run, session)
            receipt = self._finish_battle(run_id, winner_team_id, draw, session, shared_authorized=True)
            resolution = {'actor_id': actor_id, 'reason': reason, 'winner_team_id': winner_team_id,
                          'draw': draw, 'created_at': _now()}
            self.db.game_runs.update_one({'_id': run_id}, {'$set': {'shared_room.state': 'completed',
                'shared_room.operator_resolution': resolution}}, session=session)
            self._audit(actor_id, 'resolve_shared_result', run_id, reason, before,
                        {'winner_team_id': winner_team_id, 'draw': draw}, session)
            return receipt
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
        return self._tx(lambda session: self._finish_campaign(run_id, outcome, session))

    def _finish_campaign(self, run_id, outcome, session):
        result = {'kind': 'campaign', 'outcome': outcome}
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

    def finish_battle(self, run_id, winner_team_id=None, draw=False):
        """Trusted bridge only; it must establish victory/surrender or mutual draw."""
        if type(draw) is not bool or (draw and winner_team_id is not None) or (not draw and not isinstance(winner_team_id, str)):
            raise DomainError('invalid_result', 'Provide one winning team or an agreed draw.')
        return self._tx(lambda session: self._finish_battle(run_id, winner_team_id, draw, session))

    def _finish_battle(self, run_id, winner_team_id, draw, session, *, shared_authorized=False):
        result = {'kind': 'alliance', 'winner_team_id': winner_team_id, 'draw': draw}
        previous = self._existing_settlement(run_id, result, session)
        if previous is not None:
            return previous
        run = self._run(run_id, session)
        self._require_ruleset(run)
        if run['kind'] != 'alliance' or run['state'] != 'running':
            raise DomainError('invalid_state', 'Only a running alliance battle can finish.')
        if run.get('shared_room') and not shared_authorized:
            raise DomainError('result_agreement_required', 'Shared games require bound player reports and captain review.')
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
                    'approved_maps': list(MAPS), 'created_at': _now(), 'revision': 0}
            self.db.areas.insert_one(area, session=session)
            self._audit(actor_id, 'create_area', area['_id'], 'Create an area', None,
                        {'name': name}, session)
            return area
        return self._tx(write)

    def admin_edit_area(self, actor_id, area_id, name, enabled, approved_maps, reason, expected_revision):
        name, key = _name(name, 'Area name')
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        if (type(enabled) is not bool or not isinstance(approved_maps, list) or
                not approved_maps or any(not isinstance(value, str) or value not in MAPS for value in approved_maps) or
                len(approved_maps) != len(set(approved_maps))):
            raise DomainError('invalid_input', 'Choose at least one distinct approved map and a valid enabled setting.')
        def write(session):
            self._admin(actor_id, session)
            area = self.db.areas.find_one({'_id': _directory_id(area_id)}, session=session)
            if area is None:
                raise DomainError('not_found', 'Area not found.')
            if area.get('revision', 0) != expected_revision:
                raise DomainError('stale_area', 'This area changed. Reload it before saving.')
            if self.db.teams.find_one({'area_id': area_id, 'active_run_id': {'$ne': None}}, {'_id': 1}, session=session):
                raise DomainError('busy', 'Finish or cancel the area\'s active team battles first.')
            before = {key: area[key] for key in ('name', 'enabled', 'approved_maps')}
            after = {'name': name, 'enabled': enabled, 'approved_maps': list(approved_maps)}
            self.db.areas.update_one({'_id': area_id}, {'$set': {**after, 'name_key': key},
                '$inc': {'revision': 1}}, session=session)
            self._audit(actor_id, 'edit_area', area_id, reason, before, after, session)
            return self.db.areas.find_one({'_id': area_id}, session=session)
        return self._tx(write)

    def team_orders(self, actor_id, team_id):
        self._directory_player(actor_id)
        team = self._team(_directory_id(team_id, uuid=True))
        if actor_id not in {member['account_id'] for member in team['members']}:
            raise DomainError('forbidden', 'Only current team members may read captain orders.')
        # Retain fifty locally, but keep a single wire response well below the
        # bridge's 32 KiB JSON bound even with escaped non-ASCII text.
        history = team.get('orders', [])
        return {'team_id': team_id, 'team_name': team['name'], 'has_more': len(history) > 10,
                'orders': [{**{key: entry[key] for key in ('id', 'author_id', 'author_name', 'text')},
                            'created_at': self._time(entry['created_at'])}
                           for entry in reversed(history[-10:])]}

    def post_team_order(self, actor_id, team_id, text):
        team_id = _directory_id(team_id, uuid=True)
        text = _reason(text)
        try:
            valid_size = len(text.encode('utf-8')) <= 500
        except UnicodeEncodeError:
            valid_size = False
        if not valid_size:
            raise DomainError('invalid_input', 'An order must fit within 500 UTF-8 bytes.')
        if any(ord(char) < 32 and char not in '\n\t' for char in text):
            raise DomainError('invalid_input', 'The order contains unsupported control characters.')
        def write(session):
            team = self._team(team_id, session)
            actor = self._captain(actor_id, team, session)
            order = {'id': _id(), 'author_id': actor_id, 'author_name': actor['username'],
                     'text': text, 'created_at': _now()}
            self.db.teams.update_one({'_id': team_id}, {'$push': {'orders': {'$each': [order], '$slice': -50}},
                                                       '$inc': {'revision': 1}}, session=session)
            return {'order': {**{key: order[key] for key in ('id', 'author_id', 'author_name', 'text')},
                              'created_at': self._time(order['created_at'])}}
        return self._tx(write)

    def admin_correct_experience(self, actor_id, account_id, delta, reason, expected_revision):
        """Bounded audited correction; never edits unit type, team or combat stats."""
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        if type(delta) is not int or not -1000 <= delta <= 1000 or delta == 0:
            raise DomainError('invalid_input', 'An experience correction must be a nonzero integer from -1000 to 1000.')
        def write(session):
            account = self._admin_account_revision(actor_id, account_id, expected_revision, session)
            if account['role'] != 'player':
                raise DomainError('forbidden', 'Only player leaders receive experience corrections.')
            self._idle(account)
            before = deepcopy(account['leader'])
            leader = deepcopy(before)
            total = leader['total_experience'] + delta
            current = leader['experience'] + delta
            _, threshold, advances = UNIT_TYPES[leader['unit_type']]
            pending = [(STARTERS[leader['starter_id']]['unit_type'], 0)]
            spent = None
            while pending:
                unit, cost = pending.pop()
                if unit == leader['unit_type']:
                    spent = cost
                    break
                pending.extend((child, cost + UNIT_TYPES[unit][1]) for child in UNIT_TYPES[unit][2])
            if spent is None or total < spent or (advances and current < 0):
                raise DomainError('invalid_correction', 'This correction would remove experience already spent on advancement.')
            leader['total_experience'] = total
            leader['experience'] = current if advances else 0
            leader['advancement_choices'] = list(advances) if advances and current >= threshold else []
            self.db.accounts.update_one({'_id': account_id}, {'$set': {'leader': leader}, '$inc': {'revision': 1}}, session=session)
            self._audit(actor_id, 'correct_leader_experience', account_id, reason, before, leader, session)
            return self._progression_profile(self._account(account_id, session, active=False))
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

    def _admin_account_revision(self, actor_id, account_id, expected_revision, session):
        """Authorize and serialize one submitted account form, including self edits."""
        self._admin(actor_id, session)
        account = self._account(account_id, session, active=False)
        # _admin already touched the actor in this transaction. The submitted
        # revision describes the account before that privileged-operation guard.
        original_revision = account['revision'] - (1 if actor_id == account_id else 0)
        if original_revision != expected_revision:
            raise DomainError('stale_account', 'This account changed. Reload the page before trying again.')
        return account

    @staticmethod
    def _expected_account_revision(value):
        if type(value) is not int or not 0 <= value <= 9223372036854775806:
            raise DomainError('invalid_input', 'A valid account revision is required.')

    def _clear_account_attempts(self, account, username_keys, session):
        # Login uses fixed fifteen-minute buckets. Clear only this role/name's
        # current and preceding buckets; never erase unrelated login counters.
        bucket = int(_now().timestamp()) // 900
        ids = [hashlib.sha256(f"{account['role']}:{key}:{number}".encode()).hexdigest()
               for key in set(username_keys) for number in (bucket - 1, bucket)]
        self.db.auth_attempts.delete_many({'_id': {'$in': ids}}, session=session)

    def admin_edit_account(self, actor_id, account_id, username, status, reason, expected_revision):
        """Edit only login name/status; identity and all game-owned fields stay intact."""
        username, key = validate_username(username)
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        if status not in ('active', 'suspended'):
            raise DomainError('invalid_input', 'Account status must be active or suspended.')

        def write(session):
            account = self._admin_account_revision(actor_id, account_id, expected_revision, session)
            self._idle(account)
            if actor_id == account_id and status == 'suspended':
                raise DomainError('forbidden', 'An administrator cannot suspend their own account.')
            if account['role'] == 'admin' and status == 'suspended':
                if self.db.accounts.count_documents({'role': 'admin', 'status': 'active'}, session=session) <= 1:
                    raise DomainError('last_admin', 'The last active administrator cannot be suspended.')
            before = {'username': account['username'], 'status': account['status']}
            after = {'username': username, 'status': status}
            update = {'$set': {'username': username, 'username_key': key, 'status': status}}
            if actor_id != account_id:
                update['$inc'] = {'revision': 1}
            self.db.accounts.update_one({'_id': account_id}, update, session=session)
            if before != after:
                self.db.auth_sessions.delete_many({'account_id': account_id}, session=session)
            if account['username'] != username:
                self._clear_account_attempts(account, (account['username_key'], key), session)
            self._audit(actor_id, 'edit_account', account_id, reason, before, after, session)
            return public_account(self._account(account_id, session, active=False))
        return self._tx(write)

    def admin_reset_password(self, actor_id, account_id, password, confirmation, reason, expected_revision):
        """Set a new exact password and revoke every target session atomically."""
        from .auth import hash_password
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        if (not isinstance(password, str) or not 12 <= len(password) <= 128
                or '\x00' in password or any(0xD800 <= ord(char) <= 0xDFFF for char in password)):
            raise DomainError('invalid_input', 'Use a password of 12 to 128 valid Unicode characters without NUL.')
        if not isinstance(confirmation, str) or password != confirmation:
            raise DomainError('invalid_input', 'The password confirmation must match exactly.')
        # Avoid expensive hashing for an unauthorized caller, while rechecking
        # authorization inside the transaction before changing any records.
        actor = self._account(actor_id)
        if actor['role'] != 'admin':
            raise DomainError('forbidden', 'Administrator access is required.')
        encoded = hash_password(password)

        def write(session):
            account = self._admin_account_revision(actor_id, account_id, expected_revision, session)
            # Password recovery is allowed during an active run. It never
            # releases or changes a game reservation, leader, team or reward.
            update = {'$set': {'password_hash': encoded}}
            if actor_id != account_id:
                update['$inc'] = {'revision': 1}
            self.db.accounts.update_one({'_id': account_id}, update, session=session)
            self.db.auth_sessions.delete_many({'account_id': account_id}, session=session)
            self._clear_account_attempts(account, (account['username_key'],), session)
            self._audit(actor_id, 'reset_password', account_id, reason, None,
                        {'password_reset': True, 'sessions_revoked': True}, session)
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
