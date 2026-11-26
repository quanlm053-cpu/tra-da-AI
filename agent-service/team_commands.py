import re
import unicodedata
import json

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower().replace('đ','d')) if not unicodedata.combining(c))

def team_start(text):
    text=normalized(text)
    return bool(re.search(r'\b(ca doi|tat ca|team|cung nhau)\b',text) and re.search(r'\b(lam|bat dau|trien khai|tiep tuc|start)\b',text) and not re.search(r'tien do|den dau|xong chua|dang lam gi|bao cao|tai sao',text))

def start(service,story_id,message):
    match=re.search(r'\b(?:story|task cha)\s*#?\s*(\d+)\b',normalized(message))
    target=int(match[1]) if match else story_id
    if not re.search(r'\b(lam|bat dau|trien khai|tiep tuc|start)\b',normalized(message)) or re.search(r'tien do|den dau|xong chua|dang lam gi|bao cao|tai sao',normalized(message)):
        row=service.db.execute('SELECT state,data FROM jobs WHERE id=?',(target,)).fetchone()
        if not row:return f'Story #{target} chưa được đội tiếp nhận.'
        job=json.loads(row[1])
        return f'Story #{target}: {row[0]}, bước {job["stage"]}. '+str(job.get('error',''))+'\nĐể giao việc: Cả đội làm Story '+str(target)
    issue=service.api.issue(target)
    if issue['project']['id']!=service.config['project_id'] or issue['tracker']['id']!=service.config['trackers']['story']:
        raise ValueError('Hãy chọn một Story trong dự án hiện tại.')
    status=issue['status']['id']
    if status==service.s['done']:raise ValueError('Story đã Done; cần mở lại trước khi giao đội làm tiếp.')
    if status==service.s['blocked']:raise ValueError('Story đang Blocked. PM cần bỏ chặn trước khi chạy đội.')
    row=service.db.execute('SELECT state,data FROM jobs WHERE id=?',(target,)).fetchone()
    if not row:
        if status==service.s['backlog']:
            service.api.update(target,status_id=service.s['selected'],notes='[AI:team] PM giao cả đội bắt đầu Story qua văn phòng AI.')
        elif status!=service.s['selected']:
            raise ValueError('Story chưa có kế hoạch trong dịch vụ; hãy đưa về Selected để BA nhận việc.')
        job={'id':target,'stage':'claim','calls':0,'rounds':0}
    else:
        job=json.loads(row[1])
        if row[0]=='active':return f'Cả đội đã đang xử lý Story #{target}. Không tạo lượt chạy trùng.'
        if job.get('calls',0)>=service.config['max_agent_calls_per_story']:
            raise ValueError('Story đã hết số lượt agent cấu hình; PM cần xem kết quả trước khi tăng giới hạn.')
        if job.get('rounds',0)>=service.config['max_repair_rounds']:
            raise ValueError('Story đã hết số vòng sửa cấu hình; PM cần xem kết quả trước khi chạy tiếp.')
        service.story(job)
    job.pop('error',None)
    job['team_request']=message
    service.save(job,'active')
    service.api.update(target,notes='[AI:team] Nhận lệnh PM: '+message+'\nĐội tự bàn giao BA → Backend → Frontend → Reviewer → QA; lỗi review/test trả về dev sửa.')
    return f'Đã giao cả đội tiếp tục Story #{target} từ bước {job["stage"]}. Các phần việc độc lập chạy song song trong checkout riêng, sau đó ghép code, review và QA tích hợp. Theo dõi bàn giao và sản phẩm trong bảng công việc.'
