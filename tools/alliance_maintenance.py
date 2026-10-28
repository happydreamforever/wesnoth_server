"""Offline cold backup and verified restore into a new, private Alliance runtime.

Backups contain private database credentials and player records. They are local
recovery artifacts, never diagnostics to upload. No original runtime is replaced.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import secrets
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo.errors import PyMongoError
from alliance.config import ConfigurationError, Settings
from alliance.deployment import (MONGO_VERSION, _check_mongod, _client, _credentials,
    _protect_directory, _uri, _write_new, check_database, owned_runtime)
from alliance.runtime_lock import runtime_lock, _acquire, _file_identity, _release
from alliance.schema import SCHEMA_VERSION

PURPOSE = "wesnoth-alliance-cold-backup"
CONTROLS = ("owner.json", "root.json", "config.json", "keyfile", "mongo.json")
MAX_FILES, MAX_BYTES = 20000, 100 * 1024**3


class MaintenanceError(Exception):
    """Fixed public error codes only; private exception details never escape."""


def local_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path).startswith("\\\\"):
        raise MaintenanceError("invalid_local_path")
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400):
            raise MaintenanceError("redirected_path")
    return path


def regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise MaintenanceError("unsafe_file_type")
    return info


def read_small(path, limit=65536):
    before = regular(path)
    if before.st_size > limit:
        raise MaintenanceError("oversized_metadata")
    with path.open("rb") as stream:
        actual = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
            raise MaintenanceError("file_changed")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise MaintenanceError("oversized_metadata")
    return raw


def digest(path):
    before = regular(path)
    total = 0
    hashed = hashlib.sha256()
    with path.open("rb") as stream:
        actual = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
            raise MaintenanceError("file_changed")
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                raise MaintenanceError("backup_size_limit")
            hashed.update(chunk)
    after = regular(path)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or total != before.st_size:
        raise MaintenanceError("file_changed")
    return {"bytes": total, "sha256": hashed.hexdigest()}


def inventory(runtime, *, recovery_source=False):
    files = {name: digest(runtime / name) for name in CONTROLS
             if not recovery_source or (runtime / name).exists()}
    pending = [runtime / name for name in ("data", "battles") if (runtime / name).exists()]
    total = sum(item["bytes"] for item in files.values())
    while pending:
        directory = pending.pop()
        local_path(directory)
        for entry in directory.iterdir():
            if entry == runtime / "battles/daemon.lock":
                # Process-lifetime locks are not recovery data. Shared room,
                # event, replay and interrupted upload files are all included.
                regular(entry)
                continue
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400:
                pending.append(entry)
            else:
                record = digest(entry)
                files[entry.relative_to(runtime).as_posix()] = record
                total += record["bytes"]
            if len(files) > MAX_FILES or total > MAX_BYTES:
                raise MaintenanceError("backup_size_limit")
    if not recovery_source and ("data/WiredTiger" not in files or files.get("data/mongod.lock", {}).get("bytes") != 0):
        raise MaintenanceError("database_not_cleanly_stopped")
    return files


def validate_runtime(runtime):
    path = owned_runtime(local_path(runtime))
    for name in CONTROLS:
        read_small(path / name)
    settings = Settings.load(path)
    credentials = _credentials(path)  # root.json was already required; never creates it here.
    if (settings.mongo_uri != _uri("wesnoth_app", credentials["app_password"], "wesnoth_game") or
        settings.secret_key != credentials["secret_key"] or settings.bridge_secret != credentials["bridge_secret"] or
        read_small(path / "keyfile").decode().strip() != credentials["keyfile"]):
        raise MaintenanceError("runtime_credentials_disagree")
    mongo = json.loads(read_small(path / "mongo.json"))
    expected = {"storage": {"dbPath": str(path / "data")},
        "systemLog": {"destination": "file", "path": str(path / "logs/mongodb.log"), "logAppend": True},
        "net": {"bindIp": "127.0.0.1", "port": 27018},
        "security": {"keyFile": str(path / "keyfile"), "authorization": "enabled"},
        "replication": {"replSetName": "wesnoth-rs"}}
    if mongo != expected:
        raise MaintenanceError("managed_mongo_configuration_changed")
    return path


@contextmanager
def battle_storage_lock(runtime):
    path = local_path(runtime / "battles/daemon.lock")
    if not path.exists():
        # Before first daemon use no guard exists. Reserved database/listener
        # ports prevent that daemon from passing its required startup DB ping.
        yield
        return
    regular(path)
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    locked = False
    try:
        _file_identity(path, fd)
        try:
            _acquire(fd)
        except OSError:
            raise MaintenanceError("battle_service_must_be_stopped") from None
        locked = True
        info = _file_identity(path, fd)
        if info.st_size > 1 or os.read(fd, 2) not in (b"", b"0"):
            raise MaintenanceError("unexpected_battle_guard")
        yield
    finally:
        if locked:
            _release(fd)
        os.close(fd)


@contextmanager
def reserved_ports():
    """Block official service startup while the stopped runtime is copied."""
    sockets = {}
    try:
        for host, port in (("127.0.0.1", 27018), ("127.0.0.1", 18765), ("0.0.0.0", 15000), ("0.0.0.0", 15001), ("0.0.0.0", 15002)):
            peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets[port] = peer
            if os.name == "nt":
                peer.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                # A cleanly stopped Linux diagnostic may leave TIME_WAIT sockets.
                # Active listeners still prevent this exact-address bind.
                peer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                peer.bind((host, port))
            except OSError:
                raise MaintenanceError("services_must_be_stopped") from None
        yield sockets
    finally:
        for peer in sockets.values():
            peer.close()


def new_destination(destination, *excluded):
    path = local_path(destination)
    for original in excluded:
        original = local_path(original)
        if path == original or path in original.parents or original in path.parents:
            raise MaintenanceError("overlapping_destination")
    if path.exists():
        raise MaintenanceError("destination_already_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o700)
    _protect_directory(path)
    return path


def copy_manifest(source, destination, files):
    for name, expected in sorted(files.items()):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise MaintenanceError("invalid_manifest_path")
        origin, target = source / relative, destination / relative
        local_path(origin)
        before = regular(origin)
        target.parent.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            reader = stack.enter_context(origin.open("rb"))
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            writer = stack.enter_context(os.fdopen(fd, "wb"))
            actual = os.fstat(reader.fileno())
            if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
                raise MaintenanceError("file_changed")
            while chunk := reader.read(1024 * 1024):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if digest(target) != expected or digest(origin) != expected:
            raise MaintenanceError("copy_verification_failed")


def backup(runtime, destination):
    source = validate_runtime(runtime)
    with runtime_lock(source), reserved_ports(), battle_storage_lock(source):
        files = inventory(source)
        target = new_destination(destination, source)
        _write_new(target / "INCOMPLETE", "Private backup; completion has not been verified.\n")
        copy_manifest(source, target / "runtime", files)
        if inventory(source) != files:
            raise MaintenanceError("source_changed")
        manifest = {"purpose": PURPOSE, "format": 1, "mongodb_version": MONGO_VERSION,
            "producer_schema_version": SCHEMA_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
            "files": files}
        _write_new(target / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        (target / "INCOMPLETE").unlink()
    return {"files": len(files), "bytes": sum(row["bytes"] for row in files.values()),
            "schema_checked": False, "private_backup": True}


def verify_restore(runtime, mongod, ports):
    """Start only the new copy, and request a normal authenticated shutdown."""
    _check_mongod(mongod)
    credentials = _credentials(runtime)
    ports[27018].close()
    process = subprocess.Popen([str(mongod), "--config", str(runtime / "mongo.json")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 40
        with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise MaintenanceError("restored_database_exited")
                try:
                    opts = client.admin.command("getCmdLineOpts")["parsed"]
                    if Path(opts["storage"]["dbPath"]).resolve() != runtime / "data":
                        raise MaintenanceError("restored_database_identity_mismatch")
                    if client.admin.command("hello").get("isWritablePrimary"):
                        break
                except PyMongoError:
                    time.sleep(0.25)
            else:
                raise MaintenanceError("restored_database_start_timeout")
        # A cold backup's producer version does not prove its database schema.
        # Inspect the restored database itself. Legacy v1 remains recoverable
        # in an isolated copy, but is never upgraded or opened by the v2 app.
        with _client(Settings.load(runtime).mongo_uri) as client:
            db = client.wesnoth_game
            metadata = db.schema_metadata.find_one({"_id": "alliance"})
            schema = metadata.get("version") if metadata else None
            if type(schema) is not int or schema not in (1, 2, 3, SCHEMA_VERSION):
                raise MaintenanceError("unsupported_restored_database_schema")
            if schema != SCHEMA_VERSION:
                required = {"accounts", "teams", "areas", "game_runs", "settlements", "schema_metadata",
                            "admin_audit", "auth_sessions", "auth_attempts"}
                if (client.server_info()["version"] != MONGO_VERSION
                        or not required.issubset(db.list_collection_names())
                        or not db.accounts.find_one({"role": "admin", "status": "active"}, {"_id": 1})):
                    raise MaintenanceError("legacy_restore_incomplete")
                with client.start_session() as session:
                    session.start_transaction()
                    db.schema_metadata.insert_one({"_id": "restore-check-" + secrets.token_hex(16), "version": 1}, session=session)
                    session.abort_transaction()
                print("LEGACY DATABASE RECOVERY VERIFIED. Use the matching retained release to run this copy.")
            else:
                check_database(runtime)
    finally:
        if process.poll() is None:
            with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
                # Never send shutdown solely because a port answered. Bind it
                # again to this owned child's exact new dbPath first.
                if process.poll() is not None:
                    raise MaintenanceError("restored_database_exited")
                opts = client.admin.command("getCmdLineOpts")["parsed"]
                if Path(opts["storage"]["dbPath"]).resolve() != runtime / "data":
                    raise MaintenanceError("restored_database_identity_mismatch")
                try:
                    client.admin.command("shutdown", timeoutSecs=10)
                except PyMongoError:
                    pass
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                raise MaintenanceError("restored_database_shutdown_unconfirmed") from None
        if process.returncode != 0:
            raise MaintenanceError("restored_database_not_cleanly_stopped")
    return schema


def restore(runtime, backup_path, destination, mongod):
    # Recovery must also work when the original data/config is damaged or missing.
    # Its owned marker and path guards still protect any existing original.
    source = local_path(runtime)
    source_present = source.exists()
    if source_present:
        owned_runtime(source)
    archived = local_path(backup_path)
    if (archived / "INCOMPLETE").exists():
        raise MaintenanceError("backup_incomplete")
    manifest = json.loads(read_small(archived / "manifest.json", 8 * 1024**2))
    if (manifest.get("purpose") != PURPOSE or manifest.get("format") != 1 or
        manifest.get("mongodb_version") != MONGO_VERSION or
        manifest.get("producer_schema_version") not in (1, 2, 3, SCHEMA_VERSION)):
        raise MaintenanceError("unsupported_backup_version")
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) > MAX_FILES or set(CONTROLS) - files.keys():
        raise MaintenanceError("invalid_backup_manifest")
    # Recompute the entire bounded archive before reserving a destination.
    if inventory(archived / "runtime") != files:
        raise MaintenanceError("backup_integrity_failed")
    with ExitStack() as stack:
        if source_present:
            stack.enter_context(runtime_lock(source))
        ports = stack.enter_context(reserved_ports())
        if source_present:
            stack.enter_context(battle_storage_lock(source))
        before = inventory(source, recovery_source=True) if source_present else None
        target = new_destination(destination, source, archived)
        _write_new(target / "RESTORE_INCOMPLETE", "Restored copy has not passed verification. Do not run it.\n")
        copy_manifest(archived / "runtime", target, files)
        (target / "logs").mkdir()
        mongo = json.loads(read_small(target / "mongo.json"))
        mongo["storage"]["dbPath"] = str(target / "data")
        mongo["systemLog"]["path"] = str(target / "logs/mongodb.log")
        mongo["security"]["keyFile"] = str(target / "keyfile")
        # Only this newly created copy is rebased; original and archive stay exact.
        (target / "mongo.json").write_text(json.dumps(mongo, indent=2) + "\n", encoding="utf-8")
        validate_runtime(target)
        with runtime_lock(target):
            verified_schema = verify_restore(target, mongod, ports)
        after = inventory(source, recovery_source=True) if source_present else None
        if source.exists() != source_present or after != before or inventory(archived / "runtime") != files:
            raise MaintenanceError("protected_source_changed")
        (target / "RESTORE_INCOMPLETE").unlink()
        _write_new(target / "restore-verified.json", json.dumps({"format": 1,
            "schema_version": verified_schema, "mongodb_version": MONGO_VERSION,
            "verified_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    return {"files": len(files), "schema_checked": True, "database_stopped": True,
            "original_unchanged": True, "original_present": source_present, "activation_performed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backup", "restore"))
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--mongod", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "restore" and (args.backup is None or args.mongod is None):
            raise MaintenanceError("restore_arguments_required")
        result = backup(args.runtime, args.destination) if args.command == "backup" else restore(
            args.runtime, args.backup, args.destination, args.mongod)
    except MaintenanceError as error:
        print("ALLIANCE MAINTENANCE FAILED: " + str(error))
        print("Original files were not replaced. Retain any incomplete new destination for review.")
        return 1
    except (Exception, KeyboardInterrupt):
        print("ALLIANCE MAINTENANCE FAILED: operation_incomplete")
        print("Original files were not replaced. Retain the new destination and inspect its local logs; do not upload private backup/runtime files.")
        return 1
    print("ALLIANCE " + args.command.upper() + " VERIFIED")
    print(json.dumps(result, sort_keys=True))
    print("Private recovery artifact: keep it locally. No service was activated or existing runtime replaced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
