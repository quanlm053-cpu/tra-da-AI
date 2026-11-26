import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from agent_registry import AgentRegistry
from agent_settings import validate,settings,runtime_options
from agent_providers import prepare,decode,check_available,command_for,validate_result,diagnostic,auth_hint,gemini_cached_key,gemini_models
from agent_redmine import AgentRedmine
from office import Office,schema,HERE,make_server


def handoff():
    return dict(summary='Đã kiểm tra',outcome='passed',repair_role='none',artifacts=[],
                consult_role='none',consult_question='',stories=[])


class ProviderTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.output=self.root/'handoff.json'
        self.spec=schema(agent_ids=['frontend','pm'])
        self.schema=self.root/'schema.json';self.schema.write_text(json.dumps(self.spec),encoding='utf-8')

    def config(self,provider):
        return settings({'runtime':{'adapter':provider,'model':'chosen-model'}})['runtime']

    def prepare(self,provider,read_only=False,tools=None):
        with patch('agent_providers.command_for',return_value=['fake-cli']):
            return prepare(provider,self.config(provider),read_only,tools or ['shell','read_issue'],
                           self.root/'state.json',self.output,self.schema)

    def test_all_three_adapters_persist_without_credentials(self):
        registry=AgentRegistry(self.root)
        for provider in ('codex','claude','gemini'):
            row=registry.change({'name':provider,'title':'Task','runtime':{'adapter':provider,'model':'chosen-model'}})
            self.assertEqual(AgentRegistry(self.root).get(row['id'])['runtime']['adapter'],provider)
        with self.assertRaises(ValueError):validate({'runtime':{'adapter':'arbitrary-command'}})
        with self.assertRaises(ValueError):validate({'runtime':{'api_key':'secret'}})

    def test_claude_uses_strict_mcp_schema_and_no_permission_bypass(self):
        cmd,env=self.prepare('claude')
        for flag in ('--restricted','--strict-mcp-config','--json-schema','--permission-prompts'):self.assertIn(flag,cmd)
        self.assertNotIn('--dangerously-skip-permissions',cmd)
        self.assertIn('mcp__lending__read_issue',cmd[cmd.index('--allowedTools')+1])
        self.assertNotIn('mcp__lending__project_state',cmd[cmd.index('--allowedTools')+1])
        self.assertEqual(cmd[cmd.index('--model')+1],'chosen-model')
        server=json.loads(self.output.with_suffix('.provider.json').read_text())['mcpServers']['lending']
        self.assertEqual(json.loads(server['args'][-1]),['read_issue'])
        self.assertEqual(env,{})

    def test_claude_readonly_cannot_get_shell_or_edit(self):
        cmd,_=self.prepare('claude',True,['shell','read_issue'])
        native=cmd[cmd.index('--tools')+1].split(',')
        self.assertEqual(native,['Read','Glob','Grep'])

    def test_gemini_private_policy_is_per_run_and_limits_tools(self):
        cmd,env=self.prepare('gemini')
        data=json.loads(Path(env['TRADA_GEMINI_WORK']+'/.gemini/settings.json').read_text())
        self.assertNotIn('GEMINI_CLI_SYSTEM_SETTINGS_PATH',env)
        self.assertEqual(env['GEMINI_CLI_TRUST_WORKSPACE'],'true')
        self.assertTrue((Path(env['TRADA_GEMINI_HOME'])/'.gemini/settings.json').is_file())
        self.assertTrue(cmd[1].endswith('gemini-runtime-launcher.mjs'))
        self.assertIn('write_file',data['tools']['core'])
        self.assertIn('run_shell_command',data['tools']['allowed'])
        self.assertFalse(data['hooksConfig']['enabled'])
        self.assertFalse(data['experimental']['enableAgents'])
        self.assertFalse(data['admin']['extensions']['enabled'])
        self.assertEqual(data['mcpServers']['lending']['includeTools'],['read_issue'])
        self.assertEqual(cmd[cmd.index('--approval-mode')+1],'default')
        self.assertNotIn('--yolo',cmd)
        self.assertEqual(cmd[cmd.index('--allowed-mcp-server-names')+1],'lending')

    def test_gemini_readonly_removes_shell_and_write_tools(self):
        _,env=self.prepare('gemini',True,['shell','read_issue'])
        core=json.loads(Path(env['TRADA_GEMINI_WORK']+'/.gemini/settings.json').read_text())['tools']['core']
        for name in ('write_file','replace','run_shell_command','google_web_search'):self.assertNotIn(name,core)

    def test_shell_and_web_are_independent_for_both_providers(self):
        for provider in ('claude','gemini'):
            cmd,env=self.prepare(provider,False,['web_search'])
            if provider=='claude':core=cmd[cmd.index('--tools')+1].split(',')
            else:core=json.loads(Path(env['TRADA_GEMINI_WORK']+'/.gemini/settings.json').read_text())['tools']['core']
            self.assertNotIn('Bash',core);self.assertNotIn('run_shell_command',core)
            self.assertIn('WebSearch' if provider=='claude' else 'google_web_search',core)

    def test_valid_provider_envelopes_decode_to_same_contract(self):
        expected=handoff()
        for provider,body in [('claude',{'structured_output':expected}),('claude',{'result':json.dumps(expected)}),
                              ('gemini',{'response':json.dumps(expected),'stats':{'totalTokens':2}})]:
            self.assertEqual(decode(provider,json.dumps(body),self.spec),expected)

    def test_malformed_error_missing_field_and_bad_enum_fail_closed(self):
        bad=[{'error':{'message':'bad key'}},{'response':'not json'},
             {'response':json.dumps({'summary':'unstructured'})},
             {'response':json.dumps({**handoff(),'outcome':'anything'})},
             {'response':json.dumps({**handoff(),'consult_role':'outside-project'})},
             {'response':json.dumps({**handoff(),'extra':True})}]
        for body in bad:
            with self.subTest(body=body),self.assertRaises(ValueError):
                decode('gemini',json.dumps(body),self.spec)

    def test_pm_actions_validate_assignee_and_numeric_types(self):
        spec=schema(pm=True,agent_ids=['pm','frontend'])
        data={**handoff(),'action':dict(type='create_task',target_id=2,title='UI',description='Fix',
              assignee='frontend',due_date='',repo_slug='',visibility='')}
        validate_result(data,spec)
        for patch_action in ({'assignee':'rogue'},{'target_id':True},{'type':'run-shell'}):
            with self.assertRaises(ValueError):validate_result({**data,'action':{**data['action'],**patch_action}},spec)

    def test_missing_cli_or_auth_fails_without_changing_provider(self):
        for provider in ('claude','gemini'):
            with patch('agent_providers.command_for',return_value=[]):
                with self.assertRaises(ValueError):check_available(self.config(provider),require_auth=True)
            with patch('agent_providers.command_for',return_value=['fake-cli']),patch('agent_providers.auth_hint',return_value=False),patch('agent_providers.subprocess.run',side_effect=OSError):
                with self.assertRaisesRegex(ValueError,'đăng nhập'):check_available(self.config(provider),require_auth=True)

    def test_options_never_return_keys_or_unverified_auth_success(self):
        cache=self.root/'.codex/models_cache.json'
        cache.parent.mkdir(parents=True,exist_ok=True)
        cache.write_text(json.dumps({'models':[{'slug':'codex-test','display_name':'Test model'}]}),encoding='utf-8')
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'secret-test-key','GEMINI_API_KEY':'secret-google-key'}),patch('agent_settings.Path.home',return_value=self.root):
            options=runtime_options()
        self.assertEqual(options['provider_runtime_version'],1)
        self.assertEqual({r['id'] for r in options['adapters']},{'codex','claude','gemini'})
        self.assertNotIn('secret-',json.dumps(options))
        self.assertTrue(all(not r['authentication_verified'] for r in options['adapters']))
        self.assertEqual({r['adapter'] for r in options['models']},{'codex','claude'})
        self.assertEqual(options['gemini_catalog_version'],1)

    def test_real_subprocess_boundary_both_providers_receive_context_and_return_handoff(self):
        # Deterministic fake CLI exercises stdin/stdout, cwd, model flags and provider output parsing without network/token usage.
        fake=self.root/'fake.py'
        fake.write_text("import json,sys,os\nprompt=sys.stdin.buffer.read().decode('utf-8')\nopen('received.txt','w',encoding='utf-8').write(prompt)\n"
                        "value="+repr(handoff())+"\n"
                        "print(json.dumps({'structured_output':value} if '--print' in sys.argv else {'response':json.dumps(value)}))\n",encoding='utf-8')
        office=Office.__new__(Office)
        office.runtime=self.root;office.state_path=self.root/'state.json';office.agents=AgentRegistry(self.root)
        office.project=2;office.project_config={'identifier':'qa'};office.codex='codex';office.api=Mock()
        office.lock=threading.RLock();office.stop=threading.Event()
        office.data={'stories':[],'chat':[],'messages':[],'active':None}
        for provider in ('claude','gemini'):
            row=office.agents.change({'name':provider,'title':'Review UI','instructions':'Check keyboard navigation.',
                'runtime':{'adapter':provider,'model':'chosen-model'},'access':'read'})
            office.agents.transition(row['id'],'ready')
            profile=office.agents.get(row['id'])
            fingerprint=AgentRedmine(Mock(),2,office.agents).fingerprint(profile)
            office.agents.sync_update(row['id'],state='synced',redmine_managed=True,redmine_user_id=9,user_status=1,fingerprint=fingerprint)
            def fake_prepare(*args,**kwargs):
                cmd,env=prepare(*args,**kwargs)
                if args[0]=='gemini':cmd=[sys.executable,str(fake),*cmd[2:]]
                return cmd,env
            with patch('agent_providers.command_for',return_value=[sys.executable,str(fake)]),patch('agent_providers.auth_hint',return_value=True),patch('agent_providers.prepare',side_effect=fake_prepare):
                result=office._call(row['id'],self.root,{'message':'Read task 123'},allow_paused=True)
            self.assertEqual(result,handoff())
            prompt=(self.root/'received.txt').read_text(encoding='utf-8')
            self.assertIn('Check keyboard navigation.',prompt);self.assertIn('Read task 123',prompt)
            if provider=='gemini':self.assertIn('FINAL OUTPUT CONTRACT',prompt)

    def test_live_models_bridge_does_not_return_hardcoded_catalog(self):
        response={'ok':True,'models':[{'id':'gemini-real','source':'google_api','verified':False}],'source':'google_api'}
        result=Mock(returncode=0,stdout=json.dumps(response).encode())
        with patch('agent_providers.shutil.which',return_value='node'),patch('agent_providers.subprocess.run',return_value=result) as run:
            self.assertEqual(gemini_models(),response)
        self.assertEqual(run.call_args.args[0][-1],'models')
        self.assertNotIn('API_KEY',str(run.call_args))

    def test_model_probe_requires_explicit_safe_model_and_sanitizes_bridge_failures(self):
        for model in ('','--model','../../other','https://bad','gemini-a/b',None):
            with patch('agent_providers.subprocess.run') as run:
                with self.assertRaises(ValueError):gemini_models('probe',model)
                run.assert_not_called()
        response=Mock(returncode=0,stdout=b'{"ok":false,"error":"quota exhausted"}')
        with patch('agent_providers.shutil.which',return_value='node'),patch('agent_providers.subprocess.run',return_value=response):
            with self.assertRaisesRegex(ValueError,'quota exhausted'):gemini_models('probe','gemini-2.5-flash')

    def test_catalog_route_is_readonly_and_model_probe_requires_office_origin(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        manager=Mock();server=make_server(manager,0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_address[1])
        try:
            with patch('agent_providers.gemini_models',return_value={'ok':True,'models':[]}) as api:
                with urlopen(base+'/lending-api/agents/models') as response:
                    self.assertEqual(json.load(response)['models'],[])
                api.assert_called_once_with()
                body=json.dumps({'adapter':'gemini','model':'gemini-one'}).encode()
                with self.assertRaises(HTTPError):
                    urlopen(Request(base+'/lending-api/agents/model-test',data=body,
                        headers={'Content-Type':'application/json','Origin':'https://evil.example'}))
                self.assertEqual(api.call_count,1)
                with urlopen(Request(base+'/lending-api/agents/model-test',data=body,
                        headers={'Content-Type':'application/json','Origin':'http://localhost:8766'})) as response:
                    self.assertTrue(json.load(response)['ok'])
                api.assert_called_with('probe','gemini-one')
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)

    def test_gemini_cached_cli_key_enables_activation_without_environment_key(self):
        with patch.dict(os.environ,{},clear=True),patch('agent_providers.Path.home',return_value=self.root),patch('agent_providers.gemini_cached_key',return_value=True),patch('agent_providers.command_for',return_value=['node','gemini.js']):
            self.assertTrue(auth_hint('gemini'))
            self.assertEqual(check_available(self.config('gemini'),require_auth=True),['node','gemini.js'])

    def test_cached_key_probe_returns_boolean_only_and_handles_failures(self):
        for payload,code,expected in [(b'{"configured":true}',0,True),(b'{"configured":false}',0,False),(b'not JSON',0,False),(b'{}',1,False)]:
            result=Mock(returncode=code,stdout=payload)
            with patch('agent_providers.shutil.which',return_value='node'),patch('agent_providers.subprocess.run',return_value=result):
                self.assertIs(gemini_cached_key(),expected)
        with patch('agent_providers.shutil.which',return_value='node'),patch('agent_providers.subprocess.run',side_effect=subprocess.TimeoutExpired('node',12)):
            self.assertFalse(gemini_cached_key())

    def test_decode_supports_fenced_json_but_not_prose_with_embedded_action(self):
        fence=chr(96)*3
        value=fence+'json\n'+json.dumps(handoff())+'\n'+fence
        self.assertEqual(decode('gemini',json.dumps({'response':value}),self.spec),handoff())
        with self.assertRaises(ValueError):decode('gemini',json.dumps({'response':'I propose '+json.dumps(handoff())}),self.spec)


if __name__=='__main__':unittest.main()
