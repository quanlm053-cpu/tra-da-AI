"""Exercise the entire workflow without invoking Codex or modifying real tickets."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from controller import ROOT, Service


class FakeAPI:
    def __init__(self):
        self.items = {200:{'id':200,'project':{'id':1},'status':{'id':8},'children':[{'id':201},{'id':202},{'id':203},{'id':204}]}}
        for issue_id in range(201,205):
            self.items[issue_id] = {'id':issue_id,'subject':str(issue_id),'parent':{'id':200},'status':{'id':13},'attachments':[{'filename':f'task-{issue_id}-product.zip'}]}
        self.history = []

    def issue(self, issue_id):
        return copy.deepcopy(self.items[issue_id])

    def update(self, issue_id, **fields):
        if 'status_id' in fields:
            self.items[issue_id]['status']['id'] = fields['status_id']
            self.history.append((issue_id,fields['status_id']))


class LifecycleTest(unittest.TestCase):
    def test_five_roles_through_story_done(self):
        service = Service.__new__(Service)
        service.config = json.loads((ROOT/'config.json').read_text())
        service.config['github']={'enabled':False}
        service.config['parallel_enabled']=False
        service.s = service.config['statuses']
        service.api = FakeAPI()
        service.save = lambda *a,**kw: None
        service.checkout = lambda job: Path('.')
        service.code_fingerprint = lambda worktree: 'reviewed'
        called = []
        plan = [dict(issue_id=i,role=r,subject=str(i),description='test') for i,r in zip(range(201,205),['ba','frontend','backend','qa'])]
        def agent(job,role):
            called.append(role)
            return {'outcome':'passed','summary':'test','checks':[{'command':'integration test','result':'passed'}],
                    'task_plan':plan if role=='ba' else [],'bugs':[]}
        service.agent = agent
        job = {'id':200,'stage':'claim','calls':0,'rounds':0}
        with patch('controller.run_git', return_value='fake-commit'),patch('preview.ensure',return_value=None):
            for _ in range(12):
                if job['stage'] == 'complete':
                    break
                service.step(job)
        self.assertEqual(called,['ba','backend','frontend','reviewer','qa'])
        self.assertEqual(job['stage'],'complete')
        self.assertEqual([status for issue,status in service.api.history if issue==200],[2,10,11,12,15])
        self.assertTrue(all(service.api.items[i]['status']['id']==15 for i in range(201,205)))


if __name__ == '__main__':
    unittest.main()
