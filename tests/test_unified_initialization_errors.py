"""Initialization failures identify a safe stage without exposing private values.

These tests replace database/process boundaries. They never start MongoDB,
collect real credentials or change an existing runtime.
"""
from contextlib import ExitStack, contextmanager, nullcontext, redirect_stderr, redirect_stdout
import getpass
import io
from pathlib import Path
import sys
import traceback
import unittest
import warnings
from unittest.mock import MagicMock, patch

from argon2.exceptions import HashingError
from pymongo.errors import OperationFailure, PyMongoError

from alliance import deployment
from alliance.auth import AuthError
from alliance.config import ConfigurationError
from tools import alliance_fresh_start as fresh


SECRET = "PRIVATE_VALUE_mongodb://operator:never-print-this@private-host/private-db"
STAGES = {
    "runtime", "runtime-configuration", "database-start", "replica-set",
    "schema", "application-user", "administrator-input",
    "administrator-password", "administrator-account",
    "application-verification", "database-shutdown",
}
REASONS = {
    "username_input_ended", "invalid_admin_username", "password_input_unavailable",
    "password_mismatch", "invalid_password_length", "password_hash_failed",
    "database_operation_failed", "database_connection_failed", "file_access_denied",
    "file_operation_failed", "configuration_error", "interrupted", "unexpected_error",
}


