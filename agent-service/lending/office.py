"""Separate project worker. Start explicitly; a new repository stays empty until a brief."""
from __future__ import annotations

import json
import copy
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from controller import Redmine, Service, json_file
from github_bridge import GitHub, git, safe_files


def forget_agent_credentials(key):
    from discord_credentials import delete_token
    delete_token(key)

REPO_NAME = 'quanlm053-cpu/club-equipment-lending'
REPO = HERE.parents[1] / 'club-equipment-lending'
RUNTIME = HERE.parent / 'runtime' / 'lending'
STATE = RUNTIME / 'state.json'
PROJECT = 2
ROLES = ('sa', 'ba', 'backend', 'frontend', 'devops', 'reviewer', 'tester')
LABELS = dict(zip(('pm', *ROLES), ('PM', 'SA', 'BA', 'BE', 'FE', 'DEVOPS', 'REVIEW', 'TESTER')))
TASK_NAMES = {
    'sa':'Thiết kế dữ liệu và API', 'ba':'Viết yêu cầu và dựng prototype',
    'backend':'Triển khai API và dữ liệu', 'frontend':'Dựng giao diện và nối API',
    'devops':'Chuẩn bị build và CI', 'reviewer':'Rà soát mã và phân quyền',
    'tester':'Kiểm thử theo tiêu chí nghiệm thu',
}
TASK_TOPICS = {
    111:'đăng nhập và phân quyền', 112:'tra cứu lịch trống', 113:'yêu cầu mượn',
    114:'duyệt yêu cầu', 115:'giao thiết bị', 116:'nhận lại thiết bị',
}
STATUS = {'backlog': 7, 'selected': 8, 'progress': 2, 'review': 10,
          'ready': 11, 'testing': 12, 'todo': 13, 'child_review': 14, 'done': 15}
CI_NAME = 'lending-validation'
CI_PATH = '.github/workflows/lending-validation.yml'
CI_CONTENT = """name: Lending validation
on: [pull_request]
permissions:
  contents: read
jobs:
  validate:
    name: lending-validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '26'
      - run: npm ci
      - run: npm test
      - run: npm run build
"""


def normalize(text):
    folded = unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
    return ' '.join(''.join(c for c in folded if unicodedata.category(c) != 'Mn').strip(' .!?').split())


def direct_task_request(message):
    if message.rstrip().endswith('?'):
        return None
    match = re.fullmatch(r'(?:hay |giup toi |bay gio )?(?:lam|trien khai|tiep tuc|chay) task\s*#?\s*(\d+)(?: di| nhe| ngay)?', normalize(message))
    return int(match[1]) if match else None


def dispatch_requested(message):
    """Only explicit work requests can create Redmine issues from PM chat."""
    if message.rstrip().endswith('?'):
        return False
    return bool(re.match(
        r'^(?:(?:pm|hay|thu|giup toi|ban|may|a khoan|bay gio|toi muon)[, ]+)*(?:tao (?:mot |1 )?(?:task|story|dau viec)|giao viec|them (?:tinh nang|chuc nang|task|story)|trien khai)\b',
        normalize(message)))

def dispatch_context(row, history):
    message = row['message']
    if dispatch_requested(message):
        return message
    confirmation = normalize(message)
    if message.rstrip().endswith('?') or not re.fullmatch(
        r'(?:cho )?(?:cac agent |agent |ca doi )?(?:bat dau(?: lam viec| cong viec)?|lam viec|trien khai)(?: di)?|tao va bat dau lam viec(?: di)?',
        confirmation
    ):
        return None
    return next((item['message'] for item in reversed(history)
                 if item['id'] < row['id'] and dispatch_requested(item['message'])),None)

PM_TASK_CAPABILITIES = (
    'PM có thể khởi tạo dự án mới từ đề bài, tạo repo GitHub/project Redmine riêng, '
    'chia phân hệ thành Story với phụ thuộc và task chuyên môn; chuyển giữa các dự án. '
    'PM tạo task con trong Story hiện có cho sửa chữ, CSS hoặc lỗi nhỏ theo vai trò phụ trách. '
    'Chức năng độc lập hoặc thay đổi lớn được lập thành Story mới. '
    'phân công đội, chạy lại Story/Task bị chặn, dừng hoặc tiếp tục dự án, '
    'sửa tiêu đề, mô tả, người được giao và hạn hoàn thành của issue trong dự án. '
    'Bộ điều phối thực thi action và báo kết quả thực tế. '
    'Người dùng thêm agent trong panel Agents. PM chỉ giao việc cho id sẵn sàng trong available_agents; '
    'chọn agent theo nhiệm vụ và chuyên môn, không tự thêm agent mới vào mọi Story. '
    'Agent bổ sung chỉ đọc nhận task phân tích và bàn giao báo cáo, không xuất bản code. '
    'Code qua REVIEW, TESTER, CI trước khi merge; preview tự cập nhật từ main.'
)

def schema(pm=False, agent_ids=None, collaboration=False, consult_ids=None):
    available = list(agent_ids) if agent_ids is not None else list(LABELS)
    specialists = [key for key in (available if consult_ids is None else consult_ids)
                   if consult_ids is not None or key != 'pm']
    def obj(**props):
        return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}
    string = {'type': 'string'}
    result = obj(summary=string, outcome={'type':'string','enum':['passed','needs_changes','blocked']},
               repair_role={'type':'string','enum':['backend','frontend','none']},
               artifacts={'type':'array','items':string},
               consult_role={'type':'string','enum':['none',*specialists]}, consult_question=string,
               stories={'type':'array','items':obj(title=string, acceptance=string)})
    if collaboration:
        result['properties']['requests']={'type':'array','maxItems':5,'items':obj(
            type={'type':'string','enum':['delegate_task','propose_agent']},target_id=string,
            parent_story_id={'type':'integer','minimum':0},title=string,instructions=string,
            independent={'type':'boolean'})}
        result['required'].append('requests')
    if pm:
        result['properties']['stories']['items'] = obj(
            title=string, acceptance=string, module=string,
            depends_on={'type':'array','items':{'type':'integer','minimum':0}})
        result['properties']['action'] = obj(
            type={'type':'string','enum':['answer','create_story','create_task','resume','pause','update_issue',
                                        'start_project','switch_project']},
            target_id={'type':'integer'},
            title=string, description=string, assignee={'type':'string','enum':['',*available]},
            due_date=string,
            repo_slug=string, visibility={'type':'string','enum':['','private','public']},
        )
        result['required'].append('action')
    return result


