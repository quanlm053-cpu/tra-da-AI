"""Bounded live CLI + file tools + MCP verification in an isolated synthetic workspace."""
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from agent_settings import validate
from agent_providers import HERE,PROVIDERS,command_for,check_available,prepare,decode,validate_result,runtime_error

_guard=threading.Lock()


def stop_process(proc):
    if proc.poll() is None:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
        else:proc.kill()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill()


def verify_runtime(payload,root,timeout=90):
    if not isinstance(payload,dict):raise ValueError('Cấu hình thử runtime không hợp lệ.')
    runtime=validate({'runtime':payload.get('runtime',{})})['runtime']
    access=payload.get('access','read')
    if access not in ('read','write'):raise ValueError('Quyền thử cần là read hoặc write.')
    binary=command_for('codex')
    codex=binary[0] if binary else None
    check_available(runtime,codex,require_auth=True)
    if not _guard.acquire(blocking=False):raise ValueError('Đang có một lượt thử runtime. Chờ kết quả trước khi thử tiếp.')
    try:
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='runtime-',dir=root) as directory:
            base=Path(directory);workspace=base/'workspace';workspace.mkdir()
            file_token=uuid.uuid4().hex
            mcp_token=uuid.uuid4().hex
            (workspace/'input.txt').write_text(file_token,encoding='utf-8')
            state=base/'synthetic.json';state.write_text(json.dumps({'token':mcp_token}),encoding='utf-8')
            spec={'type':'object','properties':{key:{'type':'string'} for key in ('summary','file_token','mcp_token','artifact')},
                  'required':['summary','file_token','mcp_token','artifact'],'additionalProperties':False}
            schema_path=base/'output.schema.json';schema_path.write_text(json.dumps(spec),encoding='utf-8')
            output=base/'output.json'
            command,extra_env=prepare(runtime['adapter'],runtime,access=='read',['project_state'],state,
                output,schema_path,codex,mcp_entry=HERE/'provider_smoke_mcp.py',cwd=workspace,check_mode=True)
            prompt=('This is a synthetic runtime check, not a project task. Use native read_file/Read tools to read input.txt. '
                'You MUST call the provided MCP tool whose name ends in project_state once and read its check_token. Do not call MCP using a shell command. Do not list directories. '
                +'Exact input file path: '+str(workspace.resolve()/'input.txt')+'. Exact output file path: '+str(workspace.resolve()/'result.txt')+'. '
                +'Do not use shell, network, GitHub, subagents or files outside this workspace. '
                + ('Create result.txt using native file editing tools. Its exact content must be the input.txt token followed by | followed by the MCP check_token. Set artifact to result.txt. '
                   if access=='write' else 'Do not create or change any file. Set artifact to an empty string. ')
                +'Return file_token and mcp_token with the exact values read from the file and MCP. '
                'Return only one final JSON object matching this schema: '+json.dumps(spec))
            env={**os.environ,**extra_env,'PATH':str(HERE.parent/'tools/bin')+os.pathsep+os.environ.get('PATH','')}
            with (base/'stdout.json').open('wb') as stdout,(base/'stderr.log').open('wb') as stderr:
                proc=subprocess.Popen(command,cwd=workspace,env=env,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:
                    proc.stdin.write(prompt.encode('utf-8'));proc.stdin.close()
                    deadline=time.monotonic()+timeout
                    while proc.poll() is None:
                        diagnostic_text=(base/'stderr.log').read_text(encoding='utf-8',errors='replace')[-12000:]
                        issue=runtime_error(runtime['adapter'],diagnostic_text)
                        if issue:raise ValueError(issue)
                        if time.monotonic()>deadline:
                            detail='MCP đã được gọi.' if state.with_suffix('.audit').exists() else 'Chưa ghi nhận agent gọi MCP.'
                            raise ValueError(PROVIDERS[runtime['adapter']]+' quá thời gian thử. '+detail+' Chưa xác nhận runtime hoạt động.')
                        time.sleep(.25)
                finally:stop_process(proc)
            issue=runtime_error(runtime['adapter'],(base/'stderr.log').read_text(encoding='utf-8',errors='replace')[-12000:])
            if issue:raise ValueError(issue)
            if proc.returncode:
                raise ValueError(PROVIDERS[runtime['adapter']]+' chưa hoàn tất lượt thử. Kiểm tra đăng nhập, quyền model, quota và quyền công cụ.')
            try:
                if runtime['adapter']=='codex':
                    result=json.loads(output.read_text(encoding='utf-8'));validate_result(result,spec)
                else:result=decode(runtime['adapter'],(base/'stdout.json').read_text(encoding='utf-8'),spec)
            except (OSError,ValueError,TypeError):
                raise ValueError('CLI chưa trả đúng JSON bàn giao của lượt thử; chưa xác nhận thành công.') from None
            if result['file_token']!=file_token:raise ValueError('Chưa xác nhận agent đọc file đầu vào đúng.')
            audit=state.with_suffix('.audit')
            if result['mcp_token']!=mcp_token or not audit.is_file() or 'project_state' not in audit.read_text():
                raise ValueError('MCP đã được gọi nhưng token bàn giao chưa đúng.' if audit.is_file() else 'CLI đã chạy nhưng chưa ghi nhận gọi MCP. '+result['summary'][:180])
            if (workspace/'input.txt').read_text(encoding='utf-8')!=file_token:raise ValueError('Agent đã sửa file đầu vào trong lượt thử.')
            files={p.relative_to(workspace).as_posix() for p in workspace.rglob('*') if p.is_file()}
            if access=='write':
                artifact=workspace/'result.txt'
                if result['artifact']!='result.txt' or not artifact.is_file() or artifact.read_text(encoding='utf-8').strip()!=file_token+'|'+mcp_token:
                    raise ValueError('Chưa xác nhận agent tạo file bàn giao đúng.')
                allowed={'input.txt','result.txt'}
            else:
                if result['artifact']:raise ValueError('Agent chỉ đọc báo một file không được phép tạo.')
                allowed={'input.txt'}
            unexpected=files-allowed
            # CLIs may keep their own workspace metadata; never treat it as task output.
            unexpected={p for p in unexpected if not p.startswith(('.gemini/','.claude/','.codex/'))}
            if unexpected:raise ValueError('Lượt thử tạo file ngoài phạm vi yêu cầu.')
            return dict(verified=True,adapter=runtime['adapter'],model=runtime['model'] or '(CLI default)',
                access=access,checks={'cli':True,'structured_output':True,'read_file':True,'mcp':True,
                    'write_file':access=='write','read_only_unchanged':access=='read'},
                verified_at=time.time(),duration_ms=round((time.monotonic()-started)*1000),
                message='CLI, đọc file, MCP và bàn giao đã đạt'+('; tạo file đã đạt.' if access=='write' else '; file đầu vào giữ nguyên.'))
    finally:_guard.release()