class InitializationErrorTests(unittest.TestCase):
    def assert_private(self, text):
        self.assertNotIn(SECRET, text)
        self.assertNotIn("never-print-this", text)
        self.assertNotIn("private-host", text)
        self.assertNotIn("Traceback (most recent call last)", text)
        self.assertNotIn("ALLIANCE INITIALIZATION PASSED", text)
        self.assertNotIn("UNIFIED FRESH START VERIFIED", text)
        self.assertNotIn("Owned database stopped", text)

    @contextmanager
    def initialized_boundaries(self):
        """Run the real staged initializer with harmless process/database doubles."""
        roles = [{"role": "readWrite", "db": "wesnoth_game"}]
        anonymous, privileged, scoped, process = (MagicMock() for _ in range(4))
        anonymous.admin.command.return_value = {
            "setName": "wesnoth-rs", "isWritablePrimary": True,
        }
        privileged.wesnoth_game.command.return_value = {"users": [{"roles": roles}]}
        privileged.wesnoth_game.accounts.find_one.return_value = None
        scoped.__enter__.return_value.admin.command.return_value = {
            "authInfo": {"authenticatedUserRoles": roles},
        }
        process.poll.return_value = 0
        runtime = Path("/fixture-only/runtime")
        settings = MagicMock(mongo_uri="mongodb://fixture-only")
        with ExitStack() as stack:
            boundaries = {
                "runtime": stack.enter_context(patch.object(deployment, "owned_runtime", return_value=runtime)),
                "runtime-configuration": stack.enter_context(patch.object(
                    deployment, "_configure_runtime", return_value={
                        "database_admin_password": SECRET, "app_password": SECRET,
                    })),
                "database-start": stack.enter_context(patch.object(deployment, "_start_mongo", return_value=process)),
                "schema": stack.enter_context(patch("alliance.schema.bootstrap_schema")),
                "administrator-input": stack.enter_context(patch.object(
                    deployment, "_admin_credentials", return_value=("FixtureAdmin", SECRET))),
                "administrator-password": stack.enter_context(patch("alliance.auth.hash_password", return_value="fixture-hash")),
                "administrator-account": stack.enter_context(patch("alliance.domain.AllianceService")),
                "application-verification": stack.enter_context(patch.object(deployment.Settings, "load", return_value=settings)),
                "database-shutdown": stack.enter_context(patch.object(deployment, "_stop_owned")),
            }
            stack.enter_context(patch.object(deployment, "runtime_lock", return_value=nullcontext()))
            stack.enter_context(patch.object(deployment, "_client", side_effect=[anonymous, privileged, scoped]))
            stack.enter_context(patch("alliance.auth.bootstrap_auth_schema"))
            boundaries["administrator-account"] = boundaries["administrator-account"].return_value.bootstrap_admin
            boundaries["replica-set"] = anonymous.admin.command
            boundaries["application-user"] = privileged.wesnoth_game.command
            boundaries["process"] = process
            yield runtime, boundaries

    def test_public_wrapper_classifies_private_exceptions_without_their_messages(self):
        cases = (
            (lambda: AuthError("invalid_password", SECRET), "invalid_password_length"),
            (lambda: HashingError(SECRET), "password_hash_failed"),
            (lambda: OperationFailure(SECRET, code=13), "database_operation_failed"),
            (lambda: PyMongoError(SECRET), "database_connection_failed"),
            (lambda: PermissionError(SECRET), "file_access_denied"),
            (lambda: OSError(SECRET), "file_operation_failed"),
            (lambda: ConfigurationError(SECRET), "configuration_error"),
            (lambda: KeyboardInterrupt(SECRET), "interrupted"),
            (lambda: RuntimeError(SECRET), "unexpected_error"),
        )
        for make_error, reason in cases:
            with self.subTest(reason=reason):
                def fail(runtime, mongod, *, stage, **kwargs):
                    stage("administrator-password")
                    raise make_error()

                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err), \
                        patch.object(deployment, "_initialize", side_effect=fail):
                    with self.assertRaises(deployment.InitializationError) as caught:
                        deployment.initialize(Path("/fixture-only/runtime"), Path("/fixture-only/mongod"))
                self.assertEqual(caught.exception.stage, "administrator-password")
                self.assertEqual(caught.exception.reason, reason)
                self.assertIsInstance(caught.exception, ConfigurationError)
                self.assert_private(out.getvalue() + err.getvalue() + str(caught.exception))
                # Suppressed chaining must not expose a private exception if a
                # caller formats the sanitized failure for its own diagnostic.
                rendered = "".join(traceback.format_exception(caught.exception))
                self.assertNotIn(SECRET, rendered)

    def test_real_initializer_assigns_each_failure_to_its_active_stage(self):
        for stage in sorted(STAGES):
            with self.subTest(stage=stage), self.initialized_boundaries() as (runtime, boundaries):
                boundaries[stage].side_effect = RuntimeError(SECRET)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    with self.assertRaises(deployment.InitializationError) as caught:
                        deployment.initialize(runtime, Path("/fixture-only/mongod"))
                self.assertEqual(caught.exception.stage, stage)
                self.assertEqual(caught.exception.reason, "unexpected_error")
                self.assert_private(out.getvalue() + err.getvalue() + str(caught.exception))

    def test_failure_classification_never_reimports_unavailable_auth(self):
        exception_module = sys.modules["argon2.exceptions"]
        cases = (
            (exception_module, HashingError(SECRET), "password_hash_failed"),
            (exception_module, PermissionError(SECRET), "file_access_denied"),
            (exception_module, RuntimeError(SECRET), "unexpected_error"),
            (None, HashingError(SECRET), "unexpected_error"),
        )
        for loaded_exceptions, error, expected in cases:
            with self.subTest(error=type(error).__name__, exceptions_loaded=loaded_exceptions is not None):
                # A failed auth import is absent/None in sys.modules. Reporting
                # its failure must not retry the import or Argon2's initial hash.
                with patch.dict(sys.modules, {
                    "alliance.auth": None, "argon2.exceptions": loaded_exceptions,
                }), patch("builtins.__import__", side_effect=AssertionError(
                    "Failure classification attempted an import")) as imported:
                    reason = deployment._initialization_reason(error)
                imported.assert_not_called()
                self.assertEqual(reason, expected)
                self.assertNotIn(SECRET, reason)

    def test_cleanup_failure_retains_the_primary_stage_and_safe_secondary_reason(self):
        with self.initialized_boundaries() as (runtime, boundaries):
            boundaries["schema"].side_effect = OperationFailure(SECRET, code=13)
            boundaries["database-shutdown"].side_effect = PermissionError(SECRET)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                with self.assertRaises(deployment.InitializationError) as caught:
                    deployment.initialize(runtime, Path("/fixture-only/mongod"))
            self.assertEqual(caught.exception.stage, "schema")
            self.assertEqual(caught.exception.reason, "database_operation_failed")
            self.assertEqual(caught.exception.cleanup_reason, "file_access_denied")
            boundaries["database-shutdown"].assert_called_once()
            self.assert_private(out.getvalue() + err.getvalue() + str(caught.exception))

    def test_nonzero_database_exit_cannot_report_success(self):
        with self.initialized_boundaries() as (runtime, boundaries):
            boundaries["process"].poll.return_value = 14
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                with self.assertRaises(deployment.InitializationError) as caught:
                    deployment.initialize(runtime, Path("/fixture-only/mongod"))
            self.assertEqual(caught.exception.stage, "database-shutdown")
            self.assertEqual(caught.exception.reason, "configuration_error")
            self.assert_private(out.getvalue() + err.getvalue() + str(caught.exception))

    def test_error_fields_reject_untrusted_stage_and_reason_values(self):
        error = deployment.InitializationError(SECRET, SECRET, cleanup_reason=SECRET)
        self.assertIn(error.stage, STAGES | {"fresh-start"})
        self.assertIn(error.reason, REASONS)
        self.assertTrue(error.cleanup_reason is None or error.cleanup_reason in REASONS)
        self.assert_private(str(error))


