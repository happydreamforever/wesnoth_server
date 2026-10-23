"""Artifact preservation tests and executable PowerShell helper simulations."""
from __future__ import annotations

import hashlib
import http.client
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alliance_dependencies", ROOT / "tools/alliance_dependencies.py")
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"


def artifact(filename="fixture.whl", content=b"test wheel"):
    return {"filename": filename, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "url": "https://files.pythonhosted.org/fixture"}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance paths with spaces ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_offline_missing_never_opens_network(self):
        with patch.object(deps.urllib.request, "urlopen", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(deps.PreparationError, "missing"):
                deps.ensure_artifact(self.root / "missing.whl", artifact(), False)

    def test_offline_existing_cache_is_verified(self):
        path = self.root / "cached.whl"
        path.write_bytes(b"test wheel")
        with patch.object(deps.urllib.request, "urlopen", side_effect=AssertionError("network")):
            deps.ensure_artifact(path, artifact(), False)
        self.assertEqual(path.read_bytes(), b"test wheel")

    def test_corrupt_cache_is_preserved_even_with_download(self):
        path = self.root / "cached.whl"
        path.write_bytes(b"user evidence")
        with patch.object(deps.urllib.request, "urlopen", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(deps.PreparationError, "preserved"):
                deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(path.read_bytes(), b"user evidence")

    def test_download_verified_before_publication(self):
        path = self.root / "wheel.whl"
        with patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO(b"test wheel")):
            deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(path.read_bytes(), b"test wheel")
        self.assertEqual(list(self.root.glob("*.download-*")), [])

    def test_wrong_download_hash_rejected_without_final_file(self):
        path = self.root / "wheel.whl"
        with patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO(b"fail wheel")):
            with self.assertRaises(deps.PreparationError):
                deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oversize_download_rejected(self):
        with patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO(b"way too much data")):
            with self.assertRaisesRegex(deps.PreparationError, "exceeds"):
                deps.ensure_artifact(self.root / "wheel.whl", artifact(), True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_connection_timeout_retries_then_verifies(self):
        failure = OSError("fixture Windows timeout")
        failure.winerror = 10060
        path = self.root / "wheel.whl"
        with patch.object(deps.urllib.request, "urlopen", side_effect=[
                urllib.error.URLError(failure), io.BytesIO(b"test wheel")]) as network, \
                patch.object(deps.time, "sleep") as sleep:
            deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(network.call_count, 2)
        sleep.assert_called_once_with(2)
        self.assertEqual(path.read_bytes(), b"test wheel")
        self.assertEqual(list(self.root.glob("*.download-*")), [])

    def test_read_failure_restarts_only_current_file(self):
        class InterruptedStream(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise ConnectionResetError("fixture interrupted body")
                return super().read(4)
        path = self.root / "wheel.whl"
        previous = self.root / "already-verified.whl"
        previous.write_bytes(b"keep completed package")
        broken = InterruptedStream(b"test wheel")
        with patch.object(deps.urllib.request, "urlopen", side_effect=[
                broken, io.BytesIO(b"test wheel")]) as network, patch.object(deps.time, "sleep"):
            deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(network.call_count, 2)
        self.assertTrue(broken.closed)
        self.assertEqual(path.read_bytes(), b"test wheel")
        self.assertEqual(previous.read_bytes(), b"keep completed package")
        self.assertEqual(list(self.root.glob("*.download-*")), [])

    def test_exhausted_retries_are_bounded_and_keep_completed_cache(self):
        path = self.root / "missing.whl"
        previous = self.root / "completed.whl"
        previous.write_bytes(b"saved")
        with patch.object(deps.urllib.request, "urlopen", side_effect=TimeoutError()) as network, \
                patch.object(deps.time, "sleep") as sleep:
            with self.assertRaisesRegex(deps.PreparationError, "after 3 attempts: missing.whl"):
                deps.ensure_artifact(path, artifact(), True)
        self.assertEqual(network.call_count, 3)
        self.assertEqual([c.args for c in sleep.call_args_list], [(2,), (4,)])
        self.assertEqual(previous.read_bytes(), b"saved")
        self.assertEqual(list(self.root.iterdir()), [previous])

    def test_transient_http_dns_and_incomplete_reads_retry(self):
        failures = [urllib.error.HTTPError("https://example.invalid", code, "fixture", {}, io.BytesIO())
                    for code in (408, 429, 500, 502, 503, 504)]
        failures += [urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "fixture")),
                     http.client.IncompleteRead(b"partial"), http.client.RemoteDisconnected("fixture")]
        for index, failure in enumerate(failures):
            with self.subTest(failure=type(failure).__name__, index=index), \
                    patch.object(deps.urllib.request, "urlopen", side_effect=[failure, io.BytesIO(b"test wheel")]) as network, \
                    patch.object(deps.time, "sleep") as sleep:
                deps.ensure_artifact(self.root / f"retry{index}.whl", artifact(), True)
                self.assertEqual(network.call_count, 2)
                sleep.assert_called_once_with(2)
                if isinstance(failure, urllib.error.HTTPError):
                    self.assertTrue(failure.closed)

    def test_permanent_network_errors_are_not_retried(self):
        failures = [urllib.error.HTTPError("https://example.invalid", 404, "fixture", {}, io.BytesIO()),
                    urllib.error.URLError(ssl.SSLCertVerificationError("fixture certificate failure")),
                    urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "fixture")),
                    urllib.error.URLError("unknown URL configuration")]
        for failure in failures:
            with self.subTest(failure=repr(failure)), \
                    patch.object(deps.urllib.request, "urlopen", side_effect=failure) as network, \
                    patch.object(deps.time, "sleep") as sleep:
                with self.assertRaises((deps.PreparationError, OSError)):
                    deps.ensure_artifact(self.root / "missing.whl", artifact(), True)
                self.assertEqual(network.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_downloads_fail_without_network_retry(self):
        for body in (b"fail wheel", b"short", b"too much content"):
            with self.subTest(body=body), \
                    patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO(body)) as network, \
                    patch.object(deps.time, "sleep") as sleep:
                with self.assertRaises(deps.PreparationError):
                    deps.ensure_artifact(self.root / "bad.whl", artifact(), True)
                self.assertEqual(network.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_local_io_error_is_never_retried_as_network_timeout(self):
        with patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO(b"test wheel")) as network, \
                patch.object(deps.os, "fsync", side_effect=TimeoutError("local fixture timeout")), \
                patch.object(deps.time, "sleep") as sleep:
            with self.assertRaisesRegex(TimeoutError, "local fixture"):
                deps.ensure_artifact(self.root / "local.whl", artifact(), True)
        self.assertEqual(network.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_offline_and_cached_calls_do_not_retry_or_download(self):
        path = self.root / "cached.whl"
        path.write_bytes(b"test wheel")
        with patch.object(deps.urllib.request, "urlopen", side_effect=AssertionError("network")), \
                patch.object(deps.time, "sleep") as sleep:
            deps.ensure_artifact(path, artifact(), True)
            with self.assertRaises(deps.PreparationError):
                deps.ensure_artifact(self.root / "missing.whl", artifact(), False)
            sleep.assert_not_called()

    def test_prepare_reuses_previous_wheel_but_never_reports_partial_success(self):
        cache = self.root / "cache"
        (cache / "wheels").mkdir(parents=True)
        previous = cache / "wheels" / "first.whl"
        previous.write_bytes(b"test wheel")
        manifest = {"wheels": [artifact("first.whl"), artifact("second.whl")],
                    "mongodb": {**artifact("mongo.zip"), "version": "8.0.32"}}
        output = io.StringIO()
        with patch.object(deps.urllib.request, "urlopen", side_effect=TimeoutError()) as network, \
                patch.object(deps.time, "sleep"), patch("sys.stdout", output):
            with self.assertRaises(deps.PreparationError):
                deps.prepare(manifest, cache, True)
        self.assertEqual(network.call_count, 3)
        self.assertEqual(previous.read_bytes(), b"test wheel")
        self.assertIn("Using verified cached first.whl", output.getvalue())
        self.assertNotIn("ALLIANCE DEPENDENCIES VERIFIED:", output.getvalue())

    def test_real_http_busy_then_body_timeout_then_verified_success(self):
        # Exercise actual urllib exceptions and socket reads on loopback, with
        # an intentionally short fixture timeout; no external host is contacted.
        release = threading.Event()
        requests = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                requests.append(self.path)
                if len(requests) == 1:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", "10")
                self.end_headers()
                if len(requests) == 2:
                    self.wfile.write(b"test")
                    self.wfile.flush()
                    release.wait(5)
                else:
                    self.wfile.write(b"test wheel")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        opener = deps.urllib.request.build_opener(deps.urllib.request.ProxyHandler({}))
        item = {**artifact(), "url": f"http://127.0.0.1:{server.server_port}/fixture"}
        try:
            with patch.object(deps.urllib.request, "urlopen", side_effect=lambda url, timeout: opener.open(url, timeout=0.2)), \
                    patch.object(deps.time, "sleep") as sleep:
                deps.ensure_artifact(self.root / "actual.whl", item, True)
            self.assertEqual(len(requests), 3)
            self.assertEqual([c.args for c in sleep.call_args_list], [(2,), (4,)])
            self.assertEqual((self.root / "actual.whl").read_bytes(), b"test wheel")
            self.assertEqual(list(self.root.glob("*.download-*")), [])
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def mongo_fixture(self, missing=False):
        path = self.root / "mongo.zip"
        files = {}
        with zipfile.ZipFile(path, "w") as archive:
            for name in deps.MONGO_FILES:
                content = name.encode()
                files[name] = {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                if missing and name == "bin/mongod.exe":
                    continue
                archive.writestr("mongodb-win32-x86_64-windows-8.0.32/" + name, content)
            archive.writestr("../../unselected-file", b"never extracted")
        return {"mongodb": {**artifact(path.name, path.read_bytes()), "version": "8.0.32", "files": files}}

    def test_extract_only_selected_files_and_reuse(self):
        manifest = self.mongo_fixture()
        destination = self.root / "installed mongo"
        binary = deps.extract_mongodb(manifest, self.root, destination)
        self.assertEqual(binary.read_bytes(), b"bin/mongod.exe")
        self.assertEqual(set(p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()), set(deps.MONGO_FILES) | {"alliance-owned.json"})
        self.assertEqual(deps.extract_mongodb(manifest, self.root, destination), binary)
        self.assertFalse((self.root.parent / "unselected-file").exists())

    def test_extract_rejects_foreign_destination(self):
        manifest = self.mongo_fixture()
        destination = self.root / "foreign"
        destination.mkdir()
        (destination / "keep").write_text("existing")
        with self.assertRaisesRegex(deps.PreparationError, "ownership"):
            deps.extract_mongodb(manifest, self.root, destination)
        self.assertEqual((destination / "keep").read_text(), "existing")

    def test_tampered_binary_and_receipt_cannot_override_pin(self):
        manifest = self.mongo_fixture()
        destination = self.root / "installed"
        binary = deps.extract_mongodb(manifest, self.root, destination)
        binary.write_bytes(b"replacement")
        receipt = destination / "alliance-owned.json"
        data = json.loads(receipt.read_text())
        data["files"]["bin/mongod.exe"] = {"size": 11, "sha256": hashlib.sha256(b"replacement").hexdigest()}
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(deps.PreparationError, "selection"):
            deps.extract_mongodb(manifest, self.root, destination)
        self.assertEqual(binary.read_bytes(), b"replacement")

    def test_missing_zip_member_leaves_no_partial_install(self):
        manifest = self.mongo_fixture(missing=True)
        with self.assertRaises(KeyError):
            deps.extract_mongodb(manifest, self.root, self.root / "destination")
        self.assertFalse((self.root / "destination").exists())
        self.assertEqual(list(self.root.glob("*.extract-*")), [])

    @staticmethod
    def rename_error(code):
        error = PermissionError("fixture denied MongoDB publication")
        error.winerror = code
        return error

    def assert_complete_mongo_stage(self, stage, manifest):
        self.assertTrue(stage.is_dir())
        self.assertEqual(
            {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()},
            set(deps.MONGO_FILES) | {"alliance-owned.json"})
        for name, expected in manifest["mongodb"]["files"].items():
            self.assertEqual((stage / name).stat().st_size, expected["size"])
            self.assertEqual(deps.digest(stage / name), expected["sha256"])

    def test_mongo_windows_rename_retry_extracts_once_and_reuses_same_stage(self):
        manifest = self.mongo_fixture()
        real_rename = Path.rename
        for code in (5, 32, 33):
            destination = self.root / f"installed-{code}"
            attempts = []
            def rename(path, target):
                attempts.append((path, Path(target)))
                if len(attempts) == 1:
                    raise self.rename_error(code)
                return real_rename(path, target)
            with self.subTest(winerror=code), patch.object(Path, "rename", rename), \
                    patch.object(deps.zipfile, "ZipFile", wraps=zipfile.ZipFile) as archive, \
                    patch.object(deps.time, "sleep") as sleep:
                binary = deps.extract_mongodb(manifest, self.root, destination)
            self.assertEqual(archive.call_count, 1)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0], attempts[1])
            sleep.assert_called_once_with(0.5)
            self.assertEqual(binary, destination / "bin/mongod.exe")
            self.assert_complete_mongo_stage(destination, manifest)
            self.assertFalse(attempts[0][0].exists())
            self.assertEqual(deps.digest(self.root / "mongo.zip"), manifest["mongodb"]["sha256"])

    def test_mongo_exhausted_rename_retries_preserve_complete_stage_and_cache(self):
        manifest = self.mongo_fixture()
        destination = self.root / "installed"
        attempts = []
        def rename(path, target):
            attempts.append((path, Path(target)))
            raise self.rename_error(5)
        with patch.object(Path, "rename", rename), \
                patch.object(deps.zipfile, "ZipFile", wraps=zipfile.ZipFile) as archive, \
                patch.object(deps.time, "sleep") as sleep:
            with self.assertRaises((deps.PreparationError, OSError)):
                deps.extract_mongodb(manifest, self.root, destination)
        self.assertEqual(archive.call_count, 1)
        self.assertEqual(len(attempts), 6)
        self.assertEqual(len(set(attempts)), 1)
        self.assertEqual([call.args for call in sleep.call_args_list], [(0.5,), (1,), (2,), (4,), (8,)])
        self.assertEqual(list(self.root.glob("installed.extract-*")), [attempts[0][0]])
        self.assert_complete_mongo_stage(attempts[0][0], manifest)
        self.assertFalse(os.path.lexists(destination))
        self.assertEqual(deps.digest(self.root / "mongo.zip"), manifest["mongodb"]["sha256"])

    def test_mongo_destination_created_during_backoff_is_never_replaced(self):
        manifest = self.mongo_fixture()
        for kind in ("directory", "file", "dangling-link"):
            destination = self.root / kind
            attempts = []
            def rename(path, target):
                attempts.append(path)
                raise self.rename_error(32)
            def add_destination(_delay):
                if kind == "directory":
                    destination.mkdir()
                    (destination / "keep").write_bytes(b"user data")
                elif kind == "file":
                    destination.write_bytes(b"user data")
                else:
                    destination.symlink_to(self.root / "absent")
            with self.subTest(kind=kind), patch.object(Path, "rename", rename), \
                    patch.object(deps.time, "sleep", side_effect=add_destination) as sleep:
                with self.assertRaises(deps.PreparationError):
                    deps.extract_mongodb(manifest, self.root, destination)
            self.assertEqual(len(attempts), 1)
            sleep.assert_called_once_with(0.5)
            self.assert_complete_mongo_stage(attempts[0], manifest)
            if kind == "directory":
                self.assertEqual((destination / "keep").read_bytes(), b"user data")
            elif kind == "file":
                self.assertEqual(destination.read_bytes(), b"user data")
            else:
                self.assertTrue(destination.is_symlink())
                self.assertEqual(destination.readlink(), self.root / "absent")

    def test_mongo_changed_stage_blocks_another_rename_and_is_preserved(self):
        manifest = self.mongo_fixture()
        for kind in ("binary", "receipt", "metadata", "extra-file", "identity"):
            destination = self.root / f"changed-{kind}"
            attempts = []
            def rename(path, target):
                attempts.append(path)
                raise self.rename_error(5)
            def change_source(_delay):
                stage = attempts[0]
                if kind == "binary":
                    (stage / "bin/mongod.exe").write_bytes(b"replacement")
                elif kind == "receipt":
                    receipt = stage / "alliance-owned.json"
                    receipt.write_bytes(receipt.read_bytes() + b"\n")
                elif kind == "metadata":
                    path = stage / "bin/mongod.exe"
                    info = path.stat()
                    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
                elif kind == "extra-file":
                    (stage / "unexpected").write_bytes(b"preserve evidence")
                else:
                    backup = self.root / "original-stage"
                    os.rename(stage, backup)
                    shutil.copytree(backup, stage)
            with self.subTest(kind=kind), patch.object(Path, "rename", rename), \
                    patch.object(deps.time, "sleep", side_effect=change_source):
                with self.assertRaises(deps.PreparationError):
                    deps.extract_mongodb(manifest, self.root, destination)
            self.assertEqual(len(attempts), 1)
            self.assertTrue(attempts[0].is_dir())
            self.assertFalse(os.path.lexists(destination))
            if kind == "binary":
                self.assertEqual((attempts[0] / "bin/mongod.exe").read_bytes(), b"replacement")
            elif kind == "extra-file":
                self.assertEqual((attempts[0] / "unexpected").read_bytes(), b"preserve evidence")

    def test_mongo_nonwindows_permission_and_other_io_errors_are_not_retried(self):
        manifest = self.mongo_fixture()
        for index, error in enumerate((PermissionError("POSIX permission"),
                                       FileNotFoundError("missing source"), self.rename_error(87))):
            destination = self.root / f"permanent-{index}"
            attempts = []
            def rename(path, target):
                attempts.append(path)
                raise error
            with self.subTest(error=error), patch.object(Path, "rename", rename), \
                    patch.object(deps.time, "sleep") as sleep:
                with self.assertRaises((deps.PreparationError, OSError)):
                    deps.extract_mongodb(manifest, self.root, destination)
            self.assertEqual(len(attempts), 1)
            sleep.assert_not_called()
            self.assert_complete_mongo_stage(attempts[0], manifest)
            self.assertFalse(os.path.lexists(destination))

    def test_mongo_interrupted_publication_preserves_completed_extraction(self):
        manifest = self.mongo_fixture()
        for interrupt_at in ("rename", "backoff"):
            destination = self.root / interrupt_at
            attempts = []
            def rename(path, target):
                attempts.append(path)
                if interrupt_at == "rename":
                    raise KeyboardInterrupt()
                raise self.rename_error(5)
            with self.subTest(interrupt_at=interrupt_at), patch.object(Path, "rename", rename), \
                    patch.object(deps.time, "sleep", side_effect=KeyboardInterrupt()) as sleep:
                with self.assertRaises(KeyboardInterrupt):
                    deps.extract_mongodb(manifest, self.root, destination)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(sleep.call_count, 1 if interrupt_at == "backoff" else 0)
            self.assert_complete_mongo_stage(attempts[0], manifest)
            self.assertFalse(os.path.lexists(destination))

    def test_mongo_existing_root_and_bin_links_are_rejected_without_changes(self):
        manifest = self.mongo_fixture()
        original = self.root / "original"
        deps.extract_mongodb(manifest, self.root, original)
        original_files = {path.relative_to(original).as_posix(): path.read_bytes()
                          for path in original.rglob("*") if path.is_file()}
        linked = self.root / "root-link"
        linked.symlink_to(original, target_is_directory=True)
        dangling = self.root / "dangling-root"
        dangling.symlink_to(self.root / "absent", target_is_directory=True)
        bin_linked = self.root / "bin-linked"
        shutil.copytree(original, bin_linked)
        shutil.rmtree(bin_linked / "bin")
        (bin_linked / "bin").symlink_to(original / "bin", target_is_directory=True)
        for destination in (linked, dangling, bin_linked):
            with self.subTest(destination=destination), patch.object(deps.time, "sleep") as sleep:
                with self.assertRaises(deps.PreparationError):
                    deps.extract_mongodb(manifest, self.root, destination)
                sleep.assert_not_called()
        self.assertEqual({path.relative_to(original).as_posix(): path.read_bytes()
                          for path in original.rglob("*") if path.is_file()}, original_files)
        self.assertTrue(linked.is_symlink())
        self.assertTrue(dangling.is_symlink())
        self.assertTrue((bin_linked / "bin").is_symlink())

    def test_mongo_successful_rename_is_followed_by_final_pin_verification(self):
        manifest = self.mongo_fixture()
        destination = self.root / "installed"
        real_rename = Path.rename
        def rename(path, target):
            result = real_rename(path, target)
            (Path(target) / "bin/mongod.exe").write_bytes(b"modified after rename")
            return result
        with patch.object(Path, "rename", rename), patch.object(deps.time, "sleep") as sleep:
            with self.assertRaises(deps.PreparationError):
                deps.extract_mongodb(manifest, self.root, destination)
        sleep.assert_not_called()
        self.assertEqual((destination / "bin/mongod.exe").read_bytes(), b"modified after rename")

    def test_mongo_windows_junction_detection_rejects_root_and_bin(self):
        # NTFS junctions cannot be created by this Linux suite; exercise the
        # Windows pathlib result while preserving a real complete directory.
        manifest = self.mongo_fixture()
        destination = self.root / "installed"
        deps.extract_mongodb(manifest, self.root, destination)
        for redirected in (destination, destination / "bin"):
            with self.subTest(redirected=redirected), \
                    patch.object(Path, "is_junction", lambda path: path == redirected), \
                    patch.object(Path, "rename") as rename, patch.object(deps.time, "sleep") as sleep:
                with self.assertRaises(deps.PreparationError):
                    deps.extract_mongodb(manifest, self.root, destination)
                rename.assert_not_called()
                sleep.assert_not_called()
            self.assert_complete_mongo_stage(destination, manifest)

    def test_installer_publication_failure_never_executes_binary_or_creates_venv(self):
        manifest = {**self.mongo_fixture(), "wheels": []}
        destination = self.root / "installed"
        venv = self.root / "venv"
        attempts = []
        def rename(path, target):
            attempts.append(path)
            raise self.rename_error(5)
        with patch.object(deps, "assert_windows_python"), patch.object(Path, "rename", rename), \
                patch.object(deps.time, "sleep"), patch.object(deps.subprocess, "run") as execute:
            with self.assertRaises((deps.PreparationError, OSError)):
                deps.install(manifest, self.root, venv, destination)
        execute.assert_not_called()
        self.assertFalse(venv.exists())
        self.assertFalse(os.path.lexists(destination))
        self.assert_complete_mongo_stage(attempts[0], manifest)

    def test_installer_rejects_nonwindows_before_any_changes(self):
        with patch.object(deps.sys, "platform", "linux"):
            with self.assertRaisesRegex(deps.PreparationError, "Windows"):
                deps.install({}, self.root / "cache", self.root / "venv", self.root / "mongo")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_all_requirements_match_manifest(self):
        manifest = deps.load_manifest()
        lines = (deps.PINS / "requirements-windows.txt").read_text().splitlines()
        actual = {line for line in lines if line and not line.startswith("#")}
        expected = {f"{x['name']}=={x['version']} --hash=sha256:{x['sha256']}" for x in manifest["wheels"]}
        self.assertEqual(actual, expected)
        self.assertEqual(set(manifest["mongodb"]["files"]), set(deps.MONGO_FILES))


