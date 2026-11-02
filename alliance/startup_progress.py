"""Bounded, per-launch battle startup diagnostics; never a health credential.

Only the workflow creates the header. The child appends four fixed phases. A
partial last append is pending; replacement, malformed or foreign data fails
closed. The workflow still requires the pinned TLS health response for PASS.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import uuid4

PHASES = ("runtime", "worker_verification", "listener", "serving")
PURPOSE = "wesnoth-battle-startup"
MAX_BYTES = 8192


class ProgressError(ValueError):
    """Fixed diagnostics only; never include arbitrary file content."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ProgressError("invalid_startup_launch_id")
    return value


def _path(value):
    path = Path(value)
    if not path.is_absolute():
        raise ProgressError("startup_progress_path_not_absolute")
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProgressError("startup_progress_redirected")
    return path


def _identity(path, fd):
    actual, named = os.fstat(fd), path.lstat()
    if (not stat.S_ISREG(actual.st_mode) or not stat.S_ISREG(named.st_mode)
            or actual.st_nlink != 1 or named.st_nlink != 1
            or getattr(named, "st_file_attributes", 0) & 0x400
            or (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
        raise ProgressError("startup_progress_file_changed")
    return actual


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def create_progress(value, launch_id=None):
    path = _path(value)
    launch_id = _identifier(launch_id if launch_id is not None else uuid4().hex)
    raw = _json({"format": 1, "purpose": PURPOSE, "launch_id": launch_id, "created_at_utc": utc_now()})
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_BINARY", 0), 0o600)
    try:
        _identity(path, fd)
        if os.write(fd, raw) != len(raw):
            raise ProgressError("startup_progress_write_incomplete")
        os.fsync(fd)
        _identity(path, fd)
    finally:
        os.close(fd)
    return launch_id


def _read(value):
    path = _path(value)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
        raise ProgressError("startup_progress_not_bounded_file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_BINARY", 0))
    try:
        info = _identity(path, fd)
        raw = os.read(fd, MAX_BYTES + 1)
        _identity(path, fd)
    finally:
        os.close(fd)
    if len(raw) > MAX_BYTES:
        raise ProgressError("startup_progress_too_large")
    return raw, (info.st_dev, info.st_ino)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProgressError("startup_progress_duplicate_field")
        result[key] = value
    return result


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", value):
        raise ProgressError("startup_progress_invalid_timestamp")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ProgressError("startup_progress_invalid_timestamp") from None


def read_progress(path, launch_id):
    launch_id = _identifier(launch_id)
    raw, identity = _read(path)
    lines = raw.split(b"\n")
    partial = bool(lines[-1])
    complete = lines[:-1]
    if not 1 <= len(complete) <= 5 or any(not line or len(line) > 1024 for line in complete):
        raise ProgressError("startup_progress_invalid_records")
    try:
        values = [json.loads(line.decode("ascii"), object_pairs_hook=_unique) for line in complete]
    except (ValueError, UnicodeError):
        raise ProgressError("startup_progress_invalid_json") from None
    header = values[0]
    if (not isinstance(header, dict) or set(header) != {"format", "purpose", "launch_id", "created_at_utc"}
            or type(header["format"]) is not int or header["format"] != 1
            or header["purpose"] != PURPOSE or header["launch_id"] != launch_id):
        raise ProgressError("startup_progress_header_differs")
    _timestamp(header["created_at_utc"])
    previous_ms, pid = -1, None
    records = values[1:]
    for index, record in enumerate(records):
        if (not isinstance(record, dict)
                or set(record) != {"phase", "launch_id", "pid", "elapsed_ms", "at_utc"}
                or record["phase"] != PHASES[index] or record["launch_id"] != launch_id
                or type(record["pid"]) is not int or not 0 < record["pid"] <= 2**32 - 1
                or type(record["elapsed_ms"]) is not int or not previous_ms <= record["elapsed_ms"] <= 86400000
                or record["elapsed_ms"] < 0 or (pid is not None and record["pid"] != pid)):
            raise ProgressError("startup_progress_phase_differs")
        _timestamp(record["at_utc"])
        previous_ms, pid = record["elapsed_ms"], record["pid"]
    if partial and (len(lines[-1]) > 1024 or len(records) == len(PHASES)):
        raise ProgressError("startup_progress_invalid_tail")
    return {"phase": records[-1]["phase"] if records else "preflight", "records": records,
            "partial": partial, "raw": raw, "identity": identity}


class StartupProgress:
    def __init__(self, path=None, launch_id=None):
        if (path is None) != (launch_id is None):
            raise ProgressError("startup_progress_pair_required")
        self.path, self.launch_id = path, launch_id
        self.started = time.monotonic()
        self.current_phase = "preflight"
        self.index = 0
        self.raw = None
        self.identity = None
        if path is not None:
            state = read_progress(path, launch_id)
            if state["records"] or state["partial"]:
                raise ProgressError("startup_progress_already_started")
            self.raw = state["raw"]
            self.identity = state["identity"]

    def phase(self, name):
        if self.index >= len(PHASES) or name != PHASES[self.index]:
            raise ProgressError("startup_progress_invalid_transition")
        elapsed_ms = max(0, round((time.monotonic() - self.started) * 1000))
        stamp = utc_now()
        record = {"phase": name, "launch_id": self.launch_id, "pid": os.getpid(),
                  "elapsed_ms": elapsed_ms, "at_utc": stamp}
        if self.path is not None:
            path = _path(self.path)
            if _read(path) != (self.raw, self.identity):
                raise ProgressError("startup_progress_changed_before_append")
            data = _json(record)
            if len(self.raw) + len(data) > MAX_BYTES:
                raise ProgressError("startup_progress_too_large")
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_BINARY", 0))
            try:
                opened = _identity(path, fd)
                if (opened.st_dev, opened.st_ino) != self.identity or opened.st_size != len(self.raw):
                    raise ProgressError("startup_progress_changed_before_append")
                if os.write(fd, data) != len(data):
                    raise ProgressError("startup_progress_write_incomplete")
                os.fsync(fd)
                _identity(path, fd)
            finally:
                os.close(fd)
            self.raw += data
        self.index += 1
        self.current_phase = name
        print(f"BATTLE STARTUP phase={name}; elapsed_ms={elapsed_ms}; utc={stamp}", flush=True)
