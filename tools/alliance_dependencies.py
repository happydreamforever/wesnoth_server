#!/usr/bin/env python3
"""Pinned, opt-in downloads and an offline Windows Alliance environment.

This tool never reads .env or initializes a database. Existing mismatched files
are preserved and rejected instead of being replaced.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import http.client
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
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
VENV = ROOT / "build" / "alliance-venv"
MONGO = ROOT / "build" / "alliance-mongodb"
OWNER = "wesnoth-alliance-dependencies-v1"
DOWNLOAD_ATTEMPTS = 3
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


def ensure_artifact(path: Path, item: dict, download: bool) -> None:
    if path.exists() or path.is_symlink():
        verify(path, item)
        print(f"Using verified cached {path.name}.", flush=True)
        return
    if not download:
        verify(path, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        partial = path.with_name(path.name + ".download-" + uuid.uuid4().hex)
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
            # Publication and local I/O errors are deliberately outside the
            # network retry classification. Never replace an existing file.
            with partial.open("rb") as source, path.open("xb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
            verify(path, item)
            return
        except _TransientDownloadError as error:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise PreparationError(
                    f"Download failed after {DOWNLOAD_ATTEMPTS} attempts: {path.name} ({error}). "
                    "Completed cache files are preserved. Keep internet connected and rerun preparation.") from None
            delay = 2 ** attempt
            print(f"Temporary download failure for {path.name} ({error}); retrying in {delay}s.", flush=True)
        finally:
            partial.unlink(missing_ok=True)
        time.sleep(delay)


def prepare(manifest: dict, cache: Path, download: bool = False) -> None:
    for item in manifest["wheels"]:
        ensure_artifact(cache / "wheels" / item["filename"], item, download)
    ensure_artifact(cache / manifest["mongodb"]["filename"], manifest["mongodb"], download)
    print(f"ALLIANCE DEPENDENCIES VERIFIED: {len(manifest['wheels'])} wheels; MongoDB {manifest['mongodb']['version']}.")


def write_json_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write("\n")


def extract_mongodb(manifest: dict, cache: Path, destination: Path) -> Path:
    item = manifest["mongodb"]
    archive = cache / item["filename"]
    verify(archive, item)
    marker = destination / "alliance-owned.json"
    if destination.exists():
        if not marker.is_file() or marker.is_symlink():
            raise PreparationError("Existing MongoDB directory has no ownership receipt; preserved.")
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        if receipt.get("owner") != OWNER or receipt.get("archive_sha256") != item["sha256"]:
            raise PreparationError("Existing MongoDB directory belongs to another recipe; preserved.")
        if receipt.get("files") != item["files"] or set(item["files"]) != set(MONGO_FILES):
            raise PreparationError("MongoDB receipt file selection differs from the recipe.")
        for name, expected in receipt["files"].items():
            verify(destination / name, {**expected, "filename": name})
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
        work.rename(destination)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return destination / "bin" / "mongod.exe"


def assert_windows_python() -> None:
    if sys.platform != "win32" or sys.version_info[:3] != (3, 14, 3) or sys.maxsize <= 2**32:
        raise PreparationError("Use the verified Windows x86_64 CPython 3.14.3 interpreter.")


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


def install(manifest: dict, cache: Path, venv: Path, mongodb: Path) -> None:
    assert_windows_python()
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "install", "check-python", "check-installed"))
    parser.add_argument("--download", action="store_true", help="Permit pinned downloads during prepare only.")
    args = parser.parse_args(argv)
    try:
        if args.download and args.command != "prepare":
            raise PreparationError("Only prepare accepts --download; installation and runtime checks are offline.")
        if args.command == "check-python":
            assert_windows_python()
            print("Python 3.14.3; Windows x86_64 runtime verified.")
            return 0
        manifest = load_manifest()
        if args.command == "check-installed":
            verify_installed(manifest, VENV, MONGO)
        elif args.command == "prepare":
            prepare(manifest, CACHE, args.download)
        else:
            install(manifest, CACHE, VENV, MONGO)
        return 0
    except (PreparationError, OSError, ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile, importlib.metadata.PackageNotFoundError) as error:
        # Configuration secrets are never read here; avoid exposing subprocess environments.
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
