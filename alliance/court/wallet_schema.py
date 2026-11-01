"""Strict durable records for virtual Crowns, inventories and daily allowances."""
from __future__ import annotations

MAX_CROWNS = 9_000_000_000_000
MAX_ITEMS = 100_000
STRING = {'bsonType': 'string'}
DATE = {'bsonType': 'date'}
INTEGER = {'bsonType': ['int', 'long'], 'minimum': 0, 'maximum': MAX_CROWNS}
SIGNED = {'bsonType': ['int', 'long'], 'minimum': -MAX_CROWNS, 'maximum': MAX_CROWNS}
KIND = {'enum': ['personal', 'team']}


def record(required, fields):
    return {'$jsonSchema': {'bsonType': 'object', 'required': ['_id', *required],
                           'properties': {'_id': STRING, **fields}, 'additionalProperties': False}}


SCHEMAS = {
    'court_wallets': record(['kind', 'owner_id', 'generation', 'available', 'held', 'revision'], {
        'kind': KIND, 'owner_id': STRING, 'generation': STRING,
        'available': INTEGER, 'held': INTEGER, 'revision': INTEGER,
    }),
    'court_holds': record(['kind', 'owner_id', 'generation', 'amount', 'purpose', 'state',
                          'created_at', 'revision'], {
        'kind': KIND, 'owner_id': STRING, 'generation': STRING, 'amount': INTEGER,
        'purpose': STRING, 'state': {'enum': ['held', 'captured', 'released', 'refunded']},
        'created_at': DATE, 'updated_at': DATE, 'revision': INTEGER,
        'refund_reason': STRING,
    }),
    'court_ledger': record(['generation', 'operation', 'binding', 'wallet_ids', 'postings',
                           'created_at'], {
        'generation': STRING, 'operation': STRING, 'binding': {'bsonType': 'object'},
        'wallet_ids': {'bsonType': 'array', 'items': STRING, 'uniqueItems': True, 'maxItems': 2},
        'postings': {'bsonType': 'array', 'minItems': 2, 'maxItems': 4, 'items': {
            'bsonType': 'object', 'required': ['account', 'amount'],
            'properties': {'account': STRING, 'amount': SIGNED}, 'additionalProperties': False}},
        'created_at': DATE,
    }),
    'court_cash_requests': record(['account_id', 'kind', 'owner_id', 'package', 'state',
                                  'generation', 'created_at', 'revision'], {
        'account_id': STRING, 'kind': KIND, 'owner_id': STRING,
        'package': {'enum': [100, 500, 1000]},
        'state': {'enum': ['pending', 'approved', 'rejected']},
        'generation': STRING, 'created_at': DATE, 'revision': INTEGER,
        'reviewed_at': DATE, 'reviewed_by': STRING, 'reason': STRING,
    }),
    'court_inventory': record(['account_id', 'item_id', 'generation', 'available', 'held', 'revision'], {
        'account_id': STRING, 'item_id': {'enum': ['healing_draught', 'remedy']},
        'generation': STRING,
        'available': {'bsonType': ['int', 'long'], 'minimum': 0, 'maximum': MAX_ITEMS},
        'held': {'bsonType': ['int', 'long'], 'minimum': 0, 'maximum': MAX_ITEMS},
        'revision': INTEGER,
    }),
    'court_item_holds': record(['account_id', 'item_id', 'run_id', 'generation', 'state',
                               'created_at', 'revision'], {
        'account_id': STRING, 'item_id': {'enum': ['healing_draught', 'remedy']},
        'run_id': STRING, 'generation': STRING,
        'state': {'enum': ['held', 'consumed', 'released', 'refunded']},
        'created_at': DATE, 'updated_at': DATE, 'revision': INTEGER,
        'evidence_key': STRING, 'refund_reason': STRING,
    }),
    'court_quotas': record(['kind', 'owner_id', 'day', 'used', 'reserved', 'extra', 'revision'], {
        'kind': {'enum': ['attack', 'plan']}, 'owner_id': STRING,
        'day': {'bsonType': 'string', 'pattern': '^\\d{4}-\\d{2}-\\d{2}$'},
        'used': INTEGER, 'reserved': INTEGER, 'extra': INTEGER, 'revision': INTEGER,
    }),
    'court_quota_holds': record(['kind', 'owner_id', 'day', 'state', 'created_at', 'revision'], {
        'kind': {'enum': ['attack', 'plan']}, 'owner_id': STRING, 'day': STRING,
        'state': {'enum': ['reserved', 'used', 'released', 'restored']},
        'created_at': DATE, 'updated_at': DATE, 'revision': INTEGER,
    }),
    'court_reward_claims': record(['kind', 'owner_id', 'generation', 'source_id', 'amount', 'created_at'], {
        'kind': STRING, 'owner_id': STRING, 'generation': STRING, 'source_id': STRING,
        'amount': INTEGER, 'created_at': DATE, 'day': STRING,
        'outcome': {'enum': ['win', 'loss', 'draw']},
        'mode': {'enum': ['normal', 'plan', 'competition']},
        'opponent_team_id': {'bsonType': ['string', 'null']},
    }),
}


def bootstrap_indexes(db):
    db.court_wallets.create_index([('kind', 1), ('owner_id', 1)], unique=True, name='court_wallet_owner')
    db.court_holds.create_index([('kind', 1), ('owner_id', 1), ('state', 1)], name='court_pending_funds')
    db.court_ledger.create_index([('wallet_ids', 1), ('created_at', -1), ('_id', 1)], name='court_wallet_history')
    db.court_cash_requests.create_index([('account_id', 1), ('state', 1), ('created_at', -1)], name='court_cash_requests')
    db.court_cash_requests.create_index([('state', 1), ('created_at', 1)], name='court_cash_review')
    db.court_inventory.create_index([('account_id', 1), ('item_id', 1)], unique=True, name='court_inventory_owner')
    db.court_item_holds.create_index([('run_id', 1), ('account_id', 1)], unique=True, name='court_one_item_per_battle',
        partialFilterExpression={'state': {'$in': ['held', 'consumed']}})
    db.court_quotas.create_index([('kind', 1), ('owner_id', 1), ('day', 1)], unique=True, name='court_daily_quota')
    db.court_quota_holds.create_index([('kind', 1), ('owner_id', 1), ('state', 1)], name='court_quota_reservations')
    db.court_reward_claims.create_index([('kind', 1), ('owner_id', 1), ('source_id', 1)], unique=True, name='court_reward_once')

    db.court_reward_claims.create_index([('owner_id', 1), ('kind', 1), ('day', 1)], name='court_reward_daily')
