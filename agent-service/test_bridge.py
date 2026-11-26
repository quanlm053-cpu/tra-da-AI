"""Narrow controller-owned fixture operations, never arbitrary SQL or production DB."""
import hmac
import json
import os
import secrets
import shutil
import subprocess
import urllib.request
from pathlib import Path

ACTIONS={'status','create','snapshot','set-stock','set-price','rollback-on','rollback-off','cleanup'}

def credentials(root):
    p=Path(root)/'runtime/test-bridge-key'
    if not p.exists():p.write_text(secrets.token_urlsafe(32))
    return p.read_text().strip()

def execute(root,body,key):
    root=Path(root).resolve()
    if not hmac.compare_digest(key or '',credentials(root)):raise PermissionError('Invalid test capability')
    if not isinstance(body,dict) or body.get('action') not in ACTIONS:raise ValueError('Unsupported fixture action')
    env={**os.environ,**json.loads((root/'runtime/test-environment.json').read_text())}
    if env.get('DB_NAME')!='TicketLab_AI_Test':raise ValueError('Test database guard failed')
    proc=subprocess.run([shutil.which('node'),str(root/'test_db_bridge.cjs')],input=json.dumps(body),
        text=True,encoding='utf-8',capture_output=True,timeout=40,env=env,cwd=root)
    if proc.returncode:raise RuntimeError('Test fixture operation failed; '+proc.stderr.strip()[:180])
    result=json.loads(proc.stdout)
    if body['action']=='status':
        result['servers']={}
        for name,url in [('frontend','http://localhost:3101/'),('backend','http://localhost:5101/api/events')]:
            try:
                with urllib.request.urlopen(url,timeout=15) as response:result['servers'][name]=response.status
            except Exception:result['servers'][name]=None
    return result
