#!/usr/bin/env python3
"""Pinned, opt-in downloads and an offline Windows Alliance environment.

This tool never reads .env or initializes a database. Existing mismatched files
are preserved and rejected instead of being replaced.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import http.client
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "tools" / "alliance-dependencies"
CACHE = ROOT / "build" / "alliance-dependencies"
VENV = ROOT / "build" / "alliance-venv-py312"
LEGACY_VENV = ROOT / "build" / "alliance-venv"
PYTHON_VERSION = (3, 12, 10)
MONGO = ROOT / "build" / "alliance-mongodb"
OWNER = "wesnoth-alliance-dependencies-v1"
DOWNLOAD_ATTEMPTS = 3
ARTIFACT_RENAME_DELAYS = (0.5, 1, 2)
MONGO_RENAME_DELAYS = (0.5, 1, 2, 4, 8)
MONGO_FILES = (
    "LICENSE-Community.txt", "MPL-2", "README", "THIRD-PARTY-NOTICES",
    "bin/mongod.exe", "bin/vc_redist.x64.exe",
)


class PreparationError(RuntimeError):
    pass


class _TransientDownloadError(Exception):
    """Only errors from network operations may enter the retry loop."""


def _network_operation(operation):
    try:
        return operation()
    except urllib.error.HTTPError as error:
        error.close()
        if error.code in (408, 429, 500, 502, 503, 504):
            raise _TransientDownloadError(f"HTTP {error.code}") from error
        raise PreparationError(f"Download server returned HTTP {error.code}; no automatic retry.") from None
    except (OSError, http.client.IncompleteRead) as error:
        reason = error.reason if isinstance(error, urllib.error.URLError) else error
        # Certificate/protocol problems, permanent DNS failures, and generic
        # text-only URL errors must not be disguised as a temporary timeout.
        if isinstance(reason, ssl.SSLError):
            raise
        codes = {errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED,
                 errno.ECONNREFUSED, errno.ENETUNREACH, errno.EHOSTUNREACH,
                 10053, 10054, 10060, 10061, 10065, 11002}
        transient = (isinstance(reason, (TimeoutError, ConnectionError, http.client.IncompleteRead))
                     or (isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN)
                     or (isinstance(reason, OSError) and
                         (reason.errno in codes or getattr(reason, "winerror", None) in codes)))
        if not transient:
            raise
        raise _TransientDownloadError(type(reason).__name__) from error


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_manifest(path: Path = PINS / "windows.json") -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != 1 or result.get("platform") != "win_amd64":
        raise PreparationError("Unsupported Alliance dependency manifest.")
    names = set()
    for item in [*result["wheels"], result["mongodb"]]:
        filename = item["filename"]
        if filename in names or Path(filename).name != filename or any(c in filename for c in "\\/:"):
            raise PreparationError("Unsafe or repeated dependency filename.")
        names.add(filename)
        if not isinstance(item["size"], int) or item["size"] < 1:
            raise PreparationError("Invalid dependency size.")
        if len(item["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["sha256"]):
            raise PreparationError("Invalid dependency SHA256.")
        if not item["url"].startswith(("https://files.pythonhosted.org/", "https://fastdl.mongodb.org/windows/")):
            raise PreparationError("Unapproved dependency URL.")
    return result


def verify(path: Path, item: dict) -> None:
    if path.is_symlink() or not path.is_file():
        raise PreparationError(f"Required dependency is missing: {path.name}. Run preparation with -Download while connected.")
    if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
        raise PreparationError(f"Dependency differs from its pin; preserved for inspection: {path.name}")


def _publish_artifact(partial: Path, path: Path, item: dict) -> None:
    """Publish complete bytes exclusively; never expose a partially copied wheel."""
    for attempt in range(len(ARTIFACT_RENAME_DELAYS) + 1):
        _safe_local_path(partial)
        _safe_local_path(path)
        verify(partial, item)
        if partial.stat().st_nlink != 1:
            raise PreparationError('Verified download has unexpected hard links; preserved.')
        if path.exists() or path.is_symlink():
            raise PreparationError(f'Dependency destination appeared during publication; preserved: {path.name}')
        try:
            if sys.platform == 'win32':
                # Windows rename fails if the destination exists. Both paths
                # are in one directory, so no partial copy becomes visible.
                os.rename(partial, path)
            else:
                # POSIX rename replaces existing files. Link exclusively, then
                # remove our temporary name; the resulting artifact is ordinary.
                os.link(partial, path)
                partial.unlink()
        except OSError as error:
            code = getattr(error, 'winerror', None)
            if sys.platform != 'win32' or code not in (5, 32, 33):
                raise
            if attempt == len(ARTIFACT_RENAME_DELAYS):
                raise PreparationError(
                    f'Windows denied dependency publication (WinError {code}). '
                    'Verified download retained; rerun preparation to resume without downloading it again.') from None
            time.sleep(ARTIFACT_RENAME_DELAYS[attempt])
        else:
            verify(path, item)
            return


def _resume_verified_download(path: Path, item: dict) -> bool:
    """Retain incomplete attempts, but reuse exact verified bytes after a local failure."""
    attempts = []
    for candidate in path.parent.glob(path.name + '.download-*'):
        suffix = candidate.name[len(path.name + '.download-'):]
        if len(suffix) != 32 or any(c not in '0123456789abcdef' for c in suffix):
            continue
        attempts.append(candidate)
        if len(attempts) > 64:
            raise PreparationError('Too many retained dependency downloads; preserve the cache for review.')
    for candidate in sorted(attempts):
        _safe_local_path(candidate)
        if candidate.stat().st_nlink != 1:
            raise PreparationError('Retained download has unexpected hard links; preserved.')
        try:
            verify(candidate, item)
        except PreparationError:
            continue
        print(f'Resuming verified download for {path.name}.', flush=True)
        _publish_artifact(candidate, path, item)
        return True
    return False


def ensure_artifact(path: Path, item: dict, download: bool) -> None:
    if path.exists() or path.is_symlink():
        verify(path, item)
        print(f"Using verified cached {path.name}.", flush=True)
        return
    if _resume_verified_download(path, item):
        return
    if not download:
        verify(path, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        partial = path.with_name(path.name + ".download-" + uuid.uuid4().hex)
        verified_download = False
        print(f"Downloading pinned {path.name} ({item['size']} bytes; attempt {attempt}/{DOWNLOAD_ATTEMPTS}).", flush=True)
        try:
            response = _network_operation(lambda: urllib.request.urlopen(item["url"], timeout=90))
            with response, partial.open("xb") as output:
                count = 0
                while chunk := _network_operation(lambda: response.read(1024 * 1024)):
                    count += len(chunk)
                    if count > item["size"]:
                        raise PreparationError(f"Download exceeds its pinned size: {path.name}")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            verify(partial, item)
            verified_download = True
            # Publication and local I/O errors are deliberately outside the
            # network retry classification. Never replace an existing file.
            _publish_artifact(partial, path, item)
            return
        except _TransientDownloadError as error:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise PreparationError(
                    f"Download failed after {DOWNLOAD_ATTEMPTS} attempts: {path.name} ({error}). "
                    "Completed cache files are preserved. Keep internet connected and rerun preparation.") from None
            delay = 2 ** attempt
            print(f"Temporary download failure for {path.name} ({error}); retrying in {delay}s.", flush=True)
        finally:
            # A local publication error must leave complete verified bytes
            # available to an offline retry. Unverified attempts are disposable.
            if not verified_download:
                partial.unlink(missing_ok=True)
        time.sleep(delay)


def prepare(manifest: dict, cache: Path, download: bool = False) -> None:
    for item in manifest["wheels"]:
        ensure_artifact(cache / "wheels" / item["filename"], item, download)
    ensure_artifact(cache / manifest["mongodb"]["filename"], manifest["mongodb"], download)
    print(f"ALLIANCE DEPENDENCIES VERIFIED: {len(manifest['wheels'])} wheels; MongoDB {manifest['mongodb']['version']}.", flush=True)


def write_json_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write("\n")


def _mongodb_tree_snapshot(directory: Path, item: dict) -> dict:
    """Verify the exact owned tree and capture its identity before publication."""
    if directory.is_symlink() or directory.is_junction() or not directory.is_dir():
        raise PreparationError(f"MongoDB directory is missing or redirected; preserved: {directory}")
    marker = directory / "alliance-owned.json"
    if marker.is_symlink() or not marker.is_file():
        raise PreparationError("Existing MongoDB directory has no ownership receipt; preserved.")
    folder = directory / "bin"
    if folder.is_symlink() or folder.is_junction() or not folder.is_dir():
        raise PreparationError(f"MongoDB directory is missing or redirected; preserved: {folder}")
    names = (".", "bin", "alliance-owned.json", *MONGO_FILES)

    def identities():
        result = {}
        for name in names:
            value = (directory / name).lstat()
            result[name] = (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns)
        return result

    before = identities()
    receipt = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("owner") != OWNER or receipt.get("archive_sha256") != item["sha256"]:
        raise PreparationError("Existing MongoDB directory belongs to another recipe; preserved.")
    if receipt.get("files") != item["files"] or set(item["files"]) != set(MONGO_FILES):
        raise PreparationError("MongoDB receipt file selection differs from the recipe.")
    if set(receipt) != {"owner", "archive_sha256", "files"}:
        raise PreparationError("MongoDB ownership receipt changed; preserved.")
    expected_top = {Path(name).parts[0] for name in MONGO_FILES} | {marker.name}
    if ({p.name for p in directory.iterdir()} != expected_top or
            {p.name for p in (directory / "bin").iterdir()} != {"mongod.exe", "vc_redist.x64.exe"}):
        raise PreparationError("MongoDB directory contains unexpected files; preserved.")
    for name, expected in item["files"].items():
        verify(directory / name, {**expected, "filename": name})
    after = identities()
    if after != before:
        raise PreparationError("MongoDB directory changed during verification; preserved.")
    return after


def _publish_mongodb(work: Path, destination: Path, item: dict) -> None:
    original = _mongodb_tree_snapshot(work, item)
    attempts = len(MONGO_RENAME_DELAYS) + 1
    for attempt in range(attempts):
        if destination.exists() or destination.is_symlink() or destination.is_junction():
            raise PreparationError(f"MongoDB destination appeared during installation; preserved: {destination}")
        if _mongodb_tree_snapshot(work, item) != original:
            raise PreparationError(f"Extracted MongoDB directory changed; preserved: {work}")
        try:
            # Windows rename refuses an existing destination. Never use replace
            # or delete a competing destination to make this operation succeed.
            work.rename(destination)
        except OSError as error:
            code = getattr(error, "winerror", None)
            if code not in (5, 32, 33):
                raise
            if attempt == attempts - 1:
                raise PreparationError(
                    f"Windows denied MongoDB directory publication after {attempts} attempts (WinError {code}). "
                    f"Verified extraction preserved: {work}. Send the install log; do not delete these files.") from None
            delay = MONGO_RENAME_DELAYS[attempt]
            print(f"Windows denied MongoDB directory rename (WinError {code}); "
                  f"retry {attempt + 2}/{attempts} in {delay}s. Keeping the extracted files.", flush=True)
            time.sleep(delay)
        else:
            _mongodb_tree_snapshot(destination, item)
            return


def extract_mongodb(manifest: dict, cache: Path, destination: Path) -> Path:
    item = manifest["mongodb"]
    archive = cache / item["filename"]
    verify(archive, item)
    marker = destination / "alliance-owned.json"
    if destination.exists() or destination.is_symlink() or destination.is_junction():
        _mongodb_tree_snapshot(destination, item)
        return destination / "bin" / "mongod.exe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=destination.name + ".extract-", dir=destination.parent))
    try:
        files = {}
        prefix = f"mongodb-win32-x86_64-windows-{item['version']}/"
        with zipfile.ZipFile(archive) as source:
            for name in MONGO_FILES:
                entry = source.getinfo(prefix + name)
                if entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise PreparationError("Unexpected directory or symlink in MongoDB archive.")
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as incoming, target.open("xb") as output:
                    shutil.copyfileobj(incoming, output, 1024 * 1024)
                verify(target, item["files"][name])
                files[name] = item["files"][name]
        write_json_new(work / marker.name, {"owner": OWNER, "archive_sha256": item["sha256"], "files": files})
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    # A completed extraction is useful evidence if publication is blocked.
    # Cleanup above applies only before the complete ownership receipt exists.
    try:
        _publish_mongodb(work, destination, item)
    except BaseException:
        print(f"MongoDB publication stopped; no cleanup performed. "
              f"Keep any files at {work} and {destination}.", flush=True)
        raise
    return destination / "bin" / "mongod.exe"


def assert_windows_python() -> None:
    if (sys.platform != "win32" or sys.version_info[:3] != PYTHON_VERSION or sys.maxsize <= 2**32
            or sys.implementation.name != "cpython" or platform.machine().lower() not in ("amd64", "x86_64")):
        raise PreparationError("Use the verified Windows x86_64 CPython 3.12.10 interpreter.")


def clean_environment() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
    env.update({"PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INDEX": "1"})
    return env


def verify_installed(manifest: dict, venv: Path, mongodb: Path) -> None:
    assert_windows_python()
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    receipt = json.loads((venv / "alliance-owned.json").read_text(encoding="utf-8"))
    if receipt != {"owner": OWNER, "manifest_sha256": fingerprint}:
        raise PreparationError("Alliance virtual environment receipt differs from the pinned dependencies.")
    if Path(sys.executable).resolve() != (venv / "Scripts" / "python.exe").resolve():
        raise PreparationError("Run this check with the Alliance virtual environment interpreter.")
    for item in manifest["wheels"]:
        if importlib.metadata.version(item["name"]) != item["version"]:
            raise PreparationError(f"Installed dependency version differs: {item['name']}")
    for name, item in manifest["mongodb"]["files"].items():
        verify(mongodb / name, item)
    print("Pinned Alliance environment and MongoDB files verified.")


def native_smoke() -> None:
    """Exercise runtime ABIs locally without sockets, accounts or databases."""
    import _cffi_backend
    from argon2 import PasswordHasher
    from cffi import FFI
    import bson
    from bson import BSON
    from markupsafe import _speedups, escape
    from flask import Flask
    from flask_wtf import FlaskForm
    from waitress import create_server

    hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    fixture = 'local dependency ABI check; never an account password'
    encoded = hasher.hash(fixture)
    if not hasher.verify(encoded, fixture):
        raise PreparationError('Argon2 native verification failed.')
    ffi = FFI()
    memory = ffi.new('unsigned char[]', b'ABI')
    if bytes(ffi.buffer(memory, 3)) != b'ABI' or not _cffi_backend:
        raise PreparationError('CFFI native allocation failed.')
    document = {'runtime': 'python312', 'value': 12, 'valid': True}
    if not bson.has_c() or BSON(BSON.encode(document)).decode() != document:
        raise PreparationError('BSON native round-trip failed.')
    if not callable(_speedups._escape_inner) or str(escape('<runtime>')) != '&lt;runtime&gt;':
        raise PreparationError('MarkupSafe native escaping failed.')
    application = Flask('alliance-python312-smoke')
    application.add_url_rule('/runtime-check', 'runtime_check', lambda: {'status': 'ok'})
    with application.test_client() as client:
        response = client.get('/runtime-check')
        if response.status_code != 200 or response.get_json() != {'status': 'ok'}:
            raise PreparationError('Flask local request failed.')
    if not FlaskForm or not callable(create_server):
        raise PreparationError('Backend service imports failed.')
    for available, version in ((ssl.HAS_TLSv1_2, ssl.TLSVersion.TLSv1_2),
                               (ssl.HAS_TLSv1_3, ssl.TLSVersion.TLSv1_3)):
        if not available:
            raise PreparationError('The new interpreter lacks a required TLS version.')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = version
        context.maximum_version = version
        if not context.get_ciphers():
            raise PreparationError('The new interpreter has no usable TLS ciphers.')
    print('ALLIANCE PYTHON NATIVE MODULE CHECK PASSED', flush=True)


def validate_existing_venv(venv: Path, manifest: dict) -> None:
    if not venv.exists():
        return
    preservation_inventory(venv)
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    owner = _safe_local_path(venv / 'alliance-owned.json')
    if not owner.is_file() or json.loads(owner.read_text(encoding='utf-8')) != {'owner': OWNER, 'manifest_sha256': fingerprint}:
        raise PreparationError('Existing Python 3.12 environment has another owner or dependency pin; preserved.')
    config = _safe_local_path(venv / 'pyvenv.cfg')
    executable = _safe_local_path(venv / 'Scripts/python.exe')
    if config.exists():
        fields = {}
        for line in config.read_text(encoding='utf-8').splitlines():
            if '=' not in line:
                continue
            key, value = (part.strip() for part in line.split('=', 1))
            if key in fields:
                raise PreparationError('Existing Python environment configuration has duplicate fields.')
            fields[key] = value
        if fields.get('version') != '3.12.10':
            raise PreparationError('Existing Python environment uses another interpreter version; preserved.')
    elif executable.exists():
        raise PreparationError('Existing Python environment executable has no verified configuration; preserved.')


def install(manifest: dict, cache: Path, venv: Path, mongodb: Path, *, existing_mongodb: bool = False) -> None:
    assert_windows_python()
    if existing_mongodb:
        _mongodb_tree_snapshot(mongodb, manifest["mongodb"])
        prepare_wheels(manifest, cache)
        mongod = mongodb / "bin/mongod.exe"
    else:
        prepare(manifest, cache)
        mongod = extract_mongodb(manifest, cache, mongodb)
    check = subprocess.run([str(mongod), "--version"], capture_output=True, text=True, check=False)
    if check.returncode or f"v{manifest['mongodb']['version']}" not in check.stdout:
        raise PreparationError(f"Pinned mongod.exe could not report its version (exit {check.returncode}). The bundled VC++ runtime installer is in build/alliance-mongodb/bin. No installer was run.")
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    owner = venv / "alliance-owned.json"
    if venv.exists():
        if not owner.is_file() or json.loads(owner.read_text(encoding="utf-8")) != {"owner": OWNER, "manifest_sha256": fingerprint}:
            raise PreparationError("Existing Alliance virtual environment has another owner or dependency pin; preserved.")
    else:
        venv.mkdir(parents=True)
        write_json_new(owner, {"owner": OWNER, "manifest_sha256": fingerprint})
    env = clean_environment()
    subprocess.run([sys.executable, "-I", "-m", "venv", str(venv)], check=True, env=env)
    python = venv / "Scripts" / "python.exe"
    subprocess.run([
        str(python), "-I", "-m", "pip", "install", "--no-index", "--disable-pip-version-check",
        "--only-binary=:all:", "--no-deps", "--require-hashes", "--find-links", str(cache / "wheels"),
        "-r", str(PINS / "requirements-windows.txt"),
    ], check=True, env=env)
    subprocess.run([str(python), "-I", "-m", "pip", "check"], check=True, env=env)
    expected = {item["name"]: item["version"] for item in manifest["wheels"]}
    program = "import importlib.metadata as m,json,sys; expected=json.loads(sys.argv[1]); bad=[n for n,v in expected.items() if m.version(n)!=v]; print('Installed dependency versions verified.' if not bad else 'Version verification failed.'); sys.exit(bool(bad))"
    subprocess.run([str(python), "-I", "-c", program, json.dumps(expected)], check=True, env=env)
    print("ALLIANCE OFFLINE ENVIRONMENT INSTALLED")
    print("Database and administrator accounts have not been initialized.")


def _safe_local_path(path: Path, *, directory=False) -> Path:
    path = Path(path).absolute()
    for entry in (*reversed(path.parents), path):
        try:
            metadata = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise PreparationError('Python transition paths cannot traverse links or junctions.')
    if path.exists() and (not path.is_dir() if directory else not path.is_file()):
        raise PreparationError('Python transition path has an unexpected type.')
    return path


def prepare_wheels(manifest: dict, cache: Path, download=False) -> None:
    cache = _safe_local_path(cache, directory=True)
    for item in manifest['wheels']:
        path = _safe_local_path(cache / 'wheels' / item['filename'])
        if path.exists() and path.stat().st_nlink != 1:
            raise PreparationError('Python wheel cache cannot use hard links.')
        ensure_artifact(path, item, download)
    print('ALLIANCE PYTHON 3.12 WHEELS VERIFIED: ' + str(len(manifest['wheels'])) + ' pinned wheels.', flush=True)


def prepare_python312(manifest: dict, cache: Path, mongodb: Path, download=False) -> None:
    assert_windows_python()
    if manifest['python'] != '3.12.10':
        raise PreparationError('Python 3.12 preparation requires its pinned dependency manifest.')
    _safe_local_path(mongodb, directory=True)
    _mongodb_tree_snapshot(mongodb, manifest['mongodb'])
    prepare_wheels(manifest, cache, download)
    print('ALLIANCE PYTHON 3.12 CACHE READY', flush=True)
    print('Existing MongoDB files are verified and unchanged; its archive was not downloaded or extracted.', flush=True)


def preservation_inventory(path: Path) -> dict:
    path = _safe_local_path(path, directory=True)
    if not path.exists():
        return {'exists': False, 'files': {}}
    result = {}
    for directory, subdirs, files in os.walk(path, followlinks=False):
        for name in subdirs:
            _safe_local_path(Path(directory) / name, directory=True)
        for name in files:
            entry = _safe_local_path(Path(directory) / name)
            if entry.stat().st_nlink != 1:
                raise PreparationError('A preserved Python environment file is hard-linked; stop for review.')
            relative = entry.relative_to(path).as_posix()
            result[relative] = {'size': entry.stat().st_size, 'sha256': digest(entry)}
            if len(result) > 100000:
                raise PreparationError('Preserved Python environment exceeds its inventory bound.')
    return {'exists': True, 'files': result}


@contextmanager
def stopped_services():
    sockets = []
    try:
        for port in (27018, 18765, 15000, 15001, 15002):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(listener)
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(('0.0.0.0', port))
            except OSError:
                raise PreparationError('Stop all five game services before the Python environment transition.') from None
        yield
    finally:
        for listener in sockets:
            listener.close()


def install_python312(manifest: dict, cache: Path, venv: Path, mongodb: Path,
                      legacy_venv: Path = LEGACY_VENV, journal_root: Path | None = None) -> None:
    assert_windows_python()
    if manifest['python'] != '3.12.10':
        raise PreparationError('Python 3.12 installation requires its pinned dependency manifest.')
    venv = _safe_local_path(venv, directory=True)
    legacy_venv = _safe_local_path(legacy_venv, directory=True)
    mongodb = _safe_local_path(mongodb, directory=True)
    for protected in (legacy_venv, mongodb):
        if venv == protected or venv in protected.parents or protected in venv.parents:
            raise PreparationError('The new Python environment must be separate from preserved environments and MongoDB.')
    validate_existing_venv(venv, manifest)
    if journal_root is None:
        journal_root = venv.parent / 'alliance-python312-transition'
    journal_root = _safe_local_path(journal_root, directory=True)
    for protected in (legacy_venv, mongodb, venv):
        if journal_root == protected or journal_root in protected.parents or protected in journal_root.parents:
            raise PreparationError('The Python transition journal must be separate from preserved and installed files.')
    journal_root.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    marker = {'owner': 'wesnoth-alliance-python312-transition-v1', 'manifest_sha256': fingerprint,
              'new_venv': str(venv), 'preserved_venv': str(legacy_venv), 'mongodb': str(mongodb)}
    owner = journal_root / 'owner.json'
    if owner.exists():
        if json.loads(_safe_local_path(owner).read_text(encoding='utf-8')) != marker:
            raise PreparationError('The existing Python transition journal belongs to another configuration.')
    else:
        write_json_new(owner, marker)
    lock = journal_root / 'operation.lock'
    record = {'pid': os.getpid(), 'nonce': uuid.uuid4().hex}
    try:
        write_json_new(lock, record)
    except FileExistsError:
        raise PreparationError('Another Python transition holds its operation lock. Preserve it and stop for review.') from None
    attempt = journal_root / ('attempt-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + record['nonce'])
    attempt.mkdir()
    try:
        with stopped_services():
            before = {'legacy_venv': preservation_inventory(legacy_venv), 'mongodb': preservation_inventory(mongodb)}
            snapshot = journal_root / 'preserved-before.json'
            if snapshot.exists():
                if json.loads(_safe_local_path(snapshot).read_text(encoding='utf-8')) != before:
                    raise PreparationError('Preserved Python or MongoDB files changed since this transition began.')
            else:
                write_json_new(snapshot, before)
            prepare_python312(manifest, cache, mongodb)
            write_json_new(attempt / 'started.json', {'manifest_sha256': fingerprint, 'existing_database_untouched': True})
            completed = any(journal_root.glob('attempt-*/complete.json'))
            if not completed:
                install(manifest, cache, venv, mongodb, existing_mongodb=True)
            else:
                print('Checking the completed Python 3.12 environment without reinstalling it.', flush=True)
            # The new interpreter performs the complete installed-version and
            # MongoDB check. No runtime/database schema is opened or changed.
            subprocess.run([str(venv / 'Scripts/python.exe'), '-I', '-B', str(ROOT / 'tools/alliance_dependencies.py'),
                            'check-installed'], check=True, env=clean_environment())
            subprocess.run([str(venv / 'Scripts/python.exe'), '-I', '-B', str(ROOT / 'tools/alliance_dependencies.py'),
                            'check-native'], check=True, env=clean_environment())
            after = {'legacy_venv': preservation_inventory(legacy_venv), 'mongodb': preservation_inventory(mongodb)}
            if after != before:
                raise PreparationError('Preservation verification failed; keep both environments and this journal.')
            write_json_new(attempt / 'complete.json', {'python': '3.12.10', 'legacy_venv_preserved': True,
                           'mongodb_preserved': True, 'runtime_accessed': False, 'database_initialized': False,
                           'new_venv': str(venv)})
            print('ALLIANCE PYTHON 3.12 TRANSITION VERIFIED', flush=True)
            print('Old Python environment, MongoDB, accounts and runtime-v2 remain untouched.', flush=True)
    finally:
        if lock.is_file() and json.loads(_safe_local_path(lock).read_text(encoding='utf-8')) == record:
            lock.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "install", "prepare-python312", "install-python312", "check-python", "check-installed", "check-native"))
    parser.add_argument("--download", action="store_true", help="Permit pinned downloads during prepare only.")
    args = parser.parse_args(argv)
    try:
        if args.download and args.command not in ("prepare", "prepare-python312"):
            raise PreparationError("Only preparation accepts --download; installation and runtime checks are offline.")
        if args.command == "check-python":
            assert_windows_python()
            print("Python 3.12.10; Windows x86_64 runtime verified.")
            return 0
        if args.command == 'check-native':
            assert_windows_python()
            native_smoke()
            return 0
        manifest = load_manifest()
        if args.command == "prepare-python312":
            prepare_python312(manifest, CACHE, MONGO, args.download)
        elif args.command == "install-python312":
            install_python312(manifest, CACHE, VENV, MONGO)
        elif args.command == "check-installed":
            verify_installed(manifest, VENV, MONGO)
        elif args.command == "prepare":
            prepare(manifest, CACHE, args.download)
        else:
            install(manifest, CACHE, VENV, MONGO)
        return 0
    except (PreparationError, OSError, ValueError, KeyError, ImportError, subprocess.CalledProcessError, zipfile.BadZipFile, importlib.metadata.PackageNotFoundError) as error:
        # Configuration secrets are never read here; avoid exposing subprocess environments.
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
