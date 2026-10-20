#!/usr/bin/env python3
"""Exercise the real C++ Alliance transport; only temporary loopback peers.

Reads the existing public profile, never its private key or MongoDB settings.
Disposable identities and failures remain in the new restricted scratch folder.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import copy

SPEC = importlib.util.spec_from_file_location(
    "alliance_transport_fixture", Path(__file__).with_name("alliance_transport.py"))
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)
CANARY = bytes.fromhex(
    "1f8b08000000000002038b4eccc9c94ccc4b4e8d2f28ca4f4a8de52a4bcc294db555"
    "ca4b2cc92c4bd54d4ecc4b2caad42d3354e28ad647570a00b6c2a6933c000000")


class FixtureError(Exception):
    pass


def exact(stream, count):
    result = bytearray()
    while len(result) < count:
        part = stream.recv(count - len(result))
        if not part:
            raise EOFError
        result.extend(part)
    return bytes(result)


def server_context(identity, version=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if version is not None:
        context.minimum_version = context.maximum_version = version
    context.load_cert_chain(identity / "server-cert.pem", identity / "server-key.pem")
    return context


@contextmanager
def peer(context, behavior):
    """One peer, bounded lifetime; count unexpected reconnects as failures."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(3)
    listener.settimeout(0.1)
    stop = threading.Event()
    result = {"connections": 0, "preamble": None, "application_bytes": 0,
              "stage": "accept", "error": None}

    def worker():
        try:
            while not stop.is_set():
                try:
                    raw, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            result["connections"] += 1
            with raw:
                raw.settimeout(4)
                result["stage"] = "preamble"
                result["preamble"] = exact(raw, 4).hex()
                if result["preamble"] != "00000001":
                    raise FixtureError("Native client did not request TLS")
                if behavior == "preamble-eof":
                    return
                if behavior == "preamble-reset":
                    # Winsock's linger fields are unsigned short; POSIX uses int.
                    layout = "HH" if os.name == "nt" else "ii"
                    raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                   struct.pack(layout, 1, 0))
                    return
                if behavior in ("preamble-stall", "cancel"):
                    stop.wait(3)
                    return
                response = {"downgrade": 0xffffffff, "unexpected": 2}.get(behavior, 0)
                raw.sendall(struct.pack("!I", response))
                if behavior in ("downgrade", "unexpected"):
                    result["application_bytes"] = len(raw.recv(4096))
                    return
                if behavior == "plaintext":
                    raw.sendall(b"This is not a TLS server.\r\n")
                    # Subsequent bytes may be ClientHello, never account frames.
                    return
                if behavior == "tls-stall":
                    stop.wait(3)
                    return
                result["stage"] = "tls-handshake"
                with context.wrap_socket(raw, server_side=True) as secure:
                    result["tls_version"] = secure.version()
                    result["stage"] = "application"
                    if behavior == "server-push":
                        secure.sendall(struct.pack("!I", len(CANARY)) + CANARY)
                        result["application_bytes"] = len(secure.recv(4096))
                        return
                    size = struct.unpack("!I", exact(secure, 4))[0]
                    if size != len(CANARY):
                        raise FixtureError("Unexpected application frame size")
                    data = exact(secure, size)
                    result["application_bytes"] = len(data)
                    if data != CANARY:
                        raise FixtureError("Unexpected application canary")
                    if behavior == "oversized":
                        secure.sendall(struct.pack("!I", 65537))
                    elif behavior == "empty-frame":
                        secure.sendall(bytes(4))
                    elif behavior == "partial-header":
                        secure.sendall(b"\x00\x00")
                    elif behavior == "partial-body":
                        secure.sendall(struct.pack("!I", len(CANARY)) + CANARY[:3])
                    elif behavior == "receive-stall":
                        stop.wait(3)
                    else:
                        secure.sendall(struct.pack("!I", size) + data)
        except (ssl.SSLError, ConnectionResetError, BrokenPipeError, EOFError, OSError) as error:
            result["error"] = T.error_details(error)
        except Exception as error:
            result["unexpected_error"] = type(error).__name__
        finally:
            # Keep the listener until the client exits: count any downgrade retry.
            while not stop.is_set():
                try:
                    retry, _ = listener.accept()
                    result["connections"] += 1
                    retry.close()
                except socket.timeout:
                    continue
                except OSError:
                    break

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], result
    finally:
        stop.set()
        thread.join(5)
        # Account for a queued reconnect even if it raced with the stop event.
        if not thread.is_alive():
            while True:
                try:
                    retry, _ = listener.accept()
                    result["connections"] += 1
                    retry.close()
                except socket.timeout:
                    break
        listener.close()
        if thread.is_alive():
            raise FixtureError("Loopback peer did not finish within its bound")


