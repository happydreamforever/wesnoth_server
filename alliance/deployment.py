"""Owned local MongoDB lifecycle; no global installation or existing-DB migration."""
import getpass
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import warnings
from urllib.parse import quote

from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from .config import Settings, ConfigurationError
from .runtime_lock import runtime_lock

PURPOSE = "wesnoth-alliance-local"
MONGO_VERSION = "8.0.32"


def _write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def _protect_directory(path):
    if os.name == "nt":
        # Remove inheritance only on this newly owned directory, never on its parent.
        result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                                capture_output=True, text=True, check=True)
        import csv
        sid = next(csv.reader([result.stdout.strip()]))[1]
        if not sid.startswith("S-1-5-"):
            raise ConfigurationError("Could not determine the Windows account SID.")
        result = subprocess.run(["icacls.exe", str(path), "/inheritance:r", "/grant:r",
            f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True, text=True)
        if result.returncode:
            raise ConfigurationError("Could not restrict the new runtime directory to its owner and SYSTEM.")
    else:
        path.chmod(0o700)


def owned_runtime(runtime, create=False):
    path = Path(runtime).absolute()
    def redirected(item):
        return item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction())
    # Check the lexical path before resolve/mkdir can follow an existing parent.
    # Refuse traversal rather than normalizing away a possibly redirected segment.
    if ".." in path.parts:
        raise ConfigurationError("Runtime directory must not contain parent traversal.")
    if any(redirected(item) for item in (*reversed(path.parents), path)):
        raise ConfigurationError("Runtime directory and its parents must not be symbolic links or junctions.")
    marker = path / "owner.json"
    if not path.exists() and create:
        path.mkdir(parents=True, mode=0o700)
        _protect_directory(path)
        _write_new(marker, json.dumps({"purpose": PURPOSE, "format": 1}))
    try:
        valid = not redirected(marker) and json.loads(marker.read_text()) == {"purpose": PURPOSE, "format": 1}
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise ConfigurationError("Runtime is not an owned Alliance directory; existing files were preserved.")
    for name in ("config.json", "root.json", "keyfile", "mongo.json", "data", "logs",
                 "operation.lock", "operation.guard"):
        if redirected(path / name):
            raise ConfigurationError("A managed runtime path is a link or junction; refusing to follow it.")
    return path.resolve()


def _credentials(path):
    # Persist one complete credentials object before generating derivative files.
    # Interrupted initialization resumes with the same passwords and key.
    root_file = path / "root.json"
    if not root_file.exists():
        _write_new(root_file, json.dumps({"format": 1, "purpose": PURPOSE,
            "database_admin_password": secrets.token_urlsafe(48),
            "app_password": secrets.token_urlsafe(48),
            "keyfile": secrets.token_urlsafe(96).replace("-", "a").replace("_", "b"),
            "secret_key": secrets.token_urlsafe(48), "bridge_secret": secrets.token_urlsafe(48)}))
    try:
        credentials = json.loads(root_file.read_text())
        if credentials["format"] != 1 or credentials["purpose"] != PURPOSE:
            raise ValueError
        for key in ("database_admin_password", "app_password", "keyfile", "secret_key", "bridge_secret"):
            if not isinstance(credentials[key], str) or len(credentials[key]) < 43:
                raise ValueError
        return credentials
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigurationError("Private runtime credentials are invalid; preserve the runtime for recovery.") from None


def _uri(user, password, database):
    return (f"mongodb://{user}:{quote(password, safe='')}@127.0.0.1:27018/{database}"
            f"?authSource={database}&replicaSet=wesnoth-rs&directConnection=true")


def _client(uri):
    return MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=3000,
                       socketTimeoutMS=15000, tz_aware=True, appname="WesnothAlliance")


def _configure_runtime(path):
    credentials = _credentials(path)
    service = {"mongo_uri": _uri("wesnoth_app", credentials["app_password"], "wesnoth_game"),
        "secret_key": credentials["secret_key"], "bridge_secret": credentials["bridge_secret"],
        "host": "127.0.0.1", "port": 18765}
    config = {"purpose": PURPOSE, "format": 1, "service": service}
    for name in ("data", "logs"):
        (path / name).mkdir(exist_ok=True, mode=0o700)
    mongo = {"storage": {"dbPath": str(path / "data")},
        "systemLog": {"destination": "file", "path": str(path / "logs" / "mongodb.log"), "logAppend": True},
        "net": {"bindIp": "127.0.0.1", "port": 27018},
        "security": {"keyFile": str(path / "keyfile"), "authorization": "enabled"},
        "replication": {"replSetName": "wesnoth-rs"}}
    expected = {"config.json": json.dumps(config, indent=2) + "\n",
                "keyfile": credentials["keyfile"] + "\n", "mongo.json": json.dumps(mongo, indent=2) + "\n"}
    for name, value in expected.items():
        target = path / name
        if target.exists():
            if target.read_text() != value:
                raise ConfigurationError(f"Managed {name} differs from its owned configuration. Existing files preserved.")
        else:
            _write_new(target, value)
    return credentials


