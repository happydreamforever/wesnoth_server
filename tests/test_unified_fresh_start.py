"""Fresh-game preparation never resets an existing or already-used database."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from alliance.deployment import owned_runtime, _configure_runtime
from tools import alliance_maintenance as maintenance
from tools import alliance_fresh_start as fresh


class FreshStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="unified recovery ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.old = owned_runtime(self.base / "old runtime", create=True)
        _configure_runtime(self.old)
        (self.old / "data/WiredTiger").write_bytes(b"retained previous database")
        (self.old / "data/mongod.lock").touch()
        self.archive, self.new = self.base / "private backup", self.base / "new runtime"
        maintenance.backup(self.old, self.archive)
        self.before = maintenance.inventory(self.old)
        self.addCleanup(patch.stopall)
        patch.object(fresh, "SCHEMA_VERSION", 2).start()
        self.initialize = patch.object(fresh, "initialize", side_effect=self.initialize_fixture).start()

    def initialize_fixture(self, runtime, mongod):
        _configure_runtime(runtime)
        (runtime / "data/WiredTiger").write_bytes(b"new game only")
        (runtime / "data/mongod.lock").touch()

    def run_fresh(self):
        return fresh.fresh_start(self.old, self.archive, self.new, Path("/unused/mongod"))

    def assert_preserved(self):
        self.assertEqual(maintenance.inventory(self.old), self.before)
        self.assertEqual(maintenance.inventory(self.archive / "runtime"), self.before)

    def test_fresh_game_does_not_copy_old_accounts_or_credentials(self):
        result = self.run_fresh()
        self.assertFalse(result["reused"])
        self.assertNotEqual((self.old / "root.json").read_bytes(), (self.new / "root.json").read_bytes())
        self.assertEqual((self.new / "data/WiredTiger").read_bytes(), b"new game only")
        self.assertTrue((self.new / fresh.COMPLETE).is_file())
        self.assert_preserved()

    def test_completed_retry_never_erases_new_progress_or_initializes_again(self):
        self.run_fresh()
        (self.new / "data/players.wt").write_bytes(b"new player progress")
        before = maintenance.inventory(self.new)
        result = self.run_fresh()
        self.assertTrue(result["reused"])
        self.assertEqual(self.initialize.call_count, 1)
        self.assertEqual(maintenance.inventory(self.new), before)
        self.assert_preserved()

    def test_interrupted_initialization_resumes_same_new_runtime(self):
        self.initialize.side_effect = RuntimeError("PRIVATE_PASSWORD must not escape")
        output = io.StringIO()
        with redirect_stdout(output):
            result = fresh.main(["--previous-runtime", str(self.old), "--backup", str(self.archive),
                                 "--runtime", str(self.new), "--mongod", "/unused/mongod"])
        self.assertEqual(result, 1)
        self.assertNotIn("PRIVATE_PASSWORD", output.getvalue())
        self.assertTrue((self.new / fresh.MARKER).is_file())
        self.assertFalse((self.new / fresh.COMPLETE).exists())
        self.initialize.side_effect = self.initialize_fixture
        self.run_fresh()
        self.assertTrue((self.new / fresh.COMPLETE).exists())
        self.assert_preserved()

    def test_changed_old_database_requires_new_backup(self):
        (self.old / "data/new.wt").write_bytes(b"later progress")
        with self.assertRaisesRegex(maintenance.MaintenanceError, "backup_does_not_match"):
            self.run_fresh()
        self.initialize.assert_not_called()
        self.assertFalse(self.new.exists())

    def test_backup_tamper_refused_before_new_runtime(self):
        (self.archive / "runtime/data/WiredTiger").write_bytes(b"changed")
        with self.assertRaisesRegex(maintenance.MaintenanceError, "backup_integrity"):
            self.run_fresh()
        self.initialize.assert_not_called()
        self.assertFalse(self.new.exists())

    def test_unrelated_runtime_is_never_adopted(self):
        owned_runtime(self.new, create=True)
        (self.new / "keep").write_bytes(b"existing data")
        with self.assertRaises((FileNotFoundError, maintenance.MaintenanceError)):
            self.run_fresh()
        self.initialize.assert_not_called()
        self.assertEqual((self.new / "keep").read_bytes(), b"existing data")

    def test_changed_completion_or_source_binding_refused(self):
        self.run_fresh()
        for name in (fresh.COMPLETE, fresh.MARKER):
            path = self.new / name
            original = path.read_bytes()
            record = json.loads(original); record["schema_version"] = 999
            path.write_text(json.dumps(record))
            with self.assertRaises(maintenance.MaintenanceError): self.run_fresh()
            path.write_bytes(original)
        self.assertEqual(self.initialize.call_count, 1)
        self.assert_preserved()

    def test_any_live_game_listener_stops_before_new_runtime(self):
        for port in (15000, 15001, 15002, 18765, 27018):
            with self.subTest(port=port), socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(("127.0.0.1", port)); listener.listen()
                with self.assertRaisesRegex(maintenance.MaintenanceError, "services_must_be_stopped"):
                    self.run_fresh()
        self.initialize.assert_not_called()
        self.assertFalse(self.new.exists())


if __name__ == "__main__":
    unittest.main()
