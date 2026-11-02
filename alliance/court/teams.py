"""Ten-member Teams, reviewed membership fees and safe home relocation."""
from datetime import timedelta
from uuid import uuid4

from .base import exact, fail, identifier, integer, public, revision, text


class TeamMixin:
    def _confirmed(self, payload):
        if payload.get('confirmation') != 'confirmed':
            fail('confirmation_required', 'Review and confirm this action.')

    def _assert_member_idle(self, account_id, session):
        if (self.db.court_seats.find_one({'_id': account_id}, session=session)
                or self.db.network_battle_reservations.find_one({'_id': account_id}, session=session)):
            fail('player_committed', 'Leave or finish the current battle commitment first.')

    def _assert_team_idle(self, team_id, session):
        # The Team revision is also touched by each battle/entry commitment.
        self.db.court_teams.update_one({'_id': team_id}, {'$inc': {'revision': 1}}, session=session)
        active = {'$nin': ['completed', 'cancelled', 'rejected', 'declined', 'expired']}
        if (self.db.court_matches.find_one({'team_ids': team_id, 'state': active}, session=session)
                or self.db.court_competitions.find_one({'entries.team_id': team_id, 'state': active}, session=session)
                or self.db.court_holds.find_one({'kind': 'team', 'owner_id': team_id, 'state': 'held'}, session=session)):
            fail('team_committed', 'Finish or cancel this Team’s battles, entries and held funds first.')

    def _court_create_team(self, actor, payload, session):
        exact(payload, ('name', 'area_id', 'price_revision', 'confirmation'))
        self._confirmed(payload)
        settings = self._price_revision(payload, session)
        self._touch_population(session)
        if self._team_for(actor, session, required=False):
            fail('already_member', 'You already belong to a Team.')
        if self.db.court_applications.find_one({'account_id': actor, 'state': 'pending'}, session=session):
            fail('application_pending', 'Withdraw the current application before creating a Team.')
        area = self._area(payload['area_id'], session)
        count = self.db.court_teams.count_documents({'area_id': area['_id'], 'status': 'active'}, session=session)
        if count >= settings['limits']['teams_per_area']:
            fail('area_full', 'This Area has no place for another Team.')
        name = text(payload['name'], 'Team name', 32, 3)
        if self.db.court_teams.find_one({'name_key': name.casefold()}, session=session):
            fail('name_taken', 'That Team name is already in use.')
        hold = 'team-create:' + actor + ':' + payload['command_id']
        self._wallet_hold('personal', actor, settings['prices']['create_team'], hold, 'create_team', session)
        team = {'_id': str(uuid4()), 'name': name, 'name_key': name.casefold(),
            'area_id': area['_id'], 'captain_id': actor, 'members': [{'account_id': actor,
            'joined_at': self._now()}], 'status': 'active', 'experience': 0, 'level': 1,
            'revision': 0, 'allowances': {}, 'created_at': self._now()}
        self.db.court_teams.insert_one(team, session=session)
        self._wallet_capture(hold, session)
        self._refresh_population(session)
        self._history(team['_id'], 'team_created', 'Team created', {'area_id': area['_id']}, session)
        return {'team': self._team_public(team, actor, session)}

    def _expire_applications(self, session):
        for row in self.db.court_applications.find({'state': 'pending',
                'expires_at': {'$lte': self._now()}}, session=session).limit(100):
            self._close_application(row, 'expired', session)

    def _court_apply_team(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'price_revision', 'confirmation'))
        self._confirmed(payload)
        settings = self._price_revision(payload, session)
        if self._team_for(actor, session, required=False):
            fail('already_member', 'You already belong to a Team.')
        self._assert_member_idle(actor, session)
        if self.db.court_applications.find_one({'account_id': actor, 'state': 'pending'}, session=session):
            fail('application_pending', 'You already have a pending Team application.')
        team = self._team(payload['team_id'], session)
        revision(team, payload['revision'])
        self._area(team['area_id'], session)
        if len(team['members']) >= settings['limits']['team_members']:
            fail('team_full', 'This Team is full.')
        key = str(uuid4())
        hold = 'team-join:' + key
        self._wallet_hold('personal', actor, settings['prices']['join_team'], hold, 'join_team', session)
        row = {'_id': key, 'account_id': actor, 'team_id': team['_id'], 'state': 'pending',
            'revision': 0, 'hold_id': hold, 'created_at': self._now(),
            'expires_at': self._now() + timedelta(hours=24)}
        self.db.court_applications.insert_one(row, session=session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        self._notify(team['captain_id'], 'application', 'New application',
            self._actor(actor, session)['username'] + ' would like to join.',
            {'area_id': team['area_id'], 'team_id': team['_id']}, session)
        return {'application': self._application_public(row, session)}

    def _application(self, payload, session):
        row = self.db.court_applications.find_one({'_id': identifier(payload['application_id'])}, session=session)
        if not row:
            fail('not_found', 'This application is unavailable.')
        revision(row, payload['revision'])
        if row['state'] != 'pending':
            fail('application_decided', 'This application has already been resolved.')
        if row['expires_at'] <= self._now():
            fail('application_expired', 'This application has expired.')
        return row

    def _close_application(self, row, state, session):
        if state == 'approved':
            self._wallet_capture(row['hold_id'], session)
        else:
            self._wallet_release(row['hold_id'], session)
        self.db.court_applications.update_one({'_id': row['_id'], 'state': 'pending'},
            {'$set': {'state': state, 'decided_at': self._now()}, '$inc': {'revision': 1}}, session=session)
        team = self.db.court_teams.find_one({'_id': row['team_id']}, session=session)
        self._notify(row['account_id'], 'application_' + state, 'Application ' + state,
            (team['name'] if team else 'The Team') + ': ' + state,
            {'team_id': row['team_id'], **({'area_id': team['area_id']} if team else {})}, session)

    def _court_withdraw_application(self, actor, payload, session):
        exact(payload, ('application_id', 'revision'))
        row = self._application(payload, session)
        if row['account_id'] != actor:
            fail('forbidden', 'This is not your application.')
        self._close_application(row, 'withdrawn', session)
        return {'state': 'withdrawn'}

    def _court_approve_member(self, actor, payload, session):
        exact(payload, ('application_id', 'revision'), ('confirmation',))
        row = self._application(payload, session)
        team = self._team(row['team_id'], session)
        self._captain(actor, team, session)
        member = self._actor(row['account_id'], session)
        self._assert_member_idle(member['_id'], session)
        if self._team_for(member['_id'], session, required=False):
            fail('already_member', 'The applicant already belongs to a Team.')
        if len(team['members']) >= self._settings(session)['limits']['team_members']:
            fail('team_full', 'This Team is full. No joining fee was charged.')
        # Conflict with simultaneous applicant suspension or another admission.
        self.db.accounts.update_one({'_id': member['_id']}, {'$inc': {'revision': 1}}, session=session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$push': {'members': {
            'account_id': member['_id'], 'joined_at': self._now()}}, '$inc': {'revision': 1}}, session=session)
        self._close_application(row, 'approved', session)
        self._history(team['_id'], 'member_joined', member['username'] + ' joined',
            {'account_id': member['_id']}, session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _court_reject_member(self, actor, payload, session):
        exact(payload, ('application_id', 'revision'), ('confirmation',))
        row = self._application(payload, session)
        self._captain(actor, self._team(row['team_id'], session), session)
        self._close_application(row, 'rejected', session)
        return {'state': 'rejected'}

    def _abandon_holdings(self, team, session):
        for castle in self.db.court_castles.find({'owner_team_id': team['_id']}, session=session):
            if castle.get('reservation_id'):
                fail('castle_committed', 'A Castle is committed to a battle.')
            self.db.court_castles.update_one({'_id': castle['_id']}, {'$set': {
                'owner_team_id': None, 'protected_until': None, 'owned_since': None},
                '$inc': {'revision': 1}}, session=session)
            self._history(team['_id'], 'castle_abandoned', 'Castle abandoned',
                {'castle_id': castle['_id'], 'name': castle['name']}, session)

    def _court_leave_team(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'confirmation'))
        self._confirmed(payload)
        team = self._team(payload['team_id'], session)
        revision(team, payload['revision'])
        if actor not in {m['account_id'] for m in team['members']}:
            fail('not_member', 'You do not belong to this Team.')
        self._assert_member_idle(actor, session)
        self._touch_population(session)
        if team['captain_id'] == actor and len(team['members']) > 1:
            fail('captain_transfer_required', 'Choose another captain before leaving.')
        if team['captain_id'] == actor:
            self._assert_team_idle(team['_id'], session)
            self._abandon_holdings(team, session)
            for application in self.db.court_applications.find({'team_id': team['_id'], 'state': 'pending'}, session=session):
                self._close_application(application, 'rejected', session)
            self.db.court_teams.update_one({'_id': team['_id']}, {'$set': {
                'status': 'archived', 'captain_id': None, 'members': [], 'archived_at': self._now()},
                '$inc': {'revision': 1}}, session=session)
        else:
            self.db.court_teams.update_one({'_id': team['_id']}, {'$pull': {'members': {'account_id': actor}},
                '$inc': {'revision': 1}}, session=session)
        # Existing immutable match contracts retain their snapshots. New matches
        # must revalidate current donor membership, never copy the live collection.
        self.db.court_defenses.update_many({'team_id': team['_id'], 'owner_id': actor},
            {'$set': {'status': 'withdrawn'}, '$inc': {'revision': 1}}, session=session)
        self._history(team['_id'], 'member_left', self._actor(actor, session)['username'] + ' left',
            {'account_id': actor}, session)
        self._refresh_population(session)
        return {'team': None}

    def _court_remove_member(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'account_id', 'confirmation'))
        self._confirmed(payload)
        team = self._team(payload['team_id'], session)
        self._captain(actor, team, session)
        revision(team, payload['revision'])
        target = identifier(payload['account_id'])
        if target == actor or target not in {m['account_id'] for m in team['members']}:
            fail('not_member', 'Choose another current member.')
        self._assert_member_idle(target, session)
        member = self.db.accounts.find_one({'_id': target}, {'username': 1}, session=session)
        if member is None:
            fail('not_member', 'This member is unavailable.')
        # Conflict with a simultaneous battle claim, ownership or role change.
        self.db.accounts.update_one({'_id': target}, {'$inc': {'revision': 1}}, session=session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$pull': {'members': {'account_id': target}},
            '$unset': {'allowances.' + target: ''}, '$inc': {'revision': 1}}, session=session)
        self.db.court_defenses.update_many({'team_id': team['_id'], 'owner_id': target},
            {'$set': {'status': 'withdrawn'}, '$inc': {'revision': 1}}, session=session)
        self._history(team['_id'], 'member_removed', member['username'] + ' was removed',
            {'account_id': target, 'captain_id': actor}, session)
        self._notify(target, 'membership', 'Team membership ended',
            'The captain removed you from ' + team['name'] + '.', {'team_id': team['_id']}, session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _court_rename_team(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'name', 'confirmation'))
        self._confirmed(payload)
        team = self._team(payload['team_id'], session)
        self._captain(actor, team, session)
        revision(team, payload['revision'])
        name = text(payload['name'], 'Team name', 48, 3)
        if name == team['name']:
            return {'team': self._team_public(team, actor, session)}
        if self.db.court_teams.find_one({'name_key': name.casefold(), 'status': 'active',
                '_id': {'$ne': team['_id']}}, session=session):
            fail('name_taken', 'That Team name is already in use.')
        self._assert_team_idle(team['_id'], session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$set': {'name': name, 'name_key': name.casefold()},
            '$inc': {'revision': 1}}, session=session)
        self._history(team['_id'], 'renamed', 'Team renamed', {'previous_name': team['name'], 'name': name}, session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _court_transfer_captain(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'account_id', 'confirmation'))
        self._confirmed(payload)
        team = self._team(payload['team_id'], session)
        self._captain(actor, team, session)
        revision(team, payload['revision'])
        target = self._actor(identifier(payload['account_id']), session)
        if target['_id'] == actor or target['_id'] not in {m['account_id'] for m in team['members']}:
            fail('not_member', 'Choose another current member.')
        self._assert_team_idle(team['_id'], session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$set': {'captain_id': target['_id']},
            '$inc': {'revision': 1}}, session=session)
        self._team_notice(team, 'captain', 'Captain changed', target['username'] + ' is now captain.',
            {'team_id': team['_id'], 'area_id': team['area_id']}, session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _court_set_allowance(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'account_id', 'amount'))
        team = self._team(payload['team_id'], session)
        self._captain(actor, team, session)
        revision(team, payload['revision'])
        member = identifier(payload['account_id'])
        if member not in {m['account_id'] for m in team['members']}:
            fail('not_member', 'Choose a current member.')
        amount = integer(payload['amount'], 0, 100000)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$set': {'allowances.' + member: amount},
            '$inc': {'revision': 1}}, session=session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _court_relocate(self, actor, payload, session):
        exact(payload, ('team_id', 'revision', 'area_id', 'confirm_abandon', 'price_revision', 'confirmation'))
        self._confirmed(payload)
        if payload['confirm_abandon'] is not True:
            fail('confirmation_required', 'Confirm that existing Castles will become neutral.')
        settings = self._price_revision(payload, session)
        team = self._team(payload['team_id'], session)
        self._captain(actor, team, session)
        revision(team, payload['revision'])
        area = self._area(payload['area_id'], session)
        if area['_id'] == team['area_id']:
            fail('same_area', 'Choose a different Area.')
        self._touch_population(session)
        self._assert_team_idle(team['_id'], session)
        if self.db.court_teams.count_documents({'area_id': area['_id'], 'status': 'active'}, session=session) >= settings['limits']['teams_per_area']:
            fail('area_full', 'This Area has no place for another Team.')
        hold = 'team-relocate:' + actor + ':' + payload['command_id']
        self._wallet_hold('team', team['_id'], settings['prices']['relocate'], hold, 'relocate', session)
        self._abandon_holdings(team, session)
        self.db.court_teams.update_one({'_id': team['_id']}, {'$set': {'area_id': area['_id']},
            '$inc': {'revision': 1}}, session=session)
        self._wallet_capture(hold, session)
        self._refresh_population(session)
        self._history(team['_id'], 'relocated', 'Team relocated',
            {'from_area': team['area_id'], 'area_id': area['_id']}, session)
        self._team_notice(team, 'relocated', 'Team relocated', area['name'] + ' is the new home Area.',
            {'team_id': team['_id'], 'area_id': area['_id']}, session)
        return {'team': self._team_public(self._team(team['_id'], session), actor, session)}

    def _application_public(self, row, session=None):
        account = self.db.accounts.find_one({'_id': row['account_id']}, {'username': 1}, session=session)
        team = self.db.court_teams.find_one({'_id': row['team_id']}, {'name': 1}, session=session)
        return public({'id': row['_id'], 'account_id': row['account_id'], 'team_id': row['team_id'],
            'username': account['username'] if account else 'Unavailable player',
            'team_name': team['name'] if team else 'Unavailable Team', 'state': row['state'],
            'revision': row['revision'], 'expires_at': row['expires_at']})

    def _team_public(self, team, actor, session=None):
        if team is None:
            return None
        member_ids = {m['account_id'] for m in team['members']}
        member = actor in member_ids
        now = self._now()
        members = []
        for item in team['members']:
            account = self.db.accounts.find_one({'_id': item['account_id']},
                {'username': 1, 'status': 1, 'court_seen_at': 1}, session=session)
            if account:
                online = bool(account.get('court_seen_at') and account['court_seen_at'] > now - timedelta(seconds=90))
                members.append({'account_id': item['account_id'], 'username': account['username'],
                    'captain': item['account_id'] == team['captain_id'],
                    'status': ('online' if online else 'offline') if member else 'member'})
        area = self._area(team['area_id'], session, enabled=False)
        result = {'id': team['_id'], 'name': team['name'], 'area_id': team['area_id'],
            'area_name': area['name'], 'captain_id': team['captain_id'], 'captain': actor == team['captain_id'],
            'level': team['level'], 'experience': team['experience'], 'revision': team['revision'],
            'member_count': len(team['members']), 'capacity': 10, 'members': members}
        if member:
            result['wallet'] = self._wallet_public('team', team['_id'], session)
            names = {m['account_id']: m['username'] for m in members}
            result['defenses'] = [{key: row[key] for key in ('team_id', 'owner_id', 'selection', 'status', 'revision')}
                | {'id': row['_id'], 'owner_name': names.get(row['owner_id'], 'Unavailable player')}
                for row in self.db.court_defenses.find({'team_id': team['_id'],
                    'status': {'$in': ['offered', 'approved']}}, session=session).limit(20)]
            # Former members can retain historical allowance entries. Only the
            # current roster belongs in the bounded mobile Team projection.
            result['allowances'] = {key: value for key, value in team['allowances'].items()
                if key in member_ids} if actor == team['captain_id'] else {
                actor: team['allowances'].get(actor, self._settings(session)['limits']['member_allowance'])}
            result['castles'] = [self._castle_public(c, session) for c in
                self.db.court_castles.find({'owner_team_id': team['_id']}, session=session).sort('_id', 1)]
            approval_query = {'team_id': team['_id'], 'expires_at': {'$gt': now},
                '$or': [{'account_id': actor, 'state': {'$in': ['pending', 'approved']}}]}
            if actor == team['captain_id']:
                approval_query['$or'].append({'state': 'pending'})
            result['attack_approvals'] = []
            for row in self.db.court_attack_approvals.find(approval_query, session=session).sort('expires_at', 1).limit(40):
                castle = self.db.court_castles.find_one({'_id': row['castle_id']}, {'name': 1}, session=session)
                result['attack_approvals'].append({key: row[key] for key in
                    ('account_id', 'castle_id', 'amount', 'state', 'expires_at', 'revision')} | {
                    'id': row['_id'], 'username': names.get(row['account_id'], 'Unavailable player'),
                    'castle_name': castle['name'] if castle else 'Unavailable Castle'})
        if actor == team['captain_id']:
            result['applications'] = [self._application_public(row, session) for row in
                self.db.court_applications.find({'team_id': team['_id'], 'state': 'pending'}, session=session).limit(100)]
        return public(result)
