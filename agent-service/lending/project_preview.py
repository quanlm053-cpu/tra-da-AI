"""Serve the latest merged build of a project behind a stable local URL."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import preview


def main(config):
    preview.REPO = Path(config['repo_path'])
    preview.RUNTIME = Path(config['runtime_path'])
    preview.RELEASES = preview.RUNTIME / 'preview-releases'
    preview.RELEASES.mkdir(exist_ok=True)
    port = config['preview_port']
    backend = port + 2000
    state = {'revision':''}
    class Proxy(BaseHTTPRequestHandler):
        def forward(self):
            if self.path=='/__preview_version':
                body=json.dumps(state).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            connection=http.client.HTTPConnection('127.0.0.1',backend,timeout=30)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<=size<=8_000_000:
                    return self.send_error(413)
                headers={key:value for key,value in self.headers.items() if key.lower()!='accept-encoding'}
                headers['Accept-Encoding']='identity'
                connection.request(self.command,self.path,self.rfile.read(size) if size else None,headers)
                response=connection.getresponse()
                body=response.read()
                if 'text/html' in response.getheader('Content-Type','') and not response.getheader('Content-Encoding'):
                    script=('<script>setInterval(async()=>{try{let r=await fetch("/__preview_version",{cache:"no-store"});'
                            'if(r.ok&&(await r.json()).revision!=='+json.dumps(state['revision'])+
                            ')location.reload()}catch{}},10000)</script>')
                    body=body.replace(b'</body>',script.encode()+b'</body>')
                self.send_response(response.status)
                for key,value in response.getheaders():
                    if key.lower() not in ('transfer-encoding','content-length','connection','cache-control'):
                        self.send_header(key,value)
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (OSError,ValueError):
                self.send_error(503,'Project preview is waiting for a runnable build.')
            finally:
                connection.close()
        do_GET=forward
        do_POST=forward
        do_PUT=forward
        do_PATCH=forward
        do_DELETE=forward
    server=ThreadingHTTPServer(('127.0.0.1',port),Proxy)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    process=None
    current=None
    def launch(release,revision):
        env={**os.environ,'PORT':str(backend),'APP_ORIGIN':config['preview_url'].rstrip('/'),
             'PREVIEW_REVISION':revision,
             'NODE_ENV':'development','AI_ENV':'demo','SQLSERVER_DRIVER':'odbc',
             'DATABASE_URL':'Driver={ODBC Driver 17 for SQL Server};Server=lpc:localhost;'
                            f'Database={config["preview_database"]};Trusted_Connection=yes;'
                            'Encrypt=yes;TrustServerCertificate=yes;'}
        with (preview.RUNTIME/'preview-app.log').open('ab') as log:
            child=subprocess.Popen([shutil.which('npm.cmd') or shutil.which('npm'),'run','preview'],
                                   cwd=release,env=env,stdout=log,stderr=log)
        deadline=time.monotonic()+45
        while child.poll() is None and time.monotonic()<deadline:
            connection=http.client.HTTPConnection('127.0.0.1',backend,timeout=2)
            try:
                connection.request('GET','/',headers={'Host':f'localhost:{port}'})
                response=connection.getresponse()
                response.read()
                if response.status==200:
                    return child
            except OSError:
                pass
            finally:
                connection.close()
            time.sleep(.5)
        terminate(child)
        raise RuntimeError('npm run preview chưa phục vụ HTTP thành công.')
    try:
        while True:
            try:
                preview.command(['git','fetch','origin','main'],preview.REPO)
                revision=preview.command(['git','rev-parse','origin/main'],preview.REPO)
                if revision!=state['revision'] or process is None or process.poll() is not None:
                    files=preview.command(['git','ls-tree','--name-only',revision],preview.REPO).splitlines()
                    if 'package-lock.json' not in files:
                        time.sleep(30)
                        continue
                    release=preview.prepare(revision)
                    package=json.loads((release/'package.json').read_text(encoding='utf-8'))
                    if not package.get('scripts',{}).get('preview'):
                        raise RuntimeError('Dự án chưa có npm script preview.')
                    terminate(process)
                    try:
                        process=launch(release,revision)
                    except Exception:
                        if current:
                            process=launch(current,state['revision'])
                        raise
                    current=release
                    state['revision']=revision
                    print('Project preview updated: '+revision,flush=True)
            except Exception as exc:
                print('Project preview: '+str(exc),flush=True)
            time.sleep(30)
    finally:
        terminate(process)
        server.shutdown()
        server.server_close()


def terminate(process):
    if process:
        from controller import Service
        Service.terminate(None,process)


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    main(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
