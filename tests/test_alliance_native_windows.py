"""Execute the native-probe Windows wrapper with isolated simulated executables.

Linux PowerShell checks argument boundaries, ownership, failures and restoration.
These tests do not establish Windows compiler/TLS or Android runtime success.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = "Test-WindowsAllianceNative.ps1"
SUCCESS = "ALLIANCE NATIVE FIXTURE COMPLETE"
FAKE_NATIVE = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
name = pathlib.Path(sys.argv[0]).name
if name == 'python.exe':
    action = 'check-python' if args[-1] == 'check-python' else 'fixture'
elif name == 'cmake.exe':
    action = 'cmake-version' if args == ['--version'] else ('configure' if '-S' in args else 'build')
elif name == 'g++.exe':
    action = 'compiler-target' if args == ['-dumpmachine'] else 'compiler-version'
else:
    action = 'ninja-version' if name == 'ninja.exe' else 'openssl-version'
with open(os.environ['NATIVE_CALLS'], 'a') as output:
    output.write(json.dumps({'name': name, 'action': action, 'args': args, 'path': os.environ['PATH']}) + '\n')
if os.environ.get('NATIVE_FAIL') == action and action != 'fixture':
    print('Injected native failure')
    sys.exit(9)
versions = {
    'cmake-version': 'cmake version 4.3.0\n\nCMake suite maintained and supported by Kitware.',
    'ninja-version': '1.13.2', 'compiler-target': 'x86_64-w64-mingw32',
    'compiler-version': '16.2.0', 'openssl-version': 'OpenSSL 3.6.3 9 Jun 2026',
}
if action in versions:
    print('unexpected-version' if os.environ.get('NATIVE_BAD_VERSION') == action else versions[action])
elif action == 'configure':
    stage = pathlib.Path(args[args.index('-B') + 1])
    (stage / 'simulated-configure.json').write_text(json.dumps(args))
elif action == 'build':
    stage = pathlib.Path(args[args.index('--build') + 1])
    if os.environ.get('NATIVE_OUTPUT') != 'missing':
        (stage / 'alliance-native-probe.exe').write_bytes(b'' if os.environ.get('NATIVE_OUTPUT') == 'empty' else b'owned simulated probe')
elif action == 'fixture':
    scratch = pathlib.Path(args[args.index('--scratch') + 1])
    scratch.mkdir()
    (scratch / 'fixture-sentinel').write_bytes(b'new scratch only')
    with pathlib.Path(args[args.index('--report') + 1]).open('x') as output:
        json.dump({'simulated': True, 'status': 'failed' if os.environ.get('NATIVE_FAIL') == action else 'passed'}, output)
    if os.environ.get('NATIVE_FAIL') == action:
        print('Injected fixture failure after partial report')
        sys.exit(9)
else:
    print('Simulated Python 3.14.3 check')
'''
LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:NATIVE_SETTINGS -Raw | ConvertFrom-Json
$env:PATH = $env:NATIVE_BASE_PATH
$beforePath = $env:PATH
$parameters = @{}
foreach ($property in $settings.parameters.PSObject.Properties) {
    $parameters[$property.Name] = $property.Value
}
& $settings.helper @parameters
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper did not restore PATH.' }
[IO.File]::WriteAllText($settings.after_path, $env:PATH)
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), "Existing Linux PowerShell is unavailable; no tools are installed")
class NativePowerShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="alliance native PS ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "server with spaces & literal $"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        self.helper = self.tools / HELPER
        self.helper.write_bytes((ROOT / "tools" / HELPER).read_bytes())
        self.client = self.root / "wesnoth_client"
        self.source = self.client / "tools/native-alliance"
        self.source.mkdir(parents=True)
        (self.source / "CMakeLists.txt").write_bytes(b"existing native sources")
        self.localappdata = self.root / "Local App Data"
        self.python = self.localappdata / "Programs/Python/Python314/python.exe"
        self.msys = self.root / "MSYS with spaces & literal $"
        self.compiler = self.msys / "mingw64/bin/g++.exe"
        self.openssl = self.msys / "mingw64/bin/openssl.exe"
        self.ninja = self.msys / "ucrt64/bin/ninja.exe"
        self.cmake = self.root / "Program Files & literal $/CMake/bin/cmake.exe"
        for executable in (self.python, self.compiler, self.openssl, self.ninja, self.cmake):
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text(FAKE_NATIVE)
            executable.chmod(0o755)
        for name in ("alliance_dependencies.py", "test_alliance_native.py"):
            (self.tools / name).write_bytes(b"Python module fixture, never imported")
        self.profile = self.repo / "runtime/alliance-transport/public-profile.json"
        self.protected = {}
        sentinels = [
            (self.repo / ".env", b"PRIVATE_ENV_SENTINEL"),
            (self.repo / "runtime/alliance/root.json", b"PRIVATE_RUNTIME_SENTINEL"),
            (self.repo / "runtime/alliance-transport/private-key.pem", b"PRIVATE_KEY_SENTINEL"),
            (self.repo / "runtime/alliance-transport/server-certificate.pem", b"UNCHANGED_CERT"),
            (self.profile, b"UNCHANGED_PUBLIC_PROFILE"),
            (self.repo / "build/windows-mingw64/bin/wesnothd.exe", b"COMPLETED_SERVER"),
            (self.repo / "build/alliance-native-previous/fixture.pem", b"OLDER_FIXTURE"),
            (self.repo / "README.md", b"UNRELATED_USER_CHANGES"),
            (self.client / "build/android-engine/prefix/libmain.so", b"COMPLETED_ENGINE"),
            (self.client / "build/android-game/apk/game.apk", b"COMPLETED_APK"),
            (self.client / "build/android-game-data/game.obb", b"COMPLETED_OBB"),
        ]
        for path, content in sentinels:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.protected[path] = hashlib.sha256(content).hexdigest()
        for path in (self.helper, self.source / "CMakeLists.txt"):
            self.protected[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.calls = self.root / "calls.jsonl"
        self.after_path = self.root / "after-path.txt"
        self.settings = self.root / "settings.json"
        self.launcher = self.root / "launcher.ps1"
        self.launcher.write_text(LAUNCHER)
        self.parameters = {"MsysRoot": str(self.msys), "CMakePath": str(self.cmake)}
        self.environment = {
            **os.environ, "OS": "Windows_NT", "LOCALAPPDATA": str(self.localappdata),
            "NATIVE_CALLS": str(self.calls), "NATIVE_SETTINGS": str(self.settings),
            "NATIVE_BASE_PATH": os.environ["PATH"],
        }

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def run_helper(self, *, success=True, failure="", bad_version="", expected_logs=1, logged=True):
        self.settings.write_text(json.dumps({
            "helper": str(self.helper), "parameters": self.parameters, "after_path": str(self.after_path),
        }))
        result = subprocess.run(
            [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(self.launcher)],
            env={**self.environment, "NATIVE_FAIL": failure, "NATIVE_BAD_VERSION": bad_version},
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout)
        self.assertEqual(SUCCESS in result.stdout, success, result.stdout)
        self.assertEqual(self.after_path.read_text(), self.environment["PATH"], result.stdout)
        logs = sorted((self.repo / "diagnostics").glob("alliance-native-*.txt"))
        self.assertEqual(len(logs), expected_logs, result.stdout)
        reports = ""
        for path in logs:
            raw = path.read_bytes()
            reports += raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if logged:
            self.assertIn("Saved log:", result.stdout)
            self.assertIn("Native report (if produced):", reports)
            self.assertEqual("ERROR:" in reports, not success, reports)
        else:
            self.assertNotIn("Saved log:", result.stdout)
        for secret in ("PRIVATE_ENV_SENTINEL", "PRIVATE_RUNTIME_SENTINEL", "PRIVATE_KEY_SENTINEL"):
            self.assertNotIn(secret, result.stdout + reports)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        return result, reports

    def test_success_builds_only_new_probe_then_passes_public_profile_and_unique_scratch(self):
        _, report = self.run_helper()
        calls = self.read_calls()
        self.assertEqual([call["action"] for call in calls], [
            "check-python", "cmake-version", "ninja-version", "compiler-target", "compiler-version",
            "openssl-version", "configure", "build", "fixture",
        ])
        self.assertEqual(calls[0]["args"], ["-I", "-B", str(self.tools / "alliance_dependencies.py"), "check-python"])
        stages = [path for path in (self.repo / "build").glob("alliance-native-*") if path.name != "alliance-native-previous"]
        self.assertEqual(len(stages), 1)
        stage = stages[0]
        self.assertEqual(calls[6]["args"], [
            "-S", str(self.source), "-B", str(stage), "-G", "Ninja",
            "-DCMAKE_CXX_COMPILER=" + str(self.compiler), "-DCMAKE_MAKE_PROGRAM=" + str(self.ninja),
            "-DCMAKE_PREFIX_PATH=" + str(self.msys / "mingw64"),
            "-DBOOST_INCLUDE_DIR=" + str(self.msys / "mingw64/include"),
            "-DOPENSSL_ROOT_DIR=" + str(self.msys / "mingw64"),
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SUPPRESS_REGENERATION=ON",
        ])
        self.assertEqual(calls[7]["args"], ["--build", str(stage), "--parallel", "2", "--", "-d", "keepdepfile"])
        self.assertEqual(calls[8]["args"], [
            "-I", "-B", str(self.tools / "test_alliance_native.py"), "--probe", str(stage / "alliance-native-probe.exe"),
            "--profile", str(self.profile), "--openssl", str(self.openssl), "--require-openssl-version", "3.6.3",
            "--scratch", str(stage / "fixtures"), "--report", str(self.repo / "diagnostics" / (stage.name + ".json")),
        ])
        self.assertTrue(all(call["path"] == str(self.compiler.parent) + ";" + self.environment["PATH"] for call in calls))
        self.assertIn("native client transport on Windows loopback", report)
        self.assertIn("Android, account login, MongoDB and team gameplay remain pending", report)

    def test_custom_client_root_and_python_are_literal_arguments(self):
        custom_client = self.root / "Client & literal $"
        custom_source = custom_client / "tools/native-alliance"
        custom_source.mkdir(parents=True)
        (custom_source / "CMakeLists.txt").write_bytes(b"custom source fixture")
        custom_python = self.root / "Python & literal $/python.exe"
        custom_python.parent.mkdir()
        custom_python.write_bytes(self.python.read_bytes())
        custom_python.chmod(0o755)
        self.python.unlink()
        self.parameters.update(ClientRoot=str(custom_client), PythonPath=str(custom_python))
        self.run_helper()
        self.assertEqual(self.read_calls()[6]["args"][1], str(custom_source))

    def select_existing_probe(self):
        probe = self.repo / "build/alliance-native-previous/alliance-native-probe [checked] & literal $.exe"
        probe.write_bytes(b"EXISTING_NATIVE_PROBE")
        self.protected[probe] = hashlib.sha256(probe.read_bytes()).hexdigest()
        self.parameters["ProbePath"] = str(probe)
        return probe

    def test_existing_probe_skips_build_tools_and_client_source_and_uses_fresh_scratch(self):
        probe = self.select_existing_probe()
        for path in (self.compiler, self.ninja, self.cmake, self.source / "CMakeLists.txt"):
            self.protected.pop(path, None)
            path.unlink()
        self.parameters["ClientRoot"] = str(self.root / "missing client checkout")
        _, report = self.run_helper()
        calls = self.read_calls()
        self.assertEqual([call["action"] for call in calls], ["check-python", "openssl-version", "fixture"])
        arguments = calls[-1]["args"]
        self.assertEqual(arguments[arguments.index("--probe") + 1], str(probe))
        self.assertEqual(arguments[arguments.index("--profile") + 1], str(self.profile))
        self.assertEqual(arguments[arguments.index("--require-openssl-version") + 1], "3.6.3")
        scratch = Path(arguments[arguments.index("--scratch") + 1])
        self.assertNotEqual(scratch.parent, probe.parent)
        self.assertEqual(scratch.name, "fixtures")
        self.assertEqual(scratch.parent.parent, self.repo / "build")
        self.assertEqual((scratch / "fixture-sentinel").read_bytes(), b"new scratch only")
        self.assertFalse((scratch.parent / "alliance-native-probe.exe").exists())
        self.assertTrue(all(call["path"] == str(self.compiler.parent) + ";" + self.environment["PATH"] for call in calls))
        self.assertIn("Reusing existing native Alliance probe without rebuilding:", report)
        self.assertNotIn("Building the small native", report)

    def test_invalid_selected_probe_stops_without_silent_build_fallback(self):
        probe = self.select_existing_probe()
        del self.protected[probe]
        for index, state in enumerate(("empty-parameter", "empty-file", "missing", "directory"), 1):
            with self.subTest(state=state):
                if state == "empty-parameter":
                    self.parameters["ProbePath"] = ""
                else:
                    self.parameters["ProbePath"] = str(probe)
                    if state == "empty-file":
                        probe.write_bytes(b"")
                    elif state == "missing":
                        probe.unlink()
                    else:
                        probe.mkdir()
                _, report = self.run_helper(success=False, expected_logs=index)
                self.assertIn("selected existing probe is missing or empty", report)
                self.assertEqual(self.read_calls(), [])
                self.assertEqual({path.name for path in (self.repo / "build").iterdir()},
                                 {"windows-mingw64", "alliance-native-previous"})

    def test_reuse_python_pin_failure_stops_before_fixture(self):
        self.select_existing_probe()
        self.run_helper(success=False, failure="check-python")
        self.assertEqual([call["action"] for call in self.read_calls()], ["check-python"])

    def test_reuse_openssl_pin_and_command_failure_stop_before_fixture(self):
        self.select_existing_probe()
        self.run_helper(success=False, bad_version="openssl-version")
        self.assertEqual([call["action"] for call in self.read_calls()], ["check-python", "openssl-version"])
        self.calls.unlink()
        self.run_helper(success=False, failure="openssl-version", expected_logs=2)
        self.assertEqual([call["action"] for call in self.read_calls()], ["check-python", "openssl-version"])

    def test_reuse_fixture_failure_keeps_partial_report_and_preserves_existing_stage(self):
        probe = self.select_existing_probe()
        _, report = self.run_helper(success=False, failure="fixture")
        calls = self.read_calls()
        self.assertEqual([call["action"] for call in calls], ["check-python", "openssl-version", "fixture"])
        arguments = calls[-1]["args"]
        scratch = Path(arguments[arguments.index("--scratch") + 1])
        partial = Path(arguments[arguments.index("--report") + 1])
        self.assertEqual(json.loads(partial.read_text())["status"], "failed")
        self.assertEqual((scratch / "fixture-sentinel").read_bytes(), b"new scratch only")
        self.assertEqual(arguments[arguments.index("--probe") + 1], str(probe))
        self.assertIn("fixture failed with exit 9", report)

    def test_repeated_reuse_preserves_old_probe_scratch_and_reports(self):
        probe = self.select_existing_probe()
        self.run_helper()
        first = {path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        self.run_helper(expected_logs=2)
        for path, content in first.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertEqual(len(list((self.repo / "diagnostics").glob("*.json"))), 2)
        self.assertEqual(len(list((self.repo / "build").glob("alliance-native-*/fixtures/fixture-sentinel"))), 2)
        self.assertEqual([path for path in (self.repo / "build").rglob("alliance-native-probe*.exe")], [probe])

    def test_python_pin_failure_stops_before_any_build(self):
        _, report = self.run_helper(success=False, failure="check-python")
        self.assertEqual(len(self.read_calls()), 1)
        self.assertIn("CPython 3.14.3 is required", report)

    def test_all_tool_version_and_target_failures_stop_before_configuration(self):
        for action in ("cmake-version", "ninja-version", "compiler-target", "compiler-version", "openssl-version"):
            with self.subTest(action=action):
                self.run_helper(success=False, bad_version=action, expected_logs=len(list((self.repo / "diagnostics").glob("*.txt"))) + 1)
                self.assertNotIn("configure", [call["action"] for call in self.read_calls()])
        self.assertEqual({path.name for path in (self.repo / "build").iterdir()}, {"windows-mingw64", "alliance-native-previous"})

    def test_native_version_command_nonzero_stops_with_saved_log(self):
        self.run_helper(success=False, failure="compiler-target")
        self.assertEqual(self.read_calls()[-1]["action"], "compiler-target")

    def test_configure_failure_stops_build_and_fixture(self):
        _, report = self.run_helper(success=False, failure="configure")
        self.assertEqual(self.read_calls()[-1]["action"], "configure")
        self.assertIn("configuration failed with exit 9", report)

    def test_build_failure_stops_fixture(self):
        _, report = self.run_helper(success=False, failure="build")
        self.assertEqual(self.read_calls()[-1]["action"], "build")
        self.assertIn("build failed with exit 9", report)

    def test_missing_and_empty_build_output_stop_fixture(self):
        for index, outcome in enumerate(("missing", "empty"), 1):
            with self.subTest(outcome=outcome):
                self.environment["NATIVE_OUTPUT"] = outcome
                self.run_helper(success=False, expected_logs=index)
                self.assertNotIn("fixture", [call["action"] for call in self.read_calls()])

    def test_fixture_failure_keeps_scratch_stage_and_log_without_success(self):
        _, report = self.run_helper(success=False, failure="fixture")
        self.assertEqual(self.read_calls()[-1]["action"], "fixture")
        self.assertIn("fixture failed with exit 9", report)
        self.assertEqual(len(list((self.repo / "build").glob("alliance-native-*/alliance-native-probe.exe"))), 1)

    def test_nonwindows_stops_before_native_execution(self):
        self.environment["OS"] = "Linux"
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_public_profile_stops_before_native_execution(self):
        del self.protected[self.profile]
        self.profile.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_missing_source_cmakelist_stops_before_native_execution(self):
        cmakelist = self.source / "CMakeLists.txt"
        del self.protected[cmakelist]
        cmakelist.unlink()
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_empty_ninja_stops_before_native_execution(self):
        self.ninja.write_bytes(b"")
        self.run_helper(success=False)
        self.assertEqual(self.read_calls(), [])

    def test_repeated_runs_preserve_first_build_reports_and_fixtures(self):
        self.run_helper()
        first = {path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        self.run_helper(expected_logs=2)
        for path, content in first.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertEqual(len(list((self.repo / "diagnostics").glob("*.json"))), 2)
        self.assertEqual(len(list((self.repo / "build").glob("alliance-native-*/alliance-native-probe.exe"))), 2)

    def test_diagnostics_creation_error_stops_without_changing_existing_file(self):
        (self.repo / "diagnostics").write_bytes(b"existing file")
        self.run_helper(success=False, expected_logs=0, logged=False)
        self.assertEqual(self.read_calls(), [])
        self.assertEqual((self.repo / "diagnostics").read_bytes(), b"existing file")


if __name__ == "__main__":
    unittest.main()
