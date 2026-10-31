"""Audited host actions which retain the game's ownership and settlement rules.

This module does not expose arbitrary document editing. Every operation checks
an active administrator and current revision inside the same transaction as its
mutation and audit entry. World evidence and completed rewards remain immutable.
"""
from copy import deepcopy
import hashlib
import hmac
import json
import re


def admin_record_revision(record):
    """Opaque fence for changing states, generations and legacy revision fields."""
    room = record.get('shared_room', {})
    fields = {key: record.get(key) for key in
              ('_id', 'kind', 'state', 'revision', 'generation', 'next_checkpoint')}
    fields['shared_room'] = {key: room.get(key) for key in ('state', 'generation', 'revision')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def admin_hero_grant_form(hero_id):
    """Return the canonical lowest-tier form used for an administrative unlock.

    Catalogue order is not a progression order. The deterministic tie-break is
    shared by the confirmation page and transaction; it does not claim that
    this form is the character's first appearance in an authored campaign.
    """
    from .domain import DomainError
    from .heroes import load_catalog
    if not isinstance(hero_id, str) or not re.fullmatch(r'[a-z0-9_-]{1,80}', hero_id):
        raise DomainError('invalid_input', 'Choose a hero from the catalogue.')
    catalog, _ = load_catalog()
    if not any(hero['id'] == hero_id for hero in catalog['heroes']):
        raise DomainError('invalid_input', 'Choose a hero from the catalogue.')
    forms = [form for form in catalog['forms'] if form['hero_id'] == hero_id]
    if not forms:
        raise DomainError('invalid_input', 'This hero has no available catalogue form.')
    return deepcopy(min(forms, key=lambda form: (form['native_level'], form['source_type'], form['id'])))


class AdminManagement:
    def admin_grant_hero(self, actor_id, account_id, hero_id, reason, expected_revision):
        """Unlock one canonical hero without inventing a campaign checkpoint.

        This only adds an absent hero. Existing forms, experience, frozen
        selections, sessions and personal armies are left intact. Suspended
        player accounts may be configured without reactivating their access.
        """
        from .domain import DomainError, _directory_id, _id, _now, _reason
        from .product import account_profile
        _directory_id(account_id, uuid=True)
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        form = admin_hero_grant_form(hero_id)

        def write(session):
            account = self._admin_account_revision(actor_id, account_id, expected_revision, session)
            if account['role'] != 'player':
                raise DomainError('forbidden', 'Only player accounts can own heroes.')
            if self.db.account_heroes.find_one({'account_id': account_id, 'hero_id': hero_id}, session=session):
                raise DomainError('hero_already_owned', 'This player already owns this hero. Existing progress was preserved.')
            # Story rewards, tactical preparation and account editing write the
            # same account. A race retries against its current revision instead
            # of replacing earned hero data from a stale page.
            self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
            self.db.account_heroes.insert_one({
                '_id': _id(), 'account_id': account_id, 'hero_id': hero_id,
                'forms': [form['id']], 'total_experience': 0, 'revision': 0,
                'unlocked_at': _now(), 'unlock_source': 'administrator', 'granted_by': actor_id,
            }, session=session)
            self._audit(actor_id, 'grant_hero', account_id, reason,
                        {'hero_id': hero_id, 'owned': False},
                        {'hero_id': hero_id, 'owned': True, 'forms': [form['id']],
                         'total_experience': 0, 'source': 'administrator'}, session)
            return account_profile(self.db, self._account(account_id, session, active=False), session)
        return self._tx(write)

    def admin_create_player(self, actor_id, username, password, confirmation, reason):
        """Create an ordinary player with zero heroes; never fabricate progress."""
        from .auth import hash_password
        from .domain import DomainError, _id, _now, _reason, validate_username
        from .product import account_profile
        username, key = validate_username(username)
        reason = _reason(reason)
        if (not isinstance(password, str) or not 12 <= len(password) <= 128
                or '\x00' in password or any(0xD800 <= ord(char) <= 0xDFFF for char in password)):
            raise DomainError('invalid_input', 'Use a password of 12 to 128 valid Unicode characters without NUL.')
        if not isinstance(confirmation, str) or password != confirmation:
            raise DomainError('invalid_input', 'The password confirmation must match exactly.')
        if self._account(actor_id)['role'] != 'admin':
            raise DomainError('forbidden', 'Administrator access is required.')
        encoded = hash_password(password)
        def write(session):
            self._admin(actor_id, session)
            account = {'_id': _id(), 'username': username, 'username_key': key,
                'password_hash': encoded, 'role': 'player', 'status': 'active',
                'database_generation': self._generation(session), 'active_run_id': None,
                'revision': 0, 'training_completed': [], 'created_at': _now()}
            self.db.accounts.insert_one(account, session=session)
            self._audit(actor_id, 'create_player', account['_id'], reason, None,
                        {'username': username, 'role': 'player', 'status': 'active'}, session)
            return account_profile(self.db, account, session)
        return self._tx(write)

    @staticmethod
    def _management_revision(actual, expected):
        from .domain import DomainError
        if type(expected) is not int or not 0 <= expected <= 9223372036854775806:
            raise DomainError('invalid_input', 'A current revision is required.')
        if actual != expected:
            raise DomainError('stale_revision', 'This record changed. Reload it before confirming the action.')

    def _management_team_idle(self, team, session):
        """Serialize governance against tactical starts and strategic orders."""
        from .domain import DomainError
        self._idle(team)
        self._governance_idle(team['_id'], session)
        if self._world_state(session, required=False) is not None:
            # Strategic writes and phase transitions use this same fence.
            self._world_planning(session)
        if self.db.world_contracts.find_one({'team_ids': team['_id'],
                'state': {'$nin': ['completed', 'cancelled']}}, {'_id': 1}, session=session):
            raise DomainError('busy', 'Finish or cancel the team’s World and Company contracts first.')
        if self.db.world_wars.find_one({'team_ids': team['_id'],
                'state': {'$in': ['proposed', 'active']}}, {'_id': 1}, session=session):
            raise DomainError('busy', 'Finish or cancel the current territorial war before changing team governance.')
        if self.db.world_defenses.find_one({'team_id': team['_id'],
                'status': {'$ne': 'withdrawn'}}, {'_id': 1}, session=session):
            raise DomainError('busy', 'Withdraw standing defense permissions before changing team governance.')

    def _management_member_idle(self, account_id, session):
        from .domain import DomainError
        account = self._account(account_id, session, active=False)
        if account['role'] != 'player':
            raise DomainError('forbidden', 'Only player accounts can hold team membership.')
        self._idle(account)
        if (self.db.network_battle_reservations.find_one({'_id': account_id}, session=session)
                or self.db.company_asset_locks.find_one({'owner_id': account_id}, session=session)
                or self.db.world_contracts.find_one({'armies.account_id': account_id,
                    'state': {'$nin': ['completed', 'cancelled']}}, session=session)):
            raise DomainError('busy', 'This player has an active deployment. Complete or cancel it first.')
        # Force/battle preparation and account changes touch the same account.
        self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
        return account

    def admin_manage_team(self, actor_id, team_id, operation, value, reason, expected_revision):
        """Edit governance or administrative area without changing territory."""
        from .domain import DomainError, _directory_id, _name, _reason
        _directory_id(team_id, uuid=True)
        reason = _reason(reason)
        if operation not in ('rename', 'captain', 'remove_member', 'move_area'):
            raise DomainError('invalid_input', 'Unknown team management action.')
        if operation == 'rename':
            value, name_key = _name(value, 'Team name')
        elif operation == 'move_area':
            _directory_id(value)
        else:
            _directory_id(value, uuid=True)

        def write(session):
            self._admin(actor_id, session)
            team = self._team(team_id, session)
            self._management_revision(team['revision'], expected_revision)
            self._management_team_idle(team, session)
            before = {key: deepcopy(team[key]) for key in ('name', 'captain_id', 'members', 'area_id')}
            if operation == 'rename':
                update = {'$set': {'name': value, 'name_key': name_key}}
            elif operation == 'move_area':
                self._area(value, session)
                update = {'$set': {'area_id': value}}
            else:
                if value not in {member['account_id'] for member in team['members']}:
                    raise DomainError('not_member', 'Choose a current member of this team.')
                member = self._management_member_idle(value, session)
                if operation == 'captain':
                    if member['status'] != 'active':
                        raise DomainError('forbidden', 'The new captain must have an active player account.')
                    if value == team['captain_id']:
                        raise DomainError('invalid_input', 'Choose another current member as captain.')
                    self._management_member_idle(team['captain_id'], session)
                    update = {'$set': {'captain_id': value}}
                else:
                    if value == team['captain_id']:
                        raise DomainError('captain_transfer_required', 'Appoint another captain before removing this member.')
                    if self.db.world_castles.find_one({'governor_id': value}, session=session):
                        raise DomainError('busy', 'Appoint a replacement governor before removing this member.')
                    # Match ordinary membership departure: retain World
                    # enrollment/history and participation fences. Joining a
                    # new team requires explicit World re-enrollment; removal
                    # must not manufacture another move or attack this round.
                    update = {'$pull': {'members': {'account_id': value}}}
            update['$inc'] = {'revision': 1}
            self.db.teams.update_one({'_id': team_id}, update, session=session)
            if operation != 'rename':
                # Changed membership/captain authority revokes all existing
                # consent on this team's current flexible drafts, not history.
                self.db.game_runs.update_many({'kind': 'alliance', 'state': 'draft',
                    'plan_format': 2, 'team_ids': team_id},
                    {'$set': {'approvals': {}, 'ready': []}, '$inc': {'revision': 1}}, session=session)
                if operation == 'remove_member':
                    self._revoke_draft_readiness(value, session)
            current = self._team(team_id, session)
            after = {key: deepcopy(current[key]) for key in ('name', 'captain_id', 'members', 'area_id')}
            self._audit(actor_id, 'manage_team_' + operation, team_id, reason, before, after, session)
            return {'id': team_id, **after, 'revision': current['revision']}
        return self._tx(write)

    def admin_cancel_record(self, actor_id, kind, record_id, reason, expected_revision):
        """Cancel one retained contract through its actual lifecycle release."""
        from .domain import DomainError, _directory_id, _reason
        _directory_id(record_id, uuid=True)
        reason = _reason(reason)
        if kind not in ('plan', 'run', 'world'):
            raise DomainError('invalid_input', 'Unknown battle or campaign record kind.')
        if not isinstance(expected_revision, str) or not re.fullmatch('[0-9a-f]{64}', expected_revision):
            raise DomainError('invalid_input', 'A current record version is required.')

        def write(session):
            self._admin(actor_id, session)
            row = self._world_run(record_id, session) if kind == 'world' else self._run(record_id, session)
            if not hmac.compare_digest(admin_record_revision(row), expected_revision):
                raise DomainError('stale_revision', 'This record changed. Reload it before confirming cancellation.')
            if kind == 'plan' and row['kind'] != 'alliance':
                raise DomainError('invalid_input', 'This record is not a Team battle plan.')
            if row['state'] == 'completed':
                raise DomainError('invalid_state', 'A completed result and its rewards cannot be cancelled.')
            if row['state'] == 'cancelled':
                return {'id': record_id, 'state': 'cancelled', 'revision': admin_record_revision(row)}
            before = {'state': row['state'], 'revision': admin_record_revision(row)}
            if kind == 'world':
                self._world_cancel(row, reason, session)
                current = self._world_run(record_id, session)
            else:
                self._cancel(record_id, reason, session)
                self.db.game_runs.update_one({'_id': record_id}, {'$inc': {'revision': 1}}, session=session)
                current = self._run(record_id, session)
            result = {'id': record_id, 'state': current['state'], 'revision': admin_record_revision(current)}
            self._audit(actor_id, 'cancel_' + kind, record_id, reason, before, result, session)
            return result
        return self._tx(write)

    def admin_revoke_sessions(self, actor_id, account_id, reason, expected_revision):
        """Revoke credentials without releasing a player's battle/asset leases."""
        from .domain import _directory_id, _reason
        _directory_id(account_id, uuid=True)
        reason = _reason(reason)
        self._expected_account_revision(expected_revision)
        def write(session):
            self._admin_account_revision(actor_id, account_id, expected_revision, session)
            removed = self.db.auth_sessions.delete_many({'account_id': account_id}, session=session).deleted_count
            self.db.casual_tickets.delete_many({'account_id': account_id}, session=session)
            if actor_id != account_id:
                self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
            result = {'account_id': account_id, 'sessions_revoked': removed}
            self._audit(actor_id, 'revoke_sessions', account_id, reason, None, result, session)
            return result
        return self._tx(write)

    def admin_rest_company(self, actor_id, account_id, reason, expected_revision):
        """Use the same Rest rules; territorial and committed wounds persist."""
        from .domain import DomainError, _directory_id, _reason
        _directory_id(account_id, uuid=True)
        reason = _reason(reason)
        def write(session):
            self._admin(actor_id, session)
            owner = self._account(account_id, session, active=False)
            if owner['role'] != 'player':
                raise DomainError('forbidden', 'Only a player has a personal Company.')
            self.db.accounts.update_one({'_id': account_id}, {'$inc': {'revision': 1}}, session=session)
            before = self.db.company_wounds.count_documents({'owner_id': account_id, 'kind': 'rest_wounded'}, session=session)
            result = self._company_command(account_id, 'company_rest', {'expected_revision': expected_revision}, session)
            remaining = self.db.company_wounds.count_documents({'owner_id': account_id, 'kind': 'rest_wounded'}, session=session)
            output = {'account_id': account_id, 'revision': result['revision'], 'healed': before - remaining,
                      'territorial_wounds': self.db.company_wounds.count_documents(
                          {'owner_id': account_id, 'kind': 'world_wounded'}, session=session)}
            self._audit(actor_id, 'rest_company', account_id, reason, {'rest_wounds': before}, output, session)
            return output
        return self._tx(write)

    def admin_withdraw_defense(self, actor_id, assignment_id, reason, expected_revision):
        """Withdraw future permission; a frozen active engagement keeps control."""
        from .domain import DomainError, _directory_id, _reason
        _directory_id(assignment_id, uuid=True)
        reason = _reason(reason)
        def write(session):
            self._admin(actor_id, session)
            row = self.db.world_defenses.find_one({'_id': assignment_id}, session=session)
            if row is None:
                raise DomainError('not_found', 'This standing defense is unavailable.')
            self._management_revision(row['revision'], expected_revision)
            if row['status'] == 'withdrawn':
                return {'id': assignment_id, 'status': 'withdrawn', 'revision': row['revision']}
            # All strategic changes share the global phase/commit fence.
            self._world_state(session)
            self.db.world_states.update_one({'_id': 'world'}, {'$inc': {'revision': 1}}, session=session)
            self.db.accounts.update_one({'_id': row['owner_id']}, {'$inc': {'revision': 1}}, session=session)
            status = 'withdraw_pending' if row.get('run_id') else 'withdrawn'
            self.db.world_defenses.update_one({'_id': assignment_id},
                {'$set': {'status': status}, '$inc': {'revision': 1}}, session=session)
            if status == 'withdrawn':
                self.db.company_asset_locks.delete_many({'assignment_id': assignment_id}, session=session)
            result = {'id': assignment_id, 'status': status, 'revision': row['revision'] + 1}
            self._audit(actor_id, 'withdraw_defense', assignment_id, reason,
                        {'status': row['status'], 'run_id': row.get('run_id')}, result, session)
            return result
        return self._tx(write)
