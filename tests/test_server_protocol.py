#!/usr/bin/env python3
"""Exercise the real 1.19.26 TCP/gzip/WML guest protocol, using only stdlib.

Usage: python tests/test_server_protocol.py --server build/bin/wesnothd
The server runs in a temporary directory and is always stopped. Clients connect
to loopback, but upstream listens on all interfaces: use a network-isolated
container on the VPS (Docker --network none). This is not a gameplay test.
"""

import argparse
import contextlib
import gzip
import io
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time


VERSION = "1.19.26"
MAX_MESSAGE = 1024 * 1024


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Client:
    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline

    def close(self):
        self.sock.close()

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Protocol test exceeded its overall timeout")
        self.sock.settimeout(remaining)

    def read_exactly(self, count):
        data = bytearray()
        while len(data) < count:
            self.remaining()
            part = self.sock.recv(count - len(data))
            if not part:
                raise AssertionError("Server closed the connection before completing a response")
            data.extend(part)
        return bytes(data)

    def send(self, text):
        payload = gzip.compress(text.encode("utf-8"), mtime=0)
        self.remaining()
        self.sock.sendall(struct.pack("!I", len(payload)) + payload)

    def receive(self):
        size = struct.unpack("!I", self.read_exactly(4))[0]
        require(0 < size <= MAX_MESSAGE, f"Invalid compressed WML frame size: {size}")
        payload = self.read_exactly(size)
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            text = stream.read(MAX_MESSAGE + 1)
        require(len(text) <= MAX_MESSAGE, "Uncompressed response exceeds the smoke-test limit")
        return text.decode("utf-8")

    def until(self, predicate, description):
        # Login emits several independent frames (lobby, users, announcements).
        # Keep a global deadline so irrelevant frames cannot extend the timeout.
        for _ in range(64):
            text = self.receive()
            if "[error]" in text:
                raise AssertionError(f"Server returned an error while waiting for {description}: {text}")
            if predicate(text):
                return text
        raise AssertionError(f"Too many unrelated frames while waiting for {description}")

    def handshake(self):
        self.remaining()
        self.sock.sendall(struct.pack("!I", 0))
        require(struct.unpack("!I", self.read_exactly(4))[0] == 42, "Native handshake reply was not 42")
        self.until(lambda text: "[version]" in text, "version request")

    def negotiate(self, version):
        self.handshake()
        # Native simple_wml requires attributes in lexicographic order.
        # All other normal payloads in this test have at most one attribute.
        self.send(f'[version]\nclient_source="protocol-smoke"\nversion="{version}"\n[/version]\n')

    def login(self, nickname):
        self.negotiate(VERSION)
        self.until(lambda text: "[mustlogin]" in text, "guest login request")
        self.send(f'[login]\nusername="{nickname}"\n[/login]\n')
        self.until(lambda text: "[join_lobby]" in text, "lobby admission")
        listing = self.until(lambda text: "[gamelist]" in text, "initial game/user listing")
        require(f'name="{nickname}"' in listing, f"Guest {nickname} is absent from the lobby listing")
        require('registered="no"' in listing, "Guest was not listed as unregistered")
        return listing


def connect(port, deadline, process, wait_for_start=False):
    while True:
        if process.poll() is not None:
            raise AssertionError(f"Server exited unexpectedly with code {process.returncode}")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Server did not become ready within the timeout")
        try:
            return Client(socket.create_connection(("127.0.0.1", port), timeout=min(remaining, 1)), deadline)
        except (ConnectionRefusedError, socket.timeout):
            if not wait_for_start:
                raise
            time.sleep(min(0.05, remaining))


