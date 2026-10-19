"""Real OpenSSL identities and Python TLS; no database or game process is used."""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/alliance_transport.py"
spec = importlib.util.spec_from_file_location("alliance_transport", MODULE)
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
OPENSSL = shutil.which("openssl")
MANAGED = {"owner.json", "openssl.cnf", "server-key.pem", "server-cert.pem",
           "public-profile.json", "prepared.json"}


def snapshot(root):
    """Include bytes, permissions and link targets without following a link."""
    if not root.exists() and not root.is_symlink():
        return None
    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        mode = path.lstat().st_mode
        content = os.readlink(path) if stat.S_ISLNK(mode) else (
            path.read_bytes() if stat.S_ISREG(mode) else None)
        result[str(path.relative_to(root))] = (mode, content)
    return result


@unittest.skipUnless(OPENSSL, "An existing OpenSSL executable is required")
class TransportIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="alliance TLS fixtures ")
        cls.addClassCleanup(cls.fixtures.cleanup)
        cls.base = Path(cls.fixtures.name) / "original identity"
        cls.other = Path(cls.fixtures.name) / "different identity"
        with redirect_stdout(io.StringIO()):
            cls.profile, created = transport.prepare_identity(
                cls.base, "127.0.0.1", 15001, Path(OPENSSL))
            cls.other_profile, other_created = transport.prepare_identity(
                cls.other, "127.0.0.2", 15001, Path(OPENSSL))
        if not created or not other_created:
            raise AssertionError("Fresh fixture identities were not created")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance TLS case ")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.identity = self.directory / "owned identity"
        shutil.copytree(self.base, self.identity)

    def prepare(self, root=None, address="127.0.0.1", port=15001):
        with redirect_stdout(io.StringIO()):
            return transport.prepare_identity(
                root or self.identity, address, port, Path(OPENSSL))

    def assert_rejected_preserved(self, root=None):
        root = root or self.identity
        before = snapshot(root)
        with self.assertRaises(transport.TransportError):
            self.prepare(root)
        self.assertEqual(snapshot(root), before)

    def rebind(self, certificate=None):
        """Model modified stored hashes; TLS must independently check semantics."""
        if certificate is not None:
            pem = certificate.decode("ascii")
            (self.identity / "server-cert.pem").write_bytes(certificate)
            profile = copy.deepcopy(self.profile)
            profile["certificate_pem"] = pem
            profile["certificate_sha256"] = hashlib.sha256(
                ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
            (self.identity / "public-profile.json").write_text(json.dumps(profile))
        files = {name: hashlib.sha256((self.identity / name).read_bytes()).hexdigest()
                 for name in MANAGED - {"prepared.json"}}
        (self.identity / "prepared.json").write_text(json.dumps({
            "format": 1, "purpose": "wesnoth-alliance-transport", "files": files}))

    def openssl(self, *args, cwd=None):
        result = subprocess.run([OPENSSL, *map(str, args)], cwd=cwd,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def test_public_profile_is_exact_public_certificate_and_no_private_material(self):
        self.assertEqual({path.name for path in self.identity.iterdir()}, MANAGED)
        self.assertEqual(set(self.profile), {"format", "protocol", "server_address", "port",
                                            "minimum_tls", "certificate_pem", "certificate_sha256"})
        self.assertEqual(self.profile["protocol"], "wesnoth-alliance-tls")
        self.assertEqual(self.profile["minimum_tls"], "1.2")
        self.assertEqual(self.profile["server_address"], "127.0.0.1")
        self.assertEqual(self.profile["certificate_pem"].encode("ascii"),
                         (self.identity / "server-cert.pem").read_bytes())
        self.assertEqual(hashlib.sha256(ssl.PEM_cert_to_DER_cert(
            self.profile["certificate_pem"])).hexdigest(), self.profile["certificate_sha256"])
        self.assertNotIn("PRIVATE KEY", json.dumps(self.profile))
        self.assertNotIn("server-key.pem", json.dumps(self.profile))

    def test_identity_has_single_ip_san_and_server_leaf_extensions(self):
        text = self.openssl("x509", "-in", self.identity / "server-cert.pem",
                            "-noout", "-text").decode("ascii")
        self.assertIn("Public-Key: (3072 bit)", text)
        self.assertIn("CA:FALSE", text)
        self.assertIn("TLS Web Server Authentication", text)
        self.assertNotIn("TLS Web Client Authentication", text)
        self.assertEqual(text.count("IP Address:"), 1)
        self.assertIn("IP Address:127.0.0.1", text)
        self.assertNotIn("DNS:", text)
        dates = self.openssl("x509", "-in", self.identity / "server-cert.pem",
                             "-noout", "-dates").decode("ascii").splitlines()
        starts, ends = [ssl.cert_time_to_seconds(line.split("=", 1)[1]) for line in dates]
        self.assertEqual(ends - starts, 365 * 24 * 60 * 60)

    @unittest.skipIf(os.name == "nt", "POSIX permissions only; Windows ACLs require Windows evidence")
    def test_private_directory_and_all_files_have_restricted_posix_permissions(self):
        self.assertEqual(stat.S_IMODE(self.identity.stat().st_mode), 0o700)
        for path in self.identity.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_reuse_verifies_without_key_generation_or_any_file_changes(self):
        before = snapshot(self.identity)
        actual = transport.openssl_run

        def version_only(openssl, args, cwd=None):
            self.assertEqual(args, ["version"], "Existing identity must not regenerate")
            return actual(openssl, args, cwd)

        with patch.object(transport, "openssl_run", side_effect=version_only):
            profile, created = self.prepare()
        self.assertFalse(created)
        self.assertEqual(profile, self.profile)
        self.assertEqual(transport.verify_identity(self.identity, "127.0.0.1", 15001), profile)
        self.assertEqual(snapshot(self.identity), before)

    def test_changed_address_or_port_does_not_replace_existing_identity(self):
        before = snapshot(self.identity)
        for address, port in (("127.0.0.2", 15001), ("127.0.0.1", 15002)):
            with self.subTest(address=address, port=port):
                with self.assertRaises(transport.TransportError):
                    self.prepare(address=address, port=port)
                self.assertEqual(snapshot(self.identity), before)

    def test_every_managed_file_tamper_is_rejected_without_further_mutation(self):
        for name in sorted(MANAGED):
            with self.subTest(file=name):
                path = self.identity / name
                original = path.read_bytes()
                path.write_bytes(original + b"\nmodified")
                self.assert_rejected_preserved()
                path.write_bytes(original)

    def test_incomplete_and_additional_file_states_are_preserved(self):
        for name in sorted(MANAGED):
            with self.subTest(missing=name):
                path = self.identity / name
                content = path.read_bytes()
                path.unlink()
                self.assert_rejected_preserved()
                path.write_bytes(content)
                path.chmod(0o600)
        extra = self.identity / "operator-note.txt"
        extra.write_bytes(b"Preserve this note")
        self.assert_rejected_preserved()

    def test_unowned_existing_directory_and_bad_owner_are_preserved(self):
        unowned = self.directory / "unowned"
        unowned.mkdir()
        self.assert_rejected_preserved(unowned)
        sentinel = unowned / "sentinel"
        sentinel.write_bytes(b"keep")
        self.assert_rejected_preserved(unowned)
        owner = json.loads((self.identity / "owner.json").read_text())
        owner["purpose"] = "unrelated-project"
        (self.identity / "owner.json").write_text(json.dumps(owner))
        self.rebind()
        self.assert_rejected_preserved()

    def test_symlink_roots_parents_and_managed_files_are_rejected(self):
        link = self.directory / "linked identity"
        link.symlink_to(self.identity, target_is_directory=True)
        before = snapshot(self.identity)
        with self.assertRaises(transport.TransportError):
            self.prepare(link)
        self.assertEqual(snapshot(self.identity), before)
        parent_link = self.directory / "linked parent"
        parent_link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(transport.TransportError):
            self.prepare(parent_link / "fresh child")
        self.assertFalse((self.directory / "fresh child").exists())
        path = self.identity / "server-key.pem"
        path.unlink()
        path.symlink_to(self.base / "server-key.pem")
        self.assert_rejected_preserved()

    def test_hardlinked_private_key_is_rejected_without_affecting_target(self):
        path = self.identity / "server-key.pem"
        target = self.directory / "key outside identity"
        path.rename(target)
        os.link(target, path)
        before = target.read_bytes()
        self.assert_rejected_preserved()
        self.assertEqual(target.read_bytes(), before)

    def test_invalid_addresses_and_ports_never_create_identity(self):
        bad_addresses = (None, 123, "", "localhost", "https://127.0.0.1", "127.0.0.1:15001",
                         "[::1]", "fe80::1%eth0", " 127.0.0.1", "１２７.0.0.1", "☃",
                         "0.0.0.0", "::", "224.0.0.1", "ff02::1", "255.255.255.255")
        root = self.directory / "must not exist"
        for host in bad_addresses:
            with self.subTest(address=host):
                with self.assertRaises(transport.TransportError):
                    self.prepare(root, address=host)
                self.assertFalse(root.exists())
        for port in (None, True, False, 0, -1, 65536, "15001", 15001.0):
            with self.subTest(port=port):
                with self.assertRaises(transport.TransportError):
                    self.prepare(root, port=port)
                self.assertFalse(root.exists())

    def test_ipv6_address_is_canonicalized_in_a_real_certificate(self):
        root = self.directory / "IPv6 identity"
        profile, created = self.prepare(root, address="0:0:0:0:0:0:0:1")
        self.assertTrue(created)
        self.assertEqual(profile["server_address"], "::1")
        self.assertEqual(transport.verify_identity(root, "::1", 15001), profile)

    def test_wrong_openssl_version_prevents_creation(self):
        root = self.directory / "wrong version"
        with self.assertRaises(transport.TransportError):
            transport.prepare_identity(root, "127.0.0.1", 15001, Path(OPENSSL), "0.0.0")
        self.assertFalse(root.exists())

    def test_wrong_openssl_version_rejects_reuse_without_changing_identity(self):
        before = snapshot(self.identity)
        with self.assertRaises(transport.TransportError):
            transport.prepare_identity(self.identity, "127.0.0.1", 15001, Path(OPENSSL), "0.0.0")
        self.assertEqual(snapshot(self.identity), before)

    def test_openssl_subprocess_ignores_global_configuration_overrides(self):
        names = ("OPENSSL_CONF", "OPENSSL_CONF_INCLUDE", "OPENSSL_MODULES", "OPENSSL_ENGINES",
                 "OPENSSL_TEST_LIBCTX", "ALLIANCE_TEST_PRESERVED")
        injected = {name: "test-global-override" for name in names}
        code = "import json,os; print(json.dumps({name:os.environ.get(name) for name in " + repr(names) + "}))"
        with patch.dict(os.environ, injected):
            output = transport.openssl_run(Path(sys.executable), ["-I", "-c", code])
            self.assertEqual({name: os.environ[name] for name in names}, injected)
        child = json.loads(output)
        self.assertEqual(child.pop("OPENSSL_CONF"), os.devnull)
        self.assertEqual(child.pop("ALLIANCE_TEST_PRESERVED"), "test-global-override")
        self.assertTrue(all(value is None for value in child.values()))

    def test_generation_failure_preserves_incomplete_identity_and_never_retries(self):
        root = self.directory / "interrupted"
        actual = transport.openssl_run

        def interrupted(openssl, args, cwd=None):
            if args[0] == "req":
                raise transport.TransportError("Injected generation interruption")
            return actual(openssl, args, cwd)

        with patch.object(transport, "openssl_run", side_effect=interrupted):
            with self.assertRaises(transport.TransportError):
                self.prepare(root)
        self.assertEqual({path.name for path in root.iterdir()}, {"owner.json", "openssl.cnf"})
        self.assert_rejected_preserved(root)

    def test_crlf_certificate_generation_preserves_raw_bytes_and_canonical_public_profile(self):
        root = self.directory / "CRLF certificate"
        actual = transport.openssl_run

        def crlf_output(openssl, args, cwd=None):
            output = actual(openssl, args, cwd)
            if args[0] == "req":
                certificate = Path(cwd) / "server-cert.pem"
                certificate.write_bytes(certificate.read_bytes().replace(b"\n", b"\r\n"))
            return output

        with patch.object(transport, "openssl_run", side_effect=crlf_output):
            profile, created = self.prepare(root)
        self.assertTrue(created)
        self.assertNotIn("\r", profile["certificate_pem"])
        self.assertIn(b"\r\n", (root / "server-cert.pem").read_bytes())
        before = snapshot(root)
        self.assertEqual(self.prepare(root), (profile, False))
        self.assertEqual(snapshot(root), before)

    def test_duplicate_json_fields_and_noninteger_receipt_format_are_rejected(self):
        path = self.identity / "public-profile.json"
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"format": 1', b'"format": 1, "format": 1'))
        self.rebind()
        self.assert_rejected_preserved()
        path.write_bytes(original)
        self.rebind()
        receipt_path = self.identity / "prepared.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["format"] = True
        receipt_path.write_text(json.dumps(receipt))
        self.assert_rejected_preserved()

    def test_client_context_requires_verification_and_only_provisioned_trust(self):
        context = transport.tls_client_context(self.profile)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.cert_store_stats()["x509"], 1)
        self.assertTrue(context.verify_flags & ssl.VERIFY_X509_STRICT)

    def test_public_profile_policy_encoding_and_fingerprint_fail_closed(self):
        changes = ({"format": True}, {"format": 2}, {"protocol": "http"},
                   {"minimum_tls": "1.1"}, {"server_address": "localhost"},
                   {"server_address": "0:0:0:0:0:0:0:1"}, {"port": True},
                   {"certificate_sha256": "0" * 64}, {"certificate_pem": "PRIVATE KEY"},
                   {"certificate_pem": self.profile["certificate_pem"] * 2},
                   {"unexpected": "field"})
        for changeset in changes:
            with self.subTest(changes=list(changeset)):
                profile = {**self.profile, **changeset}
                with self.assertRaises(transport.TransportError):
                    transport.tls_client_context(profile)

    def test_real_loopback_probe_proves_both_tls_versions_and_fail_closed_cases(self):
        before = snapshot(self.identity)
        passed = transport.run_probe(self.identity, copy.deepcopy(self.profile))
        self.assertEqual(passed, [
            "TLS1.2 trusted numeric-IP identity and encrypted payload",
            "TLS1.3 trusted numeric-IP identity and encrypted payload",
            "wrong-ip rejected before application data",
            "untrusted rejected before application data",
            "plaintext rejected before application data",
        ])
        self.assertEqual(snapshot(self.identity), before)

    def test_probe_rejects_different_supplied_profile_before_opening_socket(self):
        profile = {**self.profile, "port": 15002}
        with patch.object(transport.socket, "socket", side_effect=AssertionError("Socket must remain closed")):
            with self.assertRaises(transport.TransportError):
                transport.run_probe(self.identity, profile)

    def test_key_mismatch_is_rejected_even_after_inventory_is_rewritten(self):
        (self.identity / "server-key.pem").write_bytes((self.other / "server-key.pem").read_bytes())
        self.rebind()
        self.assert_rejected_preserved()

    def test_wrong_ip_certificate_is_rejected_even_with_matching_key_and_rewritten_inventory(self):
        (self.identity / "server-key.pem").write_bytes((self.other / "server-key.pem").read_bytes())
        self.rebind((self.other / "server-cert.pem").read_bytes())
        self.assert_rejected_preserved()

    def test_expired_certificate_is_rejected_even_after_all_stored_hashes_are_rewritten(self):
        fixture = self.directory / "expired certificate fixture"
        fixture.mkdir()
        (fixture / "index.txt").write_text("")
        (fixture / "serial").write_text("01\n")
        (fixture / "ca.cnf").write_text(
            "[ca]\ndefault_ca=local\n[local]\ndatabase=index.txt\nserial=serial\n"
            "new_certs_dir=.\ndefault_md=sha256\npolicy=any_name\n"
            "[any_name]\ncommonName=supplied\n")
        self.openssl("req", "-new", "-key", self.identity / "server-key.pem", "-out", "request.pem",
                     "-config", self.identity / "openssl.cnf", cwd=fixture)
        self.openssl("ca", "-batch", "-selfsign", "-keyfile", self.identity / "server-key.pem",
                     "-in", "request.pem", "-out", "expired.pem", "-config", "ca.cnf",
                     "-extfile", self.identity / "openssl.cnf", "-extensions", "server",
                     "-startdate", "20000101000000Z", "-enddate", "20010101000000Z", cwd=fixture)
        certificate = self.openssl("x509", "-in", fixture / "expired.pem")
        self.rebind(certificate)
        self.assert_rejected_preserved()

    def test_cli_reuse_saves_public_report_and_preserves_existing_report(self):
        report = self.directory / "public report.json"
        command = [sys.executable, "-I", "-B", str(MODULE), "--identity-root", str(self.identity),
                   "--openssl", OPENSSL, "--report", str(report)]
        before = snapshot(self.identity)
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(report.read_text())
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["identity"], "reused")
        self.assertEqual(data["port"], 15001)
        self.assertEqual(len(data["checks"]), 5)
        output = result.stdout + result.stderr + report.read_text()
        self.assertNotIn("PRIVATE KEY", output)
        self.assertNotIn("certificate_pem", output)
        saved_report = report.read_bytes()
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report.read_bytes(), saved_report)
        self.assertEqual(snapshot(self.identity), before)

    def test_cli_failure_keeps_identity_and_saves_failure_report(self):
        (self.identity / "prepared.json").write_text("[]")
        before = snapshot(self.identity)
        report = self.directory / "failure.json"
        result = subprocess.run([sys.executable, "-I", "-B", str(MODULE),
            "--identity-root", str(self.identity), "--openssl", OPENSSL, "--report", str(report)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(report.read_text())["status"], "failed")
        self.assertNotIn("PRIVATE KEY", result.stdout + result.stderr + report.read_text())
        self.assertEqual(snapshot(self.identity), before)


if __name__ == "__main__":
    unittest.main()
