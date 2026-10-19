"""Artifact preservation tests and executable PowerShell helper simulations."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
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
        self.env = {**os.environ, "OS": "Windows_NT", "LOCALAPPDATA": str(self.root), "ALLIANCE_CALLS": str(self.calls)}

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, name, *args, failure=""):
        return subprocess.run([str(PWSH), "-NoProfile", "-File", str(self.root / "tools" / name), *args], capture_output=True, text=True, env={**self.env, "ALLIANCE_FAIL": failure})

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
                self.assertEqual(args[args.index("--runtime") + 1], str(self.root / "runtime/alliance"))
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
