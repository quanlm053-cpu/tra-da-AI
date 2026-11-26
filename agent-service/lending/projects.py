"""Create isolated projects and keep their resumable workers addressable."""
import hashlib
import json
import re
import subprocess
import shutil
import sys
import socket
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from github_bridge import token, git


def github(path, method='GET', body=None):
    request = Request('https://api.github.com'+path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+token(), 'Accept':'application/vnd.github+json',
                 'Content-Type':'application/json', 'User-Agent':'AI-office'})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        if method=='GET' and exc.code==404:
            return None
        raise RuntimeError(f'GitHub từ chối thao tác {method} {path}, HTTP {exc.code}.') from None


def ordered_plan(plans):
    if not 1 <= len(plans) <= 30:
        raise ValueError('Kế hoạch dự án cần từ 1 đến 30 Story.')
    pending = set(range(len(plans)))
    if len({plan['title'].strip() for plan in plans})!=len(plans):
        raise ValueError('Tên các Story trong kế hoạch phải phân biệt.')
    ordered = []
    while pending:
        ready = [index for index in sorted(pending)
                 if all(dep in ordered for dep in plans[index].get('depends_on', []))]
        if not ready:
            raise ValueError('Kế hoạch có phụ thuộc vòng hoặc chỉ số Story không hợp lệ.')
        for index in ready:
            if not plans[index]['title'].strip() or not plans[index]['acceptance'].strip():
                raise ValueError('Mỗi Story cần tên và tiêu chí nghiệm thu.')
            ordered.append(index)
            pending.remove(index)
    return ordered


