"""Project-scoped agent identities. No credentials or executable commands in profiles."""
import copy
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from agent_settings import settings, validate

SPECIALTIES = ('sa', 'ba', 'backend', 'frontend', 'devops', 'reviewer', 'tester', 'specialist')
INACTIVE = ('archived', 'terminated')
DEFAULTS = [
    ('pm', 'PM', 'Điều phối dự án', 'pm'),
    ('sa', 'SA', 'Thiết kế dữ liệu và API', 'sa'),
    ('ba', 'BA', 'Viết yêu cầu và dựng prototype', 'ba'),
    ('backend', 'BE', 'Triển khai API và dữ liệu', 'backend'),
    ('frontend', 'FE', 'Dựng giao diện và nối API', 'frontend'),
    ('devops', 'DEVOPS', 'Chuẩn bị build và CI', 'devops'),
    ('reviewer', 'REVIEW', 'Rà soát mã và phân quyền', 'reviewer'),
    ('tester', 'TESTER', 'Kiểm thử theo tiêu chí nghiệm thu', 'tester'),
]
COLORS = {'pm':'#f2bd76','sa':'#b0a3ff','ba':'#b0a3ff','backend':'#44d4e3',
          'frontend':'#60a7ff','devops':'#44d4e3','reviewer':'#ffbc76','tester':'#75dab4'}


