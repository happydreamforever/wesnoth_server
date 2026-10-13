"""Run the unchanged LAN helper in real PowerShell with Windows queries mocked.

No Windows network, process, firewall, service or Android calls are made.
Run: python3 tests/test_windows_lan_address.py --powershell /path/to/pwsh
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PWSH = None
HELPER = 'Show-WindowsLanAddress.ps1'
MOCKS = r'''
$ErrorActionPreference='Stop'
$global:LanAddressFixture=Get-Content -LiteralPath $env:LAN_FIXTURE -Raw | ConvertFrom-Json
function Get-NetTCPConnection {
    [CmdletBinding()]param([string]$State)
    if ($State -ne 'Listen') { throw 'Unexpected connection query' }
    if ($global:LanAddressFixture.query_error) { throw 'Injected network query failure' }
    $global:LanAddressFixture.listeners
}
function Get-Process {
    [CmdletBinding()]param([int]$Id)
    if ($global:LanAddressFixture.process_error) { throw 'Injected process lookup failure' }
    [pscustomobject]@{ProcessName=$global:LanAddressFixture.process}
}
function Get-NetAdapter {
    [CmdletBinding()]param([switch]$Physical)
    if (-not $Physical) { throw 'Physical filter missing' }
    $global:LanAddressFixture.adapters
}
function Get-NetIPAddress {
    [CmdletBinding()]param([string]$AddressFamily)
    if ($AddressFamily -ne 'IPv4') { throw 'IPv4 filter missing' }
    $global:LanAddressFixture.addresses
}
function Get-NetConnectionProfile {
    [CmdletBinding()]param()
    $global:LanAddressFixture.profiles
}
& $global:LanAddressFixture.helper -Port $global:LanAddressFixture.port
exit $LASTEXITCODE
'''


class WindowsLanAddressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wesnoth LAN report ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'server with spaces & literal $'
        self.helper = self.repo / 'tools' / HELPER
        self.helper.parent.mkdir(parents=True)
        self.helper.write_bytes((REPO / 'tools' / HELPER).read_bytes())
        self.protected = {}
        for name, data in [('.env', b'SECRET_MUST_NOT_APPEAR'),
                           ('build/windows-mingw64/bin/wesnothd.exe', b'EXISTING_SERVER_SENTINEL'),
                           ('README.md', b'UNRELATED_USER_WORK')]:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.protected[path] = hashlib.sha256(data).hexdigest()
        self.protected[self.helper] = hashlib.sha256(self.helper.read_bytes()).hexdigest()
        self.config = {
            'helper': str(self.helper), 'port': 15000, 'process': 'wesnothd',
            'process_error': False, 'query_error': False,
            'listeners': [
                {'LocalAddress': '0.0.0.0', 'LocalPort': 15000, 'OwningProcess': 500},
                {'LocalAddress': '::', 'LocalPort': 15000, 'OwningProcess': 500},
                {'LocalAddress': '127.0.0.1', 'LocalPort': 5037, 'OwningProcess': 501}],
            'adapters': [
                {'Name': 'Wi-Fi', 'Status': 'Up', 'InterfaceIndex': 42},
                {'Name': 'Ethernet', 'Status': 'Disconnected', 'InterfaceIndex': 43}],
            'addresses': [
                {'IPAddress': '192.168.1.25', 'AddressState': 'Preferred', 'InterfaceIndex': 42},
                {'IPAddress': '192.168.1.30', 'AddressState': 'Tentative', 'InterfaceIndex': 42},
                {'IPAddress': '127.0.0.1', 'AddressState': 'Preferred', 'InterfaceIndex': 42},
                {'IPAddress': '169.254.1.2', 'AddressState': 'Preferred', 'InterfaceIndex': 42},
                {'IPAddress': '172.31.100.1', 'AddressState': 'Preferred', 'InterfaceIndex': 100},
                {'IPAddress': '192.168.2.12', 'AddressState': 'Preferred', 'InterfaceIndex': 43}],
            'profiles': [{'InterfaceIndex': 42, 'NetworkCategory': 'Private'}],
        }

    def run_helper(self, success=True):
        cfg = self.root / 'fixture.json'
        cfg.write_text(json.dumps(self.config))
        launcher = self.root / 'launcher.ps1'
        launcher.write_text(MOCKS)
        process = subprocess.run(
            [PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(launcher)],
            env=dict(os.environ, OS='Windows_NT', LAN_FIXTURE=str(cfg)), cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        self.assertEqual(process.returncode, 0 if success else 1, process.stdout)
        logs = list((self.repo / 'diagnostics').glob('lan-address-*.txt'))
        self.assertEqual(len(logs), 1, process.stdout)
        # Windows PowerShell 5.1 Tee-Object writes UTF-16; PowerShell 7 writes UTF-8.
        raw = logs[0].read_bytes()
        report = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        self.assertEqual('LAN ADDRESS REPORT COMPLETE' in report, success, report)
        self.assertEqual('ERROR:' in report, not success, report)
        self.assertIn('Saved log:', process.stdout)
        self.assertNotIn('SECRET_MUST_NOT_APPEAR', process.stdout + report)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        return report

    def test_wildcard_listener_reports_selected_physical_ipv4_only(self):
        report = self.run_helper()
        self.assertIn('192.168.1.25:15000', report)
        self.assertIn('Private', report)
        self.assertIn('Android connectivity is untested', report)
        for address in ('192.168.1.30', '127.0.0.1', '169.254.1.2', '172.31.100.1', '192.168.2.12'):
            self.assertNotIn(address + ':15000', report)

    def test_multiple_physical_addresses_and_specific_bind(self):
        self.config['adapters'][1]['Status'] = 'Up'
        self.config['listeners'] = [{'LocalAddress': '192.168.2.12', 'LocalPort': 15000, 'OwningProcess': 500}]
        report = self.run_helper()
        self.assertIn('192.168.2.12:15000', report)
        self.assertNotIn('192.168.1.25:15000', report)
        self.assertIn('Unknown', report)

    def test_multiple_physical_addresses_and_wildcard_bind(self):
        self.config['adapters'][1]['Status'] = 'Up'
        report = self.run_helper()
        self.assertIn('192.168.1.25:15000', report)
        self.assertIn('192.168.2.12:15000', report)

    def test_public_profile_is_reported_without_changes(self):
        self.config['profiles'][0]['NetworkCategory'] = 'Public'
        self.assertIn('Public', self.run_helper())

    def test_no_listener_fails_with_saved_metadata(self):
        self.config['listeners'] = []
        self.assertIn('No listener on TCP 15000', self.run_helper(False))

    def test_wrong_process_never_offers_an_address(self):
        self.config['process'] = 'unrelated-app'
        report = self.run_helper(False)
        self.assertIn('unrelated-app', report)
        self.assertNotIn('192.168.1.25:15000', report)

    def test_loopback_only_listener_never_offers_an_address(self):
        self.config['listeners'] = [{'LocalAddress': '127.0.0.1', 'LocalPort': 15000, 'OwningProcess': 500}]
        self.assertNotIn('192.168.1.25:15000', self.run_helper(False))

    def test_ipv6_only_listener_does_not_imply_ipv4_connectivity(self):
        self.config['listeners'] = [{'LocalAddress': '::', 'LocalPort': 15000, 'OwningProcess': 500}]
        self.assertNotIn('192.168.1.25:15000', self.run_helper(False))

    def test_unknown_process_never_offers_an_address(self):
        self.config['process_error'] = True
        self.assertNotIn('192.168.1.25:15000', self.run_helper(False))

    def test_no_active_physical_address_fails(self):
        self.config['adapters'] = []
        self.assertIn('No active physical LAN IPv4 address', self.run_helper(False))

    def test_query_failure_is_saved_and_returns_nonzero(self):
        self.config['query_error'] = True
        self.assertIn('Injected network query failure', self.run_helper(False))

    def test_selected_nondefault_port(self):
        self.config['port'] = 15123
        self.config['listeners'] = [{'LocalAddress': '0.0.0.0', 'LocalPort': 15123, 'OwningProcess': 500}]
        self.assertIn('192.168.1.25:15123', self.run_helper())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--powershell', default=shutil.which('pwsh') or shutil.which('powershell.exe'))
    args = parser.parse_args()
    if not args.powershell:
        parser.error('Provide --powershell; tests never install it.')
    PWSH = str(Path(args.powershell).resolve(strict=True))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WindowsLanAddressTests))
    raise SystemExit(0 if result.wasSuccessful() else 1)