@unittest.skipUnless(PWSH.is_file(), "Linux PowerShell host unavailable; Windows execution is still required")
class PowerShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance PS paths ")
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        for script in (ROOT / "tools").glob("*Alliance*.ps1"):
            shutil.copy2(script, self.root / "tools" / script.name)
        (self.root / "tools/alliance_dependencies.py").touch()
        self.native = self.root / "Programs/Python/Python314/python.exe"
        self.venv = self.root / "build/alliance-venv/Scripts/python.exe"
        for path in (self.native, self.venv):
            path.parent.mkdir(parents=True)
            path.write_text('#!/usr/bin/python3\nimport json,os,sys\nwith open(os.environ["ALLIANCE_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\nprint("Simulated native output")\nsys.exit(9 if os.environ.get("ALLIANCE_FAIL") in sys.argv[1:] else 0)\n')
            path.chmod(0o755)
        mongod = self.root / "build/alliance-mongodb/bin/mongod.exe"
        mongod.parent.mkdir(parents=True)
        mongod.touch()
        self.calls = self.root / "calls.jsonl"
        self.driver = self.root / "driver.ps1"
        self.driver.write_text("param([string]$Wrapper,[switch]$Download)\n"
            "$null=New-PSDrive -Name C -PSProvider FileSystem -Root $env:ALLIANCE_FIXTURE_ROOT\n"
            "$arguments=@{}\nif ($Download) { $arguments.Download=$true }\n"
            "& (Join-Path $env:ALLIANCE_FIXTURE_ROOT ('tools/'+$Wrapper)) @arguments\nexit $LASTEXITCODE\n")
        self.env = {**os.environ, "OS": "Windows_NT", "LOCALAPPDATA": "C:\\", "ALLIANCE_CALLS": str(self.calls),
                    "ALLIANCE_FIXTURE_ROOT": str(self.root)}

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, name, *args, failure=""):
        return subprocess.run([str(PWSH), "-NoProfile", "-File", str(self.driver), "-Wrapper", name, *args], capture_output=True, text=True, env={**self.env, "ALLIANCE_FAIL": failure})

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_prepare_download_is_explicit(self):
        result = self.invoke("Prepare-WindowsAlliance.ps1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("--download", self.read_calls()[-1])
        result = self.invoke("Prepare-WindowsAlliance.ps1", "-Download")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_calls()[-1][-2:], ["prepare", "--download"])

    def test_install_offline_and_native_output_is_not_exit_value(self):
        result = self.invoke("Install-WindowsAlliance.ps1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_calls()[-1][-1], "install")
        self.assertNotIn("--download", self.read_calls()[-1])

    def test_all_runtime_commands_use_dedicated_paths(self):
        for name, command in [("Initialize-WindowsAlliance.ps1", "init"), ("Run-WindowsAllianceDatabase.ps1", "database"), ("Run-WindowsAlliance.ps1", "serve"), ("Test-WindowsAlliance.ps1", "check")]:
            with self.subTest(command=command):
                result = self.invoke(name)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                calls = self.read_calls()
                self.assertEqual(calls[-2][-1], "check-installed")
                args = calls[-1]
                self.assertEqual(args[:4], ["-E", "-s", "-m", "alliance"])
                self.assertEqual(args[-1], command)
                self.assertEqual(args[args.index("--runtime") + 1], str(self.root / "WesnothAlliance/runtime-v2"))
                self.assertEqual("--mongod" in args, command in ("init", "database"))
                if command == "init":
                    self.assertNotIn("Saved log:", result.stdout)

    def test_python_failure_stops_before_execution(self):
        result = self.invoke("Prepare-WindowsAlliance.ps1", "-Download", failure="check-python")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.read_calls()), 1)

    def test_installed_integrity_failure_stops_runtime(self):
        result = self.invoke("Run-WindowsAlliance.ps1", failure="check-installed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.read_calls()), 2)
        self.assertIn("Saved log:", result.stdout)

    def test_runtime_failure_preserves_nonzero_exit_and_log(self):
        result = self.invoke("Test-WindowsAlliance.ps1", failure="check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Saved log:", result.stdout)


if __name__ == "__main__":
    unittest.main()
