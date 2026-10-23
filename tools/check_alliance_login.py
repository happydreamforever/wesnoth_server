"""Check one local player's stored password without attempting a login or writing to MongoDB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import warnings
from urllib.parse import urlsplit

# The Windows wrapper invokes this file with -I -B, independently of cwd/PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pymongo import timeout
from pymongo.errors import PyMongoError

from alliance.config import Settings
from alliance.deployment import owned_runtime, _client
from alliance.schema import SCHEMA_VERSION

MAX_BYTES = 32768
USERNAME = re.compile(r"[A-Za-z0-9_]{3,24}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
FAILURES = frozenset({"invalid_configuration", "invalid_username", "unsupported_database",
    "database_unavailable", "invalid_attempt_record", "invalid_account_record", "input_unavailable",
    "input_cancelled", "invalid_password_input", "unexpected_error"})


class DiagnosticError(Exception):
    """Internal fixed outcome; never include arbitrary exception text."""


def result(username=None):
    return {
        "format": 1, "purpose": "wesnoth-alliance-login-check",
        "status": "failed", "outcome": "unexpected_error", "username": username,
        "endpoint": "127.0.0.1:27018", "database": "wesnoth_game",
        "account": {"found": None, "id": None, "role": None, "status": None},
        "password_check": "not_checked",
        "rate_limit": {"count": None, "next_attempt_blocked": None, "window_ends_at": None},
        "database_writes": False,
    }


def complete(report, outcome, password_check="not_checked"):
    report.update(status="completed", outcome=outcome, password_check=password_check)
    return report


def ordinary_json(path):
    """Bound reads before Settings.load/owned_runtime inspect the same ordinary files."""
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError()
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_BYTES:
        raise ValueError()
    with path.open("rb") as source:
        after = os.fstat(source.fileno())
        if (not stat.S_ISREG(after.st_mode) or after.st_nlink != 1 or after.st_size > MAX_BYTES
                or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError()
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError()
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError()
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError()
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)


def local_settings(runtime):
    try:
        if not runtime.is_absolute() or ".." in runtime.parts:
            raise ValueError()
        owner = ordinary_json(runtime / "owner.json")
        if (not isinstance(owner, dict) or type(owner.get("format")) is not int
                or owner != {"purpose": "wesnoth-alliance-local", "format": 1}):
            raise ValueError()
        config = ordinary_json(runtime / "config.json")
        if (not isinstance(config, dict) or type(config.get("format")) is not int
                or config.get("format") != 1):
            raise ValueError()
        path = owned_runtime(runtime)
        settings = Settings.load(path)
        # Avoid even DNS resolution: this diagnostic only uses the fixed IPv4 endpoint.
        if urlsplit(settings.mongo_uri).hostname != "127.0.0.1":
            raise ValueError()
        return settings
    except Exception:
        raise DiagnosticError("invalid_configuration") from None


def read_account(runtime, username):
    """Exactly three bounded reads; no auth service, transactions, updates or initialization."""
    report = result(username if isinstance(username, str) and USERNAME.fullmatch(username) else None)
    if report["username"] is None:
        raise DiagnosticError("invalid_username")
    settings = local_settings(runtime)
    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp()) // 900
    attempt_id = hashlib.sha256(f"player:{username.casefold()}:{bucket}".encode()).hexdigest()
    try:
        with _client(settings.mongo_uri) as client, timeout(6):
            db = client.wesnoth_game
            schema = db.schema_metadata.find_one({"_id": "alliance"}, {"_id": 0, "version": 1})
            if not schema or type(schema.get("version")) is not int or schema["version"] != SCHEMA_VERSION:
                raise DiagnosticError("unsupported_database")
            account = db.accounts.find_one({"username_key": username.casefold()}, {
                "_id": 1, "username": 1, "username_key": 1, "role": 1,
                "status": 1, "password_hash": 1})
            attempt = db.auth_attempts.find_one({"_id": attempt_id}, {"_id": 0, "count": 1})
    except PyMongoError:
        raise DiagnosticError("database_unavailable") from None
    count = 0 if attempt is None else attempt.get("count")
    if type(count) is not int or not 0 <= count <= 2147483647:
        raise DiagnosticError("invalid_attempt_record")
    report["rate_limit"] = {"count": count, "next_attempt_blocked": count >= 10,
        "window_ends_at": datetime.fromtimestamp((bucket + 1) * 900, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    report["account"]["found"] = account is not None
    if account is None:
        return complete(report, "account_missing"), None
    if (not isinstance(account.get("_id"), str) or not UUID.fullmatch(account["_id"])
            or not isinstance(account.get("username"), str) or not USERNAME.fullmatch(account["username"])
            or account["username"].casefold() != username.casefold()
            or account.get("username_key") != username.casefold()
            or account.get("role") not in ("player", "admin")
            or account.get("status") not in ("active", "suspended")):
        raise DiagnosticError("invalid_account_record")
    report["account"].update(id=account["_id"], role=account["role"], status=account["status"])
    if account["role"] != "player" or account["status"] != "active":
        return complete(report, "account_ineligible"), None
    return report, account.get("password_hash")


def hash_state(encoded):
    """Reject malformed encodings and excessive stored costs before Argon2 allocates memory."""
    if not isinstance(encoded, str) or not encoded.isascii() or len(encoded) > 512:
        return "invalid_hash"
    try:
        parameters = extract_parameters(encoded)
    except (InvalidHashError, ValueError, TypeError):
        return "invalid_hash"
    if (parameters.type != Type.ID or parameters.version != 19
            or not 1 <= parameters.time_cost <= 10
            or not 1 <= parameters.parallelism <= 16
            or not 8 * parameters.parallelism <= parameters.memory_cost <= 262144
            or not 8 <= parameters.salt_len <= 64 or not 16 <= parameters.hash_len <= 64):
        return "unsupported_hash"
    return "supported"


def console_input_available():
    try:
        streams = (sys.stdin, sys.stdout, sys.stderr)
        originals = (sys.__stdin__, sys.__stdout__, sys.__stderr__)
        if any(stream is not original or not stream.isatty()
               for stream, original in zip(streams, originals)):
            return False
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes
            get_mode = ctypes.WinDLL("kernel32", use_last_error=True).GetConsoleMode
            get_mode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            get_mode.restype = wintypes.BOOL
            for stream in streams:
                mode = wintypes.DWORD()
                if not get_mode(msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(mode)):
                    return False
        return True
    except Exception:
        return False


def read_password():
    if not console_input_available():
        raise DiagnosticError("input_unavailable")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("Player password (hidden; checked locally once): ")
    except (KeyboardInterrupt, EOFError):
        raise DiagnosticError("input_cancelled") from None
    except Exception:
        raise DiagnosticError("input_unavailable") from None


def collect(runtime, username):
    report = result(username if isinstance(username, str) and USERNAME.fullmatch(username) else None)
    password = encoded = None
    try:
        # Reject redirected input before accessing the database, even if no password would be needed.
        if not console_input_available():
            raise DiagnosticError("input_unavailable")
        report, encoded = read_account(runtime, username)
        if report["status"] == "completed":
            return report
        state = hash_state(encoded)
        if state != "supported":
            return complete(report, "invalid_stored_hash" if state == "invalid_hash" else "unsupported_stored_hash", state)
        password = read_password()
        try:
            valid_password = (isinstance(password, str) and 1 <= len(password) <= 128
                              and "\0" not in password and len(password.encode("utf-8")) <= 512)
        except UnicodeError:
            valid_password = False
        if not valid_password:
            raise DiagnosticError("invalid_password_input")
        try:
            matched = PasswordHasher().verify(encoded, password)
        except VerifyMismatchError:
            matched = False
        except (InvalidHashError, VerificationError):
            return complete(report, "invalid_stored_hash", "invalid_hash")
        return complete(report, "password_match" if matched else "password_mismatch", "match" if matched else "mismatch")
    except DiagnosticError as error:
        code = error.args[0] if error.args and error.args[0] in FAILURES else "unexpected_error"
        report.update(status="failed", outcome=code)
        return report
    except (KeyboardInterrupt, EOFError):
        report.update(status="failed", outcome="input_cancelled")
        return report
    except Exception:
        report.update(status="failed", outcome="unexpected_error")
        return report
    finally:
        # Drop references; Python strings do not provide guaranteed memory erasure.
        password = encoded = None


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "ALLIANCE LOGIN DIAGNOSTIC FAILED: invalid arguments; no password argument is accepted.\n")


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.report.is_absolute() or ".." in args.report.parts:
            raise ValueError()
        for path in args.report.parents:
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError()
        if args.report.resolve().is_relative_to(args.runtime.resolve()):
            raise ValueError()
        # Reserve the new output before database reads or a hidden-input prompt.
        with args.report.open("x", encoding="ascii", newline="\n") as output:
            report = collect(args.runtime, args.username)
            json.dump(report, output, indent=2, ensure_ascii=True)
            output.write("\n")
    except (OSError, ValueError, RuntimeError):
        print("ALLIANCE LOGIN DIAGNOSTIC FAILED: report unavailable; existing files preserved.")
        return 1
    print("outcome=" + report["outcome"] + "; password_check=" + report["password_check"])
    print("No login was attempted. Accounts, passwords, sessions and attempt counters were not changed.")
    print("ALLIANCE LOGIN DIAGNOSTIC " + ("COMPLETE" if report["status"] == "completed" else "FAILED"))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
