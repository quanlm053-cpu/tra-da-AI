"""Provisioning failure/recovery tests. No network or real users created."""
import copy
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

from agent_registry import AgentRegistry
from agent_redmine import AgentRedmine
from office import Office


class MemoryRedmine:
    def __init__(self):
        self.users={9:dict(id=9,login='human',mail='human@example.invalid',firstname='Human',lastname='Owner',status=1,admin=False)}
        self.roles={i:dict(id=i,name=name,assignable=True,permissions=['view_issues','add_issue_notes'])
                    for i,name in ((4,'Developer'),(5,'Reporter'),(6,'BA'),(7,'FE'),(8,'BE'),(9,'TESTER'))}
        self.memberships=[]
        self.requests=[]
        self.admin=True
        self.lose_user_response=False
        self.lose_member_response=False
        self.fail_member=False
        self.issues={}
        self.fail_task=None

    def issue(self,key):
        return copy.deepcopy(self.issues[key])

    def update(self,key,**fields):
        if self.fail_task==key:
            self.fail_task=None
            raise ConnectionError('task update unavailable')
        if 'assigned_to_id' in fields:
            self.issues[key]['assigned_to']={'id':fields['assigned_to_id']}

    def request(self, method, path, body=None):
        self.requests.append((method,path,copy.deepcopy(body)))
        url=urlsplit(path);path=url.path;query=parse_qs(url.query,keep_blank_values=True)
        if (path.startswith('/users') or method!='GET') and not self.admin:
            raise RuntimeError(f'Redmine HTTP 403 for {method} {path}')
        if path=='/roles.json':
            return {'roles':[{'id':r['id'],'name':r['name']} for r in self.roles.values()]}
        if path.startswith('/roles/'):
            return {'role':copy.deepcopy(self.roles[int(path.split('/')[-1].split('.')[0])])}
        if path=='/users.json' and method=='GET':
            if query.get('status')==['']:
                raise RuntimeError('Redmine HTTP 422 for GET /users.json')
            needle=query.get('name',[''])[0]
            status=int(query.get('status',['1'])[0])
            rows=[u for u in self.users.values() if needle in u['login'] and u['status']==status]
            offset=int(query.get('offset',[0])[0])
            return {'users':copy.deepcopy(rows[offset:offset+100]),'total_count':len(rows)}
        if path=='/users.json' and method=='POST':
            incoming=body['user']
            if any(u['login']==incoming['login'] for u in self.users.values()):
                raise RuntimeError('Redmine HTTP 422 for POST /users.json')
            key=max(self.users)+1
            self.users[key]={k:v for k,v in incoming.items() if k!='password'}
            self.users[key]['id']=key
            if self.lose_user_response:
                self.lose_user_response=False
                raise TimeoutError('lost response')
            return {'user':copy.deepcopy(self.users[key])}
        if path.startswith('/users/'):
            key=int(path.split('/')[-1].split('.')[0])
            if method=='PUT':self.users[key].update(body['user'])
            return {'user':copy.deepcopy(self.users[key])}
        if path.startswith('/projects/'):
            project=int(path.split('/')[2])
            if method=='POST':
                if self.fail_member:
                    self.fail_member=False
                    raise ConnectionError('membership unavailable')
                values=body['membership']
                row=dict(id=len(self.memberships)+100,project={'id':project},
                         user={'id':values['user_id'],'name':'Agent'},
                         roles=[{'id':key,'name':self.roles[key]['name']} for key in values['role_ids']])
                self.memberships.append(row)
                if self.lose_member_response:
                    self.lose_member_response=False
                    raise TimeoutError('lost response')
                return {'membership':copy.deepcopy(row)}
            rows=[m for m in self.memberships if m['project']['id']==project]
            offset=int(query.get('offset',[0])[0])
            return {'memberships':copy.deepcopy(rows[offset:offset+100]),'total_count':len(rows)}
        if path.startswith('/memberships/') and method=='PUT':
            key=int(path.split('/')[-1].split('.')[0])
            row=next(m for m in self.memberships if m['id']==key)
            row['roles']=[{'id':i,'name':self.roles[i]['name']} for i in body['membership']['role_ids']]
            return {}
        raise AssertionError(f'Unexpected operation: {method} {path}')


class AgentRedmineTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry=AgentRegistry(self.temp.name)
        self.api=MemoryRedmine()
        self.connector=AgentRedmine(self.api,2,self.registry)

    def create(self,name='FE-01',specialty='frontend',access='write'):
        return self.registry.change(dict(name=name,title='Thực hiện task',specialty=specialty,
            access=access,instructions='Làm đúng phạm vi và bàn giao bằng chứng.'))

    def test_create_dedicated_account_membership_and_scoped_role(self):
        row=self.create()
        result=self.connector.ensure(row['id'])
        key=result['redmine_user_id']
        self.assertNotEqual(key,9)
        self.assertTrue(result['redmine_managed'])
        self.assertEqual(result['redmine_sync']['state'],'synced')
        self.assertEqual(self.api.users[key]['status'],3)
        self.assertFalse(self.api.users[key]['admin'])
        self.assertEqual(self.api.memberships[0]['roles'][0]['id'],7)
        reboot=AgentRegistry(self.temp.name)
        self.assertEqual(reboot.get(row['id'])['redmine_user_id'],key)

    def test_retry_after_lost_user_response_creates_one_account(self):
        row=self.create();self.api.lose_user_response=True
        self.connector.ensure(row['id']);self.connector.ensure(row['id'])
        self.assertEqual(len(self.api.users),2)
        self.assertEqual(len(self.api.memberships),1)
        self.assertEqual(sum(method=='POST' and path=='/users.json' for method,path,_ in self.api.requests),1)

    def test_lookup_handles_active_locked_and_registered_accounts_without_empty_status(self):
        for status in (1,3,2):
            row=self.create(name='Lookup '+str(status))
            identity=self.connector.identity(row)
            self.api.users[100+status]={**identity,'id':100+status,'admin':False,'status':status}
            found=self.connector._find_user(identity)
            self.assertEqual(found['id'],100+status)
        self.assertTrue(all('status=&' not in path for method,path,_ in self.api.requests))

    def test_partial_membership_failure_reuses_checkpointed_user(self):
        row=self.create();self.api.fail_member=True
        with self.assertRaises(ConnectionError):
            self.connector.ensure(row['id'])
        saved=self.registry.get(row['id'])
        self.assertTrue(saved['redmine_managed'])
        self.assertEqual(self.api.users[saved['redmine_user_id']]['status'],3)
        self.connector.ensure(row['id'])
        self.assertEqual(len(self.api.users),2)
        self.assertEqual(len(self.api.memberships),1)

    def test_lost_membership_response_does_not_duplicate_membership(self):
        row=self.create();self.api.lose_member_response=True
        self.connector.ensure(row['id'])
        self.assertEqual(len(self.api.memberships),1)

    def test_no_password_or_provider_token_is_persisted(self):
        row=self.create();self.connector.ensure(row['id'])
        body=next(body for method,path,body in self.api.requests if method=='POST' and path=='/users.json')
        password=body['user']['password']
        self.assertGreater(len(password),40)
        self.assertFalse(body['send_information'])
        stored=self.registry.path.read_text(encoding='utf-8')
        self.assertFalse(password in stored,'Generated password must not be persisted')
        self.assertNotIn('password',stored)

    def test_rename_preserves_account_and_updates_redmine_display_name(self):
        row=self.create();first=self.connector.ensure(row['id'])
        renamed=self.registry.change({**first,'name':'Giao diện mới'},row['id'])
        updated=self.connector.ensure(renamed['id'])
        self.assertEqual(updated['redmine_user_id'],first['redmine_user_id'])
        user=self.api.users[updated['redmine_user_id']]
        self.assertEqual(user['lastname'],'mới')
        self.assertEqual((user['firstname']+' '+user['lastname']),'Trà đá AI Giao diện mới')
        self.assertEqual(len(self.api.users),2)

    def test_role_and_lifecycle_are_reconciled(self):
        row=self.create();self.connector.ensure(row['id'])
        ready=self.registry.transition(row['id'],'ready')
        active=self.connector.ensure(row['id'])
        self.assertEqual(active['redmine_sync']['user_status'],1)
        self.registry.transition(row['id'],'paused')
        locked=self.connector.ensure(row['id'])
        self.assertEqual(self.api.users[locked['redmine_user_id']]['status'],3)
        changed=self.registry.change({**locked,'specialty':'backend'},row['id'])
        self.connector.ensure(changed['id'])
        self.assertEqual(self.api.memberships[0]['roles'][0]['id'],8)
        self.assertEqual(len(self.api.users),2)

    def test_new_specialty_uses_reporter_without_project_admin(self):
        row=self.create('DESIGN','specialist','read')
        result=self.connector.ensure(row['id'])
        self.assertEqual(result['redmine_sync']['role_name'],'Reporter')

    def test_legacy_shared_user_is_never_renamed_or_locked(self):
        row=self.create()
        self.registry.sync_update(row['id'],redmine_user_id=9,redmine_managed=False)
        before=copy.deepcopy(self.api.users[9])
        result=self.connector.ensure(row['id'])
        self.assertNotEqual(result['redmine_user_id'],9)
        self.assertEqual(self.api.users[9],before)

    def test_collision_with_unowned_user_is_rejected(self):
        row=self.create();identity=self.connector.identity(row)
        self.api.users[10]={**identity,'id':10,'mail':'someone@example.invalid','admin':False,'status':1}
        with self.assertRaises(ValueError):
            self.connector.ensure(row['id'])
        self.assertFalse(self.api.memberships)
        self.assertEqual(self.api.users[10]['status'],1)

    def test_duplicate_has_a_separate_account(self):
        first=self.create();self.connector.ensure(first['id'])
        cloned=self.registry.duplicate(first['id'])
        self.assertIsNone(cloned['redmine_user_id'])
        result=self.connector.ensure(cloned['id'])
        self.assertNotEqual(result['redmine_user_id'],self.registry.get(first['id'])['redmine_user_id'])
        self.assertEqual(len(self.api.memberships),2)

    def test_sync_does_not_change_profile_edit_revision(self):
        row=self.create();result=self.connector.ensure(row['id'])
        self.assertEqual(row['revision'],result['revision'])

    def test_lock_before_delete_preserves_redmine_history(self):
        row=self.create();self.registry.transition(row['id'],'ready')
        result=self.connector.ensure(row['id'])
        self.connector.lock_for_delete(row['id'])
        self.assertEqual(self.api.users[result['redmine_user_id']]['status'],3)
        self.assertEqual(len(self.api.memberships),1)

    def test_rejects_unassignable_or_admin_role(self):
        row=self.create()
        self.api.roles[7]['assignable']=False
        with self.assertRaises(ValueError):self.connector.ensure(row['id'])
        self.api.roles[7]['assignable']=True
        self.api.roles[7]['permissions'].append('manage_members')
        with self.assertRaises(ValueError):self.connector.ensure(row['id'])
        self.assertEqual(len(self.api.users),1)

    def test_sync_error_blocks_readiness_and_can_retry(self):
        row=self.create()
        office=Office.__new__(Office)
        office.api=self.api;office.project=2;office.agents=self.registry
        office.lock=threading.RLock();office.running_agents={}
        office.data={'stories':[]}
        self.registry.transition(row['id'],'ready')
        self.api.admin=False
        self.assertFalse(office.sync_agent_redmine(row['id']))
        failed=self.registry.get(row['id'])
        self.assertEqual(failed['redmine_sync']['state'],'error')
        self.assertIn('quản trị',failed['redmine_sync']['error'])
        self.assertNotIn(row['id'],office.ready_agents)
        self.api.admin=True
        self.assertTrue(office.sync_agent_redmine(row['id']))
        self.assertIn(row['id'],office.ready_agents)

    def office(self):
        office=Office.__new__(Office)
        from pathlib import Path
        office.runtime=Path(self.temp.name)
        office.api=self.api;office.project=2;office.agents=self.registry
        office.lock=threading.RLock();office.running_agents={}
        office.codex='codex';office.project_config={'identifier':'test'}
        office.data={'stories':[],'chat':[],'active':None}
        office.message=Mock();office.save=Mock()
        self.addCleanup(lambda:hasattr(office,'agent_sync_executor') and office.agent_sync_executor.shutdown(wait=True))
        return office

    def test_create_endpoint_flow_automatically_provisions_without_selecting_a_member(self):
        office=self.office()
        result=office.manage_agent(dict(operation='save',name='FE-01',title='Code giao diện',
            specialty='frontend',access='write',instructions='Kiểm tra build trước bàn giao.'))
        key=result['id']
        self.assertTrue(office.agent_sync_futures[key].result(timeout=5))
        synced=self.registry.get(key)
        self.assertTrue(synced['redmine_managed'])
        self.assertEqual(synced['redmine_sync']['state'],'synced')
        self.assertNotEqual(synced['redmine_user_id'],9)
        office.manage_agent({'operation':'verify','id':key,'revision':synced['revision']})
        self.assertTrue(office.agent_sync_futures[key].result(timeout=5))
        self.assertIn(key,office.ready_agents)
        self.assertEqual(office.assignee(key),synced['redmine_user_id'])
        office.manage_agent({'operation':'pause','id':key})
        self.assertTrue(office.agent_sync_futures[key].result(timeout=5))
        self.assertNotIn(key,office.ready_agents)
        self.assertEqual(self.api.users[synced['redmine_user_id']]['status'],3)

    def test_pending_sync_recovers_after_restart_using_stable_identity(self):
        row=self.create()
        self.api.fail_member=True
        with self.assertRaises(ConnectionError):self.connector.ensure(row['id'])
        self.registry.sync_update(row['id'],state='error',retry_at=0)
        self.registry=AgentRegistry(self.temp.name)
        office=self.office()
        office.pump_agent_sync()
        self.assertTrue(office.agent_sync_futures[row['id']].result(timeout=5))
        self.assertEqual(len(self.api.users),2)
        self.assertEqual(len(self.api.memberships),1)

    def test_dedicated_identity_cannot_be_overridden_by_client_payload(self):
        row=self.create()
        result=self.connector.ensure(row['id'])
        updated=self.registry.change({**result,'redmine_user_id':9,'redmine_managed':False},row['id'])
        self.assertEqual(updated['redmine_user_id'],result['redmine_user_id'])
        self.assertTrue(updated['redmine_managed'])

    def test_existing_pending_tasks_migrate_from_old_shared_assignee(self):
        row=self.create()
        self.registry.sync_update(row['id'],redmine_user_id=9,redmine_managed=False)
        office=self.office()
        office.data['stories']=[{'id':20,'state':'queued','tasks':{row['id']:{'id':20,'state':'queued'}}}]
        self.api.issues[20]={'id':20,'project':{'id':2},'status':{'is_closed':False},'assigned_to':{'id':9}}
        self.assertTrue(office.sync_agent_redmine(row['id']))
        profile=self.registry.get(row['id'])
        self.assertEqual(self.api.issues[20]['assigned_to']['id'],profile['redmine_user_id'])
        self.assertNotEqual(profile['redmine_user_id'],9)
        self.assertEqual(self.api.users[9]['status'],1)

    def test_partial_task_migration_can_retry_without_losing_old_assignee_receipt(self):
        row=self.create()
        self.registry.sync_update(row['id'],redmine_user_id=9,redmine_managed=False)
        office=self.office()
        office.data['stories']=[{'id':key,'state':'queued','tasks':{row['id']:{'id':key,'state':'queued'}}} for key in (20,21)]
        for key in (20,21):
            self.api.issues[key]={'id':key,'project':{'id':2},'status':{'is_closed':False},'assigned_to':{'id':9}}
        self.api.fail_task=21
        self.assertFalse(office.sync_agent_redmine(row['id']))
        self.assertEqual(self.registry.get(row['id'])['redmine_sync']['previous_user_id'],9)
        self.assertTrue(office.sync_agent_redmine(row['id']))
        profile=self.registry.get(row['id'])
        for key in (20,21):
            self.assertEqual(self.api.issues[key]['assigned_to']['id'],profile['redmine_user_id'])
        self.assertIsNone(profile['redmine_sync']['previous_user_id'])
        self.assertEqual(len(self.api.users),2)

    def test_sync_does_not_overwrite_manual_task_reassignment(self):
        row=self.create()
        office=self.office()
        office.data['stories']=[{'id':20,'state':'queued','tasks':{row['id']:{'id':20,'state':'queued'}}}]
        self.api.issues[20]={'id':20,'project':{'id':2},'status':{'is_closed':False},'assigned_to':{'id':77}}
        self.assertFalse(office.sync_agent_redmine(row['id']))
        self.assertEqual(self.api.issues[20]['assigned_to']['id'],77)
        self.assertEqual(self.registry.get(row['id'])['redmine_sync']['state'],'error')


if __name__=='__main__':
    unittest.main()
