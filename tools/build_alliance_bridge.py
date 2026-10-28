#!/usr/bin/env python3
"""Offline build/verification of the separate native Alliance account bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build/alliance-account-bridge"
INPUTS = ("alliance_bridge/CMakeLists.txt", "alliance_bridge/main.cpp", "alliance_bridge/progression_protocol.hpp", "alliance_bridge/unified_protocol.hpp", "alliance_bridge/flexible_protocol.hpp", "alliance_bridge/world_protocol.hpp", "tools/build_alliance_bridge.py")
PURPOSE = "wesnoth-alliance-account-bridge"


class BuildError(ValueError):
    pass


def safe_path(path, *, directory=False):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise BuildError("Managed paths must not traverse links or junctions.")
    if directory:
        if not path.is_dir():
            raise BuildError("A required directory is missing.")
    elif not path.is_file() or path.stat().st_nlink != 1 or not path.stat().st_size:
        raise BuildError("A required ordinary, nonempty file is missing.")
    return path


def digest(path):
    with safe_path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def binding():
    return {"format": 1, "purpose": PURPOSE, "inputs": {name: digest(ROOT / name) for name in INPUTS}}


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path):
    path = safe_path(path)
    if path.stat().st_size > 32768:
        raise BuildError("Managed metadata is too large.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BuildError("Duplicate managed metadata key.")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def verify():
    expected = binding()
    if read_json(STAGE / "owner.json") != expected:
        raise BuildError("Account bridge inputs changed. Keep the existing stage for review.")
    receipt = read_json(STAGE / "receipt.json")
    executable = safe_path(STAGE / "alliance-account-bridge.exe")
    if (set(receipt) != {"binding", "executable", "versions"} or receipt["binding"] != expected
            or receipt["executable"] != {"name": executable.name, "bytes": executable.stat().st_size,
                                         "sha256": digest(executable)}):
        raise BuildError("Account bridge receipt does not match its executable and sources.")
    print("ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED", flush=True)
    return executable


def capture(command, environment):
    result = subprocess.run([str(part) for part in command], capture_output=True, timeout=30, env=environment)
    if result.returncode:
        raise BuildError("A selected native tool version check failed.")
    return result.stdout.decode("utf-8", "replace").strip()


def native(command, environment):
    # Native output goes directly to the console, not through an MSYS pipe.
    result = subprocess.run([str(part) for part in command], env=environment, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise BuildError(f"Native bridge build failed with exit {result.returncode}. Keep the saved log.")


def check_host():
    if os.name != "nt" or sys.version_info[:3] != (3, 12, 10) or sys.maxsize <= 2**32:
        raise BuildError("Use the verified Windows x86_64 Python 3.12.10.")


def build(msys, cmake):
    check_host()
    msys = safe_path(msys, directory=True)
    prefix = safe_path(msys / "mingw64", directory=True)
    compiler = safe_path(prefix / "bin/g++.exe")
    openssl = safe_path(prefix / "bin/openssl.exe")
    ninja = safe_path(msys / "ucrt64/bin/ninja.exe")
    cmake = safe_path(cmake)
    environment = os.environ.copy()
    environment["PATH"] = str(prefix / "bin") + os.pathsep + environment.get("PATH", "")
    versions = {
        "cmake": capture([cmake, "--version"], environment).splitlines()[0],
        "ninja": capture([ninja, "--version"], environment),
        "target": capture([compiler, "-dumpmachine"], environment),
        "gcc": capture([compiler, "-dumpfullversion", "-dumpversion"], environment),
        "openssl": capture([openssl, "version"], environment),
    }
    for name, value in versions.items():
        print(f"{name}: {value}", flush=True)
    if (versions["cmake"] != "cmake version 4.3.0" or versions["ninja"] != "1.13.2"
            or versions["target"] != "x86_64-w64-mingw32" or versions["gcc"] != "16.2.0"
            or not re.match(r"OpenSSL 3\.6\.3(?:\s|$)", versions["openssl"])):
        raise BuildError("Use the previously verified native tool versions; no versions were changed.")
    boost_version = safe_path(prefix / "include/boost/version.hpp").read_text(encoding="utf-8")
    if not re.search(r'^#define BOOST_LIB_VERSION "1_91"$', boost_version, re.M):
        raise BuildError("The existing MINGW64 Boost 1.91 headers are required.")
    versions["boost"] = "1.91"
    expected = binding()
    STAGE.parent.mkdir(parents=True, exist_ok=True)
    safe_path(STAGE.parent, directory=True)
    if STAGE.exists():
        verify()
        print("Completed native account bridge reused; no build was run.")
        return
    STAGE.mkdir()
    write_new(STAGE / "owner.json", expected)
    native([cmake, "-S", ROOT / "alliance_bridge", "-B", STAGE, "-G", "Ninja",
            f"-DCMAKE_CXX_COMPILER={compiler.as_posix()}",
            f"-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}",
            f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}",
            f"-DBOOST_INCLUDE_DIR={(prefix / 'include').as_posix()}",
            f"-DOPENSSL_ROOT_DIR={prefix.as_posix()}",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SUPPRESS_REGENERATION=ON"], environment)
    native([cmake, "--build", STAGE, "--parallel", "2", "--", "-d", "keepdepfile"], environment)
    executable = safe_path(STAGE / "alliance-account-bridge.exe")
    version = capture([executable, "--version"], environment)
    if version != "WESNOTH_ALLIANCE_ACCOUNT_BRIDGE protocol=4 max_connections=32 timeout_seconds=10":
        raise BuildError("Built executable version did not match the account protocol.")
    if binding() != expected:
        raise BuildError("Source inputs changed during the build; completed output was preserved.")
    write_new(STAGE / "receipt.json", {"binding": expected, "versions": versions,
                                     "executable": {"name": executable.name, "bytes": executable.stat().st_size,
                                                    "sha256": digest(executable)}})
    verify()
    print("ALLIANCE ACCOUNT BRIDGE BUILD PASSED", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--msys", type=Path, default=Path(r"D:\Test\wesnoth-setup\msys64"))
    parser.add_argument("--cmake", type=Path, default=Path(r"C:\Program Files\CMake\bin\cmake.exe"))
    args = parser.parse_args()
    try:
        verify() if args.verify else build(args.msys, args.cmake)
        return 0
    except (BuildError, OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, BuildError) else type(error).__name__
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