class ProjectManager:
    def __init__(self, default):
        self.lock = threading.RLock()
        self.setup_lock = threading.Lock()
        self.registry = default.runtime / 'projects.json'
        self.offices = {default.project_config['identifier']:default}
        self.configs = {default.project_config['identifier']:default.project_config}
        self.active = default.project_config['identifier']
        default.manager = self
        if self.registry.exists():
            saved = json.loads(self.registry.read_text(encoding='utf-8'))
            self.configs.update(saved['projects'])
            self.active = saved.get('active', self.active)
        self.sequence = max(
            [row['id'] for worker in self.offices.values() for row in worker.data['chat']] + [0])
        for config in self.configs.values():
            state=Path(config['runtime_path'])/'state.json'
            if state.exists():
                data=json.loads(state.read_text(encoding='utf-8'))
                self.sequence=max(self.sequence,max([row['id'] for row in data['chat']]+[0]))
        self.default = default

    def save(self):
        with self.lock:
            temporary = self.registry.with_suffix('.tmp')
            temporary.write_text(json.dumps({'active':self.active,'projects':self.configs},
                                           ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(self.registry)

    def next_id(self):
        with self.lock:
            self.sequence+=1
            return self.sequence

    def mirror_result(self,source,row):
        if self.active==source.project_config['identifier']:
            return
        target=self.office()
        with target.lock:
            if not any(item['id']==row['id'] for item in target.data['chat']):
                target.data['chat'].append(dict(row))
                target.save()

    def office(self, identifier=None):
        from office import Office
        with self.lock:
            if identifier is not None and not isinstance(identifier,str):
                raise ValueError('Identifier dự án phải là chuỗi.')
            identifier = identifier or self.active
            if identifier not in self.configs:
                raise ValueError('Không tìm thấy dự án.')
            if identifier not in self.offices:
                worker = Office(self.configs[identifier])
                worker.manager = self
                self.offices[identifier] = worker
                self.start_preview(worker.project_config)
            self.start_worker(self.offices[identifier])
            return self.offices[identifier]

    def start_worker(self,worker):
        with self.lock:
            thread=getattr(worker,'worker_thread',None)
            if thread is None or not thread.is_alive():
                worker.worker_thread=threading.Thread(target=worker.run,daemon=True)
                worker.worker_thread.start()

    def select(self, identifier):
        if not isinstance(identifier,str) or identifier not in self.configs:
            raise ValueError('Cần chọn identifier của dự án đã có.')
        worker = self.office(identifier)
        with self.lock:
            self.active = identifier
            self.save()
        return worker

    def listing(self):
        with self.lock:
            return [dict(identifier=key, name=value['name'], repository=value['repository'],
                         redmine_project_id=value['redmine_project_id'],active=key==self.active)
                    for key,value in self.configs.items()]

    def start_preview(self,config):
        if not config.get('preview_port'):
            return
        runtime=Path(config['runtime_path'])
        with (runtime/'preview-supervisor.log').open('ab') as log:
            try:
                subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('project_preview.py')),
                                  str(runtime/'project.json')],stdout=log,stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            except OSError:
                print('Chưa khởi động được preview cho '+config['identifier'],flush=True)

    def create(self, source, row, result):
        with self.setup_lock:
            return self._create(source, row, result)

    def _create(self, source, row, result):
        from office import Office, HERE
        action = result['action']
        slug = action['repo_slug']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,59}',slug):
            raise ValueError('Tên repo cần 3–60 ký tự chữ thường, số hoặc dấu gạch ngang.')
        if action['visibility'] not in ('private','public'):
            raise ValueError('Cần xác định public hoặc private cho repo mới.')
        order = ordered_plan(result['stories'])
        name, brief = action['title'].strip(), action['description'].strip()
        if not name or not brief:
            raise ValueError('Cần tên và đề bài cụ thể của dự án mới.')
        directory = HERE.parent / 'runtime/projects' / slug
        directory.mkdir(parents=True, exist_ok=True)
        receipt_path = directory / 'bootstrap.json'
        signature = hashlib.sha256((name+'\n'+brief).encode()).hexdigest()
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt.get('complete') and slug in self.configs:
                config = self.configs[slug]
                self.select(slug)
                return f'Dự án đã được khởi tạo: {config["name"]}. GitHub: https://github.com/{config["repository"]}'
            name = receipt.get('name',name)
            brief = receipt.get('brief',brief)
            plans = receipt['plans']
            order = ordered_plan(plans)
        else:
            if slug in self.configs:
                raise ValueError('Dự án này đã tồn tại. Hãy chuyển sang dự án đó.')
            plans = result['stories']
            receipt = dict(signature=signature,plans=plans,story_ids={},name=name,brief=brief)
        def checkpoint():
            temp = receipt_path.with_suffix('.tmp')
            temp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(receipt_path)
        checkpoint()
        account = github('/user')['login']
        repository = account+'/'+slug
        marker = '[AI Office project: '+slug+']'
        remote = github('/repos/'+repository)
        if remote:
            if marker not in (remote.get('description') or ''):
                raise ValueError('Repo cùng tên đã có sẵn và chưa thuộc dự án này. Hãy chọn tên khác.')
        else:
            remote = github('/user/repos','POST',dict(
                name=slug,description=(brief[:180]+' '+marker),private=action['visibility']=='private',
                auto_init=False))
        receipt['repository'] = repository
        checkpoint()
        api = source.api
        try:
            project = api.request('GET',f'/projects/{slug}.json')['project']
        except Exception as exc:
            if 'HTTP 404' not in str(exc):
                raise
            project = None
        if project and marker not in (project.get('description') or ''):
            raise ValueError('Project Redmine cùng tên đã thuộc công việc khác.')
        if not project:
            project = api.request('POST','/projects.json',{'project':dict(
                name=name,identifier=slug,description=brief+'\n\n'+marker,
                is_public=False,tracker_ids=[1,4,5],enabled_module_names=['issue_tracking','time_tracking','files'])})['project']
        project_id = project['id']
        receipt['redmine_project_id'] = project_id
        checkpoint()
        existing = api.request('GET',f'/projects/{project_id}/memberships.json?limit=100')['memberships']
        present = {member['user']['id'] for member in existing if 'user' in member}
        team = api.request('GET',f'/projects/{source.project}/memberships.json?limit=100')['memberships']
        for member in team:
            if 'user' in member and member['user']['id'] not in present:
                api.request('POST',f'/projects/{project_id}/memberships.json',{'membership':dict(
                    user_id=member['user']['id'],role_ids=[role['id'] for role in member['roles']])})
        checkout = HERE.parents[1] / 'ai-projects' / slug
        if not checkout.exists():
            checkout.parent.mkdir(parents=True,exist_ok=True)
            git(checkout.parent,'clone','https://github.com/'+repository+'.git',str(checkout))
        if git(checkout,'remote','get-url','origin').removesuffix('.git') != 'https://github.com/'+repository:
            raise ValueError('Checkout dự án không khớp repo mới.')
        if not git(checkout,'ls-remote','origin','refs/heads/main'):
            tracked = git(checkout,'ls-files').splitlines()
            if tracked and tracked != ['README.md']:
                raise ValueError('Checkout khởi tạo đã có tệp được theo dõi ngoài dự kiến.')
            if not tracked:
                (checkout/'README.md').write_text('# '+name+'\n\n'+brief+'\n',encoding='utf-8')
                git(checkout,'checkout','-B','main')
                git(checkout,'add','README.md')
                git(checkout,'-c','user.name=AI Office','-c','user.email=ai-office@localhost',
                    'commit','-m','Initialize project brief')
            git(checkout,'push','-u','origin','main')
        database = 'AI_'+slug.replace('-','_')[:45]
        if not receipt.get('preview_port'):
            used={value.get('preview_port',3102) for value in self.configs.values()}
            for port in range(3103,3200):
                if port in used:
                    continue
                with socket.socket() as probe:
                    try:
                        probe.bind(('127.0.0.1',port))
                    except OSError:
                        continue
                receipt['preview_port']=port
                checkpoint()
                break
            else:
                raise RuntimeError('Không tìm được cổng preview trống cho dự án.')
        config = dict(identifier=slug,name=name,redmine_project_id=project_id,
                      repository=repository,repo_path=str(checkout),runtime_path=str(directory),
                      test_database=database+'_Test',preview_database=database+'_Preview',
                      preview_port=receipt['preview_port'],
                      preview_url=f'http://localhost:{receipt["preview_port"]}/',
                      platform='Node.js, npm, Microsoft SQL Server')
        native = HERE.parent / 'runtime/lending/story-166/node_modules/mssql/msnodesqlv8.js'
        node = shutil.which('node')
        if not node or not native.is_file():
            raise RuntimeError('Chưa có Node.js hoặc driver SQL Server dùng để khởi tạo database dự án.')
        database_setup = subprocess.run(
            [node,str(HERE/'project_databases.cjs'),str(native),
             config['test_database'],config['preview_database']],
            capture_output=True,timeout=90)
        if database_setup.returncode:
            raise RuntimeError('Không khởi tạo được database riêng cho dự án. Kiểm tra quyền SQL Server.')
        receipt['databases_ready'] = True
        checkpoint()
        worker = Office(config)
        worker.manager = self
        worker.data['brief'] = brief
        worker.data['paused'] = True
        worker.stop.set()
        worker.save()
        for index in order:
            worker.dispatch_story(
                dict(id=f'bootstrap:{slug}:{index}',message=plans[index]['title']), plans[index])
            work = next(s for s in worker.data['stories'] if s['title']==plans[index]['title'])
            work['module'] = plans[index].get('module','')
            work['depends_on'] = [int(receipt['story_ids'][str(dep)]) for dep in plans[index].get('depends_on',[])]
            receipt['story_ids'][str(index)] = work['id']
            worker.save()
            checkpoint()
        worker.data['paused'] = False
        worker.stop.clear()
        summary = (f'Đã khởi tạo dự án {name}.\nGitHub: {remote["html_url"]}\n'
                   f'Redmine: {source.config["redmine_url"]}/projects/{slug}\n'
                   f'Đã chia {len(plans)} Story và giao task cho đội. SA bắt đầu phân tích kiến trúc trước BA và triển khai.')
        worker.save()
        (directory/'project.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        with self.lock:
            self.configs[slug] = config
            self.offices[slug] = worker
            self.active = slug
            self.save()
        receipt['complete'] = True
        checkpoint()
        self.start_worker(worker)
        self.start_preview(config)
        return summary+'\nMở Văn phòng AI và chọn dự án '+name+'.'
