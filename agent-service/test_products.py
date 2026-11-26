import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock
from controller import Service, Hold


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'requirements.md').write_text('Real deliverable',encoding='utf-8')
        self.service = Service.__new__(Service)
        self.service.checkout = lambda job:self.root
        self.service.api = Mock()
        self.service.api.request.return_value = {'upload':{'token':'server-token'}}
        self.job = {'id':44}
        self.child = {'id':45,'subject':'Requirements','attachments':[]}
        self.report = {'issue_id':45,'evidence':'Document ready','artifacts':['requirements.md']}

    def test_upload_contains_actual_deliverable_and_manifest(self):
        tokens = self.service.product_uploads(self.job,'ba',self.report,{},self.child)
        self.assertEqual(len(tokens),2)
        call = self.service.api.request.call_args_list[0]
        self.assertTrue(call.kwargs['binary'])
        with zipfile.ZipFile(io.BytesIO(call.args[2])) as z:
            self.assertEqual(z.read('source/requirements.md'),b'Real deliverable')
            self.assertIn('PRODUCT.json',z.namelist())

    def test_upload_is_idempotent_for_same_content(self):
        tokens = self.service.product_uploads(self.job,'ba',self.report,{},self.child)
        self.child['attachments'] = [{'filename':tokens[0]['filename']}]
        self.service.api.reset_mock()
        self.assertEqual(self.service.product_uploads(self.job,'ba',self.report,{},self.child),[])
        self.service.api.request.assert_not_called()

    def test_missing_artifacts_never_uploads(self):
        self.report['artifacts'] = []
        with self.assertRaises(Hold):
            self.service.product_uploads(self.job,'ba',self.report,{},self.child)
        self.service.api.request.assert_not_called()

    def test_secret_or_path_escape_never_uploads(self):
        (self.root/'.env').write_text('PASSWORD=private')
        for path in ['.env','../outside.txt']:
            self.report['artifacts']=[path]
            with self.assertRaises(Hold):
                self.service.product_uploads(self.job,'ba',self.report,{},self.child)
        self.service.api.request.assert_not_called()

    def test_upload_failure_prevents_progress_update(self):
        s=self.service
        s.s={'done':15,'in_review':14,'blocked':9}
        s.story=Mock()
        s.api.issue.return_value=dict(self.child,parent={'id':44},status={'id':14},done_ratio=0)
        s.api.request.side_effect=Hold('Upload unavailable')
        with self.assertRaises(Hold):
            s.completed_tasks(self.job,'ba',{'task_plan':[{'issue_id':45,'role':'ba'}],'completed_tasks':[self.report]})
        s.api.update.assert_not_called()


if __name__=='__main__':
    unittest.main()
