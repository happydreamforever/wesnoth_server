"""Executable configuration/command boundary checks; Linux PowerShell is not Windows acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIND = 'client' if ROOT.name.endswith('client') else 'server'
PWSH = (ROOT if KIND == 'client' else ROOT.parent / 'wesnoth_client') / 'build/host-tools/powershell-7.4.6/pwsh'

@unittest.skipUnless(PWSH.is_file(), 'Requires the verification PowerShell host')
class DevelopmentEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='development paths with spaces ')
        self.root = Path(self.temp.name)
        (self.root / 'tools').mkdir()
        for name in ('dev.ps1', '.env.example', 'tools/Windows-Environment.ps1'):
            shutil.copy2(ROOT / name, self.root / name)
        self.envfile = self.root / '.env'
        self.calls = self.root / 'calls.jsonl'
        self.environment = {**os.environ, 'OS': 'Windows_NT', 'LOCALAPPDATA': str(self.root),
            'USERPROFILE': str(self.root), 'ProgramFiles': str(self.root), 'DEV_CALLS': str(self.calls)}
        self.header = f'WESNOTH_ENV_FORMAT=1\nWESNOTH_PROJECT={KIND}\n'

    def tearDown(self): self.temp.cleanup()

    def ps(self, code):
        driver = self.root / 'driver.ps1'
        driver.write_text(code)
        return subprocess.run([str(PWSH), '-NoProfile', '-File', str(driver)],
                              capture_output=True, text=True, env=self.environment, timeout=40)

    def read(self, content):
        self.envfile.write_text(content)
        return self.ps("$ErrorActionPreference='Stop'\n. (Join-Path $PSScriptRoot 'tools/Windows-Environment.ps1')\n"
            f"try {{ Get-WesnothEnvironment $PSScriptRoot {KIND} | ConvertTo-Json -Compress }} "
            "catch { Write-Output $_.Exception.Message; exit 1 }\n")

    def test_template_and_data_expansion_with_spaces(self):
        result = self.read(self.header + 'WESNOTH_MSYS_ROOT="${WORKSPACE_ROOT}/my tools"\n'
            'WESNOTH_OPENSSL_PATH=${WESNOTH_MSYS_ROOT}/openssl.exe\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['WESNOTH_OPENSSL_PATH'], str(self.root.parent/'my tools/openssl.exe'))
        result = self.read((ROOT / '.env.example').read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shell_expressions_are_literal_data(self):
        result = self.read(self.header + 'WESNOTH_MSYS_ROOT=$(throw "DO_NOT_EXECUTE")\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('$(throw "DO_NOT_EXECUTE")', json.loads(result.stdout)['WESNOTH_MSYS_ROOT'])

    def test_invalid_format_cycle_duplicate_unknown_and_secret_are_not_echoed(self):
        for content in ('PRIVATE_PASSWORD=very_private_value\n', self.header+'WESNOTH_UNKNOWN=very_private_value\n',
                self.header+'WESNOTH_SERVER_IP=very_private_value\n',
                self.header+'WESNOTH_PROJECT=very_private_value\n',
                self.header+'WESNOTH_MSYS_ROOT=${WESNOTH_OPENSSL_PATH}\n',
                self.header+'WESNOTH_MSYS_ROOT=${UNSUPPORTED}\n'):
            with self.subTest(content=content):
                result = self.read(content)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('very_private_value', result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_wrong_project_oversize_and_link_refused(self):
        for content in ('WESNOTH_ENV_FORMAT=1\nWESNOTH_PROJECT=wrong\n', self.header + '#' * 8193):
            self.assertNotEqual(self.read(content).returncode, 0)
        self.envfile.unlink()
        target=self.root/'private-input'; target.write_text(self.header)
        self.envfile.symlink_to(target)
        result=self.ps(". (Join-Path $PSScriptRoot 'tools/Windows-Environment.ps1'); "
            f"try {{ Get-WesnothEnvironment $PSScriptRoot {KIND}; exit 0 }} catch {{ exit 1 }}")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), self.header)

    def test_configure_creates_once_and_preserves_existing_env(self):
        command="& (Join-Path $PSScriptRoot 'dev.ps1') configure; exit $LASTEXITCODE"
        first=self.ps(command)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.envfile.write_text('keep private existing configuration')
        second=self.ps(command)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.envfile.read_text(), 'keep private existing configuration')

    def fixture(self):
        python = self.root / 'custom tools/python.exe'
        python.parent.mkdir()
        python.write_text('#!/usr/bin/python3\nimport json,os,sys\n'
            'with open(os.environ["DEV_CALLS"],"a") as f: f.write(json.dumps({"tool":"python","args":sys.argv[1:],"mongo":os.environ.get("WESNOTH_MONGO_PORT"),"android":os.environ.get("ANDROID_USER_HOME")})+"\\n")\n'
            'sys.exit(7 if os.environ.get("DEV_FAIL") in sys.argv[1:] else 0)\n')
        python.chmod(0o755)
        for directory in ('service env/Scripts',):
            (self.root / directory).mkdir(parents=True)
            shutil.copy2(python, self.root / directory / 'python.exe')
        values = dict(WESNOTH_PYTHON_PATH=python, WESNOTH_POWERSHELL_PATH=PWSH,
            WESNOTH_MSYS_ROOT=self.root/'custom msys', WESNOTH_CMAKE_PATH=self.root/'cmake.exe',
            WESNOTH_OPENSSL_PATH=self.root/'openssl.exe',WESNOTH_SERVER_IP='192.168.40.11')
        if KIND == 'server':
            values.update(WESNOTH_RUNTIME_ROOT=self.root/'runtime v3',WESNOTH_IDENTITY_ROOT=self.root/'tls identity',
                WESNOTH_SERVICE_ENV_ROOT=self.root/'service env',WESNOTH_MONGODB_ROOT=self.root/'mongo install',
                WESNOTH_DEPENDENCY_CACHE=self.root/'dependency cache',WESNOTH_MONGO_PORT=27123,
                WESNOTH_MONGO_DATABASE='wesnoth_newpc',WESNOTH_MONGO_REPLICA_SET='newpc-rs',WESNOTH_WORLD_WORKERS=2)
        else:
            values.update(WESNOTH_ANDROID_USER_HOME=self.root/'original android home',
                WESNOTH_ARCHIVE_DIRECTORY=self.root/'archive cache', WESNOTH_JOBS=3)
        self.envfile.write_text(self.header + ''.join(f'{k}={v}\n' for k,v in values.items()))
        for helper in (ROOT / 'tools').glob('*.ps1'):
            if helper.name == 'Windows-Environment.ps1': continue
            (self.root/'tools'/helper.name).write_text(
                "param([string]$RuntimeRoot,[string]$MsysRoot,[string]$IdentityRoot,[int]$WorldWorkers,"
                "[string]$SdkRoot,[string]$PythonPath,[string]$JavaHome,[string]$GradleUserHome,"
                "[string]$ArchiveDirectory,[string]$CMakePath,[string]$NinjaPath,[string]$PublicConfigPath,"
                "[string]$OpenSslPath,[string]$GameDataRoot,[string]$Operation,[string]$DestinationPath,"
                "[string]$BackupPath,[string]$AdbPath,[string]$Serial,[int]$Jobs,"
                "[switch]$IncludeBattles,[switch]$Download,[switch]$KeepSavedProfile)\n"
                "$received=@(); foreach($key in @($PSBoundParameters.Keys | Sort-Object)){"
                "$received+=('-'+$key); if($PSBoundParameters[$key] -isnot [Management.Automation.SwitchParameter]){"
                "$received += [string]$PSBoundParameters[$key]}}\n"
                "$record=@{tool=[IO.Path]::GetFileName($MyInvocation.MyCommand.Path);args=@($received)} | ConvertTo-Json -Compress\n"
                "[IO.File]::AppendAllText($env:DEV_CALLS,$record+[Environment]::NewLine)\nexit 0\n")

    def execute(self, action, flags=''):
        return self.ps("$env:ANDROID_USER_HOME='caller android'; $env:WESNOTH_MONGO_PORT='caller mongo'\n"
            f"& (Join-Path $PSScriptRoot 'dev.ps1') {action} {flags}\n"
            "$code=$LASTEXITCODE\nWrite-Output ('RESTORED='+$env:ANDROID_USER_HOME+','+$env:WESNOTH_MONGO_PORT)\nexit $code\n")

    def records(self): return [json.loads(row) for row in self.calls.read_text().splitlines()]

    def test_one_command_dispatch_and_scoped_environment(self):
        self.fixture()
        result=self.execute('start' if KIND=='server' else 'build')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESTORED=caller android,caller mongo', result.stdout)
        records=self.records()
        if KIND=='server':
            self.assertEqual([v['tool'] for v in records], ['python']*3+['Start-WindowsAllianceStack.ps1'])
            self.assertTrue(all(v['mongo']=='27123' for v in records[:-1]))
            self.assertIn('--identity', records[2]['args'])
            args=records[-1]['args']; self.assertIn('-IncludeBattles',args)
            self.assertEqual(args[args.index('-WorldWorkers')+1], '2')
            self.assertEqual(args[args.index('-IdentityRoot')+1], str(self.root/'tls identity'))
        else:
            expected=['Build-WindowsAndroid'+v+'.ps1' for v in ('Media','Fonts','TextBase','GlibDeps','Glib','TextRender','TextLayout','Icu','Boost','Network','Engine','Game','AccountGame')]
            self.assertEqual([v['tool'] for v in records if v['tool']!='python'],expected)
            network=next(v for v in records if v['tool']=='Build-WindowsAndroidNetwork.ps1')
            self.assertEqual(network['args'][network['args'].index('-MsysRoot')+1], str(self.root/'custom msys'))
            self.assertNotIn('-ArchiveDirectory', network['args'])
            self.assertTrue(all(v['android']==str(self.root/'original android home') for v in records if v['tool']=='python'))

    def test_verification_failure_stops_before_launch_or_build(self):
        self.fixture(); self.environment['DEV_FAIL']='check-installed' if KIND=='server' else 'check'
        result=self.execute('start' if KIND=='server' else 'build')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(all(v['tool']=='python' for v in self.records()))
        self.assertIn('RESTORED=caller android,caller mongo',result.stdout)

    def test_initialization_gate_or_completed_native_stage_preservation(self):
        self.fixture()
        if KIND=='server':
            result=self.execute('init')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(self.calls.exists())
            (self.root/'runtime v3').mkdir()
            (self.root/'runtime v3/sentinel').write_bytes(b'preserve')
            result=self.execute('init','-NewDevelopmentRuntime')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(self.calls.exists())
            self.assertEqual((self.root/'runtime v3/sentinel').read_bytes(),b'preserve')
        else:
            receipt=self.root/'build/android-media/receipt.json'; receipt.parent.mkdir(parents=True)
            receipt.write_text('fixture receipt retained')
            result=self.execute('build')
            self.assertEqual(result.returncode, 0,result.stdout+result.stderr)
            self.assertNotIn('Build-WindowsAndroidMedia.ps1',[v['tool'] for v in self.records()])
            self.assertTrue(any('verify-stage' in v['args'] and 'media' in v['args'] for v in self.records()))
            self.assertEqual(receipt.read_text(),'fixture receipt retained')

    def test_download_is_explicit_and_limited_to_prepare(self):
        self.fixture()
        result=self.execute('start' if KIND=='server' else 'build','-Download')
        self.assertNotEqual(result.returncode, 0); self.assertFalse(self.calls.exists())
        result=self.execute('prepare','-Download')
        self.assertEqual(result.returncode, 0,result.stdout+result.stderr)
        helpers=[v for v in self.records() if v['tool']!='python']
        self.assertTrue(helpers); self.assertTrue(all('-Download' in v['args'] for v in helpers))

    def test_install_or_backup_preserves_explicit_action_boundary(self):
        self.fixture()
        if KIND=='server':
            result=self.execute('backup')
            self.assertNotEqual(result.returncode,0);self.assertFalse(self.calls.exists())
            result=self.execute('backup',"-DestinationPath 'E:/Private Transfer/backup'")
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            args=self.records()[-1]['args']
            self.assertEqual(args[args.index('-DestinationPath')+1],'E:/Private Transfer/backup')
        else:
            result=self.execute('install')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            args=self.records()[-1]['args']
            self.assertEqual(self.records()[-1]['tool'],'Install-AndroidAccountGame.ps1')
            self.assertIn('-KeepSavedProfile',args)
            self.assertIn('-PublicConfigPath',args)
            self.assertEqual(args[args.index('-Serial')+1],'127.0.0.1:5555')
