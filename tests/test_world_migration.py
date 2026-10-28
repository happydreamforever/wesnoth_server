"""Actual replica-set preservation and interruption checks for schema 3 -> 4."""
from copy import deepcopy
from uuid import uuid4
from bson import BSON
from test_unified_product import UnifiedProduct as Fixture
from alliance.schema import SCHEMAS, SCHEMA_3_SCHEMAS, WORLD_SCHEMAS, migrate_schema_3_to_4

class WorldMigration(Fixture):
    # Inherit setup/helpers without repeating the entire historical test class.
    def legacy(self):
        actor=self.player(True)
        team=self.domain.create_team(actor,'Retained Company Team')['_id']
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':3}})
        for name in WORLD_SCHEMAS:self.db.drop_collection(name)
        for name,validator in SCHEMA_3_SCHEMAS.items():
            self.db.command('collMod',name,validator=validator)
        before={name:sorted(BSON.encode(row) for row in self.db[name].find({})) for name in self.db.list_collection_names() if name!='schema_metadata'}
        generation=self.db.schema_metadata.find_one({'_id':'alliance'})['database_generation']
        return actor,team,before,generation

    def test_additive_interruption_resume_preserves_all_original_bson(self):
        actor,team,before,generation=self.legacy()
        for phase in ('started','collection:companies','validators','indexes'):
            def interrupt(value):
                if value==phase:raise RuntimeError('injected '+phase)
            with self.assertRaisesRegex(RuntimeError,'injected'):
                migrate_schema_3_to_4(self.db,'a'*64,checkpoint=interrupt)
            self.assertEqual(self.db.schema_metadata.find_one({'_id':'alliance'})['version'],3)
            self.assertEqual({name:sorted(BSON.encode(row) for row in self.db[name].find({})) for name in before},before)
        self.assertEqual(migrate_schema_3_to_4(self.db,'a'*64)['status'],'complete')
        self.assertEqual(migrate_schema_3_to_4(self.db,'a'*64)['status'],'already_complete')
        self.assertEqual(self.db.schema_metadata.find_one({'_id':'alliance'})['database_generation'],generation)
        self.assertEqual({name:sorted(BSON.encode(row) for row in self.db[name].find({})) for name in before},before)
        for name in WORLD_SCHEMAS:self.assertEqual(self.db[name].count_documents({}),0,name)
        with self.assertRaisesRegex(RuntimeError,'original'):
            migrate_schema_3_to_4(self.db,'b'*64)

    def test_requires_no_active_network_reservation_and_exact_database(self):
        actor,team,before,generation=self.legacy()
        from alliance.domain import _now
        reservation={'_id':actor,'kind':'team','run_id':str(uuid4()),'generation':str(uuid4()),'created_at':_now()}
        self.db.network_battle_reservations.insert_one(reservation)
        with self.assertRaisesRegex(RuntimeError,'active battles'):
            migrate_schema_3_to_4(self.db,'a'*64)
        self.assertIsNone(self.db.schema_metadata.find_one({'_id':'migration-3-to-4'}))
        self.db.network_battle_reservations.delete_one({'_id':actor})
        def interrupt(phase):
            if phase=='started':raise RuntimeError('injected')
        with self.assertRaisesRegex(RuntimeError,'injected'):
            migrate_schema_3_to_4(self.db,'a'*64,checkpoint=interrupt)
        self.db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'database_generation':str(uuid4())}})
        with self.assertRaisesRegex(RuntimeError,'original'):
            migrate_schema_3_to_4(self.db,'a'*64)
        self.assertEqual(self.db.schema_metadata.find_one({'_id':'alliance'})['version'],3)

    def test_missing_legacy_records_and_preexisting_world_data_are_not_initialized(self):
        self.legacy()
        self.db.drop_collection('teams')
        with self.assertRaisesRegex(RuntimeError,'incomplete'):
            migrate_schema_3_to_4(self.db,'a'*64)
        self.assertNotIn('teams',self.db.list_collection_names())

# Fixture is a unittest class with many independent historical tests. Only this
# migration suite belongs in this file; run that original suite separately.
for _name in dir(Fixture):
    if _name.startswith('test_') and _name not in WorldMigration.__dict__:
        setattr(WorldMigration,_name,None)
del Fixture
