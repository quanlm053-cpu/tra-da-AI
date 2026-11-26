"""Validated agent setup and project-local skill library."""
import copy
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

TOOLS = {
    'shell':'Terminal', 'web_search':'Tìm kiếm web',
    'project_state':'Ngữ cảnh dự án Redmine', 'read_issue':'Đọc Story/Task',
    'search_issues':'Tìm công việc Redmine',
}
DEFAULT_TOOLS = ['shell','project_state','read_issue','search_issues']


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError(f'{name} phải từ {minimum} đến {maximum}.')
    return value


def text(value, name, limit):
    if not isinstance(value,str) or len(value)>limit or '\0' in value:
        raise ValueError(f'{name} tối đa {limit} ký tự.')
    return value.strip()


def string_list(value, name, limit=30, item_limit=300):
    if not isinstance(value,list) or len(value)>limit:
        raise ValueError(f'{name} cần danh sách tối đa {limit} mục.')
    result = [text(item,name,item_limit) for item in value]
    if any(not item for item in result):
        raise ValueError(name+' không được chứa mục trống.')
    return list(dict.fromkeys(result))


def settings(row):
    """Defaults preserve behavior for existing agents without rewriting saved files."""
    return {
        'role':row.get('role',row.get('specialty','specialist')),
        'description':row.get('description',''),
        'goals':row.get('goals',[]),'work_rules':row.get('work_rules',[]),'tags':row.get('tags',[]),
        'runtime':{'adapter':'codex','model':'','effort':'default','timeout_minutes':30,
                   'concurrent_attempts':1,**row.get('runtime',{})},
        'capabilities':{'skill_ids':[],'default_tools':True,'tools':DEFAULT_TOOLS[:],
                        **row.get('capabilities',{})},
        'collaboration':{'assign_to':'team' if row.get('id')=='pm' else 'nobody',
                         'assignees':[],'consult_to':'team','consultants':[],
                         'autonomy':'delegate' if row.get('id')=='pm' else 'project',
                         'can_propose_agents':False,'max_depth':1,'max_open_subtasks':5,
                         **row.get('collaboration',{})},
    }


