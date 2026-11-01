"""Schema and indexes for the replacement Court battle lifecycles."""

STRING = {'bsonType': 'string'}
INTEGER = {'bsonType': ['int', 'long'], 'minimum': 0}
DATE = {'bsonType': 'date'}


def record(required, fields):
    return {'$jsonSchema': {'bsonType': 'object', 'required': ['_id', *required],
                           'properties': {'_id': STRING, **fields}}}


SCHEMAS = {
    'court_matches': record(['kind', 'state', 'revision', 'area_id', 'castle_id',
                             'team_ids', 'settings', 'seats', 'created_at', 'generation'], {
        'kind': {'enum': ['attack', 'plan', 'competition']},
        'state': {'enum': ['proposed', 'response', 'scheduled', 'queued', 'preparing',
                           'running', 'paused', 'disputed', 'completed', 'cancelled']},
        'revision': INTEGER, 'area_id': STRING, 'castle_id': STRING,
        'generation': STRING, 'created_at': DATE,
        'team_ids': {'bsonType': 'array', 'items': STRING, 'maxItems': 2, 'minItems': 2,
                     'uniqueItems': True},
        'settings': {'bsonType': 'object'},
        'seats': {'bsonType': 'array', 'maxItems': 8, 'items': {'bsonType': 'object'}},
    }),
    'court_competitions': record(['castle_id', 'area_id', 'name', 'state', 'revision',
                                  'settings', 'entry_fee', 'entries', 'round', 'rounds'], {
        'castle_id': STRING, 'area_id': STRING, 'name': STRING, 'revision': INTEGER,
        'state': {'enum': ['registration', 'round_ready', 'playing', 'completed', 'cancelled']},
        'settings': {'bsonType': 'object'}, 'entry_fee': INTEGER, 'round': INTEGER,
        'entries': {'bsonType': 'array', 'maxItems': 32, 'items': {'bsonType': 'object'}},
        'rounds': {'bsonType': 'array', 'maxItems': 5, 'items': {'bsonType': 'object'}},
    }),
    'court_defenses': record(['team_id', 'owner_id', 'selection', 'status', 'revision'], {
        'team_id': STRING, 'owner_id': STRING, 'selection': {'bsonType': 'object'},
        'status': {'enum': ['offered', 'approved', 'withdrawn']}, 'revision': INTEGER,
    }),
    'court_seats': record(['match_id', 'team_id', 'created_at'], {
        'match_id': STRING, 'team_id': STRING, 'created_at': DATE,
    }),
    'court_castle_claims': record(['castle_id', 'team_id', 'match_id', 'created_at'], {
        'castle_id': STRING, 'team_id': STRING, 'match_id': STRING, 'created_at': DATE,
    }),
    'court_attack_budgets': record(['team_id', 'account_id', 'day', 'used', 'held'], {
        'team_id': STRING, 'account_id': STRING, 'day': STRING, 'used': INTEGER, 'held': INTEGER,
    }),
    'court_attack_approvals': record(['team_id', 'account_id', 'castle_id', 'amount',
                                     'state', 'expires_at', 'revision'], {
        'team_id': STRING, 'account_id': STRING, 'castle_id': STRING, 'amount': INTEGER,
        'state': {'enum': ['pending', 'approved', 'used', 'rejected']},
        'expires_at': DATE, 'revision': INTEGER,
    }),
    'court_battle_receipts': record(['match_id', 'generation', 'winner_team_id',
                                    'draw', 'reason', 'native_verified', 'created_at'], {
        'match_id': STRING, 'generation': STRING,
        'winner_team_id': {'bsonType': ['string', 'null']},
        'draw': {'bsonType': 'bool'}, 'reason': STRING,
        'native_verified': {'bsonType': 'bool'}, 'created_at': DATE,
    }),
    'court_castle_income': record(['castle_id', 'team_id', 'day', 'amount'], {
        'castle_id': STRING, 'team_id': STRING, 'day': STRING, 'amount': INTEGER,
    }),
    'court_team_income_days': record(['team_id', 'day', 'amount'], {
        'team_id': STRING, 'day': STRING, 'amount': INTEGER,
    }),
}


def bootstrap_indexes(db):
    db.court_matches.create_index([('state', 1), ('scheduled_at', 1), ('created_at', 1)])
    db.court_matches.create_index([('team_ids', 1), ('created_at', -1), ('_id', 1)])
    db.court_matches.create_index([('castle_id', 1), ('created_at', -1)])
    db.court_competitions.create_index([('castle_id', 1), ('state', 1)])
    db.court_competitions.create_index([('area_id', 1), ('created_at', -1)])
    db.court_defenses.create_index([('team_id', 1), ('status', 1)])
    db.court_defenses.create_index([('owner_id', 1), ('status', 1)])
    db.court_castle_claims.create_index('castle_id', unique=True)
    db.court_castle_claims.create_index('team_id')
    db.court_seats.create_index('match_id')
    db.court_battle_receipts.create_index('match_id', unique=True)
    db.court_attack_approvals.create_index([('team_id', 1), ('state', 1)])
