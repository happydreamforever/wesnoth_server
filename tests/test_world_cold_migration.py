"""Real stopped-runtime schema-3 backup, resumable upgrade and isolated recovery."""
from bson import BSON
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from alliance.deployment import initialize, _credentials, _start_mongo, _stop_owned, _client, _uri
from alliance.schema import WORLD_SCHEMAS, SCHEMA_3_SCHEMAS, migrate_schema_3_to_4
from tools import alliance_maintenance as maintenance
from tools import migrate_alliance_runtime as migration

@unittest.skipUnless(os.environ.get('ALLIANCE_MAINTENANCE_MONGO'), 'Requires disposable offline MongoDB')
class WorldColdMigration(unittest.TestCase):
    def test_cold_upgrade_resume_and_original_schema3_restore(self):
        mongod=Path(os.environ['ALLIANCE_MAINTENANCE_MONGO'])
        with tempfile.TemporaryDirectory(prefix='world-cold-migration-') as temporary:
            root=Path(temporary);runtime=root/'runtime-v2';backup=root/'private-backup'
            with redirect_stdout(io.StringIO()):
                initialize(runtime,mongod,admin_username='MigrationHost',admin_password='fixture-administrator-password')
            credentials=_credentials(runtime)
            def connect():return _client(_uri('wesnoth_operator',credentials['database_admin_password'],'admin'))
            def primary(client):
                deadline=time.monotonic()+30
                while not client.admin.command('hello').get('isWritablePrimary'):
                    self.assertLess(time.monotonic(),deadline);time.sleep(.1)
            process=_start_mongo(runtime,mongod)
            try:
                with connect() as client:
                    primary(client);db=client.wesnoth_game
                    from alliance.domain import AllianceService
                    from alliance.auth import hash_password
                    from alliance.heroes import load_catalog
                    service=AllianceService(db)
                    actor=service.register('RetainedPlayer',hash_password('fixture-player-password'))['_id']
                    team=service.create_team(actor,'Retained Emerald Team')['_id']
                    form=load_catalog()[0]['forms'][0]
                    db.account_heroes.insert_one({'_id':str(uuid4()),'account_id':actor,'hero_id':form['hero_id'],
                        'forms':[form['id']],'total_experience':164,'revision':9})
                    # Exercise a historical 2->3 journal and current source version.
                    db.schema_metadata.insert_one({'_id':'migration-2-to-3','version':3,'status':'complete','backup_digest':'b'*64})
                    db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':3}})
                    for name in WORLD_SCHEMAS:db.drop_collection(name)
                    for name,validator in SCHEMA_3_SCHEMAS.items():db.command('collMod',name,validator=validator)
                    before={n:sorted(BSON.encode(d) for d in db[n].find({})) for n in db.list_collection_names() if n!='schema_metadata'}
                    generation=db.schema_metadata.find_one({'_id':'alliance'})['database_generation']
                    old_journal=BSON.encode(db.schema_metadata.find_one({'_id':'migration-2-to-3'}))
            finally:_stop_owned(process,runtime)
            legacy_replay=runtime/'battles/retained-history/replay.gz'
            legacy_replay.parent.mkdir(parents=True);legacy_replay.write_bytes(b'unchanged historical replay fixture')
            controls={n:(runtime/n).read_bytes() for n in maintenance.CONTROLS}
            cold=maintenance.inventory(runtime)
            with redirect_stdout(io.StringIO()):maintenance.backup(runtime,backup)
            def interrupted(db,digest):
                def fail(phase):
                    if phase=='collection:companies':raise RuntimeError('injected world interruption')
                return migrate_schema_3_to_4(db,digest,checkpoint=fail)
            with patch.object(migration,'migrate_schema_3_to_4',side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    migration.migrate(runtime,backup,mongod)
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            self.assertEqual(migration.migrate(runtime,backup,mongod),{'schema_version':4,'status':'complete'})
            self.assertEqual(migration.migrate(runtime,backup,mongod),{'schema_version':4,'status':'already_complete'})
            self.assertEqual({n:(runtime/n).read_bytes() for n in maintenance.CONTROLS},controls)
            self.assertEqual(legacy_replay.read_bytes(),b'unchanged historical replay fixture')
            process=_start_mongo(runtime,mongod)
            try:
                with connect() as client:
                    primary(client);db=client.wesnoth_game
                    self.assertEqual({n:sorted(BSON.encode(d) for d in db[n].find({})) for n in before},before)
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['database_generation'],generation)
                    self.assertEqual(BSON.encode(db.schema_metadata.find_one({'_id':'migration-2-to-3'})),old_journal)
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],4)
                    for name in WORLD_SCHEMAS:self.assertEqual(db[name].count_documents({}),0)
            finally:_stop_owned(process,runtime)
            preserved=maintenance.inventory(runtime)
            with redirect_stdout(io.StringIO()):
                restored=maintenance.restore(runtime,backup,root/'isolated-schema3',mongod)
            self.assertTrue(restored['schema_checked'])
            self.assertEqual(json.loads((root/'isolated-schema3/restore-verified.json').read_text())['schema_version'],3)
            self.assertEqual(maintenance.inventory(runtime),preserved)
            self.assertEqual((root/'isolated-schema3/battles/retained-history/replay.gz').read_bytes(),legacy_replay.read_bytes())
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            with self.assertRaisesRegex(maintenance.MaintenanceError,'migration_resume_backup_mismatch'):
                migration.migrate(runtime,root/'wrong-backup',mongod)
            self.assertFalse((root/'wrong-backup').exists())

if __name__=='__main__':unittest.main()
