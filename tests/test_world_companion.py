"""Secret handling and ownership checks for the Windows native companion."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from uuid import uuid4
from tools import run_world_companion as helper


class Pipe(io.BytesIO):
    def close(self): self.saved = self.getvalue()


class CompanionTests(unittest.TestCase):
    def test_private_credentials_use_only_pinned_login_and_stdin_and_are_revoked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'diagnostics').mkdir();profile=root/'profile.json';profile.write_text('{}')
            args=SimpleNamespace(battle_id=str(uuid4()),username='CompanionUser',profile=profile)
            process=SimpleNamespace(stdin=Pipe(),wait=lambda **kw:0,poll=lambda:0)
            token='t'*43; account=str(uuid4()); password='Private-Password-Only-Here'
            calls=[]
            def start(command,**kwargs):
                self.assertNotIn(password,str(command));self.assertNotIn(token,str(command))
                self.assertNotIn(token,str(kwargs['env']))
                self.assertEqual(command[0],'/owned/worker')
                return process
            def request(*values):calls.append(values);return {}
            with patch.object(helper,'ROOT',root),patch.object(helper,'installed_worker',return_value={'executable':'/owned/worker','game_data':'/owned/data'}),\
                 patch.object(helper.account_transport,'public_profile',return_value={'pinned':True}),\
                 patch.object(helper.sys.stdin,'isatty',return_value=True),patch.object(helper.getpass,'getpass',return_value=password),\
                 patch.object(helper.account_transport,'login',return_value=(token,{'id':account})) as login,\
                 patch.object(helper.account_transport,'account_request',side_effect=request),patch.object(helper.subprocess,'Popen',side_effect=start):
                self.assertEqual(helper.run(args),0)
            self.assertEqual(json.loads(process.stdin.saved),{'run_id':args.battle_id,'account_id':account,'token':token})
            login.assert_called_once_with({'pinned':True},args.username,password)
            self.assertEqual(calls,[({'pinned':True},'logout',{},token)])
            report=next((root/'diagnostics').glob('*/report.json')).read_text()
            self.assertNotIn(password,report);self.assertNotIn(token,report)
            self.assertEqual(json.loads(report)['session_logout'],'confirmed')

    def test_invalid_run_does_not_start_or_prompt(self):
        with patch.object(helper,'installed_worker') as worker,patch.object(helper.getpass,'getpass') as prompt:
            with self.assertRaises(ValueError):helper.run(SimpleNamespace(battle_id='../runtime',username='ValidName'))
            worker.assert_not_called();prompt.assert_not_called()

    def test_selection_omits_delegated_and_draft_armies(self):
        actor=str(uuid4()); chosen=str(uuid4())
        rows=[{'id':chosen,'state':'preparing','mission_id':'company_border_patrol',
               'armies':[{'account_id':actor,'controller':'human'}]},
              {'id':str(uuid4()),'state':'running','armies':[{'account_id':actor,'controller':'worker'}]},
              {'id':str(uuid4()),'state':'draft','armies':[{'account_id':actor,'controller':'human'}]}]
        with patch.object(helper.account_transport,'account_request',return_value={'version':1,'actor_id':actor,'data':{'items':rows}}) as request,\
             patch('builtins.input',return_value='1'):
            self.assertEqual(helper.select_battle({},'t'*43,actor),chosen)
        self.assertEqual(request.call_args.args[1:3],('world_query',{'operation':'battles','payload':{}}))

    def test_cancel_after_login_revokes_session_without_starting_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'diagnostics').mkdir();profile=root/'profile.json';profile.write_text('{}')
            args=SimpleNamespace(battle_id=None,username='CompanionUser',profile=profile)
            with patch.object(helper,'ROOT',root),patch.object(helper,'installed_worker',return_value={}),\
                 patch.object(helper.account_transport,'public_profile',return_value={}),\
                 patch.object(helper.sys.stdin,'isatty',return_value=True),patch.object(helper.getpass,'getpass',return_value='private'),\
                 patch.object(helper.account_transport,'login',return_value=('t'*43,{'id':str(uuid4())})),\
                 patch.object(helper,'select_battle',return_value=None),\
                 patch.object(helper.account_transport,'account_request') as request,patch.object(helper.subprocess,'Popen') as start:
                self.assertEqual(helper.run(args),0)
                start.assert_not_called()
                request.assert_called_once_with({},'logout',{},'t'*43)
            report=json.loads(next((root/'diagnostics').glob('*/report.json')).read_text())
            self.assertTrue(report['selection_cancelled'])
            self.assertEqual(report['session_logout'],'confirmed')


if __name__=='__main__':unittest.main()
