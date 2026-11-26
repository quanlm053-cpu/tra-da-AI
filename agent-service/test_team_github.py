import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import team_commands
import github_bridge

class TeamTests(unittest.TestCase):
    def test_intent_requires_command(self):
        self.assertTrue(team_commands.team_start('Tất cả làm task cha 44'))
        self.assertTrue(team_commands.team_start('Cả đội tiếp tục Story #44'))
        self.assertFalse(team_commands.team_start('Cả đội đang làm gì?'))
        self.assertFalse(team_commands.team_start('Tất cả làm xong chưa?'))
        self.assertFalse(team_commands.team_start('Backend làm task 49'))
    def service(self,state='attention',status=2):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        db.execute('CREATE TABLE jobs(id INTEGER,state TEXT,data TEXT)')
        db.execute('INSERT INTO jobs VALUES(44,?,?)',(state,json.dumps({'id':44,'stage':'frontend','calls':6,'rounds':0,'error':'timed out'})))
        writes=[]
        def save(job,state='active'):
            db.execute('UPDATE jobs SET state=?,data=? WHERE id=?',(state,json.dumps(job),job['id']));db.commit()
        api=SimpleNamespace(issue=lambda i:{'id':i,'project':{'id':1},'tracker':{'id':4},'status':{'id':status}},update=lambda *a,**kw:writes.append(kw))
        return SimpleNamespace(db=db,api=api,save=save,story=lambda j:None,config={'project_id':1,'trackers':{'story':4},'max_agent_calls_per_story':15,'max_repair_rounds':2},s={'done':15,'blocked':9,'backlog':7,'selected':8}),writes
    def test_resume_and_deduplicate(self):
        s,w=self.service()
        team_commands.start(s,44,'Cả đội làm Story 44')
        self.assertEqual(s.db.execute('SELECT state FROM jobs').fetchone()[0],'active')
        team_commands.start(s,44,'Cả đội làm Story 44')
        self.assertEqual(len(w),1)
    def test_blocked_story_cannot_start(self):
        s,w=self.service(status=9)
        with self.assertRaises(ValueError):team_commands.start(s,44,'Cả đội làm Story 44')
        self.assertEqual(w,[])
    def test_team_question_does_not_resume(self):
        s,w=self.service()
        team_commands.start(s,44,'Tiến độ cả đội đến đâu?')
        self.assertEqual(s.db.execute('SELECT state FROM jobs').fetchone()[0],'attention')
        self.assertEqual(w,[])

class GitHubTests(unittest.TestCase):
    def test_qa_added_tests_return_to_review_before_done(self):
        from controller import Service,ROOT
        service=Service.__new__(Service)
        service.config=json.loads((ROOT/'config.json').read_text())
        service.s=service.config['statuses'];service.story=lambda j:None
        service.checkout=lambda j:Path('.')
        service.code_fingerprint=lambda p:'new-tests'
        touched=[];service.child_status=lambda j,r,status:touched.append(status)
        service.agent=lambda j,r:{'outcome':'passed','checks':[{'result':'passed'}]}
        def transition(job,status,stage,note):job['stage']=stage
        service.transition=transition
        job={'id':44,'stage':'qa','reviewed_code':'old'}
        service.step(job)
        self.assertEqual(job['stage'],'reviewer')
        self.assertNotIn(service.s['done'],touched)
    def test_ci_failure_routes_back_to_dev(self):
        from controller import Service
        service=Service.__new__(Service)
        service.story=lambda j:None
        service.save=lambda *a,**kw:None
        calls=[]
        service.repair=lambda job,result:calls.append(result)
        job={'id':44,'stage':'ci','github':{}}
        with patch.object(github_bridge,'checks',return_value=('failed',['Render failed'])):
            service.step(job)
        self.assertEqual(calls[0]['outcome'],'needs_changes')
        self.assertIn('Render failed',calls[0]['bugs'][0]['description'])
    def test_ci_pending_does_not_mark_done(self):
        from controller import Service
        service=Service.__new__(Service);service.story=lambda j:None;service.save=lambda *a,**kw:None
        job={'id':44,'stage':'ci','github':{}}
        with patch.object(github_bridge,'checks',return_value=('pending',[])):service.step(job)
        self.assertEqual(job['stage'],'ci')
    def test_secret_files_are_blocked_before_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(github_bridge,'git',side_effect=['.env','']):
                with self.assertRaises(github_bridge.GitHubError):github_bridge.safe_files(folder)
    def test_only_changed_source_is_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'page.tsx').write_text('export default 1')
            with patch.object(github_bridge,'git',side_effect=['page.tsx','test-results/desktop.png']):
                self.assertEqual(github_bridge.safe_files(folder),['page.tsx'])
    def test_missing_login_returns_actionable_error(self):
        with patch.object(github_bridge.subprocess,'run',return_value=SimpleNamespace(stdout='')):
            with self.assertRaisesRegex(github_bridge.GitHubError,'github login'):github_bridge.token()

if __name__=='__main__':unittest.main()
