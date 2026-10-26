"""Execute the Windows bridge-only rebuild helper under PowerShell with simulated native builds."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / 'wesnoth_client/build/host-tools/powershell-7.4.6/pwsh'
SPEC = importlib.util.spec_from_file_location('bridge_build', ROOT / 'tools/build_alliance_bridge.py')
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
INPUTS = BUILD.INPUTS
LEGACY_INPUTS = ('alliance_bridge/CMakeLists.txt', 'alliance_bridge/main.cpp', 'tools/build_alliance_bridge.py')
HEADER = 'alliance_bridge/progression_protocol.hpp'
def quote(value): return "'" + str(value).replace("'", "''") + "'"
def sha(value): return hashlib.sha256(value).hexdigest()

@unittest.skipUnless(PWSH.is_file(), 'Portable PowerShell is unavailable')
class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bridge rebuild '); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.repo = self.base / "server $ & with ' spaces"
        self.stage = self.repo / 'build/alliance-account-bridge'; self.stage.mkdir(parents=True)
        (self.repo / 'tools').mkdir()
        self.helper = self.repo / 'tools/Rebuild-WindowsAllianceBridge.ps1'
        shutil.copyfile(ROOT / 'tools/Rebuild-WindowsAllianceBridge.ps1', self.helper)
        (self.repo / 'tools/Build-WindowsAllianceBridge.ps1').write_text('# fixture delegate')
        for name in INPUTS:
            path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('corrected ' + name)
        self.old_owner = {'format': 1, 'purpose': 'wesnoth-alliance-account-bridge',
                          'inputs': {name: sha(('old ' + name).encode()) for name in LEGACY_INPUTS}}
        self.old_receipt = self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        (self.stage / 'CMakeCache.txt').write_text('completed old configuration')
        self.new = self.base / 'new-stage-fixture'; self.new.mkdir()
        self.new_owner = dict(self.old_owner, inputs={name: sha((self.repo / name).read_bytes()) for name in INPUTS})
        self.complete_stage(self.new, self.new_owner, b'corrected new bridge')
        self.sent = {}
        for name in ('runtime/alliance-transport/server-key.pem', 'runtime/alliance-transport/public-profile.json',
                     'runtime/alliance/config.json', 'build/windows-mingw64/keep', 'build/alliance-venv/keep',
                     'build/alliance-account-bridge-before-identity-fix-old/keep', '.env'):
            path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('PRIVATE_SENTINEL_' + name)
            self.sent[path] = path.read_bytes()
        profile = self.base / 'Local AppData/WesnothAlliance/runtime/data'; profile.parent.mkdir(parents=True)
        profile.write_text('profile database sentinel'); self.sent[profile] = profile.read_bytes()
        client = self.base / 'wesnoth_client/build/android-game/keep'; client.parent.mkdir(parents=True)
        client.write_text('Android stage sentinel'); self.sent[client] = client.read_bytes()
        self.before = {x.name:x.read_bytes() for x in self.stage.iterdir()}
        self.calls = self.base / 'calls.jsonl'
    def complete_stage(self, stage, owner, executable):
        (stage / 'owner.json').write_text(json.dumps(owner, sort_keys=True))
        name = 'alliance-account-bridge.exe'; (stage / name).write_bytes(executable)
        receipt = {'binding': owner, 'executable': {'name': name, 'bytes': len(executable), 'sha256': sha(executable)}, 'versions': {'fixture': True}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True))
        return receipt
    def invoke(self, *, running=0, second_running=False, query_error=False, rename_error=False, build_exit=0, partial=False):
        self.before_invoke = {p.name:p.read_bytes() for p in self.stage.iterdir()}
        wrapper = self.base / 'wrapper.ps1'
        wrapper.write_text(f'''$ErrorActionPreference = 'Stop'
$script:queries = 0
function global:Get-CimInstance {{
    $script:queries++
    if ({quote(str(query_error))} -eq 'True') {{ throw 'fixture process query denied' }}
    if ({running} -gt 0 -or ({quote(str(second_running))} -eq 'True' -and $script:queries -gt 1)) {{ [pscustomobject]@{{Name='alliance-account-bridge.exe';ProcessId=42}} }}
}}
function global:Rename-Item {{
    param($LiteralPath, $NewName, $ErrorAction)
    if ({quote(str(rename_error))} -eq 'True') {{ throw 'fixture sharing conflict' }}
    Microsoft.PowerShell.Management\\Rename-Item -LiteralPath $LiteralPath -NewName $NewName -ErrorAction Stop
}}
function global:powershell.exe {{
    [IO.File]::AppendAllText({quote(self.calls)}, ((@($args) | ConvertTo-Json -Compress) + "`n"))
    $null = New-Item -ItemType Directory -Path {quote(self.stage)}
    if ({quote(str(partial))} -ne 'True' -and {build_exit} -eq 0) {{
        Copy-Item -LiteralPath {quote(self.new / 'owner.json')}, {quote(self.new / 'receipt.json')}, {quote(self.new / 'alliance-account-bridge.exe')} -Destination {quote(self.stage)}
    }}
    $global:LASTEXITCODE = {build_exit}
    if ($global:LASTEXITCODE -eq 0) {{ 'ALLIANCE ACCOUNT BRIDGE BUILD PASSED' }}
}}
& {quote(self.helper)} -MsysRoot 'D:\\Test\\wesnoth-setup\\msys64' -PythonPath 'C:\\Native Python\\python.exe' -CMakePath 'C:\\Program Files\\CMake\\bin\\cmake.exe'
exit $LASTEXITCODE
''')
        env = dict(os.environ, OS='Windows_NT', LOCALAPPDATA=str(self.base / 'Local AppData'))
        process = subprocess.run([str(PWSH), '-NoProfile', '-File', str(wrapper)], env=env, capture_output=True, text=True, timeout=15)
        self.output = process.stdout + process.stderr
        self.invocations = [json.loads(x) for x in self.calls.read_text().splitlines()] if self.calls.exists() else []
        self.backups = [x for x in (self.repo / 'build').glob('alliance-account-bridge-before-update-*') if not x.name.endswith('-old')]
        self.assertNotIn('PRIVATE_SENTINEL_', self.output)
        for path, data in self.sent.items(): self.assertEqual(path.read_bytes(), data)
        self.logs = list((self.repo / 'diagnostics').glob('alliance-bridge-rebuild-*.txt'))
        self.assertEqual(len(self.logs), 1, self.output)
        self.assertIn('Saved rebuild log:', self.output)
        return process.returncode
    def no_build(self):
        self.assertFalse(self.backups); self.assertFalse(self.invocations)
        self.assertEqual({p.name:p.read_bytes() for p in self.stage.iterdir()}, self.before_invoke)
        self.assertNotIn('ALLIANCE ACCOUNT BRIDGE REBUILD PASSED', self.output)
        self.assertIn('ERROR:', self.logs[0].read_text())
    def assert_success(self):
        self.assertEqual(self.invoke(), 0, self.output)
        self.assertEqual(len(self.backups), 1)
        self.assertEqual({p.name:p.read_bytes() for p in self.backups[0].iterdir()}, self.before)
        self.assertEqual(self.invocations, [['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(self.repo / 'tools/Build-WindowsAllianceBridge.ps1'), '-MsysRoot', r'D:\Test\wesnoth-setup\msys64',
            '-PythonPath', r'C:\Native Python\python.exe', '-CMakePath', r'C:\Program Files\CMake\bin\cmake.exe']])
        self.assertEqual((self.stage / 'alliance-account-bridge.exe').read_bytes(), b'corrected new bridge')
        self.assertEqual(json.loads((self.stage / 'owner.json').read_text()), self.new_owner)
        self.assertIn('ALLIANCE ACCOUNT BRIDGE REBUILD PASSED', self.logs[0].read_text())
    def current_old_stage(self):
        self.old_owner['inputs'] = {name: sha(('old ' + name).encode()) for name in INPUTS}
        self.old_receipt = self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.before = {p.name:p.read_bytes() for p in self.stage.iterdir()}
    def failed_after_build(self):
        self.assertEqual(len(self.backups), 1); self.assertEqual(len(self.invocations), 1)
        self.assertEqual({p.name:p.read_bytes() for p in self.backups[0].iterdir()}, self.before)
        for name in ('owner.json', 'receipt.json', 'alliance-account-bridge.exe'):
            self.assertEqual((self.stage / name).read_bytes(), (self.new / name).read_bytes())
        self.assertNotIn('ALLIANCE ACCOUNT BRIDGE REBUILD PASSED', self.output)
    def test_legacy_three_input_stage_rebuilds_with_current_builder_inputs(self):
        self.assertIn(HEADER, INPUTS)
        self.assert_success()
    def test_current_six_input_stage_rebuilds_and_preserves_old_build(self):
        self.current_old_stage()
        self.assert_success()
    def test_previous_five_input_stage_is_preserved_before_v3_rebuild(self):
        previous = [name for name in INPUTS if name != 'alliance_bridge/flexible_protocol.hpp']
        self.old_owner['inputs'] = {name: sha(('old ' + name).encode()) for name in previous}
        self.old_receipt = self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.before = {p.name:p.read_bytes() for p in self.stage.iterdir()}
        self.assert_success()
    def test_previous_four_input_stage_is_preserved_before_v2_rebuild(self):
        self.old_owner['inputs'] = {name: sha(('old ' + name).encode()) for name in (*LEGACY_INPUTS, HEADER)}
        self.old_receipt = self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.before = {p.name:p.read_bytes() for p in self.stage.iterdir()}
        self.assert_success()
    def test_running_bridge_is_not_stopped_or_renamed(self):
        self.assertEqual(self.invoke(running=1), 1); self.no_build()
    def test_bridge_starting_during_check_blocks_rename(self):
        self.assertEqual(self.invoke(second_running=True), 1); self.no_build()
    def test_process_query_failure_preserves_stage(self):
        self.assertEqual(self.invoke(query_error=True), 1); self.no_build()
    def test_incomplete_stage_is_preserved(self):
        (self.stage / 'receipt.json').unlink(); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_changed_executable_is_preserved(self):
        (self.stage / 'alliance-account-bridge.exe').write_bytes(b'changed'); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_ownership_mismatch_is_rejected(self):
        owner = dict(self.old_owner, purpose='unrelated-stage'); (self.stage / 'owner.json').write_text(json.dumps(owner))
        self.assertEqual(self.invoke(), 1); self.no_build()
    def test_receipt_binding_mismatch_is_rejected(self):
        receipt = json.loads(json.dumps(self.old_receipt)); receipt['binding']['inputs'][INPUTS[0]] = '0' * 64
        (self.stage / 'receipt.json').write_text(json.dumps(receipt)); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_current_header_binding_mismatch_is_rejected(self):
        self.current_old_stage()
        receipt = json.loads(json.dumps(self.old_receipt)); receipt['binding']['inputs'][HEADER] = '0' * 64
        (self.stage / 'receipt.json').write_text(json.dumps(receipt)); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_current_owner_with_legacy_receipt_is_rejected(self):
        self.current_old_stage()
        receipt = json.loads(json.dumps(self.old_receipt)); del receipt['binding']['inputs'][HEADER]
        (self.stage / 'receipt.json').write_text(json.dumps(receipt)); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_legacy_owner_with_current_receipt_is_rejected(self):
        receipt = json.loads(json.dumps(self.old_receipt)); receipt['binding']['inputs'][HEADER] = '0' * 64
        (self.stage / 'receipt.json').write_text(json.dumps(receipt)); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_old_stage_with_unknown_fourth_input_is_rejected(self):
        self.current_old_stage()
        self.old_owner['inputs']['alliance_bridge/unknown.hpp'] = self.old_owner['inputs'].pop(HEADER)
        self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.assertEqual(self.invoke(), 1); self.no_build()
    def test_old_stage_with_wrong_case_header_key_is_rejected(self):
        self.current_old_stage()
        self.old_owner['inputs'][HEADER.upper()] = self.old_owner['inputs'].pop(HEADER)
        self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.assertEqual(self.invoke(), 1); self.no_build()
    def test_current_header_with_invalid_hash_is_rejected(self):
        self.current_old_stage(); self.old_owner['inputs'][HEADER] = 'invalid'
        self.complete_stage(self.stage, self.old_owner, b'completed old bridge')
        self.assertEqual(self.invoke(), 1); self.no_build()
    def test_invalid_source_binding_is_rejected(self):
        owner = json.loads(json.dumps(self.old_owner)); owner['inputs'][INPUTS[0]] = 'invalid'
        self.complete_stage(self.stage, owner, b'completed old bridge'); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_oversized_metadata_is_rejected(self):
        (self.stage / 'owner.json').write_bytes(b' ' * 32769); self.assertEqual(self.invoke(), 1); self.no_build()
    def test_malformed_metadata_is_not_reflected_in_logs(self):
        sentinel = 'MALFORMED_METADATA_PRIVATE_SENTINEL'
        (self.stage / 'receipt.json').write_text('{"private":"' + sentinel + '", invalid')
        self.assertEqual(self.invoke(), 1); self.no_build()
        self.assertNotIn(sentinel, self.output); self.assertNotIn(sentinel, self.logs[0].read_text())
        self.assertIn('metadata could not be read or parsed', self.logs[0].read_text())
    def test_stage_link_is_rejected(self):
        target = self.repo / 'build/linked-stage-target'; self.stage.rename(target); self.stage.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.invoke(), 1); self.no_build()
        self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()}, self.before)
    def test_rename_sharing_failure_prevents_build(self):
        self.assertEqual(self.invoke(rename_error=True), 1); self.no_build()
        self.assertEqual({p.name:p.read_bytes() for p in self.stage.iterdir()}, self.before)
    def test_native_build_failure_preserves_backup_and_partial_stage(self):
        self.assertEqual(self.invoke(build_exit=1), 1); self.assertEqual(len(self.backups), 1); self.assertEqual(len(self.invocations), 1)
        self.assertEqual({p.name:p.read_bytes() for p in self.backups[0].iterdir()}, self.before)
        self.assertTrue(self.stage.is_dir()); self.assertIn('updated bridge build failed', self.logs[0].read_text())
        self.assertNotIn('ALLIANCE ACCOUNT BRIDGE REBUILD PASSED', self.output)
    def test_zero_exit_without_completed_receipt_cannot_pass(self):
        self.assertEqual(self.invoke(partial=True), 1); self.assertEqual(len(self.backups), 1)
        self.assertNotIn('ALLIANCE ACCOUNT BRIDGE REBUILD PASSED', self.output)
    def test_new_build_with_stale_sources_cannot_pass(self):
        stale = dict(self.new_owner, inputs={name: sha(('old ' + name).encode()) for name in INPUTS})
        self.complete_stage(self.new, stale, b'old source rebuilt')
        self.assertEqual(self.invoke(), 1); self.failed_after_build()
        self.assertIn('does not match the current sources', self.logs[0].read_text())
    def test_new_build_without_header_binding_cannot_pass(self):
        del self.new_owner['inputs'][HEADER]
        self.complete_stage(self.new, self.new_owner, b'corrected new bridge')
        self.assertEqual(self.invoke(), 1); self.failed_after_build()
    def test_new_build_with_replaced_header_key_cannot_pass(self):
        self.new_owner['inputs']['alliance_bridge/unknown.hpp'] = self.new_owner['inputs'].pop(HEADER)
        self.complete_stage(self.new, self.new_owner, b'corrected new bridge')
        self.assertEqual(self.invoke(), 1); self.failed_after_build()
    def test_new_build_with_changed_header_source_cannot_pass(self):
        (self.repo / HEADER).write_text('header changed after build receipt')
        self.assertEqual(self.invoke(), 1); self.failed_after_build()
        self.assertIn('does not match the current sources', self.logs[0].read_text())
    def test_new_build_with_mismatched_header_binding_cannot_pass(self):
        receipt = json.loads((self.new / 'receipt.json').read_text()); receipt['binding']['inputs'][HEADER] = '0' * 64
        (self.new / 'receipt.json').write_text(json.dumps(receipt))
        self.assertEqual(self.invoke(), 1); self.failed_after_build()
        self.assertIn('ownership and receipt disagree', self.logs[0].read_text())
    def test_new_build_with_bad_artifact_cannot_pass(self):
        (self.new / 'alliance-account-bridge.exe').write_bytes(b'changed after receipt')
        self.assertEqual(self.invoke(), 1); self.failed_after_build()

if __name__ == '__main__': unittest.main()
