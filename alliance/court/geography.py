"""Shared map-template identity and safe population-driven activation."""
from datetime import timedelta
from functools import lru_cache
import json
from pathlib import Path

from .base import fail, identifier, integer, revision, exact, public


@lru_cache(maxsize=1)
def catalogue():
    data = json.loads(Path(__file__).with_name('geography.json').read_text(encoding='utf-8'))
    if ([a['id'] for a in data['areas']] != [f'A{i:03d}' for i in range(1, 129)]
            or {c['id'] for c in data['castle_template']} != {f'C{i:03d}' for i in range(1, 65)}):
        raise RuntimeError('Court geography catalogue differs.')
    return data


class GeographyMixin:
    def _area(self, area_id, session=None, *, enabled=True):
        area = self.db.court_areas.find_one({'_id': identifier(area_id, 'area')}, session=session)
        if area is None or (enabled and not area['enabled']):
            fail('area_unavailable', 'This Area is not currently open.')
        return area

    def _castle(self, castle_id, session=None, *, enabled=True, role=None):
        castle = self.db.court_castles.find_one({'_id': identifier(castle_id, 'castle')}, session=session)
        if castle is None:
            fail('not_found', 'This Castle is unavailable.')
        self._area(castle['area_id'], session, enabled=enabled)
        if enabled and not castle['enabled']:
            fail('castle_unavailable', 'This Castle is not currently open.')
        if role and castle['role'] != role:
            fail('wrong_castle', 'Choose the correct type of Castle.')
        return castle

    def _touch_population(self, session):
        # Serialize Team creation/relocation and capacity checks before counting.
        self.db.court_settings.update_one({'_id': 'population'}, {'$inc': {'revision': 1}}, session=session)

    def _refresh_population(self, session):
        now, limits = self._now(), self._settings(session)['limits']
        counts = {row['_id']: row['count'] for row in self.db.court_teams.aggregate([
            {'$match': {'status': 'active'}}, {'$group': {'_id': '$area_id', 'count': {'$sum': 1}}}], session=session)}
        required = min(128, 1 + sum(counts.values()) // limits['area_expansion_teams'])
        for area in self.db.court_areas.find({}, session=session).sort('_id', 1):
            count = counts.get(area['_id'], 0)
            wanted = area['number'] <= required
            if area['mode'] != 'auto':
                wanted = area['mode'] == 'on'
            occupied = count > 0 or bool(self.db.court_castles.find_one({'area_id': area['_id'],
                '$or': [{'owner_team_id': {'$ne': None}}, {'reservation_id': {'$ne': None}},
                        {'event_id': {'$ne': None}}]}, {'_id': 1}, session=session))
            enabled, below = self._activation(area, wanted, occupied, now, limits)
            changes = {'enabled': enabled, 'below_since': below, 'team_count': count}
            if any(area.get(k) != v for k, v in changes.items()):
                self.db.court_areas.update_one({'_id': area['_id']}, {'$set': changes,
                    '$inc': {'revision': 1}}, session=session)
            normals = 0
            for castle in self.db.court_castles.find({'area_id': area['_id']}, session=session).sort('_id', 1):
                if castle['role'] == 'normal':
                    normals += 1
                    desired = normals <= min(60, max(limits['minimum_normal_castles'],
                        limits['normal_castles_per_team'] * count))
                else:
                    thresholds = {'C010': 2, 'C055': 10, 'C028': 4, 'C015': 12}
                    desired = count >= thresholds[castle['_id'][-4:]]
                if castle['mode'] != 'auto':
                    desired = castle['mode'] == 'on'
                desired = enabled and desired
                busy = any(castle.get(key) for key in ('owner_team_id', 'reservation_id', 'event_id'))
                active, pending = self._activation(castle, desired, busy, now, limits)
                if (active, pending) != (castle['enabled'], castle.get('below_since')):
                    self.db.court_castles.update_one({'_id': castle['_id']}, {'$set': {
                        'enabled': active, 'below_since': pending}, '$inc': {'revision': 1}}, session=session)

    @staticmethod
    def _activation(record, wanted, occupied, now, limits):
        if wanted or occupied:
            return True, None
        if not record['enabled']:
            return False, None
        since = record.get('below_since') or now
        return now < since + timedelta(seconds=limits['closure_delay_seconds']), since

    def _court_set_activation(self, actor, payload, session):
        exact(payload, ('kind', 'id', 'mode', 'revision', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        if payload['kind'] not in ('area', 'castle') or payload['mode'] not in ('auto', 'on', 'off'):
            fail('invalid_input', 'Choose an Area or Castle and its activation mode.')
        if payload['confirmation'] != 'confirmed':
            fail('confirmation_required', 'Confirm this activation change.')
        from .base import text
        reason = text(payload['reason'], 'Reason', 500, 3)
        kind = payload['kind']
        collection = self.db.court_areas if kind == 'area' else self.db.court_castles
        key = identifier(payload['id'], kind)
        row = collection.find_one({'_id': key}, session=session)
        if row is None:
            fail('not_found', 'This location does not exist.')
        revision(row, payload['revision'])
        self._touch_population(session)
        if payload['mode'] == 'off':
            if kind == 'area':
                busy = self.db.court_teams.find_one({'area_id': key, 'status': 'active'}, session=session)
                busy = busy or self.db.court_castles.find_one({'area_id': key, '$or': [
                    {'owner_team_id': {'$ne': None}}, {'reservation_id': {'$ne': None}},
                    {'event_id': {'$ne': None}}]}, session=session)
            else:
                busy = any(row.get(k) for k in ('owner_team_id', 'reservation_id', 'event_id'))
            if busy:
                fail('location_busy', 'Ownership, Teams or events must be cleared before closing this location.')
        updates = {'mode': payload['mode']}
        if payload['mode'] == 'off':
            updates.update(enabled=False, below_since=None)
        collection.update_one({'_id': key}, {'$set': updates, '$inc': {'revision': 1}}, session=session)
        self._refresh_population(session)
        self._audit(actor, 'court_activation', key, reason, {'mode': row['mode']}, updates, session)
        return {'id': key, 'mode': payload['mode']}

    def _area_public(self, area):
        return {**{k: area[k] for k in ('name', 'number', 'realm_id', 'realm_name', 'enabled',
            'mode', 'team_count', 'revision')}, 'id': area['_id']}

    def _castle_public(self, row, session=None):
        owner = self.db.court_teams.find_one({'_id': row.get('owner_team_id')}, {'name': 1}, session=session)
        state = ('protected' if row.get('protected_until') and row['protected_until'] > self._now()
                 else 'owned' if row.get('owner_team_id') else 'neutral')
        battle = None
        competition = None
        if row.get('reservation_id'):
            match = self.db.court_matches.find_one({'_id': row['reservation_id']}, session=session)
            if match and match['state'] not in ('completed', 'cancelled'):
                state = 'fighting' if match['state'] == 'running' else match['state']
                teams = []
                for team_id in match['team_ids']:
                    team = self.db.court_teams.find_one({'_id': team_id}, {'name': 1}, session=session)
                    teams.append({'id': team_id, 'name': team['name'] if team else 'Castle garrison'})
                battle = {'id': match['_id'], 'state': match['state'], 'teams': teams,
                    'deadline': match.get('response_until') or match.get('attendance_until') or match.get('prepare_until')}
        if row.get('event_id'):
            event = self.db.court_competitions.find_one({'_id': row['event_id']}, session=session)
            if event:
                state = 'competition_preparing' if event['state'] == 'registration' else 'competition'
                competition = {'id': event['_id'], 'name': event['name'], 'state': event['state'],
                    'round': event['round'], 'team_count': len(event['entries'])}
        if not row['enabled']:
            state = 'inactive'
        return public({**{k: row.get(k) for k in ('name', 'area_id', 'role', 'enabled', 'mode',
            'revision', 'owner_team_id', 'protected_until', 'reservation_id', 'event_id')},
            'id': row['_id'], 'owner_team_name': owner['name'] if owner else None,
            'state': state, 'battle': battle, 'competition': competition})
