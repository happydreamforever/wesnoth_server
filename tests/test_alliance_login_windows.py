"""Run the login wrapper with simulated Windows paths and an isolated Python.

The PTY case exercises inherited terminal streams and hidden input on Linux;
actual Windows 5.1/getpass console behavior still requires user acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = "Test-WindowsAllianceLogin.ps1"
VERIFIED = "ALLIANCE LOGIN DIAGNOSTIC REPORT VERIFIED"
FAKE_PYTHON = r'''#!/usr/bin/python3
import getpass, json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['LOGIN_CALLS'], 'a') as output:
    output.write(json.dumps({'executable':sys.argv[0], 'args':args,
                            'cwd':os.getcwd(), 'path':os.environ['PATH'],
                            'tty':[os.isatty(fd) for fd in (0,1,2)]}) + '\n')
mode = os.environ.get('LOGIN_MODE', '')
code = int(os.environ.get('LOGIN_EXIT', '0'))
if os.environ.get('LOGIN_INTERACTIVE') == 'yes':
    if not all(os.isatty(fd) for fd in (0,1,2)):
        print('Fixture did not inherit all terminal streams.')
        sys.exit(1)
    entered = getpass.getpass('Fixture hidden value: ')
    if entered != 'FIXTURE_PASSWORD_SENTINEL':
        sys.exit(1)
    del entered
    print('HIDDEN INPUT RECEIVED')
report = pathlib.Path(args[args.index('--report') + 1])
username = args[args.index('--username') + 1]
data = {'format':1, 'purpose':'wesnoth-alliance-login-check',
        'status':'failed' if code else 'completed', 'outcome':'password_match',
        'username':username, 'endpoint':'127.0.0.1:27018', 'database':'wesnoth_game',
        'account':{'found':True,'id':'11111111-1111-4111-8111-111111111111',
                   'role':'player','status':'active'},
        'password_check':'match',
        'rate_limit':{'count':0,'next_attempt_blocked':False,'window_ends_at':None},
        'database_writes':False}
if mode in ('mismatch','missing_account','ineligible','invalid_hash','unsupported_hash'):
    data['outcome'] = {'mismatch':'password_mismatch','missing_account':'account_missing',
                       'ineligible':'account_ineligible','invalid_hash':'invalid_stored_hash',
                       'unsupported_hash':'unsupported_stored_hash'}[mode]
    data['password_check'] = {'mismatch':'mismatch','invalid_hash':'invalid_hash',
                             'unsupported_hash':'unsupported_hash'}.get(mode,'not_checked')
if mode in ('format','purpose','status','username','endpoint','database','database_writes'):
    data[mode] = {'format':2,'purpose':'other','status':'passed','username':'OtherPlayer',
                  'endpoint':'203.0.113.1:27018','database':'other','database_writes':True}[mode]
if mode == 'writes_string': data['database_writes'] = 'false'
if mode == 'writes_missing': del data['database_writes']
if mode == 'unknown_outcome': data['outcome'] = 'unknown'
if mode == 'wrong_password_check': data['password_check'] = 'mismatch'
if mode == 'symlink':
    report.symlink_to(os.environ['LOGIN_REPORT_TARGET'])
elif mode != 'missing':
    with report.open('x') as output:
        if mode == 'malformed': output.write('{"private":"PRIVATE_JSON_SENTINEL", invalid')
        elif mode == 'oversized': output.write(' ' * 32769)
        elif mode != 'empty': json.dump(data, output)
print('Simulated sanitized diagnostic output', flush=True)
sys.exit(code)
'''
LAUNCHER = r'''
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $env:LOGIN_SETTINGS -Raw | ConvertFrom-Json
$null = New-PSDrive -Name C -PSProvider FileSystem -Root $env:LOGIN_DRIVE
function Get-Content {
    [CmdletBinding()]param([string]$LiteralPath, [switch]$Raw, [string]$Encoding)
    if (-not $LiteralPath.EndsWith('.json') -or -not $LiteralPath.Contains('alliance-login-')) {
        throw 'PRIVATE_CONFIG_READ_SENTINEL'
    }
    Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw -Encoding UTF8
}
function Get-Item {
    [CmdletBinding()]param([string]$LiteralPath, [switch]$Force)
    if ($settings.metadata_error) { throw 'PRIVATE_METADATA_ERROR_SENTINEL' }
    Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
}
function Start-Transcript { throw 'PRIVATE_TRANSCRIPT_SENTINEL' }
function Stop-Transcript { throw 'PRIVATE_TRANSCRIPT_SENTINEL' }
function Start-Process { throw 'Forbidden process start.' }
function Stop-Process { throw 'Forbidden process stop.' }
function powershell.exe { throw 'Forbidden secondary helper.' }
function sc.exe { throw 'Forbidden service control.' }
$env:PATH = $env:LOGIN_BASE_PATH
$beforePath = $env:PATH
$beforeLocation = (Get-Location).Path
$arguments = @{}
if ($settings.PSObject.Properties.Name -contains 'runtime_root') { $arguments.RuntimeRoot = $settings.runtime_root }
if ($settings.PSObject.Properties.Name -contains 'username') { $arguments.Username = $settings.username }
& $settings.helper @arguments
$result = $LASTEXITCODE
if ($env:PATH -cne $beforePath) { throw 'Helper changed PATH.' }
if ((Get-Location).Path -cne $beforeLocation) { throw 'Helper changed working directory.' }
Write-Host 'CALLER STATE PRESERVED'
exit $result
'''


@unittest.skipUnless(PWSH.is_file(), "Existing Linux PowerShell unavailable; no tools are installed")
class LoginWindowsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="alliance login PS ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        for name in (HELPER, "Alliance-Common.ps1"):
            shutil.copyfile(ROOT / "tools" / name, self.tools / name)
        self.helper = self.tools / HELPER
        self.python = self.repo / "build/alliance-venv/Scripts/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.diagnostic = self.tools / "check_alliance_login.py"
        self.diagnostic.write_text("# simulated safe diagnostic\n")
        self.drive = self.root / "profile drive"
        self.runtime = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime"
        self.runtime.mkdir(parents=True)
        for path, content in {
            self.repo / ".env": b"PRIVATE_ENV_SENTINEL",
            self.repo / "runtime/alliance/config.json": b"PRIVATE_OLD_CONFIG_SENTINEL",
            self.repo / "runtime/alliance-transport/server-key.pem": b"PRIVATE_IDENTITY_SENTINEL",
            self.repo / "build/alliance-account-bridge/alliance-account-bridge.exe": b"EXISTING_BRIDGE",
            self.repo / "build/alliance-venv/alliance-owned.json": b"EXISTING_VENV_RECEIPT",
            self.repo / "build/alliance-mongodb/bin/mongod.exe": b"EXISTING_MONGODB",
            self.repo / "README.md": b"UNRELATED_USER_CHANGES",
            self.repo / "diagnostics/alliance-login-previous.json": b"PREVIOUS_REPORT",
            self.runtime / "config.json": b"PRIVATE_PROFILE_CONFIG_SENTINEL",
            self.runtime / "root.json": b"PRIVATE_PROFILE_ROOT_SENTINEL",
            self.runtime / "data/WiredTiger.turtle": b"EXISTING_DATABASE",
            self.runtime / "logs/mongodb.log": b"EXISTING_DATABASE_LOG",
            self.runtime / "operation.lock": b"EXISTING_OPERATION_LOCK",
            self.root / "wesnoth_client/build/android-account-game/prefix/game.apk": b"EXISTING_APK",
        }.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.protected = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in self.root.rglob('*') if p.is_file()}
        self.calls = self.root / "calls.jsonl"
        self.settings_path = self.root / "settings.json"
        self.settings = {"helper": str(self.helper), "metadata_error": False}
        self.launcher = self.root / "launcher.ps1"
        self.launcher.write_text(LAUNCHER)
        self.env = {**os.environ, "OS":"Windows_NT", "LOCALAPPDATA":r"C:\Users\Uni\AppData\Local",
                    "LOGIN_DRIVE":str(self.drive), "LOGIN_SETTINGS":str(self.settings_path),
                    "LOGIN_CALLS":str(self.calls), "LOGIN_REPORT_TARGET":str(self.runtime/'config.json'),
                    "LOGIN_BASE_PATH":os.environ['PATH']}

    def run_terminal(self, command, env):
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=self.root, env=env, stdin=slave,
                                   stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        chunks = bytearray()
        sent = False
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        break
                    if not block:
                        break
                    chunks.extend(block)
                    if b'Fixture hidden value: ' in chunks and not sent:
                        os.write(master, b'FIXTURE_PASSWORD_SENTINEL\n')
                        sent = True
                if process.poll() is not None and not select.select([master], [], [], 0)[0]:
                    break
            process.wait(timeout=2)
            self.assertTrue(sent, chunks.decode(errors='replace'))
            return process.returncode, chunks.decode(errors='replace')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def invoke(self, *, expected=0, mode='', code=0, interactive=False):
        self.settings_path.write_text(json.dumps(self.settings))
        before = set((self.repo/'diagnostics').glob('alliance-login-*.json'))
        command = [str(PWSH), '-NoProfile', '-NonInteractive', '-File', str(self.launcher)]
        env = {**self.env, 'LOGIN_MODE':mode, 'LOGIN_EXIT':str(code),
               'LOGIN_INTERACTIVE':'yes' if interactive else ''}
        if interactive:
            actual, output = self.run_terminal(command, env)
        else:
            result = subprocess.run(command, cwd=self.root, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=20)
            actual, output = result.returncode, result.stdout
        self.assertEqual(actual, expected, output)
        self.assertEqual(VERIFIED in output, expected == 0, output)
        self.assertIn('CALLER STATE PRESERVED', output)
        self.assertFalse(list((self.repo/'diagnostics').glob('*.txt')), 'No transcript is permitted')
        for marker in ('PRIVATE_ENV_SENTINEL','PRIVATE_OLD_CONFIG_SENTINEL','PRIVATE_IDENTITY_SENTINEL',
                       'PRIVATE_PROFILE_CONFIG_SENTINEL','PRIVATE_PROFILE_ROOT_SENTINEL',
                       'PRIVATE_CONFIG_READ_SENTINEL','PRIVATE_METADATA_ERROR_SENTINEL',
                       'PRIVATE_TRANSCRIPT_SENTINEL','PRIVATE_JSON_SENTINEL','FIXTURE_PASSWORD_SENTINEL'):
            self.assertNotIn(marker, output)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        self.output = output
        self.reports = set((self.repo/'diagnostics').glob('alliance-login-*.json')) - before
        self.invocations = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        for call in self.invocations:
            self.assertEqual(call['executable'],str(self.python))
            self.assertEqual(call['cwd'],str(self.root))
            self.assertEqual(call['path'],self.env['PATH'])

    def test_default_invokes_only_diagnostic_with_literal_arguments(self):
        self.invoke()
        self.assertEqual(len(self.invocations),1)
        args = self.invocations[0]['args']
        self.assertEqual(args[:7],['-I','-B',str(self.diagnostic),'--runtime',str(self.runtime),'--username','UniPlayer'])
        self.assertEqual(args[7],'--report')
        self.assertEqual(self.reports,{Path(args[8])})
        self.assertIn('completion does not mean a successful login',self.output)

    def test_direct_invocation_inherits_all_terminal_streams_and_hides_input(self):
        self.invoke(interactive=True)
        self.assertEqual(self.invocations[0]['tty'],[True,True,True])
        self.assertIn('HIDDEN INPUT RECEIVED',self.output)

    def test_explicit_existing_runtime_and_username_are_forwarded_literally(self):
        selected = self.drive / "other [literal] $ & ' runtime"
        selected.mkdir()
        self.settings.update(runtime_root=r"C:\other [literal] $ & ' runtime",username='Other_Player24')
        self.invoke()
        self.assertEqual(self.invocations[0]['args'][4],str(selected))
        self.assertEqual(self.invocations[0]['args'][6],'Other_Player24')

    def test_completed_mismatch_and_account_findings_are_not_diagnostic_failures(self):
        for mode in ('mismatch','missing_account','ineligible','invalid_hash','unsupported_hash'):
            with self.subTest(mode=mode):
                self.invoke(mode=mode)
                self.assertIn('completion does not mean a successful login',self.output)

    def test_failed_diagnostic_exit_is_preserved_without_retry(self):
        for code in (1,2,7):
            with self.subTest(code=code):
                before = len(self.invocations) if hasattr(self,'invocations') else 0
                self.invoke(expected=code if code in (1,2) else 1,code=code)
                self.assertEqual(len(self.invocations),before+1)

    def test_invalid_report_cannot_confirm_completion(self):
        for mode in ('missing','empty','malformed','oversized','format','purpose','status','username',
                     'endpoint','database','database_writes','writes_string','writes_missing',
                     'unknown_outcome','wrong_password_check','symlink'):
            with self.subTest(mode=mode):
                self.invoke(expected=1,mode=mode)

    def test_missing_profile_environment_stops_before_python(self):
        self.env['LOCALAPPDATA']=''
        self.invoke(expected=1)
        self.assertEqual(self.invocations,[])

    def test_invalid_username_stops_before_python(self):
        for username in ('','ab','a'*25,'Uni Player','Unié','UniPlayer\n'):
            with self.subTest(username=username):
                self.settings['username']=username
                self.invoke(expected=1)
                self.assertEqual(self.invocations,[])

    def test_invalid_or_missing_runtime_stops_without_creating_it(self):
        for path in ('','relative',r'\\server\share\runtime',r'C:\Users\..\runtime',
                     r'C:\runtime:stream',r'C:\missing runtime'):
            with self.subTest(path=path):
                self.settings['runtime_root']=path
                self.invoke(expected=1)
                self.assertEqual(self.invocations,[])
        self.assertFalse((self.drive/'missing runtime').exists())

    def test_runtime_symlink_is_rejected_before_python(self):
        (self.drive/'redirect').symlink_to(self.runtime,target_is_directory=True)
        self.settings['runtime_root']=r'C:\redirect'
        self.invoke(expected=1)
        self.assertEqual(self.invocations,[])

    def test_missing_empty_or_unexecutable_tools_stop_safely(self):
        for path in (self.python,self.diagnostic,self.tools/'Alliance-Common.ps1'):
            data=path.read_bytes();digest=self.protected.pop(path)
            try:
                path.unlink()
                self.invoke(expected=1)
                self.assertEqual(self.invocations,[])
                if path.name!='Alliance-Common.ps1':
                    path.write_bytes(b'')
                    self.invoke(expected=1)
                    self.assertEqual(self.invocations,[])
            finally:
                path.write_bytes(data)
                if path==self.python:path.chmod(0o755)
                self.protected[path]=digest
        self.python.chmod(0o644)
        self.invoke(expected=1)
        self.assertEqual(self.invocations,[])

    def test_raw_metadata_exception_is_not_reflected(self):
        self.settings['metadata_error']=True
        self.invoke(expected=1)
        self.assertEqual(self.invocations,[])

    def test_non_windows_is_rejected_without_native_call(self):
        self.env['OS']='Linux'
        self.invoke(expected=1)
        self.assertEqual(self.invocations,[])

    def test_repeated_runs_preserve_old_reports_and_use_unique_names(self):
        self.invoke();first=self.reports.pop();saved=first.read_bytes()
        self.invoke()
        self.assertNotIn(first,self.reports)
        self.assertEqual(first.read_bytes(),saved)
        self.assertEqual(len(self.invocations),2)


if __name__ == '__main__':
    unittest.main()