def validate(payload, old=None):
    defaults = settings(old or {})
    def field(name): return payload.get(name,defaults[name])
    result = {
        'role':text(field('role'),'Vai trò',100),
        'description':text(field('description'),'Mô tả',4000),
        'goals':string_list(field('goals'),'Mục tiêu'),
        'work_rules':string_list(field('work_rules'),'Quy tắc'),
        'tags':string_list(field('tags'),'Nhãn',20,40),
    }
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,39}',tag) for tag in result['tags']):
        raise ValueError('Nhãn chỉ dùng chữ thường, số, dấu chấm/gạch ngang; bắt đầu bằng chữ hoặc số.')
    runtime=field('runtime')
    if not isinstance(runtime,dict):
        raise ValueError('Runtime không hợp lệ.')
    runtime={**defaults['runtime'],**runtime}
    if set(runtime)-set(defaults['runtime']) or runtime['adapter'] not in ('codex','claude','gemini'):
        raise ValueError('Nhà cung cấp phải là Codex, Claude hoặc Gemini.')
    runtime['model']=text(runtime['model'],'Model',120)
    if runtime['model'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*',runtime['model']):
        raise ValueError('Tên model không hợp lệ.')
    if runtime['effort'] not in ('default','low','medium','high','xhigh'):
        raise ValueError('Mức suy luận không hợp lệ.')
    integer(runtime['timeout_minutes'],'Timeout',1,180)
    integer(runtime['concurrent_attempts'],'Số lượt đồng thời',1,8)
    result['runtime']=runtime
    cap=field('capabilities')
    if not isinstance(cap,dict):
        raise ValueError('Capabilities không hợp lệ.')
    cap={**defaults['capabilities'],**cap}
    if set(cap)-set(defaults['capabilities']) or type(cap['default_tools']) is not bool:
        raise ValueError('Cấu hình công cụ không hợp lệ.')
    cap['skill_ids']=string_list(cap['skill_ids'],'Skill',20,80)
    cap['tools']=string_list(cap['tools'],'Công cụ',len(TOOLS),40)
    if any(key not in TOOLS for key in cap['tools']):
        raise ValueError('Công cụ chưa được hệ thống hỗ trợ.')
    result['capabilities']=cap
    collab=field('collaboration')
    if not isinstance(collab,dict):
        raise ValueError('Collaboration không hợp lệ.')
    collab={**defaults['collaboration'],**collab}
    if set(collab)-set(defaults['collaboration']):
        raise ValueError('Trường cộng tác chưa được hỗ trợ.')
    if collab['assign_to'] not in ('nobody','team','selected') or collab['consult_to'] not in ('nobody','team','selected'):
        raise ValueError('Phạm vi cộng tác không hợp lệ.')
    if collab['autonomy'] not in ('project','suggest','delegate') or type(collab['can_propose_agents']) is not bool:
        raise ValueError('Mức tự chủ không hợp lệ.')
    collab['assignees']=string_list(collab['assignees'],'Người nhận task',24,80)
    collab['consultants']=string_list(collab['consultants'],'Agent được hỏi',24,80)
    integer(collab['max_depth'],'Độ sâu phân công',1,5)
    integer(collab['max_open_subtasks'],'Task con đang mở',1,30)
    result['collaboration']=collab
    return copy.deepcopy(result)


def enabled_tools(profile):
    cap=settings(profile)['capabilities']
    return DEFAULT_TOOLS[:] if cap['default_tools'] else cap['tools'][:]


def allowed(profile, operation, target, ready):
    policy=settings(profile)['collaboration']
    key,values=('assign_to','assignees') if operation=='assign' else ('consult_to','consultants')
    return target in ready and target!=profile['id'] and (
        policy[key]=='team' or (policy[key]=='selected' and target in policy[values]))


class SkillLibrary:
    lock=threading.RLock()

    def __init__(self, runtime, builtin):
        self.path=Path(runtime)/'skills.json'
        self.builtin=Path(builtin)

    def all(self):
        rows=[]
        for file in sorted(self.builtin.glob('*/SKILL.md')):
            rows.append(dict(id='role:'+file.parent.name,name=file.parent.name.upper(),
                             description='Hướng dẫn chuyên môn '+file.parent.name,
                             content=file.read_text(encoding='utf-8'),builtin=True))
        if self.path.exists():
            rows.extend(json.loads(self.path.read_text(encoding='utf-8')))
        return rows

    def listing(self):
        return [{k:v for k,v in r.items() if k!='content'} for r in self.all()]

    def content(self, ids):
        rows={r['id']:r for r in self.all()}
        if any(key not in rows for key in ids):
            raise ValueError('Có skill không còn tồn tại. Chọn lại skill trước khi lưu/chạy.')
        return '\n\n'.join('SKILL '+rows[key]['name']+'\n'+rows[key]['content'] for key in ids)

    def create(self, payload):
        name=text(payload.get('name'),'Tên skill',80)
        content=text(payload.get('content'),'Nội dung skill',32000)
        description=text(payload.get('description',''),'Mô tả skill',300)
        if not name or not content:
            raise ValueError('Cần tên và nội dung skill.')
        with self.lock:
            rows=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []
            if len(rows)>=100:raise ValueError('Thư viện hỗ trợ tối đa 100 skill riêng.')
            if any(r['name'].casefold()==name.casefold() for r in self.all()):
                raise ValueError('Tên skill đã tồn tại.')
            row=dict(id='custom-'+uuid.uuid4().hex[:12],name=name,description=description,content=content,builtin=False)
            rows.append(row)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_name('skills-'+uuid.uuid4().hex+'.tmp')
            try:
                tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
                os.replace(tmp,self.path)
            finally:tmp.unlink(missing_ok=True)
            return {k:v for k,v in row.items() if k!='content'}


def runtime_options():
    models=[]
    file=Path.home()/'.codex/models_cache.json'
    try:
        data=json.loads(file.read_text(encoding='utf-8'))
        for row in data.get('models',[]):
            slug=row.get('slug','')
            if slug and 'auto-review' not in slug:
                models.append(dict(id=slug,name=row.get('display_name',slug)))
    except (OSError,ValueError,TypeError,AttributeError):pass
    from agent_providers import descriptors,MODELS
    for model in models:model['adapter']='codex'
    for provider,ids in MODELS.items():
        models.extend(dict(id=slug,name=slug,adapter=provider) for slug in ids)
    return dict(provider_runtime_version=1,gemini_catalog_version=1,agent_runtime_check_version=1,adapters=descriptors(),models=models,
                tools=[dict(id=key,name=value) for key,value in TOOLS.items()])
