"""Agent lifecycle and dispatch tests; no real Redmine, GitHub or AI calls."""
import copy
import json
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import Mock, patch

from agent_registry import AgentRegistry
from agent_redmine import AgentRedmine
from office import Office, ROLES, schema, STATUS, make_server


class AgentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = AgentRegistry(self.temp.name)
        self.office = Office.__new__(Office)
        self.office.runtime=Path(self.temp.name)
        self.office.agents = self.registry
        self.office.lock = threading.RLock()
        self.office.running_agents = {}
        self.office.codex = 'codex'
        self.office.project = 2
        self.office.project_config = {'identifier':'test'}
        self.office.data = {'stories':[],'chat':[],'messages':[],'active':None,'paused':True}
        self.office.message = Mock()
        self.office.save = Mock()
        self.office.api = Mock()
        lock_patch=patch('agent_redmine.AgentRedmine.lock_for_delete')
        lock_patch.start()
        self.addCleanup(lock_patch.stop)
        self.office.request_agent_sync=Mock(side_effect=self.fake_sync)
        self.office.api.request.return_value = {'memberships':[{'user':{'id':9,'name':'Test owner'}}]}
        self.parent = {'id':10,'subject':'Existing feature','project':{'id':2},'tracker':{'id':4},
                       'status':{'id':2,'is_closed':False},'children':[]}
        self.office.api.issue.return_value = self.parent
        self.office.create_issue = Mock(return_value=20)

    def fake_sync(self,key):
        row=self.registry.get(key)
        connector=AgentRedmine(self.office.api,2,self.registry)
        return self.registry.sync_update(key,state='synced',redmine_user_id=9,redmine_managed=True,
            login=connector.identity(row)['login'],user_status=connector.desired_status(row),
            fingerprint=connector.fingerprint(row))

    def create(self, **changes):
        return self.registry.change(dict(name='SECURITY',title='Rà soát bảo mật',specialty='specialist',
            instructions='Đọc API; ghi kết quả có bằng chứng.',redmine_user_id=9,**changes))

    def ready(self, **changes):
        row = self.create(**changes)
        return self.office.manage_agent({'operation':'verify','id':row['id']})

    def test_defaults_preserve_ids_and_flow(self):
        self.assertEqual([a['id'] for a in self.registry.listing()],['pm',*ROLES])
        self.assertEqual(len(self.registry.listing()),8)

    def test_profile_survives_restart_and_is_project_scoped(self):
        row=self.create()
        self.assertEqual(AgentRegistry(self.temp.name).get(row['id']),row)
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(len(AgentRegistry(other).listing()),8)

    def test_new_agent_not_runnable_until_verified(self):
        row=self.create()
        self.assertEqual(row['status'],'draft')
        self.assertNotIn(row['id'],self.office.ready_agents)
        self.office.manage_agent({'operation':'verify','id':row['id']})
        self.assertIn(row['id'],self.office.ready_agents)

    def test_invalid_redmine_mapping_blocks_activation(self):
        row=self.create()
        self.office.request_agent_sync.side_effect=lambda key:self.registry.sync_update(key,state='error',error='Missing membership')
        self.office.manage_agent({'operation':'verify','id':row['id']})
        self.assertNotIn(row['id'],self.office.ready_agents)
        with self.assertRaises(ValueError):
            self.office.assignee(row['id'])

    def test_missing_cli_blocks_activation(self):
        row=self.create();self.office.codex=None
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'verify','id':row['id']})

    def test_schema_exposes_only_ready_identities(self):
        row=self.ready()
        fields=schema(pm=True,agent_ids=self.office.ready_agents)['properties']
        self.assertIn(row['id'],fields['action']['properties']['assignee']['enum'])
        self.assertIn(row['id'],fields['consult_role']['enum'])
        self.office.manage_agent({'operation':'pause','id':row['id']})
        self.assertNotIn(row['id'],schema(agent_ids=self.office.ready_agents)['properties']['consult_role']['enum'])

    def test_optimistic_revision_prevents_lost_edits(self):
        row=self.create()
        self.registry.change({**row,'name':'SECURITY 2'},row['id'])
        with self.assertRaises(ValueError):
            self.registry.change({**row,'title':'Old form'},row['id'])

    def test_duplicate_names_and_invalid_types(self):
        self.create()
        with self.assertRaises(ValueError): self.create()
        with self.assertRaises(ValueError): self.registry.change({'name':{},'title':'Task'})
        with self.assertRaises(ValueError): self.registry.change({'name':'X','title':'Task','redmine_user_id':True})

    def test_cannot_create_second_coordinator_or_promote_read_only_reviewer(self):
        for values in ({'specialty':'pm'},{'specialty':'reviewer','access':'write'}):
            with self.assertRaises(ValueError):
                self.registry.change({'name':'X','title':'Task',**values})

    def test_persistence_failure_rolls_back_memory(self):
        with patch.object(self.registry,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.create()
        self.assertEqual(len(self.registry.listing()),8)

    def test_pause_archive_and_restore_keep_history(self):
        row=self.ready()
        self.office.manage_agent({'operation':'pause','id':row['id']})
        self.office.manage_agent({'operation':'archive','id':row['id']})
        self.assertEqual(self.registry.get(row['id'])['status'],'archived')
        self.office.manage_agent({'operation':'restore','id':row['id']})
        self.office.manage_agent({'operation':'verify','id':row['id']})
        self.assertEqual(self.registry.get(row['id'])['status'],'ready')

    def test_running_agent_cannot_be_reconfigured(self):
        row=self.ready();self.office.running_agents[row['id']]=1
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'pause','id':row['id']})

    def test_unfinished_work_prevents_archive(self):
        row=self.ready()
        self.office.data['stories']=[{'id':20,'state':'queued','tasks':{row['id']:{'id':20}}}]
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'archive','id':row['id']})

    def test_existing_workflow_agents_cannot_be_archived(self):
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'archive','id':'backend'})

    def test_advisory_task_is_assigned_in_redmine_without_expanding_story_pipeline(self):
        row=self.ready()
        response=self.office.manage_agent(dict(operation='assign',id=row['id'],story_id=10,
            title='Kiểm tra API',acceptance='Báo cáo có bằng chứng',request_id='request-123456'))
        work=self.office.data['stories'][0]
        self.assertIn('Task #20',response['message'])
        self.assertTrue(work['advisory'])
        self.assertEqual(work['workflow'],[row['id']])
        self.assertEqual(self.office.create_issue.call_args.kwargs['assignee'],9)
        self.office.manage_agent(dict(operation='assign',id=row['id'],story_id=10,
            title='Kiểm tra API',acceptance='Báo cáo có bằng chứng',request_id='request-123456'))
        self.assertEqual(self.office.create_issue.call_count,1)
        self.assertEqual(len(self.office.data['stories']),1)

    def test_writer_still_requires_review_and_testing(self):
        row=self.ready(access='write')
        self.office.dispatch_task({'id':1},{'id':10},{'title':'Fix','acceptance':'Tests pass'},row['id'])
        work=self.office.data['stories'][0]
        self.assertFalse(work['advisory'])
        self.assertEqual(work['workflow'],[row['id'],'reviewer','tester'])

    def test_assignment_rejects_wrong_project_and_non_story(self):
        row=self.ready()
        self.parent['project']['id']=999
        with self.assertRaises(ValueError):
            self.office.manage_agent(dict(operation='assign',id=row['id'],story_id=10,
                title='Fix',acceptance='Pass',request_id='request-123456'))
        self.office.create_issue.assert_not_called()

    def test_failed_call_releases_running_lease(self):
        row=self.ready()
        with patch.object(self.office,'_call',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.office.call(row['id'],Path(self.temp.name),{})
        self.assertFalse(self.office.agent_busy(row['id']))

    def test_instruction_changes_require_reverification(self):
        row=self.ready()
        edited=self.registry.change({**row,'instructions':'New scope'},row['id'])
        self.assertEqual(edited['status'],'draft')

    def test_subprocess_uses_profile_skill_and_read_only_sandbox(self):
        row=self.ready()
        self.office.runtime=Path(self.temp.name)
        self.office.state_path=Path(self.temp.name)/'state.json'
        self.office.stop=threading.Event()
        self.office.project_config={}
        process=Mock()
        process.poll.return_value=0;process.returncode=0
        process.stdin=Mock()
        result={'summary':'Report','outcome':'passed','consult_role':'none','consult_question':'','artifacts':[]}
        def popen(command,**kwargs):
            Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(result),encoding='utf-8')
            return process
        with patch('office.subprocess.Popen',side_effect=popen) as launch, patch('office.Service.terminate'):
            self.office.call(row['id'],Path(self.temp.name),{})
        command=launch.call_args.args[0]
        self.assertEqual(command[command.index('--sandbox')+1],'read-only')
        prompt=process.stdin.write.call_args.args[0].decode()
        self.assertIn('Rà soát bảo mật',prompt)
        self.assertIn('Đọc API',prompt)

    def test_http_endpoints_and_origin_guard(self):
        manager=Mock()
        manager.office.return_value=self.office
        manager.listing.return_value=[{'identifier':'test'}]
        server=make_server(manager,0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)+'/lending-api'
            with urlopen(base+'/agents') as r:
                self.assertEqual(len(json.load(r)),8)
            with urlopen(base+'/state') as r:
                self.assertEqual(len(json.load(r)['agents']),8)
            body=json.dumps({'name':'SECURITY','title':'Audit','instructions':'Read APIs',
                             'redmine_user_id':9,'project':'test'}).encode()
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(base+'/agents',data=body,headers={'Content-Type':'application/json','Origin':'https://evil.example'}))
            self.assertEqual(caught.exception.code,403)
            with urlopen(Request(base+'/agents',data=body,headers={
                    'Content-Type':'application/json','Origin':'http://localhost:8766'})) as r:
                result=json.load(r)
                self.assertEqual(result['status'],'draft')
            self.assertEqual(len(self.registry.listing()),9)
            manager.office.assert_called_with('test')
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)

    def test_advisory_completion_does_not_publish(self):
        row=self.ready()
        story=dict(id=20,parent_story=10,owner_role=row['id'],advisory=True,state='queued',stage=1,
                   workflow=[row['id']],tasks={row['id']:{'id':20,'state':'delivered'}},repair_role='')
        self.office.stop=threading.Event()
        self.office.repo_for=Mock(return_value=Path(self.temp.name))
        self.office.publish=Mock()
        child={'id':20,'project':{'id':2},'status':{'id':15,'is_closed':True}}
        self.office.api.issue.side_effect=lambda key:child if key==20 else self.parent
        self.office.step(story)
        self.assertEqual(story['state'],'done')
        self.office.publish.assert_not_called()

    def test_paused_agent_does_not_touch_checkout_or_redmine(self):
        row=self.ready()
        self.office.manage_agent({'operation':'pause','id':row['id']})
        self.office.repo_for=Mock()
        self.office.api.reset_mock()
        self.office.stop=threading.Event()
        with self.assertRaises(ValueError):
            self.office.step({'id':20,'workflow':[row['id']],'stage':0,'repair_role':''})
        self.office.repo_for.assert_not_called()
        self.office.api.issue.assert_not_called()

    def test_old_list_storage_migrates_without_losing_profiles(self):
        old=self.registry.listing()
        self.registry.path.parent.mkdir(parents=True,exist_ok=True)
        self.registry.path.write_text(json.dumps(old),encoding='utf-8')
        migrated=AgentRegistry(self.temp.name)
        migrated.change({'name':'Extra','title':'Task'})
        stored=json.loads(migrated.path.read_text(encoding='utf-8'))
        self.assertEqual(stored['version'],2)
        self.assertEqual(stored['agents'][:8],old)

    def test_duplicate_copies_skills_but_not_identity_or_ready_state(self):
        row=self.ready()
        cloned=self.office.manage_agent({'operation':'duplicate','id':row['id']})
        self.assertNotEqual(cloned['id'],row['id'])
        self.assertEqual(cloned['name'],'SECURITY 2')
        self.assertEqual(cloned['instructions'],row['instructions'])
        self.assertEqual(cloned['status'],'draft')
        self.assertFalse(cloned['builtin'])
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'duplicate','id':'pm'})

    def test_archive_restore_requires_verification_and_retains_identity(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'verify','id':row['id']})
        restored=self.office.manage_agent({'operation':'restore','id':row['id']})
        self.assertEqual(restored['id'],row['id'])
        self.assertEqual(restored['status'],'draft')
        self.assertNotIn(row['id'],self.office.ready_agents)

    def test_restore_collision_can_be_resolved_by_renaming_archived_profile(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        self.create()
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'restore','id':row['id']})
        archived=self.registry.get(row['id'])
        updated=self.registry.change({**archived,'name':'SECURITY OLD'},row['id'])
        self.assertEqual(updated['status'],'archived')
        self.office.manage_agent({'operation':'restore','id':row['id']})

    def test_capacity_applies_to_restore_as_well_as_creation(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        for i in range(16):
            self.registry.change({'name':f'Extra {i}','title':'Task'})
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'restore','id':row['id']})

    def test_terminate_forgets_local_credential_but_preserves_profile(self):
        row=self.ready()
        with patch('office.forget_agent_credentials') as forget:
            ended=self.office.manage_agent({'operation':'terminate','id':row['id'],'confirm_name':row['name']})
        forget.assert_called_once_with(row['id'])
        self.assertEqual(ended['status'],'terminated')
        self.assertNotIn(row['id'],self.office.ready_agents)
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'resume','id':row['id']})
        self.office.manage_agent({'operation':'restore','id':row['id']})

    def test_delete_requires_inactive_revision_and_typed_confirmation(self):
        row=self.ready()
        for changes in ({},{'confirm_name':'WRONG'},{'revision':-1}):
            with self.assertRaises(ValueError):
                self.office.manage_agent({'operation':'delete','id':row['id'],'revision':row['revision'],'confirm_name':row['name'],**changes})
        self.office.manage_agent({'operation':'archive','id':row['id']})
        archived=self.registry.get(row['id'])
        for changes in ({'confirm_name':'WRONG'},{'revision':-1}):
            with self.assertRaises(ValueError):
                self.office.manage_agent({'operation':'delete','id':row['id'],'revision':archived['revision'],'confirm_name':row['name'],**changes})

    def test_hard_delete_preserves_attribution_without_skill_content(self):
        row=self.ready()
        self.office.data['messages']=[{'sender':row['id'],'text':'Historical handoff'}]
        self.office.manage_agent({'operation':'archive','id':row['id']})
        archived=self.registry.get(row['id'])
        with patch('office.forget_agent_credentials') as forget:
            result=self.office.manage_agent({'operation':'delete','id':row['id'],
                'revision':archived['revision'],'confirm_name':row['name']})
        self.assertTrue(result['deleted'])
        forget.assert_called_once_with(row['id'])
        with self.assertRaises(ValueError): self.registry.get(row['id'])
        self.assertEqual(self.office.labels[row['id']],'SECURITY')
        self.assertEqual(len(self.office.data['messages']),1)
        rebooted=AgentRegistry(self.temp.name)
        self.assertEqual(rebooted.deleted_profiles()[0]['name'],'SECURITY')
        self.assertNotIn('instructions',rebooted.deleted_profiles()[0])
        self.assertEqual(rebooted.history(row['id'])[0]['operation'],'delete')
        self.assertNotIn(row['instructions'],self.registry.path.read_text(encoding='utf-8'))

    def test_delete_failure_restores_profile_and_audit(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        archived=self.registry.get(row['id'])
        before=copy.deepcopy(self.registry.events)
        with patch.object(self.registry,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.registry.delete(row['id'],archived['revision'],row['name'])
        self.assertEqual(self.registry.get(row['id']),archived)
        self.assertEqual(self.registry.events,before)
        self.assertFalse(self.registry.deleted_profiles())

    def test_credential_cleanup_failure_is_reported_after_delete(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        archived=self.registry.get(row['id'])
        with patch('office.forget_agent_credentials',side_effect=OSError('vault')):
            result=self.office.manage_agent({'operation':'delete','id':row['id'],
                'revision':archived['revision'],'confirm_name':row['name']})
        self.assertTrue(result['deleted'])
        self.assertIn('warning',result)

    def test_builtin_cannot_be_deleted_or_terminated(self):
        row=self.registry.get('backend')
        for op in ('delete','terminate'):
            with patch('office.forget_agent_credentials') as forget:
                with self.assertRaises(ValueError):
                    self.office.manage_agent({'operation':op,'id':'backend','revision':row['revision'],'confirm_name':row['name']})
                forget.assert_not_called()

    def test_lifecycle_uses_revision_to_reject_stale_actions(self):
        row=self.ready()
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'pause','id':row['id'],'revision':row['revision']-1})
        self.assertEqual(self.registry.get(row['id'])['status'],'ready')

    def test_transfer_unstarted_task_updates_redmine_and_local_pipeline(self):
        source=self.ready()
        target=self.registry.duplicate(source['id'])
        self.office.manage_agent({'operation':'verify','id':target['id']})
        self.office.dispatch_task({'id':1},{'id':10},{'title':'Audit API','acceptance':'Report'},source['id'])
        issue={'id':20,'project':{'id':2},'status':{'id':13,'is_closed':False},'assigned_to':{'id':9}}
        self.office.api.issue.return_value=issue
        result=self.office.manage_agent({'operation':'reassign','id':source['id'],'target_id':target['id'],'work_id':20})
        work=self.office.data['stories'][0]
        self.assertEqual(work['workflow'],[target['id']])
        self.assertEqual(work['owner_role'],target['id'])
        self.assertNotIn(source['id'],work['tasks'])
        self.assertIn('Task #20',result['message'])
        self.office.api.update.assert_called_with(20,assigned_to_id=9,subject='SECURITY 2: Audit API')
        self.office.manage_agent({'operation':'archive','id':source['id']})

    def test_transfer_rejects_running_or_already_delivered_task(self):
        source=self.ready()
        target=self.registry.duplicate(source['id'])
        self.office.manage_agent({'operation':'verify','id':target['id']})
        self.office.dispatch_task({'id':1},{'id':10},{'title':'Audit API','acceptance':'Report'},source['id'])
        work=self.office.data['stories'][0]
        for changes in ({'state':'running'},{'state':'queued','results':{source['id']:{'summary':'done'}}}):
            work.update(changes)
            with self.assertRaises(ValueError):
                self.office.manage_agent({'operation':'reassign','id':source['id'],'target_id':target['id'],'work_id':20})

    def test_audit_records_metadata_without_storing_instruction_values(self):
        row=self.ready()
        self.office.manage_agent({'operation':'pause','id':row['id']})
        events=self.registry.history(row['id'])
        self.assertEqual(next(e for e in events if e['operation']=='status')['status'],'paused')
        self.assertEqual(events[-1]['operation'],'create')
        self.assertNotIn(row['instructions'],json.dumps(events,ensure_ascii=False))

    def test_cancel_only_queued_conversation_of_selected_agent(self):
        row=self.ready()
        chat={'id':88,'role':row['id'],'state':'queued','message':'Question','reply':''}
        self.office.data['chat']=[chat]
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'archive','id':row['id']})
        with self.assertRaises(ValueError):
            self.office.manage_agent({'operation':'cancel_chat','id':'backend','chat_id':88})
        self.office.manage_agent({'operation':'cancel_chat','id':row['id'],'chat_id':88})
        self.assertEqual(chat['state'],'failed')
        self.office.manage_agent({'operation':'archive','id':row['id']})

    def test_cancel_conversation_rolls_back_if_state_cannot_be_saved(self):
        row=self.ready()
        chat={'id':88,'role':row['id'],'state':'queued','message':'Question','reply':''}
        self.office.data['chat']=[chat]
        self.office.save.side_effect=OSError('disk')
        with self.assertRaises(OSError):
            self.office.manage_agent({'operation':'cancel_chat','id':row['id'],'chat_id':88})
        self.assertEqual(chat['state'],'queued')

    def test_http_delete_requires_confirmation_and_history_stays_queryable(self):
        row=self.ready()
        self.office.manage_agent({'operation':'archive','id':row['id']})
        archived=self.registry.get(row['id'])
        manager=Mock()
        manager.office.return_value=self.office
        manager.listing.return_value=[]
        server=make_server(manager,0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(payload):
            return urlopen(Request(base+'/agents',data=json.dumps(payload).encode(),headers={
                'Origin':'http://localhost:8766','Content-Type':'application/json'}))
        try:
            base='http://127.0.0.1:'+str(server.server_port)+'/lending-api'
            payload={'operation':'delete','id':row['id'],'revision':archived['revision'],'confirm_name':'WRONG'}
            with self.assertRaises(HTTPError) as caught:
                request(payload)
            self.assertEqual(caught.exception.code,400)
            payload['confirm_name']=row['name']
            with patch('office.forget_agent_credentials'),request(payload) as response:
                self.assertTrue(json.load(response)['deleted'])
            with urlopen(base+'/agents/history?id='+row['id']) as response:
                self.assertEqual(json.load(response)[0]['operation'],'delete')
            with urlopen(base+'/state') as response:
                data=json.load(response)
                self.assertEqual(data['agent_management_version'],4)
                self.assertEqual(data['deleted_agents'][0]['name'],row['name'])
                self.assertNotIn(row['id'],[a['id'] for a in data['agents']])
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)


if __name__=='__main__':
    unittest.main()
