"""Local configuration and actual authenticated MongoDB initialization/restart."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from alliance.auth import AuthService
from alliance.config import Settings, ConfigurationError
from alliance.deployment import (initialize, owned_runtime, runtime_lock, _start_mongo,
                                 _stop_owned, _client, check_database)


class ConfigurationTests(unittest.TestCase):
    def settings(self, **kw):
        values = dict(mongo_uri="mongodb://wesnoth_app:secret@127.0.0.1:27018/wesnoth_game?authSource=wesnoth_game&replicaSet=wesnoth-rs&directConnection=true",
                      secret_key="s" * 64, bridge_secret="b" * 64)
        values.update(kw)
        return Settings(**values)

    def test_fail_closed_remote_uri_wrong_db_binding_or_secrets(self):
        good = self.settings()
        self.assertNotIn("secret", repr(good))
        for wrong in (good.mongo_uri.replace("127.0.0.1", "example.com"),
                      good.mongo_uri.replace("wesnoth_game", "admin"),
                      good.mongo_uri.replace("27018", "27017"),
                      good.mongo_uri + "&tls=false", "mongodb://localhost/"):
            with self.assertRaises(ConfigurationError):
                self.settings(mongo_uri=wrong)
        with self.assertRaises(ConfigurationError):
            self.settings(host="0.0.0.0")
        with self.assertRaises(ConfigurationError):
            self.settings(secret_key="short")

    def test_refuse_unowned_directory_and_symlink_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "do-not-touch"
            sentinel.write_bytes(b"existing")
            with self.assertRaises(ConfigurationError):
                owned_runtime(root, create=True)
            self.assertEqual(sentinel.read_bytes(), b"existing")
            self.assertEqual(len(list(root.iterdir())), 1)

    def test_operation_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = owned_runtime(Path(directory) / "runtime", create=True)
            with runtime_lock(root):
                with self.assertRaises(ConfigurationError):
                    with runtime_lock(root):
                        self.fail("Lock incorrectly acquired")
            self.assertFalse((root / "operation.lock").exists())

    def test_config_non_object_and_windows_junction_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text("[]")
            with self.assertRaises(ConfigurationError):
                Settings.load(root)
            with patch.object(Path, "is_junction", return_value=True, create=True):
                with self.assertRaises(ConfigurationError):
                    owned_runtime(root, create=True)


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGOD"), "Owned MongoDB binary required")
class ActualDeploymentTests(unittest.TestCase):
    def test_authenticated_init_restart_resume_and_scoped_runtime(self):
        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        with tempfile.TemporaryDirectory(prefix="alliance deployment ") as directory:
            runtime = Path(directory) / "owned runtime"
            out = io.StringIO()
            with redirect_stdout(out):
                initialize(runtime, mongod, admin_username="Operator", admin_password="test admin password only")
            self.assertIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
            self.assertNotIn("test admin password only", out.getvalue())
            before = {name: (runtime / name).read_bytes() for name in ("config.json", "root.json", "keyfile", "mongo.json")}
            # No password argument needed: existing first admin must be preserved.
            with redirect_stdout(io.StringIO()):
                initialize(runtime, mongod)
            self.assertEqual(before, {name: (runtime / name).read_bytes() for name in before})
            settings = Settings.load(runtime)
            process = _start_mongo(runtime, mongod)
            try:
                with redirect_stdout(io.StringIO()):
                    check_database(runtime)
                with _client(settings.mongo_uri) as client:
                    token = AuthService(client.wesnoth_game).authenticate("Operator", "test admin password only", "admin")["token"]
                    self.assertEqual(AuthService(client.wesnoth_game).validate_token(token, "admin")["role"], "admin")
                    self.assertEqual(client.wesnoth_game.schema_metadata.count_documents({"check": True}), 0)
                    with self.assertRaises(OperationFailure):
                        client.admin.command("usersInfo", 1)
                with MongoClient("mongodb://127.0.0.1:27018/?directConnection=true") as anonymous:
                    with self.assertRaises(OperationFailure):
                        anonymous.wesnoth_game.accounts.find_one()
                # An already occupied port is rejected; its database remains running.
                with self.assertRaises(ConfigurationError):
                    _start_mongo(runtime, mongod)
                self.assertIsNone(process.poll())
                # Exercise actual production Waitress/CLI/socket wiring, not only
                # Flask's in-process test client. The new service stays loopback.
                with tempfile.TemporaryFile() as output:
                    service = subprocess.Popen([sys.executable, "-B", "-m", "alliance",
                        "--runtime", str(runtime), "serve"], stdout=output, stderr=output)
                    try:
                        for _ in range(50):
                            if service.poll() is not None:
                                self.fail("Production service exited during startup")
                            try:
                                with urllib.request.urlopen("http://127.0.0.1:18765/login", timeout=1) as response:
                                    html = response.read()
                                    self.assertIn(b"csrf_token", html)
                                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                                break
                            except urllib.error.URLError:
                                time.sleep(0.1)
                        else:
                            self.fail("Production service did not become ready")
                        request = urllib.request.Request("http://127.0.0.1:18765/internal/v1/health",
                            headers={"Authorization": "Bearer " + settings.bridge_secret})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            health = json.loads(response.read())
                        self.assertFalse(health["game_bridge_integrated"])
                        self.assertFalse(health["campaign_content_ready"])
                    finally:
                        service.terminate()
                        service.wait(timeout=15)
            finally:
                _stop_owned(process, runtime)


if __name__ == "__main__":
    unittest.main()
