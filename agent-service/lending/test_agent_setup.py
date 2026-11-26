import json
import tempfile
import threading
import time
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock,patch

from agent_registry import AgentRegistry
from agent_settings import settings,validate,SkillLibrary,enabled_tools,allowed
from agent_redmine import AgentRedmine
from office import Office,HERE,schema


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.registry=AgentRegistry(self.temp.name)
        self.office=Office.__new__(Office)
        self.office.runtime=Path(self.temp.name);self.office.state_path=self.office.runtime/'state.json'
        self.office.agents=self.registry;self.office.project=2;self.office.project_config={'identifier':'test'}
        self.office.lock=threading.RLock();self.office.stop=threading.Event()
        self.office.running_agents={};self.office.codex='codex'
        self.office.data={'stories':[],'chat':[],'messages':[],'active':None}
        self.office.save=Mock();self.office.message=Mock()
        self.office.api=Mock();self.office.assignee=Mock(return_value=9)
        self.office.api.issue.return_value={'id':10,'project':{'id':2},'tracker':{'id':4},
            'status':{'id':2,'is_closed':False},'children':[]}
        self.office.create_issue=Mock(return_value=20)
        self.office.request_agent_sync=Mock(side_effect=lambda key:self.registry.get(key))

    def agent(self,**extra):
        row=self.registry.change(dict(name='Helper',title='Task',specialty='specialist',instructions='Instructions',**extra))
        self.registry.transition(row['id'],'ready')
        row=self.registry.get(row['id'])
        connector=AgentRedmine(self.office.api,2,self.registry)
        return self.registry.sync_update(row['id'],state='synced',redmine_managed=True,redmine_user_id=9,
            user_status=1,fingerprint=connector.fingerprint(row))

    def proposal(self,**extra):
        return dict(type='delegate_task',target_id='frontend',parent_story_id=10,title='Independent UI fix',
                    instructions='Build passes',independent=True,**extra)

    def test_legacy_defaults_preserve_execution_and_pm_delegation(self):
        old={'id':'pm','specialty':'pm'}
        result=settings(old)
        self.assertEqual(result['runtime']['timeout_minutes'],30)
        self.assertEqual(result['collaboration']['autonomy'],'delegate')
        self.assertEqual(settings({'id':'new'})['collaboration']['assign_to'],'nobody')

    def test_all_profile_fields_survive_restart_and_duplication(self):
        row=self.registry.change(dict(name='Design',title='UI',role='Product Designer',description='UI/UX',
            goals=['Responsive'],work_rules=['Review first'],tags=['ui-design'],runtime={'model':'gpt-6.2-sol'}))
        reboot=AgentRegistry(self.temp.name).get(row['id'])
        self.assertEqual(reboot['goals'],['Responsive'])
        self.assertEqual(reboot['runtime']['model'],'gpt-6.2-sol')
        clone=self.registry.duplicate(row['id'])
        self.assertEqual(clone['work_rules'],row['work_rules'])
        self.assertNotEqual(clone['id'],row['id'])

    def test_validation_rejects_unsupported_adapter_limits_tags_and_tools(self):
        for payload in (
            {'runtime':{'adapter':'unknown'}},{'runtime':{'timeout_minutes':0}},
            {'runtime':{'concurrent_attempts':9}},{'runtime':{'timeout_minutes':True}},
            {'runtime':{'model':'--unsafe'}},{'tags':['Bad Tag']},
            {'capabilities':{'tools':['unknown']}},{'collaboration':{'max_depth':0}},
            {'collaboration':{'can_propose_agents':'yes'}},
        ):
            with self.subTest(payload=payload),self.assertRaises(ValueError):validate(payload)

    def test_custom_skill_persists_and_cannot_read_arbitrary_paths(self):
        library=self.office.library
        skill=library.create({'name':'UX Review','description':'UX','content':'Check keyboard navigation.'})
        self.assertIn('keyboard',SkillLibrary(self.temp.name,HERE/'skills').content([skill['id']]))
        with self.assertRaises(ValueError):library.content(['../../config.json'])
        with self.assertRaises(ValueError):library.create({'name':'UX Review','content':'Duplicate'})

    def test_default_tools_and_explicit_empty_tools_are_different(self):
        self.assertIn('shell',enabled_tools({}))
        self.assertEqual(enabled_tools({'capabilities':{'default_tools':False,'tools':[]}}),[])

    def test_model_effort_tools_and_prompt_reach_the_actual_process(self):
        skill=self.office.library.create({'name':'Review UI','content':'Check keyboard navigation.'})
        row=self.agent(role='UI Specialist',goals=['Responsive'],work_rules=['Run build'],
            runtime={'model':'gpt-6.2-sol','effort':'high','timeout_minutes':2},
            capabilities={'skill_ids':[skill['id']],'default_tools':False,'tools':['read_issue']})
        proc=Mock();proc.poll.return_value=0;proc.returncode=0;proc.stdin=Mock()
        def launch(command,**kwargs):
            Path(command[command.index('--output-last-message')+1]).write_text(json.dumps({
                'outcome':'passed','summary':'OK','consult_role':'none','consult_question':'','artifacts':[]}),encoding='utf-8')
            return proc
        with patch('office.subprocess.Popen',side_effect=launch) as start,patch('office.Service.terminate'):
            self.office.call(row['id'],Path(self.temp.name),{})
        command=start.call_args.args[0]
        self.assertEqual(command[command.index('--model')+1],'gpt-6.2-sol')
        self.assertIn('model_reasoning_effort="high"',command)
        self.assertIn('features.shell_tool=false',command)
        self.assertIn('web_search="disabled"',command)
        self.assertIn('mcp_servers.lending.enabled_tools=["read_issue"]',command)
        prompt=proc.stdin.write.call_args.args[0].decode()
        for expected in ('Responsive','Run build','keyboard navigation','UI Specialist'):
            self.assertIn(expected,prompt)

    def test_concurrency_limit_waits_and_releases_leases(self):
        row=self.agent(runtime={'concurrent_attempts':1})
        active=0;peak=0;mutex=threading.Lock()
        def run(*args,**kwargs):
            nonlocal active,peak
            with mutex:active+=1;peak=max(peak,active)
            time.sleep(.1)
            with mutex:active-=1
            return {}
        with patch.object(self.office,'_call',side_effect=run):
            threads=[threading.Thread(target=self.office.call,args=(row['id'],Path(self.temp.name),{})) for _ in range(3)]
            for t in threads:t.start()
            for t in threads:t.join(timeout=3)
        self.assertEqual(peak,1)
        self.assertEqual(self.office.running_agents[row['id']],0)

    def test_timeout_uses_agent_setting_and_stops_process(self):
        row=self.agent(runtime={'timeout_minutes':1})
        proc=Mock();proc.poll.return_value=None;proc.stdin=Mock()
        with patch('office.subprocess.Popen',return_value=proc),patch('office.Service.terminate') as stop,patch('office.time.monotonic',side_effect=[0,61]):
            with self.assertRaises(TimeoutError):self.office._call(row['id'],Path(self.temp.name),{})
        stop.assert_called_once()

    def test_two_writers_in_same_checkout_are_serialized(self):
        row=self.agent(access='write',runtime={'concurrent_attempts':2})
        active=0;peak=0;mutex=threading.Lock()
        def run(*args,**kwargs):
            nonlocal active,peak
            with mutex:active+=1;peak=max(peak,active)
            time.sleep(.1)
            with mutex:active-=1
            return {}
        with patch.object(self.office,'_call',side_effect=run):
            workers=[threading.Thread(target=self.office.call,args=(row['id'],Path(self.temp.name),{})) for _ in range(2)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(timeout=3)
        self.assertEqual(peak,1)
        self.assertFalse(self.office.running_paths)

    def test_mcp_server_rejects_a_disabled_tool_without_calling_redmine(self):
        payload='\n'.join(json.dumps(row) for row in [
            {'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'read_issue','arguments':{'id':1}}}])+'\n'
        result=subprocess.run([sys.executable,str(HERE/'mcp.py'),str(Path(self.temp.name)/'absent.json'),
            '["project_state"]'],input=payload.encode(),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)
        responses=[json.loads(line) for line in result.stdout.decode().splitlines()]
        self.assertEqual([tool['name'] for tool in responses[0]['result']['tools']],['project_state'])
        self.assertTrue(responses[1]['result']['isError'])

    def test_consultation_scope_is_enforced_before_second_model_call(self):
        row=self.agent(collaboration={'consult_to':'nobody'})
        with patch.object(self.office,'call',return_value={'consult_role':'backend','consult_question':'Help'} ) as call:
            with self.assertRaises(ValueError):self.office.consult(row['id'],Path(self.temp.name),{})
        self.assertEqual(call.call_count,1)

    def test_schema_consultation_and_assignment_scopes_are_separate(self):
        fields=schema(pm=True,agent_ids=['pm','frontend','backend'],consult_ids=['backend'])['properties']
        self.assertEqual(fields['consult_role']['enum'],['none','backend'])
        self.assertIn('frontend',fields['action']['properties']['assignee']['enum'])

    def test_nobody_cannot_delegate_and_no_proposal_permission_cannot_hire(self):
        row=self.agent()
        result=self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},chat_id=1)
        self.assertIn('chưa được',result[0])
        self.assertFalse(self.office.data.get('agent_requests'))
        request=self.proposal();request['type']='propose_agent'
        self.office.process_agent_requests(row['id'],{'requests':[request]},chat_id=2)
        self.assertEqual(len(self.registry.listing()),9)

    def test_suggested_task_waits_for_owner_and_approval_is_idempotent(self):
        row=self.agent(collaboration={'assign_to':'selected','assignees':['frontend'],'autonomy':'suggest'})
        self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},chat_id=1)
        request=self.office.data['agent_requests'][0]
        self.office.create_issue.assert_not_called()
        response=self.office.review_agent_request({'request_id':request['id'],'decision':'approve'})
        self.assertIn('Task #20',response['message'])
        self.office.review_agent_request({'request_id':request['id'],'decision':'approve'})
        self.assertEqual(self.office.create_issue.call_count,1)

    def test_independent_delegation_obeys_depth_and_open_limits(self):
        row=self.agent(collaboration={'assign_to':'team','autonomy':'delegate','max_depth':1,'max_open_subtasks':1})
        result=self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},chat_id=1)
        self.assertIn('Đã phân công',result[0])
        result=self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},chat_id=2)
        self.assertIn('giới hạn',result[0])
        result=self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},work={'id':99,'delegation_depth':1})
        self.assertIn('độ sâu',result[0])

    def test_dependent_task_does_not_create_cycle_with_parent_story(self):
        row=self.agent(collaboration={'assign_to':'team','autonomy':'suggest'})
        source={'id':10,'state':'queued','tasks':{}}
        self.office.data['stories']=[source]
        proposal=self.proposal();proposal['independent']=False
        self.office.process_agent_requests(row['id'],{'requests':[proposal]},work=source)
        request=self.office.data['agent_requests'][0]
        self.office.review_agent_request({'request_id':request['id'],'decision':'approve'})
        self.assertEqual(request['state'],'waiting_source')
        self.office.create_issue.assert_not_called()
        source['state']='done'
        self.office.execute_agent_request(request)
        self.assertEqual(request['state'],'executed')

    def test_agent_proposal_always_requires_owner_and_creates_only_a_draft(self):
        row=self.agent(collaboration={'can_propose_agents':True,'autonomy':'delegate'})
        proposal=self.proposal();proposal.update(type='propose_agent',title='New Designer')
        self.office.process_agent_requests(row['id'],{'requests':[proposal]},chat_id=1)
        request=self.office.data['agent_requests'][0]
        self.assertEqual(len(self.registry.listing()),9)
        self.office.review_agent_request({'request_id':request['id'],'decision':'approve'})
        added=self.registry.get(request['created_agent'])
        self.assertEqual(added['status'],'draft')
        self.assertEqual(added['access'],'read')
        self.office.review_agent_request({'request_id':request['id'],'decision':'approve'})
        self.assertEqual(len(self.registry.listing()),10)

    def test_rejected_request_cannot_be_executed(self):
        row=self.agent(collaboration={'assign_to':'team'})
        self.office.process_agent_requests(row['id'],{'requests':[self.proposal()]},chat_id=1)
        request=self.office.data['agent_requests'][0]
        self.office.review_agent_request({'request_id':request['id'],'decision':'reject'})
        with self.assertRaises(ValueError):self.office.execute_agent_request(request)
        self.office.create_issue.assert_not_called()

    def test_pm_suggest_mode_queues_action_without_changing_redmine(self):
        pm=self.registry.get('pm')
        self.registry.change({**pm,'collaboration':{**pm['collaboration'],'autonomy':'suggest'}},'pm')
        answer=self.office.execute_pm_action({'id':1,'message':'Create task'},{
            'summary':'Plan','outcome':'passed','action':{'type':'create_task','title':'Fix UI','assignee':'frontend'}})
        self.assertIn('chờ duyệt',answer)
        self.office.api.update.assert_not_called()
        self.assertEqual(self.office.data['agent_requests'][0]['type'],'pm_action')


if __name__=='__main__':unittest.main()
