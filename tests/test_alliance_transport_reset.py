"""Strict rejection accounting and real loopback reset regressions.

The abortive-close cases use real local sockets. Injected faults exercise
otherwise platform-dependent error paths without claiming Windows execution.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "alliance_transport_reset_subject", ROOT / "tools/alliance_transport.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
OPENSSL = shutil.which("openssl")
CHALLENGE = b"Alliance reset regression application payload"
POSITIVE_CHECKS = [
    "TLS1.2 trusted numeric-IP identity and encrypted payload",
    "TLS1.3 trusted numeric-IP identity and encrypted payload",
]
ALL_CHECKS = POSITIVE_CHECKS + [
    "wrong-ip rejected before application data",
    "untrusted rejected before application data",
    "plaintext rejected before application data",
]


def snapshot(root):
    """Compare private fixture bytes and modes without reporting their values."""
    return {str(path.relative_to(root)): (
        path.lstat().st_mode, path.read_bytes() if path.is_file() else None)
        for path in (root, *sorted(root.rglob("*")))}


def abortive_close(connection):
    # Winsock's linger uses two unsigned shorts; POSIX uses two ints.
    layout = "HH" if os.name == "nt" else "ii"
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                          struct.pack(layout, 1, 0))
    connection.close()


class FailingContext:
    """Fail in the server's actual accepted-socket handshake boundary."""

    def __init__(self, error):
        self.error = error

    def wrap_socket(self, raw, *, server_side):
        if not server_side:
            raise AssertionError("Expected the server side of the fixture")
        raise self.error


class ClientContextProxy:
    """Keep real memory-BIO identity verification and positive socket checks."""

    def __init__(self, context, actual_host, negative_action):
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "actual_host", actual_host)
        object.__setattr__(self, "negative_action", negative_action)

    def __getattr__(self, name):
        return getattr(self.context, name)

    def __setattr__(self, name, value):
        setattr(self.context, name, value)

    def wrap_socket(self, raw, *, server_hostname):
        if server_hostname != self.actual_host:
            return self.negative_action(self.context, raw, self.actual_host)
        return self.context.wrap_socket(raw, server_hostname=server_hostname)


class PlaintextFaultConnection:
    """Inject a reset at one operation on an actual accepted socket."""

    def __init__(self, connection, phase):
        self.connection, self.phase = connection, phase

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def recv(self, size):
        if self.phase == "receive":
            raise ConnectionResetError("Injected plaintext receive reset")
        return self.connection.recv(size)

    def sendall(self, data):
        if self.phase == "send":
            raise ConnectionResetError("Injected plaintext send reset")
        return self.connection.sendall(data)


class PlaintextFaultListener:
    def __init__(self, listener, phase):
        self.listener, self.phase = listener, phase

    def __getattr__(self, name):
        return getattr(self.listener, name)

    def accept(self):
        connection, address = self.listener.accept()
        return PlaintextFaultConnection(connection, self.phase), address


