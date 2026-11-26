"""Controller-owned GitHub branch/PR publishing; credentials stay in GCM memory."""
import json
import os
import re
import time
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

class GitHubError(Exception):pass

def git(repo,*args):
    p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',
        timeout=120,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'})
    if p.returncode:raise GitHubError('Git không thực hiện được '+args[0]+'. Kiểm tra quyền GitHub hoặc thay đổi nhánh.')
    return p.stdout.strip()

def token():
    p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,
        timeout=20,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'})
    fields=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)
    if not fields.get('password'):
        raise GitHubError('Chưa đăng nhập GitHub. Chạy: git credential-manager github login --username quanlm053-cpu --device')
    return fields['password']

class GitHub:
    def __init__(self,repo):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):raise GitHubError('Tên repository không hợp lệ.')
        self.repo=repo
        self._token=token()
    def request(self,path,method='GET',body=None):
        req=urllib.request.Request('https://api.github.com/repos/'+self.repo+path,method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json','User-Agent':'TicketLab-office','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
        except urllib.error.HTTPError as exc:raise GitHubError('GitHub HTTP '+str(exc.code)+'; kiểm tra quyền repo và nhánh.') from None

def safe_files(repo):
    paths=set(git(repo,'diff','HEAD','--name-only').splitlines()+git(repo,'ls-files','--others','--exclude-standard').splitlines())
    allowed=[]
    for name in sorted(paths):
        path=Path(name)
        if name.endswith('.tsbuildinfo') or name=='next-env.d.ts':continue
        if path.is_absolute() or '..' in path.parts:raise GitHubError('Đường dẫn ngoài checkout.')
        if any(p in ('node_modules','.next','runtime','test-results','playwright-report') for p in path.parts):continue
        if any(p.startswith('.env') and p not in ('.env.example','.env.sample') for p in path.parts) or path.suffix.lower() in ('.key','.pem','.pfx','.sqlite','.db','.bak'):
            raise GitHubError('Không publish tệp nhạy cảm: '+name)
        full=Path(repo)/name
        if not full.resolve().is_relative_to(Path(repo).resolve()):raise GitHubError('Không publish symlink trỏ ngoài checkout.')
        if full.is_file():
            if full.stat().st_size>10_000_000:raise GitHubError('Tệp quá lớn: '+name)
            if full.suffix.lower() in ('.js','.ts','.tsx','.json','.md','.txt','.yml','.yaml','.sql'):
                text=full.read_text(encoding='utf-8',errors='replace')
                if re.search(r'gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-proj-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',text):
                    raise GitHubError('Phát hiện chuỗi thông tin xác thực trong '+name)
        allowed.append(name)
    return allowed

def publish(service,job):
    cfg=service.config.get('github',{})
    if not cfg.get('enabled'):return None
    repo=service.checkout(job)
    remote=git(repo,'remote','get-url','origin')
    expected='https://github.com/'+cfg['repository']
    if remote.removesuffix('.git')!=expected:raise GitHubError('Origin không khớp repository được cấu hình.')
    branch='ai/story-'+str(job['id'])
    if git(repo,'branch','--show-current')!=branch:raise GitHubError('Chỉ publish nhánh AI của Story, không push main.')
    gh=GitHub(cfg['repository'])
    if not gh.request('').get('permissions',{}).get('push'):raise GitHubError('Tài khoản GitHub chưa có quyền push repository.')
    files=safe_files(repo)
    if git(repo,'diff','--cached','--name-only'):raise GitHubError('Checkout có thay đổi đang stage từ bên ngoài; cần kiểm tra trước khi publish.')
    if files:
        git(repo,'add','--',*files)
        git(repo,'-c','user.name=TicketLab AI','-c','user.email=ticketlab-ai@localhost','commit','-m',f'Story #{job["id"]}: reviewed changes and test evidence')
    sha=git(repo,'rev-parse','HEAD')
    git(repo,'push','--set-upstream','origin','HEAD:refs/heads/'+branch)
    owner=cfg['repository'].split('/')[0]
    prs=gh.request('/pulls?'+urllib.parse.urlencode({'state':'open','head':owner+':'+branch}))
    if prs:pr=prs[0]
    else:
        pr=gh.request('/pulls','POST',{'title':f'Story #{job["id"]}: {service.api.issue(job["id"])["subject"]}',
            'head':branch,'base':cfg.get('base_branch','main'),'draft':True,
            'body':f'Implements Redmine Story #{job["id"]}.\n\nCode review and local QA evidence are stored in docs/ai/story-{job["id"]}/ and task attachments.\n\nCI runs a frontend render smoke test and backend unit tests. Database acceptance testing remains separate. Human PM acceptance and merge are required.'})
    job['github']={'url':pr['html_url'],'number':pr['number'],'sha':sha,'branch':branch,'checks':'pending','started':time.time()}
    service.save(job)
    service.api.update(job['id'],notes='[AI:github] Đã đẩy nhánh và tạo/cập nhật draft PR: '+pr['html_url']+'\nCI sẽ build, render giao diện, lưu ảnh và kiểm tra lỗi. Chưa merge.')
    return pr['html_url']

def checks(service,job):
    cfg=service.config['github'];published=job['github'];gh=GitHub(cfg['repository'])
    pr=gh.request('/pulls/'+str(published['number']))
    if pr['head']['sha']!=published['sha']:raise GitHubError('PR đã đổi HEAD ngoài dịch vụ; cần review lại.')
    runs=gh.request('/commits/'+published['sha']+'/check-runs').get('check_runs',[])
    expected=[r for r in runs if r['name']=='ticketlab-ai-validation']
    if not expected or any(r['status']!='completed' for r in expected):
        if time.time()-published.get('started',time.time())>1800:raise GitHubError('CI chưa hoàn tất sau 30 phút; kiểm tra GitHub Actions và quyền workflow.')
        return 'pending',[]
    if any(r['conclusion'] in ('cancelled','timed_out','action_required','stale') for r in expected):
        raise GitHubError('CI bị hủy/quá giờ hoặc cần quyền chạy; chưa có kết luận lỗi sản phẩm.')
    failures=[r for r in expected if r['conclusion'] not in ('success','skipped')]
    if failures:
        details=[]
        for r in failures:
            output=r.get('output') or {}
            annotations=gh.request('/check-runs/'+str(r['id'])+'/annotations')
            details.append(r['name']+' '+str(r['conclusion'])+' '+str(r.get('html_url',''))+'\n'+str(output.get('summary',''))[:4000]+'\n'+'\n'.join(str(a.get('message',''))[:1000] for a in annotations[:10]))
        return 'failed',details
    return 'passed',[]
