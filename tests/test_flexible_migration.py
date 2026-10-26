"""Authenticated cold backup, interruption, resume and schema-2 recovery."""
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
from alliance.deployment import initialize, _credentials, _start_mongo, _stop_owned, _client, _uri
from alliance.schema import migrate_schema_2_to_3
from tools import alliance_maintenance as maintenance
from tools import migrate_alliance_runtime as migration

@unittest.skipUnless(os.environ.get('ALLIANCE_MAINTENANCE_MONGO'), 'Requires disposable offline MongoDB')
class Migration(unittest.TestCase):
    def test_cold_upgrade_interruption_resume_preserves_records_and_schema2_restore(self):
        mongod=Path(os.environ['ALLIANCE_MAINTENANCE_MONGO'])
        with tempfile.TemporaryDirectory(prefix='flexible-migration-') as temporary:
            root=Path(temporary);runtime=root/'runtime-v2';backup=root/'private-backup'
            with redirect_stdout(io.StringIO()):initialize(runtime,mongod,admin_username='MigrationAdmin',admin_password='fixture-administrator-password')
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
                    service=AllianceService(db);player=service.register('MigrationPlayer',hash_password('fixture-player-password'))
                    service.create_team(player['_id'],'Retained Team')
                    db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':2}})
                    db.drop_collection('network_battle_reservations')
                    before={n:sorted(BSON.encode(d) for d in db[n].find({})) for n in db.list_collection_names() if n!='schema_metadata'}
                    identity=db.schema_metadata.find_one({'_id':'alliance'})
            finally:_stop_owned(process,runtime)
            controls={n:(runtime/n).read_bytes() for n in maintenance.CONTROLS}
            cold=maintenance.inventory(runtime)
            def interrupted(db,digest):
                def fail(phase):
                    if phase=='validators':raise RuntimeError('injected validator interruption')
                return migrate_schema_2_to_3(db,digest,checkpoint=fail)
            with patch.object(migration,'migrate_schema_2_to_3',side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,'injected'):migration.migrate(runtime,backup,mongod)
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            self.assertEqual(migration.migrate(runtime,backup,mongod),{'schema_version':3,'status':'complete'})
            self.assertEqual(migration.migrate(runtime,backup,mongod),{'schema_version':3,'status':'already_complete'})
            self.assertEqual({n:(runtime/n).read_bytes() for n in maintenance.CONTROLS},controls)
            process=_start_mongo(runtime,mongod)
            try:
                with connect() as client:
                    primary(client);db=client.wesnoth_game
                    after={n:sorted(BSON.encode(d) for d in db[n].find({})) for n in before}
                    self.assertEqual(after,before)
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['database_generation'],identity['database_generation'])
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],3)
            finally:_stop_owned(process,runtime)
            preserved=maintenance.inventory(runtime)
            with redirect_stdout(io.StringIO()):restored=maintenance.restore(runtime,backup,root/'schema2-recovery',mongod)
            self.assertTrue(restored['schema_checked']);self.assertEqual(maintenance.inventory(runtime),preserved)
            self.assertEqual(json.loads((root/'schema2-recovery/restore-verified.json').read_text())['schema_version'],2)
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            with self.assertRaisesRegex(maintenance.MaintenanceError,'migration_resume_backup_mismatch'):
                migration.migrate(runtime,root/'different-backup',mongod)
            self.assertFalse((root/'different-backup').exists())

if __name__=='__main__':unittest.main()