def _check_mongod(mongod):
    if not mongod or not Path(mongod).is_file():
        raise ConfigurationError("Provide the verified portable mongod executable.")
    result = subprocess.run([str(mongod), "--version"], capture_output=True, text=True, timeout=30)
    if result.returncode or f"db version v{MONGO_VERSION}\n" not in result.stdout.replace("\r\n", "\n"):
        raise ConfigurationError(f"The selected mongod must report version {MONGO_VERSION}; check its Windows runtime requirements.")


def _start_mongo(path, mongod):
    _check_mongod(mongod)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        if sock.connect_ex(("127.0.0.1", 27018)) == 0:
            raise ConfigurationError("TCP 27018 is already in use. No existing database was changed or stopped.")
    process = subprocess.Popen([str(mongod), "--config", str(path / "mongo.json")],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = _client("mongodb://127.0.0.1:27018/?directConnection=true")
    try:
        for _ in range(30):
            if process.poll() is not None:
                raise ConfigurationError(f"Owned MongoDB did not start; inspect {path / 'logs' / 'mongodb.log'} locally.")
            try:
                hello = client.admin.command("hello")
                if process.poll() is not None:
                    raise ConfigurationError("Owned MongoDB exited during startup; existing services were left unchanged.")
                if hello.get("setName") not in (None, "wesnoth-rs"):
                    raise ConfigurationError("Unexpected database identity on the local Alliance port.")
                return process
            except PyMongoError:
                time.sleep(0.5)
        raise ConfigurationError("Owned MongoDB startup timed out; keep the runtime log for diagnosis.")
    except BaseException:
        _stop_owned(process, path)
        raise
    finally:
        client.close()


def _stop_owned(process, path=None):
    # MongoDB's shutdown command flushes normally on Windows too. Popen.terminate
    # uses TerminateProcess there, so reserve it for an unresponsive owned child.
    if process.poll() is None and path is not None:
        try:
            credentials = _credentials(path)
            with _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin")) as client:
                try:
                    client.admin.command("shutdown", timeoutSecs=10)
                except PyMongoError:
                    pass  # A successful shutdown normally closes this connection.
            process.wait(timeout=15)
        except (PyMongoError, ConfigurationError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _admin_credentials(admin_username, admin_password):
    from .domain import DomainError, validate_username
    if admin_username is None:
        for _ in range(5):
            # A complete flushed line is visible even when a parent consumes
            # stdout line by line. Do not embed this prompt in input().
            print("New admin username (3-24 ASCII letters, digits or underscores):",
                  flush=True)
            try:
                username, _ = validate_username(input())
                break
            except EOFError:
                raise ConfigurationError(
                    "Administrator input ended. Rerun initialization in an interactive PowerShell "
                    "console using the same runtime; existing data was preserved.") from None
            except DomainError:
                print("Use 3-24 ASCII letters, digits or underscores for the username.",
                      flush=True)
        else:
            raise ConfigurationError(
                "Administrator username was invalid five times. Rerun initialization using the "
                "same runtime; existing data was preserved.")
    else:
        # Explicit callers get the same rule and fail before password collection.
        username, _ = validate_username(admin_username)

    password = admin_password
    if password is None:
        try:
            with warnings.catch_warnings():
                # getpass normally falls back to visible input when no terminal
                # is available. Stop before it reads any unmasked password.
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("New admin password (12-128 characters): ")
                confirmation = getpass.getpass("Repeat admin password: ")
        except (EOFError, getpass.GetPassWarning):
            raise ConfigurationError(
                "Hidden password input is unavailable or ended. Rerun initialization in an "
                "interactive PowerShell console without input redirection using the same runtime; "
                "existing data was preserved.") from None
        if confirmation != password:
            raise ConfigurationError("Passwords did not match. Rerun initialization to complete the admin step.")
    return username, password


def initialize(runtime, mongod, *, admin_username=None, admin_password=None):
    """Create only the explicit owned runtime; safe to resume with unchanged files."""
    from .auth import bootstrap_auth_schema, hash_password
    from .domain import AllianceService
    from .schema import bootstrap_schema
    path = owned_runtime(runtime, create=True)
    with runtime_lock(path):
        credentials = _configure_runtime(path)
        process = _start_mongo(path, mongod)
        anonymous = _client("mongodb://127.0.0.1:27018/?directConnection=true")
        privileged = _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin"))
        try:
            hello = anonymous.admin.command("hello")
            if not hello.get("setName"):
                anonymous.admin.command("replSetInitiate", {"_id": "wesnoth-rs", "members": [
                    {"_id": 0, "host": "localhost:27018"}]})
            elif hello["setName"] != "wesnoth-rs":
                raise ConfigurationError("Unexpected replica set. No initialization will be attempted.")
            for _ in range(60):
                if anonymous.admin.command("hello").get("isWritablePrimary"):
                    break
                time.sleep(0.5)
            else:
                raise ConfigurationError("The owned single-node replica set did not become primary.")
            try:
                privileged.admin.command("ping")
            except OperationFailure as exc:
                if exc.code != 18:
                    raise
                # Only a brand new database permits this localhost-exception operation.
                anonymous.admin.command("createUser", "wesnoth_operator",
                    pwd=credentials["database_admin_password"], roles=[{"role": "root", "db": "admin"}])
                privileged.close()
                privileged = _client(_uri("wesnoth_operator", credentials["database_admin_password"], "admin"))
                privileged.admin.command("ping")
            db = privileged.wesnoth_game
            bootstrap_schema(db)
            bootstrap_auth_schema(db)
            users = db.command("usersInfo", "wesnoth_app")["users"]
            expected_roles = [{"role": "readWrite", "db": "wesnoth_game"}]
            if not users:
                db.command("createUser", "wesnoth_app", pwd=credentials["app_password"], roles=expected_roles)
            elif users[0].get("roles") != expected_roles:
                raise ConfigurationError("Existing application database user has unexpected roles; no permissions changed.")
            if not db.accounts.find_one({"role": "admin"}):
                username, password = _admin_credentials(admin_username, admin_password)
                AllianceService(db).bootstrap_admin(username, hash_password(password))
            settings = Settings.load(path)
            with _client(settings.mongo_uri) as app_client:
                app_client.wesnoth_game.accounts.find_one({}, {"_id": 1})
                status = app_client.admin.command("connectionStatus")
                if status["authInfo"]["authenticatedUserRoles"] != expected_roles:
                    raise ConfigurationError("Runtime database scope verification failed.")
        finally:
            anonymous.close()
            privileged.close()
            _stop_owned(process, path)
        if process.poll() != 0:
            raise ConfigurationError(
                f"Owned MongoDB did not exit cleanly after initialization; inspect {path / 'logs' / 'mongodb.log'} locally.")
        print("ALLIANCE INITIALIZATION PASSED")
        print("MongoDB 8.0.32; authenticated single-node replica set; scoped application user; admin account ready.")
        print("Owned database stopped. Start the database window, then the service window.")


def run_database(runtime, mongod):
    path = owned_runtime(runtime)
    Settings.load(path)
    with runtime_lock(path):
        # Comparing managed settings prevents accidentally broadening the binding.
        _configure_runtime(path)
        process = _start_mongo(path, mongod)
        print("Alliance MongoDB running on 127.0.0.1:27018. Keep this window open. Ctrl+C stops this process.", flush=True)
        try:
            code = process.wait()
            if code:
                raise ConfigurationError("Owned MongoDB exited unexpectedly. Preserve its local log.")
        except KeyboardInterrupt:
            pass
        finally:
            _stop_owned(process, path)


def check_database(runtime):
    path = owned_runtime(runtime)
    settings = Settings.load(path)
    with _client(settings.mongo_uri) as client:
        if client.server_info()["version"] != MONGO_VERSION:
            raise ConfigurationError("Unexpected database version.")
        hello = client.admin.command("hello")
        if hello.get("setName") != "wesnoth-rs" or not hello.get("isWritablePrimary"):
            raise ConfigurationError("The local replica set is not writable and ready.")
        db = client.wesnoth_game
        from .schema import SCHEMA_VERSION
        if db.schema_metadata.find_one({"_id": "alliance", "version": SCHEMA_VERSION}) is None:
            raise ConfigurationError("Unsupported or incomplete Alliance schema; explicit initialization/migration required.")
        required = {"accounts", "teams", "areas", "game_runs", "settlements", "schema_metadata",
                    "admin_audit", "auth_sessions", "auth_attempts"}
        if not required.issubset(db.list_collection_names()):
            raise ConfigurationError("Alliance schema is incomplete; resume initialization.")
        if not db.accounts.find_one({"role": "admin", "status": "active"}, {"_id": 1}):
            raise ConfigurationError("No active administrator. Resume initialization.")
        # An aborted transaction verifies transaction support without a persistent record.
        with client.start_session() as session:
            session.start_transaction()
            db.schema_metadata.insert_one({"_id": "check-" + secrets.token_hex(16), "version": 1, "check": True}, session=session)
            session.abort_transaction()
        print("PASS MongoDB 8.0.32 / authenticated replica set / schema / administrator / transaction rollback")
        print("ALLIANCE DATABASE CHECK PASSED")
        print("This checks the new backend only; the installed Android game is not yet integrated.")


def serve(runtime):
    from waitress import serve as waitress_serve
    from .web import create_app
    path = owned_runtime(runtime)
    settings = Settings.load(path)
    check_database(runtime)
    with _client(settings.mongo_uri) as client:
        app = create_app(settings, client.wesnoth_game)
        print("Alliance admin: http://127.0.0.1:18765/", flush=True)
        print("Keep this window open. The native game account bridge is a later milestone.", flush=True)
        waitress_serve(app, host=settings.host, port=settings.port, threads=4,
                       max_request_body_size=65536, channel_timeout=30, clear_untrusted_proxy_headers=True)
