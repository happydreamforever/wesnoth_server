"""Explicit fresh-database bootstrap. Never clears or converts an existing game."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from pymongo import UpdateOne
from ..schema import SCHEMA_3_SCHEMAS
from ..auth import bootstrap_auth_schema
from .base import PRICES, LIMITS
from .geography import catalogue


def object_schema(required, properties):
    return {'$jsonSchema': {'bsonType': 'object', 'required': list(required), 'properties': properties}}


STRING = {'bsonType': 'string'}
NUMBER = {'bsonType': ['int', 'long'], 'minimum': 0}
DATE = {'bsonType': 'date'}
NULL_ID = {'bsonType': ['string', 'null']}
BASE_NAMES = ('accounts', 'account_heroes', 'story_checkpoints', 'game_runs', 'casual_games',
              'casual_tickets', 'network_battle_reservations', 'admin_audit', 'schema_metadata')
SCHEMAS = {name: deepcopy(SCHEMA_3_SCHEMAS[name]) for name in BASE_NAMES}
SCHEMAS['network_battle_reservations']['$jsonSchema']['properties']['kind']['enum'] = ['court', 'individual']
SCHEMAS['court_teams'] = object_schema(('_id', 'name', 'name_key', 'area_id', 'captain_id',
    'members', 'status', 'experience', 'level', 'revision', 'allowances'), {
    '_id': STRING, 'name': STRING, 'name_key': STRING, 'area_id': STRING,
    'captain_id': NULL_ID, 'members': {'bsonType': 'array', 'maxItems': 10,
        'items': {'bsonType': 'object', 'required': ['account_id', 'joined_at'],
                  'properties': {'account_id': STRING, 'joined_at': DATE}}},
    'status': {'enum': ['active', 'archived']}, 'experience': NUMBER, 'level': NUMBER,
    'revision': NUMBER, 'allowances': {'bsonType': 'object'}})
SCHEMAS['court_areas'] = object_schema(('_id', 'name', 'number', 'enabled', 'mode', 'team_count', 'revision'), {
    '_id': STRING, 'name': STRING, 'number': NUMBER, 'enabled': {'bsonType': 'bool'},
    'mode': {'enum': ['auto', 'on', 'off']}, 'team_count': NUMBER, 'revision': NUMBER})
SCHEMAS['court_castles'] = object_schema(('_id', 'area_id', 'name', 'role', 'enabled', 'mode',
    'owner_team_id', 'reservation_id', 'event_id', 'revision'), {'_id': STRING,
    'area_id': STRING, 'name': STRING, 'role': {'enum': ['normal', 'plan', 'competition']},
    'enabled': {'bsonType': 'bool'}, 'mode': {'enum': ['auto', 'on', 'off']},
    'owner_team_id': NULL_ID, 'reservation_id': NULL_ID, 'event_id': NULL_ID, 'revision': NUMBER})
SCHEMAS['court_applications'] = object_schema(('_id', 'account_id', 'team_id', 'state', 'revision',
    'hold_id', 'created_at', 'expires_at'), {'_id': STRING, 'account_id': STRING, 'team_id': STRING,
    'state': {'enum': ['pending', 'approved', 'rejected', 'withdrawn', 'expired']},
    'revision': NUMBER, 'hold_id': STRING, 'created_at': DATE, 'expires_at': DATE})
SCHEMAS['court_commands'] = object_schema(('_id', 'account_id', 'command_id', 'operation', 'digest',
    'result', 'created_at'), {'_id': STRING, 'account_id': STRING, 'command_id': STRING,
    'operation': STRING, 'digest': STRING, 'result': {'bsonType': 'object'}, 'created_at': DATE})
SCHEMAS['court_settings'] = object_schema(('_id', 'revision'), {'_id': STRING, 'revision': NUMBER})
SCHEMAS['court_notifications'] = object_schema(('_id', 'account_id', 'kind', 'title', 'message',
    'target', 'created_at', 'revision'), {'_id': STRING, 'account_id': STRING, 'kind': STRING,
    'title': STRING, 'message': STRING, 'target': {'bsonType': 'object'}, 'created_at': DATE, 'revision': NUMBER})
SCHEMAS['court_history'] = object_schema(('_id', 'team_id', 'kind', 'title', 'data', 'created_at'), {
    '_id': STRING, 'team_id': STRING, 'kind': STRING, 'title': STRING,
    'data': {'bsonType': 'object'}, 'created_at': DATE})
SCHEMAS['court_rooms'] = object_schema(('_id', 'generation', 'owner_id', 'state', 'revision', 'expires_at'), {
    '_id': STRING, 'generation': STRING, 'owner_id': STRING, 'state': {'enum': ['waiting', 'playing', 'closed']},
    'revision': NUMBER, 'created_at': DATE, 'expires_at': DATE})
SCHEMAS['court_room_admissions'] = object_schema(('_id', 'account_id', 'kind', 'game_id',
    'database_generation', 'native_generation', 'hold_id', 'state', 'fee', 'expires_at'), {
    '_id': STRING, 'account_id': STRING, 'kind': {'enum': ['create', 'join']}, 'game_id': STRING,
    'database_generation': STRING, 'native_generation': NULL_ID, 'hold_id': STRING,
    'state': {'enum': ['reserved', 'admitted', 'started', 'closed']}, 'fee': NUMBER, 'expires_at': DATE})


def bootstrap_court_schema(db):
    from .wallet_schema import SCHEMAS as WALLET_SCHEMAS, bootstrap_indexes as wallet_indexes
    from .battle_schema import SCHEMAS as BATTLE_SCHEMAS, bootstrap_indexes as battle_indexes
    previous = db.schema_metadata.find_one({'_id': 'alliance'})
    existing = set(db.list_collection_names())
    if previous and previous.get('version') != 5:
        raise RuntimeError('Court requires a new empty database. Preserve the previous runtime and backup.')
    if not previous and any(db[name].find_one({}, {'_id': 1}) for name in existing if not name.startswith('system.')):
        raise RuntimeError('The database contains existing records; fresh initialization refused.')
    all_schemas = {**SCHEMAS, **WALLET_SCHEMAS, **BATTLE_SCHEMAS}
    # Establish an owned generation before any resumable population is written.
    if 'schema_metadata' not in existing:
        db.create_collection('schema_metadata', validator=SCHEMAS['schema_metadata'])
        existing.add('schema_metadata')
    db.schema_metadata.update_one({'_id': 'alliance'}, {'$setOnInsert': {'version': 5,
        'database_generation': str(uuid4()), 'created_at': datetime.now(timezone.utc),
        'court_initialized': False}}, upsert=True)
    for name, validator in all_schemas.items():
        if name not in existing:
            db.create_collection(name, validator=validator, validationLevel='strict', validationAction='error')
        else:
            db.command('collMod', name, validator=validator, validationLevel='strict', validationAction='error')
    bootstrap_auth_schema(db)
    db.accounts.create_index('username_key', unique=True)
    db.account_heroes.create_index([('account_id', 1), ('hero_id', 1)], unique=True)
    db.story_checkpoints.create_index([('run_id', 1), ('sequence', 1)], unique=True)
    db.casual_tickets.create_index('expires_at', expireAfterSeconds=0)
    db.game_runs.create_index([('participants.account_id', 1), ('created_at', -1)])
    db.court_teams.create_index('name_key', unique=True)
    db.court_teams.create_index('members.account_id', unique=True,
        partialFilterExpression={'members.account_id': {'$exists': True}})
    db.court_teams.create_index([('area_id', 1), ('status', 1)])
    db.court_castles.create_index([('area_id', 1), ('role', 1)])
    db.court_castles.create_index('owner_team_id')
    db.court_applications.create_index('account_id', unique=True, partialFilterExpression={'state': 'pending'})
    db.court_applications.create_index([('state', 1), ('expires_at', 1)])
    db.court_notifications.create_index([('account_id', 1), ('created_at', -1), ('_id', 1)])
    db.court_history.create_index([('team_id', 1), ('created_at', -1), ('_id', 1)])
    db.court_commands.create_index([('account_id', 1), ('command_id', 1)], unique=True)
    db.court_room_admissions.create_index([('account_id', 1), ('state', 1)])
    db.court_room_admissions.create_index([('game_id', 1), ('native_generation', 1)])
    db.court_room_admissions.create_index([('state', 1), ('expires_at', 1)])
    db.court_rooms.create_index([('generation', 1), ('state', 1)])
    wallet_indexes(db)
    battle_indexes(db)
    db.court_settings.update_one({'_id': 'rules'}, {'$setOnInsert': {
        'revision': 0, 'prices': deepcopy(PRICES), 'limits': deepcopy(LIMITS)}}, upsert=True)
    db.court_settings.update_one({'_id': 'population'}, {'$setOnInsert': {'revision': 0}}, upsert=True)
    data = catalogue()
    db.court_areas.bulk_write([UpdateOne({'_id': row['id']}, {'$setOnInsert': {
        'name': row['name'], 'number': row['number'], 'realm_id': row['realm_id'],
        'realm_name': row['realm_name'], 'enabled': row['id'] == 'A001', 'mode': 'auto',
        'team_count': 0, 'below_since': None, 'revision': 0}}, upsert=True) for row in data['areas']])
    for area in data['areas']:
        operations, normal_count = [], 0
        for castle in data['castle_template']:
            if castle['role'] == 'normal':
                normal_count += 1
            operations.append(UpdateOne({'_id': area['id'] + '-' + castle['id']}, {'$setOnInsert': {
                'area_id': area['id'], 'name': castle['name'], 'role': castle['role'],
                'art_class': castle['art_class'], 'mode': 'auto',
                'enabled': area['id'] == 'A001' and castle['role'] == 'normal' and normal_count <= 4,
                'owner_team_id': None, 'protected_until': None, 'reservation_id': None,
                'event_id': None, 'below_since': None, 'revision': 0}}, upsert=True))
        db.court_castles.bulk_write(operations)
    db.schema_metadata.update_one({'_id': 'alliance'}, {'$set': {'court_initialized': True}})
    return {'schema_version': 5, 'areas': 128, 'castles': 8192, 'fresh_game': True}