class AgentRegistry:
    def __init__(self, runtime):
        self.path = Path(runtime) / 'agents.json'
        self.lock = threading.RLock()
        stored = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
        self.events = stored.get('events',[]) if isinstance(stored,dict) else []
        self.deleted = stored.get('deleted',[]) if isinstance(stored,dict) else []
        self.rows = (stored['agents'] if isinstance(stored,dict) else stored) if stored is not None else [
            dict(id=key, name=name, title=title, specialty=kind, instructions='', builtin=True,
                 status='ready', access='read' if key in ('pm','reviewer','tester') else 'write',
                 color=COLORS[key], redmine_user_id=None, revision=1)
            for key, name, title, kind in DEFAULTS
        ]

    def listing(self):
        with self.lock:
            return [copy.deepcopy({**row,**settings(row)}) for row in self.rows]

    def history(self, key):
        with self.lock:
            return copy.deepcopy([e for e in self.events if e['id']==key][-100:][::-1])

    def deleted_profiles(self):
        with self.lock:
            return copy.deepcopy(self.deleted)

    def record(self, operation, row, **details):
        self.events.append(dict(operation=operation,id=row['id'],name=row['name'],
                                revision=row['revision'],at=time.time(),**details))
        try:
            self.save()
        except Exception:
            self.events.pop()
            raise

    def get(self, key):
        with self.lock:
            row = next((a for a in self.rows if a['id'] == key), None)
            if row is None:
                raise ValueError('Không tìm thấy agent.')
            return copy.deepcopy({**row,**settings(row)})

    def sync_update(self, key, **values):
        """System-owned connection metadata; does not change the user-edit revision."""
        allowed = {'state','error','retry_at','login','role_id','role_name','membership_id',
                   'user_status','fingerprint','redmine_user_id','redmine_managed','previous_user_id'}
        if set(values)-allowed:
            raise ValueError('Trường đồng bộ không hợp lệ.')
        with self.lock:
            row = next((a for a in self.rows if a['id']==key),None)
            if row is None:
                raise ValueError('Không tìm thấy agent.')
            previous = copy.deepcopy(row)
            values = dict(values)
            for field in ('redmine_user_id','redmine_managed'):
                if field in values:
                    row[field] = values.pop(field)
            row['redmine_sync'] = {**row.get('redmine_sync',{}),**values,'updated_at':time.time()}
            try:
                self.record('redmine_sync',row,sync_state=row['redmine_sync'].get('state'))
            except Exception:
                row.clear();row.update(previous)
                raise
            return copy.deepcopy(row)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name('agents-' + uuid.uuid4().hex + '.tmp')
        try:
            tmp.write_text(json.dumps(dict(version=2,agents=self.rows,deleted=self.deleted,events=self.events),
                                      ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def change(self, payload, key=None):
        with self.lock:
            old = self.get(key) if key else None
            if old and payload.get('revision') != old['revision']:
                raise ValueError('Cấu hình đã thay đổi. Tải lại trước khi lưu.')
            def field(name, default):
                return payload.get(name, old.get(name, default) if old else default)
            name, title = field('name',''), field('title','')
            instructions = field('instructions','')
            if not isinstance(name,str) or not 1 <= len(name.strip()) <= 40:
                raise ValueError('Tên agent cần từ 1 đến 40 ký tự.')
            if not isinstance(title,str) or not 1 <= len(title.strip()) <= 160:
                raise ValueError('Nhiệm vụ cần từ 1 đến 160 ký tự.')
            if (not old or old['status'] not in INACTIVE or old['name'].casefold()!=name.strip().casefold()) and any(a['name'].casefold()==name.strip().casefold() and a['id']!=key
                   and a['status'] not in INACTIVE for a in self.rows):
                raise ValueError('Tên agent đã được sử dụng.')
            if not isinstance(instructions,str) or len(instructions)>65536:
                raise ValueError('Hướng dẫn tối đa 65536 ký tự.')
            specialty = field('specialty','specialist')
            if specialty not in (*SPECIALTIES, 'pm'):
                raise ValueError('Chuyên môn không hợp lệ.')
            if specialty=='pm' and (not old or old['id']!='pm'):
                raise ValueError('Chỉ có một PM điều phối.')
            access = field('access','read')
            if access not in ('read','write'):
                raise ValueError('Quyền không hợp lệ.')
            if specialty in ('pm','reviewer','tester') and access!='read':
                raise ValueError('PM, REVIEW và TESTER chỉ được đọc code.')
            color = field('color','#a78bfa')
            if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
                raise ValueError('Màu không hợp lệ.')
            supplied_user = payload.get('redmine_user_id')
            if supplied_user is not None and (type(supplied_user) is not int or supplied_user<=0):
                raise ValueError('Người phụ trách Redmine không hợp lệ.')
            user = old.get('redmine_user_id') if old else None
            row = dict(id=key or 'agent-'+uuid.uuid4().hex[:12], name=name.strip(),
                       title=title.strip(), instructions=instructions.strip(), specialty=specialty,
                       access=access, color=color, redmine_user_id=user, builtin=bool(old and old['builtin']),
                       status='draft', revision=(old['revision']+1 if old else 1))
            row.update(validate(payload,old or {'specialty':specialty}))
            row['role']=row['role'] or specialty
            if old:
                for metadata in ('redmine_sync','redmine_managed'):
                    if metadata in old:
                        row[metadata] = copy.deepcopy(old[metadata])
            if old and old['status'] in INACTIVE:
                row['status'] = old['status']
            if old and old['builtin']:
                for fixed in ('specialty','access'):
                    if row[fixed]!=old[fixed]:
                        raise ValueError('Giữ nguyên chuyên môn và quyền của agent gốc.')
                row['status']=old['status']
            before = copy.deepcopy(self.rows)
            if old:
                self.rows[self.rows.index(next(a for a in self.rows if a['id']==key))] = row
            else:
                if sum(a['status'] not in INACTIVE for a in self.rows)>=24:
                    raise ValueError('Văn phòng hỗ trợ tối đa 24 agent chưa lưu trữ.')
                self.rows.append(row)
            try:
                changed = [k for k in row if not old or old.get(k)!=row[k]]
                self.record('update' if old else 'create',row,fields=changed)
            except Exception:
                self.rows = before
                raise
            return copy.deepcopy(row)

    def transition(self, key, status):
        if status not in ('draft','ready','paused','archived','terminated'):
            raise ValueError('Trạng thái không hợp lệ.')
        with self.lock:
            row = next((a for a in self.rows if a['id']==key),None)
            if row is None:
                raise ValueError('Không tìm thấy agent.')
            if row['builtin'] and status in INACTIVE:
                raise ValueError('Không lưu trữ agent gốc đang phục vụ workflow hiện có.')
            if row['id']=='pm' and status!='ready':
                raise ValueError('Dùng nút dừng dự án để tạm dừng điều phối; PM vẫn cần trả lời.')
            allowed = {'draft':('ready','archived','terminated'), 'ready':('ready','paused','archived','terminated'),
                       'paused':('ready','paused','archived','terminated'), 'archived':('draft','terminated'),
                       'terminated':('draft',)}
            if status not in allowed[row['status']]:
                raise ValueError('Chuyển trạng thái không hợp lệ; agent đã lưu trữ/chấm dứt cần khôi phục về bản nháp.')
            if row['status'] in INACTIVE and status not in INACTIVE:
                if sum(a['status'] not in INACTIVE for a in self.rows)>=24:
                    raise ValueError('Văn phòng đã đủ 24 agent. Lưu trữ agent khác trước khi khôi phục.')
                if any(a['id']!=key and a['status'] not in INACTIVE and
                       a['name'].casefold()==row['name'].casefold() for a in self.rows):
                    raise ValueError('Tên agent đã được dùng. Đổi tên agent đang hoạt động trước khi khôi phục.')
            before = copy.deepcopy(row)
            row.update(status=status, revision=row['revision']+1)
            try:
                self.record('status',row,previous=before['status'],status=status)
            except Exception:
                row.clear(); row.update(before)
                raise
            return copy.deepcopy(row)

    def duplicate(self, key):
        with self.lock:
            source = self.get(key)
            if source['specialty']=='pm':
                raise ValueError('PM là bộ điều phối duy nhất; không nhân bản PM.')
            base = source['name'][:34]
            index = 2
            while any(a['name'].casefold()==f'{base} {index}'.casefold() and a['status'] not in INACTIVE for a in self.rows):
                index += 1
            return self.change({**source,'name':f'{base} {index}'})

    def delete(self, key, revision, confirm_name):
        with self.lock:
            row = self.get(key)
            if row['builtin']:
                raise ValueError('Agent gốc đang phục vụ workflow, không được xóa.')
            if row['status'] not in INACTIVE:
                raise ValueError('Lưu trữ hoặc chấm dứt agent trước khi xóa vĩnh viễn.')
            if type(revision) is not int or revision!=row['revision']:
                raise ValueError('Hồ sơ đã thay đổi. Tải lại trước khi xóa.')
            if confirm_name!=row['name']:
                raise ValueError('Nhập chính xác tên agent để xác nhận xóa.')
            before = self.rows[:]
            self.rows = [a for a in self.rows if a['id']!=key]
            # Minimal attribution remains for completed tasks and messages. No skill or secret retained.
            tombstone = dict(id=key,name=row['name'],title=row['title'],deleted_at=time.time())
            for field in ('redmine_user_id','redmine_managed'):
                if field in row: tombstone[field] = row[field]
            if row.get('redmine_sync',{}).get('login'):
                tombstone['redmine_login'] = row['redmine_sync']['login']
            self.deleted.append(tombstone)
            try:
                self.record('delete',row)
            except Exception:
                self.rows = before
                self.deleted.pop()
                raise
            return dict(id=key,name=row['name'],deleted=True)
