"""Authenticated cold backup, interruption, resume and schema-2 recovery."""
from bson import BSON
from hashlib import sha256
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
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
                    from alliance.heroes import load_catalog
                    service=AllianceService(db);player=service.register('MigrationPlayer',hash_password('fixture-player-password'))
                    service.create_team(player['_id'],'Retained Team')
                    catalogue,_=load_catalog();form=catalogue['forms'][0]
                    draft_ids=[]
                    for pair in range(2):
                        players=[];teams=[]
                        for team in range(2):
                            members=[]
                            for seat in range(2):
                                actor=service.register('Migration_'+str(pair)+str(team)+str(seat),hash_password('fixture-player-password'))['_id']
                                db.account_heroes.insert_one({'_id':str(uuid4()),'account_id':actor,'hero_id':form['hero_id'],
                                    'forms':[form['id']],'total_experience':0,'revision':0})
                                members.append(actor)
                            team_id=service.create_team(members[0],'Migration Team '+str(pair)+str(team))['_id']
                            service.request_join(members[1],team_id);service.approve_member(members[0],team_id,members[1])
                            teams.append(team_id);players.append(members)
                        def plan():
                            run=service.create_battle(players[0][0],teams[1],'isars-cross',dict(zip(teams,players)),native_plan=True)['id']
                            for actor in sum(players,[]):service.directory_select_hero(actor,run,form['hero_id'],form['id'])
                            for actor in sum(players,[]):service.directory_battle_ready(actor,run,True)
                            for actor in (players[0][0],players[1][0]):service.directory_approve_battle(actor,run)
                            return run
                        if pair==0:
                            completed=plan();service.start_battle(players[0][0],completed);service.finish_battle(completed,teams[0])
                            cancelled=plan();service.directory_cancel_battle(players[0][0],cancelled)
                        draft_ids.append(plan())
                    # A retained local story is not an active network battle.
                    story=service.story_begin(player['_id'],catalogue['campaigns'][0]['id'],catalogue['version'],load_catalog()[1])
                    db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'version':2}})
                    db.drop_collection('network_battle_reservations')
                    inactive=db.game_runs.find_one({'_id':draft_ids[0]})
                    for active in ({'state':'running'}, {'shared_room':{'state':'preparing','generation':str(uuid4())}}):
                        db.game_runs.update_one({'_id':draft_ids[0]},{'$set':active})
                        guarded=BSON.encode(db.game_runs.find_one({'_id':draft_ids[0]}))
                        with self.assertRaisesRegex(RuntimeError,'active battles'):
                            migrate_schema_2_to_3(db,'a'*64)
                        self.assertIsNone(db.schema_metadata.find_one({'_id':'migration-2-to-3'}))
                        self.assertEqual(BSON.encode(db.game_runs.find_one({'_id':draft_ids[0]})),guarded)
                        db.game_runs.replace_one({'_id':draft_ids[0]},inactive)
                    before={n:sorted(BSON.encode(d) for d in db[n].find({})) for n in db.list_collection_names() if n!='schema_metadata'}
                    identity=db.schema_metadata.find_one({'_id':'alliance'})
            finally:_stop_owned(process,runtime)
            controls={n:(runtime/n).read_bytes() for n in maintenance.CONTROLS}
            cold=maintenance.inventory(runtime)
            def interrupted(db,digest):
                def fail(phase):
                    if phase=='draft_converted':raise RuntimeError('injected draft interruption')
                return migrate_schema_2_to_3(db,digest,checkpoint=fail)
            with patch.object(migration,'migrate_schema_2_to_3',side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,'injected'):migration.migrate(runtime,backup,mongod,target_schema=3)
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            process=_start_mongo(runtime,mongod)
            try:
                with connect() as client:
                    primary(client);db=client.wesnoth_game
                    self.assertEqual(db.game_runs.count_documents({'plan_format':2}),1)
                    converted=BSON.encode(db.game_runs.find_one({'plan_format':2}))
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],2)
                    db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'database_generation':str(uuid4())}})
                    with self.assertRaisesRegex(RuntimeError,'identity'):
                        migrate_schema_2_to_3(db,db.schema_metadata.find_one({'_id':'migration-2-to-3'})['backup_digest'])
                    self.assertEqual(BSON.encode(db.game_runs.find_one({'plan_format':2})),converted)
                    db.schema_metadata.update_one({'_id':'alliance'},{'$set':{'database_generation':identity['database_generation']}})
            finally:_stop_owned(process,runtime)
            self.assertEqual(migration.migrate(runtime,backup,mongod,target_schema=3),{'schema_version':3,'status':'complete'})
            self.assertEqual(migration.migrate(runtime,backup,mongod,target_schema=3),{'schema_version':3,'status':'already_complete'})
            self.assertEqual({n:(runtime/n).read_bytes() for n in maintenance.CONTROLS},controls)
            process=_start_mongo(runtime,mongod)
            try:
                with connect() as client:
                    primary(client);db=client.wesnoth_game
                    after={n:sorted(BSON.encode(d) for d in db[n].find({})) for n in before}
                    self.assertEqual({n:v for n,v in after.items() if n!='game_runs'},
                                     {n:v for n,v in before.items() if n!='game_runs'})
                    original={BSON(raw).decode()['_id']:raw for raw in before['game_runs']}
                    self.assertEqual(db.game_runs.count_documents({'plan_format':2}),2)
                    self.assertIn(converted,after['game_runs'])
                    for run in db.game_runs.find({}):
                        if run['_id'] not in draft_ids:
                            self.assertEqual(BSON.encode(run),original[run['_id']]);continue
                        snapshot=run['legacy_plan_snapshot'];raw=original[run['_id']]
                        self.assertEqual(bytes(snapshot['bson']),raw);self.assertEqual(snapshot['sha256'],sha256(raw).hexdigest())
                        self.assertEqual(snapshot['database_generation'],identity['database_generation'])
                        source=BSON(raw).decode();self.assertEqual(run['participants'],source['participants'])
                        self.assertEqual(run['approvals'],{});self.assertEqual(run['ready'],[])
                        self.assertNotIn('shared_room',run);self.assertEqual(run['revision'],1)
                        self.assertEqual({s['side']:s['account_id'] for s in run['slots']},
                                         {p['side']:p['account_id'] for p in source['participants']})
                        self.assertEqual({s['kind'] for s in run['slots']},{'reserved'})
                        descriptor=AllianceService(db).directory_battle_detail(run['participants'][0]['account_id'],run['_id'])
                        self.assertEqual(descriptor['format'],2);self.assertEqual(descriptor['room_state'],'')
                        self.assertEqual({p['selection']['hero_id'] for t in descriptor['teams'] for p in t['players']},{form['hero_id']})
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['database_generation'],identity['database_generation'])
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],3)
            finally:_stop_owned(process,runtime)
            preserved=maintenance.inventory(runtime)
            with redirect_stdout(io.StringIO()):restored=maintenance.restore(runtime,backup,root/'schema2-recovery',mongod)
            self.assertTrue(restored['schema_checked']);self.assertEqual(maintenance.inventory(runtime),preserved)
            self.assertEqual(json.loads((root/'schema2-recovery/restore-verified.json').read_text())['schema_version'],2)
            self.assertEqual(maintenance.inventory(backup/'runtime'),cold)
            with self.assertRaisesRegex(maintenance.MaintenanceError,'migration_resume_backup_mismatch'):
                migration.migrate(runtime,root/'different-backup',mongod,target_schema=3)
            self.assertFalse((root/'different-backup').exists())

if __name__=='__main__':unittest.main()
