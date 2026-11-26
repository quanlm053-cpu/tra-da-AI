"""Persistent local chat inbox; only the single controller consumes jobs."""
import json
import time

ROLES = ('ba','backend','frontend','reviewer','qa','team')

def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE NOT NULL,
        story_id INTEGER NOT NULL, role TEXT NOT NULL, message TEXT NOT NULL,
        state TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '', created REAL NOT NULL)''')
    db.commit()

def enqueue(db, body):
    init(db)
    story, role, message, request = body.get('story_id'), body.get('role'), body.get('message'), body.get('request_id')
    from team_commands import team_start
    if isinstance(message,str) and team_start(message):role='team'
    if type(story) is not int or role not in ROLES or not isinstance(message,str) or not 1 <= len(message.strip()) <= 6000:
        raise ValueError('Story, agent hoặc nội dung không hợp lệ.')
    if not isinstance(request,str) or not 8 <= len(request) <= 80:
        raise ValueError('Thiếu mã yêu cầu.')
    if not db.execute('SELECT 1 FROM jobs WHERE id=?',(story,)).fetchone():
        raise ValueError('Story chưa được dịch vụ tiếp nhận.')
    existing = db.execute('SELECT id,story_id,role,message FROM chats WHERE request_id=?',(request,)).fetchone()
    if existing:
        if existing[1:] != (story,role,message.strip()):
            raise ValueError('Mã yêu cầu đã được dùng cho nội dung khác.')
        return existing[0]
    if db.execute("SELECT COUNT(*) FROM chats WHERE state IN ('queued','running')").fetchone()[0] >= 30:
        raise ValueError('Hàng chờ đang đầy. Vui lòng chờ agent xử lý.')
    cur=db.execute('INSERT INTO chats(request_id,story_id,role,message,state,created) VALUES(?,?,?,?,?,?)',
                   (request,story,role,message.strip(),'queued',time.time()))
    db.commit()
    return cur.lastrowid

def messages(db, story):
    init(db)
    rows=db.execute('SELECT id,role,message,state,reply,created FROM chats WHERE story_id=? ORDER BY id DESC LIMIT 50',(story,)).fetchall()
    return [dict(zip(('id','role','message','state','reply','created'),r)) for r in reversed(rows)]

def process_one(service):
    init(service.db)
    row=service.db.execute("SELECT id,story_id,role,message FROM chats WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
    if not row:return False
    chat_id,story_id,role,message=row
    service.db.execute("UPDATE chats SET state='running' WHERE id=?",(chat_id,));service.db.commit()
    try:
        from team_commands import start
        if role=='team':
            reply=start(service,story_id,message)
            service.db.execute("UPDATE chats SET state='done',reply=? WHERE id=?",(reply,chat_id));service.db.commit()
            return True
        saved=service.db.execute('SELECT state,data FROM jobs WHERE id=?',(story_id,)).fetchone()
        if not saved:raise ValueError('Không tìm thấy Story.')
        job=json.loads(saved[1])
        history=messages(service.db,story_id)
        history=[m for m in history if m['role']==role and m['state']=='done'][-8:]
        result=service.agent(job,role,chat={'id':chat_id,'message':message,'history':history,'job_state':saved[0]})
        reply=result['summary']
        state='done'
    except Exception as exc:
        reply=('Chưa hoàn thành: '+str(exc)) if isinstance(exc,ValueError) or type(exc).__name__ in ('Hold','Cancelled') else 'Lượt agent gặp lỗi '+type(exc).__name__+'. Xem log dịch vụ.'
        state='failed'
    service.db.execute('UPDATE chats SET state=?,reply=? WHERE id=?',(state,reply,chat_id));service.db.commit()
    return True