def probe_run(binary, profile, certificate, *, port=None, extra=()):
    command = [str(binary), "--address", profile["server_address"], "--port",
               str(port or profile["port"]), "--certificate", str(certificate),
               "--sha256", profile["certificate_sha256"], "--timeout-ms", "1500", *extra]
    started = time.monotonic()
    environment = os.environ.copy()
    # These tests are self-contained even on hosts with global OpenSSL settings.
    environment["OPENSSL_CONF"] = os.devnull
    for name in ("OPENSSL_CONF_INCLUDE", "OPENSSL_MODULES", "OPENSSL_ENGINES"):
        environment.pop(name, None)
    result = subprocess.run(command, capture_output=True, timeout=12, env=environment)
    if len(result.stdout) > 8192 or len(result.stderr) > 8192:
        raise FixtureError("Native probe output exceeded its diagnostic bound")
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise FixtureError("Native probe did not produce its JSON result") from None
    if not isinstance(value, dict) or type(value.get("ok")) is not bool:
        raise FixtureError("Native probe result has an invalid schema")
    if (result.returncode == 0) != value["ok"]:
        raise FixtureError("Native probe result disagrees with its exit status")
    value["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return value


def probe_metadata(binary, flag):
    result = subprocess.run([str(binary), flag], capture_output=True, timeout=10)
    if result.returncode or len(result.stdout) > 8192:
        raise FixtureError("Native " + flag + " failed")
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise FixtureError("Invalid native metadata") from None
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise FixtureError("Native metadata check failed")
    return value


def expired_certificate(scratch, identity, openssl):
    """Self-sign one expired leaf using only the disposable fixture identity.

    No CA database/serial rotation is needed for this single test certificate.
    Explicit dates require the selected OpenSSL 3.6.3 (VPS checks use 3.5.7).
    """
    directory = scratch / "expired"
    directory.mkdir()
    T.openssl_run(openssl, ["req", "-new", "-key", str(identity / "server-key.pem"),
        "-out", "request.pem", "-config", str(identity / "openssl.cnf")], cwd=directory)
    data = T.openssl_run(openssl, ["x509", "-req", "-in", "request.pem",
        "-signkey", str(identity / "server-key.pem"), "-sha256", "-set_serial", "1",
        "-extfile", str(identity / "openssl.cnf"), "-extensions", "server",
        "-not_before", "20000101000000Z", "-not_after", "20010101000000Z"], cwd=directory)
    path = directory / "public.pem"
    T.write_new(path, data)
    return path, data.decode("ascii")


def run(args, report):
    T.check_path(args.scratch)
    T.check_path(args.profile)
    original = T.read_file(args.profile)
    profile = T.read_json(args.profile)
    T.validate_profile(profile)
    args.scratch.mkdir(mode=0o700)  # Always new; never adopts or deletes old state.
    T.restrict_directory(args.scratch)
    T.write_new(args.scratch / "owner.json", T.json_bytes({"kind": "alliance-native-fixture", "format": 1}))
    public_cert = args.scratch / "existing-public-cert.pem"
    T.write_new(public_cert, profile["certificate_pem"])
    report.update({"scope": "native C++ component; no account login or Android execution",
                   "python": sys.version.split()[0], "python_ssl": ssl.OPENSSL_VERSION,
                   "public_profile_sha256": hashlib.sha256(original).hexdigest(),
                   "probe_sha256": hashlib.sha256(args.probe.read_bytes()).hexdigest(),
                   "checks": []})
    versions = probe_metadata(args.probe, "--version")
    report["native_versions"] = versions
    if os.name == "nt" and (versions.get("boost") != "1_91" or
        versions.get("openssl_header_number") != 0x30600030 or
        versions.get("openssl_library_number") != 0x30600030 or
        versions.get("compiler") != "gcc" or versions.get("compiler_major") != 16 or
        versions.get("compiler_minor") != 2):
        raise FixtureError("Native Windows compiler/Boost/OpenSSL differs from the verified pins")
    print("Native Boost=" + str(versions.get("boost")) + "; OpenSSL number=" +
          hex(versions.get("openssl_library_number", 0)), flush=True)

    def checked(name, result, *, ok=True, errors=(), observation=None):
        row = {"case": name, "result": result, "status": "failed"}
        if observation is not None:
            row["peer"] = dict(observation)
        report["checks"].append(row)
        if result["ok"] != ok or (errors and result.get("error") not in errors):
            raise FixtureError("Unexpected native result for " + name)
        if observation is not None:
            if observation.get("unexpected_error") or observation["connections"] != 1:
                raise FixtureError("Unexpected peer failure or reconnect for " + name)
            if observation["preamble"] != "00000001":
                raise FixtureError("Wrong native TLS preamble for " + name)
            if name in ("TLS1.2", "TLS1.3") and result.get("tls_version") != "TLSv" + name[3:]:
                raise FixtureError("Native TLS version differs for " + name)
            if ok and (result.get("received_bytes") != len(CANARY) or
                       result.get("is_gzip") is not True or
                       result.get("tls_version") != observation.get("tls_version")):
                raise FixtureError("Native frame or negotiated TLS differs for " + name)
            expected_stage = {"preamble-stall": "preamble_read", "cancel": "preamble_read",
                              "tls-stall": "tls_handshake", "receive-stall": "receive_header"}.get(name)
            if expected_stage and result.get("stage") != expected_stage:
                raise FixtureError("Native deadline/cancel failed at unexpected stage for " + name)
            if name not in ("TLS1.2", "TLS1.3", "oversized", "empty-frame", "partial-header",
                            "partial-body", "receive-stall") and observation["application_bytes"] != 0:
                raise FixtureError("Unexpected application bytes for " + name)
        row["status"] = "passed"
        print("PASS " + name, flush=True)

    print("RUN existing-public-profile (no socket)", flush=True)
    checked("existing-public-profile", probe_run(args.probe, profile, public_cert,
                                                 extra=("--validate-only",)))
    if T.read_file(args.profile) != original:
        raise FixtureError("Original public profile changed")
    checked("before-connect-guards", probe_metadata(args.probe, "--guards-only"))

    identity = args.scratch / "loopback-identity"
    loopback, _ = T.prepare_identity(identity, "127.0.0.1", 15001, args.openssl,
                                    required_version=args.require_openssl_version)
    other = args.scratch / "untrusted-identity"
    T.prepare_identity(other, "127.0.0.1", 15001, args.openssl,
                       required_version=args.require_openssl_version)
    cert = identity / "server-cert.pem"
    for name, field, value, error in (
        ("wrong-ip", "server_address", "127.0.0.2", "certificate_rejected"),
        ("wrong-pin", "certificate_sha256", "0" * 64, "pin_mismatch"),
        ("hostname-refused", "server_address", "localhost", "invalid_profile"),
        ("broadcast-refused", "server_address", "255.255.255.255", "invalid_profile")):
        changed = copy.deepcopy(loopback)
        changed[field] = value
        print("RUN " + name + " (no socket)", flush=True)
        checked(name, probe_run(args.probe, changed, cert, extra=("--validate-only",)),
                ok=False, errors=(error,))
    print("PREPARE expired fixture certificate (disposable identity)", flush=True)
    expired_path, expired_pem = expired_certificate(args.scratch, identity, args.openssl)
    changed = copy.deepcopy(loopback)
    changed["certificate_sha256"] = hashlib.sha256(ssl.PEM_cert_to_DER_cert(expired_pem)).hexdigest()
    print("RUN expired (no socket)", flush=True)
    checked("expired", probe_run(args.probe, changed, expired_path, extra=("--validate-only",)),
            ok=False, errors=("certificate_rejected",))
    cases = [
        ("TLS1.2", "echo", ssl.TLSVersion.TLSv1_2, True),
        ("TLS1.3", "echo", ssl.TLSVersion.TLSv1_3, True),
        ("server-push", "server-push", None, True),
        ("untrusted", "untrusted", None, False),
        *[(name, name, None, False) for name in (
            "downgrade", "unexpected", "preamble-eof", "preamble-reset", "preamble-stall",
            "plaintext", "tls-stall", "cancel", "oversized", "empty-frame",
            "partial-header", "partial-body", "receive-stall")],
    ]
    for name, behavior, version, success in cases:
        print("RUN " + name, flush=True)
        context = server_context(other if name == "untrusted" else identity, version)
        extra = ("--receive-only",) if name == "server-push" else (
            ("--cancel-after-ms", "150") if name == "cancel" else ())
        with peer(context, behavior) as (port, observation):
            result = probe_run(args.probe, loopback, cert, port=port, extra=extra)
        # Failure type expectations are checked below; no arbitrary failure passes.
        expected = {
            "untrusted": ("certificate_rejected",), "downgrade": ("tls_required",),
            "unexpected": ("tls_required",), "preamble-eof": ("preamble_failed",),
            "preamble-reset": ("preamble_failed",), "preamble-stall": ("timeout",),
            "plaintext": ("tls_failed",), "tls-stall": ("timeout",), "cancel": ("cancelled",),
            "oversized": ("invalid_frame",), "empty-frame": ("invalid_frame",),
            "partial-header": ("read_failed",), "partial-body": ("read_failed",), "receive-stall": ("timeout",),
        }.get(name, ())
        checked(name, result, ok=success, errors=expected, observation=observation)
    report["status"] = "passed"
    print("ALLIANCE NATIVE TRANSPORT CHECK PASSED", flush=True)
    print("C++ transport only; game UI, account login and MongoDB acceptance remain pending.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("probe", "profile", "openssl", "report", "scratch"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--require-openssl-version")
    args = parser.parse_args()
    for name in ("probe", "profile", "openssl", "report", "scratch"):
        setattr(args, name, getattr(args, name).absolute())
    report = {"format": 1, "status": "failed"}
    result = 1
    report_allowed = False
    try:
        T.check_path(args.report)
        if args.report.exists():
            raise FixtureError("Report already exists; preserved")
        report_allowed = True
        run(args, report)
        result = 0
    except Exception as error:
        report["error"] = T.error_details(error)
        # Only our own messages are shown; third-party exceptions may contain data.
        print("ERROR: " + (str(error) if isinstance(error, (FixtureError, T.TransportError))
                           else type(error).__name__), flush=True)
    finally:
        try:
            if report_allowed:
                T.write_new(args.report, T.json_bytes(report))
                print("Report saved: " + str(args.report), flush=True)
        except Exception as error:
            print("ERROR saving native report: " + type(error).__name__, flush=True)
            result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
