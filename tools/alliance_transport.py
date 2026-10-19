#!/usr/bin/env python3
"""Prepare a private offline TLS identity and exercise its public profile locally.

This foundation does not start MongoDB/wesnothd or integrate account login into
the game. All probe sockets bind/connect to 127.0.0.1 on an OS-assigned port.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import stat
import subprocess
import sys
import threading


PURPOSE = "wesnoth-alliance-transport"
PROFILE_KEYS = {"format", "protocol", "server_address", "port", "minimum_tls",
                "certificate_pem", "certificate_sha256"}
FILES = ("owner.json", "openssl.cnf", "server-key.pem", "server-cert.pem", "public-profile.json")
TIMEOUT = 5


class TransportError(Exception):
    pass


def address(value):
    try:
        if not isinstance(value, str) or "%" in value:
            raise ValueError
        parsed = ipaddress.ip_address(value)
        if parsed.is_unspecified or parsed.is_multicast or str(parsed) == "255.255.255.255":
            raise ValueError
        return str(parsed)
    except ValueError:
        raise TransportError("Use a numeric unicast server IP address, without a port or zone suffix.") from None


def valid_port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise TransportError("Server port must be an integer from 1 to 65535.")
    return value


def linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def check_path(path):
    for item in (path, *path.parents):
        if linked(item):
            raise TransportError("Identity/report paths must not traverse symbolic links or junctions.")


def read_file(path, limit=32768):
    if linked(path):
        raise TransportError(f"Managed file is a link: {path.name}; files preserved.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise TransportError(f"Managed file is not a bounded, singly linked regular file: {path.name}.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise TransportError(f"Managed file is too large: {path.name}.")
    return data


def write_new(path, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate field")
            value[key] = item
        return value
    try:
        return json.loads(read_file(path), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise TransportError(f"Invalid JSON in {path.name}; files preserved.") from None


def restrict_directory(path):
    if os.name != "nt":
        path.chmod(0o700)
        return
    result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, timeout=30, check=True)
    rows = list(csv.reader(result.stdout.strip().splitlines()))
    if len(rows) != 1 or len(rows[0]) != 2 or not re.fullmatch(r"S-1-5-(?:\d+-)*\d+", rows[0][1]):
        raise TransportError("Could not determine the current Windows account SID; no key generated.")
    result = subprocess.run(["icacls.exe", str(path), "/inheritance:r", "/grant:r",
                             f"*{rows[0][1]}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise TransportError("Could not restrict the new identity directory; no key generated.")


def openssl_run(openssl, args, cwd=None):
    # No shell, global openssl.cnf, stdin passwords or private-key output.
    environment = os.environ.copy()
    for key in ("OPENSSL_CONF_INCLUDE", "OPENSSL_MODULES", "OPENSSL_ENGINES", "OPENSSL_TEST_LIBCTX"):
        environment.pop(key, None)
    environment["OPENSSL_CONF"] = os.devnull
    result = subprocess.run([str(openssl), *args], cwd=cwd, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=60, env=environment)
    if result.returncode:
        raise TransportError(f"OpenSSL {args[0]} failed (exit {result.returncode}); identity files preserved.")
    return result.stdout


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise TransportError("Public connection profile has unexpected fields.")
    if (type(profile["format"]) is not int or profile["format"] != 1
            or profile["protocol"] != "wesnoth-alliance-tls" or profile["minimum_tls"] != "1.2"):
        raise TransportError("Public connection profile format/protocol/TLS policy is unsupported.")
    if address(profile["server_address"]) != profile["server_address"]:
        raise TransportError("Profile address must be canonical.")
    valid_port(profile["port"])
    pem = profile["certificate_pem"]
    if not isinstance(pem, str) or len(pem) > 16384 or not re.fullmatch(
            r"-----BEGIN CERTIFICATE-----\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\n", pem):
        raise TransportError("Profile must contain exactly one public certificate.")
    try:
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    except ValueError:
        raise TransportError("Profile certificate encoding is invalid.") from None
    if profile["certificate_sha256"] != fingerprint:
        raise TransportError("Public certificate fingerprint does not match its profile.")


def tls_client_context(profile):
    validate_profile(profile)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.load_verify_locations(cadata=profile["certificate_pem"])
    # Deliberately no load_default_certs(), global trust installation or fallback.
    return context


def server_context(root):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(root / "server-cert.pem"), str(root / "server-key.pem"))
    return context


def _check_pair_and_identity(root, profile):
    # Memory BIOs verify key pairing, validity dates, numeric-IP SAN and trust
    # using a real TLS handshake without opening a listener or network socket.
    incoming_client, outgoing_client = ssl.MemoryBIO(), ssl.MemoryBIO()
    incoming_server, outgoing_server = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = tls_client_context(profile).wrap_bio(incoming_client, outgoing_client,
                                                server_hostname=profile["server_address"])
    server = server_context(root).wrap_bio(incoming_server, outgoing_server, server_side=True)
    complete = [False, False]
    for _ in range(32):
        for index, peer in enumerate((client, server)):
            if not complete[index]:
                try:
                    peer.do_handshake()
                    complete[index] = True
                except ssl.SSLWantReadError:
                    pass
        incoming_server.write(outgoing_client.read())
        incoming_client.write(outgoing_server.read())
        if all(complete):
            if hashlib.sha256(client.getpeercert(binary_form=True)).hexdigest() != profile["certificate_sha256"]:
                raise TransportError("Peer certificate differs from provisioned identity.")
            return
    raise TransportError("Identity validation handshake did not complete.")


def verify_identity(root, server_address=None, port=None):
    root = Path(root).absolute()
    check_path(root)
    try:
        if not root.is_dir() or {p.name for p in root.iterdir()} != set(FILES) | {"prepared.json"}:
            raise TransportError("Identity is incomplete or contains unexpected files; preserve it for review.")
        owner = read_json(root / "owner.json")
        if not isinstance(owner, dict) or set(owner) != {"purpose", "format", "server_address", "port"}:
            raise TransportError("Existing directory is not an owned transport identity; files preserved.")
        if owner["purpose"] != PURPOSE or type(owner["format"]) is not int or owner["format"] != 1:
            raise TransportError("Identity ownership/version is unsupported; files preserved.")
        profile = read_json(root / "public-profile.json")
        validate_profile(profile)
        expected = {"purpose": PURPOSE, "format": 1, "server_address": profile["server_address"], "port": profile["port"]}
        if owner != expected:
            raise TransportError("Identity owner and public profile disagree; files preserved.")
        if ((server_address is not None and address(server_address) != profile["server_address"])
                or (port is not None and valid_port(port) != profile["port"])):
            raise TransportError("Requested address/port differs from existing identity; no key was replaced.")
        receipt = read_json(root / "prepared.json")
        hashes = {name: hashlib.sha256(read_file(root / name)).hexdigest() for name in FILES}
        if (not isinstance(receipt, dict) or type(receipt.get("format")) is not int
                or receipt != {"format": 1, "purpose": PURPOSE, "files": hashes}):
            raise TransportError("Identity file fingerprint changed; files preserved.")
        if read_file(root / "server-cert.pem").decode("ascii").replace("\r\n", "\n") != profile["certificate_pem"]:
            raise TransportError("Public profile and server certificate disagree.")
        _check_pair_and_identity(root, profile)
        return profile
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise TransportError(f"Identity validation failed ({type(error).__name__}); files preserved.") from None


def prepare_identity(root, server_address, port, openssl, required_version=None):
    host, port = address(server_address), valid_port(port)
    root = Path(root).absolute()
    check_path(root)
    openssl = Path(openssl).absolute()
    version = openssl_run(openssl, ["version"]).decode("ascii", errors="replace").strip()
    match = re.match(r"OpenSSL (\d+\.\d+\.\d+)\b", version)
    if not match or (required_version and match[1] != required_version):
        raise TransportError("Selected OpenSSL does not match the required version; no identity created.")
    print("OpenSSL executable: " + version, flush=True)
    if root.exists():
        return verify_identity(root, host, port), False
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)  # Exclusive: concurrent initialization cannot overwrite files.
    restrict_directory(root)  # Must complete before private material is generated.
    write_new(root / "owner.json", json_bytes({"purpose": PURPOSE, "format": 1, "server_address": host, "port": port}))
    config = ("[req]\nprompt = no\ndistinguished_name = dn\nx509_extensions = server\n"
              "[dn]\nCN = Wesnoth Alliance Local Server\n[server]\n"
              "basicConstraints = critical,CA:FALSE\nkeyUsage = critical,digitalSignature,keyEncipherment\n"
              "extendedKeyUsage = serverAuth\nsubjectKeyIdentifier = hash\nauthorityKeyIdentifier = keyid:always\n"
              f"subjectAltName = IP:{host}\n")
    write_new(root / "openssl.cnf", config)
    # Output locations are inside this exclusively created, restricted directory.
    # An interrupted directory is preserved and never silently regenerated.
    openssl_run(openssl, ["req", "-new", "-x509", "-newkey", "rsa:3072", "-noenc",
                         "-sha256", "-days", "365", "-config", "openssl.cnf",
                         "-keyout", "server-key.pem", "-out", "server-cert.pem"], cwd=root)
    if os.name != "nt":
        (root / "server-key.pem").chmod(0o600)
        (root / "server-cert.pem").chmod(0o600)
    pem = read_file(root / "server-cert.pem").decode("ascii").replace("\r\n", "\n")
    # Native OpenSSL may write CRLF on Windows. Canonicalize only the public
    # profile string; the original certificate bytes stay covered by the receipt.
    profile = {"format": 1, "protocol": "wesnoth-alliance-tls", "server_address": host,
               "port": port, "minimum_tls": "1.2", "certificate_pem": pem,
               "certificate_sha256": hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()}
    write_new(root / "public-profile.json", json_bytes(profile))
    _check_pair_and_identity(root, profile)
    hashes = {name: hashlib.sha256(read_file(root / name)).hexdigest() for name in FILES}
    write_new(root / "prepared.json", json_bytes({"format": 1, "purpose": PURPOSE, "files": hashes}))
    return verify_identity(root, host, port), True


@contextmanager
def loopback_peer(context, challenge, *, plaintext=False):
    errors, received = [], []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(TIMEOUT)
    endpoint = listener.getsockname()

    def serve():
        try:
            with listener.accept()[0] as raw:
                raw.settimeout(TIMEOUT)
                if plaintext:
                    raw.recv(4096)
                    raw.sendall(b"HTTP/1.0 400 Plaintext rejected\r\n\r\n")
                    return
                try:
                    with context.wrap_socket(raw, server_side=True) as secure:
                        data = bytearray()
                        while len(data) < len(challenge):
                            part = secure.recv(len(challenge) - len(data))
                            if not part:
                                break
                            data.extend(part)
                        if data:
                            received.append(bytes(data))
                            secure.sendall(bytes(data))
                except ssl.SSLError:
                    pass  # Negative peer-verification cases intentionally abort.
        except BaseException as error:
            errors.append(type(error).__name__)

    worker = threading.Thread(target=serve, name="alliance-tls-loopback", daemon=True)
    worker.start()
    try:
        yield endpoint, received
    finally:
        worker.join(TIMEOUT + 1)
        listener.close()
        if worker.is_alive() or errors:
            raise TransportError("Loopback fixture did not finish cleanly: " + ",".join(errors))


def run_probe(root, profile):
    # Verify immutable files again before loading the private key for the fixture.
    if verify_identity(root) != profile:
        raise TransportError("Probe profile differs from the owned identity.")
    context = server_context(Path(root))
    challenge = b"Wesnoth-Alliance-probe:" + secrets.token_bytes(24)
    passed = []
    for version, name in ((ssl.TLSVersion.TLSv1_2, "TLS1.2"), (ssl.TLSVersion.TLSv1_3, "TLS1.3")):
        client = tls_client_context(profile)
        client.minimum_version = client.maximum_version = version
        with loopback_peer(context, challenge) as (endpoint, received):
            with socket.create_connection(endpoint, timeout=TIMEOUT) as raw:
                with client.wrap_socket(raw, server_hostname=profile["server_address"]) as secure:
                    if hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest() != profile["certificate_sha256"]:
                        raise TransportError("Loopback peer fingerprint differs from profile.")
                    secure.sendall(challenge)
                    reply = bytearray()
                    while len(reply) < len(challenge):
                        part = secure.recv(len(challenge) - len(reply))
                        if not part:
                            break
                        reply.extend(part)
                    if bytes(reply) != challenge:
                        raise TransportError("Encrypted probe payload did not round-trip.")
        if received != [challenge]:
            raise TransportError("Loopback server did not receive the exact probe payload.")
        passed.append(f"{name} trusted numeric-IP identity and encrypted payload")
    for kind in ("wrong-ip", "untrusted", "plaintext"):
        client = tls_client_context(profile) if kind != "untrusted" else ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.minimum_version = ssl.TLSVersion.TLSv1_2
        host = profile["server_address"]
        if kind == "wrong-ip":
            host = "192.0.2.2" if host == "192.0.2.1" else "192.0.2.1"
        rejected = False
        with loopback_peer(context, challenge, plaintext=(kind == "plaintext")) as (endpoint, received):
            with socket.create_connection(endpoint, timeout=TIMEOUT) as raw:
                try:
                    with client.wrap_socket(raw, server_hostname=host):
                        raise TransportError(f"Negative TLS case unexpectedly connected: {kind}.")
                except ssl.SSLCertVerificationError as error:
                    if kind == "plaintext" or (kind == "wrong-ip" and error.verify_code != 64):
                        raise
                    rejected = True
                except ssl.SSLError:
                    if kind != "plaintext":
                        raise
                    rejected = True
        if not rejected or received:
            raise TransportError("Negative TLS case did not reject before application data.")
        passed.append(f"{kind} rejected before application data")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument("--server-address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15001)
    parser.add_argument("--openssl", type=Path, required=True)
    parser.add_argument("--require-openssl-version")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"format": 1, "scope": "Python loopback TLS identity fixture; no native game or MongoDB integration",
              "python": sys.version.split()[0], "python_ssl": ssl.OPENSSL_VERSION, "status": "failed"}
    try:
        check_path(args.report.absolute())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the report before any key generation. Never overwrite old logs.
        with args.report.open("x", encoding="utf-8") as out:
            try:
                profile, created = prepare_identity(args.identity_root, args.server_address, args.port,
                                                    args.openssl, args.require_openssl_version)
                report.update(identity="created" if created else "reused", server_address=profile["server_address"],
                              port=profile["port"], certificate_sha256=profile["certificate_sha256"])
                print("PASS " + report["identity"] + " server identity; private key stays on this computer.", flush=True)
                print("Public profile: " + str(args.identity_root / "public-profile.json"), flush=True)
                report["checks"] = run_probe(args.identity_root, profile)
                for item in report["checks"]:
                    print("PASS " + item, flush=True)
                report["status"] = "passed"
            except (Exception, KeyboardInterrupt) as error:
                report["error"] = str(error) if isinstance(error, TransportError) else type(error).__name__
                print("ERROR: " + report["error"], file=sys.stderr, flush=True)
            finally:
                json.dump(report, out, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
        print("Report saved: " + str(args.report), flush=True)
        if report["status"] == "passed":
            print("ALLIANCE TRANSPORT IDENTITY CHECK PASSED", flush=True)
            print("Local Python TLS fixture only. Account login, MongoDB and native game integration remain pending.", flush=True)
            return 0
    except (OSError, TransportError) as error:
        print("ERROR: Report could not be reserved/written: " + type(error).__name__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
