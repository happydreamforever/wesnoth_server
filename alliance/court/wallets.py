"""Transactional virtual Crowns, shop ownership, inventory and daily quotas.

All mutating methods require the caller's MongoDB transaction. Public commands
are additionally fenced by CourtBase._execute. No request processes payments,
and no caller can supply a credit amount to the purchase-approval operation.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4

from .base import fail, exact, integer, identifier, revision, text
from .wallet_schema import MAX_CROWNS, MAX_ITEMS
from ..admin_management import admin_hero_grant_form
from ..heroes import hero_progress, load_catalog


ITEMS = {
    'healing_draught': {'id': 'healing_draught', 'name': 'Healing Draught',
                        'description': 'Restore up to 12 HP to your living hero.', 'heal': 12},
    'remedy': {'id': 'remedy', 'name': 'Remedy',
               'description': 'Remove poison and slowed from your hero.', 'cures': ['poisoned', 'slowed']},
}
PACKAGES = (100, 500, 1000)


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,240}', value):
        fail('invalid_input', 'The transaction reference is invalid.')
    return value


def confirmed(payload):
    if payload.get('confirmation') != 'confirmed':
        fail('confirmation_required', 'Review the cost and confirm this action.')


def wallet_id(kind, owner_id):
    if kind not in ('personal', 'team'):
        fail('invalid_input', 'Choose a personal or Team wallet.')
    return f'{kind}:{identifier(owner_id)}'


def digest(*values):
    return sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class EconomyMixin:
    def _wallet_owner(self, kind, owner_id, session):
        wallet_id(kind, owner_id)
        collection = self.db.accounts if kind == 'personal' else self.db.court_teams
        query = {'_id': owner_id}
        if kind == 'personal':
            query.update(role='player', database_generation=self._generation(session))
        owner = collection.find_one(query, session=session)
        if owner is None:
            fail('wallet_unavailable', 'The wallet owner is unavailable.')
        return owner

    def _wallet_public(self, kind, owner_id, session=None):
        name = wallet_id(kind, owner_id)
        row = self.db.court_wallets.find_one({'_id': name}, session=session)
        if row is None:
            return {'kind': kind, 'owner_id': owner_id, 'currency': 'Crowns',
                    'available': 0, 'held': 0, 'revision': 0}
        if row['generation'] != self._generation(session):
            fail('generation_changed', 'The game generation changed. Sign in again.')
        return {'kind': kind, 'owner_id': owner_id, 'currency': 'Crowns',
                'available': row['available'], 'held': row['held'], 'revision': row['revision']}

    def _wallet_ensure(self, kind, owner_id, session):
        self._wallet_owner(kind, owner_id, session)
        name = wallet_id(kind, owner_id)
        generation = self._generation(session)
        self.db.court_wallets.update_one({'_id': name}, {'$setOnInsert': {
            'kind': kind, 'owner_id': owner_id, 'generation': generation,
            'available': 0, 'held': 0, 'revision': 0}}, upsert=True, session=session)
        row = self.db.court_wallets.find_one({'_id': name}, session=session)
        if row['generation'] != generation:
            fail('generation_changed', 'The game generation changed. Sign in again.')
        return row

    def _wallet_mutate(self, kind, owner_id, available, held, session):
        row = self._wallet_ensure(kind, owner_id, session)
        next_available, next_held = row['available'] + available, row['held'] + held
        if next_available < 0:
            fail('insufficient_funds', 'There are not enough available Crowns.')
        if next_held < 0:
            fail('invalid_hold', 'The held balance does not match this operation.')
        if next_available + next_held > MAX_CROWNS:
            fail('balance_limit', 'The wallet balance limit would be exceeded.')
        changed = self.db.court_wallets.update_one({'_id': row['_id'], 'revision': row['revision']},
            {'$inc': {'available': available, 'held': held, 'revision': 1}}, session=session)
        if changed.modified_count != 1:
            fail('balance_changed', 'The wallet changed. Refresh and retry.')

    def _ledger_previous(self, operation, reference, binding, session):
        row_id = digest(self._generation(session), operation, key(reference))
        previous = self.db.court_ledger.find_one({'_id': row_id}, session=session)
        if previous is not None and previous['binding'] != binding:
            fail('transaction_conflict', 'This transaction reference belongs to different details.')
        return row_id, previous

    def _ledger_insert(self, row_id, operation, binding, wallets, postings, session):
        if sum(amount for _, amount in postings) != 0:
            raise ValueError('Unbalanced Crown postings.')
        self.db.court_ledger.insert_one({'_id': row_id, 'generation': self._generation(session),
            'operation': operation, 'binding': deepcopy(binding), 'wallet_ids': sorted(set(wallets)),
            'postings': [{'account': account, 'amount': amount} for account, amount in postings],
            'created_at': self._now()}, session=session)

    def _wallet_credit(self, kind, owner_id, amount, receipt_key, reason, session):
        amount = integer(amount)
        name = wallet_id(kind, owner_id)
        reason = text(reason, 'Credit reason', 500)
        binding = {'kind': kind, 'owner_id': owner_id, 'amount': amount, 'reason': reason}
        row_id, previous = self._ledger_previous('credit', receipt_key, binding, session)
        if previous is None:
            self._wallet_mutate(kind, owner_id, amount, 0, session)
            self._ledger_insert(row_id, 'credit', binding, [name],
                [('system:issuance', -amount), (name + ':available', amount)], session)
        return {'receipt_id': row_id, 'amount': amount, 'wallet': self._wallet_public(kind, owner_id, session)}

    def _wallet_hold(self, kind, owner_id, amount, hold_id, purpose, session):
        amount = integer(amount)
        hold_id, purpose = key(hold_id), text(purpose, 'Hold purpose', 200)
        name = wallet_id(kind, owner_id)
        binding = {'kind': kind, 'owner_id': owner_id, 'generation': self._generation(session),
                   'amount': amount, 'purpose': purpose}
        previous = self.db.court_holds.find_one({'_id': hold_id}, session=session)
        if previous is not None:
            if any(previous[field] != value for field, value in binding.items()):
                fail('transaction_conflict', 'This hold belongs to different purchase details.')
            return self._hold_public(previous)
        self._wallet_mutate(kind, owner_id, -amount, amount, session)
        row = {'_id': hold_id, **binding, 'state': 'held', 'created_at': self._now(), 'revision': 0}
        self.db.court_holds.insert_one(row, session=session)
        row_id, _ = self._ledger_previous('hold', hold_id, binding, session)
        self._ledger_insert(row_id, 'hold', binding, [name],
            [(name + ':available', -amount), (name + ':held', amount)], session)
        return self._hold_public(row)

    @staticmethod
    def _hold_public(row):
        return {'id': row['_id'], **{k: row[k] for k in ('kind', 'owner_id', 'amount', 'purpose', 'state')}}

    def _wallet_transition(self, hold_id, state, session, reason=None):
        row = self.db.court_holds.find_one({'_id': key(hold_id)}, session=session)
        if row is None or row['generation'] != self._generation(session):
            fail('hold_unavailable', 'The payment hold is unavailable.')
        if state == 'refunded':
            reason = text(reason, 'Refund reason', 500)
        if row['state'] == state:
            if state == 'refunded' and row['refund_reason'] != reason:
                fail('transaction_conflict', 'The refund was already recorded with different details.')
            return self._hold_public(row)
        source = 'captured' if state == 'refunded' else 'held'
        if row['state'] != source:
            fail('hold_finalized', 'This payment has already been finalized.')
        amount, name = row['amount'], wallet_id(row['kind'], row['owner_id'])
        available = amount if state in ('released', 'refunded') else 0
        held = -amount if source == 'held' else 0
        self._wallet_mutate(row['kind'], row['owner_id'], available, held, session)
        updates = {'state': state, 'updated_at': self._now()}
        if reason is not None:
            updates['refund_reason'] = reason
        self.db.court_holds.update_one({'_id': hold_id, 'revision': row['revision']},
            {'$set': updates, '$inc': {'revision': 1}}, session=session)
        binding = {'hold_id': hold_id, 'amount': amount, 'kind': row['kind'], 'owner_id': row['owner_id']}
        if reason is not None:
            binding['reason'] = reason
        operation = {'captured': 'capture', 'released': 'release', 'refunded': 'refund'}[state]
        row_id, _ = self._ledger_previous(operation, hold_id, binding, session)
        postings = ([(name + ':held', -amount), ('system:spent', amount)] if state == 'captured' else
                    [(name + ':held', -amount), (name + ':available', amount)] if state == 'released' else
                    [('system:spent', -amount), (name + ':available', amount)])
        self._ledger_insert(row_id, operation, binding, [name], postings, session)
        return self._hold_public({**row, **updates})

    def _wallet_capture(self, hold_id, session):
        return self._wallet_transition(hold_id, 'captured', session)

    def _wallet_release(self, hold_id, session):
        return self._wallet_transition(hold_id, 'released', session)

    def _wallet_refund(self, hold_id, reason, session):
        return self._wallet_transition(hold_id, 'refunded', session, reason)

    def _wallet_transfer(self, actor, team_id, amount, receipt_key, session):
        amount = integer(amount, 1)
        binding = {'from_account': actor, 'to_team': team_id, 'amount': amount}
        row_id, previous = self._ledger_previous('contribution', receipt_key, binding, session)
        if previous is None:
            source, target = wallet_id('personal', actor), wallet_id('team', team_id)
            self._wallet_mutate('personal', actor, -amount, 0, session)
            self._wallet_mutate('team', team_id, amount, 0, session)
            self._ledger_insert(row_id, 'contribution', binding, [source, target],
                [(source + ':available', -amount), (target + ':available', amount)], session)
        return {'receipt_id': row_id, 'amount': amount,
                'personal': self._wallet_public('personal', actor, session),
                'team': self._wallet_public('team', team_id, session)}

    def _court_donate(self, actor, payload, session):
        exact(payload, ('team_id', 'amount', 'price_revision', 'confirmation'))
        confirmed(payload)
        self._actor(actor, session)
        self._price_revision(payload, session)
        team = self._team_for(actor, session)
        if team['_id'] != identifier(payload['team_id']):
            fail('forbidden', 'You can contribute only to your current Team.')
        # Serialize contributions with relocation, departure and archiving.
        self.db.court_teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        result = self._wallet_transfer(actor, team['_id'], payload['amount'], 'donate:' + actor + ':' + payload['command_id'], session)
        self._notify(team['captain_id'], 'treasury', 'Team contribution',
                     'A member contributed Crowns to the Team.', {'team_id': team['_id']}, session)
        return result

    def _court_request_cash(self, actor, payload, session):
        exact(payload, ('kind', 'package'), ('team_id',))
        self._actor(actor, session)
        package = integer(payload['package'], 1, 1000)
        if package not in PACKAGES:
            fail('invalid_input', 'Choose a listed virtual Crown package.')
        kind = payload['kind']
        if kind == 'team':
            team = self._team_for(actor, session)
            self._captain(actor, team, session)
            if identifier(payload.get('team_id')) != team['_id']:
                fail('forbidden', 'Choose your current Team wallet.')
            owner_id = team['_id']
            self.db.court_teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        elif kind == 'personal' and 'team_id' not in payload:
            owner_id = actor
        else:
            fail('invalid_input', 'Choose a personal or Team wallet.')
        if self.db.court_cash_requests.count_documents({'account_id': actor, 'state': 'pending'}, session=session) >= 3:
            fail('pending_limit', 'Wait for your pending requests to be reviewed.')
        row = {'_id': str(uuid4()), 'account_id': actor, 'kind': kind, 'owner_id': owner_id,
               'package': package, 'state': 'pending', 'generation': self._generation(session),
               'created_at': self._now(), 'revision': 0}
        self.db.court_cash_requests.insert_one(row, session=session)
        return {'request': self._cash_request_public(row)}

    @staticmethod
    def _cash_request_public(row):
        return {'id': row['_id'], **{k: row[k] for k in
                ('account_id', 'kind', 'owner_id', 'package', 'state', 'created_at', 'revision')},
                **{k: row[k] for k in ('reviewed_at', 'reason') if k in row}}

    def _review_cash(self, actor, payload, session, approve):
        exact(payload, ('request_id', 'revision', 'reason', 'confirmation'))
        confirmed(payload)
        self._admin_actor(actor, session)
        reason = text(payload['reason'], 'Review reason', 500, 3)
        row = self.db.court_cash_requests.find_one({'_id': identifier(payload['request_id'])}, session=session)
        if row is None or row['generation'] != self._generation(session):
            fail('not_found', 'This Crown request is unavailable.')
        revision(row, payload['revision'])
        if row['state'] != 'pending':
            fail('request_decided', 'This Crown request has already been reviewed.')
        if approve:
            requester = self._actor(row['account_id'], session)
            self.db.accounts.update_one({'_id': requester['_id']}, {'$inc': {'revision': 1}}, session=session)
            if row['kind'] == 'team':
                team = self._team(row['owner_id'], session)
                if team['captain_id'] != requester['_id']:
                    fail('request_changed', 'The requesting captain changed. Reject this request and review a new one.')
                self.db.court_teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
            self._wallet_credit(row['kind'], row['owner_id'], row['package'],
                                'cash-request:' + row['_id'], 'Approved virtual Crown package', session)
        after = {'state': 'approved' if approve else 'rejected', 'reviewed_at': self._now(),
                 'reviewed_by': actor, 'reason': reason}
        self.db.court_cash_requests.update_one({'_id': row['_id'], 'revision': row['revision']},
            {'$set': after, '$inc': {'revision': 1}}, session=session)
        self._audit(actor, 'approve_crowns' if approve else 'reject_crowns', row['_id'], reason,
                    {'state': 'pending'}, {**after, 'package': row['package'], 'kind': row['kind'],
                     'owner_id': row['owner_id']}, session)
        self._notify(row['account_id'], 'cash_request', 'Crown request reviewed',
                     'Your virtual Crown request was ' + after['state'] + '.',
                     {'request_id': row['_id']}, session)
        return {'request': self._cash_request_public({**row, **after, 'revision': row['revision'] + 1})}

    def _court_approve_cash(self, actor, payload, session):
        return self._review_cash(actor, payload, session, True)

    def _court_reject_cash(self, actor, payload, session):
        return self._review_cash(actor, payload, session, False)

    def _court_buy_hero(self, actor, payload, session):
        exact(payload, ('hero_id', 'price_revision', 'confirmation'))
        confirmed(payload)
        self._actor(actor, session)
        settings = self._price_revision(payload, session)
        form = admin_hero_grant_form(payload['hero_id'])
        if self.db.account_heroes.find_one({'account_id': actor, 'hero_id': payload['hero_id']}, session=session):
            fail('hero_already_owned', 'You already own this hero. Your forms and experience were preserved.')
        hold_id = 'hero:' + actor + ':' + payload['command_id']
        self._wallet_hold('personal', actor, settings['prices']['hero'], hold_id, 'Hero purchase', session)
        self.db.accounts.update_one({'_id': actor}, {'$inc': {'revision': 1}}, session=session)
        self.db.account_heroes.insert_one({'_id': str(uuid4()), 'account_id': actor,
            'hero_id': payload['hero_id'], 'forms': [form['id']], 'total_experience': 0,
            'revision': 0, 'unlocked_at': self._now(), 'unlock_source': 'shop'}, session=session)
        payment = self._wallet_capture(hold_id, session)
        return {'hero_id': payload['hero_id'], 'form_id': form['id'], 'hero_level': 1,
                'experience': 0, 'total_experience': 0, 'payment': payment,
                'wallet': self._wallet_public('personal', actor, session)}

    def _inventory_row(self, actor, item_id, session, *, create=False):
        identifier(actor)
        if not isinstance(item_id, str) or item_id not in ITEMS:
            fail('invalid_input', 'Choose a listed item.')
        name = actor + ':' + item_id
        if create:
            self.db.court_inventory.update_one({'_id': name}, {'$setOnInsert': {
                'account_id': actor, 'item_id': item_id, 'generation': self._generation(session),
                'available': 0, 'held': 0, 'revision': 0}}, upsert=True, session=session)
        row = self.db.court_inventory.find_one({'_id': name}, session=session)
        if row is not None and row['generation'] != self._generation(session):
            fail('generation_changed', 'The game generation changed. Sign in again.')
        return row

    def _inventory_mutate(self, actor, item_id, available, held, session):
        row = self._inventory_row(actor, item_id, session, create=True)
        next_available, next_held = row['available'] + available, row['held'] + held
        if next_available < 0 or next_held < 0:
            fail('item_unavailable', 'This item is unavailable or already reserved.')
        if next_available + next_held > MAX_ITEMS:
            fail('inventory_limit', 'The inventory limit would be exceeded.')
        self.db.court_inventory.update_one({'_id': row['_id'], 'revision': row['revision']},
            {'$inc': {'available': available, 'held': held, 'revision': 1}}, session=session)

    def _court_buy_item(self, actor, payload, session):
        exact(payload, ('item_id', 'quantity', 'price_revision', 'confirmation'))
        confirmed(payload)
        self._actor(actor, session)
        settings = self._price_revision(payload, session)
        item_id = payload['item_id']
        if not isinstance(item_id, str) or item_id not in ITEMS:
            fail('invalid_input', 'Choose a listed item.')
        quantity = integer(payload['quantity'], 1, 99)
        amount = integer(settings['prices']['item'] * quantity)
        hold_id = 'item:' + actor + ':' + payload['command_id']
        self._wallet_hold('personal', actor, amount, hold_id, 'Item purchase', session)
        self._inventory_mutate(actor, item_id, quantity, 0, session)
        payment = self._wallet_capture(hold_id, session)
        return {'item_id': item_id, 'quantity': quantity, 'payment': payment,
                'inventory': self._inventory_public(actor, session),
                'wallet': self._wallet_public('personal', actor, session)}

    def _inventory_public(self, actor, session=None):
        owned = {r['item_id']: r for r in self.db.court_inventory.find({'account_id': actor}, session=session)}
        return [{**deepcopy(item), 'available': owned.get(name, {}).get('available', 0),
                 'held': owned.get(name, {}).get('held', 0)} for name, item in ITEMS.items()]

    def _inventory_hold(self, actor, item_id, run_id, hold_id, session):
        """Internal preparation only; the caller validates the battle and item rules."""
        identifier(actor)
        key(run_id)
        row = self.db.court_item_holds.find_one({'_id': key(hold_id)}, session=session)
        if row is not None:
            if (row['account_id'], row['item_id'], row['run_id'], row['generation']) != (
                    actor, item_id, run_id, self._generation(session)):
                fail('transaction_conflict', 'This item hold belongs to another selection.')
            return {k: row[k] for k in ('account_id', 'item_id', 'run_id', 'state')}
        if self.db.court_item_holds.find_one({'account_id': actor, 'run_id': run_id, 'state': {'$in': ['held', 'consumed']}}, session=session):
            fail('item_limit', 'Only one item may be selected for this battle.')
        self._inventory_mutate(actor, item_id, -1, 1, session)
        row = {'_id': hold_id, 'account_id': actor, 'item_id': item_id, 'run_id': run_id,
               'generation': self._generation(session), 'state': 'held', 'created_at': self._now(), 'revision': 0}
        self.db.court_item_holds.insert_one(row, session=session)
        return {k: row[k] for k in ('account_id', 'item_id', 'run_id', 'state')}

    def _inventory_transition(self, hold_id, state, session, evidence_key=None, reason=None):
        row = self.db.court_item_holds.find_one({'_id': key(hold_id)}, session=session)
        if row is None or row['generation'] != self._generation(session):
            fail('item_unavailable', 'This item reservation is unavailable.')
        if state == 'consumed':
            evidence_key = key(evidence_key)
        if state == 'refunded':
            reason = text(reason, 'Item refund reason', 500)
        if row['state'] == state:
            field, expected = ('evidence_key', evidence_key) if state == 'consumed' else ('refund_reason', reason)
            if expected is not None and row.get(field) != expected:
                fail('transaction_conflict', 'The item was finalized with different evidence.')
            return {'item_id': row['item_id'], 'state': state}
        source = 'consumed' if state == 'refunded' else 'held'
        if row['state'] != source:
            fail('item_finalized', 'This item reservation has already been finalized.')
        self._inventory_mutate(row['account_id'], row['item_id'],
                               1 if state in ('released', 'refunded') else 0,
                               -1 if source == 'held' else 0, session)
        update = {'state': state, 'updated_at': self._now()}
        if evidence_key is not None:
            update['evidence_key'] = evidence_key
        if reason is not None:
            update['refund_reason'] = reason
        self.db.court_item_holds.update_one({'_id': hold_id, 'revision': row['revision']},
            {'$set': update, '$inc': {'revision': 1}}, session=session)
        return {'item_id': row['item_id'], 'state': state}

    def _inventory_consume(self, hold_id, evidence_key, session):
        return self._inventory_transition(hold_id, 'consumed', session, evidence_key=evidence_key)

    def _inventory_release(self, hold_id, session):
        return self._inventory_transition(hold_id, 'released', session)

    def _inventory_refund(self, hold_id, reason, session):
        return self._inventory_transition(hold_id, 'refunded', session, reason=reason)

    def _quota_row(self, kind, owner_id, session, *, day=None, create=False):
        if kind not in ('attack', 'plan'):
            fail('invalid_input', 'Choose an attack or plan allowance.')
        identifier(owner_id)
        day = day or self._now().date().isoformat()
        name = f'{kind}:{owner_id}:{day}'
        if create:
            self.db.court_quotas.update_one({'_id': name}, {'$setOnInsert': {'kind': kind,
                'owner_id': owner_id, 'day': day, 'used': 0, 'reserved': 0, 'extra': 0, 'revision': 0}},
                upsert=True, session=session)
        return self.db.court_quotas.find_one({'_id': name}, session=session)

    def _quota_public(self, kind, owner_id, session=None):
        day = self._now().date().isoformat()
        row = self._quota_row(kind, owner_id, session, day=day) or {'used': 0, 'reserved': 0, 'extra': 0}
        limits = self._settings(session)['limits']
        base = limits['attacks_per_day' if kind == 'attack' else 'plans_per_day']
        return {'kind': kind, 'owner_id': owner_id, 'day': day, 'base': base,
                **{k: row[k] for k in ('used', 'reserved', 'extra')},
                'remaining': max(0, base + row['extra'] - row['used'] - row['reserved']),
                'resets_at': datetime.combine(datetime.fromisoformat(day).date() + timedelta(days=1),
                                              datetime.min.time(), timezone.utc)}

    def _quota_reserve(self, kind, owner_id, reservation_id, session):
        reference = key(reservation_id)
        previous = self.db.court_quota_holds.find_one({'_id': reference}, session=session)
        if previous is not None:
            if (previous['kind'], previous['owner_id']) != (kind, owner_id):
                fail('transaction_conflict', 'This trial reservation belongs to another action.')
            return {k: previous[k] for k in ('kind', 'owner_id', 'day', 'state')}
        row = self._quota_row(kind, owner_id, session, create=True)
        base = self._settings(session)['limits']['attacks_per_day' if kind == 'attack' else 'plans_per_day']
        if row['used'] + row['reserved'] >= base + row['extra']:
            fail('daily_limit', 'No trials remain today.')
        self.db.court_quotas.update_one({'_id': row['_id'], 'revision': row['revision']},
            {'$inc': {'reserved': 1, 'revision': 1}}, session=session)
        held = {'_id': reference, 'kind': kind, 'owner_id': owner_id, 'day': row['day'],
                'state': 'reserved', 'created_at': self._now(), 'revision': 0}
        self.db.court_quota_holds.insert_one(held, session=session)
        return {k: held[k] for k in ('kind', 'owner_id', 'day', 'state')}

    def _quota_commit(self, reservation_id, session):
        row = self.db.court_quota_holds.find_one({'_id': key(reservation_id)}, session=session)
        if row is None:
            fail('trial_unavailable', 'The trial reservation is unavailable.')
        if row['state'] == 'used':
            return {k: row[k] for k in ('kind', 'owner_id', 'day', 'state')}
        if row['state'] != 'reserved':
            fail('trial_finalized', 'The trial reservation was already finalized.')
        quota = self._quota_row(row['kind'], row['owner_id'], session, day=row['day'])
        if quota is None or quota['reserved'] < 1:
            fail('trial_unavailable', 'The trial reservation no longer matches its daily allowance.')
        self.db.court_quotas.update_one({'_id': quota['_id'], 'revision': quota['revision']},
            {'$inc': {'reserved': -1, 'used': 1, 'revision': 1}}, session=session)
        self.db.court_quota_holds.update_one({'_id': row['_id']},
            {'$set': {'state': 'used', 'updated_at': self._now()}, '$inc': {'revision': 1}}, session=session)
        return {'kind': row['kind'], 'owner_id': row['owner_id'], 'day': row['day'], 'state': 'used'}

    def _quota_release(self, reservation_id, session, *, restore_used=False):
        row = self.db.court_quota_holds.find_one({'_id': key(reservation_id)}, session=session)
        if row is None:
            fail('trial_unavailable', 'The trial reservation is unavailable.')
        target = 'restored' if restore_used else 'released'
        if row['state'] == target:
            return {'state': target}
        source, counter = ('used', 'used') if restore_used else ('reserved', 'reserved')
        if row['state'] != source:
            fail('trial_finalized', 'The trial reservation was already finalized.')
        quota = self._quota_row(row['kind'], row['owner_id'], session, day=row['day'])
        if quota is None or quota[counter] < 1:
            fail('trial_unavailable', 'The daily allowance no longer matches its reservation.')
        self.db.court_quotas.update_one({'_id': quota['_id'], 'revision': quota['revision']},
            {'$inc': {counter: -1, 'revision': 1}}, session=session)
        self.db.court_quota_holds.update_one({'_id': row['_id']},
            {'$set': {'state': target, 'updated_at': self._now()}, '$inc': {'revision': 1}}, session=session)
        return {'state': target}

    def _court_buy_trial(self, actor, payload, session):
        exact(payload, ('kind', 'price_revision', 'confirmation'), ('account_id',))
        confirmed(payload)
        self._actor(actor, session)
        settings = self._price_revision(payload, session)
        team = self._team_for(actor, session)
        self._captain(actor, team, session)
        kind = payload['kind']
        if kind == 'attack':
            owner_id = identifier(payload.get('account_id'))
            if owner_id not in {m['account_id'] for m in team['members']}:
                fail('forbidden', 'Extra attacks are available only for current Team members.')
            self._actor(owner_id, session)
            maximum, price = settings['limits']['extra_attacks_per_day'], settings['prices']['extra_attack']
        elif kind == 'plan' and 'account_id' not in payload:
            owner_id = team['_id']
            maximum, price = settings['limits']['extra_plans_per_day'], settings['prices']['extra_plan']
        else:
            fail('invalid_input', 'Choose an attack or plan allowance.')
        row = self._quota_row(kind, owner_id, session, create=True)
        if row['extra'] >= maximum:
            fail('extra_trial_limit', 'The maximum extra trials for today have been purchased.')
        self.db.court_teams.update_one({'_id': team['_id']}, {'$inc': {'revision': 1}}, session=session)
        hold_id = 'extra-trial:' + actor + ':' + payload['command_id']
        self._wallet_hold('team', team['_id'], price, hold_id, 'Extra daily ' + kind + ' trial', session)
        self.db.court_quotas.update_one({'_id': row['_id'], 'revision': row['revision']},
            {'$inc': {'extra': 1, 'revision': 1}}, session=session)
        self._wallet_capture(hold_id, session)
        return {'quota': self._quota_public(kind, owner_id, session),
                'wallet': self._wallet_public('team', team['_id'], session)}

    @staticmethod
    def _history_cursor(row):
        value = json.dumps([row['created_at'].isoformat(), row['_id']], separators=(',', ':')).encode()
        return base64.urlsafe_b64encode(value).decode().rstrip('=')

    def _wallet_view(self, kind, owner_id, session=None, after=''):
        query = {'wallet_ids': wallet_id(kind, owner_id)}
        if after:
            try:
                if not isinstance(after, str) or len(after) > 256 or not re.fullmatch(r'[A-Za-z0-9_-]+', after):
                    raise ValueError()
                stamp, row_id = json.loads(base64.urlsafe_b64decode(after + '=' * (-len(after) % 4)))
                stamp = datetime.fromisoformat(stamp)
                if stamp.tzinfo is None or not re.fullmatch(r'[0-9a-f]{64}', row_id):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                fail('invalid_input', 'The wallet page is invalid.')
            query['$or'] = [{'created_at': {'$lt': stamp}}, {'created_at': stamp, '_id': {'$gt': row_id}}]
        rows = list(self.db.court_ledger.find(query, session=session).sort([('created_at', -1), ('_id', 1)]).limit(26))
        return {'wallet': self._wallet_public(kind, owner_id, session),
                'transactions': [{'id': r['_id'], 'operation': r['operation'],
                    'details': r['binding'], 'created_at': r['created_at']} for r in rows[:25]],
                'next': self._history_cursor(rows[24]) if len(rows) > 25 else ''}

    def _court_wallet(self, actor, payload, session=None):
        exact(payload, (), ('kind', 'after'))
        self._actor(actor, session)
        kind = payload.get('kind', 'personal')
        owner_id = self._team_for(actor, session)['_id'] if kind == 'team' else actor
        result = self._wallet_view(kind, owner_id, session, payload.get('after', ''))
        requests = self.db.court_cash_requests.find({'kind': kind, 'owner_id': owner_id}, session=session).sort([('created_at', -1), ('_id', 1)]).limit(25)
        result['requests'] = [self._cash_request_public(row) for row in requests]
        if kind == 'personal':
            result['inventory'] = self._inventory_public(actor, session)
            result['attacks'] = self._quota_public('attack', actor, session)
        else:
            result['plans'] = self._quota_public('plan', owner_id, session)
        return result

    def _court_shop(self, actor, payload, session=None):
        exact(payload, (), ('q', 'filter', 'after'))
        self._actor(actor, session)
        query = text(payload.get('q', ''), 'Search', 80, 0).casefold()
        chosen = payload.get('filter', 'all')
        after = payload.get('after', '')
        if chosen not in ('all', 'owned', 'locked') or not isinstance(after, str) or not re.fullmatch(r'[a-z0-9_-]{0,80}', after):
            fail('invalid_input', 'The shop filter is invalid.')
        catalog, _ = load_catalog()
        owned = {r['hero_id']: r for r in self.db.account_heroes.find({'account_id': actor}, session=session)}
        rows = [h for h in sorted(catalog['heroes'], key=lambda h: h['id'])
                if h['id'] > after and (not query or query in h['name'].casefold())
                and (chosen == 'all' or (h['id'] in owned) == (chosen == 'owned'))]
        settings = self._settings(session)
        heroes = []
        for hero in rows[:24]:
            form = admin_hero_grant_form(hero['id'])
            heroes.append({'hero_id': hero['id'], 'name': hero['name'], 'owned': hero['id'] in owned,
                'form_id': form['id'], 'unit_type': form['unit_type'], 'native_level': form['native_level'],
                'price': settings['prices']['hero'],
                **(hero_progress(owned[hero['id']]['total_experience']) if hero['id'] in owned else
                   {'hero_level': 1, 'experience': 0, 'total_experience': 0})})
        return {'price_revision': settings['revision'], 'prices': deepcopy(settings['prices']),
                'wallet': self._wallet_public('personal', actor, session), 'heroes': heroes,
                'next': rows[23]['id'] if len(rows) > 24 else '',
                'items': [{**item, 'price': settings['prices']['item']} for item in self._inventory_public(actor, session)],
                'packages': list(PACKAGES), 'virtual_only': True}

    def _campaign_cash(self, actor, campaign_id, scenario_id, session):
        """Trusted story settlement only; one grant per campaign/scenario, not per save."""
        self._actor(actor, session)
        source = digest(text(campaign_id, 'Campaign', 200), text(scenario_id, 'Scenario', 200))
        claim_id = digest('campaign', actor, source)
        existing = self.db.court_reward_claims.find_one({'_id': claim_id}, session=session)
        if existing is not None:
            return {'amount': existing['amount'], 'already_awarded': True}
        amount = integer(self._settings(session)['limits']['campaign_cash'])
        self._wallet_credit('personal', actor, amount, 'campaign:' + claim_id,
                            'First verified scenario victory', session)
        self.db.court_reward_claims.insert_one({'_id': claim_id, 'kind': 'campaign', 'owner_id': actor,
            'generation': self._generation(session), 'source_id': source, 'amount': amount,
            'created_at': self._now()}, session=session)
        return {'amount': amount, 'already_awarded': False}

    def _battle_cash(self, actor, run_id, outcome, session, *, mode='plan', opponent_team_id=None):
        """Called only from a verified native Court settlement in its transaction.

        Wallet revision updates serialize the daily cap even for zero-value
        awards. Forfeits, cancellations and individual Rooms do not call this
        helper. A result is bound to its original mode, opponent and outcome.
        """
        identifier(actor)
        key(run_id)
        if outcome not in ('win', 'loss', 'draw') or mode not in ('normal', 'plan', 'competition'):
            fail('invalid_input', 'The battle reward classification is invalid.')
        if mode == 'plan':
            identifier(opponent_team_id)
        elif opponent_team_id is not None:
            identifier(opponent_team_id)
        self._wallet_owner('personal', actor, session)
        generation = self._generation(session)
        claim_id = digest('battle', generation, actor, run_id)
        binding = {'outcome': outcome, 'mode': mode, 'opponent_team_id': opponent_team_id}
        old = self.db.court_reward_claims.find_one({'_id': claim_id}, session=session)
        if old is not None:
            if old['generation'] != generation or any(old.get(k) != v for k, v in binding.items()):
                fail('transaction_conflict', 'This battle already has a different reward receipt.')
            return {'amount': old['amount'], 'already_awarded': True}
        day = self._now().date().isoformat()
        query = {'kind': 'battle', 'owner_id': actor, 'generation': generation, 'day': day}
        previous = list(self.db.court_reward_claims.find(query, session=session))
        earned = sum(r['amount'] for r in previous)
        allowance = max(0, integer(self._settings(session)['limits']['battle_cash_per_day']) - earned)
        repeated = mode == 'plan' and any(r.get('mode') == 'plan' and
            r.get('opponent_team_id') == opponent_team_id for r in previous)
        amount = 0 if repeated else min({'win': 10, 'loss': 0, 'draw': 5}[outcome], allowance)
        self._wallet_credit('personal', actor, amount, 'battle:' + claim_id,
                            'Verified Team battle reward', session)
        self.db.court_reward_claims.insert_one({'_id': claim_id, 'kind': 'battle', 'owner_id': actor,
            'generation': generation, 'source_id': run_id, 'amount': amount,
            'created_at': self._now(), 'day': day, **binding}, session=session)
        return {'amount': amount, 'already_awarded': False}