@unittest.skipUnless(OPENSSL, "An existing OpenSSL executable is required")
class TransportResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="Alliance reset fixtures ")
        cls.addClassCleanup(cls.fixtures.cleanup)
        cls.identity = Path(cls.fixtures.name) / "existing identity"
        with redirect_stdout(io.StringIO()):
            cls.profile, created = transport.prepare_identity(
                cls.identity, "127.0.0.1", 15001, Path(OPENSSL))
        if not created:
            raise AssertionError("Expected a fresh private test identity")

    def setUp(self):
        before = snapshot(self.identity)
        self.addCleanup(lambda: self.assertEqual(snapshot(self.identity), before))

    def connect_and_reset(self, endpoint):
        raw = socket.create_connection(endpoint, timeout=transport.TIMEOUT)
        try:
            abortive_close(raw)
        finally:
            raw.close()

    def faulty_peer(self, error, *, expect_rejection):
        details = {}
        with transport.loopback_peer(
                FailingContext(error), CHALLENGE,
                expect_rejection=expect_rejection, details=details) as (endpoint, received):
            with socket.create_connection(endpoint, timeout=transport.TIMEOUT):
                pass
        self.assertEqual(received, [])
        return details

    def client_factory(self, action):
        original = transport.tls_client_context

        def create(profile):
            return ClientContextProxy(original(profile), profile["server_address"], action)

        return create

    def plaintext_reset(self, phase, details):
        original_socket = socket.socket
        sockets_created = 0

        def make_socket(*args, **kwargs):
            nonlocal sockets_created
            sockets_created += 1
            connection = original_socket(*args, **kwargs)
            if sockets_created == 1:
                return PlaintextFaultListener(connection, phase)
            return connection

        with patch.object(transport.socket, "socket", side_effect=make_socket):
            with transport.loopback_peer(
                    None, CHALLENGE, plaintext=True, expect_rejection=True,
                    details=details) as (endpoint, received):
                with socket.create_connection(endpoint, timeout=transport.TIMEOUT) as raw:
                    if phase == "send":
                        raw.sendall(b"Client hello fixture")
        self.assertEqual(received, [])

    def assert_failed_wrong_ip(self, diagnostics):
        self.assertEqual(diagnostics["checks"], POSITIVE_CHECKS)
        cases = diagnostics["case_results"]
        self.assertEqual([case["id"] for case in cases], ["TLS1.2", "TLS1.3", "wrong-ip"])
        self.assertEqual([case["status"] for case in cases], ["passed", "passed", "failed"])
        self.assertIn("client_phase", cases[-1])
        self.assertIn("peer", cases[-1])
        self.assertIn("error", cases[-1])

    def test_real_abortive_close_during_positive_handshake_fails(self):
        details = {}
        with self.assertRaises(transport.TransportError):
            with transport.loopback_peer(
                    transport.server_context(self.identity), CHALLENGE,
                    details=details) as (endpoint, received):
                self.connect_and_reset(endpoint)
        self.assertEqual(received, [])
        self.assertEqual(details["phase"], "tls-handshake")
        self.assertEqual(details["status"], "failed")
        self.assertEqual(details["error"]["type"], "ConnectionResetError")

    def test_real_abortive_close_during_explicit_negative_handshake_is_recorded(self):
        details = {}
        with transport.loopback_peer(
                transport.server_context(self.identity), CHALLENGE,
                expect_rejection=True, details=details) as (endpoint, received):
            self.connect_and_reset(endpoint)
        self.assertEqual(received, [])
        self.assertEqual(details["phase"], "tls-handshake")
        self.assertEqual(details["status"], "rejection-close")
        self.assertEqual(details["error"]["type"], "ConnectionResetError")

    def test_server_ssl_error_cannot_silently_pass_positive_case(self):
        with self.assertRaises(transport.TransportError):
            self.faulty_peer(ssl.SSLError("Injected server handshake failure"),
                             expect_rejection=False)

    def test_explicit_negative_accepts_only_listed_handshake_disconnect_errors(self):
        for error in (ssl.SSLError("Injected rejection alert"),
                      ConnectionResetError("Injected peer reset"),
                      BrokenPipeError("Injected peer broken pipe")):
            with self.subTest(error=type(error).__name__):
                details = self.faulty_peer(error, expect_rejection=True)
                self.assertEqual(details["phase"], "tls-handshake")
                self.assertEqual(details["status"], "rejection-close")
                self.assertEqual(details["error"]["type"], type(error).__name__)

    def test_unexpected_server_failures_remain_fatal_for_negative_case(self):
        for error in (TimeoutError("Injected timeout"),
                      PermissionError("Injected permission error")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(transport.TransportError):
                    self.faulty_peer(error, expect_rejection=True)

    def test_negative_plaintext_send_reset_is_recorded_as_rejection_close(self):
        details = {}
        self.plaintext_reset("send", details)
        self.assertEqual(details["phase"], "plaintext-send")
        self.assertEqual(details["status"], "rejection-close")
        self.assertEqual(details["error"]["type"], "ConnectionResetError")

    def test_negative_plaintext_receive_reset_remains_fatal(self):
        details = {}
        with self.assertRaises(transport.TransportError):
            self.plaintext_reset("receive", details)
        self.assertEqual(details["phase"], "plaintext-receive")
        self.assertEqual(details["status"], "failed")
        self.assertEqual(details["error"]["type"], "ConnectionResetError")

    def test_negative_reset_after_successful_handshake_is_fatal_without_app_data(self):
        details = {}
        context = transport.server_context(self.identity)
        client = transport.tls_client_context(self.profile)
        # TLS1.2 completes on both endpoints before wrap_socket returns, avoiding
        # TLS1.3's post-handshake ticket write race at the boundary under test.
        context.maximum_version = client.maximum_version = ssl.TLSVersion.TLSv1_2
        with self.assertRaises(transport.TransportError):
            with transport.loopback_peer(
                    context, CHALLENGE, expect_rejection=True,
                    details=details) as (endpoint, received):
                with socket.create_connection(endpoint, timeout=transport.TIMEOUT) as raw:
                    with client.wrap_socket(raw, server_hostname="127.0.0.1") as secure:
                        abortive_close(secure)
        self.assertEqual(received, [])
        self.assertEqual(details["phase"], "receive-payload")
        self.assertEqual(details["status"], "failed")

    def test_negative_reset_after_received_application_data_is_fatal(self):
        details = {}
        client = transport.tls_client_context(self.profile)
        with self.assertRaises(transport.TransportError):
            with transport.loopback_peer(
                    transport.server_context(self.identity), CHALLENGE,
                    expect_rejection=True, details=details) as (endpoint, received):
                with socket.create_connection(endpoint, timeout=transport.TIMEOUT) as raw:
                    with client.wrap_socket(raw, server_hostname="127.0.0.1") as secure:
                        secure.sendall(CHALLENGE)
                        reply = bytearray()
                        while len(reply) < len(CHALLENGE):
                            chunk = secure.recv(len(CHALLENGE) - len(reply))
                            self.assertTrue(chunk, "Expected the actual application echo")
                            reply.extend(chunk)
                        self.assertEqual(bytes(reply), CHALLENGE)
                        abortive_close(secure)
        self.assertEqual(received, [CHALLENGE])
        self.assertEqual(details["phase"], "tls-shutdown")
        self.assertEqual(details["status"], "failed")

    def test_peer_cleanup_error_preserves_original_client_exception(self):
        original = RuntimeError("Original client failure must remain visible")
        details = {}
        with self.assertRaises(RuntimeError) as caught:
            with transport.loopback_peer(
                    FailingContext(PermissionError("Simultaneous peer failure")),
                    CHALLENGE, details=details) as (endpoint, received):
                with socket.create_connection(endpoint, timeout=transport.TIMEOUT):
                    raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(received, [])
        self.assertEqual(details["status"], "failed")
        self.assertEqual(details["error"]["type"], "PermissionError")

    def test_real_probe_reports_each_case_and_progress_after_clean_tls_shutdown(self):
        diagnostics, progress = {}, []
        passed = transport.run_probe(self.identity, copy.deepcopy(self.profile),
                                     diagnostics=diagnostics, progress=progress.append)
        self.assertEqual(passed, ALL_CHECKS)
        self.assertEqual(diagnostics["checks"], ALL_CHECKS)
        cases = diagnostics["case_results"]
        self.assertEqual([case["id"] for case in cases],
                         ["TLS1.2", "TLS1.3", "wrong-ip", "untrusted", "plaintext"])
        self.assertTrue(all(case["status"] == "passed" for case in cases))
        self.assertTrue(all("client_phase" in case and "peer" in case for case in cases))
        for case in cases[:2]:
            self.assertEqual(case["peer"]["status"], "complete")
            self.assertEqual(case["peer"]["phase"], "tls-shutdown")
        for case in cases[2:]:
            self.assertIn("rejection", case)
        self.assertEqual(len(progress), 10)
        for index in range(5):
            self.assertTrue(progress[index * 2].startswith("RUN "))
            self.assertTrue(progress[index * 2 + 1].startswith("PASS "))
        self.assertNotIn("PRIVATE KEY", json.dumps(diagnostics))
        self.assertNotIn("certificate_pem", json.dumps(diagnostics))

    def test_real_client_rejections_pass_when_peer_alerts_surface_as_windows_resets(self):
        original_server_context = transport.server_context
        translated = []

        class AlertAsResetContext:
            def __init__(self, context):
                self.context = context

            def __getattr__(self, name):
                return getattr(self.context, name)

            def wrap_socket(self, *args, **kwargs):
                try:
                    return self.context.wrap_socket(*args, **kwargs)
                except ssl.SSLError as error:
                    translated.append(type(error).__name__)
                    raise ConnectionResetError(10054, "Injected Winsock reset observation") from None

        def create(root):
            return AlertAsResetContext(original_server_context(root))

        diagnostics = {}
        with patch.object(transport, "server_context", side_effect=create):
            passed = transport.run_probe(self.identity, self.profile, diagnostics=diagnostics)
        self.assertEqual(passed, ALL_CHECKS)
        self.assertEqual(len(translated), 2)
        cases = diagnostics["case_results"]
        for case in cases[2:4]:
            self.assertEqual(case["status"], "passed")
            self.assertEqual(case["rejection"]["type"], "SSLCertVerificationError")
            self.assertEqual(case["peer"]["phase"], "tls-handshake")
            self.assertEqual(case["peer"]["status"], "rejection-close")
            self.assertEqual(case["peer"]["error"],
                             {"type": "ConnectionResetError", "errno": 10054})

    def test_client_reset_does_not_count_as_certificate_rejection(self):
        original = ConnectionResetError("Injected client-side reset")

        def reset_client(context, raw, actual_host):
            abortive_close(raw)
            raise original

        diagnostics, progress = {}, []
        with patch.object(transport, "tls_client_context",
                          side_effect=self.client_factory(reset_client)):
            with self.assertRaises(ConnectionResetError) as caught:
                transport.run_probe(self.identity, self.profile,
                                    diagnostics=diagnostics, progress=progress.append)
        self.assertIs(caught.exception, original)
        self.assert_failed_wrong_ip(diagnostics)
        self.assertIn("ConnectionResetError", json.dumps(diagnostics["case_results"][-1]))
        self.assertEqual(sum(item.startswith("PASS ") for item in progress), 2)
        self.assertEqual(sum(item.startswith("RUN ") for item in progress), 3)

    def test_cli_persists_partial_passes_failed_case_and_original_error(self):
        private_text = "PRIVATE KEY fixture text must not enter diagnostics"

        def reset_client(context, raw, actual_host):
            abortive_close(raw)
            raise ConnectionResetError(104, private_text)

        report = Path(self.fixtures.name) / "partial failure report.json"
        output, errors = io.StringIO(), io.StringIO()
        command = [str(ROOT / "tools/alliance_transport.py"),
                   "--identity-root", str(self.identity), "--openssl", OPENSSL,
                   "--report", str(report)]
        with patch.object(sys, "argv", command), redirect_stdout(output), redirect_stderr(errors):
            with patch.object(transport, "tls_client_context",
                              side_effect=self.client_factory(reset_client)):
                result = transport.main()
        self.assertEqual(result, 1)
        diagnostics = json.loads(report.read_text())
        self.assertEqual(diagnostics["status"], "failed")
        self.assertEqual(diagnostics["identity"], "reused")
        self.assertEqual(diagnostics["error"], "ConnectionResetError")
        self.assert_failed_wrong_ip(diagnostics)
        self.assertEqual(diagnostics["case_results"][-1]["error"],
                         {"type": "ConnectionResetError", "errno": 104})
        self.assertIn("RUN wrong-ip", output.getvalue())
        self.assertNotIn("PASS wrong-ip", output.getvalue())
        self.assertIn("ERROR: ConnectionResetError", errors.getvalue())
        combined = report.read_text() + output.getvalue() + errors.getvalue()
        self.assertNotIn(private_text, combined)
        self.assertNotIn("certificate_pem", combined)

    def test_unexpected_negative_handshake_success_fails_despite_peer_reset(self):
        def connect_with_actual_identity(context, raw, actual_host):
            secure = context.wrap_socket(raw, server_hostname=actual_host)
            layout = "HH" if os.name == "nt" else "ii"
            secure.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                              struct.pack(layout, 1, 0))
            return secure

        diagnostics = {}
        with patch.object(transport, "tls_client_context",
                          side_effect=self.client_factory(connect_with_actual_identity)):
            with self.assertRaisesRegex(transport.TransportError, "unexpectedly connected"):
                transport.run_probe(self.identity, self.profile, diagnostics=diagnostics)
        self.assert_failed_wrong_ip(diagnostics)


if __name__ == "__main__":
    unittest.main()
