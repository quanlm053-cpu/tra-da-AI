import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
import parallel_team

class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.repo=root/'source';self.repo.mkdir();self.runtime=root/'runtime';self.runtime.mkdir()
        def git(*args):
            subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
        git('init');git('config','user.name','test');git('config','user.email','test@localhost')
        for name in ('app/page.tsx','backend/api.js'):
            p=self.repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('baseline')
        git('add','.');git('commit','-m','baseline')
        self.service=SimpleNamespace(repo=self.repo,runtime=self.runtime,config={'max_agent_calls_per_story':30},
            checkout=lambda j:self.repo,save=lambda *a,**kw:None,story=lambda j:None,
            api=SimpleNamespace(update=lambda *a,**kw:None),completed_tasks=lambda *a:None)
        self.job={'id':44,'stage':'parallel','calls':0,'plan':[]}
    def test_real_concurrency_and_isolated_merge(self):
        barrier=threading.Barrier(2)
        def run(role,lane):
            barrier.wait(timeout=8)
            name='backend/api.js' if role=='backend' else 'app/page.tsx'
            (lane/name).write_text(role)
            return {'outcome':'passed','summary':role,'completed_tasks':[]}
        parallel_team.run_wave(self.service,self.job,roles=('backend','frontend'),invoke=run)
        self.assertEqual((self.repo/'backend/api.js').read_text(),'backend')
        self.assertEqual((self.repo/'app/page.tsx').read_text(),'frontend')
        self.assertEqual(self.job['calls'],2)
        self.assertEqual(self.job['running_roles'],[])
    def test_wrong_owner_never_overwrites_main(self):
        base=parallel_team.files(self.repo)
        lane=parallel_team.prepare_lane(self.service,self.job,'frontend','scope-test',base)
        (lane/'backend/api.js').write_text('wrong owner')
        with self.assertRaises(parallel_team.ParallelError):
            parallel_team.promote(self.repo,base,{'frontend':lane},self.job)
        self.assertEqual((self.repo/'backend/api.js').read_text(),'baseline')
    def test_external_main_edit_is_preserved(self):
        base=parallel_team.files(self.repo)
        lane=parallel_team.prepare_lane(self.service,self.job,'backend','conflict-test',base)
        (lane/'backend/api.js').write_text('agent')
        (self.repo/'backend/api.js').write_text('human edit')
        with self.assertRaises(parallel_team.ParallelError):parallel_team.promote(self.repo,base,{'backend':lane},self.job)
        self.assertEqual((self.repo/'backend/api.js').read_text(),'human edit')
    def test_qa_preparation_cannot_modify_product_code(self):
        self.assertTrue(parallel_team.allowed('docs/ai/story-44/parallel/qa.md','qa',self.job))
        self.assertFalse(parallel_team.allowed('app/page.tsx','qa',self.job))
    def test_frontend_owns_scoped_typescript_config(self):
        self.assertTrue(parallel_team.allowed('tsconfig.booking.json','frontend',self.job))
        self.assertFalse(parallel_team.allowed('tsconfig.booking.json','backend',self.job))

if __name__=='__main__':unittest.main()
