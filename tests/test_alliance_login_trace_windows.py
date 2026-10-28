"""Run the trace launcher with simulated Windows paths and an isolated Python.

The PTY case exercises inherited terminal streams on Linux;
actual Windows 5.1 console behavior still requires user acceptance.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import threading
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = ROOT.parent / "wesnoth_client/build/host-tools/powershell-7.4.6/pwsh"
HELPER = "Trace-WindowsAllianceLogin.ps1"
VERIFIED = "ALLIANCE LOGIN TRACE REPORT VERIFIED"
OUTCOMES = (
    'service_authorization_rejected','different_username','invalid_input','account_missing',
    'invalid_stored_hash','password_mismatch','password_verification_failed','account_ineligible','session_state_changed',
    'rate_limited','login_accepted','backend_unavailable','backend_error','request_rejected',
    'request_failed','authorization_or_credentials_rejected','capture_timeout_no_request','capture_timeout_in_progress',
    'capture_cancelled',
)
FAKE_PYTHON = r'''#!/usr/bin/python3
import json, os, pathlib, sys, time
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
    print('INHERITED CONSOLE VERIFIED', flush=True)
report = pathlib.Path(args[args.index('--report') + 1])
username = args[args.index('--username') + 1]
data = {'format':1, 'purpose':'wesnoth-alliance-login-trace',
        'status':'failed' if code else 'completed', 'outcome':'startup_failed' if code else 'password_mismatch',
        'username':username, 'endpoint':'127.0.0.1:18765', 'capture_seconds':300, 'http_status':401}
if mode.startswith('outcome:'):
    data['outcome'] = mode.split(':',1)[1]
    if data['outcome'] in ('capture_timeout_no_request','capture_timeout_in_progress','capture_cancelled'):data['http_status']=None
if mode in ('format','purpose','status','username','endpoint','capture_seconds','http_status'):
    data[mode] = {'format':2,'purpose':'other','status':'armed','username':'OtherPlayer',
                  'endpoint':'203.0.113.1:18765','capture_seconds':301,'http_status':600}[mode]
if mode == 'format_string': data['format']='1'
if mode == 'username_array': data['username']=[username]
if mode == 'format_bool': data['format']=True
if mode == 'capture_string': data['capture_seconds']='300'
if mode == 'status_string': data['http_status']='401'
if mode == 'status_bool': data['http_status']=True
if mode == 'status_small': data['http_status']=99
if mode == 'unknown_outcome': data['outcome']='PRIVATE_UNKNOWN_OUTCOME_SENTINEL'
if mode == 'missing_key': del data['http_status']
if mode == 'extra_key': data['secret']='PRIVATE_JSON_SENTINEL'
if mode == 'wrong_key_case': data['Format']=data.pop('format')
if mode == 'array': data=[data]
if mode == 'failed': data.update(status='failed',outcome='startup_failed')
if mode == 'running':
    with report.open('x') as output:
        json.dump({**data,'status':'armed','outcome':'waiting','http_status':None},output)
    print('ALLIANCE LOGIN TRACE READY',flush=True)
    control=pathlib.Path(os.environ['LOGIN_CONTROL'])
    deadline=time.monotonic()+15
    while not (control/'capture').exists():
        if time.monotonic()>deadline: sys.exit(1)
        time.sleep(0.02)
    report.write_text(json.dumps(data))
    print('ALLIANCE LOGIN TRACE COMPLETE',flush=True)
    while not (control/'stop').exists():
        if time.monotonic()>deadline: sys.exit(1)
        time.sleep(0.02)
else:
    if mode == 'symlink':
        report.symlink_to(os.environ['LOGIN_REPORT_TARGET'])
    elif mode != 'missing':
        with report.open('x') as output:
            if mode == 'malformed': output.write('{"private":"PRIVATE_JSON_SENTINEL", invalid')
            elif mode == 'oversized': output.write(' ' * 32769)
            elif mode != 'empty': json.dump(data, output)
    print('Simulated sanitized trace output', flush=True)
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
class LoginTraceWindowsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="alliance trace PS ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "server $ & with ' spaces"
        self.tools = self.repo / "tools"
        self.tools.mkdir(parents=True)
        for name in (HELPER, "Alliance-Common.ps1"):
            shutil.copyfile(ROOT / "tools" / name, self.tools / name)
        self.helper = self.tools / HELPER
        self.python = self.repo / "build/alliance-venv-py312/Scripts/python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.trace_tool = self.tools / "trace_alliance_login.py"
        self.trace_tool.write_text("# simulated safe trace backend\n")
        self.drive = self.root / "profile drive"
        self.runtime = self.drive / "Users/Uni/AppData/Local/WesnothAlliance/runtime-v2"
        self.runtime.mkdir(parents=True)
        for path, content in {
            self.repo / ".env": b"PRIVATE_ENV_SENTINEL",
            self.repo / "runtime/alliance/config.json": b"PRIVATE_OLD_CONFIG_SENTINEL",
            self.repo / "runtime/alliance-transport/server-key.pem": b"PRIVATE_IDENTITY_SENTINEL",
            self.repo / "build/alliance-account-bridge/alliance-account-bridge.exe": b"EXISTING_BRIDGE",
            self.repo / "build/alliance-venv-py312/alliance-owned.json": b"EXISTING_VENV_RECEIPT",
            self.repo / "build/alliance-mongodb/bin/mongod.exe": b"EXISTING_MONGODB",
            self.repo / "README.md": b"UNRELATED_USER_CHANGES",
            self.repo / "diagnostics/alliance-login-trace-previous.json": b"PREVIOUS_REPORT",
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
        self.control = self.root / 'control'
        self.control.mkdir()
        self.env = {**os.environ, "OS":"Windows_NT", "LOCALAPPDATA":r"C:\Users\Uni\AppData\Local",
                    "LOGIN_CONTROL":str(self.control), "LOGIN_DRIVE":str(self.drive), "LOGIN_SETTINGS":str(self.settings_path),
                    "LOGIN_CALLS":str(self.calls), "LOGIN_REPORT_TARGET":str(self.runtime/'config.json'),
                    "LOGIN_BASE_PATH":os.environ['PATH']}

    def run_terminal(self, command, env):
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=self.root, env=env, stdin=slave,
                                   stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        chunks = bytearray()
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
                if process.poll() is not None and not select.select([master], [], [], 0)[0]:
                    break
            process.wait(timeout=2)
            return process.returncode, chunks.decode(errors='replace')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def invoke(self, *, expected=0, mode='', code=0, interactive=False):
        self.settings_path.write_text(json.dumps(self.settings))
        before = set((self.repo/'diagnostics').glob('alliance-login-trace-*.json'))
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
                       'PRIVATE_TRANSCRIPT_SENTINEL','PRIVATE_JSON_SENTINEL','PRIVATE_UNKNOWN_OUTCOME_SENTINEL'):
            self.assertNotIn(marker, output)
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))
        self.output = output
        self.reports = set((self.repo/'diagnostics').glob('alliance-login-trace-*.json')) - before
        self.invocations = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        for call in self.invocations:
            self.assertEqual(call['executable'],str(self.python))
            self.assertEqual(call['cwd'],str(self.root))
            self.assertEqual(call['path'],self.env['PATH'])

    def test_completed_outcome_contract_matches_python_and_wrapper_exactly(self):
        module=ast.parse((ROOT/'tools/trace_alliance_login.py').read_text())
        definition=next(node.value for node in module.body if isinstance(node,ast.Assign)
                        and any(isinstance(target,ast.Name) and target.id=='OUTCOMES' for target in node.targets))
        production=frozenset(ast.literal_eval(definition.args[0]))
        allowed=re.search(r'\$allowedOutcomes = @\((.*?)\n    \)',self.helper.read_text(),re.S)
        self.assertIsNotNone(allowed)
        wrapper=frozenset(re.findall(r"'([^']+)'",allowed.group(1)))
        self.assertEqual(production,frozenset(OUTCOMES))
        self.assertEqual(production,wrapper)

    def test_default_invokes_only_trace_backend_with_literal_arguments(self):
        self.invoke()
        self.assertEqual(len(self.invocations),1)
        args = self.invocations[0]['args']
        self.assertEqual(args[:7],['-I','-B',str(self.trace_tool),'--runtime',str(self.runtime),'--username','UniPlayer'])
        self.assertEqual(args[7],'--report')
        self.assertEqual(self.reports,{Path(args[8])})
        self.assertIn('completion is not a successful-login assertion',self.output)

    def test_direct_invocation_inherits_all_terminal_streams(self):
        self.invoke(interactive=True)
        self.assertEqual(self.invocations[0]['tty'],[True,True,True])
        self.assertIn('INHERITED CONSOLE VERIFIED',self.output)

    def test_explicit_existing_runtime_and_username_are_forwarded_literally(self):
        selected = self.drive / "other [literal] $ & ' runtime"
        selected.mkdir()
        self.settings.update(runtime_root=r"C:\other [literal] $ & ' runtime",username='Other_Player24')
        self.invoke()
        self.assertEqual(self.invocations[0]['args'][4],str(selected))
        self.assertEqual(self.invocations[0]['args'][6],'Other_Player24')

    def test_all_fixed_completed_outcomes_are_accepted_without_login_success_claim(self):
        for outcome in OUTCOMES:
            with self.subTest(outcome=outcome):
                self.invoke(mode='outcome:'+outcome)
                self.assertIn('completion is not a successful-login assertion',self.output)

    def test_failed_trace_exit_is_preserved_without_retry(self):
        for code in (1,2,7):
            with self.subTest(code=code):
                before = len(self.invocations) if hasattr(self,'invocations') else 0
                self.invoke(expected=code if code in (1,2) else 1,code=code)
                self.assertEqual(len(self.invocations),before+1)

    def test_invalid_report_cannot_confirm_completion(self):
        for mode in ('missing','empty','malformed','oversized','format','purpose','status','username',
                     'endpoint','capture_seconds','http_status','format_string','format_bool','capture_string',
                     'status_string','status_bool','status_small','unknown_outcome','missing_key','extra_key',
                     'wrong_key_case','username_array','array','failed','symlink'):
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
        for path in (self.python,self.trace_tool,self.tools/'Alliance-Common.ps1'):
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

    def test_backend_keeps_serving_after_report_without_launcher_restart(self):
        observed = []
        errors = []
        def observe():
            try:
                deadline = time.monotonic()+12
                report = None
                while time.monotonic()<deadline:
                    reports = list((self.repo/'diagnostics').glob('alliance-login-trace-*.json'))
                    reports = [p for p in reports if p.name!='alliance-login-trace-previous.json']
                    if reports:
                        report = reports[0]
                        try:
                            data = json.loads(report.read_text())
                            if data['status']=='armed': break
                        except (json.JSONDecodeError,KeyError): pass
                    time.sleep(0.02)
                self.assertIsNotNone(report)
                self.assertEqual(data['status'],'armed')
                observed.append('armed')
                (self.control/'capture').touch()
                while time.monotonic()<deadline:
                    try:
                        data = json.loads(report.read_text())
                        if data['status']=='completed': break
                    except json.JSONDecodeError: pass
                    time.sleep(0.02)
                self.assertEqual(data['status'],'completed')
                self.assertFalse((self.control/'stop').exists())
                observed.append('completed_before_stop')
            except BaseException as exc:
                errors.append(exc)
            finally:
                (self.control/'stop').touch()
        thread=threading.Thread(target=observe)
        thread.start()
        try:
            self.invoke(mode='running')
        finally:
            thread.join(timeout=15)
        self.assertFalse(thread.is_alive())
        if errors: raise errors[0]
        self.assertEqual(observed,['armed','completed_before_stop'])
        self.assertEqual(len(self.invocations),1)
        self.assertLess(self.output.index('Sanitized JSON report:'),self.output.index('ALLIANCE LOGIN TRACE READY'))
        self.assertLess(self.output.index('ALLIANCE LOGIN TRACE COMPLETE'),self.output.index(VERIFIED))

    def test_diagnostics_symlink_cannot_redirect_report(self):
        diagnostics=self.repo/'diagnostics'
        old=diagnostics/'alliance-login-trace-previous.json'
        digest=self.protected.pop(old)
        saved=old.read_bytes()
        old.unlink(); diagnostics.rmdir()
        diagnostics.symlink_to(self.runtime,target_is_directory=True)
        try:
            self.invoke(expected=1)
            self.assertEqual(self.invocations,[])
        finally:
            diagnostics.unlink(); diagnostics.mkdir(); old.write_bytes(saved)
            self.protected[old]=digest


if __name__ == '__main__':
    unittest.main()
