"""Run the receipt-verified native lobby with the selected local account service."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.alliance_maintenance import local_path, validate_runtime
from tools.alliance_transport import verify_identity
from tools.alliance_workflow import backend_check
from tools.build_unified_multiplayer import verify, VERSION, ROOT


def quoted_path(path):
    value = str(path).replace("\\", "/")
    if any(char in value for char in ('"', '\n', '\r', '\x00')):
        raise ValueError("unsupported_path")
    return '"' + value + '"'


def configuration(runtime, identity):
    return ("# Owned unified game lobby configuration; no password is embedded.\n"
            "tls_enabled=yes\nalliance_auth=yes\n"
            "tls_fullchain=" + quoted_path(identity / "server-cert.pem") + "\n"
            "tls_private_key=" + quoted_path(identity / "server-key.pem") + "\n"
            "alliance_runtime=" + quoted_path(runtime) + "\n"
            "alliance_catalog=" + quoted_path(ROOT / "alliance/hero_catalog.json") + "\n"
            "alliance_backend_port=18765\n"
            'versions_accepted="1.19.26"\nconnections_allowed=32\n'
            'motd="Welcome. Your game account is already signed in. Casual games do not award permanent experience."\n')


def run(runtime, identity):
    runtime = validate_runtime(runtime)
    identity = local_path(identity)
    profile = verify_identity(identity)
    if profile["port"] != 15001 or not backend_check(runtime):
        raise ValueError("backend_or_identity_unavailable")
    binary = verify()
    version = subprocess.run([str(binary), "--unified-version"], capture_output=True, text=True, timeout=10)
    if version.returncode or version.stdout.strip() != VERSION:
        raise ValueError("wrong_native_server")
    directory = local_path(runtime / "multiplayer")
    directory.mkdir(mode=0o700, exist_ok=True)
    config = directory / ("launch-" + uuid.uuid4().hex + ".cfg")
    with config.open("x", encoding="utf-8", newline="\n") as output:
        output.write(configuration(runtime, identity)); output.flush(); os.fsync(output.fileno())
    print(f"Starting authenticated multiplayer at {profile['server_address']}:15000.", flush=True)
    print("Keep this window open. Ctrl+C stops this native lobby.", flush=True)
    process = subprocess.Popen([str(binary), "--config", str(config), "--port", "15000", "--log-info=server"], cwd=directory)
    try:
        code = process.wait()
        if code: raise ValueError("native_lobby_stopped")
    except KeyboardInterrupt:
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate(); process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.runtime, args.identity)
        return 0
    except (Exception, KeyboardInterrupt):
        print("ERROR: Unified multiplayer stopped. Check its build, selected runtime, backend and trusted identity.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
