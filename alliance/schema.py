"""Explicit schema/index bootstrap for the dedicated local Alliance database."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from pymongo import ASCENDING
from pymongo.errors import CollectionInvalid

from .rules import MAPS

SCHEMA_VERSION = 3


def _object(required, properties):
    return {'bsonType': 'object', 'required': required, 'properties': properties}


STRING = {'bsonType': 'string'}
INTEGER = {'bsonType': ['int', 'long'], 'minimum': 0}
NULLABLE_STRING = {'bsonType': ['string', 'null']}
LEADER = _object(['starter_id', 'unit_type', 'level', 'experience', 'total_experience', 'advancement_choices'], {
    'starter_id': STRING, 'unit_type': STRING, 'level': INTEGER,
    'experience': INTEGER, 'total_experience': INTEGER,
    'advancement_choices': {'bsonType': 'array', 'items': STRING, 'maxItems': 3, 'uniqueItems': True},
})
SCHEMAS = {
    'accounts': {'$jsonSchema': _object(
        ['_id', 'username', 'username_key', 'password_hash', 'role', 'status',
         'database_generation', 'active_run_id', 'revision'], {
            '_id': STRING, 'username': STRING, 'username_key': STRING, 'password_hash': STRING,
            'role': {'enum': ['player', 'admin']}, 'status': {'enum': ['active', 'suspended']},
            'database_generation': STRING,
            'active_run_id': NULLABLE_STRING, 'revision': INTEGER,
        })},
    'teams': {'$and': [
        {'$jsonSchema': _object(
            ['_id', 'name', 'name_key', 'area_id', 'captain_id', 'members', 'join_requests',
             'experience', 'level', 'rating', 'active_run_id', 'status', 'revision'], {
                '_id': STRING, 'name': STRING, 'name_key': STRING, 'area_id': STRING,
                'captain_id': NULLABLE_STRING, 'members': {'bsonType': 'array', 'maxItems': 8,
                    'items': _object(['account_id', 'joined_at'], {'account_id': STRING,
                                                                 'joined_at': {'bsonType': 'date'}})},
                'join_requests': {'bsonType': 'array', 'maxItems': 64, 'uniqueItems': True, 'items': STRING},
                'experience': INTEGER, 'level': INTEGER,
                'rating': {'bsonType': ['int', 'long']}, 'active_run_id': NULLABLE_STRING,
                'orders': {'bsonType': 'array', 'maxItems': 50, 'items': _object(
                    ['id', 'author_id', 'author_name', 'text', 'created_at'], {
                        'id': STRING, 'author_id': STRING, 'author_name': STRING,
                        'text': {'bsonType': 'string', 'maxLength': 500}, 'created_at': {'bsonType': 'date'}})},
                'status': {'enum': ['active', 'archived']}, 'revision': INTEGER,
            })},
        {'$expr': {'$eq': [{'$size': '$members'}, {'$size': {'$setUnion': ['$members.account_id', []]}}]}},
        {'$expr': {'$cond': [{'$eq': ['$status', 'active']},
                            {'$in': ['$captain_id', '$members.account_id']},
                            {'$and': [{'$eq': ['$captain_id', None]}, {'$eq': [{'$size': '$members'}, 0]}]}]}},
    ]},
    'areas': {'$jsonSchema': _object(['_id', 'name', 'name_key', 'enabled', 'approved_maps'], {
        '_id': STRING, 'name': STRING, 'name_key': STRING, 'enabled': {'bsonType': 'bool'},
        'revision': INTEGER,
        'approved_maps': {'bsonType': 'array', 'items': {'enum': list(MAPS)}, 'uniqueItems': True},
    })},
    'game_runs': {'$jsonSchema': _object(['_id', 'kind', 'state', 'ruleset_version', 'participants', 'created_at'], {
        '_id': STRING, 'kind': {'enum': ['campaign', 'alliance']},
        'state': {'enum': ['draft', 'running', 'completed', 'cancelled']},
        'ruleset_version': STRING, 'participants': {'bsonType': 'array', 'maxItems': 8,
             'items': _object(['account_id'], {'account_id': STRING})}, 'created_at': {'bsonType': 'date'},
    })},
    'settlements': {'$jsonSchema': _object(['_id', 'result', 'rewards', 'created_at'], {
        '_id': STRING, 'result': {'bsonType': 'object'}, 'rewards': {'bsonType': 'object'},
        'created_at': {'bsonType': 'date'},
    })},
    'admin_audit': {'$jsonSchema': _object(['_id', 'actor_id', 'action', 'target_id', 'reason', 'created_at'], {
        '_id': STRING, 'actor_id': STRING, 'action': STRING, 'target_id': STRING,
        'reason': STRING, 'created_at': {'bsonType': 'date'},
    })},
    'schema_metadata': {'$jsonSchema': _object(['_id', 'version'], {'_id': STRING, 'version': INTEGER})},
    'account_heroes': {'$jsonSchema': _object(
        ['_id', 'account_id', 'hero_id', 'forms', 'total_experience', 'revision'], {
            '_id': STRING, 'account_id': STRING, 'hero_id': STRING,
            'forms': {'bsonType': 'array', 'items': STRING, 'uniqueItems': True, 'minItems': 1},
            'total_experience': INTEGER, 'revision': INTEGER})},
    'story_checkpoints': {'$jsonSchema': _object(
        ['_id', 'run_id', 'account_id', 'sequence', 'digest', 'result'], {
            '_id': STRING, 'run_id': STRING, 'account_id': STRING, 'sequence': INTEGER,
            'digest': STRING, 'result': {'bsonType': 'object'}})},
    'casual_games': {'$jsonSchema': _object(['_id', 'database_generation', 'players'], {
        '_id': STRING, 'database_generation': STRING, 'players': {'bsonType': 'array', 'maxItems': 99}})},
    'casual_tickets': {'$jsonSchema': _object(
        ['_id', 'account_id', 'purpose', 'expires_at', 'consumed'], {
            '_id': STRING, 'account_id': STRING, 'purpose': {'enum': ['lobby', 'hero']},
            'expires_at': {'bsonType': 'date'}, 'consumed': {'bsonType': 'bool'}})},
}


SCHEMAS['network_battle_reservations'] = {'$jsonSchema': _object(
    ['_id', 'kind', 'run_id', 'generation', 'created_at'], {
        '_id': STRING, 'kind': {'enum': ['team', 'individual']}, 'run_id': STRING,
        'generation': STRING, 'created_at': {'bsonType': 'date'}, 'expires_at': {'bsonType': 'date'}})}


# Legacy records remain byte-for-byte readable. New plans have their own strict
# shape; schema activation is explicit and never reinterprets old run history.
FLEX_SETTINGS = _object(['gold', 'base_income', 'turns', 'fog', 'shroud', 'observers'], {
    'gold': {'bsonType': ['int', 'long'], 'minimum': 0, 'maximum': 1000},
    'base_income': {'bsonType': ['int', 'long'], 'minimum': 0, 'maximum': 20},
    'turns': {'bsonType': ['int', 'long'], 'minimum': -1, 'maximum': 1000},
    'fog': {'bsonType': 'bool'}, 'shroud': {'bsonType': 'bool'}, 'observers': {'bsonType': 'bool'}})
FLEX_SLOT = _object(['side', 'kind', 'team_id', 'account_id', 'ai_faction', 'ai_leader'], {
    'side': {'bsonType': ['int', 'long'], 'minimum': 1, 'maximum': 8},
    'kind': {'enum': ['open', 'reserved', 'ai', 'closed']}, 'team_id': STRING,
    'account_id': STRING, 'ai_faction': STRING, 'ai_leader': STRING})
SCHEMAS['game_runs'] = {'$and': [SCHEMAS['game_runs'], {'$or': [
    {'plan_format': {'$exists': False}},
    {'$jsonSchema': _object(['plan_format', 'revision', 'settings', 'slots', 'team_ids', 'approvals', 'ready'], {
        'plan_format': {'enum': [2]}, 'revision': INTEGER, 'settings': FLEX_SETTINGS,
        'slots': {'bsonType': 'array', 'minItems': 4, 'maxItems': 8, 'items': FLEX_SLOT},
        'team_ids': {'bsonType': 'array', 'minItems': 2, 'maxItems': 2, 'uniqueItems': True, 'items': STRING},
        'approvals': {'bsonType': 'object'}, 'ready': {'bsonType': 'array', 'uniqueItems': True, 'maxItems': 8, 'items': STRING}})}
]}]}


def migrate_schema_2_to_3(db, backup_digest, *, checkpoint=None):
    """Resume a fenced, additive migration; caller owns the stopped runtime.

    Only validators/indexes and metadata change. Neither records, identity nor
    account reservations are rewritten. The checkpoint hook enables real fault
    injection against a disposable replica set.
    """
    import re
    if not isinstance(backup_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', backup_digest):
        raise RuntimeError('A verified cold backup digest is required.')
    current = db.schema_metadata.find_one({'_id': 'alliance'})
    if current is None or current['version'] not in (2, 3):
        raise RuntimeError('Only the existing schema 2 database can be upgraded.')
    journal_id = 'migration-2-to-3'
    journal = db.schema_metadata.find_one({'_id': journal_id})
    if journal and journal.get('database_generation') != current.get('database_generation'):
        raise RuntimeError('The migration database identity differs from its original journal.')
    if current['version'] == 3:
        if not journal or journal.get('phase') != 'complete' or journal.get('backup_digest') != backup_digest:
            raise RuntimeError('The completed migration receipt differs from this backup.')
        return {'schema_version': 3, 'status': 'already_complete', 'database_generation': current['database_generation']}
    if journal and journal.get('backup_digest') != backup_digest:
        raise RuntimeError('Resume with the original verified migration backup.')
    db.schema_metadata.update_one({'_id': journal_id}, {'$setOnInsert': {
        'version': 3, 'phase': 'started', 'backup_digest': backup_digest,
        'database_generation': current['database_generation'], 'created_at': datetime.now(timezone.utc)}}, upsert=True)
    if checkpoint: checkpoint('started')
    for name, validator in SCHEMAS.items():
        if name not in db.list_collection_names():
            if name != 'network_battle_reservations':
                raise RuntimeError('Schema 2 is incomplete; migration will not initialize missing data.')
            db.create_collection(name, validator=validator, validationLevel='strict', validationAction='error')
        # Existing documents must satisfy the new backwards-compatible validator.
        if db[name].find_one({'$nor': [validator]}, {'_id': 1}) is not None:
            raise RuntimeError('An existing record is incompatible; preserve the migration for review.')
        db.command('collMod', name, validator=validator, validationLevel='strict', validationAction='error')
    db.schema_metadata.update_one({'_id': journal_id}, {'$set': {'phase': 'validators'}})
    if checkpoint: checkpoint('validators')
    db.game_runs.create_index([('team_ids', ASCENDING), ('state', ASCENDING), ('created_at', -1), ('_id', ASCENDING)], name='team_run_history')
    db.schema_metadata.update_one({'_id': journal_id}, {'$set': {'phase': 'indexes'}})
    if checkpoint: checkpoint('indexes')
    with db.client.start_session() as session:
        def commit(s):
            owned = db.schema_metadata.find_one({'_id': 'alliance', 'version': 2,
                'database_generation': current['database_generation']}, session=s)
            if owned is None: raise RuntimeError('The database identity changed during migration.')
            db.schema_metadata.update_one({'_id': 'alliance'}, {'$set': {'version': 3}}, session=s)
            db.schema_metadata.update_one({'_id': journal_id}, {'$set': {'phase': 'complete',
                'completed_at': datetime.now(timezone.utc)}}, session=s)
        session.with_transaction(commit)
    return {'schema_version': 3, 'status': 'complete', 'database_generation': current['database_generation']}


def bootstrap_schema(db):
    """Install the current schema only in a fresh owned database; never migrate implicitly.

    Caller must first validate local MongoDB configuration and authorization. No
    document migrations or destructive collection changes are performed here.
    """
    previous = db.schema_metadata.find_one({'_id': 'alliance'})
    if previous is not None and previous['version'] != SCHEMA_VERSION:
        raise RuntimeError('Unsupported Alliance schema version; explicit migration is required.')
    existing = set(db.list_collection_names())
    if previous is None and any(db[name].find_one({}, {'_id': 1}) for name in existing if name in SCHEMAS):
        raise RuntimeError('Database has unowned Alliance records; initialization refused.')
    for name, validator in SCHEMAS.items():
        if name not in existing:
            try:
                db.create_collection(name, validator=validator, validationLevel='strict', validationAction='error')
            except CollectionInvalid:
                pass  # Another initializer won; indexes/metadata below remain idempotent.
        else:
            db.command('collMod', name, validator=validator, validationLevel='strict', validationAction='error')
    db.accounts.create_index([('username_key', ASCENDING)], unique=True, name='unique_username')
    db.teams.create_index([('name_key', ASCENDING)], unique=True, name='unique_team_name')
    db.teams.create_index([('members.account_id', ASCENDING)], unique=True,
                         partialFilterExpression={'members.account_id': {'$exists': True}},
                         name='one_team_per_account')
    db.teams.create_index([('area_id', ASCENDING), ('status', ASCENDING), ('rating', -1)], name='area_standings')
    db.areas.create_index([('name_key', ASCENDING)], unique=True, name='unique_area_name')
    db.game_runs.create_index([('team_ids', ASCENDING), ('state', ASCENDING), ('created_at', -1), ('_id', ASCENDING)], name='team_run_history')
    db.game_runs.create_index([('state', ASCENDING), ('created_at', -1)], name='run_status')
    db.game_runs.create_index([('participants.account_id', ASCENDING), ('created_at', -1)], name='account_runs')
    db.account_heroes.create_index([('account_id', ASCENDING), ('hero_id', ASCENDING)], unique=True, name='owned_hero')
    db.story_checkpoints.create_index([('run_id', ASCENDING), ('sequence', ASCENDING)], unique=True, name='story_sequence')
    db.casual_tickets.create_index('expires_at', expireAfterSeconds=0, name='ticket_expiry')
    db.admin_audit.create_index([('created_at', -1)], name='audit_time')
    db.schema_metadata.update_one({'_id': 'alliance'}, {'$setOnInsert': {
        'version': SCHEMA_VERSION, 'database_generation': str(uuid4()),
        'created_at': datetime.now(timezone.utc)}}, upsert=True)
    db.areas.update_one({'_id': 'area-1'}, {'$setOnInsert': {
        'name': 'Area 1', 'name_key': 'area 1', 'enabled': True,
        'approved_maps': list(MAPS), 'created_at': datetime.now(timezone.utc)}}, upsert=True)
