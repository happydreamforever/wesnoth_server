"""Preserving Court reset tests. Every path and MongoDB belongs to a scratch fixture."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from bson import BSON
from alliance import deployment
from alliance.auth import hash_password
from alliance.admin_management import admin_hero_grant_form
from alliance.court.service import CourtService
from alliance.domain import AllianceService
from alliance.runtime_lock import runtime_lock
from tools import alliance_fresh_start as fresh
from tools import alliance_maintenance as maintenance
from tools import court_fresh_start as cli


class CourtFreshGuards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='court fresh fixture ')
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.old = deployment.owned_runtime(self.base / 'runtime-v2', create=True)
        deployment._configure_runtime(self.old)
        (self.old / 'data/WiredTiger').write_bytes(b'fixture prior game')
        (self.old / 'data/mongod.lock').touch()
        self.archive = self.base / 'private archive'
        self.target = self.base / 'runtime-v3'
        maintenance.backup(self.old, self.archive)
        self.before = maintenance.inventory(self.old)
        self.initializer = patch.object(fresh, 'initialize', side_effect=self.initialize_fixture)
        self.initialize = self.initializer.start()
        self.addCleanup(self.initializer.stop)

    def initialize_fixture(self, runtime, mongod, *, product='legacy'):
        self.assertEqual(product, 'court')
        deployment._configure_runtime(runtime)
        (runtime / 'data/WiredTiger').write_bytes(b'new Court database fixture')
        (runtime / 'data/mongod.lock').touch()

    def run_reset(self):
        return fresh.fresh_start(self.old, self.archive, self.target, Path('/unused/mongod'), product='court')

    def preserved(self):
        self.assertEqual(maintenance.inventory(self.old), self.before)
        self.assertEqual(maintenance.inventory(self.archive / 'runtime'), self.before)

    def test_court_target_version_is_explicit_and_old_files_credentials_retained(self):
        result = self.run_reset()
        self.assertEqual(result['schema_version'], 5)
        self.assertFalse(result['reused'])
        marker = json.loads((self.target / fresh.COMPLETE).read_text())
        self.assertEqual(marker['schema_version'], 5)
        self.assertEqual(marker['previous_runtime'], str(self.old))
        self.assertNotEqual((self.old / 'root.json').read_bytes(), (self.target / 'root.json').read_bytes())
        self.preserved()

    def test_repeat_completion_never_reinitializes_or_erases_new_data(self):
        self.run_reset()
        (self.target / 'data/new-player.wt').write_bytes(b'current Court progress')
        before = maintenance.inventory(self.target)
        result = self.run_reset()
        self.assertTrue(result['reused'])
        self.assertEqual(self.initialize.call_count, 1)
        self.assertEqual(maintenance.inventory(self.target), before)
        self.preserved()

    def test_interrupted_reset_keeps_journal_and_safe_cli_diagnostic(self):
        self.initialize.side_effect = RuntimeError('NEVER-EXPOSE-PRIVATE-FIXTURE')
        output = io.StringIO()
        args = ['--previous-runtime', str(self.old), '--backup', str(self.archive),
            '--runtime', str(self.target), '--mongod', '/unused/mongod']
        with redirect_stdout(output): self.assertEqual(cli.main(args), 1)
        self.assertNotIn('NEVER-EXPOSE-PRIVATE-FIXTURE', output.getvalue())
        self.assertTrue((self.target / fresh.MARKER).is_file())
        self.assertFalse((self.target / fresh.COMPLETE).exists())
        self.initialize.side_effect = self.initialize_fixture
        self.run_reset()
        self.preserved()

    def test_legacy_and_court_journals_cannot_adopt_each_other(self):
        self.run_reset()
        before = maintenance.inventory(self.target)
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'destination_is_not_this_fresh_start'):
            fresh.fresh_start(self.old, self.archive, self.target, Path('/unused/mongod'))
        self.assertEqual(maintenance.inventory(self.target), before)
        self.preserved()

    def test_changed_archive_or_original_refuses_before_creating_target(self):
        (self.old / 'data/new-progress.wt').write_bytes(b'later progress')
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'backup_does_not_match'):
            self.run_reset()
        self.initialize.assert_not_called()
        self.assertFalse(self.target.exists())
        (self.old / 'data/new-progress.wt').unlink()
        (self.archive / 'runtime/data/WiredTiger').write_bytes(b'tampered archive')
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'backup_integrity'):
            self.run_reset()
        self.assertFalse(self.target.exists())

    def test_court_reset_accepts_supported_producer_without_claiming_archive_schema(self):
        path = self.archive / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['producer_schema_version'] = 2
        path.write_text(json.dumps(manifest))
        archive_before = maintenance.inventory(self.archive / 'runtime')
        result = self.run_reset()
        self.assertEqual(result['schema_version'], 5)
        self.assertNotIn('schema_version', manifest)
        self.assertEqual(maintenance.inventory(self.old), self.before)
        self.assertEqual(maintenance.inventory(self.archive / 'runtime'), archive_before)

    def test_court_reset_rejects_unknown_archive_producer_before_creating_target(self):
        path = self.archive / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['producer_schema_version'] = 999
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'unsupported_backup_version'):
            self.run_reset()
        self.assertFalse(self.target.exists())
        self.initialize.assert_not_called()
        self.assertEqual(maintenance.inventory(self.old), self.before)
        self.assertEqual(maintenance.inventory(self.archive / 'runtime'), self.before)

    def test_unrelated_target_overlapping_path_and_live_runtime_lock_refused(self):
        self.target.mkdir()
        (self.target / 'keep.txt').write_bytes(b'Never replace unrelated files')
        with self.assertRaises((deployment.ConfigurationError, maintenance.MaintenanceError)): self.run_reset()
        self.assertEqual((self.target / 'keep.txt').read_bytes(), b'Never replace unrelated files')
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'overlapping_destination'):
            fresh.fresh_start(self.old, self.archive, self.old / 'nested', Path('/unused'), product='court')
        with runtime_lock(self.old), self.assertRaises(ValueError): self.run_reset()
        self.initialize.assert_not_called()
        self.preserved()

    def test_unknown_product_and_tampered_completion_are_refused(self):
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'unknown_fresh_product'):
            fresh.fresh_start(self.old, self.archive, self.target, Path('/unused'), product='future')
        self.assertFalse(self.target.exists())
        self.run_reset()
        path = self.target / fresh.COMPLETE
        data = json.loads(path.read_text())
        data['schema_version'] = 999
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(maintenance.MaintenanceError, 'fresh_start_completion_changed'):
            self.run_reset()
        self.assertEqual(self.initialize.call_count, 1)
        self.preserved()


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGOD'), 'Requires isolated owned MongoDB binary')
class CourtFreshReal(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='court real fresh ')
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.mongod = Path(os.environ['ALLIANCE_TEST_MONGOD'])
        self.password = 'fixture-court-local-password-123'

    def start(self, runtime):
        process = deployment._start_mongo(runtime, self.mongod)
        credentials = deployment._credentials(runtime)
        client = deployment._client(deployment._uri('wesnoth_operator', credentials['database_admin_password'], 'admin'))
        deadline = time.monotonic() + 30
        while not client.admin.command('hello').get('isWritablePrimary'):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.1)
        return process, client

    @staticmethod
    def records(db):
        return {name: sorted(BSON.encode(row) for row in db[name].find({}))
            for name in db.list_collection_names()}

    def test_real_schema4_archive_fresh_schema5_and_isolated_restoration(self):
        old, archive, new = self.base / 'runtime-v2', self.base / 'private archive', self.base / 'runtime-v3'
        deployment.initialize(old, self.mongod, admin_username='OldHost', admin_password=self.password)
        process, client = self.start(old)
        try:
            db = client.wesnoth_game
            service = AllianceService(db)
            account = service.register('ArchivedPlayer', hash_password(self.password))
            service.create_team(account['_id'], 'Archived Team')
            db.account_heroes.insert_one({'_id': 'archived-hero', 'account_id': account['_id'], 'hero_id': 'abhai',
                'forms': [admin_hero_grant_form('abhai')['id']], 'revision': 7, 'total_experience': 456})
            self.assertEqual(db.schema_metadata.find_one({'_id': 'alliance'})['version'], 4)
            old_generation = db.schema_metadata.find_one({'_id': 'alliance'})['database_generation']
            records = self.records(db)
        finally:
            client.close()
            deployment._stop_owned(process, old)
        replay = old / 'battles' / 'archived-battle'
        replay.mkdir(parents=True)
        (replay / 'verified.replay').write_bytes(b'preserved replay bytes from prior generation')
        before = maintenance.inventory(old)
        maintenance.backup(old, archive)
        with patch.object(deployment, '_admin_credentials', return_value=('CourtHost', self.password)):
            result = fresh.fresh_start(old, archive, new, self.mongod, product='court')
        self.assertEqual(result['schema_version'], 5)
        self.assertEqual(maintenance.inventory(old), before)
        self.assertEqual(maintenance.inventory(archive / 'runtime'), before)
        process, client = self.start(new)
        try:
            db = client.wesnoth_game
            meta = db.schema_metadata.find_one({'_id': 'alliance'})
            self.assertEqual(meta['version'], 5)
            self.assertTrue(meta['court_initialized'])
            self.assertNotEqual(meta['database_generation'], old_generation)
            self.assertEqual(db.accounts.count_documents({}), 1)
            self.assertEqual(db.accounts.find_one()['username'], 'CourtHost')
            self.assertEqual(db.court_areas.count_documents({}), 128)
            self.assertEqual(db.court_castles.count_documents({}), 8192)
            for name in ('account_heroes', 'court_teams', 'court_wallets', 'court_matches'):
                self.assertEqual(db[name].count_documents({}), 0)
            self.assertNotIn('company_soldiers', db.list_collection_names())
            fresh_records = self.records(db)
        finally:
            client.close()
            deployment._stop_owned(process, new)
        current_files = maintenance.inventory(new)
        self.assertTrue(fresh.fresh_start(old, archive, new, self.mongod, product='court')['reused'])
        self.assertEqual(maintenance.inventory(new), current_files)
        restored = self.base / 'schema4 recovery'
        result = maintenance.restore(old, archive, restored, self.mongod)
        self.assertTrue(result['schema_checked'])
        process, client = self.start(restored)
        try: self.assertEqual(self.records(client.wesnoth_game), records)
        finally:
            client.close()
            deployment._stop_owned(process, restored)
        self.assertEqual((restored / 'battles/archived-battle/verified.replay').read_bytes(), b'preserved replay bytes from prior generation')
        self.assertEqual(maintenance.inventory(old), before)
        self.assertEqual(maintenance.inventory(archive / 'runtime'), before)
        self.assertEqual(maintenance.inventory(new), current_files)
        new_archive, new_restore = self.base / 'Court backup', self.base / 'Court recovery'
        maintenance.backup(new, new_archive)
        result = maintenance.restore(new, new_archive, new_restore, self.mongod)
        self.assertTrue(result['schema_checked'])
        self.assertEqual(json.loads((new_restore / 'restore-verified.json').read_text())['schema_version'], 5)
        process, client = self.start(new_restore)
        try: self.assertEqual(self.records(client.wesnoth_game), fresh_records)
        finally:
            client.close()
            deployment._stop_owned(process, new_restore)
        self.assertEqual(maintenance.inventory(new), current_files)

    def test_real_interrupted_court_bootstrap_resumes_without_replacing_generation(self):
        from alliance.court import schema
        old, archive, new = self.base / 'old', self.base / 'archive', self.base / 'new'
        deployment.initialize(old, self.mongod, admin_username='OldHost', admin_password=self.password)
        maintenance.backup(old, archive)
        original = maintenance.inventory(old)
        bootstrap = schema.bootstrap_court_schema
        def interrupted(db):
            bootstrap(db)
            raise RuntimeError('PRIVATE-FAILURE-MUST-NOT-ESCAPE')
        with patch.object(schema, 'bootstrap_court_schema', side_effect=interrupted):
            with self.assertRaises(deployment.InitializationError) as raised:
                fresh.fresh_start(old, archive, new, self.mongod, product='court')
        self.assertEqual(raised.exception.stage, 'schema')
        self.assertNotIn('PRIVATE-FAILURE-MUST-NOT-ESCAPE', str(raised.exception))
        self.assertTrue((new / fresh.MARKER).is_file())
        self.assertFalse((new / fresh.COMPLETE).exists())
        credentials_before = (new / 'root.json').read_bytes()
        process, client = self.start(new)
        try:
            generation = client.wesnoth_game.schema_metadata.find_one({'_id': 'alliance'})['database_generation']
            self.assertEqual(client.wesnoth_game.court_castles.count_documents({}), 8192)
            self.assertEqual(client.wesnoth_game.accounts.count_documents({}), 0)
        finally:
            client.close()
            deployment._stop_owned(process, new)
        with patch.object(deployment, '_admin_credentials', return_value=('CourtHost', self.password)):
            result = fresh.fresh_start(old, archive, new, self.mongod, product='court')
        self.assertFalse(result['reused'])
        self.assertEqual((new / 'root.json').read_bytes(), credentials_before)
        process, client = self.start(new)
        try:
            self.assertEqual(client.wesnoth_game.schema_metadata.find_one({'_id': 'alliance'})['database_generation'], generation)
            self.assertEqual(client.wesnoth_game.accounts.count_documents({}), 1)
            self.assertEqual(client.wesnoth_game.court_castles.count_documents({}), 8192)
        finally:
            client.close()
            deployment._stop_owned(process, new)
        self.assertEqual(maintenance.inventory(old), original)
        self.assertEqual(maintenance.inventory(archive / 'runtime'), original)
