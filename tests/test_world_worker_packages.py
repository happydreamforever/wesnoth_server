"""Pinned archive preparation checks; signature-process results are simulated.

These tests do not claim Windows execution, signature trust, or a native build.
Real archive/signature verification is recorded separately in delivery evidence.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import world_worker_packages as packages


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def package_row(name, version="1.0-1", depends=()):
    archive = ("fixture package " + name).encode()
    signature = ("fixture signature " + name).encode()
    return {
        "name": name,
        "version": version,
        "filename": name + "-" + version + "-any.pkg.tar.zst",
        "size": len(archive),
        "sha256": sha256(archive),
        "mtree_sha256": sha256(b"fixture package mtree " + name.encode()),
        "signature": {"size": len(signature), "sha256": sha256(signature)},
        "depends": list(depends),
        "provides": [],
        "conflicts": [],
        "replaces": [],
    }, archive, signature


class WorkerPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="world package paths ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.msys = self.root / "msys64"
        self.local = self.msys / "var/lib/pacman/local"
        self.local.mkdir(parents=True)
        (self.msys / "var/cache/pacman/pkg").mkdir(parents=True)
        (self.msys / "usr/bin").mkdir(parents=True)
        (self.msys / "usr/bin/pacman.exe").write_bytes(b"fixture pacman executable")
        self.cache = self.root / "reviewed cache"
        self.base, base_archive, base_signature = package_row("mingw-w64-x86_64-gcc", "16.2.0-3")
        self.first, first_archive, first_signature = package_row("mingw-w64-x86_64-SDL3", depends=[self.base["name"]])
        self.second, second_archive, second_signature = package_row("mingw-w64-x86_64-pango", depends=[self.first["name"]])
        self.artifacts = {}
        for row, archive, signature in ((self.base, base_archive, base_signature), (self.first, first_archive, first_signature), (self.second, second_archive, second_signature)):
            self.artifacts[row["filename"]] = archive
            self.artifacts[row["filename"] + ".sig"] = signature
        self.manifest = {
            "format": 1,
            "purpose": "wesnoth-world-worker-packages",
            "release": 1192624,
            "source": {"repository": "https://repo.msys2.org/mingw/mingw64/", "official_keyring": {
                "repository": "https://github.com/msys2/MSYS2-keyring",
                "commit": "a" * 40,
                "url": "https://raw.githubusercontent.com/msys2/MSYS2-keyring/" + "a" * 40 + "/msys2.gpg",
                "bytes": len(b"fixture public keyring"),
                "sha256": sha256(b"fixture public keyring"),
                "binary_bytes": len(b"fixture public keyring"),
                "binary_sha256": sha256(b"fixture public keyring"),
                "snapshot_signer": "A" * 40,
            }},
            "roots": [self.second["name"]],
            "baseline": [{"name": self.base["name"], "version": self.base["version"]}],
            "packages": [self.base, self.first, self.second],
        }
        self.manifest_path = self.root / "packages.json"
        self.write_manifest()
        self.add_installed(self.base["name"], self.base["version"], {"mingw64/bin/g++.exe": b"original compiler"})
        self.add_installed("bash", "5.3-1", {"usr/bin/bash.exe": b"original shell"})
        self.add_installed("mingw-w64-ucrt-x86_64-ninja", "1.13.2-1", {"ucrt64/bin/ninja.exe": b"original ninja"})

    def write_manifest(self, value=None):
        self.manifest_path.write_text(json.dumps(self.manifest if value is None else value), encoding="utf-8")
        return self.manifest_path

    def add_installed(self, name, version, files, provides=()):
        directory = self.local / (name + "-" + version)
        directory.mkdir()
        (directory / "desc").write_text("%NAME%\n" + name + "\n\n%VERSION%\n" + version + "\n\n%PROVIDES%\n" + "\n".join(provides) + "\n", encoding="utf-8")
        (directory / "files").write_text("%FILES%\n" + "\n".join(files) + "\n", encoding="utf-8")
        lines = ["#mtree", "/set type=file uid=0 gid=0 mode=644"]
        for relative, raw in files.items():
            path = self.msys / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            lines.append("./" + relative + " size=" + str(len(raw)) + " sha256digest=" + sha256(raw))
        (directory / "mtree").write_bytes(gzip.compress("\n".join(lines).encode()))
        return directory

    def seed_source_archives(self):
        source = self.msys / "var/cache/pacman/pkg"
        for filename, raw in self.artifacts.items():
            (source / filename).write_bytes(raw)
        return source

    def owned_cache(self):
        cache = packages.owned_cache(self.cache, sha256(self.manifest_path.read_bytes()))
        keyring = cache / packages.keyring_spec(self.manifest)["filename"]
        if not keyring.exists():
            keyring.write_bytes(b"fixture public keyring")
        binary = cache / (keyring.stem + "-binary.gpg")
        if not binary.exists():
            binary.write_bytes(b"fixture public keyring")
        return cache

    def valid_signature_result(self, fingerprint="A" * 40, digest="8"):
        status = "[GNUPG:] VALIDSIG " + fingerprint + " 2026-10-28 1793145600 0 4 0 1 " + digest + " 00\n"
        return subprocess.CompletedProcess(["gpgv-fixture"], 0, stdout=status.encode(), stderr=b"")

    def test_manifest_roundtrip_and_duplicate_json_keys_reject(self):
        packages.load_manifest(self.manifest_path)
        self.manifest_path.write_text('{"format":1,"format":1}', encoding="utf-8")
        with self.assertRaises(packages.BuildError):
            packages.load_manifest(self.manifest_path)

    def test_manifest_rejects_unsafe_name_archive_url_and_duplicate_package(self):
        mutations = [
            lambda row: row["packages"][1].update(name="../escape"),
            lambda row: row["packages"][1].update(filename="../escape.pkg.tar.zst"),
            lambda row: row["packages"][1].update(sha256="0" * 63),
            lambda row: row["source"].update(repository="https://example.invalid/packages/"),
            lambda row: row["packages"].append(deepcopy(row["packages"][1])),
            lambda row: row.update(release=1192623),
            lambda row: row["packages"][1]["signature"].update(size=0),
            lambda row: row["packages"][1]["signature"].update(signature={}),
            lambda row: row["packages"][1].update(depends=[{}]),
            lambda row: row.update(roots=[{}]),
            lambda row: row["packages"][1].update(depends=["mingw-w64-x86_64-missing"]),
            lambda row: row["packages"][1].update(mtree_sha256="not-a-pinned-hash"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = deepcopy(self.manifest)
                mutate(value)
                self.write_manifest(value)
                with self.assertRaises(packages.BuildError):
                    packages.load_manifest(self.manifest_path)

    def test_baseline_requires_exact_existing_version_and_presence(self):
        before = packages.installed_snapshot(self.msys)
        self.assertEqual({row["name"] for row in packages.check_installed(self.manifest, before)}, {self.first["name"], self.second["name"]})
        for change in ("different", "missing"):
            with self.subTest(change=change):
                current = deepcopy(before)
                if change == "missing":
                    del current[self.base["name"]]
                else:
                    current[self.base["name"]]["version"] = "17.0.0-1"
                with self.assertRaises(packages.BuildError):
                    packages.check_installed(self.manifest, current)

    def test_preexisting_approved_dependency_is_allowed_only_at_pinned_version(self):
        self.add_installed(self.first["name"], self.first["version"], {"mingw64/include/SDL3/SDL.h": b"fixture header"})
        snapshot = packages.installed_snapshot(self.msys)
        self.assertEqual([row["name"] for row in packages.check_installed(self.manifest, snapshot)], [self.second["name"]])
        snapshot[self.first["name"]]["version"] = "unexpected-1"
        with self.assertRaises(packages.BuildError):
            packages.check_installed(self.manifest, snapshot)

    def test_dependency_provider_conflict_preserves_original_package(self):
        before = packages.installed_snapshot(self.msys)
        for field in ("conflicts", "replaces"):
            with self.subTest(field=field):
                altered = deepcopy(self.manifest)
                altered["packages"][1][field] = [self.base["name"]]
                with self.assertRaises(packages.BuildError):
                    packages.check_installed(altered, before)
        self.assertEqual((self.msys / "mingw64/bin/g++.exe").read_bytes(), b"original compiler")

    def test_exact_source_cache_reuse_is_offline_and_preserves_sources(self):
        source = self.seed_source_archives()
        before = {path.name: path.read_bytes() for path in source.iterdir()}
        self.owned_cache()
        from tools import alliance_dependencies
        with patch.object(alliance_dependencies.urllib.request, "urlopen", side_effect=AssertionError("network is forbidden")), \
                patch.object(packages, "run_gpgv", return_value=self.valid_signature_result()) as signatures:
            with redirect_stdout(io.StringIO()):
                packages.prepare_cache(self.manifest, self.msys, self.cache, download=False)
                packages.prepare_cache(self.manifest, self.msys, self.cache, download=False)
        self.assertEqual(signatures.call_count, 6)
        self.assertEqual(before, {path.name: path.read_bytes() for path in source.iterdir()})
        for filename, raw in before.items():
            self.assertEqual((self.cache / filename).read_bytes(), raw)

    def test_corrupt_package_or_signature_is_preserved_without_download(self):
        self.seed_source_archives()
        self.owned_cache()
        for filename in (self.base["filename"], self.base["filename"] + ".sig"):
            with self.subTest(filename=filename):
                path = self.cache / filename
                path.write_bytes(b"retained corrupt evidence")
                with patch.object(packages, "ensure_artifact", side_effect=AssertionError("must not replace corrupt cache")):
                    with self.assertRaises(packages.BuildError):
                        packages.prepare_cache(self.manifest, self.msys, self.cache, download=True)
                self.assertEqual(path.read_bytes(), b"retained corrupt evidence")
                path.write_bytes(self.artifacts[filename])

    def test_missing_cache_in_offline_mode_never_opens_network(self):
        self.owned_cache()
        from tools import alliance_dependencies
        with patch.object(alliance_dependencies.urllib.request, "urlopen", side_effect=AssertionError("offline network")):
            with self.assertRaises((packages.BuildError, packages.PreparationError)):
                packages.prepare_cache(self.manifest, self.msys, self.cache, download=False)
        self.assertFalse((self.cache / self.base["filename"]).exists())

    def test_unowned_or_differently_bound_cache_is_not_repurposed(self):
        self.cache.mkdir()
        evidence = self.cache / "user-evidence.txt"
        evidence.write_bytes(b"retain")
        with self.assertRaises((packages.BuildError, FileNotFoundError)):
            self.owned_cache()
        self.assertEqual(evidence.read_bytes(), b"retain")
        marker = {"format": 1, "purpose": packages.PURPOSE, "release": 1192624, "manifest_sha256": "0" * 64}
        (self.cache / "owned.json").write_text(json.dumps(marker), encoding="utf-8")
        with self.assertRaises(packages.BuildError):
            self.owned_cache()
        self.assertEqual(json.loads((self.cache / "owned.json").read_text()), marker)

    def test_cache_operation_lock_is_preserved(self):
        self.owned_cache()
        operation = self.cache / "operation.lock"
        evidence = b'{"pid":4321,"nonce":"existing-operation","started_at":"fixture"}'
        operation.write_bytes(evidence)
        with self.assertRaisesRegex(packages.BuildError, "cache lock"):
            packages.execute(self.msys, self.manifest_path, self.cache)
        self.assertEqual(operation.read_bytes(), evidence)

    def test_existing_pacman_lock_is_never_removed(self):
        lock = self.msys / "var/lib/pacman/db.lck"
        lock.write_bytes(b"existing pacman operation")
        with self.assertRaisesRegex(packages.BuildError, "database lock"):
            packages.execute(self.msys, self.manifest_path, self.cache)
        self.assertEqual(lock.read_bytes(), b"existing pacman operation")
        self.assertFalse((self.cache / "operation.lock").exists())

    def test_signature_status_requires_one_strong_pinned_valid_signature(self):
        packages.validate_signature_status(self.valid_signature_result(), "A" * 40)
        wrong = [self.valid_signature_result("B" * 40), self.valid_signature_result(digest="2")]
        wrong.append(subprocess.CompletedProcess(["fixture"], 1, stdout=self.valid_signature_result().stdout, stderr=b"failed"))
        wrong.append(subprocess.CompletedProcess(["fixture"], 0, stdout=b"", stderr=b""))
        wrong.append(subprocess.CompletedProcess(["fixture"], 0, stdout=b"\xff", stderr=b""))
        wrong.append(subprocess.CompletedProcess(["fixture"], 0, stdout=self.valid_signature_result().stdout * 2, stderr=b""))
        for marker in ("BADSIG", "ERRSIG", "EXPSIG", "EXPKEYSIG", "REVKEYSIG", "NO_PUBKEY", "FAILURE"):
            wrong.append(subprocess.CompletedProcess(["fixture"], 0, stdout=self.valid_signature_result().stdout + ("[GNUPG:] " + marker + " fixture\n").encode(), stderr=b""))
        for index, result in enumerate(wrong):
            with self.subTest(index=index), self.assertRaises(packages.BuildError):
                packages.validate_signature_status(result, "A" * 40)

    def test_keyring_pin_refuses_wrong_origin_unpinned_commit_and_fingerprint(self):
        packages.keyring_spec(self.manifest)
        for field, value in (("url", "https://example.invalid/keyring"), ("commit", "main"), ("snapshot_signer", "unknown"), ("bytes", 0)):
            with self.subTest(field=field):
                manifest = deepcopy(self.manifest)
                manifest["source"]["official_keyring"][field] = value
                with self.assertRaises(packages.BuildError):
                    packages.keyring_spec(manifest)

    def test_bad_signature_retains_archives_and_does_not_accept_cache(self):
        self.seed_source_archives()
        self.owned_cache()
        with patch.object(packages, "run_gpgv", return_value=self.valid_signature_result("B" * 40)):
            with self.assertRaises(packages.BuildError):
                packages.prepare_cache(self.manifest, self.msys, self.cache, download=False)
        for filename, raw in self.artifacts.items():
            self.assertEqual((self.cache / filename).read_bytes(), raw)

    def test_signature_and_dearmor_commands_use_only_owned_public_inputs(self):
        self.owned_cache()
        home = self.cache / "empty-signature-home"
        home.mkdir()
        for name in ("gpg.exe", "gpgv.exe"):
            (self.msys / "usr/bin" / name).write_bytes(b"fixture executable")
        keyring = self.cache / packages.keyring_spec(self.manifest)["filename"]
        archive = self.cache / self.first["filename"]
        signature = self.cache / (self.first["filename"] + ".sig")
        with patch.object(packages, "cygpath", side_effect=lambda msys, path: Path(path).as_posix()), \
                patch.object(packages.subprocess, "run", return_value=self.valid_signature_result()) as runner:
            packages.run_gpgv(self.msys, keyring, signature, archive, home)
            command = runner.call_args.args[0]
            self.assertEqual(Path(command[0]).name, "gpgv.exe")
            self.assertEqual(command[-2:], [str(signature), str(archive)])
            self.assertEqual(command[command.index("--homedir") + 1], str(home))
            self.assertEqual(command[command.index("--keyring") + 1], str(keyring))
            self.assertNotIn("GNUPGHOME", runner.call_args.kwargs["env"])
            self.assertEqual(runner.call_args.kwargs["env"]["PATH"], str(self.msys / "usr/bin"))
            packages.run_dearmor(self.msys, keyring, home)
            command = runner.call_args.args[0]
            self.assertEqual(Path(command[0]).name, "gpg.exe")
            self.assertIn("--no-options", command)
            self.assertIn("--dearmor", command)
            self.assertNotIn("--import", command)
            self.assertNotIn("--recv-keys", command)
            self.assertEqual(runner.call_args.kwargs["input"], b"fixture public keyring")

    def test_binary_keyring_requires_exact_decoded_hash_and_preserves_corruption(self):
        self.owned_cache()
        binary = self.cache / ("msys2-keyring-" + "a" * 40 + "-binary.gpg")
        binary.unlink()
        home = self.cache / "empty-signature-home"
        home.mkdir()
        incorrect = subprocess.CompletedProcess(["fixture"], 0, stdout=b"unreviewed binary key", stderr=b"")
        with patch.object(packages, "run_dearmor", return_value=incorrect):
            with self.assertRaises(packages.BuildError):
                packages.binary_keyring(self.manifest, self.msys, self.cache, home)
        self.assertFalse(binary.exists())
        correct = subprocess.CompletedProcess(["fixture"], 0, stdout=b"fixture public keyring", stderr=b"")
        with patch.object(packages, "run_dearmor", return_value=correct):
            self.assertEqual(packages.binary_keyring(self.manifest, self.msys, self.cache, home), binary)
        binary.write_bytes(b"retained unexpected binary")
        with patch.object(packages, "run_dearmor", side_effect=AssertionError("must not replace existing binary")):
            with self.assertRaises(packages.BuildError):
                packages.binary_keyring(self.manifest, self.msys, self.cache, home)
        self.assertEqual(binary.read_bytes(), b"retained unexpected binary")

    def test_interrupted_source_copy_retains_scratch_and_can_retry(self):
        source = self.seed_source_archives()
        self.owned_cache()
        spec = next(packages.artifact_specs(self.manifest))
        original = source / spec["filename"]
        destination = self.cache / spec["filename"]

        def interrupted(incoming, outgoing, *args):
            outgoing.write(incoming.read(5))
            raise OSError("fixture interrupted copy")

        with patch.object(packages.shutil, "copyfileobj", side_effect=interrupted):
            with self.assertRaises(OSError):
                packages.copy_artifact(original, destination, spec)
        self.assertFalse(destination.exists())
        retained = [path for path in self.cache.iterdir() if ".copying-" in path.name]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), original.read_bytes()[:5])
        packages.copy_artifact(original, destination, spec)
        packages.verify_artifact(destination, spec)
        self.assertTrue(retained[0].exists())
        self.assertEqual(destination.stat().st_nlink, 1)

    def test_interrupted_download_never_publishes_partial_archive(self):
        self.owned_cache()
        spec = next(packages.artifact_specs(self.manifest))
        destination = self.cache / spec["filename"]

        def interrupted(path, artifact, download):
            Path(path).write_bytes(b"partial network response")
            raise packages.PreparationError("fixture interrupted download")

        with patch.object(packages, "ensure_artifact", side_effect=interrupted):
            with self.assertRaises(packages.PreparationError):
                packages.prepare_download(destination, spec, True)
        self.assertFalse(destination.exists())
        retained = [path for path in self.cache.iterdir() if path.is_file() and path.read_bytes() == b"partial network response"]
        self.assertEqual(len(retained), 1)

        def completed(path, artifact, download):
            self.assertTrue(download)
            Path(path).write_bytes(self.artifacts[artifact["filename"]])

        with patch.object(packages, "ensure_artifact", side_effect=completed):
            packages.prepare_download(destination, spec, True)
        packages.verify_artifact(destination, spec)
        self.assertTrue(retained[0].exists())

    def test_concurrent_cache_publication_does_not_overwrite_existing_file(self):
        source = self.seed_source_archives()
        self.owned_cache()
        spec = next(packages.artifact_specs(self.manifest))
        original = source / spec["filename"]
        destination = self.cache / spec["filename"]

        def racing_copy(incoming, outgoing, *args):
            outgoing.write(incoming.read())
            destination.write_bytes(b"concurrent retained file")

        with patch.object(packages.shutil, "copyfileobj", side_effect=racing_copy):
            with self.assertRaises((packages.BuildError, FileExistsError)):
                packages.copy_artifact(original, destination, spec)
        self.assertEqual(destination.read_bytes(), b"concurrent retained file")

    def test_successful_cache_workflow_does_not_modify_original_msys(self):
        self.seed_source_archives()
        self.owned_cache()
        before = {path.relative_to(self.msys).as_posix(): path.read_bytes() for path in self.msys.rglob("*") if path.is_file()}
        report_path = self.root / "public-report.json"
        with patch.object(packages, "run_gpgv", return_value=self.valid_signature_result()), redirect_stdout(io.StringIO()):
            report = packages.execute(self.msys, self.manifest_path, self.cache, report_path=report_path)
        self.assertEqual(report["status"], "cache_verified")
        self.assertEqual(report["packages_installed"], 0)
        self.assertFalse(report["repository_refreshed"])
        self.assertFalse(report["keyring_changed"])
        self.assertFalse(report["services_started"])
        self.assertEqual(before, {path.relative_to(self.msys).as_posix(): path.read_bytes() for path in self.msys.rglob("*") if path.is_file()})
        self.assertEqual(json.loads(report_path.read_text()), report)
        self.assertFalse((self.cache / "operation.lock").exists())

    def test_concurrent_installed_metadata_change_stops_after_cache_check(self):
        self.owned_cache()
        original = packages.installed_snapshot(self.msys)
        altered = deepcopy(original)
        altered["bash"]["metadata"] = {"desc": "changed"}
        with patch.object(packages, "installed_snapshot", side_effect=[original, altered]), \
                patch.object(packages, "prepare_cache"):
            with self.assertRaises(packages.BuildError):
                packages.execute(self.msys, self.manifest_path, self.cache)
        attempts = list(self.cache.glob("attempt-*/result.json"))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(attempts[0].read_text())["status"], "stopped")
        self.assertFalse((self.cache / "operation.lock").exists())


if __name__ == "__main__":
    unittest.main()