class AdministratorCredentialReasonTests(unittest.TestCase):
    def capture(self, username, *, input_effect=None, password_effect=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
                patch("builtins.input", side_effect=input_effect), \
                patch("getpass.getpass", side_effect=password_effect) as hidden:
            with self.assertRaises(deployment.AdministratorInputError) as caught:
                deployment._admin_credentials(username, None)
        text = out.getvalue() + err.getvalue() + str(caught.exception)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("never-print-this", text)
        self.assertIsInstance(caught.exception, ConfigurationError)
        return caught.exception, hidden

    def test_username_eof_has_fixed_reason_before_password_collection(self):
        error, hidden = self.capture(None, input_effect=EOFError(SECRET))
        self.assertEqual(error.reason, "username_input_ended")
        self.assertIn("same runtime", str(error))
        hidden.assert_not_called()

    def test_five_invalid_usernames_have_fixed_reason_without_echo(self):
        error, hidden = self.capture(None, input_effect=[SECRET] * 5)
        self.assertEqual(error.reason, "invalid_admin_username")
        self.assertIn("invalid five times", str(error))
        hidden.assert_not_called()

    def test_hidden_input_eof_or_visible_fallback_has_fixed_reason(self):
        def visible_fallback(prompt):
            warnings.warn(SECRET, getpass.GetPassWarning)
            self.fail("Hidden input must stop before the visible fallback")

        for effect in ([EOFError(SECRET)], [SECRET, EOFError(SECRET)], visible_fallback):
            with self.subTest(effect=type(effect).__name__):
                error, _ = self.capture("FixtureAdmin", password_effect=effect)
                self.assertEqual(error.reason, "password_input_unavailable")
                self.assertIn("Hidden password input", str(error))

    def test_confirmation_mismatch_has_fixed_reason_without_either_password(self):
        error, _ = self.capture("FixtureAdmin", password_effect=[SECRET, SECRET + "different"])
        self.assertEqual(error.reason, "password_mismatch")
        self.assertIn("did not match", str(error))


class FreshStartFailureOutputTests(unittest.TestCase):
    arguments = ["--previous-runtime", "/fixture-only/old", "--backup", "/fixture-only/backup",
                 "--runtime", "/fixture-only/new", "--mongod", "/fixture-only/mongod"]

    def capture(self, error):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
                patch.object(fresh, "fresh_start", side_effect=error):
            result = fresh.main(self.arguments)
        self.assertEqual(result, 1)
        text = out.getvalue() + err.getvalue()
        self.assertNotIn(SECRET, text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("UNIFIED FRESH START VERIFIED", text)
        self.assertNotIn("ALLIANCE INITIALIZATION PASSED", text)
        self.assertNotIn("Owned database stopped", text)
        self.assertIn("UNIFIED FRESH START STOPPED", text)
        return text

    def test_staged_failure_prints_only_safe_stage_reason_and_resume_guidance(self):
        for stage, reason in (
            ("administrator-input", "password_mismatch"),
            ("administrator-password", "invalid_password_length"),
            ("administrator-password", "password_hash_failed"),
            ("schema", "database_operation_failed"),
            ("database-start", "database_connection_failed"),
            ("database-shutdown", "file_access_denied"),
        ):
            with self.subTest(stage=stage, reason=reason):
                error = deployment.InitializationError(stage, reason)
                error.__cause__ = RuntimeError(SECRET)
                text = self.capture(error)
                self.assertIn("stage=" + stage, text)
                self.assertIn("reason=" + reason, text)
                self.assertIn("runtime", text.lower())

    def test_unknown_and_interrupt_failures_are_sanitized_at_fresh_start_boundary(self):
        for error in (RuntimeError(SECRET), KeyboardInterrupt(SECRET), OSError(SECRET)):
            with self.subTest(error=type(error).__name__):
                text = self.capture(error)
                self.assertIn("stage=fresh-start", text)
                self.assertIn("reason=", text)

    def test_secondary_shutdown_error_does_not_erase_the_primary_failure(self):
        text = self.capture(deployment.InitializationError(
            "administrator-password", "password_hash_failed", cleanup_reason="file_access_denied"))
        self.assertIn("stage=administrator-password", text)
        self.assertIn("reason=password_hash_failed", text)
        self.assertIn("file_access_denied", text)


if __name__ == "__main__":
    unittest.main()
