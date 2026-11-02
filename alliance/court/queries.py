"""Bounded, authorized projections for the persistent mobile workspace."""
from copy import deepcopy
import re

from ..heroes import catalog_hero, catalog_form, hero_progress
from .base import exact, fail, identifier, integer, text, revision, public_command_receipt


QUERIES = frozenset('''snapshot areas area castle my_team teams team plans plan
competitions competition shop wallet notifications history command_status room_quote'''.split())


class QueryMixin:
    def court_query(self, actor, request):
        exact(request, ('version', 'query'), ('payload',))
        if (set(request) - {'version', 'query', 'payload'} or type(request['version']) is not int
                or request['version'] != 1):
            fail('unsupported_protocol', 'Update the game to use Court.')
        query = request['query']
        if not isinstance(query, str) or query not in QUERIES:
            fail('unsupported_query', 'This page is unavailable.')
        payload = request.get('payload', {})
        if not isinstance(payload, dict):
            fail('invalid_input', 'A query object is required.')
        def read(session):
            self._actor(actor, session)
            result = getattr(self, '_query_' + query)(actor, payload, session)
            return self._envelope(actor, result, session)
        return self._tx(read)

    def _hero_choices(self, actor, session):
        result = []
        for row in self.db.account_heroes.find({'account_id': actor}, session=session).sort('hero_id', 1):
            hero = catalog_hero(row['hero_id'])
            forms = []
            for form_id in row['forms']:
                _, form = catalog_form(row['hero_id'], form_id)
                forms.append({'id': form_id, 'name': form.get('name', form['unit_type']),
                    'unit_type': form['unit_type'], 'native_level': form['native_level']})
            result.append({'id': row['hero_id'], 'hero_id': row['hero_id'], 'name': hero['name'],
                'forms': forms, 'revision': row['revision'], **hero_progress(row['total_experience'])})
        return result

    def _query_snapshot(self, actor, payload, session):
        exact(payload)
        team = self._team_for(actor, session, required=False)
        settings = self._settings(session)
        return {'team': self._team_public(team, actor, session) if team else None,
            'wallet': self._wallet_public('personal', actor, session),
            'areas': [self._area_public(row) for row in self.db.court_areas.find({}, session=session).sort('_id', 1)],
            'notifications_unread': self.db.court_notifications.count_documents({'account_id': actor, 'read_at': None}, session=session),
            'settings': {key: deepcopy(settings[key]) for key in ('revision', 'prices', 'limits')},
            'heroes': self._hero_choices(actor, session)}

    def _query_areas(self, actor, payload, session):
        exact(payload)
        return {'items': [self._area_public(row) for row in self.db.court_areas.find({}, session=session).sort('_id', 1)], 'next': ''}

    def _query_area(self, actor, payload, session):
        exact(payload, ('area_id',))
        self._team_for(actor, session)
        area = self._area(payload['area_id'], session)
        return {'area': self._area_public(area),
            'castles': [self._castle_public(row, session) for row in self.db.court_castles.find({'area_id': area['_id']}, session=session).sort('_id', 1)],
            'teams': [self._team_public(row, actor, session) for row in self.db.court_teams.find({'area_id': area['_id'], 'status': 'active'}, session=session).sort('name_key', 1).limit(30)]}

    def _query_castle(self, actor, payload, session):
        exact(payload, ('castle_id',))
        self._team_for(actor, session)
        castle = self._castle(payload['castle_id'], session)
        matches = list(self.db.court_matches.find({'castle_id': castle['_id']}, session=session).sort('created_at', -1).limit(20))
        competition = self.db.court_competitions.find_one({'_id': castle.get('event_id')}, session=session)
        return {'castle': self._castle_public(castle, session),
            'matches': [self._court_match_public(row, actor, session) for row in matches],
            'competition': self._competition_public(competition) if competition else None}

    def _query_my_team(self, actor, payload, session):
        exact(payload)
        team = self._team_for(actor, session, required=False)
        applications = self.db.court_applications.find({'account_id': actor, 'state': 'pending'}, session=session).limit(1)
        return {'team': self._team_public(team, actor, session) if team else None,
                'applications': [self._application_public(row, session) for row in applications]}

    def _query_team(self, actor, payload, session):
        exact(payload, ('team_id',))
        return {'team': self._team_public(self._team(payload['team_id'], session), actor, session)}

    def _query_teams(self, actor, payload, session):
        exact(payload, (), ('q', 'area_id', 'after'))
        query = {'status': 'active'}
        if payload.get('area_id'):
            query['area_id'] = self._area(payload['area_id'], session)['_id']
        term = text(payload.get('q', ''), 'Search', 64, 0)
        if term:
            query['name_key'] = {'$regex': re.escape(term.casefold())}
        if payload.get('after'):
            query['_id'] = {'$gt': identifier(payload['after'])}
        rows = list(self.db.court_teams.find(query, session=session).sort('_id', 1).limit(21))
        return {'items': [self._team_public(row, actor, session) for row in rows[:20]],
                'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def _query_plans(self, actor, payload, session):
        result = self._court_matches_query(actor, payload, session)
        return {'items': result['matches'], **result}

    def _query_plan(self, actor, payload, session):
        exact(payload, ('match_id',))
        match = self._battle_match(payload['match_id'], session)
        if not self._battle_can_view(actor, match, session):
            fail('forbidden', 'This battle is unavailable to your account.')
        return {'match': self._court_match_public(match, actor, session)}

    def _query_competitions(self, actor, payload, session):
        result = self._court_competitions_query(actor, payload, session)
        return {'items': result.get('competitions', []), **result}

    def _query_competition(self, actor, payload, session):
        exact(payload, ('competition_id',))
        return self._court_competitions_query(actor, payload, session)

    def _query_shop(self, actor, payload, session):
        return self._court_shop(actor, payload, session)

    def _query_wallet(self, actor, payload, session):
        return self._court_wallet(actor, payload, session)

    def _query_notifications(self, actor, payload, session):
        exact(payload, (), ('after', 'unread'))
        query = {'account_id': actor}
        if payload.get('after'):
            anchor = self.db.court_notifications.find_one({'_id': identifier(payload['after']),
                'account_id': actor}, session=session)
            if anchor is None:
                fail('invalid_input', 'Refresh this inbox page.')
            query['$or'] = [{'created_at': {'$lt': anchor['created_at']}},
                {'created_at': anchor['created_at'], '_id': {'$lt': anchor['_id']}}]
        if 'unread' in payload:
            if type(payload['unread']) is not bool:
                fail('invalid_input', 'Choose an inbox filter.')
            if payload['unread']:
                query['read_at'] = None
        rows = list(self.db.court_notifications.find(query, session=session).sort([('created_at', -1), ('_id', -1)]).limit(21))
        return {'items': [dict(id=row['_id'], **{key: row[key] for key in (
            'kind', 'title', 'message', 'target', 'created_at', 'read_at', 'revision')}) for row in rows[:20]],
            'next': rows[19]['_id'] if len(rows) > 20 else ''}

    def _court_read_notification(self, actor, payload, session):
        exact(payload, ('notification_id',))
        key = identifier(payload['notification_id'])
        row = self.db.court_notifications.find_one({'_id': key, 'account_id': actor}, session=session)
        if row is None:
            fail('not_found', 'This notification is unavailable.')
        if row['read_at'] is None:
            self.db.court_notifications.update_one({'_id': key}, {'$set': {'read_at': self._now()}, '$inc': {'revision': 1}}, session=session)
        return {'notification_id': key, 'read': True}

    def _query_history(self, actor, payload, session):
        exact(payload, (), ('team_id', 'after', 'match_after', 'castle_id'))
        match_query = {'state': 'history'}
        if payload.get('match_after'):
            match_query['after'] = payload['match_after']
        if payload.get('castle_id'):
            match_query['castle_id'] = identifier(payload['castle_id'], 'castle')
        matches = self._court_matches_query(actor, match_query, session)
        team = self._team_for(actor, session, required=False)
        if payload.get('team_id') and (not team or team['_id'] != identifier(payload['team_id'])):
            fail('forbidden', 'Only current members can inspect the Team ledger.')
        if not team:
            return {'items': [], 'next': '', 'matches': matches['matches'], 'match_next': matches['next']}
        query = {'team_id': team['_id']}
        if payload.get('castle_id'):
            query['data.castle_id'] = match_query['castle_id']
        if payload.get('after'):
            anchor = self.db.court_history.find_one({'_id': identifier(payload['after']),
                'team_id': team['_id']}, session=session)
            if anchor is None:
                fail('invalid_input', 'Refresh this history page.')
            query['$or'] = [{'created_at': {'$lt': anchor['created_at']}},
                {'created_at': anchor['created_at'], '_id': {'$lt': anchor['_id']}}]
        rows = list(self.db.court_history.find(query, session=session).sort([('created_at', -1), ('_id', -1)]).limit(21))
        return {'items': [dict(id=row['_id'], description=self._court_history_description(row, actor, session),
                              **{key: row[key] for key in ('kind', 'title', 'created_at')}) for row in rows[:20]],
            'next': rows[19]['_id'] if len(rows) > 20 else '',
            'matches': matches['matches'], 'match_next': matches['next']}

    def _court_history_description(self, row, actor, session):
        """Summarize known history fields, never stringify private data/IDs."""
        data, kind = row['data'], row['kind']

        def name(collection, key, fallback, field='name'):
            item = self.db[collection].find_one({'_id': key}, {field: 1}, session=session) if key else None
            return item.get(field, fallback) if item else fallback

        if kind == 'battle':
            match = self.db.court_matches.find_one({'_id': data.get('match_id')}, session=session)
            if match and row['team_id'] in match['team_ids']:
                return self._court_match_public(match, actor, session)['description']
            return 'Battle history is retained. Open the battle record for its result.'
        if kind in ('member_joined', 'member_left', 'member_removed'):
            who = name('accounts', data.get('account_id'), 'A member', 'username')
            action = {'member_joined': 'joined the Team.', 'member_left': 'left the Team.',
                      'member_removed': 'was removed from the Team.'}[kind]
            return who + ' ' + action
        if kind == 'team_created':
            return 'Team created in ' + name('court_areas', data.get('area_id'), 'its home Area') + '.'
        if kind == 'renamed':
            return f"Team renamed from {data.get('previous_name', 'its previous name')} to {data.get('name', 'its new name')}."
        if kind == 'relocated':
            return ('Home moved from ' + name('court_areas', data.get('from_area'), 'the previous Area') +
                    ' to ' + name('court_areas', data.get('area_id'), 'the new Area') + '.')
        if kind == 'castle_abandoned':
            return name('court_castles', data.get('castle_id'), 'The Castle') + ' returned to neutral ownership.'
        if kind == 'defense':
            return 'A saved hero template was approved for future computer defense.'
        if kind == 'competition':
            competition = self.db.court_competitions.find_one({'_id': data.get('competition_id')}, {'name': 1}, session=session)
            title = competition['name'] if competition else 'Competition'
            if data.get('winner_team_id'):
                winner = name('court_teams', data['winner_team_id'], 'The winning Team')
                prize = next((p['amount'] for p in data.get('prizes', []) if p['team_id'] == row['team_id']), 0)
                return f"{title}: {winner} won. Your Team prize: {prize} Crowns from the entry pool."
            return title + ' cancelled. Entry fees released or refunded.'
        return 'Team activity recorded.'

    def _query_command_status(self, actor, payload, session):
        exact(payload, ('command_id',))
        key = self._generation(session) + ':' + actor + ':' + identifier(payload['command_id'])
        row = self.db.court_commands.find_one({'_id': key}, session=session)
        return {'found': row is not None, 'receipt': public_command_receipt(row['result']) if row else None}

    def _court_set_rules(self, actor, payload, session):
        exact(payload, ('revision', 'prices', 'limits', 'reason', 'confirmation'))
        self._admin_actor(actor, session)
        self._confirmed(payload)
        reason = text(payload['reason'], 'Reason', 500, 3)
        current = self._settings(session)
        revision(current, payload['revision'])
        prices, limits = payload['prices'], payload['limits']
        if not isinstance(prices, dict) or set(prices) != set(current['prices']) or not isinstance(limits, dict) or set(limits) != set(current['limits']):
            fail('invalid_input', 'The rule fields differ. Refresh the settings form.')
        prices = {key: integer(value, 0, 1000000) for key, value in prices.items()}
        may_disable = {'attacks_per_day', 'extra_attacks_per_day', 'plans_per_day',
            'extra_plans_per_day', 'member_allowance', 'battle_cash_per_day',
            'castle_income', 'team_income_per_day', 'campaign_cash'}
        limits = {key: integer(value, 0 if key in may_disable else 1, 1000000)
                  for key, value in limits.items()}
        # Product sizes and timing fences are not mutable economy difficulty.
        adjustable = {'attacks_per_day', 'extra_attacks_per_day', 'plans_per_day',
            'extra_plans_per_day', 'member_allowance', 'battle_cash_per_day',
            'castle_income', 'team_income_per_day', 'campaign_cash',
            'area_expansion_teams', 'normal_castles_per_team', 'minimum_normal_castles'}
        if any(limits[key] != current['limits'][key] for key in limits if key not in adjustable):
            fail('invalid_input', 'This release fixes battle sizes and safety deadlines.')
        if limits['minimum_normal_castles'] > 60:
            fail('invalid_input', 'An Area contains sixty Normal Castles.')
        updates = {'prices': prices, 'limits': limits}
        self.db.court_settings.update_one({'_id': 'rules'}, {'$set': updates, '$inc': {'revision': 1}}, session=session)
        self._touch_population(session)
        self._refresh_population(session)
        self._audit(actor, 'court_rules', 'rules', reason,
            {key: current[key] for key in ('prices', 'limits')}, updates, session)
        return {'revision': current['revision'] + 1, **updates}