def stop_server(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_test(binary, config, timeout, log_path):
    process = None
    failure = None
    report = []
    with tempfile.TemporaryDirectory(prefix="wesnoth protocol ") as temporary:
        work = Path(temporary)
        environment = os.environ.copy()
        for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "TMPDIR", "TEMP", "TMP"):
            directory = work / name.lower()
            directory.mkdir()
            environment[name] = str(directory)
        # The bootstrap also sets PREFERENCES_DIR=server-userdata, which avoids
        # Windows KnownFolder APIs directing server state outside this cwd.
        server_log = work / "server.log"
        try:
            version = subprocess.run([str(binary), "--version"], cwd=work, env=environment,
                                     capture_output=True, text=True, errors="replace", timeout=timeout, check=True)
            require(version.stdout.strip() == f"Battle for Wesnoth server {VERSION}",
                    f"Unexpected server version: {version.stdout!r}")
            report.append(f"PASS server reports {VERSION}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            # There is a short race after releasing the port. A competing bind
            # causes a clear server failure, never a connection to another port.
            with server_log.open("wb") as output, contextlib.ExitStack() as clients:
                process = subprocess.Popen([str(binary), "--config", str(config), "--port", str(port), "--log-info=server"],
                                           cwd=work, env=environment, stdout=output, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + timeout
                    malformed = connect(port, deadline, process, wait_for_start=True)
                    clients.callback(malformed.close)
                    malformed.handshake()
                    malformed.send(f'[version]\nversion="{VERSION}"\nclient_source="protocol-smoke"\n[/version]\n')
                    malformed_response = malformed.receive()
                    require('[error]' in malformed_response and 'Invalid WML received: attributes not in order' in malformed_response,
                            f"Malformed WML was not rejected: {malformed_response}")
                    malformed.close()
                    require(process.poll() is None, "Malformed WML stopped the server")
                    report.append("PASS malformed WML rejected without stopping the server")

                    invalid = connect(port, deadline, process)
                    clients.callback(invalid.close)
                    invalid.negotiate("0.0.0")
                    rejected = invalid.until(lambda text: "[reject]" in text, "wrong-version rejection")
                    require(re.search(r'accepted_versions="1\.19\.26"', rejected),
                            f"Wrong-version rejection did not advertise {VERSION}: {rejected}")
                    invalid.close()
                    report.append("PASS native handshake and incompatible-version rejection")

                    first = connect(port, deadline, process)
                    clients.callback(first.close)
                    first.login("SmokeGuestOne")
                    second = connect(port, deadline, process)
                    clients.callback(second.close)
                    listing = second.login("SmokeGuestTwo")
                    require('name="SmokeGuestOne"' in listing, "Second guest cannot see the first guest")
                    report.append("PASS two guest logins and shared lobby/game listing")

                    first.send('[message]\nmessage="WesnothSmokeMessage"\n[/message]\n')
                    relayed = second.until(lambda text: "WesnothSmokeMessage" in text, "lobby chat relay")
                    require('[message]' in relayed and 'sender="SmokeGuestOne"' in relayed,
                            f"Lobby message has incorrect sender or structure: {relayed}")
                    report.append("PASS compressed WML lobby message relay")

                    first.send("[refresh_lobby]\n[/refresh_lobby]\n")
                    refreshed = first.until(lambda text: "[gamelist]" in text, "refreshed lobby listing")
                    require('name="SmokeGuestTwo"' in refreshed, "Lobby refresh lost the second guest")
                    require(process.poll() is None, "Server stopped during the protocol test")
                    report.append("PASS lobby refresh; server remains running")
                finally:
                    stop_server(process)
        except KeyboardInterrupt:
            failure = "Protocol test interrupted"
        except Exception as error:
            failure = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                failure += f"\nstdout: {error.stdout}\nstderr: {error.stderr}"
        finally:
            stop_server(process)
            captured = server_log.read_text(encoding="utf-8", errors="replace") if server_log.exists() else "Server was not started."
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("\n".join(report) + "\n" + (f"FAIL {failure}\n" if failure else "PASS protocol smoke test\n")
                                    + "\n--- server output ---\n" + captured, encoding="utf-8")
        for line in report:
            print(line)
        if failure:
            print(f"FAIL {failure}\n--- server output ---\n{captured}", file=sys.stderr)
            return 1
    print("PASS protocol smoke test (guest protocol only; gameplay and MongoDB are not tested)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, type=Path, help="Path to the built wesnothd executable")
    parser.add_argument("--timeout", type=float, default=30, help="Maximum protocol-test duration in seconds (default: 30)")
    parser.add_argument("--log-path", type=Path, help="Also save the outcome and server output at this path")
    arguments = parser.parse_args()
    if not 1 <= arguments.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    binary = arguments.server.resolve()
    if not binary.is_file() or binary.stat().st_size == 0:
        parser.error(f"Server executable is missing or empty: {binary}")
    config = Path(__file__).resolve().parents[1] / "configs" / "lan.cfg"
    if not config.is_file():
        parser.error(f"Server config is missing: {config}")
    return run_test(binary, config, arguments.timeout, arguments.log_path.resolve() if arguments.log_path else None)


if __name__ == "__main__":
    raise SystemExit(main())
