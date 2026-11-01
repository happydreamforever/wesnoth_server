"""Transaction, authorization and public-record primitives for Emerald Court."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4

from ..domain import DomainError


PRICES = dict(create_team=50, join_team=5, create_room=5, join_room=2,
              hero=100, item=5, attack_neutral=5, attack_owned=10, plan=10,
              relocate=50, extra_attack=10, extra_plan=20)
LIMITS = dict(team_members=10, teams_per_area=30, area_expansion_teams=16,
              castles_per_team=3, normal_castles_per_team=2,
              minimum_normal_castles=4, closure_delay_seconds=86400,
              protection_seconds=3600, defender_response_seconds=120,
              member_allowance=20, attacks_per_day=3, extra_attacks_per_day=2,
              plans_per_day=3, extra_plans_per_day=2, proposal_seconds=600,
              attendance_seconds=300, reconnect_seconds=300,
              preparation_seconds=300, queue_seconds=600,
              hero_level_cap=30, battle_cash_per_day=50,
              castle_income=5, team_income_per_day=15,
              income_hold_seconds=3600, campaign_cash=25,
              tournament_max_teams=32, voluntary_cancel_seconds=120)


def fail(code, message):
    raise DomainError(code, message)


def exact(payload, required=(), optional=()):
    if (not isinstance(payload, dict) or not set(required) <= set(payload)
            or set(payload) - set(required) - set(optional) - {'command_id'}):
        fail('invalid_input', 'The request fields differ. Refresh and try again.')


def integer(value, low=0, high=9_000_000_000_000):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        fail('invalid_input', 'A number is outside its permitted range.')
    return int(value)


def identifier(value, kind='uuid'):
    patterns = {'uuid': r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
                'area': r'A\d{3}', 'castle': r'A\d{3}-C\d{3}'}
    if not isinstance(value, str) or not re.fullmatch(patterns.get(kind, patterns['uuid']), value):
        fail('invalid_input', 'The selected record is invalid.')
    if kind in ('area', 'castle') and not 1 <= int(value[1:4]) <= 128:
        fail('invalid_input', 'The selected Area is invalid.')
    if kind == 'castle' and not 1 <= int(value[6:]) <= 64:
        fail('invalid_input', 'The selected Castle is invalid.')
    return value


def text(value, label='Name', maximum=80, minimum=1):
    if not isinstance(value, str):
        fail('invalid_input', f'{label} is required.')
    value = value.strip()
    if not minimum <= len(value) <= maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail('invalid_input', f'{label} must contain {minimum}–{maximum} readable characters.')
    return value


def revision(record, expected):
    if record.get('revision', 0) != integer(expected):
        fail('stale_revision', 'Updated—review changes before confirming.')


def public(value):
    """Serialize only records explicitly selected by a public projection."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    return value


class CourtBase:
    def __init__(self, db, *, clock=None):
        self.db = db
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError('Court clock must return an aware UTC datetime.')
        return value.astimezone(timezone.utc)

    def _generation(self, session=None):
        record = self.db.schema_metadata.find_one({'_id': 'alliance', 'version': 5}, session=session)
        if (not record or record.get('court_initialized') is not True
                or not isinstance(record.get('database_generation'), str)):
            fail('unsupported_ruleset', 'This release requires the verified fresh Court game.')
        return record['database_generation']

    def _actor(self, actor, session=None):
        account = self.db.accounts.find_one({'_id': identifier(actor), 'role': 'player',
            'status': 'active', 'database_generation': self._generation(session)}, session=session)
        if account is None:
            fail('account_unavailable', 'Please sign in to an active player account.')
        return account

    def _admin_actor(self, actor, session=None):
        account = self.db.accounts.find_one({'_id': identifier(actor), 'role': 'admin',
            'status': 'active', 'database_generation': self._generation(session)}, session=session)
        if account is None:
            fail('forbidden', 'An active administrator is required.')
        return account

    def _settings(self, session=None):
        row = self.db.court_settings.find_one({'_id': 'rules'}, session=session)
        if row is None:
            fail('unsupported_ruleset', 'Court settings have not been initialized.')
        return deepcopy(row)

    def _price_revision(self, payload, session):
        row = self._settings(session)
        if integer(payload.get('price_revision')) != row['revision']:
            fail('price_changed', 'Prices changed—review the current cost.')
        # Serialize spending against a concurrent admin price change without
        # invalidating the public price revision for every ordinary purchase.
        self.db.court_settings.update_one({'_id': 'rules', 'revision': row['revision']},
            {'$inc': {'spending_fence': 1}}, session=session)
        return row

    def _team_for(self, actor, session=None, required=True):
        row = self.db.court_teams.find_one({'status': 'active', 'members.account_id': actor}, session=session)
        if row is None and required:
            fail('team_required', 'Join a Team first.')
        return row

    def _team(self, team_id, session=None):
        row = self.db.court_teams.find_one({'_id': identifier(team_id), 'status': 'active'}, session=session)
        if row is None:
            fail('not_found', 'This Team is unavailable.')
        return row

    def _captain(self, actor, team, session):
        self._actor(actor, session)
        if team.get('captain_id') != actor:
            fail('forbidden', 'Only the captain can perform this action.')

    def _notify(self, account_ids, kind, title, message, target, session):
        if isinstance(account_ids, str):
            account_ids = [account_ids]
        for actor in sorted(set(account_ids)):
            self.db.court_notifications.insert_one({'_id': str(uuid4()), 'account_id': actor,
                'kind': kind, 'title': title, 'message': message, 'target': deepcopy(target),
                'created_at': self._now(), 'read_at': None, 'revision': 0}, session=session)

    def _team_notice(self, team, kind, title, message, target, session):
        self._notify([m['account_id'] for m in team['members']], kind, title, message, target, session)

    def _history(self, team_id, kind, title, data, session):
        self.db.court_history.insert_one({'_id': str(uuid4()), 'team_id': team_id,
            'kind': kind, 'title': title, 'data': deepcopy(data), 'created_at': self._now()}, session=session)

    def _envelope(self, actor, data, session=None):
        return public({'version': 1, 'actor_id': actor,
            'database_generation': self._generation(session), 'server_time': self._now(), 'data': data})

    def _execute(self, actor, operation, payload, handler, *, admin=False):
        if not isinstance(payload, dict):
            fail('invalid_input', 'A command object is required.')
        command = identifier(payload.get('command_id'))
        try:
            encoded = json.dumps({'operation': operation, 'payload': payload},
                sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        except (TypeError, ValueError, RecursionError):
            fail('invalid_input', 'The command cannot be represented.')
        if len(encoded) > 65536:
            fail('invalid_input', 'The command is too large.')
        digest = sha256(encoded).hexdigest()
        def write(session):
            (self._admin_actor if admin else self._actor)(actor, session)
            generation = self._generation(session)
            key = f'{generation}:{actor}:{command}'
            previous = self.db.court_commands.find_one({'_id': key}, session=session)
            if previous:
                if previous['digest'] != digest:
                    fail('command_conflict', 'This action identifier belongs to a different request.')
                return previous['result']
            # Race with account suspension/deletion/session governance.
            self.db.accounts.update_one({'_id': actor}, {'$inc': {'revision': 1}}, session=session)
            result = self._envelope(actor, handler(actor, payload, session), session)
            self.db.court_commands.insert_one({'_id': key, 'account_id': actor,
                'command_id': command, 'operation': operation, 'digest': digest,
                'result': result, 'created_at': self._now()}, session=session)
            return result
        return self._tx(write)
