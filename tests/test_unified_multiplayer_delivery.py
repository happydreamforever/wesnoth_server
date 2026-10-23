"""Native-lobby receipts and secret-free launch configuration boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_unified_multiplayer as build
from tools import run_unified_multiplayer as run


class NativeDelivery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='native delivery ');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stage=self.root/'build/windows-unified-mingw64'
        for name in ('CMakeLists.txt','tools/build_unified_multiplayer.py','tools/build_alliance_bridge.py',
                     'alliance_bridge/unified_protocol.hpp','engine/source.cpp','alliance_casual/adapter.cpp','alliance/hero_catalog.json'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('verified source '+name)
        (self.stage/'bin').mkdir(parents=True);self.binary=self.stage/'bin/wesnothd.exe';self.binary.write_bytes(b'fixture executable')
        self.addCleanup(patch.stopall);patch.object(build,'ROOT',self.root).start();patch.object(build,'STAGE',self.stage).start()
        self.binding=build.binding()
        (self.stage/'owner.json').write_text(json.dumps(self.binding))
        self.receipt={'binding':self.binding,'version':build.VERSION,'executable':{'bytes':self.binary.stat().st_size,'sha256':build.digest(self.binary)}}
        self.save_receipt()

    def save_receipt(self): (self.stage/'receipt.json').write_text(json.dumps(self.receipt))

    def test_current_exact_source_and_executable_pass(self):
        self.assertEqual(build.verify(),self.binary)
        self.assertIn('alliance/hero_catalog.json',self.binding['inputs'])
        self.assertIn('alliance_casual/adapter.cpp',self.binding['inputs'])
        self.assertIn('alliance_bridge/unified_protocol.hpp',self.binding['inputs'])

    def test_catalogue_change_refuses_existing_executable(self):
        (self.root/'alliance/hero_catalog.json').write_text('changed approved combat statistics')
        with self.assertRaises(build.BuildError):build.verify()

    def test_missing_or_tampered_input_cannot_keep_valid_receipt(self):
        for name in ('engine/source.cpp','alliance_casual/adapter.cpp','alliance_bridge/unified_protocol.hpp',
                     'tools/build_alliance_bridge.py'):
            path=self.root/name;before=path.read_bytes();path.unlink()
            with self.assertRaises(build.BuildError):build.verify()
            path.write_bytes(before)

    def test_wrong_protocol_and_binary_rejected(self):
        self.receipt['version']='Battle for Wesnoth server 1.19.26';self.save_receipt()
        with self.assertRaises(build.BuildError):build.verify()
        self.receipt['version']=build.VERSION;self.save_receipt();self.binary.write_bytes(b'changed')
        with self.assertRaises(build.BuildError):build.verify()

    def test_duplicate_receipt_fields_refused(self):
        (self.stage/'receipt.json').write_text('{"version":"one","version":"two"}')
        with self.assertRaises(build.BuildError):build.verify()

    def test_linked_source_refused(self):
        path=self.root/'engine/source.cpp';path.unlink();path.symlink_to(self.root/'CMakeLists.txt')
        with self.assertRaises(build.BuildError):build.binding()

    def test_changed_input_rebuild_preserves_completed_binary_and_receipts(self):
        before = {p.relative_to(self.stage).as_posix(): p.read_bytes()
                  for p in self.stage.rglob('*') if p.is_file()}
        (self.root/'engine/source.cpp').write_text('corrected source')
        backup = build.preserve_previous()
        self.assertFalse(self.stage.exists())
        self.assertEqual(before, {p.relative_to(backup).as_posix(): p.read_bytes()
                                 for p in backup.rglob('*') if p.is_file()})
        self.assertIn('-before-update-', backup.name)

    def test_same_input_completed_or_incomplete_stage_stays_for_reuse(self):
        self.assertIsNone(build.preserve_previous())
        (self.stage/'receipt.json').unlink()
        self.assertIsNone(build.preserve_previous())
        self.assertTrue(self.binary.is_file())

    def test_changed_input_incomplete_or_tampered_build_is_not_moved(self):
        (self.root/'engine/source.cpp').write_text('corrected source')
        self.binary.write_bytes(b'tampered previous binary')
        with self.assertRaises(build.BuildError): build.preserve_previous()
        self.assertTrue(self.stage.is_dir())
        (self.stage/'receipt.json').unlink()
        with self.assertRaises(build.BuildError): build.preserve_previous()
        self.assertTrue(self.stage.is_dir())

    def test_foreign_owner_cannot_be_adopted_for_update(self):
        self.binding['purpose'] = 'another build'
        (self.stage/'owner.json').write_text(json.dumps(self.binding))
        self.save_receipt()
        with self.assertRaises(build.BuildError): build.preserve_previous()
        self.assertTrue(self.stage.is_dir())

    def test_launch_config_only_references_owned_identity_and_runtime(self):
        with patch.object(run,'ROOT',self.root):
            config=run.configuration(self.root/'private runtime',self.root/'saved identity')
        self.assertIn('tls_enabled=yes\nalliance_auth=yes\n',config)
        self.assertIn('alliance_catalog=',config);self.assertIn('alliance_runtime=',config)
        self.assertIn('alliance_backend_port=18765\n',config)
        self.assertIn('connections_allowed=32\n',config)
        self.assertNotIn('bridge_secret',config);self.assertNotIn('password=',config)
        for bad in ('x"\nalliance_auth=no','x\r','x\0'):
            with self.assertRaises(ValueError):run.quoted_path(bad)


if __name__=='__main__':unittest.main()
