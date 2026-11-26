import sqlite3
import unittest
import json
from types import SimpleNamespace
import chat_queue

class ChatQueueTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE jobs(id INTEGER,state TEXT,data TEXT)')
        self.db.execute('INSERT INTO jobs VALUES(44,?,?)',('attention',json.dumps({'id':44,'stage':'frontend'})))
        self.body=dict(story_id=44,role='ba',message='Tiến độ đến đâu?',request_id='request-0001')
    def tearDown(self):self.db.close()
    def test_idempotent_retry(self):
        a=chat_queue.enqueue(self.db,self.body)
        self.assertEqual(a,chat_queue.enqueue(self.db,self.body))
        self.assertEqual(len(chat_queue.messages(self.db,44)),1)
        with self.assertRaises(ValueError):chat_queue.enqueue(self.db,{**self.body,'message':'Different'})
    def test_invalid_scope(self):
        for change in ({'role':'pm'},{'story_id':99},{'message':''},{'message':'x'*6001}):
            with self.assertRaises(ValueError):chat_queue.enqueue(self.db,{**self.body,**change})
    def test_controller_consumes_and_preserves_job_state(self):
        chat_queue.enqueue(self.db,self.body)
        calls=[]
        def agent(job,role,chat):
            calls.append((role,chat['job_state']))
            return {'summary':'Đã đọc tài liệu.','outcome':'passed'}
        service=SimpleNamespace(db=self.db,agent=agent)
        self.assertTrue(chat_queue.process_one(service))
        self.assertFalse(chat_queue.process_one(service))
        self.assertEqual(calls,[('ba','attention')])
        self.assertEqual(chat_queue.messages(self.db,44)[0]['state'],'done')
        self.assertEqual(self.db.execute('SELECT state FROM jobs').fetchone()[0],'attention')
    def test_agent_failure_is_recorded_not_replayed(self):
        chat_queue.enqueue(self.db,self.body)
        def agent(*args,**kw):raise ValueError('Missing input')
        service=SimpleNamespace(db=self.db,agent=agent)
        chat_queue.process_one(service)
        self.assertEqual(chat_queue.messages(self.db,44)[0]['state'],'failed')
        self.assertFalse(chat_queue.process_one(service))

if __name__=='__main__':unittest.main()
