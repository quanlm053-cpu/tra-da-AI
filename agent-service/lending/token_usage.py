"""Project-local usage accounting. Never infer tokens from text length."""
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


def month():
    return datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m')


def extract(provider, path):
    try:
        raw=Path(path).read_text(encoding='utf-8')
        if provider=='codex':
            rows=[json.loads(line) for line in raw.splitlines() if line.strip().startswith('{')]
            usages=[r['usage'] for r in rows if r.get('type')=='turn.completed' and isinstance(r.get('usage'),dict)]
            if not usages:return None
            return dict(input=sum(u.get('input_tokens',0) for u in usages),
                        output=sum(u.get('output_tokens',0) for u in usages),
                        cached=sum(u.get('cached_input_tokens',0) for u in usages))
        data=json.loads(raw)
        if provider=='claude':
            u=data.get('usage')
            if not isinstance(u,dict):return None
            return dict(input=u.get('input_tokens',0)+u.get('cache_read_input_tokens',0)+u.get('cache_creation_input_tokens',0),
                        output=u.get('output_tokens',0),cached=u.get('cache_read_input_tokens',0))
        models=data.get('stats',{}).get('models',{})
        if not models:return None
        tokens=[m['tokens'] for m in models.values() if isinstance(m.get('tokens'),dict)]
        if not tokens:return None
        # Gemini total includes thinking tokens; avoid adding cached tokens twice.
        return dict(input=sum(u.get('prompt',u.get('input',0)) for u in tokens),
                    output=sum(u.get('candidates',0)+u.get('thoughts',0) for u in tokens),
                    cached=sum(u.get('cached',0) for u in tokens),
                    total=sum(u.get('total',u.get('input',u.get('prompt',0))+u.get('candidates',0)+u.get('thoughts',0)) for u in tokens))
    except (OSError,ValueError,TypeError,KeyError):return None


class TokenUsage:
    lock=threading.RLock()

    def __init__(self, runtime):
        self.path=Path(runtime)/'token-usage.json'

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'limits':{},'runs':[]}

    def save(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        tmp.replace(self.path)

    def set_limit(self,agent,value):
        if type(value) is not int or not 0<=value<=1_000_000_000:
            raise ValueError('Giới hạn tháng cần là số nguyên từ 0 đến 1 tỷ; 0 là không giới hạn.')
        with self.lock:
            data=self.read();data['limits'][agent]=value;self.save(data)

    def start(self,agent,provider,model,context):
        with self.lock:
            data=self.read();limit=data['limits'].get(agent,0)
            rows=[r for r in data['runs'] if r['agent']==agent and r['month']==month()]
            if limit and (sum((r.get('usage') or {}).get('total',0) for r in rows)>=limit or
                          any(r['state']=='running' or r.get('usage') is None for r in rows)):
                raise ValueError('Đã chạm giới hạn token hoặc còn lượt chưa xác định mức dùng. Kiểm tra mục Token trước khi chạy tiếp.')
            key=str(time.time_ns())
            data['runs'].append(dict(id=key,agent=agent,provider=provider,model=model or 'default',month=month(),
                at=time.time(),task=context.get('task'),story=(context.get('story') or {}).get('id') if isinstance(context.get('story'),dict) else None,
                state='running',usage=None))
            self.save(data);return key

    def finish(self,key,usage,state):
        with self.lock:
            data=self.read();row=next(r for r in data['runs'] if r['id']==key)
            if usage is not None:
                usage['total']=usage.get('total',usage['input']+usage['output'])
            row.update(usage=usage,state=state);self.save(data)

    def snapshot(self):
        with self.lock:
            data=self.read()
        return {**data,'month':month(),'scope':'office-runtime','timezone':'Asia/Bangkok'}
