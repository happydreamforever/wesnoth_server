"""Real offline v1 retention, fresh v2 initialization and restore acceptance."""
from contextlib import redirect_stderr, redirect_stdout
import io
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
    def test_private_admin_failures_resume_same_new_runtime_without_reset(self):
        """Exercise the real fresh-start CLI boundary after hidden input fails."""
        from argon2 import PasswordHasher
        from alliance.config import ConfigurationError, Settings

        mongod = Path(os.environ['ALLIANCE_MAINTENANCE_MONGO'])
        legacy = Path(os.environ['ALLIANCE_LEGACY_SOURCE'])
        with tempfile.TemporaryDirectory(prefix='unified private admin recovery ') as directory:
            base = Path(directory)
            old, new, archive = base / 'v1', base / 'v2', base / 'private-v1-backup'
            script = '''from pathlib import Path
import sys
from alliance.deployment import initialize
initialize(Path(sys.argv[1]),Path(sys.argv[2]),
           admin_username='OldAdmin',admin_password='fixture-old-admin-123')
'''
            completed = subprocess.run(
                [sys.executable, '-B', '-c', script, str(old), str(mongod)],
                cwd=legacy, env={**os.environ, 'PYTHONPATH': str(legacy)},
                capture_output=True, text=True, timeout=90)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            before = maintenance.inventory(old)
            maintenance.backup(old, archive)
            arguments = ['--previous-runtime', str(old), '--backup', str(archive),
                         '--runtime', str(new), '--mongod', str(mongod)]
            password = 'fixture-new-private-admin-123'
            private_values = [password, 'first-private-password-123',
                              'different-private-password-123', 'tiny',
                              'private scoped verification fixture']

            def assert_old_preserved():
                self.assertEqual(maintenance.inventory(old), before)
                self.assertEqual(maintenance.inventory(archive / 'runtime'), before)

            def assert_child_stopped():
                with maintenance.reserved_ports():
                    pass
                self.assertEqual((new / 'data/mongod.lock').stat().st_size, 0)

            def controls():
                return {name: (new / name).read_bytes() for name in maintenance.CONTROLS}

            def database_snapshot():
                credentials = _credentials(new)
                child = _start_mongo(new, mongod)
                try:
                    with _client(_uri('wesnoth_operator', credentials['database_admin_password'],
                                      'admin')) as client:
                        end = time.monotonic() + 30
                        while not client.admin.command('hello').get('isWritablePrimary'):
                            self.assertLess(time.monotonic(), end)
                            time.sleep(.1)
                        db = client.wesnoth_game
                        schema = db.schema_metadata.find_one({'_id': 'alliance'})
                        self.assertEqual(schema['version'], 2)
                        return {
                            'generation': schema['database_generation'],
                            'accounts': list(db.accounts.find({}).sort('_id', 1)),
                            'admin_audits': list(db.admin_audit.find({}).sort('_id', 1)),
                            'heroes': db.account_heroes.count_documents({}),
                            'teams': db.teams.count_documents({}),
                        }
                finally:
                    _stop_owned(child, new)

            def invoke(passwords, *, existing_admin=False):
                out, err = io.StringIO(), io.StringIO()
                username_effect = AssertionError('Existing administrator must not be prompted') \
                    if existing_admin else None
                password_effect = AssertionError('Existing password must not be replaced') \
                    if existing_admin else passwords
                with redirect_stdout(out), redirect_stderr(err), \
                     patch('builtins.input', return_value='uni', side_effect=username_effect), \
                     patch('getpass.getpass', side_effect=password_effect):
                    result = fresh.main(arguments)
                rendered = out.getvalue() + err.getvalue()
                for value in private_values:
                    self.assertNotIn(value, rendered)
                self.assertNotIn('Traceback', rendered)
                self.assertNotIn('$argon2', rendered)
                self.assertNotIn('mongodb://', rendered)
                assert_child_stopped()
                assert_old_preserved()
                return result, rendered

            original_controls = None
            generation = None
            for passwords, stage, reason in (
                    (['first-private-password-123', 'different-private-password-123'],
                     'administrator-input', 'password_mismatch'),
                    (['tiny', 'tiny'], 'administrator-password', 'invalid_password_length')):
                with self.subTest(failure='mismatch' if passwords[0] != passwords[1] else 'length'):
                    result, rendered = invoke(passwords)
                    self.assertEqual(result, 1)
                    self.assertIn('UNIFIED FRESH START STOPPED:', rendered)
                    self.assertIn('stage=' + stage, rendered)
                    self.assertIn('reason=' + reason, rendered)
                    self.assertNotIn('ALLIANCE INITIALIZATION PASSED', rendered)
                    self.assertNotIn('UNIFIED FRESH START VERIFIED', rendered)
                    self.assertTrue((new / fresh.MARKER).is_file())
                    self.assertFalse((new / fresh.COMPLETE).exists())
                    state = database_snapshot()
                    self.assertEqual(state['accounts'], [])
                    self.assertEqual(state['admin_audits'], [])
                    self.assertEqual((state['heroes'], state['teams']), (0, 0))
                    if original_controls is None:
                        original_controls, generation = controls(), state['generation']
                    else:
                        self.assertEqual(controls(), original_controls)
                        self.assertEqual(state['generation'], generation)

            # Failure after the administrator transaction is resumable too:
            # the next attempt must retain that account and its exact password.
            load_settings = Settings.load

            def fail_new_scope(runtime):
                if Path(runtime) == new:
                    raise ConfigurationError('private scoped verification fixture')
                return load_settings(runtime)

            with patch('alliance.deployment.Settings.load', side_effect=fail_new_scope):
                result, rendered = invoke([password, password])
            self.assertEqual(result, 1)
            self.assertIn('stage=application-verification', rendered)
            self.assertIn('reason=configuration_error', rendered)
            self.assertNotIn('ALLIANCE INITIALIZATION PASSED', rendered)
            self.assertFalse((new / fresh.COMPLETE).exists())
            saved = database_snapshot()
            self.assertEqual(len(saved['accounts']), 1)
            admin = saved['accounts'][0]
            self.assertEqual((admin['username'], admin['role'], admin['status']),
                             ('uni', 'admin', 'active'))
            self.assertTrue(PasswordHasher().verify(admin['password_hash'], password))
            self.assertEqual(saved['generation'], generation)
            self.assertEqual(controls(), original_controls)

            result, rendered = invoke([], existing_admin=True)
            self.assertEqual(result, 0, rendered)
            self.assertIn('ALLIANCE INITIALIZATION PASSED', rendered)
            self.assertIn('UNIFIED FRESH START VERIFIED', rendered)
            self.assertIn('"reused": false', rendered)
            self.assertEqual(database_snapshot(), saved)
            self.assertEqual(controls(), original_controls)
            self.assertTrue((new / fresh.COMPLETE).is_file())

            before_reuse = maintenance.inventory(new)
            with patch.object(fresh, 'initialize', side_effect=AssertionError(
                    'Completed fresh start must not initialize again')):
                result, rendered = invoke([], existing_admin=True)
            self.assertEqual(result, 0, rendered)
            self.assertIn('"reused": true', rendered)
            self.assertEqual(maintenance.inventory(new), before_reuse)
            self.assertEqual(controls(), original_controls)
            assert_old_preserved()

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
