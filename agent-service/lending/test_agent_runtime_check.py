import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import provider_runtime_check as check
from agent_providers import runtime_error,HERE


class RuntimeCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.script=self.root/'fake-cli.py'
        self.script.write_text(
            "import json,sys,subprocess,os\n"
            "from pathlib import Path\n"
            "prompt=sys.stdin.buffer.read().decode('utf-8')\n"
            "workspace=Path.cwd();base=workspace.parent\n"
            "value=(workspace/'input.txt').read_text(encoding='utf-8')\n"
            "messages=[{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'project_state','arguments':{}}}]\n"
            "proc=subprocess.run([sys.executable,"+repr(str(HERE/'provider_smoke_mcp.py'))+",str(base/'synthetic.json')],input=('\\n'.join(json.dumps(m) for m in messages)+'\\n').encode(),capture_output=True,check=True)\n"
            "token=json.loads(json.loads(proc.stdout)['result']['content'][0]['text'])['check_token']\n"
            "write='Set artifact to result.txt' in prompt\n"
            "artifact='result.txt' if write else ''\n"
            "if write:(workspace/artifact).write_text(value+'|'+token,encoding='utf-8')\n"
            "answer={'summary':'Done','file_token':value,'mcp_token':token,'artifact':artifact}\n"
            "if os.environ.get('FAKE_BAD_RESULT'):answer['mcp_token']='wrong'\n"
            "print(json.dumps({'structured_output':answer} if '--print' in sys.argv else {'response':json.dumps(answer)}))\n",
            encoding='utf-8')
        self.real_prepare=check.prepare

    def run_check(self,access='write',**kwargs):
        def prepare_fake(*args,**kw):
            command,env=self.real_prepare(*args,**kw)
            # Keep provider policy generation, replace just the paid model executable with a deterministic fixture.
            return [sys.executable,str(self.script),*command[2:]],env
        with patch('provider_runtime_check.check_available',return_value=['fake']),patch('provider_runtime_check.prepare',side_effect=prepare_fake),patch('agent_providers.command_for',return_value=['fake']):
            return check.verify_runtime({'runtime':{'adapter':'gemini','model':'gemini-test'},'access':access},self.root/'checks',**kwargs)

    def test_write_roundtrip_requires_file_mcp_and_valid_handoff(self):
        result=self.run_check()
        self.assertTrue(result['verified'])
        self.assertTrue(result['checks']['write_file'])
        self.assertTrue(result['checks']['mcp'])
        self.assertEqual(list((self.root/'checks').iterdir()),[])

    def test_readonly_roundtrip_leaves_no_artifact(self):
        result=self.run_check('read')
        self.assertTrue(result['checks']['read_only_unchanged'])
        self.assertFalse(result['checks']['write_file'])

    def test_wrong_mcp_token_is_not_verified_and_workspace_is_cleaned(self):
        with patch.dict(os.environ,{'FAKE_BAD_RESULT':'1'}):
            with self.assertRaisesRegex(ValueError,'MCP'):self.run_check()
        self.assertEqual(list((self.root/'checks').iterdir()),[])

    def test_busy_runtime_probe_is_rejected(self):
        check._guard.acquire()
        try:
            with patch('provider_runtime_check.check_available',return_value=['fake']):
                with self.assertRaisesRegex(ValueError,'Đang có một lượt'):check.verify_runtime({'runtime':{'adapter':'gemini'}},self.root)
        finally:check._guard.release()

    def test_missing_auth_never_launches_paid_process(self):
        with patch('provider_runtime_check.check_available',side_effect=ValueError('missing auth')),patch('provider_runtime_check.subprocess.Popen') as start:
            with self.assertRaisesRegex(ValueError,'missing auth'):check.verify_runtime({'runtime':{'adapter':'claude'}},self.root)
            start.assert_not_called()

    def test_provider_errors_stop_retry_without_exposing_log(self):
        for text in ('Quota exceeded for metric: private-project','This model is currently experiencing high demand','API key not valid secret-key','Skipping system settings file private-path'):
            message=runtime_error('gemini',text)
            self.assertTrue(message)
            for private in ('private-project','secret-key','private-path'):self.assertNotIn(private,message)
        self.assertIsNone(runtime_error('gemini','Normal startup warning'))
        self.assertIsNone(runtime_error('codex','Normal quota documentation'))

    def test_runtime_endpoint_requires_office_origin_and_never_activates_agent(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import threading
        from office import make_server
        manager=Mock();manager.office.return_value.runtime=self.root
        server=make_server(manager,0);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_address[1])
        body=json.dumps({'runtime':{'adapter':'gemini'},'access':'write'}).encode()
        try:
            with patch('provider_runtime_check.verify_runtime',return_value={'verified':True}) as verify:
                with self.assertRaises(HTTPError):
                    urlopen(Request(base+'/lending-api/agents/runtime-test',data=body,headers={'Content-Type':'application/json','Origin':'https://evil.example'}))
                verify.assert_not_called()
                with urlopen(Request(base+'/lending-api/agents/runtime-test',data=body,headers={'Content-Type':'application/json','Origin':'http://localhost:8766'})) as response:
                    self.assertTrue(json.load(response)['verified'])
                manager.office.return_value.manage_agent.assert_not_called()
        finally:server.shutdown();server.server_close();worker.join(timeout=2)

    def test_timeout_cleans_up_child_and_releases_global_lease(self):
        proc=Mock();proc.poll.return_value=None;proc.stdin=Mock()
        with patch('provider_runtime_check.check_available',return_value=['fake']),patch('provider_runtime_check.prepare',return_value=(['fake'],{})),patch('provider_runtime_check.subprocess.Popen',return_value=proc),patch('provider_runtime_check.stop_process') as stop:
            with self.assertRaisesRegex(ValueError,'quá thời gian'):check.verify_runtime({'runtime':{'adapter':'gemini'}},self.root,timeout=-1)
        stop.assert_called_once_with(proc)
        self.assertTrue(check._guard.acquire(blocking=False));check._guard.release()


if __name__=='__main__':unittest.main()
