"""Direct owner assignment must bind real work without calling a model."""
import threading
import unittest
from unittest.mock import Mock, PropertyMock, patch
from office import Office, ROLES, direct_task_request


class DirectAssignmentTest(unittest.TestCase):
    def setUp(self):
        self.o=Office.__new__(Office)
        self.o.lock=threading.RLock()
        self.o.project=2
        self.o.agents=Mock()
        self.o.agents.get.side_effect=lambda r: dict(id=r,name=r,specialty='frontend',access='write')
        self.o.agents.listing.return_value=[dict(id=r,name=r) for r in (*ROLES,'fe01')]
        self.o.agents.deleted_profiles.return_value=[]
        self.o.manager=None
        self.o.save=Mock()
        self.o.message=Mock()
        self.o.assignee=Mock(return_value=18)
        self.o.api=Mock()
        self.o.api.issue.return_value=dict(project={'id':2},status={'is_closed':False},assigned_to={'id':18})
        self.story=dict(id=192,state='queued',stage=0,tasks={'frontend':dict(id=196,state='queued')},results={})
        self.o.data=dict(stories=[self.story],active=None,paused=True)
        self.ready=patch.object(Office,'ready_agents',new_callable=PropertyMock,return_value=['fe01'])
        self.ready.start()
        self.addCleanup(self.ready.stop)

    def test_explicit_intent_only(self):
        self.assertEqual(direct_task_request('làm task #196 đi'),196)
        for text in ('đừng làm task 196','làm task 196 được không?','ví dụ làm task 196','task 196 là gì'):
            self.assertIsNone(direct_task_request(text))

    def test_rebind_preserves_dependencies_and_pause(self):
        reply=self.o.assign_existing_task('fe01',196)
        self.assertEqual(self.story['workflow'],['sa','ba','backend','fe01','devops','reviewer','tester'])
        self.assertEqual(self.story['tasks']['fe01']['id'],196)
        self.assertNotIn('frontend',self.story['tasks'])
        self.assertEqual(self.story['stage'],0)
        self.assertTrue(self.o.data['paused'])
        self.assertIn('tạm dừng',reply)
        self.o.api.update.assert_called_once_with(196,assigned_to_id=18)

    def test_repeat_does_not_duplicate_slot(self):
        self.o.assign_existing_task('fe01',196)
        self.o.assign_existing_task('fe01',196)
        self.assertEqual(self.story['workflow'].count('fe01'),1)
        self.assertEqual(len(self.story['tasks']),1)

    def test_reject_running_or_closed_or_unconfirmed(self):
        self.story['tasks']['frontend']['state']='running'
        with self.assertRaises(ValueError): self.o.assign_existing_task('fe01',196)
        self.o.api.update.assert_not_called()
        self.story['tasks']['frontend']['state']='queued'
        self.o.api.issue.return_value['assigned_to']['id']=15
        with self.assertRaises(RuntimeError): self.o.assign_existing_task('fe01',196)
        self.assertNotIn('workflow',self.story)

    def test_direct_chat_does_not_generate_model_answer(self):
        self.o.consult=Mock(side_effect=AssertionError('Must not call model'))
        row=dict(id=60,role='fe01',message='làm task 196 đi')
        self.o.pm(row)
        self.assertEqual(row['state'],'done')
        self.o.consult.assert_not_called()


if __name__=='__main__': unittest.main()
