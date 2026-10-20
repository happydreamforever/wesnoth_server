"""Execute the recovery orchestration with Linux PowerShell and native shims.

The real helper uses Windows handle identity and byte locking. The shims let the
same PowerShell path/JSON/liveness/backup flow execute here; they do not establish
Windows API or Windows Python/.NET lock interoperability acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = ROOT / "tools/Repair-WindowsAllianceRuntimeLock.ps1"
START = "2026-10-20T12:36:21.894725+00:00"

NATIVE_SHIM = r"""
using System;
using System.Collections.Generic;
using System.IO;
namespace WesnothAllianceRecovery {
    public sealed class FileMetadata {
        public string Identity;
        public uint Links;
        public uint Attributes;
        public ulong Length;
    }
    public static class NativeFiles {
        private static Dictionary<FileStream,string> paths = new Dictionary<FileStream,string>();
        public static FileStream Open(string path, string kind) {
            var stream = new FileStream(path,
                kind == "guard" ? FileMode.OpenOrCreate : FileMode.Open,
                kind == "guard" ? FileAccess.ReadWrite : FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            paths.Add(stream, path);
            return stream;
        }
        public static FileMetadata Inspect(FileStream stream) {
            string path = paths[stream];
            string file = Path.GetFileName(path);
            string mode = Environment.GetEnvironmentVariable("RECOVERY_CASE");
            if (mode == "identity-error") throw new IOException("Simulated native identity error");
            return new FileMetadata {
                Identity = path,
                Links = mode == "hardlink-" + file ? 2U : 1U,
                Attributes = (uint)File.GetAttributes(path),
                Length = (ulong)stream.Length
            };
        }
        public static void Preserve(FileStream stream, string destination) {
            string mode = Environment.GetEnvironmentVariable("RECOVERY_CASE");
            if (mode == "rename-error") throw new IOException("Simulated sharing failure");
            if (mode == "backup-exists") File.WriteAllText(destination, "existing backup");
            File.Move(paths[stream], destination);
        }
    }
}
"""


@unittest.skipUnless(PWSH.is_file(), "Linux PowerShell host unavailable")
class RecoveryPowerShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alliance recovery ")
        self.base = Path(self.temp.name)
        self.repo = self.base / "repository"
        self.drive = self.base / "profile drive"
        self.runtime = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime [local]"
        self.runtime.mkdir(parents=True)
        (self.repo / "tools").mkdir(parents=True)
        for name in ("Alliance-Common.ps1", HELPER.name):
            shutil.copy2(ROOT / "tools" / name, self.repo / "tools" / name)
        self.marker = self.runtime / "operation.lock"
        self.original = json.dumps({"pid": 7400, "started_at": START}).encode()
        self.marker.write_bytes(self.original)
        self.owner = self.runtime / "owner.json"
        self.owner.write_text(json.dumps({"purpose": "wesnoth-alliance-local", "format": 1}))
        self.protected = {}
        for name in ("config.json", "root.json", "keyfile", "mongo.json", "data/WiredTiger.turtle", "logs/mongodb.log"):
            path = self.runtime / name
            path.parent.mkdir(exist_ok=True)
            data = ("private fixture " + name).encode()
            path.write_bytes(data)
            self.protected[path] = data
        (self.base / "native-shim.cs").write_text(NATIVE_SHIM)
        self.driver = self.base / "driver.ps1"
        self.driver.write_text(r"""
$ErrorActionPreference = 'Stop'
$null = New-PSDrive -Name C -PSProvider FileSystem -Root $env:RECOVERY_DRIVE
Add-Type -Path $env:RECOVERY_SHIM
$script:processQueries = 0
$script:listenerQueries = 0
function Get-CimInstance {
    [CmdletBinding()] param($ClassName, $Filter, $Property)
    $script:processQueries++
    Add-Content -LiteralPath $env:RECOVERY_CALLS -Value ('process ' + $script:processQueries + ' ' + $Filter)
    if ($env:RECOVERY_CASE -eq 'process-error') { throw 'Simulated CIM query error' }
    if ($env:RECOVERY_CASE -eq 'process-live' -or
        ($env:RECOVERY_CASE -eq 'process-late' -and $script:processQueries -eq 2)) {
        [pscustomobject]@{ProcessId=7400;Name='python.exe'}
    }
    if ($env:RECOVERY_CASE -eq 'pid-reused') {
        [pscustomobject]@{ProcessId=7400;Name='unrelated.exe'}
    }
}
function Get-NetTCPConnection {
    [CmdletBinding()] param($State)
    $script:listenerQueries++
    Add-Content -LiteralPath $env:RECOVERY_CALLS -Value ('listener ' + $script:listenerQueries)
    if ($env:RECOVERY_CASE -eq 'listener-error') { throw 'Simulated listener query error' }
    if ($env:RECOVERY_CASE -eq 'listener-live' -or
        ($env:RECOVERY_CASE -eq 'listener-late' -and $script:listenerQueries -eq 2)) {
        [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=27018;OwningProcess=5555}
    } else {
        [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=12345;OwningProcess=5555}
    }
    if ($env:RECOVERY_CASE -eq 'marker-changed' -and $script:listenerQueries -eq 1) {
        [IO.File]::WriteAllText($env:RECOVERY_MARKER, '{"pid": 7401, "started_at": "2026-10-20T12:36:21.894725+00:00"}')
    }
}
$arguments = @{RuntimeRoot=$env:RECOVERY_ROOT}
if ($env:RECOVERY_EXPECTED -ne 'omit') {
    $arguments.ExpectedPid = [int]$env:RECOVERY_EXPECTED_PID
    if ($env:RECOVERY_EXPECTED -ne 'half') { $arguments.ExpectedStartedAt = $env:RECOVERY_START }
}
& $env:RECOVERY_HELPER @arguments
exit $LASTEXITCODE
""")
        self.calls = self.base / "calls.txt"
        self.env = {
            **os.environ, "OS": "Windows_NT",
            "RECOVERY_DRIVE": str(self.drive),
            "RECOVERY_SHIM": str(self.base / "native-shim.cs"),
            "RECOVERY_HELPER": str(self.repo / "tools" / HELPER.name),
            "RECOVERY_CALLS": str(self.calls),
            "RECOVERY_ROOT": r"C:\Users\Uni\AppData\Local\WesnothAlliance\runtime [local]",
            "RECOVERY_MARKER": str(self.marker),
            "RECOVERY_START": START,
            "RECOVERY_EXPECTED_PID": "7400",
        }

    def tearDown(self):
        for path, original in self.protected.items():
            self.assertEqual(path.read_bytes(), original, path)
        self.temp.cleanup()

    def invoke(self, case="", **env):
        return subprocess.run(
            [str(PWSH), "-NoProfile", "-File", str(self.driver)],
            env={**self.env, "RECOVERY_CASE": case, **env},
            capture_output=True, text=True, timeout=30,
        )

    def assert_failed(self, result, *, marker=None):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("ALLIANCE RUNTIME LOCK RECOVERY PASSED", result.stdout)
        self.assertIn("Saved log:", result.stdout)
        self.assertEqual(self.marker.read_bytes(), self.original if marker is None else marker)
        self.assertTrue(list((self.repo / "diagnostics").glob("*.txt")))

    def test_success_preserves_exact_marker_and_permanent_guard(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALLIANCE RUNTIME LOCK RECOVERY PASSED", result.stdout)
        self.assertFalse(self.marker.exists())
        backups = list(self.runtime.glob("operation.lock.recovered-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertEqual((self.runtime / "operation.guard").read_bytes(), b"\0")
        calls = self.calls.read_text()
        self.assertIn("process 2 ", calls)
        self.assertIn("listener 2", calls)
        self.assertIn("Name = 'pythonw.exe'", calls)
        self.assertIn("OR ProcessId = 7400", calls)
        for private in self.protected.values():
            self.assertNotIn(private.decode(), result.stdout + result.stderr)

    def test_optional_evidence_can_be_omitted_but_not_half_supplied(self):
        result = self.invoke(RECOVERY_EXPECTED="half")
        self.assert_failed(result)
        self.assertFalse(self.calls.exists())
        result = self.invoke(RECOVERY_EXPECTED="omit")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.marker.exists())

    def test_expected_identity_mismatch_stops_before_liveness(self):
        for env in ({"RECOVERY_EXPECTED_PID": "7401"}, {"RECOVERY_START": START + "0"}):
            with self.subTest(env=env):
                result = self.invoke(**env)
                self.assert_failed(result)
                self.assertIn("does not match the supplied PID/timestamp", result.stdout)
                self.assertFalse(self.calls.exists())

    def test_live_owner_reused_pid_and_query_errors_preserve_marker(self):
        for case in ("process-live", "pid-reused", "process-error", "listener-live", "listener-error"):
            with self.subTest(case=case):
                result = self.invoke(case)
                self.assert_failed(result)
                expected = {
                    "process-live": "process is still running",
                    "pid-reused": "process is still running",
                    "process-error": "Simulated CIM query error",
                    "listener-live": "port has a listener",
                    "listener-error": "Simulated listener query error",
                }[case]
                self.assertIn(expected, result.stdout)
                self.assertIn("process 1 ", self.calls.read_text())

    def test_late_process_or_listener_blocks_rename(self):
        for case in ("process-late", "listener-late"):
            with self.subTest(case=case):
                result = self.invoke(case)
                self.assert_failed(result)
                self.assertIn("process 2 ", self.calls.read_text())
                self.assertIn("process is still running" if case == "process-late" else "port has a listener", result.stdout)
                self.assertFalse(list(self.runtime.glob("operation.lock.recovered-*")))

    def test_changed_marker_is_preserved_without_success(self):
        result = self.invoke("marker-changed")
        changed = b'{"pid": 7401, "started_at": "2026-10-20T12:36:21.894725+00:00"}'
        self.assert_failed(result, marker=changed)
        self.assertIn("changed during recovery", result.stdout)
        self.assertFalse(list(self.runtime.glob("operation.lock.recovered-*")))

    def test_malformed_oversized_and_unsupported_marker_stop(self):
        for data in (
            b"not json", b"x" * 4097, b"", b"\xff",
            b'{"pid":7400,"pid":7400,"started_at":"' + START.encode() + b'"}',
            json.dumps({"pid": True, "started_at": START}).encode(),
            json.dumps({"pid": 7400.0, "started_at": START}).encode(),
            json.dumps({"pid": 0, "started_at": START}).encode(),
            json.dumps({"pid": 7400, "started_at": "not a date"}).encode(),
            json.dumps({"pid": 7400, "started_at": "2026-02-31T12:36:21+00:00"}).encode(),
        ):
            with self.subTest(data=data[:80]):
                self.marker.write_bytes(data)
                self.assert_failed(self.invoke(), marker=data)
                self.assertFalse(self.calls.exists())

    def test_missing_or_foreign_owner_stops_without_creating_guard(self):
        for data in (b"{}", b'{"purpose":"another-app","format":1}', b'{"purpose":"wesnoth-alliance-local","format":true}'):
            with self.subTest(data=data):
                self.owner.write_bytes(data)
                self.assert_failed(self.invoke())
                self.assertFalse((self.runtime / "operation.guard").exists())
        self.owner.unlink()
        self.assert_failed(self.invoke())
        self.assertFalse((self.runtime / "operation.guard").exists())

    def test_missing_marker_does_not_start_database_or_create_guard(self):
        self.marker.unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No legacy operation.lock", result.stdout)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.runtime / "operation.guard").exists())

    def test_native_identity_errors_and_link_counts_fail_closed(self):
        for case in ("identity-error", "hardlink-owner.json", "hardlink-operation.lock", "hardlink-operation.guard"):
            with self.subTest(case=case):
                self.assert_failed(self.invoke(case))
                self.assertFalse(self.calls.exists())

    def test_redirected_marker_and_runtime_parent_stop(self):
        original = self.base / "linked marker"
        original.write_bytes(self.original)
        self.marker.unlink()
        self.marker.symlink_to(original)
        self.assert_failed(self.invoke())
        self.assertEqual(original.read_bytes(), self.original)
        self.marker.unlink()
        self.marker.write_bytes(self.original)
        (self.drive / "redirect").symlink_to(self.runtime, target_is_directory=True)
        self.assert_failed(self.invoke(RECOVERY_ROOT=r"C:\redirect"))

    def test_invalid_and_unc_runtime_paths_stop_without_query(self):
        for root in ("", "relative", r"\\server\share\game", r"C:\Users\..\game", r"C:\missing"):
            with self.subTest(root=root):
                self.assert_failed(self.invoke(RECOVERY_ROOT=root))
                self.assertFalse(self.calls.exists())

    def test_existing_valid_guard_is_reused_and_bad_guard_preserved(self):
        guard = self.runtime / "operation.guard"
        for data in (b"\1", b"\0\0"):
            with self.subTest(data=data):
                guard.write_bytes(data)
                self.assert_failed(self.invoke())
                self.assertEqual(guard.read_bytes(), data)
        guard.write_bytes(b"\0")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(guard.read_bytes(), b"\0")

    def test_rename_failure_and_backup_collision_preserve_original(self):
        for case in ("rename-error", "backup-exists"):
            with self.subTest(case=case):
                result = self.invoke(case)
                self.assert_failed(result)
                self.assertIn("listener 2", self.calls.read_text())
                self.assertIn("Simulated sharing failure" if case == "rename-error" else "already exists", result.stdout)
        backups = list(self.runtime.glob("operation.lock.recovered-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "existing backup")

    def test_actual_dotnet_byte_lock_contention_stops_recovery(self):
        guard = self.runtime / "operation.guard"
        guard.write_bytes(b"\0")
        holder = self.base / "holder.ps1"
        ready = self.base / "holder-ready"
        holder.write_text(
            "$f = [IO.File]::Open($env:RECOVERY_GUARD, 'Open', 'ReadWrite', 'ReadWrite')\n"
            "try {\n"
            " $f.Lock(0,1)\n"
            " [IO.File]::WriteAllText($env:RECOVERY_READY, 'ready')\n"
            " [Console]::ReadLine() | Out-Null\n"
            "} finally { $f.Dispose() }\n"
        )
        process = subprocess.Popen(
            [str(PWSH), "-NoProfile", "-File", str(holder)],
            env={**self.env, "RECOVERY_GUARD": str(guard), "RECOVERY_READY": str(ready)},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            import time
            for _ in range(100):
                if ready.exists() or process.poll() is not None:
                    break
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "PowerShell byte-lock holder did not become ready")
            result = self.invoke()
            self.assert_failed(result)
            self.assertIn("Could not acquire the runtime guard", result.stdout)
            self.assertFalse(self.calls.exists())
        finally:
            stdout, stderr = process.communicate("\n", timeout=15)
            self.assertEqual(process.returncode, 0, stdout + stderr)


class RecoveryNativeContractTests(unittest.TestCase):
    def test_windows_native_contract_preserves_marker_by_handle_without_overwrite(self):
        source = HELPER.read_text()
        self.assertIn('CreateFileW(path, access, share, IntPtr.Zero,', source)
        self.assertIn('0x00200000U', source)  # FILE_FLAG_OPEN_REPARSE_POINT
        self.assertIn('GetFileInformationByHandle(stream.SafeFileHandle', source)
        self.assertIn('$metadata.Links -ne 1', source)
        self.assertIn('access |= 0x00010000U', source)  # DELETE access for rename
        self.assertIn('SetFileInformationByHandle(stream.SafeFileHandle, 3, buffer', source)
        self.assertIn('Marshal.Copy(new byte[size], 0, buffer, size)', source)
        self.assertNotIn('[IO.File]::Delete', source)
        self.assertNotIn('Stop-Process', source)
        self.assertNotIn('Initialize-WindowsAlliance', source)
        self.assertNotIn('MongoClient', source)


if __name__ == "__main__":
    unittest.main()
