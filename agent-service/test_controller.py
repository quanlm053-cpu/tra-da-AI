import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from controller import Cancelled, Hold, Service, stage_expected, validate_plan, ROOT


class WorkflowTests(unittest.TestCase):
    def test_completed_task_updates_progress_even_if_stage_blocked(self):
        service = self.service(2)
        service.product_uploads = Mock(return_value=[{'token':'fake','filename':'task-45-product.zip'}])
        service.api.issue.side_effect = lambda issue_id: ({'id':44,'project':{'id':1},'status':{'id':2}}
            if issue_id == 44 else {'id':45,'parent':{'id':44},'status':{'id':14},'done_ratio':0})
        service.completed_tasks({'id':44,'stage':'ba'}, 'ba', {'outcome':'blocked',
            'task_plan':[{'issue_id':45,'role':'ba'}],
            'completed_tasks':[{'issue_id':45,'evidence':'requirements.md with acceptance criteria'}]})
        self.assertEqual(service.api.update.call_args.kwargs['done_ratio'],100)
        self.assertEqual(service.api.update.call_args.kwargs['status_id'],14)
        self.assertEqual(service.api.update.call_args.kwargs['uploads'][0]['token'],'fake')

    def test_completed_task_rejects_other_roles(self):
        service = self.service(2)
        with self.assertRaises(Hold):
            service.completed_tasks({'id':44,'stage':'frontend','plan':[{'issue_id':54,'role':'pm'}]},
                'frontend',{'completed_tasks':[{'issue_id':54,'evidence':'claim'}]})
        service.api.update.assert_not_called()

    def setUp(self):
        self.status = json.loads((ROOT/'config.json').read_text())['statuses']

    def test_only_complete_expects_done(self):
        self.assertEqual(stage_expected('finish', self.status), self.status['testing'])
        self.assertEqual(stage_expected('complete', self.status), self.status['done'])

    def test_plan_preserves_all_existing_children(self):
        with self.assertRaises(Hold):
            validate_plan([], [{'id':11}])
        validate_plan([dict(issue_id=11,role='pm',subject='Human approval')],[{'id':11}])

    def test_plan_rejects_unknown_child(self):
        with self.assertRaises(Hold):
            validate_plan([dict(issue_id=999,role='frontend',subject='x')],[{'id':11}])

    def test_plan_rejects_duplicate_child(self):
        task = dict(issue_id=11,role='frontend',subject='x')
        with self.assertRaises(Hold):
            validate_plan([task,task],[{'id':11}])

    def service(self, current):
        service = Service.__new__(Service)
        service.config = {'project_id':1}
        service.s = self.status
        service.api = Mock()
        service.api.issue.return_value = {'id':22,'project':{'id':1},'status':{'id':current}}
        service.save = Mock()
        return service

    def test_blocked_never_updates(self):
        service = self.service(self.status['blocked'])
        with self.assertRaises(Cancelled):
            service.transition({'id':22,'stage':'frontend'},self.status['code_review'],'reviewer','x')
        service.api.update.assert_not_called()

    def test_external_status_never_overwritten(self):
        service = self.service(self.status['backlog'])
        with self.assertRaises(Hold):
            service.transition({'id':22,'stage':'frontend'},self.status['code_review'],'reviewer','x')
        service.api.update.assert_not_called()

    def test_recovers_successful_transition_after_crash(self):
        service = self.service(self.status['code_review'])
        job = {'id':22,'stage':'review_prepare', 'transition':{'to':self.status['code_review'],'next':'reviewer'}}
        with self.assertRaises(Cancelled):
            service.story(job)
        self.assertEqual(job['stage'],'reviewer')
        self.assertNotIn('transition',job)
        service.api.update.assert_not_called()

    def test_completed_transition_recovers_without_reopening(self):
        service = self.service(self.status['done'])
        job = {'id':22,'stage':'finish','transition':{'to':self.status['done'],'next':'complete'}}
        with self.assertRaises(Cancelled):
            service.story(job)
        service.step(job)
        service.save.assert_called_with(job,'complete')

    def test_existing_child_creation_is_idempotent(self):
        service = self.service(self.status['in_progress'])
        service.children = Mock(return_value=[{'id':42,'subject':'Existing task','description':''}])
        self.assertEqual(service.create_task({'id':22},{'subject':' Existing TASK '}),42)
        service.api.request.assert_not_called()

    def test_pm_child_blocks_story_completion(self):
        service = self.service(self.status['testing'])
        service.checkout = Mock(return_value=Path('.'))
        service.code_fingerprint = Mock(return_value='reviewed')
        service.children = Mock(return_value=[{'id':32,'status':{'id':13}}])
        with self.assertRaises(Hold):
            service.step({'id':22,'stage':'finish','reviewed_code':'reviewed'})
        service.api.update.assert_not_called()

    def test_changes_after_review_block_completion(self):
        service = self.service(self.status['testing'])
        service.checkout = Mock(return_value=Path('.'))
        service.code_fingerprint = Mock(return_value='changed')
        with self.assertRaises(Hold):
            service.step({'id':22,'stage':'finish','reviewed_code':'reviewed'})
        service.api.update.assert_not_called()


if __name__ == '__main__':
    unittest.main()
