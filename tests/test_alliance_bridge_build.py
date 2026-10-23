"""Receipt/path checks for the new bridge stage; no tool installation or builds."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bridge_build", ROOT / "tools/build_alliance_bridge.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class BridgeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bridge stage ")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo with spaces"
        self.repo.mkdir()
        self.old_root, self.old_stage = BUILD.ROOT, BUILD.STAGE
        BUILD.ROOT = self.repo
        BUILD.STAGE = self.repo / "build/alliance-account-bridge"
        self.addCleanup(self.restore)
        for name in BUILD.INPUTS:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("input:" + name)
        BUILD.STAGE.mkdir(parents=True)
        BUILD.write_new(BUILD.STAGE / "owner.json", BUILD.binding())
        self.exe = BUILD.STAGE / "alliance-account-bridge.exe"
        self.exe.write_bytes(b"test-owned-executable")
        self.receipt = {
            "binding": BUILD.binding(), "versions": {"fixture": True},
            "executable": {"name": self.exe.name, "bytes": self.exe.stat().st_size, "sha256": BUILD.digest(self.exe)},
        }
        BUILD.write_new(BUILD.STAGE / "receipt.json", self.receipt)

    def restore(self):
        BUILD.ROOT, BUILD.STAGE = self.old_root, self.old_stage

    def test_complete_verification_does_not_modify_files(self):
        before = {str(path): path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        self.assertEqual(BUILD.verify(), self.exe)
        after = {str(path): path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_changed_source_rejected_before_reuse(self):
        (self.repo / BUILD.INPUTS[0]).write_text("changed")
        with self.assertRaises(BUILD.BuildError):
            BUILD.verify()
        self.assertEqual(self.exe.read_bytes(), b"test-owned-executable")

    def test_changed_binary_rejected(self):
        self.exe.write_bytes(b"changed-output")
        with self.assertRaises(BUILD.BuildError):
            BUILD.verify()

    def test_incomplete_stage_rejected_without_overwrite(self):
        (BUILD.STAGE / "receipt.json").unlink()
        with self.assertRaises(BUILD.BuildError):
            BUILD.verify()
        self.assertEqual(self.exe.read_bytes(), b"test-owned-executable")

    def test_duplicate_receipt_and_link_rejected(self):
        (BUILD.STAGE / "receipt.json").write_text('{"binding":1,"binding":2}')
        with self.assertRaises(BUILD.BuildError):
            BUILD.verify()
        self.exe.unlink()
        target = self.repo / "elsewhere"
        target.write_bytes(b"must-not-follow")
        try:
            self.exe.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(BUILD.BuildError):
            BUILD.digest(self.exe)


class BuildInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bridge build invocation ")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo with spaces"
        self.repo.mkdir()
        self.old_root, self.old_stage = BUILD.ROOT, BUILD.STAGE
        BUILD.ROOT, BUILD.STAGE = self.repo, self.repo / "build/alliance-account-bridge"
        self.addCleanup(self.restore)
        for name in BUILD.INPUTS:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("input:" + name)
        self.msys = self.repo / "msys with spaces"
        self.cmake = self.repo / "cmake with spaces/cmake.exe"
        for path in (self.msys / "mingw64/bin/g++.exe", self.msys / "mingw64/bin/openssl.exe",
                     self.msys / "ucrt64/bin/ninja.exe", self.cmake):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture native tool")
        header = self.msys / "mingw64/include/boost/version.hpp"
        header.parent.mkdir(parents=True)
        header.write_text('#define BOOST_LIB_VERSION "1_91"\n')
        self.commands = []

    def restore(self):
        BUILD.ROOT, BUILD.STAGE = self.old_root, self.old_stage

    def capture(self, command, environment):
        tool, option = Path(command[0]).name, command[1]
        self.assertTrue(environment["PATH"].startswith(str(self.msys / "mingw64/bin")))
        if tool == "cmake.exe": return "cmake version 4.3.0"
        if tool == "ninja.exe": return "1.13.2"
        if tool == "openssl.exe": return "OpenSSL 3.6.3 9 Jun 2026"
        if tool == "g++.exe": return "x86_64-w64-mingw32" if option == "-dumpmachine" else "16.2.0"
        if tool == "alliance-account-bridge.exe":
            return "WESNOTH_ALLIANCE_ACCOUNT_BRIDGE protocol=2 max_connections=32 timeout_seconds=10"
        self.fail("Unexpected tool")

    def native(self, command, _environment):
        self.commands.append(command)
        if "--build" in command:
            (BUILD.STAGE / "alliance-account-bridge.exe").write_bytes(b"completed fixture executable")

    def test_build_preserves_argument_boundaries_and_reuses_completed_stage(self):
        with patch.object(BUILD, "check_host"), patch.object(BUILD, "capture", self.capture), patch.object(BUILD, "native", self.native):
            BUILD.build(self.msys, self.cmake)
            self.assertEqual(len(self.commands), 2)
            self.assertEqual(self.commands[0][2], self.repo / "alliance_bridge")
            self.assertIn("-DCMAKE_SUPPRESS_REGENERATION=ON", self.commands[0])
            self.assertEqual(self.commands[1][-3:], ["--", "-d", "keepdepfile"])
            BUILD.build(self.msys, self.cmake)
            self.assertEqual(len(self.commands), 2)

    def test_build_failure_keeps_incomplete_owned_stage_and_no_receipt(self):
        with patch.object(BUILD, "check_host"), patch.object(BUILD, "capture", self.capture), patch.object(BUILD, "native", side_effect=BUILD.BuildError("injected")):
            with self.assertRaises(BUILD.BuildError):
                BUILD.build(self.msys, self.cmake)
        self.assertTrue((BUILD.STAGE / "owner.json").is_file())
        self.assertFalse((BUILD.STAGE / "receipt.json").exists())

    def test_wrong_tool_version_stops_before_stage_creation(self):
        def wrong(command, environment):
            return "2.0" if Path(command[0]).name == "ninja.exe" else self.capture(command, environment)
        with patch.object(BUILD, "check_host"), patch.object(BUILD, "capture", wrong):
            with self.assertRaises(BUILD.BuildError):
                BUILD.build(self.msys, self.cmake)
        self.assertFalse(BUILD.STAGE.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