class Office:
    def __init__(self, project_config=None):
        self.project_config = project_config or {
            'identifier':'club-equipment-lending', 'name':'Mượn thiết bị',
            'redmine_project_id':PROJECT, 'repository':REPO_NAME,
            'repo_path':str(REPO), 'runtime_path':str(RUNTIME),
            'test_database':'ClubEquipmentLending_Test', 'preview_database':'ClubEquipmentLending_Preview',
            'preview_url':'http://localhost:3102/', 'platform':'Node.js, npm, Microsoft SQL Server',
        }
        deployment = HERE.parents[1] / 'deployment.local.json'
        if project_config is None and deployment.exists():
            supplied=json_file(deployment)
            supplied.pop('discord',None)
            self.project_config.update(supplied)
            for key in ('repo_path','runtime_path'):
                location=Path(self.project_config[key])
                self.project_config[key]=str(location if location.is_absolute() else (HERE.parents[1]/location).resolve())
        from agent_registry import AgentRegistry
        self.agents = AgentRegistry(Path(self.project_config['runtime_path']))
        self.project = self.project_config['redmine_project_id']
        self.repository = self.project_config['repository']
        self.repo = Path(self.project_config['repo_path'])
        self.runtime = Path(self.project_config['runtime_path'])
        self.state_path = self.runtime / 'state.json'
        self.manager = None
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.running_agents = {}
        self.agent_sync_futures = {}
        self.stop = threading.Event()
        self.config = json_file(HERE.parent / 'config.json')
        self.api = Redmine(self.config)
        self.codex = shutil.which('codex')
        if not self.codex and os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
            paths = (Path(os.environ['LOCALAPPDATA']) / 'OpenAI/Codex/bin').glob('*/codex.exe')
            cli = max(paths, key=lambda p: p.stat().st_mtime, default=None)
            self.codex = str(cli) if cli else None
        self.data = json_file(self.state_path) if self.state_path.exists() else {
            'stories': [], 'chat': [], 'messages': [], 'brief': '', 'paused': True, 'active': None}
        self.data['project'] = self.project_config
        if self.data['active'] or self.data.get('preparing') or any(c['state'] == 'running' for c in self.data['chat']):
            self.data['paused'] = True
            self.data['active'] = None
            self.data['preparing'] = None
            for c in self.data['chat']:
                if c['state'] == 'running':
                    c.update(state='failed', reply='Phiên trước bị gián đoạn. Gửi lại yêu cầu nếu cần.')
        if self.data['paused']:
            self.stop.set()
        self.save()
        (self.runtime/'schema.json').write_text(json.dumps(schema()), encoding='utf-8')
        (self.runtime/'schema-pm.json').write_text(json.dumps(schema(pm=True)), encoding='utf-8')

    @property
    def labels(self):
        return {a['id']:a['name'] for a in [*self.agents.deleted_profiles(),*self.agents.listing()]}

    @property
    def task_names(self):
        return {a['id']:a['title'] for a in self.agents.listing()}

    @property
    def ready_agents(self):
        from agent_redmine import AgentRedmine
        connector = AgentRedmine(self.api,self.project,self.agents)
        return [a['id'] for a in self.agents.listing() if a['status']=='ready' and (a['builtin'] or (
            a.get('redmine_managed') and a.get('redmine_sync',{}).get('state')=='synced'
            and a['redmine_sync'].get('user_status')==1
            and a['redmine_sync'].get('fingerprint')==connector.fingerprint(a)
            and not (getattr(self,'agent_sync_futures',{}).get(a['id'])
                     and not self.agent_sync_futures[a['id']].done())))]

    def request_agent_sync(self, key):
        with self.lock:
            profile = self.agents.get(key)
            if profile['builtin']:
                return profile
            if not hasattr(self,'agent_sync_futures'):
                self.agent_sync_futures = {}
            pending = self.agent_sync_futures.get(key)
            if pending and not pending.done():
                return profile
            self.agents.sync_update(key,state='pending',error='',retry_at=0)
            if not hasattr(self,'agent_sync_executor'):
                self.agent_sync_executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='agent-redmine')
            self.agent_sync_futures[key] = self.agent_sync_executor.submit(self.sync_agent_redmine,key)
            return self.agents.get(key)

    def sync_agent_redmine(self, key):
        from agent_redmine import AgentRedmine
        try:
            profile = AgentRedmine(self.api,self.project,self.agents).ensure(key)
            self.agents.sync_update(key,state='provisioning')
            with self.lock:
                tasks = {s['tasks'][key]['id'] for s in self.data.get('stories',[])
                         if key in s['tasks'] and s['state'] not in ('done','cancelled')
                         and s['tasks'][key]['state'] not in ('done','delivered')}
            user_id = profile['redmine_user_id']
            previous_id = profile.get('redmine_sync',{}).get('previous_user_id')
            for task_id in tasks:
                issue = self.api.issue(task_id)
                if issue['project']['id']!=self.project:
                    raise ValueError(f'Task #{task_id} nằm ngoài dự án, chưa tự đổi người nhận.')
                if issue['status']['is_closed']:
                    continue
                assigned = issue.get('assigned_to',{}).get('id')
                if assigned not in (None,previous_id,user_id):
                    raise ValueError(f'Task #{task_id} đã được giao cho tài khoản khác trên Redmine; cần kiểm tra trước khi đồng bộ.')
                if assigned!=user_id:
                    self.api.update(task_id,assigned_to_id=user_id)
                    if self.api.issue(task_id).get('assigned_to',{}).get('id')!=user_id:
                        raise ValueError(f'Chưa xác minh được người nhận mới của Task #{task_id}.')
            self.agents.sync_update(key,state='synced',previous_user_id=None)
            return True
        except Exception as exc:
            code = re.search(r'Redmine HTTP (\d+)',str(exc))
            if code and code[1] in ('401','403'):
                reason = 'Redmine từ chối quyền. Tài khoản kết nối cần quyền quản trị để tạo user và thêm thành viên dự án.'
            elif isinstance(exc,ValueError):
                reason = str(exc)
            else:
                reason = 'Chưa đồng bộ được Redmine. Kiểm tra kết nối và quyền của tài khoản dịch vụ; có thể thử lại mà không tạo trùng user.'
            try:
                self.agents.sync_update(key,state='error',error=reason,retry_at=time.time()+60)
            except Exception:
                print('Không lưu được trạng thái đồng bộ agent.',flush=True)
            return False

    def pump_agent_sync(self):
        from agent_redmine import AgentRedmine
        connector = AgentRedmine(self.api,self.project,self.agents)
        for profile in self.agents.listing():
            if profile['builtin']:
                continue
            sync = profile.get('redmine_sync',{})
            if (sync.get('fingerprint')!=connector.fingerprint(profile) or sync.get('state')!='synced'):
                if sync.get('retry_at',0)<=time.time() and not self.agent_busy(profile['id']):
                    self.request_agent_sync(profile['id'])

    def members(self):
        result, offset = [], 0
        while True:
            page = self.api.request('GET',f'/projects/{self.project}/memberships.json?limit=100&offset={offset}')
            rows = page['memberships']
            result.extend(m['user'] for m in rows if 'user' in m)
            offset += len(rows)
            if not rows or offset>=page.get('total_count',offset):
                return result

    def assignee(self, role):
        profile = self.agents.get(role)
        if not profile['builtin'] and role not in self.ready_agents:
            raise ValueError('Agent chưa đồng bộ tài khoản Redmine hoặc chưa sẵn sàng.')
        members = self.members()
        member = next((m for m in members if
            (m['id']==profile['redmine_user_id'] if profile.get('redmine_user_id')
             else m['name']=='Lending AI '+LABELS.get(role,profile['name']))),None)
        if not member:
            raise ValueError('Cần chọn thành viên Redmine hợp lệ cho '+profile['name'])
        return member['id']

    def agent_busy(self, key):
        sync = getattr(self,'agent_sync_futures',{}).get(key)
        return bool(sync and not sync.done()) or bool(self.running_agents.get(key)) or any(a and a.get('role')==key for a in (self.data.get('active'),self.data.get('preparing'))) or any(
            c.get('role','pm')==key and c['state']=='running' for c in self.data['chat'])

    def agent_blockers(self, key):
        pending = [s['id'] for s in self.data['stories'] if s['state'] not in ('done','cancelled') and key in s['tasks']]
        chats = [c['id'] for c in self.data['chat'] if c.get('role')==key and c['state'] in ('queued','running')]
        proposals = [r['id'] for r in self.data.get('agent_requests',[]) if key in (r['agent'],r.get('target_id'))
                     and r['state'] in ('pending','failed','waiting_source','executing')]
        if pending or chats or proposals:
            details = ('Task/Story: '+', '.join('#'+str(i) for i in pending)) if pending else ''
            if chats: details += ' · Hội thoại: '+', '.join('#'+str(i) for i in chats)
            if proposals:details += ' · Đề xuất đang mở: '+str(len(proposals))
            raise ValueError('Agent còn công việc. Chuyển hoặc hoàn thành trước. '+details)

    def reassign_agent_task(self, key, payload):
        source = self.agents.get(key)
        target = self.agents.get(payload.get('target_id'))
        if target['id']==key or target['status']!='ready' or target['id'] in ('pm','reviewer','tester'):
            raise ValueError('Chọn agent khác đang sẵn sàng.')
        if (source['access'],source['specialty'])!=(target['access'],target['specialty']):
            raise ValueError('Agent thay thế cần cùng chuyên môn và quyền đọc/sửa.')
        work = next((s for s in self.data['stories'] if s['id']==payload.get('work_id')),None)
        if not work or work.get('kind')!='task' or key not in work['tasks']:
            raise ValueError('Chỉ chuyển task riêng do agent phụ trách.')
        if work['state'] not in ('queued','attention') or work['stage']!=0 or work['results']:
            raise ValueError('Chỉ chuyển task chưa bắt đầu; giữ nguyên bản bàn giao đã thực hiện.')
        if target['id'] in work['tasks']:
            raise ValueError('Agent thay thế đã có trong workflow của task.')
        issue = self.api.issue(work['id'])
        if issue['project']['id']!=self.project or issue['status']['is_closed']:
            raise ValueError('Task ngoài dự án hoặc đã đóng.')
        user_id = self.assignee(target['id'])
        self.api.update(work['id'],assigned_to_id=user_id,subject=f'{target["name"]}: {work["title"]}'[:230])
        if self.api.issue(work['id']).get('assigned_to',{}).get('id')!=user_id:
            raise RuntimeError('Chưa xác minh người nhận mới trên Redmine. Kiểm tra task trước khi thử lại.')
        previous = copy.deepcopy(work)
        task = work['tasks'].pop(key)
        task['state'] = 'queued'
        work['tasks'][target['id']] = task
        work['workflow'] = [target['id'] if r==key else r for r in work['workflow']]
        work.update(owner_role=target['id'],state='queued',error='',repair_role='')
        work.pop('retry_at',None)
        work.pop('automatic_retries',None)
        try:
            self.save()
        except Exception:
            work.clear();work.update(previous)
            raise
        self.message('human','pm',f'Chuyển Task #{work["id"]}: {source["name"]} → {target["name"]}',work.get('parent_story'),work['id'])
        return {'message':f'Đã chuyển Task #{work["id"]} sang {target["name"]}.'}

    def manage_agent(self, payload):
        with self.lock:
            operation = payload.get('operation','save')
            key = payload.get('id')
            if key is not None and not isinstance(key,str):
                raise ValueError('Mã agent không hợp lệ.')
            if operation=='review_request':
                return self.review_agent_request(payload)
            if operation=='create_skill':
                return self.library.create(payload)
            if operation=='assign':
                if key not in self.ready_agents or key in ('pm','reviewer','tester'):
                    raise ValueError('Chọn agent sẵn sàng nhận việc.')
                parent_id = payload.get('story_id')
                if type(parent_id) is not int or parent_id<=0:
                    raise ValueError('Cần mã Story cha.')
                parent = self.api.issue(parent_id)
                if parent['project']['id']!=self.project or parent['tracker']['id']!=4:
                    raise ValueError('Chỉ giao task vào Story trong dự án hiện tại.')
                request_key = payload.get('request_id','')
                if not isinstance(request_key,str) or not re.fullmatch(r'[a-zA-Z0-9-]{8,80}',request_key):
                    raise ValueError('Mã yêu cầu không hợp lệ.')
                plan = {field:payload.get(field,'') for field in ('title','acceptance')}
                if any(not isinstance(v,str) or not 1<=len(v.strip())<=6000 for v in plan.values()):
                    raise ValueError('Cần tên task và tiêu chí nghiệm thu (tối đa 6000 ký tự).')
                return {'message':self.dispatch_task({'id':'agent-'+request_key},{'id':parent_id},plan,key)}
            if key and self.agent_busy(key):
                raise ValueError('Agent đang chạy hoặc đang đồng bộ Redmine. Đợi hoàn tất trước khi đổi cấu hình.')
            if key and payload.get('revision') is not None and payload['revision']!=self.agents.get(key)['revision']:
                raise ValueError('Cấu hình đã thay đổi. Tải lại trước khi thao tác.')
            if operation=='cancel_chat':
                chat = next((c for c in self.data['chat'] if c['id']==payload.get('chat_id') and c.get('role')==key),None)
                if not chat or chat['state']!='queued':
                    raise ValueError('Chỉ hủy được yêu cầu còn trong hàng chờ của agent này.')
                previous = dict(chat)
                chat.update(state='failed',reply='Người điều hành đã hủy yêu cầu đang chờ.')
                try:
                    self.save()
                except Exception:
                    chat.clear();chat.update(previous)
                    raise
                return {'message':'Đã hủy yêu cầu #'+str(chat['id'])+'.'}
            if operation=='reassign':
                return self.reassign_agent_task(key,payload)
            if operation=='duplicate':
                result = self.agents.duplicate(key)
                result = self.request_agent_sync(result['id'])
                self.message('human','pm',f'Nhân bản agent: {result["name"]}')
                return result
            if operation=='delete':
                self.agent_blockers(key)
                profile = self.agents.get(key)
                if profile['builtin'] or profile['status'] not in ('archived','terminated'):
                    raise ValueError('Chỉ xóa agent bổ sung đã lưu trữ hoặc chấm dứt.')
                if payload.get('confirm_name')!=profile['name']:
                    raise ValueError('Nhập chính xác tên agent để xác nhận xóa.')
                from agent_redmine import AgentRedmine
                AgentRedmine(self.api,self.project,self.agents).lock_for_delete(key)
                result = self.agents.delete(key,payload.get('revision'),payload.get('confirm_name'))
                try:
                    forget_agent_credentials(key)
                except OSError:
                    result['warning']='Đã xóa hồ sơ; chưa xóa được token cục bộ trong Windows Credential Manager.'
                self.message('human','pm',f'Đã xóa hồ sơ agent {result["name"]}; lịch sử công việc được giữ.')
                return result
            if operation=='save':
                from agent_settings import validate
                configured=validate(payload,self.agents.get(key) if key else None)
                self.library.content(configured['capabilities']['skill_ids'])
                known={a['id'] for a in self.agents.listing()}
                if any(target not in known or target==key for field in ('assignees','consultants')
                       for target in configured['collaboration'][field]):
                    raise ValueError('Có agent cộng tác không hợp lệ hoặc đang chọn chính mình.')
                result = self.agents.change(payload,key)
            elif operation=='sync':
                return self.request_agent_sync(key)
            elif operation in ('verify','resume','restore','pause','archive','terminate'):
                profile = self.agents.get(key)
                if operation in ('archive','terminate'):
                    self.agent_blockers(key)
                if operation=='terminate' and payload.get('confirm_name')!=profile['name']:
                    raise ValueError('Nhập chính xác tên agent để xác nhận chấm dứt.')
                if operation=='restore' and profile['status'] not in ('archived','terminated'):
                    raise ValueError('Agent chưa được lưu trữ hoặc chấm dứt.')
                if operation=='resume' and profile['status']!='paused':
                    raise ValueError('Agent không ở trạng thái tạm dừng.')
                if operation in ('verify','resume'):
                    from agent_providers import check_available
                    from agent_settings import settings
                    check_available(settings(profile)['runtime'],self.codex,require_auth=True)
                    if (not profile['builtin'] and profile['specialty']=='specialist' and not profile['instructions']
                            and not profile.get('capabilities',{}).get('skill_ids')):
                        raise ValueError('Cần hướng dẫn chuyên môn hoặc chọn skill cho vai trò mới.')
                    if profile['builtin']:
                        self.assignee(key)
                result = self.agents.transition(key,{'verify':'ready','resume':'ready','restore':'draft',
                    'pause':'paused','archive':'archived','terminate':'terminated'}[operation])
                if operation in ('verify','resume'):
                    for story in self.data['stories']:
                        if story['state']=='attention' and story.get('error','').startswith('Agent đang tạm dừng'):
                            flow=story.get('workflow',ROLES)
                            if story['stage']<len(flow) and (story.get('repair_role') or flow[story['stage']])==key:
                                story.update(state='queued',error='')
                if operation=='terminate':
                    try:
                        forget_agent_credentials(key)
                    except OSError:
                        result['warning']='Đã chấm dứt agent; chưa xóa được token cục bộ trong Windows.'
            else:
                raise ValueError('Thao tác agent không hợp lệ.')
            if not result['builtin']:
                result = self.request_agent_sync(result['id'])
            self.message('human','pm',f"Agent {result['name']}: {operation} → {result['status']}")
            return result

    def save(self):
        with self.lock:
            tmp = self.state_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            # Windows can temporarily deny replacement while another process
            # reads the previous snapshot. Keep it intact and retry the rename.
            for attempt in range(8):
                try:
                    tmp.replace(self.state_path)
                    return
                except PermissionError as exc:
                    if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 7:
                        raise
                    time.sleep(min(0.05 * 2 ** attempt, 0.5))

    def message(self, sender, recipient, text, story=None, task=None):
        with self.lock:
            work = next((s for s in self.data['stories'] if s['id']==story and s.get('kind')=='task'), None)
            if work:
                story = work['parent_story']
            self.data['messages'].append(dict(sender=sender, recipient=recipient, text=text,
                                              story=story, task=task, at=time.time()))
            self.save()

    def submit(self, message, role='pm'):
        if role not in self.ready_agents:
            raise ValueError('Vai trò không hợp lệ.')
        with self.lock:
            intent = normalize(message)
            request_id=self.manager.next_id() if self.manager else len(self.data['chat'])+1
            row = dict(id=request_id, message=message, role=role, state='queued', reply='',
                       project=self.project_config['identifier'])
            if role != 'pm':
                self.data['chat'].append(row)
                self.message('human', role, message)
                self.save()
                return row['id']
            if intent in ('dung du an','tam dung du an','dung toan bo du an'):
                self.stop.set()
                self.data['paused'] = True
                row.update(state='done', reply='Đã chặn lượt mới. Lượt đang chạy sẽ dừng và giữ lại phần đã lưu.')
            elif intent in ('tiep tuc du an','chay tiep du an'):
                if self.data['active'] or self.data.get('preparing'):
                    raise ValueError('Đang đợi lượt hiện tại dừng. Hãy thử lại khi văn phòng báo đã dừng.')
                self.data['paused'] = False
                self.stop.clear()
                for story in self.data['stories']:
                    if story['state'] == 'attention':
                        story.update(state='queued', error='')
                row.update(state='done', reply='Đã cho phép tiếp tục công việc đang chờ.')
            elif intent in ('bao cao tien do cong viec cua ba','bao cao tien do ba','ba dang lam gi'):
                assignments = [(s,s['tasks']['ba']) for s in self.data['stories'] if 'ba' in s['tasks']]
                states = {'running':'đang xử lý','queued':'đang chờ','delivered':'đã bàn giao','done':'hoàn thành'}
                lines = [f'Story #{s["id"]} · {s["title"]}, Task #{t["id"]}: {states[t["state"]]}'
                         + (f'. Bàn giao: {s["results"]["ba"]["summary"]}' if 'ba' in s['results'] else '')
                         + (f'. Vướng: {s["error"]}' if s.get('error') and t['state']!='done' else '')
                         for s,t in assignments]
                row.update(state='done', reply='\n'.join(lines) or 'BA chưa được giao task trong dự án này.')
            elif re.search(r'\b(co the|da co|duoc chua|ho tro)\b', intent) and re.search(
                    r'\b(tao|chinh sua|sua)\b.*\btask\b', intent) and not dispatch_requested(message):
                row.update(state='done', reply=PM_TASK_CAPABILITIES)
            self.data['chat'].append(row)
            self.save()
            return row['id']

    def check_stop(self):
        if self.stop.is_set():
            raise InterruptedError('Dự án đã tạm dừng.')

    @property
    def library(self):
        from agent_settings import SkillLibrary
        return SkillLibrary(self.runtime,HERE/'skills')

    def call(self, role, cwd, context, *, allow_paused=False, read_only=False):
        from agent_settings import settings
        profile=self.agents.get(role)
        config=settings(profile)['runtime']
        writing=not read_only and profile['access']=='write'
        root=Path(cwd).resolve()
        lease=str(time.time_ns())+'-'+role
        waiting=time.monotonic()
        while True:
            with self.lock:
                if role not in self.ready_agents:
                    raise ValueError('Agent chưa sẵn sàng: '+self.labels[role])
                if self.agents.get(role)['revision']!=profile['revision']:
                    raise ValueError('Cấu hình agent đã thay đổi trong lúc chờ. Chạy lại với cấu hình mới.')
                if not hasattr(self,'running_paths'):self.running_paths={}
                overlap=writing and any(p==root or root.is_relative_to(p) or p.is_relative_to(root) for p in self.running_paths.values())
                if self.running_agents.get(role,0)<config['concurrent_attempts'] and not overlap:
                    self.running_agents[role]=self.running_agents.get(role,0)+1
                    if writing:self.running_paths[lease]=root
                    break
            if not allow_paused:self.check_stop()
            if time.monotonic()-waiting>config['timeout_minutes']*60:
                raise TimeoutError('Hết thời gian chờ lượt chạy của '+profile['name'])
            time.sleep(.1)
        try:
            return self._call(role,cwd,context,allow_paused=allow_paused,read_only=read_only)
        finally:
            with self.lock:
                self.running_agents[role]-=1
                self.running_paths.pop(lease,None)

    def _call(self, role, cwd, context, *, allow_paused=False, read_only=False):
        from token_usage import TokenUsage,extract
        from agent_settings import settings
        runtime=settings(self.agents.get(role))['runtime']
        ledger=TokenUsage(self.runtime)
        output = self.runtime / f'{time.time_ns()}-{role}.json'
        key=ledger.start(role,runtime['adapter'],runtime['model'],context)
        state='failed'
        try:
            result=self._execute(role,cwd,context,output,allow_paused=allow_paused,read_only=read_only)
            state='completed'
            return result
        finally:
            path=output.with_suffix('.jsonl' if runtime['adapter']=='codex' else '.provider-output.json')
            ledger.finish(key,extract(runtime['adapter'],path),state)

    def _execute(self, role, cwd, context, output, *, allow_paused=False, read_only=False):
        if not allow_paused:
            self.check_stop()
        profile = self.agents.get(role)
        if role not in self.ready_agents:
            raise ValueError('Agent chưa sẵn sàng: '+profile['name'])
        from agent_settings import settings,enabled_tools,allowed
        config=settings(profile)
        runtime=config['runtime']
        from agent_providers import check_available,prepare,decode,runtime_error
        provider=runtime['adapter']
        check_available(runtime,self.codex,require_auth=provider!='codex')
        tools=enabled_tools(profile)
        collab=config['collaboration']
        can_request=bool((role!='pm' and collab['assign_to']!='nobody') or collab['can_propose_agents'])
        consultations=[key for key in self.ready_agents if allowed(profile,'consult',key,self.ready_agents)]
        specialty = profile['specialty']
        template = HERE / 'skills' / specialty / 'SKILL.md'
        skill = template.read_text(encoding='utf-8') if template.is_file() else 'Thực hiện công việc chuyên môn được giao, bàn giao kết quả có bằng chứng.'
        skill += '\nTên agent: '+profile['name']+'\nNhiệm vụ: '+profile['title']+'\n'+profile['instructions']
        skill+='\nHồ sơ chuyên môn: '+json.dumps({k:config[k] for k in ('role','description','goals','work_rules','tags')},ensure_ascii=False)
        skill+='\n'+self.library.content(config['capabilities']['skill_ids'])
        skill+='\nChính sách cộng tác: '+json.dumps(collab,ensure_ascii=False)
        if can_request:
            skill+='\nCó thể đề xuất requests: delegate_task hoặc propose_agent. Không tự gọi API để giao việc/tạo agent. independent chỉ true khi công việc không cần code đang làm. Quyền và giới hạn do bộ điều phối kiểm tra. Không có đề xuất thì requests rỗng.'
        schema_path = output.with_suffix('.schema.json')
        schema_path.write_text(json.dumps(schema(pm=role=='pm',agent_ids=self.ready_agents,consult_ids=consultations,collaboration=can_request)),encoding='utf-8')
        provider_env={}
        if provider=='codex':
            mcp_args = json.dumps([str(HERE/'mcp.py'), str(self.state_path),json.dumps([key for key in tools if key in ('project_state','read_issue','search_issues')])])
            command = [self.codex, 'exec', '--ignore-user-config',
                       '-c', 'approval_policy="never"', '-c', 'windows.sandbox="elevated"',
                       '-c', 'agents.enabled=false', '-c', 'features.apps=false', '-c', 'features.plugins=false',
                       '-c', 'mcp_servers.lending.command='+json.dumps(sys.executable),
                       '-c', 'mcp_servers.lending.args='+mcp_args,
                       '-c', 'mcp_servers.lending.enabled_tools='+json.dumps([key for key in tools if key in ('project_state','read_issue','search_issues')]),
                       '-c', 'features.shell_tool='+('true' if 'shell' in tools else 'false'),
                       '-c', 'web_search='+json.dumps('live' if 'web_search' in tools else 'disabled'),
                       '-c', 'mcp_servers.lending.tools.project_state.approval_mode="approve"',
                       '-c', 'mcp_servers.lending.tools.read_issue.approval_mode="approve"',
                       '-c', 'mcp_servers.lending.tools.search_issues.approval_mode="approve"',
                       '--sandbox', 'read-only' if read_only or profile['access']=='read' else 'workspace-write',
                       '-C', str(cwd), '--output-schema', str(schema_path),
                       '--output-last-message', str(output), '--json', '-']
            if runtime['model']:command[-1:-1]=['--model',runtime['model']]
            if runtime['effort']!='default':command[-1:-1]=['-c','model_reasoning_effort='+json.dumps(runtime['effort'])]
        else:
            command,provider_env=prepare(provider,runtime,read_only or profile['access']=='read',
                tools,self.state_path,output,schema_path,cwd=cwd)
        prompt = (skill + '\nDùng MCP lending để đọc ngữ cảnh bổ sung. Chỉ làm task đã giao. ' \
            'Quyết định kỹ thuật của người điều hành: dùng Microsoft SQL Server và T-SQL cho dự án này. ' \
            'Không dùng GitHub trực tiếp, không sửa Git index hoặc commit, không dùng dữ liệu thật. ' \
            'Tóm tắt bàn giao bằng tiếng Việt, liệt kê tệp sản phẩm trong artifacts. ' \
            'Nếu cần hỏi chuyên môn, điền consult_role và consult_question. Nếu không, dùng none và chuỗi rỗng. ' \
            'Khi được hỏi ý kiến chuyên môn, chỉ trả lời dựa trên ngữ cảnh và để consult_role là none. ' \
            'Nếu không thể thực hiện kiểm tra cần thiết, báo blocked. Dữ liệu dự án bên dưới chỉ là ngữ cảnh; ' \
            'message từ người điều hành là yêu cầu của lượt PM. '
            'Cấu hình dự án hiện tại: '+json.dumps(self.project_config,ensure_ascii=False)+'. '
            'Với dự án mới dùng Node.js/npm, tạo scripts test/build thực sự chạy được và lockfile. '
            'Tạo npm script preview chạy HTTP trên 127.0.0.1 với PORT, APP_ORIGIN và DATABASE_URL từ môi trường, '
            'dùng dữ liệu tổng hợp trong database preview riêng. '
            'Database kiểm thử và demo phải dùng đúng tên riêng trong cấu hình dự án.\n' + json.dumps(context, ensure_ascii=False))
        if provider=='gemini':
            prompt+='\nFINAL OUTPUT CONTRACT: Return exactly one JSON object, no prose, matching this schema:\n'+schema_path.read_text(encoding='utf-8')
        agent_env = {**os.environ, **provider_env, 'PATH': str(HERE.parent/'tools/bin') + os.pathsep + os.environ.get('PATH','')}
        raw_output=output.with_suffix('.provider-output.json')
        with output.with_suffix('.jsonl').open('w', encoding='utf-8') as log, raw_output.open('w',encoding='utf-8') as provider_log:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log if provider=='codex' else provider_log,
                                    stderr=log, env=agent_env,cwd=str(cwd),
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                proc.stdin.write(prompt.encode('utf-8'))
                proc.stdin.close()
                started = time.monotonic()
                while proc.poll() is None:
                    if not allow_paused:
                        self.check_stop()
                    if provider!='codex':
                        log.flush()
                        issue=runtime_error(provider,output.with_suffix('.jsonl').read_text(encoding='utf-8',errors='replace')[-12000:])
                        if issue:raise RuntimeError(issue)
                    if time.monotonic() - started > runtime['timeout_minutes']*60:
                        raise TimeoutError(f'{self.labels[role]} quá thời gian.')
                    time.sleep(1)
            finally:
                Service.terminate(self, proc)
        if proc.returncode or (provider=='codex' and not output.is_file()):
            with output.with_suffix('.jsonl').open(encoding='utf-8', errors='replace') as log:
                for line in log:
                    if 'usage limit' in line.casefold() and ('"type":"error"' in line or '"type":"turn.failed"' in line):
                        raise RuntimeError(f'{self.labels[role]} tạm dừng vì phiên Codex đã chạm giới hạn sử dụng.')
            raise RuntimeError(f'{self.labels[role]} ({provider}) gặp lỗi đăng nhập, model, quyền hoặc kết nối. Xem nhật ký {output.with_suffix(".jsonl").name}; không tự đổi nhà cung cấp.')
        if provider!='codex':
            try:
                result=decode(provider,raw_output.read_text(encoding='utf-8'),json_file(schema_path))
            except (ValueError,TypeError) as exc:
                raise RuntimeError(f'{self.labels[role]} ({provider}) trả bàn giao sai định dạng; chưa thực hiện action. Xem {raw_output.name}.') from exc
            output.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            return result
        return json_file(output)

    def consult(self, role, cwd, context, *, story=None, task=None, allow_paused=False, read_only=False):
        result = self.call(role,cwd,context,allow_paused=allow_paused,read_only=read_only)
        specialist = result['consult_role']
        question = result['consult_question'].strip()
        if specialist=='none' or specialist==role or not question:
            return result
        from agent_settings import allowed
        if not allowed(self.agents.get(role),'consult',specialist,self.ready_agents):
            raise ValueError('Agent chưa được phép hỏi '+self.labels.get(specialist,specialist))
        self.message(role,specialist,question,story,task)
        answer = self.call(specialist,cwd,{'consultation':question,'asked_by':role,'context':context},
                           allow_paused=allow_paused,read_only=True)
        self.message(specialist,role,answer['summary'],story,task)
        return self.call(role,cwd,{**context,'consultation_answer':answer['summary']},
                         allow_paused=allow_paused,read_only=read_only)

    def process_agent_requests(self, role, result, *, work=None, chat_id=None):
        from agent_settings import settings,allowed,text
        profile=self.agents.get(role)
        policy=settings(profile)['collaboration']
        notices=[]
        proposals=result.get('requests',[])
        if not isinstance(proposals,list):
            return ['Đề xuất không đúng định dạng danh sách; chưa thực hiện.']
        for proposal in proposals[:5]:
            try:
                if not isinstance(proposal,dict):raise ValueError('Đề xuất không hợp lệ.')
                kind=proposal.get('type')
                if kind not in ('delegate_task','propose_agent'):
                    raise ValueError('Loại đề xuất không hợp lệ.')
                if kind=='propose_agent' and not policy['can_propose_agents']:
                    raise ValueError('Agent chưa được phép đề xuất nhân sự mới.')
                if kind=='delegate_task' and not allowed(profile,'assign',proposal.get('target_id'),self.ready_agents):
                    raise ValueError('Agent chưa được giao task cho người nhận này.')
                if kind=='delegate_task' and (type(proposal.get('parent_story_id')) is not int or proposal['parent_story_id']<=0):
                    raise ValueError('Cần mã Story cha hợp lệ để đề xuất giao task.')
                title=text(proposal.get('title'),'Tên đề xuất',160)
                detail=text(proposal.get('instructions'),'Nội dung đề xuất',6000)
                if not title or not detail:raise ValueError('Đề xuất cần tên và nội dung.')
                depth=(work or {}).get('delegation_depth',0)+1
                limit=min(policy['max_depth'],(work or {}).get('delegation_limit',5))
                if kind=='delegate_task' and depth>limit:
                    raise ValueError('Đã chạm giới hạn độ sâu phân công.')
                identity=hashlib.sha256(json.dumps([role,(work or {}).get('id'),chat_id,proposal],
                    ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]
                with self.lock:
                    requests=self.data.setdefault('agent_requests',[])
                    existing=next((r for r in requests if r['id']==identity),None)
                    if existing:
                        notices.append('Đề xuất '+identity[:8]+': '+existing['state'])
                        continue
                    open_count=sum(r['agent']==role and r['state'] in ('pending','failed','waiting_source','executing') for r in requests)
                    open_count+=sum(s.get('delegated_by')==role and s['state'] not in ('done','cancelled') for s in self.data['stories'])
                    if open_count>=policy['max_open_subtasks']:
                        raise ValueError('Đã chạm giới hạn công việc con đang mở.')
                    row=dict(id=identity,agent=role,type=kind,state='pending',title=title,
                        instructions=detail,target_id=proposal.get('target_id',''),
                        parent_story_id=proposal.get('parent_story_id',0),
                        independent=proposal.get('independent') is True,
                        source_work=(work or {}).get('id'),depth=depth,limit=limit,at=time.time())
                    requests.append(row)
                    self.save()
                autonomy=policy['autonomy']
                if autonomy=='project':autonomy=self.project_config.get('agent_autonomy','suggest')
                if kind=='delegate_task' and autonomy=='delegate' and row['independent']:
                    self.execute_agent_request(row)
                    notices.append('Đã phân công: '+title)
                else:
                    self.message(role,'human','Đề xuất cần duyệt: '+title,(work or {}).get('parent_story',(work or {}).get('id')))
                    notices.append('Đã gửi đề xuất chờ bạn duyệt: '+title)
            except (ValueError,RuntimeError) as exc:
                notices.append('Chưa thực hiện đề xuất: '+str(exc))
        return notices

    def execute_agent_request(self, row):
        with self.lock:
            if row['state']=='executed':
                return row.get('result','Đã thực hiện.')
            if row['state']=='rejected':
                raise ValueError('Đề xuất đã bị từ chối.')
            row['state']='executing'
            self.save()
            try:
                return self._execute_agent_request(row)
            except Exception:
                row.update(state='failed',error='Chưa thực hiện xong; kiểm tra trước khi duyệt lại.')
                self.save()
                raise

    def _execute_agent_request(self, row):
        from agent_settings import settings,allowed
        profile=self.agents.get(row['agent'])
        policy=settings(profile)['collaboration']
        if profile['status'] in ('archived','terminated'):
            raise ValueError('Agent đề xuất đã nghỉ việc.')
        if row['type']=='pm_action':
            answer=self.execute_pm_action({**row['pm_row'],'owner_approved':True},row['pm_result'])
            row.update(state='executed',result=answer)
        elif row['type']=='propose_agent':
            if not policy['can_propose_agents']:
                raise ValueError('Quyền đề xuất agent đã bị thu hồi.')
            agent=self.agents.get(row['created_agent']) if row.get('created_agent') else self.agents.change(
                dict(name=row['title'][:40],title=row['title'],role=row['title'],
                     description=row['instructions'][:4000],specialty='specialist',access='read',
                     instructions=row['instructions']))
            row['created_agent']=agent['id']
            self.save()
            self.request_agent_sync(agent['id'])
            row.update(state='executed',result='Đã tạo bản nháp '+agent['name'],created_agent=agent['id'])
        else:
            if not allowed(profile,'assign',row['target_id'],self.ready_agents):
                raise ValueError('Người nhận không còn phù hợp hoặc quyền phân công đã bị thu hồi.')
            if row['depth']>min(policy['max_depth'],row['limit']):
                raise ValueError('Giới hạn độ sâu phân công đã thay đổi.')
            if sum(s.get('delegated_by')==row['agent'] and s['state'] not in ('done','cancelled')
                   for s in self.data['stories'])>=policy['max_open_subtasks']:
                raise ValueError('Đã chạm giới hạn task con đang mở.')
            source=next((s for s in self.data['stories'] if s['id']==row.get('source_work')),None)
            if source and source['state']!='done' and not row['independent']:
                row['state']='waiting_source'
                self.save()
                return 'Đã duyệt; chờ công việc gốc hoàn thành để dùng đúng bản code.'
            parent=self.api.issue(row['parent_story_id'])
            if parent['project']['id']!=self.project or parent['tracker']['id']!=4:
                raise ValueError('Đề xuất phải trỏ tới Story trong dự án.')
            answer=self.dispatch_task({'id':'delegate-'+row['id']},{'id':parent['id']},
                {'title':row['title'],'acceptance':row['instructions']},row['target_id'])
            work=next(s for s in self.data['stories'] if s.get('task_request')=='delegate-'+row['id'])
            work.update(delegated_by=row['agent'],delegation_depth=row['depth'],delegation_limit=row['limit'])
            row.update(state='executed',result=answer)
        self.save()
        return row['result']

    def review_agent_request(self, payload):
        with self.lock:
            row=next((r for r in self.data.get('agent_requests',[]) if r['id']==payload.get('request_id')),None)
            if not row:raise ValueError('Không tìm thấy đề xuất.')
            if row['state']=='executed':return {'message':row.get('result','Đã thực hiện.')}
            if row['state']=='rejected':raise ValueError('Đề xuất đã bị từ chối.')
            if payload.get('decision')=='reject':
                row.update(state='rejected',reviewed_at=time.time())
                self.save()
                return {'message':'Đã từ chối đề xuất.'}
            if payload.get('decision')!='approve':raise ValueError('Quyết định không hợp lệ.')
            try:
                answer=self.execute_agent_request(row)
                row['reviewed_at']=time.time()
                return {'message':answer}
            except Exception:
                row.update(state='failed',error='Chưa thực hiện xong. Kiểm tra kết nối, quyền và công việc trước khi duyệt lại.')
                self.save()
                raise

    def assign_existing_task(self, role, task_id):
        """Bind an existing pipeline slot; never create a duplicate issue or skip dependencies."""
        with self.lock:
            if role not in self.ready_agents:
                raise ValueError('Agent chưa sẵn sàng nhận việc.')
            matches = [(s, old, t) for s in self.data['stories'] for old,t in s['tasks'].items()
                       if t['id']==task_id]
            if len(matches)!=1:
                raise ValueError('Task chưa có một bước thực thi duy nhất trong kế hoạch. Hãy giao PM lập kế hoạch cho task này.')
            story, old, task = matches[0]
            flow = list(story.get('workflow', ROLES))
            if old!=role and role in flow:
                raise ValueError('Agent đã phụ trách bước khác trong Story này; cần PM điều chỉnh kế hoạch.')
            if old not in flow or flow.index(old)<story['stage'] or task['state'] in ('delivered','done'):
                raise ValueError('Task đã bàn giao; hãy giao PM tạo task sửa đổi trong Story hiện có.')
            if story['state'] in ('done','cancelled','draft') or task['state']=='running' or any(
                    (self.data.get(k) or {}).get('story')==story['id'] for k in ('active','preparing')):
                raise ValueError('Không thể đổi người nhận trong khi Story đang chạy hoặc đã kết thúc.')
            profile = self.agents.get(role)
            if profile['access']!='write' or profile['specialty']!=self.agents.get(old)['specialty']:
                raise ValueError('Agent cần quyền sửa code và chuyên môn phù hợp với bước được giao.')
            issue = self.api.issue(task_id)
            if issue['project']['id']!=self.project or issue['status'].get('is_closed'):
                raise ValueError('Task nằm ngoài dự án hoặc đã đóng.')
            member = self.assignee(role)
            self.api.update(task_id, assigned_to_id=member)
            if self.api.issue(task_id).get('assigned_to',{}).get('id')!=member:
                raise RuntimeError('Redmine chưa xác nhận người nhận task; chưa đổi workflow.')
            flow[flow.index(old)] = role
            story['workflow'] = flow
            if old!=role:
                story['tasks'][role] = story['tasks'].pop(old)
            if story.get('repair_role')==old:
                story['repair_role']=role
            if story.get('owner_role')==old:
                story['owner_role']=role
            self.save()
            waiting = flow[story['stage']:flow.index(role)]
            reasons = []
            if waiting:
                reasons.append('chờ bàn giao từ '+', '.join(self.labels[r] for r in waiting))
            if self.data.get('paused'):
                reasons.append('dự án đang tạm dừng; nhắn PM “tiếp tục dự án” để chạy các bước theo thứ tự')
            if story['state']=='attention':
                reasons.append('Story cần xử lý lỗi: '+story.get('error','chưa có chẩn đoán'))
            reply = f'Đã giao Task #{task_id} trong Story #{story.get("parent_story",story["id"])} cho {self.labels[role]}.'
            reply += (' Đang '+ '; '.join(reasons)+'.') if reasons else ' Task đã vào hàng đợi thực thi của bộ điều phối.'
            self.message('pm',role,reply,story['id'],task_id)
            return reply

    def pm(self, row):
        with self.lock:
            row.update(state='running')
            self.save()
        try:
            role = row.get('role', 'pm')
            if role != 'pm':
                task_id = direct_task_request(row['message'])
                if task_id is not None:
                    reply = self.assign_existing_task(role,task_id)
                    row.update(state='done',reply=reply)
                    self.message(role,'human',reply)
                    self.save()
                    return
                result = self.consult(role, self.repo, {
                    'message': row['message'], 'brief': self.data['brief'],
                    'identity': self.agents.get(role),
                    'stories': [s for s in self.data['stories'] if role in s['tasks']],
                    'chat_id':row['id'], 'recent_conversation': [m for m in self.data['messages']
                                            if role in (m['sender'], m['recipient'])][-16:],
                    'instruction': 'Trả lời trực tiếp người điều hành bằng tiếng Việt. Chỉ nhận công việc và kết quả gắn đúng ID identity là của mình; không nhận lịch sử agent khác cùng chuyên môn. Đây là hội thoại. '
                                   'Nếu được giao triển khai, giải thích phần cần PM điều phối. '
                                   'Không tuyên bố đã tạo task hoặc sửa code trong lượt hội thoại.',
                }, allow_paused=True, read_only=True)
                notices=self.process_agent_requests(role,result,chat_id=row['id'])
                row.update(state='done', reply=result['summary']+('\n\n'+'\n'.join(notices) if notices else ''))
                self.message(role, 'human', result['summary'])
                self.save()
                return
            work_request = dispatch_context(row,self.data['chat'][-12:])
            dispatch = work_request is not None
            from issue_catalog import project_issues, planning_catalog
            catalog = planning_catalog(project_issues(self.api, self.project), row['message'])
            # PM questions may still be answered while a project is paused.
            pm_context = {'message': row['message'], 'brief':self.data['brief'],
                'stories': self.data['stories'], 'recent_chat': self.data['chat'][-8:],
                'office_capabilities': PM_TASK_CAPABILITIES,
                'available_agents': [a for a in self.agents.listing() if a['id'] in self.ready_agents],
                'projects': self.manager.listing() if self.manager else [self.project_config],
                'redmine_catalog': catalog,
                'work_request': work_request,
                'planning': 'Chọn action theo ý định mới nhất của người điều hành và lịch sử. '
                            'Câu hỏi kiến thức, khả năng hoặc tiến độ: answer, stories rỗng. '
                            'Yêu cầu xây một dự án mới từ đề bài: start_project, title=tên dự án, '
                            'description=đề bài đầy đủ, repo_slug=tên ngắn chữ thường-số-gạch ngang, '
                            'visibility=private mặc định hoặc public nếu được yêu cầu. '
                            'Chia 3–12 Story theo phân hệ module, depends_on chứa chỉ số Story phụ thuộc '
                            '(đếm từ 0), nền tảng trước tính năng phụ thuộc. '
                            'Chỉ khi người dùng giao đề bài mới thực hiện start_project. '
                            'Yêu cầu chuyển dự án: switch_project với repo_slug là identifier trong projects. '
                            'Đối chiếu redmine_catalog và search_issues trước khi tạo việc. '
                            'Ưu tiên Story hiện có kể cả đã Done cho chỉnh sửa thuộc nghiệp vụ đó. '
                            'Task đang mở làm đúng yêu cầu thì trỏ đến task đó, không tạo trùng. '
                            'Nếu có nhiều Story liên quan, chọn bản đang xử lý cùng nghiệp vụ hoặc bản thay đổi gần nhất; '
                            'không chọn kế hoạch đã Rejected/cancelled. '
                            'Yêu cầu thêm task vào Story cụ thể, sửa chữ, CSS, lỗi nhỏ thuộc một vai trò: '
                            'create_task, target_id Story cha, assignee là id agent phù hợp trong available_agents (không dùng tên hiển thị), '
                            'đúng một stories mô tả task và tiêu chí. Chỉ tạo task cho vai trò cần thiết. '
                            'Yêu cầu chức năng độc lập, thay đổi lớn: create_story và đúng một stories '
                            'với tiêu đề ngắn và tiêu chí nghiệm thu kiểm chứng được; target_id là Story/Task liên quan hoặc 0. '
                            'Yêu cầu làm tiếp/chạy lại task đã có: resume và target_id đúng issue, 0 nếu toàn dự án. '
                            'Yêu cầu dừng dự án: pause. Sửa thông tin Redmine: update_issue. '
                            'Điền title/description/assignee/due_date chỉ khi người dùng yêu cầu; chuỗi rỗng là giữ nguyên. '
                            'Ngày hạn dạng YYYY-MM-DD. Chưa xác định issue thì hỏi rõ bằng answer. '
                            'Không nói đã thực thi trước khi bộ điều phối trả kết quả. '
                            'Khi người dùng xác nhận đề xuất trước, dùng nội dung đề xuất làm yêu cầu.'}
            result = self.consult('pm', self.repo, pm_context, allow_paused=self.stop.is_set())
            explicitly_child = re.search(r'\btask\b.*\bstory\s*#?\s*\d+', normalize(row['message']))
            if explicitly_child and result.get('action',{}).get('type') == 'create_story':
                result = self.consult('pm', self.repo, {
                    **pm_context, 'correction': 'Người điều hành chỉ định thêm task vào Story hiện có. '
                    'Tra cứu cha và task trùng. Chọn create_task hoặc answer/resume nếu task đã có. '
                    'Không tạo Story mới.', 'rejected_plan':result,
                }, allow_paused=self.stop.is_set())
                if result.get('action',{}).get('type') == 'create_story':
                    raise ValueError('PM chưa xác định đúng task con trong Story được yêu cầu.')
            if result.get('action'):
                row['decision'] = result['action']
                row.update(state='done', reply=self.execute_pm_action(row, result))
                notices=self.process_agent_requests('pm',result,chat_id=row['id'])
                if notices:row['reply']+='\n\n'+'\n'.join(notices)
            elif dispatch and result['stories'] and result['outcome']=='passed':
                if len(result['stories']) != 1:
                    raise ValueError('PM cần một Story cho mỗi lệnh giao việc.')
                row.update(state='done',reply=self.dispatch_story({'message':work_request},result['stories'][0]))
            elif dispatch:
                row.update(state='failed',reply='Chưa tạo task trên Redmine. '+result['summary'])
            elif (result['stories'] and result['outcome']=='passed' and not self.data['stories']
                  and not dispatch and normalize(row['message']).startswith(('bat dau du an','khoi dong du an'))):
                self.check_stop()
                self.data['brief'] = row['message']
                self.save()
                for item in result['stories'][:12]:
                    self.check_stop()
                    issue = self.create_issue(item['title'], 4, STATUS['backlog'], item['acceptance'])
                    with self.lock:
                        self.data['stories'].append(dict(id=issue, title=item['title'], acceptance=item['acceptance'],
                            state='queued', stage=0, tasks={}, results={}, repairs=0, repair_role=''))
                        self.save()
                self.message('pm','sa','Đã lập kế hoạch. Phân tích kiến trúc cho Story nền tảng.',
                             self.data['stories'][0]['id'])
                row.update(state='done', reply=result['summary'])
            else:
                row.update(state='done', reply=result['summary'])
        except Exception as exc:
            row.update(state='failed', reply=str(exc))
        self.save()
        if self.manager:
            self.manager.mirror_result(self,row)

    def action_target(self, issue_id):
        issue = self.api.issue(issue_id)
        if issue['project']['id'] != self.project:
            raise ValueError('Issue nằm ngoài dự án đang điều hành.')
        parent = issue.get('parent', {}).get('id', issue_id)
        story = next((s for s in self.data['stories'] if s['id'] == issue_id), None)
        if story is None:
            story = next((s for s in self.data['stories'] if s['id'] == parent), None)
        return issue, story

    def execute_pm_action(self, row, result):
        action = result['action']
        kind = action['type']
        if kind == 'answer':
            return result['summary']
        from agent_settings import settings,allowed
        profile=self.agents.get('pm')
        policy=settings(profile)['collaboration']
        autonomy=policy['autonomy']
        if autonomy=='project':autonomy=self.project_config.get('agent_autonomy','suggest')
        targets=ROLES if kind in ('create_story','start_project') else [action['assignee']] if action.get('assignee') else []
        can_assign=all(allowed(profile,'assign',target,self.ready_agents) for target in targets)
        if not row.get('owner_approved') and kind!='pause' and (autonomy!='delegate' or not can_assign):
            identity='pm-'+hashlib.sha256(str(row['id']).encode()).hexdigest()[:24]
            requests=self.data.setdefault('agent_requests',[])
            if not any(r['id']==identity for r in requests):
                if sum(r['agent']=='pm' and r['state'] in ('pending','failed','waiting_source','executing')
                       for r in requests)>=policy['max_open_subtasks']:
                    raise ValueError('PM đã chạm giới hạn đề xuất đang mở.')
                requests.append(dict(id=identity,agent='pm',type='pm_action',state='pending',
                    title=action.get('title') or kind,instructions=result['summary'],at=time.time(),
                    pm_row={'id':row['id'],'message':row['message']},pm_result=copy.deepcopy(result)))
                self.save()
            return 'PM đã lập phương án. Mở Agents → PM → Đề xuất chờ duyệt để xác nhận thực hiện.'
        if result['outcome'] != 'passed':
            raise ValueError(result['summary'])
        if kind == 'start_project':
            if not self.manager:
                raise RuntimeError('Bộ quản lý dự án chưa khởi động.')
            return self.manager.create(self,row,result)
        if kind == 'switch_project':
            if not self.manager:
                raise RuntimeError('Bộ quản lý dự án chưa khởi động.')
            worker = self.manager.select(action['repo_slug'])
            return 'Đã chuyển sang dự án '+worker.project_config['name']
        target = action['target_id']
        issue, story = self.action_target(target) if target else (None, None)
        if kind == 'pause':
            self.stop.set()
            self.data['paused'] = True
            self.save()
            return 'Đã yêu cầu dừng dự án. Lượt đang chạy sẽ dừng và giữ phần đã lưu.'
        if kind == 'resume':
            if target and story is None:
                raise ValueError('Issue chưa nằm trong kế hoạch của bộ điều phối.')
            selected = [story] if story else self.data['stories']
            if story and story['state'] == 'done':
                return f'Story #{story["id"]} đã hoàn thành. Muốn thay đổi chức năng, hãy nêu nội dung cần sửa.'
            self.data['paused'] = False
            self.stop.clear()
            resumed = []
            for item in selected:
                if item['state'] == 'attention':
                    item.update(state='queued', error='')
                    item.pop('retry_at', None)
                    resumed.append(item['id'])
                    self.message('pm', 'devops', 'Đã đưa vào hàng chạy lại theo yêu cầu người điều hành.', item['id'])
            self.save()
            return ('Đã cho phép tiếp tục dự án. ' +
                    ('Story được chạy lại: ' + ', '.join(f'#{key}' for key in resumed)
                     if resumed else 'Các lượt đang chạy hoặc đang chờ sẽ tiếp tục theo kế hoạch.'))
        if kind == 'create_story':
            if len(result['stories']) != 1:
                raise ValueError('Mỗi yêu cầu thay đổi cần đúng một Story với tiêu chí nghiệm thu.')
            plan = dict(result['stories'][0])
            if issue:
                plan['acceptance'] += f'\n\nYêu cầu thay đổi liên quan Redmine #{target}: {issue["subject"]}.'
                if story:
                    plan['acceptance'] += '\nGiữ các tiêu chí hiện có trừ nội dung được yêu cầu đổi:\n' + story['acceptance']
            return self.dispatch_story(row, plan)
        if kind == 'create_task':
            if not story:
                if issue:
                    parent_id = issue.get('parent',{}).get('id',issue['id'])
                    parent = self.api.issue(parent_id)
                    if parent['project']['id']==self.project and parent['tracker']['id']==4:
                        story = {'id':parent_id}
                if not story:
                    raise ValueError('Cần xác định Story cha đang có trong dự án.')
            if len(result['stories']) != 1:
                raise ValueError('Cần một task với tiêu chí nghiệm thu cụ thể.')
            role = action['assignee']
            if role not in self.ready_agents or role in ('pm','reviewer','tester'):
                raise ValueError('Chưa xác định được vai trò thực hiện task.')
            return self.dispatch_task(row, story, result['stories'][0], role)
        if kind == 'update_issue':
            if not issue:
                raise ValueError('Cần xác định mã issue để cập nhật.')
            fields = {}
            for source, destination in [('title', 'subject'), ('description', 'description'), ('due_date', 'due_date')]:
                if action[source]:
                    fields[destination] = action[source]
            if 'due_date' in fields:
                from datetime import date
                date.fromisoformat(fields['due_date'])
            if action['assignee']:
                fields['assigned_to_id'] = self.assignee(action['assignee'])
            if not fields:
                raise ValueError('Chưa có nội dung cần cập nhật.')
            self.api.update(target, **fields)
            updated = self.api.issue(target)
            for key, value in fields.items():
                actual = updated.get('assigned_to', {}).get('id') if key == 'assigned_to_id' else updated.get(key)
                if actual != value:
                    raise RuntimeError(f'Chưa xác minh được trường {key} sau khi cập nhật issue #{target}.')
            if story and story['id'] == target and 'subject' in fields:
                story['title'] = fields['subject']
            self.save()
            return f'Đã cập nhật issue #{target}: http://localhost:3000/issues/{target}'
        raise ValueError('PM trả về thao tác chưa được hỗ trợ.')

    def dispatch_task(self, row, parent, plan, role):
        marker = f'[Lending PM task request: {row["id"]}]'
        parent_id = parent.get('parent_story', parent['id'])
        current_parent = self.api.issue(parent_id)
        if current_parent['project']['id'] != self.project:
            raise ValueError('Story cha nằm ngoài dự án.')
        title = plan['title'].strip()
        acceptance = plan['acceptance'].strip()
        if not title or not acceptance:
            raise ValueError('Task cần tên ngắn gọn và tiêu chí nghiệm thu.')
        member = {'id':self.assignee(role)}
        existing = next((s for s in self.data['stories'] if s.get('task_request')==row['id']),None)
        if existing:
            return f'Task đã được giao: http://localhost:3000/issues/{existing["id"]}'
        children = current_parent.get('children',[])
        task_id = None
        for child in children:
            if marker in (self.api.issue(child['id']).get('description') or ''):
                task_id = child['id']
                break
        if current_parent['status'].get('is_closed'):
            self.api.update(parent_id,status_id=STATUS['progress'])
            if self.api.issue(parent_id)['status']['is_closed']:
                raise RuntimeError(f'Workflow Redmine chưa cho mở lại Story #{parent_id}.')
        if task_id is None:
            task_id = self.create_issue(
                f'{self.labels[role]}: {title}', 5, STATUS['todo'], acceptance+'\n\n'+marker,
                parent_id, assignee=member['id'])
        self.api.update(parent_id,status_id=STATUS['progress'])
        profile = self.agents.get(role)
        advisory = not profile['builtin'] and profile['access']=='read'
        workflow = [role] if advisory else list(dict.fromkeys([role, 'reviewer', 'tester']))
        work = dict(id=task_id,title=title,acceptance=acceptance,kind='task',parent_story=parent_id,
                    workflow=workflow,advisory=advisory,owner_role=role,task_request=row['id'],state='queued',stage=0,
                    tasks={item:dict(id=task_id,state='queued') for item in workflow},
                    results={},repairs=0,repair_role='')
        with self.lock:
            self.data['stories'].append(work)
            self.save()
        self.message('pm',role,acceptance,parent_id,task_id)
        return f'Đã tạo Task #{task_id} trong Story #{parent_id}, giao {self.labels[role]}.\nhttp://localhost:3000/issues/{task_id}'

    def dispatch_story(self, row, plan):
        title, acceptance = plan['title'].strip(), plan['acceptance'].strip()
        if not title or not acceptance:
            raise ValueError('PM chưa xác định được phạm vi và tiêu chí nghiệm thu.')
        request_key = hashlib.sha256((str(row.get('id','')) + ':' + normalize(row['message'])).encode()).hexdigest()[:24]
        marker = f'[Lending PM request: {request_key}]'
        story = next((s for s in self.data['stories'] if s.get('request_key')==request_key),None)
        if story and story['state'] != 'draft':
            return f'Đầu việc này đã có trên Redmine: Story #{story["id"]} · http://localhost:3000/issues/{story["id"]}'
        if story is None:
            page = self.api.request('GET','/issues.json?'+urlencode(dict(
                project_id=self.project,tracker_id=4,status_id='*',subject=title[:230],limit=100)))
            existing=next((i for i in page['issues'] if marker in (i.get('description') or '')),None)
            key = existing['id'] if existing else self.create_issue(
                title,4,STATUS['backlog'],acceptance+'\n\n'+marker)
            story = dict(id=key,title=title,acceptance=acceptance,state='draft',stage=0,
                         tasks={},results={},repairs=0,repair_role='',request_key=request_key)
            with self.lock:
                self.data['stories'].append(story)
                self.save()

        children = {child['subject']:child['id'] for child in self.api.issue(story['id']).get('children',[])}
        for role in ROLES:
            if role in story['tasks']:
                continue
            name = f'{self.labels[role]}: {self.task_names[role]} · {story["title"]}'[:230]
            assignee = self.assignee(role)
            if not assignee:
                raise RuntimeError(f'Chưa tìm thấy thành viên Redmine cho vai trò {self.labels[role]}.')
            task_id = children.get(name) or self.create_issue(
                name,5,STATUS['todo'],f'{self.task_names[role]}.\n\n{story["acceptance"]}',
                story['id'],assignee=assignee)
            story['tasks'][role] = {'id':task_id,'state':'queued'}
            self.save()
        story['state']='queued'
        self.message('pm','sa','Đã lên lịch phân tích: '+story['title'],story['id'],story['tasks']['sa']['id'])
        links = '\n'.join(f'{self.labels[role]}: http://localhost:3000/issues/{task["id"]}'
                          for role,task in story['tasks'].items())
        queue_status = 'Dự án đang tạm dừng. Task sẽ chạy khi bạn nhắn “Tiếp tục dự án”.' if self.data['paused'] else 'Đã đưa vào hàng chạy. SA nhận việc đầu tiên khi đến lượt.'
        return f'Đã tạo Story #{story["id"]}: {story["title"]}\nhttp://localhost:3000/issues/{story["id"]}\n\n{links}\n\n{queue_status}'

    def create_issue(self, title, tracker, status, description, parent=None, *, assignee=None):
        fields = dict(project_id=self.project, tracker_id=tracker, status_id=status, subject=title[:230], description=description)
        if parent:
            fields['parent_issue_id'] = parent
        if assignee:
            fields['assigned_to_id'] = assignee
        issue = self.api.request('POST','/issues.json',{'issue':fields})['issue']
        return issue['id']

    def story_progress(self, story_id):
        story = self.api.issue(story_id)
        if story['project']['id'] != self.project or story['tracker']['id'] not in (4,5):
            raise ValueError('Story ngoài dự án.')

        def summarize(issue):
            return {'id': issue['id'], 'subject': issue['subject'],
                    'status': issue['status']['name'], 'closed': issue['status']['is_closed'],
                    'progress': issue['done_ratio'],
                    'start_date':issue.get('start_date'), 'due_date':issue.get('due_date'),
                    'assignee':issue.get('assigned_to',{}).get('name'),
                    'attachments': [{'id': a['id'], 'filename': a['filename']}
                                    for a in issue.get('attachments', [])]}

        with ThreadPoolExecutor(max_workers=4) as pool:
            children = list(pool.map(self.api.issue, (c['id'] for c in story.get('children', []))))
        return {'story': summarize(story), 'tasks': [summarize(c) for c in children if c['project']['id'] == self.project]}

    def task_board(self):
        tasks = []
        offset = 0
        while True:
            query = urlencode(dict(project_id=self.project, status_id='*', limit=100, offset=offset))
            page = self.api.request('GET','/issues.json?'+query)
            issues = page['issues']
            tasks.extend({'id':i['id'], 'subject':i['subject'], 'status':i['status']['name'],
                          'progress':i['done_ratio'], 'story_id':i.get('parent',{}).get('id'),
                          'start_date':i.get('start_date'), 'due_date':i.get('due_date'),
                          'assignee':i.get('assigned_to',{}).get('name'),
                          'closed':i['status'].get('is_closed', False) or i.get('closed_on') is not None}
                         for i in issues if i.get('parent'))
            offset += len(issues)
            if not issues or offset >= page['total_count']:
                return tasks

    def repo_for(self, story):
        path = self.runtime / f'story-{story["id"]}'
        branch = f'ai/story-{story["id"]}'
        if git(self.repo,'remote','get-url','origin').removesuffix('.git') != 'https://github.com/'+self.repository:
            raise RuntimeError('Origin của repo sản phẩm không đúng.')
        if not path.exists():
            refs = git(self.repo,'ls-remote','origin','refs/heads/main')
            if not refs:
                if not git(self.repo,'rev-list','--all','--max-count=1'):
                    git(self.repo,'-c','user.name=Lending AI','-c','user.email=lending-ai@localhost',
                        'commit','--allow-empty','-m','Initialize empty main for the AI team')
                if git(self.repo,'ls-tree','--name-only','HEAD'):
                    raise RuntimeError('Checkout gốc có code. Không dùng nó để khởi tạo main.')
                self.check_stop()
                git(self.repo,'push','origin','HEAD:refs/heads/main')
            git(self.repo,'fetch','origin','main')
            git(self.repo,'worktree','add','-b',branch,str(path),'origin/main')
        if git(path,'branch','--show-current') != branch:
            raise RuntimeError('Sai nhánh Story.')
        return path

    def task(self, story, role):
        if role not in story['tasks']:
            key = story['id']
            topic = TASK_TOPICS.get(key)
            title = f'{self.labels[role]}: {self.task_names[role]}' + (f' · {topic}' if topic else '')
            issue = self.create_issue(title,5,STATUS['todo'],story['acceptance'],key,assignee=self.assignee(role))
            story['tasks'][role] = dict(id=issue, state='queued')
            self.save()
        return story['tasks'][role]

    def artifact(self, story, role, result, cwd, issue):
        # Reuse the existing Redmine artifact validation and upload implementation.
        class Uploads:
            api = self.api
            def checkout(self, job):
                return cwd
        report = {'evidence':result['summary'], 'artifacts':result['artifacts']}
        report_path = None
        if not report['artifacts']:
            report_path = cwd / 'docs' / 'ai' / str(story['id']) / (role + '.md')
            if report_path.exists():
                raise RuntimeError('Đường dẫn báo cáo trùng với tệp có sẵn.')
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(result['summary'], encoding='utf-8')
            report['artifacts'] = [report_path.relative_to(cwd).as_posix()]
        try:
            uploads = Service.product_uploads(Uploads(), story, role, report, result, self.api.issue(issue),
                                             approved_workflow=CI_CONTENT.encode('utf-8'))
        finally:
            if report_path:
                report_path.unlink()
        self.api.update(issue, status_id=STATUS['child_review'], done_ratio=100,
                        notes=f'[{self.labels[role]}] {result["summary"]}', uploads=uploads)

    def fingerprint(self, cwd):
        digest = hashlib.sha256(git(cwd,'rev-parse','HEAD').encode())
        for name in safe_files(cwd):
            path = cwd / name
            digest.update(json.dumps(name).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b'<deleted>')
        return digest.hexdigest()

    def verify_preparation(self, cwd, key):
        pattern = rf'(?:docs/ai/[\w/-]+|story-{key}-[\w.-]+)\.(?:md|html|css|svg)'
        if any(not re.fullmatch(pattern, name) for name in safe_files(cwd)):
            raise RuntimeError('Chuẩn bị trước chỉ được thay đổi tài liệu hoặc prototype.')

    def step(self, story, *, preparation=False):
        self.check_stop()
        key = story['id']
        flow = story.get('workflow', ROLES)
        if story['stage']<len(flow):
            next_role = story.get('repair_role') or flow[story['stage']]
            if next_role not in self.ready_agents:
                raise ValueError('Agent đang tạm dừng hoặc chưa sẵn sàng: '+self.labels[next_role])
        current = self.api.issue(key)
        if current['project']['id'] != self.project or current['status']['id'] == 9:
            raise RuntimeError('Story ngoài dự án hoặc đã Blocked trên Redmine.')
        if current['status']['id'] == STATUS['backlog']:
            self.api.update(key,status_id=STATUS['selected'])
        cwd = self.repo_for(story)
        if not preparation and story.get('prepared_ahead') and story['stage'] == ROLES.index('backend'):
            # Refresh the implementation branch after the preceding Story has merged.
            if not story.get('implementation_started'):
                self.verify_preparation(cwd,key)
            git(cwd,'fetch','origin','main')
            git(cwd,'merge','--ff-only','origin/main')
            story['implementation_started'] = True
        if story['stage'] == len(flow):
            if story.get('advisory'):
                self.api.update(key,status_id=STATUS['done'],done_ratio=100)
                if not self.api.issue(key)['status']['is_closed']:
                    raise RuntimeError('Redmine chưa đóng task chuyên môn.')
                story['state']='done'
                for item in story['tasks'].values(): item['state']='done'
                parent = self.api.issue(story['parent_story'])
                if all(self.api.issue(child['id'])['status']['is_closed'] for child in parent.get('children',[])):
                    self.api.update(parent['id'],status_id=STATUS['done'],done_ratio=100)
                self.message(story['owner_role'],'pm','Đã bàn giao kết quả chuyên môn, không thay đổi mã nguồn.',key,key)
                return
            return self.publish(story,cwd)
        role = story['repair_role'] or flow[story['stage']]
        if role not in self.ready_agents:
            raise ValueError('Agent đang tạm dừng hoặc chưa sẵn sàng: '+self.labels[role])
        task = self.task(story,role)
        if story.get('kind') != 'task' and role == 'tester' and current['status']['id'] != STATUS['testing']:
            self.api.update(key,status_id=STATUS['ready'])
        if story.get('kind') != 'task':
            self.api.update(key,status_id=STATUS['review'] if role=='reviewer' else
                            STATUS['testing'] if role=='tester' else STATUS['progress'])
        self.api.update(task['id'],status_id=STATUS['progress'],done_ratio=0)
        task['state']='running'
        if preparation:
            story['prepared_ahead'] = True
        slot = 'preparing' if preparation else 'active'
        self.data[slot] = dict(story=key, role=role, task=task['id'])
        self.message('pm',role,f'{self.task_names[role]}. Story: {story["title"]}. Tiêu chí: {story["acceptance"]}',key,task['id'])
        if role == 'devops':
            workflow = cwd / CI_PATH
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(CI_CONTENT, encoding='utf-8')
        verified = self.fingerprint(cwd) if role in ('reviewer','tester') else None
        read_fingerprint = self.fingerprint(cwd) if self.agents.get(role)['access']=='read' else None
        if role=='tester' and story.get('reviewed')!=verified:
            raise RuntimeError('Code đã đổi sau review. Cần review lại.')
        context = {'brief':self.data['brief'],'story':story,'task':task['id']}
        specialty = self.agents.get(role)['specialty']
        context['project'] = self.project_config
        sql_evidence = None
        if specialty in ('frontend','devops','tester') and (cwd/'backend/test/sqlserver.test.js').is_file():
            from sqlserver_check import verify
            sql_evidence = verify(self,cwd,self.runtime,key)
            context['host_sql_test'] = sql_evidence
            if role=='tester' and sql_evidence['passed']:
                self.api.update(task['id'],done_ratio=30)
            context['sql_instructions'] = (
                'Bộ điều phối đã chạy SQL Server ngoài sandbox trên đúng checkout. '
                'Dùng kết quả này cho phần SQL; đừng chạy ODBC lại trong sandbox. '
                'Nếu bài test thất bại, đọc kết quả để phân loại lỗi và giao đúng vai trò sửa. '
                'Vẫn kiểm tra các tiêu chí khác của task.')
        feature = story.get('parent_story', key)
        if specialty in ('frontend', 'devops', 'tester') and feature in (166, 176):
            from browser_check import verify as verify_browser
            context['host_browser_test'] = verify_browser(self, cwd, self.runtime, key, minimum=8 if feature==176 else 12)
            context['browser_instructions'] = (
                'Bộ điều phối đã chạy Chrome/Edge ngoài sandbox với profile riêng trên đúng checkout. '
                'Đọc log và ảnh trong host_browser_test. Dùng bằng chứng này cho các ca đã chạy, '
                'không lặp lại lệnh Chrome bị từ chối quyền trong sandbox. '
                'Bài trình duyệt gọi backend thật và SQL Server thật trong schema kiểm thử riêng. '
                'Không cần Caddy cho bài localhost này. '
                'Đối chiếu tiêu chí còn thiếu trước khi kết luận.')
        if preparation:
            context['scope'] = ('Chuẩn bị trước. Chỉ viết tài liệu hoặc prototype độc lập; '
                                'lưu dưới docs/ai/ hoặc đặt tên story-ID-*.md/html/css/svg ở thư mục gốc. Không sửa mã ứng dụng, phụ thuộc hay cấu hình. Nếu cần kết quả Story trước, báo phụ thuộc.')
        if story.get('kind') == 'task':
            context['scope'] = ('Đây là task nhỏ trong Story hiện có. Chỉ thực hiện tiêu chí task này. '
                                'Không thiết kế lại hệ thống hoặc mở rộng nghiệp vụ. '
                                'REVIEW và TESTER kiểm tra trên cùng task, không tạo đầu việc cho cả đội.')
        result = self.consult(role,cwd,context,
                              story=key,task=task['id'])
        self.check_stop()
        if read_fingerprint and read_fingerprint!=self.fingerprint(cwd):
            raise RuntimeError('Agent chỉ đọc đã làm thay đổi code. Cần kiểm tra lại checkout.')
        if specialty=='backend' and result['outcome']=='blocked' and (cwd/'backend/test/sqlserver.test.js').is_file():
            reason = result['summary'].casefold()
            if any(marker in reason for marker in ('odbc','msnodesqlv8','test_database_url','sqlcmd')):
                from sqlserver_check import verify
                sql_evidence = verify(self,cwd,self.runtime,key)
                result = self.consult(role,cwd,{**context,'prior_result':result,'host_sql_test':sql_evidence,
                    'sql_instructions':'Dùng kết quả SQL Server do bộ điều phối chạy. Không chạy lại ODBC trong sandbox. '
                    'Kiểm tra các phần còn thiếu và bàn giao nếu đạt.'},story=key,task=task['id'])
        if sql_evidence and result['outcome']=='passed':
            if sql_evidence['fingerprint']!=self.fingerprint(cwd):
                from sqlserver_check import verify
                sql_evidence = verify(self,cwd,self.runtime,key)
            if not sql_evidence['passed']:
                raise RuntimeError('Kiểm thử SQL Server chưa đạt. Xem ' + sql_evidence['log'])
            result['summary'] += '\n\nSQL Server trên máy: đạt. Nhật ký: ' + sql_evidence['log']
        if verified and verified!=self.fingerprint(cwd):
            raise RuntimeError('Code thay đổi trong lúc kiểm tra.')
        if result['outcome'] == 'needs_changes' and role in ('reviewer','tester'):
            fix = result['repair_role']
            fix = next((r for r in flow if self.agents.get(r)['specialty']==fix), fix)
            owner = story.get('owner_role')
            if owner and self.agents.get(owner)['specialty']==fix:
                fix = owner
            if fix not in flow or self.agents.get(fix)['specialty'] not in ('frontend','backend') or story['repairs'] >= 2:
                raise RuntimeError(result['summary'])
            bug = self.create_issue(f'{self.labels[role]}: {story["title"]}',1,STATUS['todo'],result['summary'],key)
            story.update(repairs=story['repairs']+1,repair_role=fix,stage=flow.index('reviewer'))
            story.setdefault('bugs',[]).append(bug)
            story['results'][role] = result
            task['state']='queued'
            self.api.update(task['id'],status_id=STATUS['todo'],notes=result['summary'])
            self.message(role,fix,result['summary'],key,bug)
            return
        if result['outcome'] != 'passed':
            raise RuntimeError(result['summary'])
        if preparation:
            self.verify_preparation(cwd,key)
        if specialty in ('sa','ba','frontend','backend') and not result['artifacts']:
            raise RuntimeError(f'{self.labels[role]} chưa cung cấp tệp bàn giao.')
        # A completed role report is a milestone. Redmine reaches 100 only after upload.
        self.api.update(task['id'],done_ratio=80)
        self.artifact(story,role,result,cwd,task['id'])
        if verified:
            story['reviewed' if role=='reviewer' else 'tested']=verified
        self.process_agent_requests(role,result,work=story)
        story['results'][role] = result
        task['state']='delivered'
        if story['repair_role']:
            story['repair_role']=''
        else:
            story['stage']+=1
        recipient = flow[story['stage']] if story['stage'] < len(flow) else 'devops'
        self.message(role,recipient,result['summary'],key,task['id'])

    def publish(self, story, cwd):
        self.check_stop()
        gh = GitHub(self.repository)
        key = story['id']
        issue_label = 'Task' if story.get('kind') == 'task' else 'Story'
        branch=f'ai/story-{key}'
        if 'pr' not in story:
            if not story.get('tested') or story['tested']!=story.get('reviewed'):
                raise RuntimeError('REVIEW và TESTER chưa kiểm tra cùng một bản code.')
            if not story.get('commit'):
                if story['tested']!=self.fingerprint(cwd):
                    raise RuntimeError('Code đã đổi sau kiểm thử.')
            if (cwd/CI_PATH).read_text(encoding='utf-8') != CI_CONTENT:
                raise RuntimeError('Cấu hình kiểm tra CI đã thay đổi. Cần kiểm tra lại.')
            if git(cwd,'diff','--cached','--name-only'):
                raise RuntimeError('Có thay đổi đã stage ngoài dịch vụ.')
            paths = safe_files(cwd)
            if paths:
                git(cwd,'add','--',*paths)
                git(cwd,'-c','user.name=Lending AI','-c','user.email=lending-ai@localhost','commit','-m',f'{issue_label} #{key}: {story["title"]}')
            sha=git(cwd,'rev-parse','HEAD')
            if story.get('commit') and (story['commit']!=sha or paths):
                raise RuntimeError('Nhánh đã đổi sau khi chuẩn bị xuất bản.')
            story['commit']=sha
            self.save()
            self.check_stop()
            git(cwd,'push','origin','HEAD:refs/heads/'+branch)
            prs=gh.request('/pulls?'+urlencode({'state':'open','head':self.repository.split('/')[0]+':'+branch,'base':'main'}))
            pr=prs[0] if prs else gh.request('/pulls','POST',{'title':f'{issue_label} #{key}: {story["title"]}', 'head':branch,'base':'main',
                'body':f'Redmine {issue_label} #{key}. REVIEW and TESTER handoffs are attached in Redmine.'})
            story['pr']=dict(number=pr['number'],url=pr['html_url'],sha=sha,started=time.time())
            self.message('devops','pm','Đã mở PR, đang chờ CI: '+pr['html_url'],key)
            return
        pr=story['pr']
        number=pr['number']
        remote=gh.request(f'/pulls/{number}')
        if remote['head']['sha']!=pr['sha'] or remote['base']['ref']!='main':
            raise RuntimeError('PR đã đổi commit hoặc nhánh đích. Cần review lại.')
        if not remote.get('merged'):
            checks=gh.request('/commits/'+pr['sha']+'/check-runs').get('check_runs',[])
            check=next((x for x in checks if x['name']==CI_NAME and x.get('app',{}).get('slug')=='github-actions'),None)
            if not check or check['status']!='completed':
                if time.time()-pr['started']>1800:
                    raise RuntimeError('CI chưa chạy xong sau 30 phút.')
                return
            if check['conclusion']!='success':
                raise RuntimeError('CI chưa đạt: '+str(check.get('html_url')))
            self.check_stop()
            merge=gh.request(f'/pulls/{number}/merge','PUT',{'sha':pr['sha'],'merge_method':'merge'})
            if not merge.get('merged'):
                raise RuntimeError('GitHub chưa merge PR.')
        for task in story['tasks'].values():
            self.api.update(task['id'],status_id=STATUS['done'])
            if not self.api.issue(task['id'])['status']['is_closed']:
                raise RuntimeError(f'Redmine chưa đóng Task #{task["id"]}.')
            task['state']='done'
        for bug in story.get('bugs',[]):
            self.api.update(bug,status_id=5,done_ratio=100)  # Bug tracker uses Closed.
            if not self.api.issue(bug)['status']['is_closed']:
                raise RuntimeError(f'Redmine chưa đóng Bug #{bug}.')
        self.api.update(key,status_id=STATUS['done'],done_ratio=100,notes=f'[DEVOPS] Đã merge {pr["url"]}')
        if self.api.issue(key)['status']['id'] != STATUS['done']:
            raise RuntimeError(f'Redmine chưa chuyển Story #{key} sang Done.')
        story['state']='done'
        if story.get('parent_story'):
            parent = self.api.issue(story['parent_story'])
            if all(self.api.issue(child['id'])['status']['is_closed'] for child in parent.get('children',[])):
                self.api.update(parent['id'], status_id=STATUS['done'], done_ratio=100,
                                notes=f'Task #{key} đã kiểm tra và merge: {pr["url"]}')
        self.message('devops','pm','Đã merge sau khi REVIEW, TESTER và CI đạt: '+pr['url'],key)

    def run_step(self, story, *, preparation=False):
        try:
            story['state']='running'
            self.step(story, preparation=preparation)
            if story['state']=='running':
                story['state']='queued'
        except InterruptedError:
            story['state']='queued'
        except Exception as exc:
            story.update(state='attention',error=str(exc))
            stage = str(story['stage']) + ':' + story.get('repair_role', '')
            attempts = story.setdefault('automatic_retries', {})
            count = attempts.get(stage, 0)
            if isinstance(exc, (TimeoutError, ConnectionError)) and count < 2:
                attempts[stage] = count + 1
                story['retry_at'] = time.time() + 30 * (count + 1)
                story['error'] += f' Tự thử lại lần {count + 1}/2 sau {30 * (count + 1)} giây.'
            self.message('pm','human',str(exc),story['id'])
        finally:
            self.data['preparing' if preparation else 'active']=None
            self.save()

    def run(self):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lending-prep')
        chat_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lending-chat')
        pm_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lending-pm')
        work_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lending-work')
        chat_pending = None
        pm_pending = None
        work_pending = None
        pending = None
        preparing = None
        while True:
            try:
                self.pump_agent_sync()
            except Exception:
                print('Chưa lên lịch được đồng bộ agent; sẽ thử lại.',flush=True)
            if not self.stop.is_set():
                for request in self.data.get('agent_requests',[]):
                    source=next((s for s in self.data['stories'] if s['id']==request.get('source_work')),None)
                    if request['state']=='waiting_source' and source and source['state']=='done':
                        try:self.execute_agent_request(request)
                        except Exception:
                            request.update(state='failed',error='Chưa thực hiện xong; có thể kiểm tra và duyệt lại.')
                            self.save()
            if not self.stop.is_set():
                for queued_story in self.data['stories']:
                    if queued_story.get('retry_at') and queued_story['retry_at'] <= time.time():
                        queued_story.pop('retry_at')
                        queued_story.update(state='queued', error='')
                        self.save()
            if chat_pending is None or chat_pending.done():
                question = next((c for c in self.data['chat']
                                 if c['state']=='queued' and c.get('role','pm')!='pm'
                                 and c.get('role') in self.ready_agents), None)
                if question:
                    chat_pending = chat_executor.submit(self.pm, question)
            row=next((c for c in self.data['chat'] if c['state']=='queued'
                      and c.get('role','pm')=='pm'),None)
            if row and (pm_pending is None or pm_pending.done()):
                pm_pending = pm_executor.submit(self.pm, row)
            if pending and pending.done():
                pending = preparing = None
            completed={s['id'] for s in self.data['stories'] if s['state']=='done'}
            remaining=[s for s in self.data['stories'] if s['state'] not in ('done','draft','cancelled')
                       and all(dep in completed for dep in s.get('depends_on',[]))]
            story=remaining[0] if remaining else None
            if not self.stop.is_set() and story:
                flow = story.get('workflow',ROLES)
                role_available = story['stage']>=len(flow) or (story.get('repair_role') or flow[story['stage']]) in self.ready_agents
                if pending is None:
                    # Start future design only once implementation has begun on the leading Story.
                    future=next((s for s in remaining[1:] if s['stage']<2 and s['state']=='queued'
                                 and s['id'] in TASK_TOPICS),None)
                    if future and story['stage']>=2 and (self.runtime / f'story-{story["id"]}').exists():
                        preparing=future
                        pending=executor.submit(self.run_step,future,preparation=True)
                if (story is not preparing and story['state']!='attention'
                        and role_available
                        and (not pending or story['stage']>=2)
                        and (work_pending is None or work_pending.done())):
                    work_pending = work_executor.submit(self.run_step, story)
            time.sleep(2 if not story or not story.get('pr') else 5)


def make_server(manager, port=8767):
    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,payload):
            body=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path
            if path == '/lending-api/projects':
                return self.respond(200,manager.listing())
            try:
                office = manager.office(parse_qs(url.query).get('project',[None])[0])
            except ValueError as exc:
                return self.respond(404,{'error':str(exc)})
            if path == '/lending-api/agents/options':
                from agent_settings import runtime_options
                return self.respond(200,{**runtime_options(),'skills':office.library.listing()})
            if path == '/lending-api/agents/tokens':
                from token_usage import TokenUsage
                return self.respond(200,TokenUsage(office.runtime).snapshot())
            if path == '/lending-api/agents/models':
                from agent_providers import gemini_models
                try:
                    return self.respond(200,gemini_models())
                except ValueError as exc:
                    return self.respond(400,{'error':str(exc)})
            if path == '/lending-api/agents/provider':
                from agent_providers import diagnostic
                try:
                    return self.respond(200,diagnostic(parse_qs(url.query).get('adapter',['codex'])[0]))
                except ValueError as exc:
                    return self.respond(400,{'error':str(exc)})
                except (OSError,subprocess.TimeoutExpired):
                    return self.respond(502,{'error':'CLI không phản hồi kiểm tra cài đặt. Chưa gọi model.'})
            if path == '/lending-api/agents':
                return self.respond(200,office.agents.listing())
            if path == '/lending-api/agents/history':
                key = parse_qs(url.query).get('id',[''])[0]
                return self.respond(200,office.agents.history(key))
            if path == '/lending-api/agents/members':
                try:
                    return self.respond(200,office.members())
                except Exception:
                    return self.respond(502,{'error':'Không đọc được thành viên Redmine.'})
            if path == '/lending-api/tasks':
                try:
                    return self.respond(200, office.task_board())
                except Exception:
                    return self.respond(502, {'error':'Không đọc được danh sách task từ Redmine.'})
            match = re.fullmatch(r'/lending-api/stories/(\d+)/progress', path)
            if match:
                story_id = int(match[1])
                with office.lock:
                    known = any(s['id'] == story_id for s in office.data['stories'])
                if not known:
                    return self.respond(404, {'error':'Không tìm thấy Story trong văn phòng.'})
                try:
                    return self.respond(200, office.story_progress(story_id))
                except ValueError as exc:
                    return self.respond(404, {'error':str(exc)})
                except Exception as exc:
                    print(f'Story progress #{story_id}: {exc}', flush=True)
                    return self.respond(502, {'error':'Không đọc được tiến độ từ Redmine.'})
            if path!='/lending-api/state':
                return self.respond(404,{'error':'Không tìm thấy'})
            with office.lock:
                self.respond(200,{**office.data,'agents':office.agents.listing(),
                                  'agent_management_version':4,
                                  'deleted_agents':office.agents.deleted_profiles(),'projects':manager.listing()})

        def do_POST(self):
            if self.path not in ('/lending-api/chat','/lending-api/projects/select','/lending-api/agents','/lending-api/agents/model-test','/lending-api/agents/runtime-test','/lending-api/agents/tokens'):
                return self.respond(404,{'error':'Không tìm thấy'})
            origins={'http://localhost:8766','http://127.0.0.1:8766'}
            if self.headers.get('Origin') not in origins or self.headers.get_content_type()!='application/json':
                return self.respond(403,{'error':'Chỉ nhận lệnh từ văn phòng trên máy này.'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=600000:
                    raise ValueError('Tin nhắn quá dài hoặc bị trống.')
                payload=json.loads(self.rfile.read(size))
                if self.path == '/lending-api/projects/select':
                    office=manager.select(payload.get('identifier'))
                    return self.respond(200,{'ok':True,'project':office.project_config['identifier']})
                office=manager.office(payload.get('project'))
                if self.path == '/lending-api/agents/tokens':
                    from token_usage import TokenUsage
                    office.agents.get(payload.get('agent'))
                    ledger=TokenUsage(office.runtime)
                    ledger.set_limit(payload.get('agent'),payload.get('limit'))
                    return self.respond(200,ledger.snapshot())
                if self.path == '/lending-api/agents/runtime-test':
                    from provider_runtime_check import verify_runtime
                    return self.respond(200,verify_runtime(payload,office.runtime/'provider-checks'))
                if self.path == '/lending-api/agents/model-test':
                    from agent_providers import gemini_models
                    if payload.get('adapter')!='gemini':raise ValueError('Nút thử này hiện dành cho model Gemini.')
                    return self.respond(200,gemini_models('probe',payload.get('model')))
                if self.path == '/lending-api/agents':
                    return self.respond(200,office.manage_agent(payload))
                message=payload.get('message')
                if not isinstance(message,str) or not 0<len(message.strip())<=6000:
                    raise ValueError('Tin nhắn phải từ 1 đến 6000 ký tự.')
                request_id = office.submit(message.strip(), payload.get('role', 'pm'))
                self.respond(202,{'ok':True,'id':request_id,'project':office.project_config['identifier']})
            except (ValueError,AttributeError) as exc:
                self.respond(400,{'error':str(exc)})
            except Exception as exc:
                print(f'Office request failed: {type(exc).__name__}',flush=True)
                self.respond(502,{'error':'Chưa xác nhận được kết quả. Kiểm tra danh sách agent/task trước khi thử lại.'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve():
    from projects import ProjectManager
    manager=ProjectManager(Office())
    server=make_server(manager)
    manager.start_worker(manager.default)
    print('Club Equipment Lending API: http://127.0.0.1:8767',flush=True)
    server.serve_forever()


if __name__ == '__main__':
    serve()
