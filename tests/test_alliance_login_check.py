"""Real Argon2 verification with a strict read-only database double; no runtime credentials."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import warnings
from types import SimpleNamespace

from argon2 import PasswordHasher, Type
from pymongo.errors import ServerSelectionTimeoutError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("login_check", ROOT / "tools/check_alliance_login.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
REAL_CONSOLE_GUARD = CHECK.console_input_available
PLAYER_ID = "12345678-1234-4321-8765-0123456789ab"
NOW = datetime(2026, 10, 21, 12, 3, 4, tzinfo=timezone.utc)


class ReadCollection:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def find_one(self, query, projection):
        self.client.calls.append((self.name, deepcopy(query), deepcopy(projection)))
        if self.name == "accounts":
            if query != {"username_key": "uniplayer"}:
                raise AssertionError("Unexpected account lookup")
        elif self.name == "schema_metadata":
            if query != {"_id": "alliance"}:
                raise AssertionError("Unexpected schema lookup")
        elif self.name == "auth_attempts":
            bucket = int(NOW.timestamp()) // 900
            expected = hashlib.sha256(f"player:uniplayer:{bucket}".encode()).hexdigest()
            if query != {"_id": expected}:
                raise AssertionError("Unexpected attempts lookup")
        else:
            raise AssertionError("Unexpected collection")
        # Deliberately return extras: public output must never copy arbitrary fields.
        return deepcopy(self.client.documents[self.name])

    def __getattr__(self, _name):
        raise AssertionError("Only find_one is permitted")


class ReadClient:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []
        self.closed = False
        self.wesnoth_game = self
        for name in documents:
            setattr(self, name, ReadCollection(self, name))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def __getattr__(self, _name):
        raise AssertionError("Unexpected database operation")


class LoginCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "  équipe-勇者-PRIVATE_SENTINEL  "
        cls.encoded = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                                    hash_len=32, salt_len=16, type=Type.ID).hash(cls.password)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance login diagnostic ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.report_path = self.root / "report.json"
        self.private = "PRIVATE_CONFIGURATION_SENTINEL"
        self.uri = ("mongodb://wesnoth_app:" + self.private + "@127.0.0.1:27018/wesnoth_game"
                    "?authSource=wesnoth_game&replicaSet=wesnoth-rs&directConnection=true")
        (self.runtime / "owner.json").write_text(json.dumps({"format": 1, "purpose": "wesnoth-alliance-local"}))
        self.config = self.runtime / "config.json"
        self.config.write_text(json.dumps({"format": 1, "purpose": "wesnoth-alliance-local", "service": {
            "mongo_uri": self.uri, "host": "127.0.0.1", "port": 18765,
            "secret_key": "s" * 64, "bridge_secret": "b" * 64}}))
        self.documents = {
            "schema_metadata": {"version": 4},
            "accounts": {"_id": PLAYER_ID, "username": "UniPlayer", "username_key": "uniplayer",
                "role": "player", "status": "active", "password_hash": self.encoded,
                "private": self.private, "revision": 19},
            "auth_attempts": {"count": 3, "private": self.private},
        }
        self.client = ReadClient(self.documents)
        self.factory = self.enterContext(mock.patch.object(CHECK, "_client", return_value=self.client))
        self.console = self.enterContext(mock.patch.object(CHECK, "console_input_available", return_value=True))
        self.prompt = self.enterContext(mock.patch.object(CHECK.getpass, "getpass", return_value=self.password))
        clock = self.enterContext(mock.patch.object(CHECK, "datetime", wraps=datetime))
        clock.now.return_value = NOW

    def collect(self, username="UniPlayer"):
        files = {p.name: p.read_bytes() for p in self.runtime.iterdir() if p.is_file()}
        documents = deepcopy(self.documents)
        report = CHECK.collect(self.runtime, username)
        encoded = json.dumps(report)
        for private in (self.password, self.encoded, self.private, self.uri, "s" * 64, "b" * 64):
            self.assertNotIn(private, encoded)
        self.assertEqual(documents, self.documents)
        self.assertEqual(files, {p.name: p.read_bytes() for p in self.runtime.iterdir() if p.is_file()})
        self.assertFalse(report["database_writes"])
        self.assertLess(len(encoded), 2048)
        return report

    def test_match_preserves_exact_unicode_spaces_and_all_records(self):
        report = self.collect("UNIPLAYER")
        self.assertEqual((report["status"], report["outcome"], report["password_check"]),
                         ("completed", "password_match", "match"))
        self.assertEqual(report["account"], {"found": True, "id": PLAYER_ID, "role": "player", "status": "active"})
        self.assertEqual(report["rate_limit"], {"count": 3, "next_attempt_blocked": False,
                                             "window_ends_at": "2026-10-21T12:15:00Z"})
        self.assertEqual(len(self.client.calls), 3)
        self.assertTrue(self.client.closed)
        self.factory.assert_called_once_with(self.uri)
        self.prompt.assert_called_once()

    def test_mismatch_is_completed_diagnostic_and_does_not_increment_attempts(self):
        self.prompt.return_value = self.password.strip()
        report = self.collect()
        self.assertEqual((report["status"], report["outcome"]), ("completed", "password_mismatch"))
        self.assertEqual(self.documents["auth_attempts"]["count"], 3)

    def test_rate_limit_is_observed_not_enforced_or_cleared_by_password_check(self):
        for count, blocked in ((9, False), (10, True), (11, True)):
            with self.subTest(count=count):
                self.documents["auth_attempts"] = {"count": count}
                report = self.collect()
                self.assertEqual(report["password_check"], "match")
                self.assertEqual(report["rate_limit"]["next_attempt_blocked"], blocked)
        self.documents["auth_attempts"] = None
        self.assertEqual(self.collect()["rate_limit"]["count"], 0)

    def test_missing_or_ineligible_account_never_prompts(self):
        self.documents["accounts"] = None
        self.assertEqual(self.collect()["outcome"], "account_missing")
        self.documents["accounts"] = {"_id": PLAYER_ID, "username": "UniPlayer", "username_key": "uniplayer",
                                      "role": "admin", "status": "active"}
        self.assertEqual(self.collect()["outcome"], "account_ineligible")
        self.documents["accounts"].update(role="player", status="suspended")
        self.assertEqual(self.collect()["outcome"], "account_ineligible")
        self.prompt.assert_not_called()

    def test_bad_hash_and_unreasonable_cost_are_distinct_and_never_verify(self):
        for encoded, check in ((None, "invalid_hash"), ("not an encoded hash", "invalid_hash"),
                (self.encoded.replace("m=65536", "m=999999999"), "unsupported_hash"),
                (self.encoded.replace("t=3", "t=1000"), "unsupported_hash"),
                (self.encoded.replace("p=4", "p=99"), "unsupported_hash"),
                (self.encoded.replace("argon2id", "argon2i"), "unsupported_hash")):
            with self.subTest(check=check):
                self.documents["accounts"]["password_hash"] = encoded
                with mock.patch.object(CHECK, "PasswordHasher") as hasher:
                    report = self.collect()
                self.assertEqual(report["password_check"], check)
                hasher.assert_not_called()
        self.prompt.assert_not_called()

    def test_invalid_record_fields_never_escape(self):
        for key, value in (("_id", self.private), ("username", self.private), ("role", self.private),
                           ("status", self.private), ("username_key", "another_player")):
            original = self.documents["accounts"][key]
            self.documents["accounts"][key] = value
            self.assertEqual(self.collect()["outcome"], "invalid_account_record")
            self.documents["accounts"][key] = original
        for count in (True, -1, self.private, 2147483648):
            self.documents["auth_attempts"] = {"count": count}
            self.assertEqual(self.collect()["outcome"], "invalid_attempt_record")
        self.prompt.assert_not_called()

    def test_unsupported_schema_and_database_failure_are_redacted(self):
        for version in (1, 2, 3, 5, True, "4", None):
            with self.subTest(version=version):
                self.documents["schema_metadata"] = {"version": version}
                self.assertEqual(self.collect()["outcome"], "unsupported_database")
        self.factory.side_effect = ServerSelectionTimeoutError(self.uri)
        self.assertEqual(self.collect()["outcome"], "database_unavailable")
        self.prompt.assert_not_called()

    def test_input_cancellation_warning_and_invalid_password_never_verify(self):
        for failure, expected in ((EOFError(), "input_cancelled"), (KeyboardInterrupt(), "input_cancelled"),
                                  (OSError(self.private), "input_unavailable")):
            self.prompt.side_effect = failure
            self.assertEqual(self.collect()["outcome"], expected)
        def fallback(*_):
            warnings.warn(self.private, getpass.GetPassWarning)
            raise AssertionError("Must not reach echoing fallback")
        self.prompt.side_effect = fallback
        self.assertEqual(self.collect()["outcome"], "input_unavailable")
        self.prompt.side_effect = None
        for password in ("", "x" * 129, "nul\0password", "\ud800"):
            self.prompt.return_value = password
            with mock.patch.object(CHECK, "PasswordHasher") as hasher:
                report = self.collect()
            self.assertEqual(report["outcome"], "invalid_password_input")
            hasher.assert_not_called()

    def test_noninteractive_input_stops_before_database_and_prompt(self):
        self.console.return_value = False
        self.assertEqual(self.collect()["outcome"], "input_unavailable")
        self.factory.assert_not_called()
        self.prompt.assert_not_called()

    def test_real_console_guard_rejects_redirected_or_replaced_streams(self):
        # A replacement claiming isatty is still not the original console stream.
        stream = mock.Mock()
        stream.isatty.return_value = True
        with mock.patch.object(sys, "stdin", stream):
            self.assertFalse(REAL_CONSOLE_GUARD())

    def test_windows_console_guard_requires_all_three_real_console_handles(self):
        import ctypes
        from ctypes import wintypes  # Import before simulating the platform.
        streams = [mock.Mock() for _ in range(3)]
        for fd, stream in enumerate(streams):
            stream.isatty.return_value = True
            stream.fileno.return_value = fd
        modes = mock.Mock(return_value=True)
        library = SimpleNamespace(GetConsoleMode=modes)
        with mock.patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: fd + 10)}), \
                mock.patch.object(ctypes, "WinDLL", return_value=library, create=True), \
                mock.patch.object(CHECK.os, "name", "nt"), \
                mock.patch.multiple(sys, stdin=streams[0], stdout=streams[1], stderr=streams[2],
                                    __stdin__=streams[0], __stdout__=streams[1], __stderr__=streams[2]):
            self.assertTrue(REAL_CONSOLE_GUARD())
            self.assertEqual(modes.call_count, 3)
            modes.side_effect = [True, True, False]
            self.assertFalse(REAL_CONSOLE_GUARD())
            modes.side_effect = OSError(self.private)
            self.assertFalse(REAL_CONSOLE_GUARD())

    def test_invalid_username_and_config_never_reach_database(self):
        for username in (None, "bad name", "x", "x" * 25, "UniPlayer\n"):
            self.assertEqual(self.collect(username)["outcome"], "invalid_username")
        original = self.config.read_bytes()
        for raw in (b"x" * 32769, original.replace(b"127.0.0.1:27018", b"example.com:27018"),
                    original.replace(b'"format": 1', b'"format": true'),
                    original.replace(b'"format": 1', b'"format": 1, "format": 1')):
            self.config.write_bytes(raw)
            self.assertEqual(self.collect()["outcome"], "invalid_configuration")
        self.factory.assert_not_called()
        self.prompt.assert_not_called()

    def test_link_and_nonordinary_files_fail_without_reading_them(self):
        original = self.runtime / "preserved.json"
        self.config.rename(original)
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                if kind == "symlink": self.config.symlink_to(original)
                elif kind == "hardlink": os.link(original, self.config)
                else: os.mkfifo(self.config)
                try:
                    self.assertEqual(CHECK.collect(self.runtime, "UniPlayer")["outcome"], "invalid_configuration")
                finally:
                    self.config.unlink()
        self.factory.assert_not_called()

    def test_main_exclusive_sanitized_report_and_completed_mismatch_exit_zero(self):
        self.prompt.return_value = "wrong password"
        output = io.StringIO()
        args = ["--runtime", str(self.runtime), "--username", "UniPlayer", "--report", str(self.report_path)]
        with redirect_stdout(output):
            self.assertEqual(CHECK.main(args), 0)
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report["password_check"], "mismatch")
        self.assertIn("ALLIANCE LOGIN DIAGNOSTIC COMPLETE", output.getvalue())
        for private in (self.password, self.encoded, self.private, self.uri, "wrong password"):
            self.assertNotIn(private, output.getvalue() + self.report_path.read_text())
        original = self.report_path.read_bytes()
        with mock.patch.object(CHECK, "collect") as collect, redirect_stdout(io.StringIO()):
            self.assertEqual(CHECK.main(args), 1)
        collect.assert_not_called()
        self.assertEqual(self.report_path.read_bytes(), original)

    def test_report_in_runtime_or_redirected_parent_is_refused(self):
        redirected = self.root / "redirected"
        redirected.symlink_to(self.runtime, target_is_directory=True)
        for target in (self.runtime / "new.json", redirected / "new.json"):
            with mock.patch.object(CHECK, "collect") as collect, redirect_stdout(io.StringIO()):
                self.assertEqual(CHECK.main(["--runtime", str(self.runtime), "--username", "UniPlayer",
                                            "--report", str(target)]), 1)
            collect.assert_not_called()
            self.assertFalse(target.exists())

    def test_arbitrary_exception_and_unknown_diagnostic_code_are_not_reported(self):
        for error in (RuntimeError(self.private), CHECK.DiagnosticError(self.private)):
            with mock.patch.object(CHECK, "read_account", side_effect=error):
                self.assertEqual(self.collect()["outcome"], "unexpected_error")

    def test_accidental_password_argument_is_not_echoed(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as raised:
            CHECK.main(["--runtime", str(self.runtime), "--username", "UniPlayer", "--report",
                        str(self.report_path), "--password", self.password])
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn(self.password, output.getvalue())
        self.factory.assert_not_called()
        self.prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
