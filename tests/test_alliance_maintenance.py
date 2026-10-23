"""Cold-copy invariants plus opt-in real offline authenticated restore."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from alliance.deployment import (_configure_runtime, _client, _credentials, _start_mongo,
    _stop_owned, _uri, initialize, owned_runtime)
from alliance.runtime_lock import runtime_lock
from tools import alliance_maintenance as maintenance


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance maintenance ")
        self.base = Path(self.temp.name)
        self.runtime = owned_runtime(self.base / "original", create=True)
        _configure_runtime(self.runtime)
        (self.runtime / "data/WiredTiger").write_bytes(b"fixture format")
        (self.runtime / "data/mongod.lock").touch()
        (self.runtime / "data/collection.wt").write_bytes(b"private player data")
        self.before = maintenance.inventory(self.runtime)

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_private_exact_copy_no_schema_claim(self):
        destination = self.base / "backup"
        result = maintenance.backup(self.runtime, destination)
        self.assertFalse(result["schema_checked"])
        self.assertEqual(maintenance.inventory(destination / "runtime"), self.before)
        self.assertEqual(maintenance.inventory(self.runtime), self.before)
        self.assertFalse((destination / "INCOMPLETE").exists())
        if os.name != "nt":
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual((destination / "runtime/keyfile").stat().st_mode & 0o777, 0o600)

    def test_live_runtime_lock_refuses_before_destination(self):
        destination = self.base / "backup"
        with runtime_lock(self.runtime):
            with self.assertRaises(ValueError): maintenance.backup(self.runtime, destination)
        self.assertFalse(destination.exists())

    def test_each_service_port_must_be_stopped(self):
        for port in (27018, 18765, 15001, 15002):
            with self.subTest(port=port), socket.socket() as listener:
                listener.bind(("127.0.0.1", port)); listener.listen()
                with self.assertRaisesRegex(maintenance.MaintenanceError, "services_must_be_stopped"):
                    maintenance.backup(self.runtime, self.base / "backup")
        self.assertFalse((self.base / "backup").exists())

    def test_dirty_shutdown_refuses_before_destination(self):
        (self.runtime / "data/mongod.lock").write_text("1234")
        with self.assertRaisesRegex(maintenance.MaintenanceError, "not_cleanly_stopped"):
            maintenance.backup(self.runtime, self.base / "backup")
        self.assertFalse((self.base / "backup").exists())

    def test_links_hardlinks_and_redirected_ancestors_refused(self):
        data = self.runtime / "data/collection.wt"
        link = self.runtime / "data/link"
        link.symlink_to(data)
        with self.assertRaises(maintenance.MaintenanceError): maintenance.inventory(self.runtime)
        link.unlink(); os.link(data, link)
        with self.assertRaises(maintenance.MaintenanceError): maintenance.inventory(self.runtime)
        link.unlink()
        parent = self.base / "redirect"
        parent.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(maintenance.MaintenanceError):
            maintenance.backup(self.runtime, parent / "backup")

    def test_existing_or_overlapping_destination_preserved(self):
        target = self.base / "existing"; target.mkdir(); (target / "sentinel").write_bytes(b"keep")
        for destination in (target, self.runtime / "backup", self.base):
            with self.subTest(destination=destination), self.assertRaises(maintenance.MaintenanceError):
                maintenance.backup(self.runtime, destination)
        self.assertEqual((target / "sentinel").read_bytes(), b"keep")
        self.assertEqual(maintenance.inventory(self.runtime), self.before)

    def test_new_restore_rebases_only_copy_then_verifies(self):
        archived = self.base / "backup"; target = self.base / "restored"
        maintenance.backup(self.runtime, archived)
        with patch.object(maintenance, "verify_restore") as verify:
            result = maintenance.restore(self.runtime, archived, target, Path("/unused/mongod"))
        verify.assert_called_once()
        self.assertTrue(result["original_unchanged"])
        self.assertFalse(result["activation_performed"])
        self.assertEqual(json.loads((target / "mongo.json").read_text())["storage"]["dbPath"], str(target / "data"))
        self.assertEqual((target / "root.json").read_bytes(), (self.runtime / "root.json").read_bytes())
        self.assertEqual(maintenance.inventory(self.runtime), self.before)
        self.assertEqual(maintenance.inventory(archived / "runtime"), self.before)
        self.assertFalse((target / "RESTORE_INCOMPLETE").exists())

    def test_tamper_incomplete_and_wrong_version_never_start(self):
        archived = self.base / "backup"; maintenance.backup(self.runtime, archived)
        manifest = archived / "manifest.json"; original = manifest.read_bytes()
        for failure in ("tamper", "incomplete", "version"):
            with self.subTest(failure=failure), patch.object(maintenance, "verify_restore") as verify:
                if failure == "tamper": (archived / "runtime/data/collection.wt").write_bytes(b"tampered")
                elif failure == "incomplete": (archived / "INCOMPLETE").touch()
                else:
                    content = json.loads(original); content["producer_schema_version"] = 999
                    manifest.write_text(json.dumps(content))
                with self.assertRaises(maintenance.MaintenanceError):
                    maintenance.restore(self.runtime, archived, self.base / "restored", Path("/unused"))
                verify.assert_not_called()
                self.assertFalse((self.base / "restored").exists())
                (archived / "runtime/data/collection.wt").write_bytes(b"private player data")
                (archived / "INCOMPLETE").unlink(missing_ok=True); manifest.write_bytes(original)

    def test_failed_restore_keeps_incomplete_copy_and_original(self):
        archived = self.base / "backup"; target = self.base / "restored"
        maintenance.backup(self.runtime, archived)
        with patch.object(maintenance, "verify_restore", side_effect=RuntimeError("PRIVATE_SECRET")):
            output = io.StringIO()
            with redirect_stdout(output):
                code = maintenance.main(["restore", "--runtime", str(self.runtime), "--backup", str(archived),
                    "--destination", str(target), "--mongod", "/unused"])
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_SECRET", output.getvalue())
        self.assertNotIn(_credentials(self.runtime)["app_password"], output.getvalue())
        self.assertTrue((target / "RESTORE_INCOMPLETE").is_file())
        self.assertEqual(maintenance.inventory(self.runtime), self.before)

    def test_restore_recovery_does_not_require_healthy_original(self):
        archived = self.base / "backup"
        maintenance.backup(self.runtime, archived)
        (self.runtime / "config.json").unlink()
        (self.runtime / "data/WiredTiger").write_bytes(b"damaged")
        (self.runtime / "data/mongod.lock").write_bytes(b"old crashed process")
        damaged = maintenance.inventory(self.runtime, recovery_source=True)
        with patch.object(maintenance, "verify_restore"):
            result = maintenance.restore(self.runtime, archived, self.base / "restored", Path("/unused"))
        self.assertTrue(result["original_present"])
        self.assertEqual(maintenance.inventory(self.runtime, recovery_source=True), damaged)
        self.assertEqual((self.base / "restored/data/WiredTiger").read_bytes(), b"fixture format")

    def test_restore_can_recover_when_original_is_missing(self):
        archived = self.base / "backup"
        maintenance.backup(self.runtime, archived)
        missing = self.base / "missing-original"
        with patch.object(maintenance, "verify_restore"):
            result = maintenance.restore(missing, archived, self.base / "restored", Path("/unused"))
        self.assertFalse(result["original_present"])
        self.assertFalse(missing.exists())
        self.assertEqual(maintenance.inventory(self.runtime), self.before)

    def test_shared_room_event_replay_and_partial_files_are_retained(self):
        battle = self.runtime / "battles/00000000-0000-4000-8000-000000000001"
        battle.mkdir(parents=True)
        for name in ("room.json", "events.jsonl", "player-hash.replay", "player.replay.partial"):
            (battle / name).write_bytes(("private " + name).encode())
        guard = self.runtime / "battles/daemon.lock"; guard.write_bytes(b"0")
        archived = self.base / "backup"
        maintenance.backup(self.runtime, archived)
        for name in ("room.json", "events.jsonl", "player-hash.replay", "player.replay.partial"):
            self.assertEqual((archived / "runtime" / battle.relative_to(self.runtime) / name).read_bytes(), (battle / name).read_bytes())
        self.assertFalse((archived / "runtime/battles/daemon.lock").exists())
        self.assertEqual(guard.read_bytes(), b"0")
        with patch.object(maintenance, "verify_restore"):
            maintenance.restore(self.runtime, archived, self.base / "restored", Path("/unused"))
        self.assertEqual((self.base / "restored" / battle.relative_to(self.runtime) / "events.jsonl").read_bytes(), b"private events.jsonl")

    def test_live_battle_guard_refuses_even_before_listener_is_open(self):
        storage = self.runtime / "battles"; storage.mkdir()
        (storage / "daemon.lock").write_bytes(b"0")
        with maintenance.battle_storage_lock(self.runtime):
            with self.assertRaisesRegex(maintenance.MaintenanceError, "battle_service_must_be_stopped"):
                maintenance.backup(self.runtime, self.base / "backup")
        self.assertFalse((self.base / "backup").exists())


@unittest.skipUnless(os.environ.get("ALLIANCE_MAINTENANCE_MONGO"), "Requires disposable offline MongoDB")
class RealRestoreTests(unittest.TestCase):
    def test_real_authenticated_backup_restore_preserves_all_records(self):
        from bson import BSON
        mongod = Path(os.environ["ALLIANCE_MAINTENANCE_MONGO"])
        with tempfile.TemporaryDirectory(prefix="alliance real restore ") as directory:
            root = Path(directory); source = root / "original"
            initialize(source, mongod, admin_username="FixtureAdmin", admin_password="fixture-local-password-123")
            credentials = _credentials(source)
            process = _start_mongo(source, mongod)
            try:
                with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
                    deadline = time.monotonic() + 30
                    while not client.admin.command("hello").get("isWritablePrimary"):
                        self.assertLess(time.monotonic(), deadline); time.sleep(.1)
                    db = client.wesnoth_game
                    from alliance.domain import AllianceService
                    from alliance.auth import hash_password
                    service = AllianceService(db)
                    player = service.register("RestoredPlayer", hash_password("fixture-player-password-123"))
                    service.create_team(player["_id"], "Saved Team")
                    db.areas.update_one({"_id": "area-1"}, {"$set": {"name": "Saved Area", "name_key": "saved area"}})
                    before = {name: sorted(BSON.encode(row) for row in db[name].find({}))
                              for name in db.list_collection_names()}
            finally: _stop_owned(process, source)
            hashes = maintenance.inventory(source)
            maintenance.backup(source, root / "backup")
            result = maintenance.restore(source, root / "backup", root / "restored", mongod)
            self.assertTrue(result["schema_checked"])
            self.assertEqual(maintenance.inventory(source), hashes)
            restored = root / "restored"; process = _start_mongo(restored, mongod)
            try:
                with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
                    deadline = time.monotonic() + 30
                    while not client.admin.command("hello").get("isWritablePrimary"):
                        self.assertLess(time.monotonic(), deadline); time.sleep(.1)
                    db = client.wesnoth_game
                    after = {name: sorted(BSON.encode(row) for row in db[name].find({}))
                             for name in db.list_collection_names()}
                    self.assertEqual(before, after)
            finally: _stop_owned(process, restored)

    def test_real_unsupported_database_schema_keeps_copy_incomplete(self):
        mongod = Path(os.environ["ALLIANCE_MAINTENANCE_MONGO"])
        with tempfile.TemporaryDirectory(prefix="alliance schema restore ") as directory:
            root = Path(directory); source = root / "original"
            initialize(source, mongod, admin_username="FixtureAdmin", admin_password="fixture-local-password-123")
            credentials = _credentials(source)
            process = _start_mongo(source, mongod)
            try:
                with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
                    deadline = time.monotonic() + 30
                    while not client.admin.command("hello").get("isWritablePrimary"):
                        self.assertLess(time.monotonic(), deadline); time.sleep(.1)
                    client.wesnoth_game.schema_metadata.update_one({"_id": "alliance"}, {"$set": {"version": 999}})
            finally: _stop_owned(process, source)
            before = maintenance.inventory(source)
            maintenance.backup(source, root / "backup")
            with self.assertRaisesRegex(ValueError, "schema"):
                maintenance.restore(source, root / "backup", root / "restored", mongod)
            self.assertTrue((root / "restored/RESTORE_INCOMPLETE").is_file())
            self.assertFalse((root / "restored/restore-verified.json").exists())
            self.assertEqual(maintenance.inventory(source), before)
            self.assertEqual((root / "restored/data/mongod.lock").stat().st_size, 0)


if __name__ == "__main__": unittest.main()
