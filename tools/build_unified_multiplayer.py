"""Build the authenticated native lobby in its own stage, preserving guest builds."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_alliance_bridge import BuildError, safe_path, digest, write_new, capture, native, check_host

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build/windows-unified-mingw64"
PURPOSE = "wesnoth-unified-native-multiplayer"
VERSION = "WESNOTH_UNIFIED_MULTIPLAYER release=1192624 protocol=4"
PRESERVABLE_VERSIONS = {VERSION, "WESNOTH_UNIFIED_MULTIPLAYER release=1192621 protocol=3", "WESNOTH_UNIFIED_MULTIPLAYER release=1192617 protocol=2"}


def binding():
    names = ["CMakeLists.txt", "tools/build_unified_multiplayer.py", "tools/build_alliance_bridge.py",
             "alliance_bridge/unified_protocol.hpp", "alliance/hero_catalog.json"]
    for directory in ("engine", "alliance_casual"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file():
                safe_path(path)
                names.append(path.relative_to(ROOT).as_posix())
    return {"format": 1, "purpose": PURPOSE, "inputs": {name: digest(ROOT / name) for name in names}}


def read_metadata(path):
    safe_path(path)
    if path.stat().st_size > 8 * 1024**2:
        raise BuildError("Native lobby metadata is oversized.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise BuildError("Native lobby metadata contains duplicate fields.")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def verify():
    expected = binding()
    if read_metadata(STAGE / "owner.json") != expected:
        raise BuildError("Native lobby sources differ from the saved build. Preserve the stage.")
    receipt = read_metadata(STAGE / "receipt.json")
    executable = safe_path(STAGE / "bin/wesnothd.exe")
    if (set(receipt) != {"binding", "executable", "version"} or receipt["binding"] != expected
            or receipt["version"] != VERSION or receipt["executable"] != {
                "bytes": executable.stat().st_size, "sha256": digest(executable)}):
        raise BuildError("Native lobby receipt does not match the executable.")
    print("UNIFIED MULTIPLAYER ARTIFACT VERIFIED", flush=True)
    return executable


def preserve_previous():
    """Retain a completed older build before compiling changed inputs."""
    if not STAGE.exists():
        return None
    safe_path(STAGE, directory=True)
    owner = read_metadata(STAGE / "owner.json")
    if owner == binding():
        # A same-input interrupted build is resumed by build(), not renamed.
        return None
    if (not isinstance(owner, dict) or set(owner) != {"format", "purpose", "inputs"}
            or owner["format"] != 1 or owner["purpose"] != PURPOSE
            or not isinstance(owner["inputs"], dict) or not owner["inputs"]
            or any(not isinstance(name, str) or not name or "\\" in name
                   or name.startswith("/") or ".." in name.split("/")
                   or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for name, value in owner["inputs"].items())):
        raise BuildError("Previous native lobby ownership is invalid. Existing stage was preserved.")
    receipt = read_metadata(STAGE / "receipt.json")
    executable = safe_path(STAGE / "bin/wesnothd.exe")
    if (not isinstance(receipt, dict) or set(receipt) != {"binding", "executable", "version"}
            or receipt["binding"] != owner or receipt["version"] not in PRESERVABLE_VERSIONS
            or receipt["executable"] != {"bytes": executable.stat().st_size,
                                        "sha256": digest(executable)}):
        raise BuildError("Previous native lobby is incomplete or changed. Existing stage was preserved.")
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
    backup = STAGE.with_name(STAGE.name + "-before-update-" + suffix)
    # Rename within the same parent; never delete or overwrite an older build.
    STAGE.rename(backup)
    print("Previous native multiplayer build preserved: " + str(backup), flush=True)
    return backup


def build(msys, cmake):
    check_host()
    prefix = safe_path(Path(msys) / "mingw64", directory=True)
    compiler = safe_path(prefix / "bin/g++.exe")
    ninja = safe_path(Path(msys) / "ucrt64/bin/ninja.exe")
    cmake = safe_path(cmake)
    environment = os.environ.copy()
    environment["PATH"] = str(prefix / "bin") + os.pathsep + environment.get("PATH", "")
    versions = {"cmake": capture([cmake, "--version"], environment).splitlines()[0],
        "ninja": capture([ninja, "--version"], environment),
        "target": capture([compiler, "-dumpmachine"], environment),
        "gcc": capture([compiler, "-dumpfullversion", "-dumpversion"], environment),
        "openssl": capture([prefix / "bin/openssl.exe", "version"], environment)}
    if (versions["cmake"] != "cmake version 4.3.0" or versions["ninja"] != "1.13.2"
            or versions["target"] != "x86_64-w64-mingw32" or versions["gcc"] != "16.2.0"
            or not re.match(r"OpenSSL 3\.6\.3(?:\s|$)", versions["openssl"])):
        raise BuildError("Use the already verified native Windows tool versions.")
    for key, value in versions.items(): print(f"{key}: {value}", flush=True)
    expected = binding()
    STAGE.parent.mkdir(parents=True, exist_ok=True)
    safe_path(STAGE.parent, directory=True)
    if STAGE.exists():
        safe_path(STAGE, directory=True)
        if read_metadata(STAGE / "owner.json") != expected:
            raise BuildError("Existing native lobby stage has different inputs. Preserve it and send the log.")
        if (STAGE / "receipt.json").exists():
            verify()
            return
        print("Resuming the same-input native lobby build.", flush=True)
    else:
        STAGE.mkdir()
        write_new(STAGE / "owner.json", expected)
    native([cmake, "-S", ROOT, "-B", STAGE, "-G", "Ninja",
        f"-DCMAKE_CXX_COMPILER={compiler.as_posix()}",
        f"-DCMAKE_C_COMPILER={(prefix / 'bin/gcc.exe').as_posix()}",
        f"-DCMAKE_RC_COMPILER={(prefix / 'bin/windres.exe').as_posix()}",
        f"-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}",
        f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}", f"-DBoost_ROOT={prefix.as_posix()}",
        f"-DOPENSSL_ROOT_DIR={prefix.as_posix()}", f"-DICU_ROOT={prefix.as_posix()}",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SUPPRESS_REGENERATION=ON"], environment)
    native([cmake, "--build", STAGE, "--parallel", "2", "--", "-d", "keepdepfile"], environment)
    executable = safe_path(STAGE / "bin/wesnothd.exe")
    if capture([executable, "--unified-version"], environment) != VERSION:
        raise BuildError("Built native server does not identify the unified protocol.")
    if binding() != expected: raise BuildError("Native server inputs changed during compilation.")
    write_new(STAGE / "receipt.json", {"binding": expected, "version": VERSION,
        "executable": {"bytes": executable.stat().st_size, "sha256": digest(executable)}})
    verify()
    print("UNIFIED MULTIPLAYER BUILD PASSED", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--preserve-previous", action="store_true",
                        help="Preserve a verified completed stage when source inputs have changed.")
    parser.add_argument("--msys", type=Path, default=Path(r"D:\Test\wesnoth-setup\msys64"))
    parser.add_argument("--cmake", type=Path, default=Path(r"C:\Program Files\CMake\bin\cmake.exe"))
    args = parser.parse_args()
    try:
        if args.verify and args.preserve_previous:
            raise BuildError("Verification cannot preserve or rebuild a stage.")
        if args.preserve_previous:
            preserve_previous()
        verify() if args.verify else build(args.msys, args.cmake)
        return 0
    except Exception as error:
        print("ERROR: " + (str(error) if isinstance(error, BuildError) else type(error).__name__))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
