"""Local office data and protected chat inbox. Never returns credentials or raw tool output."""
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from controller import ROOT, Service
import chat_queue

cache = {'at':0,'value':None}
cache_lock = threading.Lock()


def snapshot():
    with cache_lock:
        if cache['value'] and time.time()-cache['at'] < 8:
            return cache['value']
        service = Service()
        try:
            rows = service.db.execute('SELECT id,state,data FROM jobs ORDER BY id DESC').fetchall()
            jobs = []
            for issue_id,state,raw in rows[:10]:
                job = json.loads(raw)
                view = {k:job.get(k) for k in ('id','stage','calls','rounds','error','running_role','running_roles','parallel_tasks','parallel_results','started_at','preview_url','github')}
                view['state'] = state
                view['results'] = {role:{'outcome':result.get('outcome'),'summary':result.get('summary'),
                    'checks':result.get('checks',[]),'completed_tasks':result.get('completed_tasks',[])}
                    for role,result in job.get('results',{}).items()}
                view['plan'] = job.get('plan',[])
                view['tasks'] = []
                view['timeline'] = []
                try:
                    issue = service.api.issue(issue_id)
                    view['subject'] = issue['subject']
                    view['story_status'] = issue['status']['name']
                    view['story_progress'] = issue.get('done_ratio',0)
                    query = f'/issues.json?parent_id={issue_id}&status_id=*&include=attachments&limit=100'
                    children = sorted(service.api.request('GET',query)['issues'],key=lambda x:x['id'])
                    for child in children:
                        view['tasks'].append({'id':child['id'],'subject':child['subject'],
                            'status':child['status']['name'],'progress':child.get('done_ratio',0),
                            'attachments':[{'filename':a['filename'],'id':a['id']} for a in child.get('attachments',[])]})
                    view['timeline'] = [{'id':j['id'],'at':j['created_on'],'text':j.get('notes','')}
                        for j in issue.get('journals',[]) if j.get('notes','').startswith('[AI')][-20:]
                except Exception as exc:
                    view['redmine_error'] = type(exc).__name__
                reports = ROOT/'runtime/reports'/str(issue_id)
                files = sorted(reports.glob('*.jsonl')) if reports.exists() else []
                view['activity'] = []
                if files and (state != 'active' or job['stage'] not in ('ba','backend','frontend','reviewer','qa') or files[-1].stem.endswith('-'+job['stage'])):
                    with files[-1].open('rb') as stream:
                        stream.seek(max(0,files[-1].stat().st_size-100_000))
                        lines = stream.read().decode('utf-8',errors='replace').splitlines()
                    for line in lines:
                        try:
                            event = json.loads(line)
                            item = event.get('item',{})
                            if item.get('type') == 'agent_message':
                                message = item.get('text','')
                                if message.lstrip().startswith('{'):
                                    continue
                                view['activity'].append(message[:1600])
                        except (ValueError,TypeError):
                            pass
                    view['activity'] = view['activity'][-5:]
                jobs.append(view)
            heartbeat = ROOT/'runtime/heartbeat'
            age = time.time()-float(heartbeat.read_text()) if heartbeat.exists() else None
            value = {'jobs':jobs,'service_alive':age is not None and age < 120,
                     'heartbeat_age':int(age) if age is not None else None,'time':time.time()}
            cache.update(at=time.time(),value=value)
            return value
        finally:
            service.db.close()


class Handler(BaseHTTPRequestHandler):
    def json_response(self, body, status=200):
        data=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)

    def do_POST(self):
        if urlsplit(self.path).path=='/api/test-fixture':
            if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1'):
                self.send_error(403);return
            import test_bridge
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Invalid body')
                result=test_bridge.execute(ROOT,json.loads(self.rfile.read(length)),self.headers.get('X-TicketLab-Test-Key',''))
                self.json_response(result)
            except PermissionError:self.json_response({'error':'Test capability required'},403)
            except (ValueError,TypeError):self.json_response({'error':'Invalid fixture operation'},400)
            except Exception:self.json_response({'error':'Test environment operation unavailable'},503)
            return
        if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1') or urlsplit(self.path).path!='/api/chat':
            self.send_error(403);return
        # Only the local office can submit executable instructions; reject cross-site forms.
        if self.headers.get('Origin') not in ('http://localhost:8766','http://127.0.0.1:8766','http://localhost:8765','http://127.0.0.1:8765'):
            self.send_error(403);return
        service=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=30000 or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                raise ValueError('Nội dung không hợp lệ.')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('Nội dung không hợp lệ.')
            service=Service()
            chat_id=chat_queue.enqueue(service.db,body)
            self.json_response({'id':chat_id,'state':'queued'},202)
        except (ValueError,TypeError):
            self.json_response({'error':'Story, agent hoặc nội dung không hợp lệ; kiểm tra hàng chờ.'},400)
        except Exception:
            self.json_response({'error':'Không thể lưu lệnh. Vui lòng thử lại.'},503)
        finally:
            if service:service.db.close()
    def log_message(self,*args):
        pass

    def do_GET(self):
        if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'):
            self.send_error(403); return
        path = urlsplit(self.path).path
        if path == '/api/chat':
            service=None
            try:
                story=int(parse_qs(urlsplit(self.path).query).get('story_id',['0'])[0])
                service=Service()
                self.json_response({'messages':chat_queue.messages(service.db,story)})
            except Exception:
                self.json_response({'error':'Không lấy được hội thoại.'},503)
            finally:
                if service:service.db.close()
            return
        elif path == '/api/state':
            try:
                data = json.dumps(snapshot(),ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            except Exception:
                self.send_error(503,'Service snapshot unavailable'); return
        elif path in ('/','/index.html'):
            data = (ROOT/'dashboard.html').read_bytes()
            mime = 'text/html; charset=utf-8'
        else:
            self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Type',mime)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    (ROOT/'runtime/dashboard.pid').write_text(str(os.getpid()))
    print('Demo console: http://localhost:8765',flush=True)
    server.serve_forever()
