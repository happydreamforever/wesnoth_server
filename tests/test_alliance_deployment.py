"""Local configuration and actual authenticated MongoDB initialization/restart."""
from contextlib import redirect_stdout, redirect_stderr
import getpass
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
import warnings
from unittest.mock import MagicMock, patch
import urllib.request
import urllib.error

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from alliance.auth import AuthService
from alliance.config import Settings, ConfigurationError
from alliance.deployment import (initialize, owned_runtime, runtime_lock, _start_mongo,
                                 _stop_owned, _client, check_database, _admin_credentials)
from alliance.domain import DomainError, validate_username


class AdministratorInputTests(unittest.TestCase):
    def test_invalid_username_reprompts_before_any_hidden_password_read(self):
        class ObservedOutput(io.StringIO):
            flushes = 0

            def flush(self):
                self.flushes += 1
                return super().flush()

        out, err = ObservedOutput(), io.StringIO()
        names = iter(("", "secret-looking invalid name", "Üni", " Uni_Admin "))
        reads = []
        password = "unit test password only"

        def read_username(*args):
            self.assertEqual(args, ())
            self.assertTrue(out.getvalue().endswith("digits or underscores):\n"))
            self.assertGreaterEqual(out.flushes, len(reads) + 1)
            self.assertEqual(hidden.call_count, 0)
            value = next(names)
            reads.append(value)
            return value

        def read_password(prompt):
            self.assertEqual(len(reads), 4)
            self.assertIn("password", prompt)
            return password

        with redirect_stdout(out), redirect_stderr(err), \
             patch("builtins.input", side_effect=read_username), \
             patch("getpass.getpass", side_effect=read_password) as hidden:
            self.assertEqual(_admin_credentials(None, None), ("Uni_Admin", password))
        self.assertEqual(hidden.call_count, 2)
        self.assertEqual(out.getvalue().count("Use 3-24 ASCII"), 3)
        for value in ("secret-looking invalid name", "Üni", "Uni_Admin", password):
            self.assertNotIn(value, out.getvalue() + err.getvalue())

    def test_explicit_username_uses_shared_rule_before_any_password_prompt(self):
        with patch("builtins.input", side_effect=AssertionError("No username prompt")), \
             patch("getpass.getpass", side_effect=AssertionError("No password prompt")):
            for value in ("", "ab", "a" * 25, "bad-name", "Üni", 123):
                with self.subTest(value=value):
                    with self.assertRaises(DomainError):
                        validate_username(value)
                    with self.assertRaises(DomainError):
                        _admin_credentials(value, None)
            self.assertEqual(_admin_credentials(" Uni_Admin ", "supplied test password"),
                             ("Uni_Admin", "supplied test password"))
            for value in ("Ab3", "a" * 24):
                self.assertEqual(_admin_credentials(value, "supplied test password")[0], value)

    def test_username_eof_is_actionable_and_does_not_read_password(self):
        with redirect_stdout(io.StringIO()), \
             patch("builtins.input", side_effect=EOFError), \
             patch("getpass.getpass") as hidden:
            with self.assertRaisesRegex(ConfigurationError, "same runtime"):
                _admin_credentials(None, None)
        hidden.assert_not_called()

    def test_repeated_invalid_usernames_stop_without_password_collection(self):
        with redirect_stdout(io.StringIO()), \
             patch("builtins.input", return_value="bad name") as username, \
             patch("getpass.getpass") as hidden:
            with self.assertRaisesRegex(ConfigurationError, "invalid five times"):
                _admin_credentials(None, None)
        self.assertEqual(username.call_count, 5)
        hidden.assert_not_called()

    def test_hidden_input_eof_or_visible_fallback_stop_without_echo(self):
        password = "must never appear in output"
        for stage in ("first-eof", "confirmation-eof", "fallback"):
            with self.subTest(stage=stage):
                out, err = io.StringIO(), io.StringIO()

                def fallback(prompt):
                    warnings.warn("Can not control echo on the terminal.", getpass.GetPassWarning)
                    self.fail("Password read must stop before visible fallback")

                effect = fallback if stage == "fallback" else (
                    [EOFError()] if stage == "first-eof" else [password, EOFError()])
                with redirect_stdout(out), redirect_stderr(err), \
                     patch("getpass.getpass", side_effect=effect):
                    with self.assertRaisesRegex(ConfigurationError, "Hidden password input") as caught:
                        _admin_credentials("UniAdmin", None)
                self.assertNotIn(password, out.getvalue() + err.getvalue() + str(caught.exception))
                self.assertIn("same runtime", str(caught.exception))

    def test_confirmation_mismatch_keeps_passwords_out_of_error(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
             patch("getpass.getpass", side_effect=["first test password", "second test password"]):
            with self.assertRaisesRegex(ConfigurationError, "did not match") as caught:
                _admin_credentials("UniAdmin", None)
        for value in ("first test password", "second test password"):
            self.assertNotIn(value, out.getvalue() + err.getvalue() + str(caught.exception))


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

    def test_redirected_ancestor_is_rejected_before_creating_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "existing profile"
            target.mkdir()
            sentinel = target / "preserve.txt"
            sentinel.write_bytes(b"existing profile data")
            link = root / "redirected profile"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ConfigurationError, "parents"):
                owned_runtime(link / "WesnothAlliance" / "runtime", create=True)
            self.assertEqual(sentinel.read_bytes(), b"existing profile data")
            self.assertEqual(list(target.iterdir()), [sentinel])
            self.assertTrue(link.is_symlink())

            dangling = root / "missing redirected profile"
            missing_target = root / "missing target"
            dangling.symlink_to(missing_target, target_is_directory=True)
            with self.assertRaisesRegex(ConfigurationError, "parents"):
                owned_runtime(dangling / "runtime", create=True)
            self.assertFalse(missing_target.exists())

    def test_junction_ancestor_and_parent_traversal_are_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            profile.mkdir()
            with patch.object(Path, "is_junction", lambda item: item == profile, create=True):
                with self.assertRaisesRegex(ConfigurationError, "parents"):
                    owned_runtime(profile / "WesnothAlliance" / "runtime", create=True)
            self.assertEqual(list(profile.iterdir()), [])
            with self.assertRaisesRegex(ConfigurationError, "parent traversal"):
                owned_runtime(profile / ".." / "runtime", create=True)
            self.assertFalse((root / "runtime").exists())

    def test_start_failure_points_to_selected_runtime_log(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "Local App Data" / "WesnothAlliance" / "runtime"
            process = MagicMock()
            process.poll.return_value = 14
            client = MagicMock()
            with patch("alliance.deployment._check_mongod"), \
                 patch("alliance.deployment.socket.socket") as socket_factory, \
                 patch("alliance.deployment.subprocess.Popen", return_value=process), \
                 patch("alliance.deployment._client", return_value=client), \
                 patch("alliance.deployment._stop_owned") as stop:
                socket_factory.return_value.__enter__.return_value.connect_ex.return_value = 1
                with self.assertRaises(ConfigurationError) as caught:
                    _start_mongo(runtime, Path("mongod"))
            self.assertIn(str(runtime / "logs" / "mongodb.log"), str(caught.exception))
            stop.assert_called_once_with(process, runtime)
            client.close.assert_called_once()
            self.assertFalse(runtime.exists())

    def test_initialization_success_follows_confirmed_cleanup(self):
        for exit_code, cleanup_error in ((0, None), (14, None), (None, None),
                                         (0, RuntimeError("cleanup failed"))):
            with self.subTest(exit_code=exit_code, cleanup_error=cleanup_error), \
                 tempfile.TemporaryDirectory() as directory:
                runtime = owned_runtime(Path(directory) / "runtime", create=True)
                owner = (runtime / "owner.json").read_bytes()
                process = MagicMock()
                process.poll.return_value = exit_code
                anonymous, privileged, scoped = MagicMock(), MagicMock(), MagicMock()
                roles = [{"role": "readWrite", "db": "wesnoth_game"}]
                anonymous.admin.command.return_value = {
                    "setName": "wesnoth-rs", "isWritablePrimary": True}
                privileged.wesnoth_game.command.return_value = {"users": [{"roles": roles}]}
                privileged.wesnoth_game.accounts.find_one.return_value = {"role": "admin"}
                scoped.__enter__.return_value.admin.command.return_value = {
                    "authInfo": {"authenticatedUserRoles": roles}}
                out = io.StringIO()
                def cleanup(*args):
                    self.assertNotIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
                    self.assertNotIn("Owned database stopped", out.getvalue())
                    if cleanup_error is not None:
                        raise cleanup_error
                with redirect_stdout(out), \
                     patch("alliance.deployment._configure_runtime",
                           return_value={"database_admin_password": "test only"}), \
                     patch("alliance.deployment._start_mongo", return_value=process), \
                     patch("alliance.deployment._client",
                           side_effect=[anonymous, privileged, scoped]), \
                     patch("alliance.deployment._stop_owned", side_effect=cleanup) as stop, \
                     patch("alliance.deployment.Settings.load"), \
                     patch("alliance.schema.bootstrap_schema"), \
                     patch("alliance.auth.bootstrap_auth_schema"):
                    if cleanup_error is not None:
                        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                            initialize(runtime, Path("mongod"))
                    elif exit_code != 0:
                        with self.assertRaisesRegex(ConfigurationError, "did not exit cleanly"):
                            initialize(runtime, Path("mongod"))
                    else:
                        initialize(runtime, Path("mongod"))
                stop.assert_called_once_with(process, runtime)
                if exit_code == 0 and cleanup_error is None:
                    self.assertIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
                    self.assertIn("Owned database stopped", out.getvalue())
                else:
                    self.assertNotIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
                    self.assertNotIn("Owned database stopped", out.getvalue())
                self.assertEqual((runtime / "owner.json").read_bytes(), owner)
                self.assertFalse((runtime / "operation.lock").exists())


@unittest.skipUnless(os.environ.get("ALLIANCE_TEST_MONGOD"), "Owned MongoDB binary required")
class ActualDeploymentTests(unittest.TestCase):
    def test_authenticated_init_restart_resume_and_scoped_runtime(self):
        mongod = Path(os.environ["ALLIANCE_TEST_MONGOD"])
        with tempfile.TemporaryDirectory(prefix="alliance deployment ") as directory:
            root = Path(directory)
            old_runtime = root / "old repository" / "runtime" / "alliance"
            old_runtime.mkdir(parents=True)
            sentinel = old_runtime / "preserved-existing-data"
            sentinel.write_bytes(b"Existing game database stays here.")
            runtime = root / "Local App Data" / "WesnothAlliance" / "runtime"
            out = io.StringIO()
            # Invalid first-admin input must leave an owned resumable database,
            # release its operation lock and avoid collecting a password.
            with redirect_stdout(out), \
                 patch("getpass.getpass", side_effect=AssertionError("Invalid username must fail first")):
                with self.assertRaises(DomainError):
                    initialize(runtime, mongod, admin_username="invalid operator")
            self.assertNotIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
            self.assertFalse((runtime / "operation.lock").exists())
            before = {name: (runtime / name).read_bytes() for name in
                      ("owner.json", "config.json", "root.json", "keyfile", "mongo.json")}
            with redirect_stdout(out), \
                 patch("builtins.input", side_effect=["bad operator", "Operator"]), \
                 patch("getpass.getpass", return_value="test admin password only"):
                initialize(runtime, mongod)
            self.assertIn("ALLIANCE INITIALIZATION PASSED", out.getvalue())
            self.assertNotIn("test admin password only", out.getvalue())
            self.assertNotIn("bad operator", out.getvalue())
            self.assertEqual(before, {name: (runtime / name).read_bytes() for name in before})
            mongo_config = json.loads(before["mongo.json"])
            self.assertEqual(mongo_config["storage"]["dbPath"], str(runtime / "data"))
            self.assertEqual(mongo_config["systemLog"]["path"], str(runtime / "logs" / "mongodb.log"))
            # No password argument needed: existing first admin must be preserved.
            with redirect_stdout(io.StringIO()), \
                 patch("builtins.input", side_effect=AssertionError("Existing admin must not prompt")), \
                 patch("getpass.getpass", side_effect=AssertionError("Existing admin must not prompt")):
                initialize(runtime, mongod)
            self.assertEqual(before, {name: (runtime / name).read_bytes() for name in before})
            self.assertEqual(sentinel.read_bytes(), b"Existing game database stays here.")
            self.assertEqual(list(old_runtime.iterdir()), [sentinel])
            self.assertFalse((runtime / "operation.lock").exists())
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
