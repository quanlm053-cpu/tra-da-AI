"""Non-public frontend preview. Never stops an existing listener."""
import json
import os
import shutil
import socket
import subprocess

def prepare(service,job):
    repo=service.checkout(job)
    for source,target in [('ai-ui-smoke.mjs','scripts/ai-ui-smoke.mjs'),('ticketlab-ai.yml','.github/workflows/ticketlab-ai.yml')]:
        destination=repo/target
        if not destination.exists():
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(service.runtime.parent/'templates'/source,destination)
    package=json.loads((repo/'package.json').read_text(encoding='utf-8'))
    if 'playwright' not in {**package.get('dependencies',{}),**package.get('devDependencies',{})}:
        npm=service.runtime.parent/'tools/npm/bin/npm-cli.js'
        if not npm.exists():return False
        proc=subprocess.run([shutil.which('node'),str(npm),'install','--save-dev','playwright','--ignore-scripts'],cwd=repo,
            capture_output=True,timeout=240)
        if proc.returncode:return False
    ignore=repo/'.gitignore'
    text=ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    if '\ntest-results/' not in text:ignore.write_text(text+'\ntest-results/\nplaywright-report/\n',encoding='utf-8')
    return True

def ensure(service,job):
    metadata=service.runtime/'preview.json'
    with socket.socket() as sock:occupied=sock.connect_ex(('127.0.0.1',3101))==0
    if occupied:
        if metadata.exists() and json.loads(metadata.read_text()).get('story_id')==job['id']:
            return 'http://localhost:3101'
        return None
    repo=service.checkout(job)
    next_script=repo/'node_modules/next/dist/bin/next'
    node=shutil.which('node')
    if not node or not next_script.exists():return None
    env={**os.environ,'NODE_ENV':'development','NEXT_PUBLIC_API_URL':'http://localhost:5101/api','NEXT_TELEMETRY_DISABLED':'1'}
    with (service.runtime/'preview.log').open('ab') as logs:
        proc=subprocess.Popen([node,str(next_script),'dev','--hostname','127.0.0.1','-p','3101'],cwd=repo,
            env=env,stdin=subprocess.DEVNULL,stdout=logs,stderr=logs,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    metadata.write_text(json.dumps({'story_id':job['id'],'pid':proc.pid,'url':'http://localhost:3101'}))
    return 'http://localhost:3101'
