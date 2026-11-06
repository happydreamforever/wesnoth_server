"""Custom local endpoint persistence and real, disposable MongoDB restoration."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alliance.config import ConfigurationError, LocalMongo, Settings
from alliance import deployment as D
from tools import alliance_maintenance as M
from tools import windows_development as W


class LocalEndpointTests(unittest.TestCase):
    def test_custom_endpoint_roundtrip_and_restricted_uri(self):
        endpoint=LocalMongo(27139,'wesnoth_newpc','newpc-rs')
        uri=D._uri('wesnoth_app','private_password',endpoint.name,endpoint=endpoint)
        self.assertEqual(LocalMongo.from_uri(uri),endpoint)
        for invalid in (uri.replace('127.0.0.1','192.168.1.10'), uri.replace('27139','15001'),
                uri.replace('wesnoth_newpc','admin'), uri+'&replicaSet=newpc-rs',
                uri+'&authSource=wesnoth_newpc', uri+'&tls=false', uri+'#fragment'):
            with self.subTest(invalid=invalid), self.assertRaises(ConfigurationError) as caught:
                LocalMongo.from_uri(invalid)
            self.assertNotIn('private_password',str(caught.exception))
        for args in ((True,'wesnoth_newpc','rs'),(1023,'wesnoth_newpc','rs'),(65536,'wesnoth_newpc','rs'),
                (27139,'admin','rs'),(27139,'wesnoth_newpc','bad rs')):
            with self.assertRaises(ConfigurationError): LocalMongo(*args)

    def test_saved_config_is_authoritative_and_conflicting_setup_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=D.owned_runtime(Path(directory)/'runtime',create=True)
            endpoint=LocalMongo(27139,'wesnoth_newpc','newpc-rs')
            D._configure_runtime(root,endpoint)
            before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
            D._configure_runtime(root)
            self.assertEqual(Settings.load(root).database,endpoint)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir() if p.is_file()})
            with self.assertRaises(ConfigurationError): D._configure_runtime(root,LocalMongo())
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir() if p.is_file()})
            with patch.object(W,'verify_identity') as identity:
                with self.assertRaisesRegex(ConfigurationError,'differ from the saved runtime'):
                    W.check(root,Path(directory)/'identity','192.168.4.10',27018,'wesnoth_game','wesnoth-rs')
                identity.assert_not_called()
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir() if p.is_file()})

    def test_matching_settings_forward_explicit_identity_and_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            root=D.owned_runtime(Path(directory)/'runtime',create=True)
            D._configure_runtime(root)
            identity=Path(directory)/'selected identity'
            with patch.object(W,'verify_identity') as verify, redirect_stdout(io.StringIO()):
                W.check(root,identity,'192.168.4.10',27018,'wesnoth_game','wesnoth-rs')
            verify.assert_called_once_with(identity,'192.168.4.10',15001)


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGOD'),'Requires disposable offline MongoDB')
class CustomMongoIntegrationTests(unittest.TestCase):
    def test_court_custom_endpoint_authenticated_restart_backup_and_restore(self):
        binary=Path(os.environ['ALLIANCE_TEST_MONGOD'])
        endpoint=LocalMongo(27139,'wesnoth_newpc','newpc-rs')
        with tempfile.TemporaryDirectory(prefix='development custom mongo ') as directory:
            root=Path(directory); runtime=root/'original'
            with redirect_stdout(io.StringIO()):
                D.initialize(runtime,binary,product='court',database=endpoint,
                    admin_username='FixtureAdmin',admin_password='fixture private password')
            self.assertEqual(Settings.load(runtime).database,endpoint)
            process=D._start_mongo(runtime,binary)
            try:
                with redirect_stdout(io.StringIO()): D.check_database(runtime)
                with D._client(Settings.load(runtime).mongo_uri) as client:
                    db=client[endpoint.name]
                    self.assertEqual(db.schema_metadata.find_one({'_id':'alliance'})['version'],5)
                    db.development_fixture.insert_one({'_id':'preserved','value':'original fixture'})
                    self.assertEqual(db.accounts.count_documents({'role':'admin'}),1)
            finally: D._stop_owned(process,runtime)
            before=M.inventory(runtime)
            M.backup(runtime,root/'backup')
            restored=root/'restored'
            self.assertTrue(M.restore(runtime,root/'backup',restored,binary)['schema_checked'])
            self.assertEqual(M.inventory(runtime),before)
            self.assertEqual(Settings.load(restored).database,endpoint)
            process=D._start_mongo(restored,binary)
            try:
                with redirect_stdout(io.StringIO()): D.check_database(restored)
                with D._client(Settings.load(restored).mongo_uri) as client:
                    self.assertEqual(client[endpoint.name].development_fixture.find_one({'_id':'preserved'})['value'],'original fixture')
            finally: D._stop_owned(process,restored)
