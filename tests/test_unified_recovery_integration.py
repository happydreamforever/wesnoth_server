"""Real offline v1 retention, fresh v2 initialization and restore acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from alliance.deployment import initialize, _credentials, _start_mongo, _stop_owned, _client, _uri
from alliance.domain import AllianceService
from alliance.auth import hash_password
from bson import BSON
from tools import alliance_fresh_start as fresh
from tools import alliance_maintenance as maintenance


@unittest.skipUnless(os.environ.get('ALLIANCE_MAINTENANCE_MONGO') and os.environ.get('ALLIANCE_LEGACY_SOURCE'),
                     'Requires isolated MongoDB and retained v1 source')
class RecoveryIntegration(unittest.TestCase):
    def test_v1_backup_fresh_v2_retry_and_both_restores(self):
        mongod=Path(os.environ['ALLIANCE_MAINTENANCE_MONGO'])
        legacy=Path(os.environ['ALLIANCE_LEGACY_SOURCE'])
        with tempfile.TemporaryDirectory(prefix='unified actual recovery ') as directory:
            base=Path(directory);old=base/'v1';new=base/'v2';archive=base/'private-v1-backup'
            script='''from pathlib import Path
import sys,time
from alliance.deployment import initialize,_credentials,_start_mongo,_stop_owned,_client,_uri
from alliance.domain import AllianceService
from alliance.auth import hash_password
p=Path(sys.argv[1]);m=Path(sys.argv[2])
initialize(p,m,admin_username='OldAdmin',admin_password='fixture-old-admin-123')
c=_credentials(p);child=_start_mongo(p,m)
try:
 with _client(_uri('wesnoth_operator',c['database_admin_password'],'admin')) as client:
  end=time.monotonic()+30
  while not client.admin.command('hello').get('isWritablePrimary'):
   assert time.monotonic()<end;time.sleep(.1)
  db=client.wesnoth_game
  assert db.schema_metadata.find_one({'_id':'alliance'})['version']==1
  svc=AllianceService(db);player=svc.register('OldPlayer',hash_password('fixture-old-player-123'))
  svc.create_team(player['_id'],'Retained old team')
finally:_stop_owned(child,p)
'''
            completed=subprocess.run([sys.executable,'-B','-c',script,str(old),str(mongod)],
                cwd=legacy,env={**os.environ,'PYTHONPATH':str(legacy)},capture_output=True,text=True,timeout=90)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            before=maintenance.inventory(old)
            maintenance.backup(old,archive)
            restored=maintenance.restore(old,archive,base/'v1-restored',mongod)
            self.assertTrue(restored['schema_checked'])
            marker=json.loads((base/'v1-restored/restore-verified.json').read_text())
            self.assertEqual(marker['schema_version'],1)
            with patch.object(fresh,'initialize',side_effect=lambda p,m:initialize(p,m,admin_username='NewAdmin',admin_password='fixture-new-admin-123')):
                self.assertFalse(fresh.fresh_start(old,archive,new,mongod)['reused'])
            self.assertEqual(maintenance.inventory(old),before)
            self.assertEqual(maintenance.inventory(archive/'runtime'),before)
            self.assertNotEqual(_credentials(old),_credentials(new))
            def use_database(path, action):
                credentials=_credentials(path);child=_start_mongo(path,mongod)
                try:
                    with _client(_uri('wesnoth_operator',credentials['database_admin_password'],'admin')) as client:
                        end=time.monotonic()+30
                        while not client.admin.command('hello').get('isWritablePrimary'):
                            self.assertLess(time.monotonic(),end);time.sleep(.1)
                        return action(client.wesnoth_game)
                finally:_stop_owned(child,path)
            def new_records(db):
                self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],2)
                self.assertEqual([a['username'] for a in db.accounts.find({})],['NewAdmin'])
                self.assertEqual(db.account_heroes.count_documents({}),0)
                self.assertEqual(db.teams.count_documents({}),0)
                player=AllianceService(db).register('NewPlayer',hash_password('fixture-new-player-123'))
                self.assertTrue(player['database_generation'])
                return {name:sorted(BSON.encode(row) for row in db[name].find({})) for name in db.list_collection_names()}
            expected=use_database(new,new_records)
            new_before=maintenance.inventory(new)
            with patch.object(fresh,'initialize') as initialize_again:
                self.assertTrue(fresh.fresh_start(old,archive,new,mongod)['reused'])
                initialize_again.assert_not_called()
            self.assertEqual(maintenance.inventory(new),new_before)
            maintenance.backup(new,base/'private-v2-backup')
            maintenance.restore(new,base/'private-v2-backup',base/'v2-restored',mongod)
            actual=use_database(base/'v2-restored',lambda db:{name:sorted(BSON.encode(row) for row in db[name].find({})) for name in db.list_collection_names()})
            self.assertEqual(actual,expected)
            self.assertEqual(maintenance.inventory(old),before)


if __name__=='__main__':unittest.main()
