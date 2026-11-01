"""Court challenges, accepted plans, tournaments and native battle authority.

Player commands never accept results, rewards, controller tickets or terminal
evidence. The worker entrypoints below are for the service supervisor only.
All helpers ending in ``session`` participate in their caller's transaction.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta, timezone
from hashlib import sha256
import hmac
import json
import re
import secrets
from uuid import uuid4

from ..heroes import catalog_form, hero_progress, MAX_XP
from ..rules import team_level
from ..domain import DomainError
from .base import exact, fail, identifier, integer, public, revision, text


ACTIVE_STATES = ('proposed', 'response', 'scheduled', 'queued', 'preparing',
                 'running', 'paused', 'disputed')
TERMINAL_STATES = ('completed', 'cancelled')
FACTIONS = ('Loyalists', 'Rebels', 'Northerners', 'Knalgan Alliance', 'Drakes', 'Undead')
BATTLE_MAPS = {
    'weldyn-channel': {'name': 'Weldyn Channel', 'scenario_id': 'multiplayer_Weldyn_Channel',
                       'size': 1, 'sides': ((1,), (2,))},
    'isars-cross': {'name': "Isar's Cross", 'scenario_id': 'multiplayer_Isars_Cross',
                    'size': 2, 'sides': ((1, 4), (2, 3))},
    'hexcake': {'name': 'Hexcake', 'scenario_id': 'multiplayer_Hexcake',
                'size': 3, 'sides': ((1, 4, 5), (2, 3, 6))},
    'mokena-prairie': {'name': 'Mokena Prairie', 'scenario_id': 'multiplayer_8p_Mokena_Prairie',
                       'size': 4, 'sides': ((1, 3, 5, 8), (2, 4, 6, 7))},
}
DEFAULT_BATTLE_SETTINGS = dict(map_id='weldyn-channel', size=1, gold=100,
    base_income=2, turns=30, fog=True, shroud=False, observers=False,
    hero_cap=30, items=False)


def canonical(value):
    return json.dumps(public(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def settings(value):
    exact(value, tuple(DEFAULT_BATTLE_SETTINGS))
    if set(value) != set(DEFAULT_BATTLE_SETTINGS):
        fail('invalid_input', 'Battle settings contain unsupported fields.')
    result = deepcopy(value)
    if not isinstance(result['map_id'], str) or result['map_id'] not in BATTLE_MAPS:
        fail('invalid_map', 'Choose an available tactical map.')
    if integer(result['size'], 1, 4) != BATTLE_MAPS[result['map_id']]['size']:
        fail('invalid_input', 'The selected map does not support that match size.')
    if integer(result['gold'], 100, 300) not in (100, 150, 200, 250, 300):
        fail('invalid_input', 'Choose a starting-gold preset.')
    integer(result['base_income'], 0, 20)
    integer(result['turns'], 1, 1000)
    if integer(result['hero_cap'], 1, 30) not in (5, 15, 30):
        fail('invalid_input', 'Choose battle level cap 5, 15 or 30.')
    for key in ('fog', 'shroud', 'observers', 'items'):
        if type(result[key]) is not bool:
            fail('invalid_input', 'Battle toggles must be true or false.')
    return result


def bounded_hash(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        fail('invalid_evidence', 'A complete native evidence hash is required.')
    return value


def tournament_score(scores, team_ids, *, seed, match_id):
    """Integer, published objective tie-break. Seed is committed before play."""
    if not isinstance(scores, list) or len(scores) != 2:
        fail('invalid_evidence', 'Both Teams require a native score.')
    values = {}
    for row in scores:
        exact(row, ('team_id', 'leaders', 'villages', 'unit_value_hp', 'gold'))
        if row['team_id'] not in team_ids or row['team_id'] in values:
            fail('invalid_evidence', 'Native scores do not match the opposing Teams.')
        values[row['team_id']] = tuple(integer(row[key], 0, 2**53 - 1)
            for key in ('leaders', 'villages', 'unit_value_hp', 'gold'))
    first, second = team_ids
    if values[first] != values[second]:
        return (first if values[first] > values[second] else second), 'objective_score'
    roll = hmac.new(seed.encode('ascii'), ('tie:' + match_id).encode(), 'sha256').digest()
    return team_ids[int.from_bytes(roll, 'big') % 2], 'recorded_draw'


def seeded_bracket(team_ids, seed):
    """Frozen unbiased shuffle and balanced byes, independent of entry ordering."""
    if (not isinstance(team_ids, list) or not 2 <= len(team_ids) <= 32
            or len(set(team_ids)) != len(team_ids)):
        fail('invalid_input', 'A knockout competition requires two to thirty-two Teams.')
    ordered = sorted(team_ids)
    counter = 0
    # Rejection sampling avoids modulo bias, unlike sorting truncated PRNG keys.
    for index in range(len(ordered) - 1, 0, -1):
        bound = index + 1
        ceiling = 2**256 - 2**256 % bound
        while True:
            block = hmac.new(seed.encode('ascii'), f'bracket:{counter}'.encode(), 'sha256').digest()
            counter += 1
            number = int.from_bytes(block, 'big')
            if number < ceiling:
                break
        other = number % bound
        ordered[index], ordered[other] = ordered[other], ordered[index]
    size = 1 << (len(ordered) - 1).bit_length()
    byes = size - len(ordered)
    result = [[team, None] for team in ordered[:byes]]
    remaining = ordered[byes:]
    result += [remaining[i:i + 2] for i in range(0, len(remaining), 2)]
    return result


class BattleMixin:
    def _battle_team_touch(self, team_id, session):
        team = self._team(team_id, session)
        self.db.court_teams.update_one({'_id': team_id}, {'$inc': {'revision': 1}}, session=session)
        return team

    def _battle_castle(self, castle_id, session, role=None):
        row = self.db.court_castles.find_one({'_id': identifier(castle_id, 'castle')}, session=session)
        if row is None:
            fail('not_found', 'This Castle is unavailable.')
        if role and row['role'] != role:
            fail('invalid_castle', 'Choose the correct Castle type for this action.')
        area = self.db.court_areas.find_one({'_id': row['area_id']}, session=session)
        if not row.get('enabled') or not area or not area.get('enabled'):
            fail('area_unavailable', 'This location is not active.')
        return row

    def _battle_match(self, match_id, session=None):
        row = self.db.court_matches.find_one({'_id': identifier(match_id)}, session=session)
        if row is None:
            fail('not_found', 'This battle is unavailable.')
        return row

    def _battle_selection(self, actor, hero_id, form_id, faction, cap, session):
        account = self._actor(actor, session)
        if any(not isinstance(value, str) or not 1 <= len(value) <= 160
               for value in (hero_id, form_id, faction)):
            fail('invalid_input', 'Choose an available hero, form and faction.')
        if faction not in FACTIONS:
            fail('invalid_input', 'Choose a supported recruitment faction.')
        row = self.db.account_heroes.find_one({'account_id': actor, 'hero_id': hero_id}, session=session)
        if row is None or form_id not in row.get('forms', []):
            fail('hero_locked', 'Choose an owned hero and an available form.')
        try:
            _, form = catalog_form(hero_id, form_id)
        except (ValueError, TypeError):
            fail('hero_locked', 'Choose an available hero form.')
        level = hero_progress(row['total_experience'])['hero_level']
        return dict(hero_id=hero_id, form_id=form_id, unit_type=form['unit_type'],
            native_level=form['native_level'], collection_level=level, hero_level=min(level, cap),
            hero_revision=row['revision'], faction=faction, owner_id=actor,
            username=account['username'])

    def _battle_membership(self, actor, match, session):
        self._actor(actor, session)
        team = self._team_for(actor, session)
        if team['_id'] not in match['team_ids'] or team['area_id'] != match['area_id']:
            fail('forbidden', 'This battle belongs to another Team or Area.')
        return team

    def _battle_can_view(self, actor, match, session):
        self._actor(actor, session)
        if actor in match.get('historical_accounts', []):
            return True
        team = self._team_for(actor, session, required=False)
        return bool(team and (team['area_id'] == match['area_id']
                              or team['_id'] in match['team_ids']))

    def _court_match_public(self, match, actor=None, session=None):
        names = {}
        for team_id in match['team_ids']:
            team = self.db.court_teams.find_one({'_id': team_id}, {'name': 1}, session=session)
            names[team_id] = team['name'] if team else 'Castle garrison'
        result = {key: deepcopy(match[key]) for key in (
            'kind', 'state', 'revision', 'castle_id', 'area_id', 'team_ids', 'settings',
            'created_at', 'scheduled_at', 'response_until', 'attendance_until',
            'prepare_until', 'result', 'competition_id', 'round', 'cancel_reason',
            'proposed_by', 'initiator_team_id', 'approved_by', 'start_delay_minutes',
            'expires_at', 'agreed_fee', 'price_revision', 'attack_cost') if key in match}
        result.update(id=match['_id'], team_names=names,
            deadline=match.get('response_until') or match.get('attendance_until') or match.get('prepare_until'),
            required_size=match['settings']['size'], seats=[{
                'side': row['side'], 'team_id': row['team_id'], 'account_id': row.get('account_id'),
                'username': row.get('username', ''), 'ready': row.get('ready', False),
                'hero': deepcopy(row.get('selection')), 'controller': row.get('controller', 'human'),
                'item_id': row.get('item_id', ''),
            } for row in match['seats']])
        receipt = match.get('result') or {}
        team = self._team_for(actor, session, required=False) if actor else None
        authorized = bool(actor and (actor in match.get('historical_accounts', []) or
                                    (team and team['_id'] in match['team_ids'])))
        result['replay_available'] = bool(authorized and receipt.get('native_verified') and receipt.get('replay_sha256'))
        result['run_id'] = match['_id']
        if match.get('descriptor') and actor in match['descriptor']['required_humans']:
            result['can_enter'] = match['state'] in ('preparing', 'running', 'paused')
        else:
            result['can_enter'] = False
        return result

    def _court_matches_query(self, actor, payload, session=None):
        exact(payload, (), ('castle_id', 'area_id', 'team_id', 'after', 'state'))
        self._actor(actor, session)
        team = self._team_for(actor, session, required=False)
        if payload.get('state') == 'history':
            clauses = [{'historical_accounts': actor}]
            if team:
                clauses.append({'team_ids': team['_id']})
            query = {'$or': clauses}
        else:
            if not team:
                fail('team_required', 'Join a Team to browse active battles.')
            query = {'area_id': team['area_id']}
        if payload.get('area_id'):
            query['area_id'] = identifier(payload['area_id'], 'area')
        if payload.get('castle_id'):
            if payload.get('state') == 'history':
                castle = self.db.court_castles.find_one({'_id': identifier(payload['castle_id'], 'castle')}, session=session)
                if castle is None:
                    fail('not_found', 'This Castle is unavailable.')
            else:
                castle = self._battle_castle(payload['castle_id'], session)
            query.update(castle_id=castle['_id'], area_id=castle['area_id'])
        if payload.get('team_id'):
            selected = self._team(identifier(payload['team_id']), session)
            query['area_id'] = selected['area_id']
            query['team_ids'] = selected['_id']
        if payload.get('after'):
            query['_id'] = {'$gt': identifier(payload['after'])}
        if payload.get('state'):
            if payload['state'] == 'history':
                query['state'] = {'$in': list(TERMINAL_STATES)}
            elif payload['state'] == 'active':
                query['state'] = {'$in': list(ACTIVE_STATES)}
            else:
                fail('invalid_input', 'Choose Active or History.')
        rows = list(self.db.court_matches.find(query, session=session).sort('_id', 1).limit(21))
        return {'matches': [self._court_match_public(row, actor, session) for row in rows[:20]],
                'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def _court_history_matches(self, actor, after='', session=None):
        return self._court_matches_query(actor, {'state': 'history', **({'after': after} if after else {})}, session)

    def _new_match(self, kind, castle, teams, battle_settings, session):
        now = self._now()
        match = dict(_id=str(uuid4()), generation=str(uuid4()), database_generation=self._generation(session), kind=kind, state='scheduled',
            revision=0, castle_id=castle['_id'], area_id=castle['area_id'],
            team_ids=list(teams), settings=deepcopy(battle_settings), seats=[],
            created_at=now, scheduled_at=now, historical_accounts=[], holds=[],
            quota_holds=[], has_started=False, loaded_humans=[], worker_loaded=False)
        groups = BATTLE_MAPS[battle_settings['map_id']]['sides']
        for team_id, sides in zip(teams, groups):
            if not team_id.startswith('garrison:'):
                match['historical_accounts'].append(self._battle_team_touch(team_id, session)['captain_id'])
            for side in sides:
                match['seats'].append(dict(side=side, team_id=team_id, account_id=None,
                    username='', selection=None, ready=False, controller='human'))
        return match

    def _court_admin_cancel_match(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        reason = self._competition_admin_review(payload)
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        if match['state'] in TERMINAL_STATES:
            fail('battle_locked', 'This battle is already final.')
        before = {'state': match['state'], 'revision': match['revision']}
        self._battle_cancel(match, 'administrator_technical_cancellation', session, technical=True)
        replacement = None
        if match['kind'] == 'competition':
            competition = self._competition(match['competition_id'], session)
            if competition['state'] not in ('round_ready', 'playing') or competition['round'] != match['round']:
                fail('invalid_state', 'This competition round is no longer active.')
            entry = next((entry for entry in competition['rounds'][-1]['matches']
                          if entry['match_id'] == match['_id']), None)
            if entry is None or entry['state'] == 'completed':
                fail('invalid_state', 'This matchup is already final.')
            castle = self.db.court_castles.find_one({'_id': match['castle_id']}, session=session)
            replacement = self._new_match('competition', castle, match['team_ids'], match['settings'], session)
            replacement.update(state='scheduled', scheduled_at=None, competition_id=competition['_id'],
                               round=match['round'], tie_seed=competition['seed'], replaces_match_id=match['_id'])
            self.db.court_matches.insert_one(replacement, session=session)
            entry.setdefault('cancelled_match_ids', []).append(match['_id'])
            entry.update(match_id=replacement['_id'], state='scheduled', winner_team_id=None)
            competition['revision'] += 1
            self.db.court_competitions.replace_one({'_id': competition['_id']}, competition, session=session)
            self._battle_notify(replacement, 'Competition matchup replaced',
                                'Fresh seats and readiness are required when the administrator reschedules.', session)
        self._audit(actor, 'court_cancel_match', match['_id'], reason, before,
                    {'state': match['state'], 'revision': match['revision'],
                     'replacement_id': replacement['_id'] if replacement else None}, session)
        return {'match': self._court_match_public(match, actor, session),
                'replacement_match_id': replacement['_id'] if replacement else None}

    def _battle_save(self, match, session, *, increment=True):
        if increment:
            match['revision'] += 1
        self.db.court_matches.replace_one({'_id': match['_id']}, match, session=session)

    def _battle_notify(self, match, title, message, session):
        recipients = set(match.get('historical_accounts', []))
        for team in self.db.court_teams.find({'_id': {'$in': match['team_ids']}}, session=session):
            recipients.update(member['account_id'] for member in team['members'])
        self._notify(recipients, 'battle', title, message,
            {'area_id': match['area_id'], 'castle_id': match['castle_id'], 'match_id': match['_id']}, session)

    def _battle_claim_seat(self, actor, match, team_id, session):
        # Membership edits and joining a match must conflict on a shared Team
        # write, not merely inspect each other's snapshot of the seat registry.
        self._battle_team_touch(team_id, session)
        existing = self.db.court_seats.find_one({'_id': actor}, session=session)
        if existing and existing['match_id'] != match['_id']:
            fail('already_joined', 'Leave your other planned battle before joining this one.')
        seat = next((row for row in match['seats'] if row.get('account_id') == actor), None)
        if seat:
            return seat
        seat = next((row for row in match['seats'] if row['team_id'] == team_id
                     and not row.get('account_id') and row['controller'] == 'human'), None)
        if seat is None:
            fail('capacity', 'Your Team has no empty seats in this battle.')
        account = self._actor(actor, session)
        self.db.court_seats.replace_one({'_id': actor}, {'_id': actor,
            'match_id': match['_id'], 'team_id': team_id, 'created_at': self._now()}, upsert=True, session=session)
        seat.update(account_id=actor, username=account['username'], selection=None, ready=False)
        match['historical_accounts'] = sorted(set(match['historical_accounts'] + [actor]))
        return seat

    def _battle_clear_readiness(self, match):
        for seat in match['seats']:
            if seat['controller'] == 'human':
                seat['ready'] = False

    def _battle_attack_budget(self, actor, team, amount, match_id, session, approval_id=None):
        if actor == team['captain_id']:
            return None
        day = self._now().date().isoformat()
        key = f'{team["_id"]}:{actor}:{day}'
        row = self.db.court_attack_budgets.find_one({'_id': key}, session=session)
        if row is None:
            row = dict(_id=key, team_id=team['_id'], account_id=actor, day=day, used=0, held=0)
            self.db.court_attack_budgets.insert_one(row, session=session)
        allowance = team.get('allowances', {}).get(actor, self._settings(session)['limits']['member_allowance'])
        if row['used'] + row['held'] + amount > allowance:
            approved = self.db.court_attack_approvals.find_one({'_id': approval_id,
                'team_id': team['_id'], 'account_id': actor, 'amount': amount,
                'state': 'approved', 'expires_at': {'$gt': self._now()}}, session=session) if approval_id else None
            if approved is None:
                fail('allowance_exceeded', 'Request captain approval or a larger daily attack allowance.')
            self.db.court_attack_approvals.update_one({'_id': approval_id},
                {'$set': {'state': 'used', 'match_id': match_id}, '$inc': {'revision': 1}}, session=session)
        self.db.court_attack_budgets.update_one({'_id': key}, {'$inc': {'held': amount}}, session=session)
        return key

    def _court_request_attack_approval(self, actor, payload, session):
        exact(payload, ('castle_id', 'price_revision'))
        rule = self._price_revision(payload, session)
        team = self._team_for(actor, session)
        castle = self._battle_castle(payload['castle_id'], session, 'normal')
        if team['area_id'] != castle['area_id'] or castle.get('owner_team_id') == team['_id']:
            fail('forbidden', 'Choose an opposing or neutral home-Area Castle.')
        amount = rule['prices']['attack_owned' if castle.get('owner_team_id') else 'attack_neutral']
        existing = self.db.court_attack_approvals.find_one({'team_id': team['_id'], 'account_id': actor,
            'castle_id': castle['_id'], 'state': {'$in': ['pending', 'approved']},
            'expires_at': {'$gt': self._now()}}, session=session)
        if existing:
            return {'approval': public(existing)}
        row = dict(_id=str(uuid4()), team_id=team['_id'], account_id=actor,
            castle_id=castle['_id'], amount=amount, state='pending', revision=0,
            expires_at=self._now() + timedelta(minutes=10))
        self.db.court_attack_approvals.insert_one(row, session=session)
        self._notify(team['captain_id'], 'approval', 'Attack approval requested',
            'Review this member’s Castle attack cost.', {'approval_id': row['_id']}, session)
        return {'approval': public(row)}

    def _court_approve_attack(self, actor, payload, session):
        exact(payload, ('approval_id', 'expected_revision', 'approved'))
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        row = self.db.court_attack_approvals.find_one({'_id': identifier(payload['approval_id']),
            'team_id': team['_id']}, session=session)
        if row is None or row['state'] != 'pending' or row['expires_at'] <= self._now():
            fail('invalid_state', 'This approval request is no longer pending.')
        revision(row, payload['expected_revision'])
        if type(payload['approved']) is not bool:
            fail('invalid_input', 'Choose approve or reject.')
        row.update(state='approved' if payload['approved'] else 'rejected', revision=row['revision'] + 1)
        self.db.court_attack_approvals.replace_one({'_id': row['_id']}, row, session=session)
        self._notify(row['account_id'], 'approval', 'Attack request reviewed', row['state'],
            {'castle_id': row['castle_id'], 'approval_id': row['_id']}, session)
        return {'approval': public(row)}

    def _court_attack(self, actor, payload, session):
        exact(payload, ('castle_id', 'expected_revision', 'hero_id', 'form_id', 'faction',
                        'price_revision'), ('approval_id',))
        rule = self._price_revision(payload, session)
        team = self._team_for(actor, session)
        castle = self._battle_castle(payload['castle_id'], session, 'normal')
        revision(castle, payload['expected_revision'])
        if castle['area_id'] != team['area_id'] or castle.get('owner_team_id') == team['_id']:
            fail('forbidden', 'Attack an opposing or neutral Castle in your home Area.')
        if castle.get('protected_until') and castle['protected_until'] > self._now():
            fail('protected', 'This Castle is protected until its countdown ends.')
        if castle.get('reservation_id') or self.db.court_castle_claims.find_one({'castle_id': castle['_id']}, session=session):
            fail('castle_busy', 'This Castle already has a committed contest.')
        if self.db.court_matches.find_one({'proposed_by': actor, 'kind': 'attack',
                'cancelled_at': {'$gt': self._now() - timedelta(seconds=rule['limits']['voluntary_cancel_seconds'])},
                'cancel_reason': 'participant_cancelled'}, session=session):
            fail('cooldown', 'Wait briefly before starting another Castle challenge.')
        self._battle_team_touch(team['_id'], session)
        occupied = self.db.court_castles.count_documents({'owner_team_id': team['_id']}, session=session)
        pending = self.db.court_castle_claims.count_documents({'team_id': team['_id']}, session=session)
        if occupied + pending >= rule['limits']['castles_per_team']:
            fail('castle_capacity', 'Abandon a holding before claiming another Castle.')
        battle_settings = deepcopy(DEFAULT_BATTLE_SETTINGS)
        battle_settings['items'] = True
        battle_settings['hero_cap'] = min(30, rule['limits']['hero_level_cap'])
        defending = castle.get('owner_team_id') or 'garrison:' + castle['_id']
        match = self._new_match('attack', castle, [team['_id'], defending], battle_settings, session)
        match.update(proposed_by=actor, initiator_team_id=team['_id'],
            original_owner=castle.get('owner_team_id'), state='response',
            response_until=self._now() + timedelta(seconds=rule['limits']['defender_response_seconds']),
            defense_template=self._battle_defense(castle.get('owner_team_id'), session))
        seat = self._battle_claim_seat(actor, match, team['_id'], session)
        seat['selection'] = self._battle_selection(actor, payload['hero_id'], payload['form_id'],
            payload['faction'], battle_settings['hero_cap'], session)
        seat['ready'] = True
        amount = rule['prices']['attack_owned' if castle.get('owner_team_id') else 'attack_neutral']
        if payload.get('approval_id'):
            approval = self.db.court_attack_approvals.find_one({'_id': identifier(payload['approval_id'])}, session=session)
            if approval is None or approval['castle_id'] != castle['_id']:
                fail('forbidden', 'The approval is for a different Castle.')
        match['attack_budget'] = self._battle_attack_budget(actor, team, amount, match['_id'], session, payload.get('approval_id'))
        match['attack_cost'] = amount
        hold = 'attack:' + match['_id']
        self._wallet_hold('team', team['_id'], amount, hold, 'castle_attack', session)
        self._quota_reserve('attack', actor, hold, session)
        match['holds'] = [hold]
        match['quota_holds'] = [hold]
        self.db.court_castle_claims.insert_one(dict(_id=match['_id'], match_id=match['_id'],
            castle_id=castle['_id'], team_id=team['_id'], created_at=self._now()), session=session)
        self.db.court_castles.update_one({'_id': castle['_id']},
            {'$set': {'reservation_id': match['_id']}, '$inc': {'revision': 1}}, session=session)
        if not castle.get('owner_team_id'):
            self._battle_use_ai(match)
        self.db.court_matches.insert_one(match, session=session)
        self._battle_notify(match, 'Castle challenged', 'A human defender may answer before the AI defense begins.', session)
        return {'match': self._court_match_public(match, actor, session)}

    def _battle_defense(self, team_id, session):
        if team_id:
            team = self._battle_team_touch(team_id, session)
            row = self.db.court_defenses.find_one({'_id': team.get('defense_id'),
                'team_id': team_id, 'status': 'approved'}, session=session)
            if row and row['owner_id'] in {member['account_id'] for member in team['members']}:
                account = self.db.accounts.find_one({'_id': row['owner_id'], 'status': 'active'}, session=session)
                if account:
                    return {'selection': deepcopy(row['selection']), 'defense_id': row['_id'],
                            'revision': row['revision'], 'kind': 'consented_template'}
        return {'kind': 'standard_garrison', 'selection': None,
                'leader_type': 'Lieutenant', 'faction': 'Loyalists'}

    def _battle_use_ai(self, match):
        defender = match['seats'][1]
        defender.update(account_id=None, username='Castle defense', controller='worker', ready=True,
            selection=deepcopy(match['defense_template'].get('selection')))
        match['state'] = 'queued'
        match['queued_at'] = self._now()
        match.pop('response_until', None)

    def _court_defend(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'hero_id', 'form_id', 'faction'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        team = self._battle_membership(actor, match, session)
        if (match['kind'] != 'attack' or match['state'] != 'response'
                or match['response_until'] <= self._now() or team['_id'] != match['original_owner']):
            fail('invalid_state', 'This Castle is not awaiting your Team’s human defender.')
        seat = self._battle_claim_seat(actor, match, team['_id'], session)
        seat['selection'] = self._battle_selection(actor, payload['hero_id'], payload['form_id'],
            payload['faction'], match['settings']['hero_cap'], session)
        seat['ready'] = True
        match.update(state='queued', queued_at=self._now())
        match.pop('response_until', None)
        self._battle_save(match, session)
        self._battle_notify(match, 'Human defense accepted', 'The battle is waiting for a native worker.', session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_cancel_attack(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        if match['kind'] != 'attack' or match['proposed_by'] != actor:
            fail('forbidden', 'Only the challenger can cancel this attack.')
        if match['state'] not in ('response', 'queued'):
            fail('battle_locked', 'This battle has already entered preparation.')
        self._battle_cancel(match, 'participant_cancelled', session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_defense_consent(self, actor, payload, session):
        exact(payload, ('hero_id', 'form_id', 'faction', 'confirmed'))
        if payload['confirmed'] is not True:
            fail('confirmation_required', 'Confirm the saved-template defense permission.')
        team = self._team_for(actor, session)
        selection = self._battle_selection(actor, payload['hero_id'], payload['form_id'],
            payload['faction'], min(30, self._settings(session)['limits']['hero_level_cap']), session)
        row = dict(_id=str(uuid4()), team_id=team['_id'], owner_id=actor, selection=selection,
            status='offered', revision=0, created_at=self._now())
        self.db.court_defenses.insert_one(row, session=session)
        self._notify(team['captain_id'], 'defense', 'Defense template offered',
            'Review the owner’s saved hero and recruitment faction.', {'defense_id': row['_id']}, session)
        return {'defense': public(row)}

    def _court_set_defense(self, actor, payload, session):
        exact(payload, ('defense_id', 'expected_revision', 'confirmed'))
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        row = self.db.court_defenses.find_one({'_id': identifier(payload['defense_id']),
            'team_id': team['_id'], 'status': {'$in': ['offered', 'approved']}}, session=session)
        if row is None or row['owner_id'] not in {member['account_id'] for member in team['members']}:
            fail('invalid_state', 'This defense offer is unavailable.')
        revision(row, payload['expected_revision'])
        self._actor(row['owner_id'], session)
        if payload['confirmed'] is not True:
            fail('confirmation_required', 'Confirm the Team’s saved defense template.')
        row.update(status='approved', approved_by=actor, approved_at=self._now(), revision=row['revision'] + 1)
        self.db.court_defenses.replace_one({'_id': row['_id']}, row, session=session)
        self.db.court_teams.update_one({'_id': team['_id']},
            {'$set': {'defense_id': row['_id']}, '$inc': {'revision': 1}}, session=session)
        self._history(team['_id'], 'defense', 'Defense template approved', {'defense_id': row['_id']}, session)
        return {'defense': public(row)}

    def _court_withdraw_defense(self, actor, payload, session):
        exact(payload, ('defense_id', 'expected_revision'))
        row = self.db.court_defenses.find_one({'_id': identifier(payload['defense_id'])}, session=session)
        if row is None or row['owner_id'] != actor:
            fail('forbidden', 'Only the owner can withdraw this hero template.')
        revision(row, payload['expected_revision'])
        row.update(status='withdrawn', withdrawn_at=self._now(), revision=row['revision'] + 1)
        self.db.court_defenses.replace_one({'_id': row['_id']}, row, session=session)
        self.db.court_teams.update_one({'_id': row['team_id'], 'defense_id': row['_id']},
            {'$unset': {'defense_id': ''}, '$inc': {'revision': 1}}, session=session)
        return {'defense': public(row), 'committed_matches_unchanged': True,
                'future_defense': 'standard_garrison'}

    def _court_create_plan(self, actor, payload, session):
        exact(payload, ('castle_id', 'opponent_team_id', 'settings', 'start_delay_minutes', 'price_revision'))
        rule = self._price_revision(payload, session)
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        other = self._team(identifier(payload['opponent_team_id']), session)
        castle = self._battle_castle(payload['castle_id'], session, 'plan')
        if other['_id'] == team['_id'] or any(t['area_id'] != castle['area_id'] for t in (team, other)):
            fail('invalid_opponent', 'Choose a different Team in your home Area.')
        delay = integer(payload['start_delay_minutes'], 5, 100)
        if delay not in (5, 15, 30, 60, 100):
            fail('invalid_input', 'Choose one of the starting-time presets.')
        if self.db.court_matches.count_documents({'kind': 'plan', 'initiator_team_id': team['_id'],
                'state': 'proposed'}, session=session) >= 5:
            fail('capacity', 'Review or cancel your pending proposals first.')
        match = self._new_match('plan', castle, [team['_id'], other['_id']], settings(payload['settings']), session)
        match.update(state='proposed', proposed_by=actor, initiator_team_id=team['_id'],
            approved_by=[actor], start_delay_minutes=delay,
            expires_at=self._now() + timedelta(seconds=rule['limits']['proposal_seconds']),
            agreed_fee=rule['prices']['plan'], price_revision=rule['revision'])
        hold = 'plan:' + match['_id'] + ':' + team['_id']
        self._wallet_hold('team', team['_id'], match['agreed_fee'], hold, 'planned_battle', session)
        match['holds'].append(hold)
        match['historical_accounts'] = sorted({actor, other['captain_id']})
        self.db.court_matches.insert_one(match, session=session)
        self._notify(other['captain_id'], 'proposal', 'Battle proposed',
            team['name'] + ' proposes a scheduled match.', {'match_id': match['_id'], 'castle_id': castle['_id']}, session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_approve_plan(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'price_revision'))
        self._price_revision(payload, session)
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        team = self._battle_membership(actor, match, session)
        self._captain(actor, team, session)
        if (match['kind'] != 'plan' or match['state'] != 'proposed'
                or match['expires_at'] <= self._now() or team['_id'] == match['initiator_team_id']):
            fail('invalid_state', 'This proposal is not awaiting your approval.')
        initiator = self._team(match['initiator_team_id'], session)
        if initiator['captain_id'] != match['proposed_by']:
            fail('stale_revision', 'The proposing captain changed. Request a new proposal.')
        self._battle_team_touch(team['_id'], session)
        self._battle_team_touch(initiator['_id'], session)
        hold = 'plan:' + match['_id'] + ':' + team['_id']
        self._wallet_hold('team', team['_id'], match['agreed_fee'], hold, 'planned_battle', session)
        quota = 'plan:' + match['_id']
        self._quota_reserve('plan', initiator['_id'], quota, session)
        self._quota_commit(quota, session)
        match['holds'].append(hold)
        match['quota_holds'].append(quota)
        match.update(state='scheduled', approved_by=[initiator['captain_id'], actor],
            scheduled_at=self._now() + timedelta(minutes=match['start_delay_minutes']))
        self._battle_save(match, session)
        self._battle_notify(match, 'Battle scheduled', 'Your captain approved the rules. Join an available seat.', session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_cancel_plan(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        team = self._battle_membership(actor, match, session)
        self._captain(actor, team, session)
        if match['kind'] != 'plan' or match['state'] not in ('proposed', 'scheduled', 'queued'):
            fail('battle_locked', 'This plan can no longer be cancelled by its captain.')
        self._battle_cancel(match, 'participant_cancelled', session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_join_match(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        team = self._battle_membership(actor, match, session)
        if match['kind'] == 'attack' or match['state'] not in ('scheduled', 'queued'):
            fail('battle_locked', 'Join an accepted, upcoming Plan or Competition match.')
        self._battle_claim_seat(actor, match, team['_id'], session)
        self._battle_clear_readiness(match)
        self._battle_save(match, session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_leave_match(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        if match['kind'] == 'attack' or match['state'] not in ('scheduled', 'queued'):
            fail('battle_locked', 'A prepared battle lineup cannot be changed.')
        seat = next((row for row in match['seats'] if row.get('account_id') == actor), None)
        if seat is None:
            fail('not_joined', 'You have no seat in this battle.')
        seat.update(account_id=None, username='', selection=None, ready=False)
        self.db.court_seats.delete_one({'_id': actor, 'match_id': match['_id']}, session=session)
        self._battle_clear_readiness(match)
        self._battle_save(match, session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_select_hero(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'hero_id', 'form_id', 'faction'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        self._battle_membership(actor, match, session)
        if match['state'] not in ('scheduled', 'queued'):
            fail('battle_locked', 'Hero choices are frozen for this battle.')
        seat = next((row for row in match['seats'] if row.get('account_id') == actor), None)
        if seat is None:
            fail('not_joined', 'Join a seat before choosing your hero.')
        seat['selection'] = self._battle_selection(actor, payload['hero_id'], payload['form_id'],
            payload['faction'], match['settings']['hero_cap'], session)
        seat['ready'] = False
        self._battle_save(match, session)
        return {'match': self._court_match_public(match, actor, session)}

    def _court_ready(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'ready'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        self._battle_membership(actor, match, session)
        if match['state'] not in ('scheduled', 'queued') or type(payload['ready']) is not bool:
            fail('battle_locked', 'Readiness can only change before preparation.')
        seat = next((row for row in match['seats'] if row.get('account_id') == actor), None)
        if seat is None or seat['selection'] is None:
            fail('hero_required', 'Join and choose an owned hero first.')
        current = self._battle_selection(actor, seat['selection']['hero_id'], seat['selection']['form_id'],
            seat['selection']['faction'], match['settings']['hero_cap'], session)
        if current != seat['selection']:
            fail('stale_hero', 'Your hero changed. Select it again before Ready.')
        seat['ready'] = payload['ready']
        self._battle_save(match, session)
        return {'match': self._court_match_public(match, actor, session)}

    def _competition(self, competition_id, session=None):
        row = self.db.court_competitions.find_one({'_id': identifier(competition_id)}, session=session)
        if row is None:
            fail('not_found', 'This competition is unavailable.')
        return row

    def _competition_public(self, row):
        result = {key: deepcopy(row[key]) for key in ('name', 'castle_id', 'area_id', 'state',
            'revision', 'settings', 'entry_fee', 'entries', 'round', 'rounds', 'created_at',
            'seed_commitment', 'revealed_seed', 'winner_team_id', 'runner_up_team_id',
            'prizes', 'cancel_reason') if key in row}
        result['id'] = row['_id']
        result['entries'] = [{key: entry[key] for key in ('team_id', 'team_name')}
                             for entry in row['entries']]
        result['tie_break'] = ['Surviving leaders', 'Villages', 'Surviving unit value weighted by HP',
                              'Tactical treasury', 'Committed random draw']
        return result

    def _court_competitions_query(self, actor, payload, session=None):
        exact(payload, (), ('castle_id', 'competition_id', 'after'))
        self._actor(actor, session)
        self._team_for(actor, session)
        if payload.get('competition_id'):
            return {'competition': self._competition_public(self._competition(payload['competition_id'], session))}
        query = {}
        if payload.get('castle_id'):
            query['castle_id'] = self._battle_castle(payload['castle_id'], session, 'competition')['_id']
        if payload.get('after'):
            query['_id'] = {'$gt': identifier(payload['after'])}
        rows = list(self.db.court_competitions.find(query, session=session).sort('_id', 1).limit(21))
        return {'competitions': [self._competition_public(row) for row in rows[:20]],
                'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def _court_admin_create_competition(self, actor, payload, session):
        exact(payload, ('castle_id', 'expected_revision', 'name', 'settings', 'entry_fee', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        reason = self._competition_admin_review(payload)
        castle = self._battle_castle(payload['castle_id'], session, 'competition')
        revision(castle, payload['expected_revision'])
        if castle.get('event_id'):
            fail('castle_busy', 'Finish or cancel the current competition first.')
        seed = secrets.token_hex(32)
        row = dict(_id=str(uuid4()), name=text(payload['name'], 'Competition name', 64),
            castle_id=castle['_id'], area_id=castle['area_id'], state='registration', revision=0,
            settings=settings(payload['settings']), entry_fee=integer(payload['entry_fee'], 0, 1000000),
            entries=[], round=0, rounds=[], created_at=self._now(), created_by=actor,
            seed=seed, seed_commitment=sha256(seed.encode()).hexdigest())
        self.db.court_competitions.insert_one(row, session=session)
        self.db.court_castles.update_one({'_id': castle['_id']},
            {'$set': {'event_id': row['_id']}, '$inc': {'revision': 1}}, session=session)
        self._audit(actor, 'court_competition_create', row['_id'], reason, None,
                    self._competition_public(row), session)
        return {'competition': self._competition_public(row)}

    @staticmethod
    def _competition_admin_review(payload):
        if payload.get('confirmation') != 'confirmed':
            fail('confirmation_required', 'Review and confirm this competition action.')
        return text(payload['reason'], 'Reason', 500)

    def _court_enter_competition(self, actor, payload, session):
        exact(payload, ('competition_id', 'expected_revision', 'price_revision'))
        self._price_revision(payload, session)
        row = self._competition(payload['competition_id'], session)
        revision(row, payload['expected_revision'])
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        if row['state'] != 'registration' or row['area_id'] != team['area_id']:
            fail('battle_locked', 'Enter an open competition in your home Area.')
        if any(entry['team_id'] == team['_id'] for entry in row['entries']):
            return {'competition': self._competition_public(row)}
        if len(row['entries']) >= self._settings(session)['limits']['tournament_max_teams']:
            fail('capacity', 'This competition is full.')
        self._battle_team_touch(team['_id'], session)
        hold = 'competition:' + row['_id'] + ':' + team['_id']
        self._wallet_hold('team', team['_id'], row['entry_fee'], hold, 'competition_entry', session)
        row['entries'].append(dict(team_id=team['_id'], team_name=team['name'],
            captain_id=actor, hold_id=hold, joined_at=self._now()))
        row['revision'] += 1
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
        self._team_notice(team, 'competition', 'Competition entered', row['name'],
            {'competition_id': row['_id'], 'castle_id': row['castle_id']}, session)
        return {'competition': self._competition_public(row)}

    def _court_leave_competition(self, actor, payload, session):
        exact(payload, ('competition_id', 'expected_revision'))
        row = self._competition(payload['competition_id'], session)
        revision(row, payload['expected_revision'])
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        if row['state'] != 'registration':
            fail('battle_locked', 'The bracket is already locked.')
        entry = next((entry for entry in row['entries'] if entry['team_id'] == team['_id']), None)
        if entry is None:
            fail('not_found', 'Your Team has not entered this competition.')
        self._battle_team_touch(team['_id'], session)
        self._wallet_release(entry['hold_id'], session)
        row['entries'].remove(entry)
        row['revision'] += 1
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
        return {'competition': self._competition_public(row)}

    def _competition_round(self, row, pairs, session):
        castle = self._battle_castle(row['castle_id'], session, 'competition')
        matches = []
        for pair in pairs:
            if len(pair) != 2 or pair[1] is None:
                matches.append(dict(match_id=None, team_ids=[pair[0]], winner_team_id=pair[0],
                                    state='completed', bye=True))
                continue
            match = self._new_match('competition', castle, pair, row['settings'], session)
            match.update(state='scheduled', scheduled_at=None, competition_id=row['_id'],
                         round=row['round'], tie_seed=row['seed'])
            for team_id in pair:
                team = self._battle_team_touch(team_id, session)
                match['historical_accounts'].append(team['captain_id'])
            self.db.court_matches.insert_one(match, session=session)
            matches.append(dict(match_id=match['_id'], team_ids=pair,
                                winner_team_id=None, state='scheduled', bye=False))
            self._battle_notify(match, 'Competition matchup', row['name'], session)
        row['rounds'].append(dict(number=row['round'], state='ready', matches=matches))

    def _court_admin_lock_competition(self, actor, payload, session):
        exact(payload, ('competition_id', 'expected_revision', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        reason = self._competition_admin_review(payload)
        row = self._competition(payload['competition_id'], session)
        revision(row, payload['expected_revision'])
        if row['state'] != 'registration' or len(row['entries']) < 2:
            fail('invalid_state', 'At least two registered Teams are needed to lock the bracket.')
        pairs = seeded_bracket([entry['team_id'] for entry in row['entries']], row['seed'])
        for entry in row['entries']:
            self._battle_team_touch(entry['team_id'], session)
            self._wallet_capture(entry['hold_id'], session)
        row.update(state='round_ready', round=1, revealed_seed=row['seed'], locked_at=self._now())
        self._competition_round(row, pairs, session)
        row['revision'] += 1
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
        self._audit(actor, 'court_competition_lock', row['_id'], reason,
                    {'state': 'registration'}, self._competition_public(row), session)
        return {'competition': self._competition_public(row)}

    def _court_admin_start_round(self, actor, payload, session):
        exact(payload, ('competition_id', 'expected_revision', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        reason = self._competition_admin_review(payload)
        row = self._competition(payload['competition_id'], session)
        revision(row, payload['expected_revision'])
        if row['state'] not in ('round_ready', 'playing'):
            fail('invalid_state', 'The previous round has not finished.')
        current = row['rounds'][-1]
        before_state = row['state']
        if row['state'] == 'playing' and not any(item['state'] == 'scheduled' for item in current['matches']):
            fail('invalid_state', 'There are no replacement matches awaiting a new start.')
        if current['state'] == 'completed':
            winners = [item['winner_team_id'] for item in current['matches'] if item['winner_team_id']]
            if len(winners) < 2:
                fail('invalid_state', 'No next round is available.')
            row['round'] += 1
            self._competition_round(row, [winners[i:i + 2] if i + 1 < len(winners)
                else [winners[i], None] for i in range(0, len(winners), 2)], session)
            current = row['rounds'][-1]
        now = self._now()
        for item in current['matches']:
            if item['match_id'] and item['state'] == 'scheduled':
                match = self._battle_match(item['match_id'], session)
                match.update(state='queued', scheduled_at=now, queued_at=now)
                self._battle_save(match, session)
                item['state'] = 'queued'
                self._battle_notify(match, 'Competition round opened',
                    'Join your matchup and choose Ready.', session)
        current['state'] = 'playing'
        row.update(state='playing', revision=row['revision'] + 1)
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
        self._audit(actor, 'court_competition_start_round', row['_id'], reason,
                    {'state': before_state}, self._competition_public(row), session)
        return {'competition': self._competition_public(row)}

    def _refund_hold(self, hold_id, reason, session):
        hold = self.db.court_holds.find_one({'_id': hold_id}, session=session)
        if hold and hold['state'] == 'held':
            self._wallet_release(hold_id, session)
        elif hold and hold['state'] == 'captured':
            self._wallet_refund(hold_id, reason, session)

    def _competition_cancel(self, row, reason, session):
        if row['state'] in ('completed', 'cancelled'):
            fail('battle_locked', 'This competition has already finished.')
        for match in self.db.court_matches.find({'competition_id': row['_id'],
                'state': {'$in': list(ACTIVE_STATES)}}, session=session):
            self._battle_cancel(match, reason, session, technical=True)
        for entry in row['entries']:
            self._battle_team_touch(entry['team_id'], session)
            self._refund_hold(entry['hold_id'], 'competition_cancelled', session)
            self._history(entry['team_id'], 'competition', 'Competition cancelled',
                {'competition_id': row['_id'], 'reason': reason}, session)
        row.update(state='cancelled', cancel_reason=reason, revision=row['revision'] + 1,
                   completed_at=self._now())
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
        self.db.court_castles.update_one({'_id': row['castle_id'], 'event_id': row['_id']},
            {'$set': {'event_id': None}, '$inc': {'revision': 1}}, session=session)

    def _court_admin_cancel_competition(self, actor, payload, session):
        exact(payload, ('competition_id', 'expected_revision', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        reason = self._competition_admin_review(payload)
        row = self._competition(payload['competition_id'], session)
        revision(row, payload['expected_revision'])
        before = self._competition_public(row)
        self._competition_cancel(row, reason, session)
        self._audit(actor, 'court_competition_cancel', row['_id'], reason,
                    before, self._competition_public(row), session)
        return {'competition': self._competition_public(row)}

    def _competition_result(self, match, winner, session):
        row = self._competition(match['competition_id'], session)
        if row['state'] in ('cancelled', 'completed'):
            fail('result_conflict', 'The competition has already finished.')
        current = row['rounds'][-1]
        item = next((item for item in current['matches'] if item['match_id'] == match['_id']), None)
        if item is None or item['state'] == 'completed':
            fail('result_conflict', 'The competition matchup does not match this result.')
        item.update(state='completed', winner_team_id=winner)
        if not all(item['state'] == 'completed' for item in current['matches']):
            row['revision'] += 1
            self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)
            return
        current['state'] = 'completed'
        winners = [item['winner_team_id'] for item in current['matches'] if item['winner_team_id']]
        if not winners:
            self._competition_cancel(row, 'no_surviving_team', session)
            return
        if len(winners) == 1:
            final = next(item for item in current['matches'] if item['winner_team_id'])
            runner = next((team for team in final['team_ids'] if team != winners[0]), None)
            # A real finalist must exist before redistributing the entry pool.
            if runner is None:
                self._competition_cancel(row, 'no_finalist', session)
                return
            pool = row['entry_fee'] * len(row['entries'])
            prizes = [(winners[0], pool * 70 // 100), (runner, pool - pool * 70 // 100)]
            for team_id, amount in prizes:
                self._battle_team_touch(team_id, session)
                self._wallet_credit('team', team_id, amount,
                    'competition-prize:' + row['_id'] + ':' + team_id, 'competition_prize', session)
            row.update(state='completed', winner_team_id=winners[0], runner_up_team_id=runner,
                prizes=[{'team_id': team, 'amount': amount} for team, amount in prizes], completed_at=self._now())
            self.db.court_castles.update_one({'_id': row['castle_id'], 'event_id': row['_id']},
                {'$set': {'event_id': None}, '$inc': {'revision': 1}}, session=session)
            for entry in row['entries']:
                self._history(entry['team_id'], 'competition', 'Competition completed',
                    {'competition_id': row['_id'], 'winner_team_id': winners[0], 'prizes': row['prizes']}, session)
        else:
            row['state'] = 'round_ready'
        row['revision'] += 1
        self.db.court_competitions.replace_one({'_id': row['_id']}, row, session=session)

    def _battle_release(self, match, session):
        self.db.court_seats.delete_many({'match_id': match['_id']}, session=session)
        self.db.network_battle_reservations.delete_many({'run_id': match['_id'],
            'generation': match['generation'], 'kind': 'court'}, session=session)
        self.db.court_castle_claims.delete_many({'match_id': match['_id']}, session=session)
        self.db.court_castles.update_one({'_id': match['castle_id'], 'reservation_id': match['_id']},
            {'$set': {'reservation_id': None}, '$inc': {'revision': 1}}, session=session)
        for seat in match['seats']:
            if seat.get('item_hold_id'):
                item = self.db.court_item_holds.find_one({'_id': seat['item_hold_id']}, session=session)
                if item and item['state'] == 'held':
                    self._inventory_release(seat['item_hold_id'], session)

    def _battle_cancel(self, match, reason, session, technical=False):
        if match['state'] in TERMINAL_STATES:
            return
        for team_id in match['team_ids']:
            if not team_id.startswith('garrison:'):
                self._battle_team_touch(team_id, session)
        for hold in match['holds']:
            self._refund_hold(hold, reason, session)
        for quota in match['quota_holds']:
            held = self.db.court_quota_holds.find_one({'_id': quota}, session=session)
            if held['state'] == 'reserved':
                self._quota_release(quota, session)
            elif technical and held['state'] == 'used':
                self._quota_release(quota, session, restore_used=True)
        if match.get('attack_budget'):
            field = 'used' if match['has_started'] else 'held'
            self.db.court_attack_budgets.update_one({'_id': match['attack_budget']},
                {'$inc': {field: -match['attack_cost']}}, session=session)
        self._battle_release(match, session)
        match.update(state='cancelled', cancel_reason=reason, cancelled_at=self._now())
        self._battle_save(match, session)
        for team_id in match['team_ids']:
            if not team_id.startswith('garrison:'):
                self._history(team_id, 'battle', 'Battle cancelled',
                    {'match_id': match['_id'], 'reason': reason}, session)
        self._battle_notify(match, 'Battle cancelled', reason.replace('_', ' '), session)
        if technical:
            for seat in match['seats']:
                if seat.get('item_hold_id'):
                    held = self.db.court_item_holds.find_one({'_id': seat['item_hold_id']}, session=session)
                    if held and held['state'] == 'consumed':
                        self._inventory_refund(held['_id'], reason, session)

    def _battle_ready_teams(self, match, session):
        ready_teams = set(match['team_ids'])
        for seat in match['seats']:
            if seat['controller'] != 'human':
                continue
            if not seat.get('account_id') or not seat.get('ready') or not seat.get('selection'):
                ready_teams.discard(seat['team_id'])
                continue
            team = self._team_for(seat['account_id'], session, required=False)
            if not team or team['_id'] != seat['team_id']:
                seat['ready'] = False
                ready_teams.discard(seat['team_id'])
                continue
            selected = seat['selection']
            try:
                current = self._battle_selection(seat['account_id'], selected['hero_id'],
                    selected['form_id'], selected['faction'], match['settings']['hero_cap'], session)
            except DomainError:
                current = None
            if current != selected:
                seat['ready'] = False
                ready_teams.discard(seat['team_id'])
            if self.db.network_battle_reservations.find_one({'_id': seat['account_id']}, session=session):
                ready_teams.discard(seat['team_id'])
        return ready_teams

    def _battle_ready(self, match, session):
        return len(self._battle_ready_teams(match, session)) == len(match['team_ids'])

    def _battle_start(self, match, session):
        if match.get('has_started'):
            match['state'] = 'running'
            return
        for hold in match['holds']:
            self._wallet_capture(hold, session)
        if match['kind'] == 'attack':
            for quota in match['quota_holds']:
                self._quota_commit(quota, session)
            if match.get('attack_budget'):
                self.db.court_attack_budgets.update_one({'_id': match['attack_budget']},
                    {'$inc': {'held': -match['attack_cost'], 'used': match['attack_cost']}}, session=session)
        match.update(state='running', has_started=True, started_at=self._now())
        match.pop('prepare_until', None)
        match.pop('attendance_until', None)
        self._battle_notify(match, 'Battle started', 'Your battle is now playing.', session)

    def _battle_descriptor(self, match):
        sides, units = [], []
        for seat in sorted(match['seats'], key=lambda row: row['side']):
            selection = seat.get('selection')
            hero = None
            if selection:
                hero = dict(kind='hero', instance_id=f"court:{match['_id']}:{seat['side']}",
                    owner_id=seat.get('account_id'), hero_id=selection['hero_id'],
                    form_id=selection['form_id'], unit_type=selection['unit_type'], xp=0,
                    effective_level=selection['hero_level'], stored_level=selection['collection_level'],
                    hero_level=selection['hero_level'], advancement_preferences={})
                units.append(deepcopy(hero))
            sides.append(dict(side=seat['side'], team_id=seat['team_id'],
                account_id=seat.get('account_id') or (selection.get('owner_id') if selection else None),
                username=seat.get('username', 'Castle defense'),
                controller=seat['controller'], faction=selection['faction'] if selection else 'Loyalists',
                leader_type=selection['unit_type'] if selection else 'Lieutenant', hero=hero, soldiers=[],
                item_id=seat.get('item_id', '') if seat['controller'] == 'human' else ''))
        descriptor = dict(run_id=match['_id'], generation=match['generation'], mode='court',
            mission_id='', map_id=match['settings']['map_id'], settings=deepcopy(match['settings']),
            seed=match['seed'], balance_revision=1, round=0, sides=sides, units=units,
            required_humans=sorted(seat['account_id'] for seat in match['seats'] if seat['controller'] == 'human'),
            worker_sides=sorted(seat['side'] for seat in match['seats'] if seat['controller'] == 'worker'),
            database_generation=match['database_generation'])
        descriptor['descriptor_sha256'] = digest(descriptor)
        return descriptor

    def _battle_machine(self, worker_id):
        if not isinstance(worker_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', worker_id):
            fail('invalid_input', 'The native worker identity is invalid.')

    def _battle_worker(self, match, worker_id, generation):
        self._battle_machine(worker_id)
        if (match.get('worker_id') != worker_id or match['generation'] != generation
                or match.get('lease_until', self._now()) <= self._now()):
            fail('forbidden', 'The native execution lease is unavailable or expired.')

    def court_capacity_available(self, worker_id):
        """Supervisor-only: reserve a real available worker before attendance starts.

        Call after the native artifact/launch preflight, never from a player API.
        The capacity lease must be refreshed while invitations/attendance run.
        """
        self._battle_machine(worker_id)
        def write(session):
            now = self._now()
            row = self.db.court_matches.find_one({'state': 'queued', 'capacity_worker': worker_id},
                session=session, sort=[('queued_at', 1), ('_id', 1)])
            if row is None:
                row = self.db.court_matches.find_one({'state': 'queued', '$or': [
                    {'capacity_worker': {'$exists': False}}, {'capacity_until': {'$lte': now}}]},
                    session=session, sort=[('queued_at', 1), ('_id', 1)])
            if row is None:
                return None
            if row.get('capacity_until') and row['capacity_until'] <= now and row.get('attendance_until'):
                # Lost infrastructure pauses, rather than consuming, attendance.
                row['attendance_until'] += now - row['capacity_until']
            row.update(capacity_worker=worker_id, capacity_until=now + timedelta(seconds=90))
            if not row.get('attendance_until'):
                row['attendance_until'] = now + timedelta(seconds=self._settings(session)['limits']['attendance_seconds'])
                self._battle_notify(row, 'Battle attendance opened', 'Your native worker is ready. Join and choose Ready.', session)
            self._battle_save(row, session)
            return {'run_id': row['_id'], 'attendance_until': public(row['attendance_until'])}
        return self._tx(write)

    def court_worker_acquire(self, worker_id):
        """Supervisor only. Freezes only complete Ready rosters and reserves humans."""
        self._battle_machine(worker_id)
        def write(session):
            now = self._now()
            old = self.db.court_matches.find_one({'state': 'paused', 'pause_reason': 'worker_unavailable',
                'lease_until': {'$lte': now}}, session=session, sort=[('created_at', 1), ('_id', 1)])
            if old:
                old.update(worker_id=worker_id, lease_until=now + timedelta(seconds=90), worker_loaded=False,
                           loaded_humans=[])
                if not old['has_started']:
                    old['prepare_until'] = now + timedelta(seconds=self._settings(session)['limits']['preparation_seconds'])
                self._battle_save(old, session)
                return public({**deepcopy(old['descriptor']), 'state': 'paused'})
            match = self.db.court_matches.find_one({'state': 'queued', 'capacity_worker': worker_id,
                'capacity_until': {'$gt': now}}, session=session, sort=[('queued_at', 1), ('_id', 1)])
            if match is None:
                return None
            if not self._battle_ready(match, session):
                self._battle_save(match, session)
                return None
            for team_id in match['team_ids']:
                if not team_id.startswith('garrison:'):
                    self._battle_team_touch(team_id, session)
            for seat in match['seats']:
                if seat['controller'] == 'human':
                    self.db.network_battle_reservations.insert_one(dict(_id=seat['account_id'],
                        kind='court', run_id=match['_id'], generation=match['generation'], created_at=now), session=session)
            match.update(state='preparing', worker_id=worker_id, lease_until=now + timedelta(seconds=90),
                prepare_until=now + timedelta(seconds=self._settings(session)['limits']['preparation_seconds']),
                loaded_humans=[], worker_loaded=False, seed=secrets.randbelow(2**31 - 1) + 1)
            match['descriptor'] = self._battle_descriptor(match)
            self._battle_save(match, session)
            self._battle_notify(match, 'Battle preparing', 'Enter the battle.', session)
            return public({**deepcopy(match['descriptor']), 'state': match['state']})
        return self._tx(write)

    def court_worker_lease(self, run_id, worker_id, generation):
        def write(session):
            match = self._battle_match(run_id, session)
            self._battle_worker(match, worker_id, generation)
            if match['state'] in TERMINAL_STATES:
                return {'run_id': run_id, 'generation': generation, 'state': match['state']}
            match['lease_until'] = self._now() + timedelta(seconds=90)
            self._battle_save(match, session)
            return {'run_id': run_id, 'generation': generation, 'state': match['state']}
        return self._tx(write)

    def _battle_loaded(self, match, scenario_sha256, session, actor=None, worker=False):
        bounded_hash(scenario_sha256)
        if match['state'] not in ('preparing', 'running', 'paused'):
            fail('battle_locked', 'This battle is not loading.')
        if match.get('scenario_sha256') not in (None, scenario_sha256):
            match.update(state='disputed', pause_reason='scenario_mismatch')
            self._battle_save(match, session)
            return {'state': 'disputed', 'reason': 'scenario_mismatch'}
        match['scenario_sha256'] = scenario_sha256
        if actor:
            match['loaded_humans'] = sorted(set(match['loaded_humans'] + [actor]))
            match.setdefault('disconnected', {}).pop(actor, None)
        match['worker_loaded'] = worker or match['worker_loaded']
        if worker and match.get('pause_reason') == 'worker_unavailable':
            match.pop('infrastructure_paused_at', None)
            if match['has_started']:
                # Recovery grants a fresh reconnect window after the actual
                # witness is available, excluding all infrastructure downtime.
                match['disconnected'] = {account: self._now()
                    for account in match['descriptor']['required_humans']
                    if account not in match['loaded_humans']}
                match['pause_reason'] = 'human_disconnected'
            else:
                match.pop('pause_reason', None)
                match['state'] = 'preparing'
        if match['worker_loaded'] and set(match['loaded_humans']) == set(match['descriptor']['required_humans']):
            self._battle_start(match, session)
            match.pop('pause_reason', None)
        self._battle_save(match, session)
        return {'run_id': match['_id'], 'generation': match['generation'], 'state': match['state'],
                'scenario_sha256': scenario_sha256}

    def court_worker_loaded(self, run_id, worker_id, generation, scenario_sha256):
        def write(session):
            match = self._battle_match(run_id, session)
            self._battle_worker(match, worker_id, generation)
            return self._battle_loaded(match, scenario_sha256, session, worker=True)
        return self._tx(write)

    def court_human_join(self, actor, run_id):
        def write(session):
            self._actor(actor, session)
            match = self._battle_match(run_id, session)
            if (match['state'] not in ('preparing', 'running', 'paused')
                    or actor not in match.get('descriptor', {}).get('required_humans', [])):
                fail('forbidden', 'This account has no human controller in the battle.')
            if not self.db.network_battle_reservations.find_one({'_id': actor,
                    'run_id': run_id, 'generation': match['generation']}, session=session):
                fail('reservation_lost', 'This account’s execution reservation is unavailable.')
            return public({**deepcopy(match['descriptor']), 'state': match['state'],
                           'scenario_sha256': match.get('scenario_sha256')})
        return self._tx(write)

    def court_human_loaded(self, actor, run_id, generation, scenario_sha256):
        def write(session):
            self._actor(actor, session)
            match = self._battle_match(run_id, session)
            if match['generation'] != generation or actor not in match.get('descriptor', {}).get('required_humans', []):
                fail('forbidden', 'This account cannot load this battle generation.')
            if not self.db.network_battle_reservations.find_one({'_id': actor,
                    'run_id': run_id, 'generation': generation}, session=session):
                fail('reservation_lost', 'The execution reservation is unavailable.')
            return self._battle_loaded(match, scenario_sha256, session, actor=actor)
        return self._tx(write)

    def court_human_disconnect(self, actor, run_id, generation):
        """Service-side connection event, not a player-command result endpoint."""
        def write(session):
            match = self._battle_match(run_id, session)
            if match['generation'] != generation or actor not in match.get('descriptor', {}).get('required_humans', []):
                fail('forbidden', 'This controller does not belong to the battle.')
            if match['state'] in ('preparing', 'running', 'paused'):
                match['loaded_humans'] = [item for item in match['loaded_humans'] if item != actor]
                match.setdefault('disconnected', {}).setdefault(actor, self._now())
                if match.get('pause_reason') != 'worker_unavailable':
                    match.update(state='paused', pause_reason='human_disconnected')
                self._battle_save(match, session)
            return {'state': match['state']}
        return self._tx(write)

    def court_worker_pause(self, run_id, worker_id, generation, reason='worker_interrupted'):
        def write(session):
            match = self._battle_match(run_id, session)
            if match.get('worker_id') != worker_id or match['generation'] != generation:
                fail('forbidden', 'Worker authority differs from this battle generation.')
            if match['state'] in ('preparing', 'running', 'paused'):
                dispute = reason in ('native_sync_error', 'native_evidence_conflict')
                match.update(state='disputed' if dispute else 'paused',
                    pause_reason=reason if dispute else 'worker_unavailable', worker_loaded=False,
                    infrastructure_paused_at=self._now())
                self._battle_save(match, session)
            return {'state': match['state']}
        return self._tx(write)

    def _court_select_item(self, actor, payload, session):
        exact(payload, ('match_id', 'expected_revision', 'item_id'))
        match = self._battle_match(payload['match_id'], session)
        revision(match, payload['expected_revision'])
        self._battle_membership(actor, match, session)
        if match['state'] not in ('response', 'scheduled', 'queued') or not match['settings']['items']:
            fail('battle_locked', 'Items are unavailable in this battle.')
        seat = next((row for row in match['seats'] if row.get('account_id') == actor), None)
        if seat is None or seat['controller'] != 'human':
            fail('not_joined', 'Join a human seat first.')
        if payload['item_id'] not in ('', 'healing_draught', 'remedy'):
            fail('invalid_input', 'Choose an available battle item.')
        if seat.get('item_hold_id'):
            self._inventory_release(seat.pop('item_hold_id'), session)
            seat.pop('item_id', None)
        if payload['item_id']:
            hold = f"court-item:{actor}:{payload['command_id']}"
            self._inventory_hold(actor, payload['item_id'], match['_id'], hold, session)
            seat.update(item_hold_id=hold, item_id=payload['item_id'])
        seat['ready'] = False
        self._battle_save(match, session)
        return {'match': self._court_match_public(match, actor, session)}

    def court_worker_item(self, run_id, worker_id, generation, evidence):
        """Only after a native validator confirmed owner, turn and applied effect."""
        exact(evidence, ('account_id', 'side', 'turn_side', 'item_id', 'command_sha256', 'applied'))
        bounded_hash(evidence['command_sha256'])
        if evidence['applied'] is not True:
            fail('invalid_evidence', 'The item effect was not applied by the native engine.')
        def write(session):
            match = self._battle_match(run_id, session)
            self._battle_worker(match, worker_id, generation)
            if (match['state'] not in ('running', 'paused') or not match['has_started']
                    or not match['worker_loaded'] or not match['settings']['items']):
                fail('battle_locked', 'This battle cannot consume an item now.')
            seat = next((row for row in match['seats'] if row.get('account_id') == evidence['account_id']), None)
            if (not seat or seat['controller'] != 'human' or seat['side'] != evidence['side']
                    or seat['side'] != evidence['turn_side'] or seat.get('item_id') != evidence['item_id']
                    or not seat.get('item_hold_id')):
                fail('invalid_evidence', 'The item is not assigned to this human controller and turn.')
            return self._inventory_consume(seat['item_hold_id'], evidence['command_sha256'], session)
        return self._tx(write)

    def _battle_settle(self, match, winner, draw, reason, session, *, evidence=None):
        prior = self.db.court_battle_receipts.find_one({'_id': match['_id']}, session=session)
        if prior:
            return public(prior)
        native = evidence is not None
        genuine = native and evidence['combat_verified'] and evidence['completed_rounds'] >= 1
        if not match['has_started']:
            for hold in match['holds']:
                self._refund_hold(hold, 'battle_not_started', session)
            for quota in match['quota_holds']:
                held = self.db.court_quota_holds.find_one({'_id': quota}, session=session)
                if held['state'] == 'reserved':
                    self._quota_release(quota, session)
        rewards, team_rewards, captured = [], [], None
        for team_id in match['team_ids']:
            if team_id.startswith('garrison:'):
                continue
            team = self._battle_team_touch(team_id, session)
            amount = {'win': 100, 'loss': 25, 'draw': 50}[
                'draw' if draw else 'win' if team_id == winner else 'loss'] if genuine else 0
            if team['experience'] + amount > MAX_XP:
                fail('progression_limit', 'Team progression requires administrator review.')
            self.db.court_teams.update_one({'_id': team_id}, {'$inc': {'experience': amount},
                '$set': {'level': team_level(team['experience'] + amount)}}, session=session)
            team_rewards.append({'team_id': team_id, 'experience': amount})
        if genuine:
            for seat in match['seats']:
                if seat['controller'] != 'human':
                    continue
                outcome = 'draw' if draw else 'win' if seat['team_id'] == winner else 'loss'
                amount = {'win': 20, 'loss': 10, 'draw': 10}[outcome]
                selected = seat['selection']
                # Increment current ownership, not the frozen battle snapshot.
                hero = self.db.account_heroes.find_one({'account_id': seat['account_id'],
                    'hero_id': selected['hero_id']}, session=session)
                if hero is None or hero['total_experience'] + amount > MAX_XP:
                    fail('progression_limit', 'Hero progression requires administrator review.')
                self.db.account_heroes.update_one({'_id': hero['_id']},
                    {'$inc': {'total_experience': amount, 'revision': 1}}, session=session)
                opponent = next(team for team in match['team_ids'] if team != seat['team_id'])
                cash = self._battle_cash(seat['account_id'], match['_id'], outcome, session,
                    mode='normal' if match['kind'] == 'attack' else match['kind'],
                    opponent_team_id=opponent if match['kind'] == 'plan' else None)
                rewards.append(dict(account_id=seat['account_id'], hero_id=selected['hero_id'],
                                    experience=amount, cash=cash['amount']))
        if match['kind'] == 'attack' and winner == match['initiator_team_id'] and (native or match['has_started']):
            castle = self.db.court_castles.find_one({'_id': match['castle_id'],
                'reservation_id': match['_id'], 'owner_team_id': match['original_owner']}, session=session)
            if not castle or not self.db.court_castle_claims.find_one({'_id': match['_id']}, session=session):
                fail('reservation_lost', 'The Castle reservation changed before settlement.')
            # The attack reserved one of the maximum ownership slots before play.
            current = self.db.court_castles.count_documents({'owner_team_id': winner}, session=session)
            if current >= self._settings(session)['limits']['castles_per_team']:
                fail('capacity', 'The reserved Castle capacity is unavailable.')
            self.db.court_castles.update_one({'_id': castle['_id']}, {'$set': {
                'owner_team_id': winner, 'owned_at': self._now(),
                'protected_until': self._now() + timedelta(seconds=self._settings(session)['limits']['protection_seconds'])},
                '$inc': {'revision': 1}}, session=session)
            captured = castle['_id']
        receipt = dict(_id=match['_id'], match_id=match['_id'], generation=match['generation'],
            winner_team_id=winner, draw=draw, reason=reason, native_verified=native,
            genuine_combat=bool(genuine), created_at=self._now(), hero_rewards=rewards,
            team_rewards=team_rewards, captured_castle_id=captured,
            evidence_digest=digest(evidence) if evidence else None,
            replay_sha256=evidence['replay_sha256'] if evidence else None,
            scores=deepcopy(evidence.get('scores', [])) if evidence else [])
        self.db.court_battle_receipts.insert_one(receipt, session=session)
        self._battle_release(match, session)
        match.update(state='completed', completed_at=self._now(), result=deepcopy(receipt))
        self._battle_save(match, session)
        for team_id in match['team_ids']:
            if not team_id.startswith('garrison:'):
                self._history(team_id, 'battle', 'Battle completed', deepcopy(receipt), session)
        self._battle_notify(match, 'Battle completed', reason.replace('_', ' '), session)
        if match['kind'] == 'competition':
            self._competition_result(match, winner, session)
        # BSON stores milliseconds. Return the durable receipt, so an immediate
        # response and any duplicate submission are byte-for-byte equivalent.
        return public(self.db.court_battle_receipts.find_one({'_id': match['_id']}, session=session))

    def court_worker_finish(self, run_id, worker_id, generation, evidence):
        """Private supervised API, following durable command/replay validation.

        The service must validate real native evidence files before calling this
        method. No player or administration command dispatches to this endpoint.
        """
        exact(evidence, ('scenario_sha256', 'replay_sha256', 'ledger_sha256',
            'command_chain_sha256', 'event_count', 'terminal', 'outcome', 'winner_team_id',
            'units', 'sync_valid', 'combat_verified', 'completed_rounds'), ('scores',))
        for name in ('scenario_sha256', 'replay_sha256', 'ledger_sha256', 'command_chain_sha256'):
            bounded_hash(evidence[name])
        integer(evidence['event_count'], 1, 10000000)
        integer(evidence['completed_rounds'], 0, 1000000)
        if (type(evidence['sync_valid']) is not bool or type(evidence['combat_verified']) is not bool
                or evidence['terminal'] not in ('victory', 'defeat', 'draw', 'turn_limit')
                or evidence['outcome'] not in ('win', 'draw') or not isinstance(evidence['units'], list)
                or len(evidence['units']) > 512):
            fail('invalid_evidence', 'The native terminal evidence is incomplete.')
        def write(session):
            match = self._battle_match(run_id, session)
            if match.get('worker_id') != worker_id or match['generation'] != generation:
                fail('forbidden', 'This worker does not own the battle generation.')
            prior = self.db.court_battle_receipts.find_one({'_id': run_id}, session=session)
            if prior:
                if prior.get('evidence_digest') != digest(evidence):
                    fail('result_conflict', 'This battle already has a different result.')
                return public(prior)
            self._battle_worker(match, worker_id, generation)
            if (match['state'] not in ('running', 'paused') or not match['has_started']
                    or not match['worker_loaded']):
                fail('battle_locked', 'This battle has not reached native play.')
            if not evidence['sync_valid'] or evidence['scenario_sha256'] != match.get('scenario_sha256'):
                match.update(state='disputed', pause_reason='native_evidence_conflict')
                self._battle_save(match, session)
                return {'run_id': run_id, 'state': 'disputed'}
            draw = evidence['outcome'] == 'draw'
            winner = evidence['winner_team_id']
            if draw != (winner is None) or (winner is not None and winner not in match['team_ids']):
                fail('invalid_evidence', 'The native result does not match the opposing Teams.')
            reason = 'draw' if draw else 'native_victory'
            if match['kind'] == 'competition' and draw:
                if evidence['completed_rounds'] < match['settings']['turns']:
                    fail('invalid_evidence', 'Competition tie-breaks require the complete agreed turn limit.')
                winner, reason = tournament_score(evidence.get('scores'), match['team_ids'],
                    seed=match['tie_seed'], match_id=match['_id'])
                # Tactical draw rewards remain draws; bracket advancement is separate.
            return self._battle_settle(match, winner, draw, reason, session, evidence=evidence)
        return self._tx(write)

    def _battle_preload_timeout(self, match, session):
        if match['kind'] == 'attack' and match['seats'][1]['controller'] == 'human':
            defender = match['seats'][1]['account_id']
            attacker = match['seats'][0]['account_id']
            if attacker in match['loaded_humans'] and defender not in match['loaded_humans']:
                # No gameplay has started: invalidate the complete old scenario
                # generation, then advertise a fresh, explicit AI contract.
                self.db.court_seats.delete_one({'_id': defender, 'match_id': match['_id']}, session=session)
                self.db.network_battle_reservations.delete_many({'run_id': match['_id'],
                    'generation': match['generation']}, session=session)
                for seat in match['seats']:
                    if seat.get('account_id') == defender:
                        if seat.get('item_hold_id'):
                            self._inventory_release(seat.pop('item_hold_id'), session)
                        seat.pop('item_id', None)
                self._battle_use_ai(match)
                match.update(generation=str(uuid4()), loaded_humans=[], worker_loaded=False)
                for key in ('descriptor', 'scenario_sha256', 'worker_id', 'lease_until',
                            'prepare_until', 'attendance_until', 'capacity_worker', 'capacity_until'):
                    match.pop(key, None)
                self._battle_save(match, session)
                self._battle_notify(match, 'Castle defense changed', 'The defender did not load. A new AI defense is preparing.', session)
                return
        self._battle_cancel(match, 'preparation_timeout', session, technical=True)

    def court_tick(self):
        """Bounded persisted deadlines. Clock changes alone never produce a win."""
        def write(session):
            now, limits = self._now(), self._settings(session)['limits']
            self._expire_applications(session)
            self._expire_room_holds(session)
            population = self.db.court_settings.find_one({'_id': 'population'}, session=session) or {}
            if population.get('next_check_at', now) <= now:
                self._refresh_population(session)
                self.db.court_settings.update_one({'_id': 'population'},
                    {'$set': {'next_check_at': now + timedelta(minutes=1)}}, session=session)
            changed = 0
            candidates = self.db.court_matches.find({'state': {'$in': list(ACTIVE_STATES)}}, session=session).sort('_id', 1).limit(500)
            for match in candidates:
                state = match['state']
                if state == 'proposed' and match['expires_at'] <= now:
                    self._battle_cancel(match, 'proposal_expired', session)
                elif state == 'response' and match['response_until'] <= now:
                    self._battle_use_ai(match)
                    self._battle_save(match, session)
                elif state == 'scheduled' and match.get('scheduled_at') and match['scheduled_at'] <= now:
                    match.update(state='queued', queued_at=now)
                    self._battle_save(match, session)
                elif state == 'queued':
                    capacity_live = match.get('capacity_until', now) > now
                    if not capacity_live:
                        if (match['kind'] == 'plan' and not match.get('attendance_until')
                                and match.get('queued_at', now) + timedelta(seconds=limits['queue_seconds']) <= now):
                            self._battle_cancel(match, 'worker_capacity_timeout', session, technical=True)
                        else:
                            continue
                    elif match.get('attendance_until', now + timedelta(seconds=1)) <= now:
                        ready_teams = self._battle_ready_teams(match, session)
                        if len(ready_teams) == len(match['team_ids']):
                            continue
                        if match['kind'] in ('competition', 'plan') and len(ready_teams) == 1:
                            self._battle_settle(match, next(iter(ready_teams)), False, 'attendance_forfeit', session)
                        elif match['kind'] == 'competition':
                            self._battle_settle(match, None, True, 'both_teams_absent', session)
                        else:
                            self._battle_cancel(match, 'attendance_timeout', session)
                    else:
                        continue
                elif state in ('preparing', 'running', 'paused'):
                    if match.get('lease_until', now) <= now and match.get('pause_reason') != 'worker_unavailable':
                        match.update(state='paused', pause_reason='worker_unavailable', worker_loaded=False,
                                     infrastructure_paused_at=now)
                        self._battle_save(match, session)
                    elif match.get('pause_reason') == 'worker_unavailable':
                        continue
                    elif not match['has_started'] and match.get('prepare_until', now + timedelta(seconds=1)) <= now:
                        self._battle_preload_timeout(match, session)
                    elif match['has_started'] and match.get('disconnected'):
                        absent = {seat['team_id'] for seat in match['seats'] if seat.get('account_id') in
                            match['disconnected'] and match['disconnected'][seat['account_id']] +
                            timedelta(seconds=limits['reconnect_seconds']) <= now}
                        if len(absent) == 1 and match['worker_loaded']:
                            winner = next(team for team in match['team_ids'] if team not in absent)
                            self._battle_settle(match, winner, False, 'disconnect_forfeit', session)
                        elif len(absent) == 2:
                            self._battle_cancel(match, 'both_teams_disconnected', session)
                        else:
                            continue
                    else:
                        continue
                else:
                    continue
                changed += 1
            return {'changed': changed}
        return self._tx(write)

    def court_castle_income(self):
        """One current-day payment only, with Castle and Team transaction fences."""
        def write(session):
            now, rules = self._now(), self._settings(session)
            day, paid = now.date().isoformat(), []
            cursor = self.db.court_settings.find_one({'_id': 'castle_income_cursor'}, session=session) or {}
            query = {'owner_team_id': {'$ne': None},
                    'owned_at': {'$lte': now - timedelta(seconds=rules['limits']['income_hold_seconds'])}}
            if cursor.get('day') == day and cursor.get('after'):
                query['_id'] = {'$gt': cursor['after']}
            castles = list(self.db.court_castles.find(query, session=session).sort('_id', 1).limit(128))
            self.db.court_settings.update_one({'_id': 'castle_income_cursor'}, {'$set': {
                'revision': 0, 'day': day, 'after': castles[-1]['_id'] if len(castles) == 128 else ''}}, upsert=True, session=session)
            for castle in castles:
                key = castle['_id'] + ':' + day
                if self.db.court_castle_income.find_one({'_id': key}, session=session):
                    continue
                team = self._battle_team_touch(castle['owner_team_id'], session)
                counter_key = team['_id'] + ':' + day
                counter = self.db.court_team_income_days.find_one({'_id': counter_key}, session=session)
                total = counter['amount'] if counter else 0
                amount = min(rules['limits']['castle_income'], max(0, rules['limits']['team_income_per_day'] - total))
                if amount == 0:
                    continue
                self.db.court_castles.update_one({'_id': castle['_id']}, {'$inc': {'revision': 1}}, session=session)
                self._wallet_credit('team', team['_id'], amount, 'castle-income:' + key, 'castle_income', session)
                self.db.court_team_income_days.update_one({'_id': counter_key}, {'$inc': {'amount': amount},
                    '$setOnInsert': {'team_id': team['_id'], 'day': day}}, upsert=True, session=session)
                row = dict(_id=key, castle_id=castle['_id'], team_id=team['_id'], day=day, amount=amount)
                self.db.court_castle_income.insert_one(row, session=session)
                paid.append(row)
            return {'payments': paid}
        return self._tx(write)

    def court_replay_authorize(self, actor, match_id):
        self._actor(actor)
        match = self._battle_match(match_id)
        team = self._team_for(actor, required=False)
        if actor not in match['historical_accounts'] and (not team or team['_id'] not in match['team_ids']):
            fail('forbidden', 'This replay belongs to the participating Teams.')
        result = match.get('result')
        if not result or not result.get('native_verified') or not result.get('replay_sha256'):
            fail('replay_unavailable', 'No verified native replay is available.')
        return {'run_id': match['_id'], 'generation': match['generation'],
                'replay_sha256': result['replay_sha256']}

    # The existing authenticated native wire uses these method names. Schema 5
    # selects this class explicitly; legacy schema 4 retains its own service.
    world_worker_acquire = court_worker_acquire
    world_worker_lease = court_worker_lease
    world_worker_loaded = court_worker_loaded
    world_worker_pause = court_worker_pause
    world_worker_finish = court_worker_finish
    world_human_join = court_human_join
    world_human_loaded = court_human_loaded
    world_human_disconnect = court_human_disconnect
    world_replay_authorize = court_replay_authorize
