"""Real expired-leaf semantics with OpenSSL 3.5+; no production identity access."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_expiry_fixture", ROOT / "tools/test_alliance_native.py")
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


class ExpiryFailureTests(unittest.TestCase):
    def test_failed_signing_leaves_no_success_certificate_or_ca_state(self):
        with tempfile.TemporaryDirectory(prefix="expired fixture failure ") as temporary:
            root = Path(temporary)
            identity = root / "identity"
            identity.mkdir()
            sentinel = identity / "sentinel"
            sentinel.write_bytes(b"unchanged identity")
            calls = []

            def failed_signer(openssl, arguments, *, cwd):
                calls.append(arguments[0])
                if arguments[0] == "req":
                    (cwd / "request.pem").write_bytes(b"request sentinel")
                    return b""
                raise F.T.TransportError("OpenSSL x509 failed (exit 1); identity files preserved.")

            with mock.patch.object(F.T, "openssl_run", side_effect=failed_signer):
                with self.assertRaises(F.T.TransportError):
                    F.expired_certificate(root, identity, Path("unused-openssl"))
            self.assertEqual(calls, ["req", "x509"])
            self.assertEqual({p.name for p in (root / "expired").iterdir()}, {"request.pem"})
            self.assertEqual(sentinel.read_bytes(), b"unchanged identity")

    def test_existing_fixture_directory_is_preserved_and_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "expired").mkdir()
            sentinel = root / "expired/public.pem"
            sentinel.write_bytes(b"old evidence")
            with mock.patch.object(F.T, "openssl_run") as invoke:
                with self.assertRaises(FileExistsError):
                    F.expired_certificate(root, root / "identity", Path("unused-openssl"))
                invoke.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"old evidence")


class RealExpiredCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get("ALLIANCE_TEST_OPENSSL") or shutil.which("openssl")
        if not selected:
            raise unittest.SkipTest("OpenSSL unavailable")
        cls.openssl = Path(selected)
        help_result = subprocess.run([str(cls.openssl), "x509", "-help"], capture_output=True, timeout=10)
        if b"-not_before" not in help_result.stdout + help_result.stderr:
            raise unittest.SkipTest("Use the pinned verification container: OpenSSL 3.5+ date options required")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="Alliance expired paths with spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identity = self.root / "disposable identity"
        F.T.prepare_identity(self.identity, "127.0.0.1", 15001, self.openssl)
        self.before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.identity.iterdir()}
        self.certificate, self.pem = F.expired_certificate(self.root, self.identity, self.openssl)

    def tearDown(self):
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.identity.iterdir()}
        self.assertEqual(self.before, after)
        self.assertEqual({p.name for p in (self.root / "expired").iterdir()}, {"request.pem", "public.pem"})

    def invoke(self, *arguments):
        environment = os.environ.copy()
        environment["OPENSSL_CONF"] = os.devnull
        return subprocess.run([str(self.openssl), *map(str, arguments)], env=environment,
                              capture_output=True, text=True, timeout=10)

    def verify(self, *options):
        return self.invoke("verify", "-no-CAfile", "-no-CApath", "-no-CAstore",
                           "-trusted", self.certificate, "-check_ss_sig", *options, self.certificate)

    def test_leaf_fails_only_time_when_trusted_for_correct_server_ip(self):
        expired = self.verify("-purpose", "sslserver", "-verify_ip", "127.0.0.1")
        self.assertNotEqual(expired.returncode, 0)
        self.assertIn("error 10 at 0 depth lookup: certificate has expired", expired.stderr)
        without_time = self.verify("-purpose", "sslserver", "-verify_ip", "127.0.0.1", "-no_check_time")
        self.assertEqual(without_time.returncode, 0, without_time.stderr)

    def test_leaf_keeps_ip_and_server_purpose_restrictions(self):
        wrong_ip = self.verify("-no_check_time", "-purpose", "sslserver", "-verify_ip", "127.0.0.2")
        self.assertNotEqual(wrong_ip.returncode, 0)
        self.assertIn("IP address mismatch", wrong_ip.stderr)
        wrong_purpose = self.verify("-no_check_time", "-purpose", "sslclient")
        self.assertNotEqual(wrong_purpose.returncode, 0)
        self.assertIn("unsuitable certificate purpose", wrong_purpose.stderr)

    def test_dates_key_and_extensions_are_preserved_without_ca_database(self):
        details = self.invoke("x509", "-in", self.certificate, "-noout", "-dates", "-serial", "-text")
        self.assertEqual(details.returncode, 0, details.stderr)
        for expected in ("notBefore=Jan  1 00:00:00 2000 GMT", "notAfter=Jan  1 00:00:00 2001 GMT",
                         "serial=01", "CA:FALSE", "TLS Web Server Authentication",
                         "Digital Signature, Key Encipherment", "IP Address:127.0.0.1"):
            self.assertIn(expected, details.stdout)
        new_key = self.invoke("x509", "-in", self.certificate, "-pubkey", "-noout")
        old_key = self.invoke("x509", "-in", self.identity / "server-cert.pem", "-pubkey", "-noout")
        self.assertEqual(new_key.returncode, 0)
        self.assertEqual(old_key.returncode, 0)
        self.assertEqual(new_key.stdout, old_key.stdout)
        self.assertEqual(self.certificate.read_text(), self.pem)


if __name__ == "__main__":
    unittest.main()
