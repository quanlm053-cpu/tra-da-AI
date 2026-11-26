"""Provider adapters. Credentials and executable commands never belong in agent profiles."""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PACKAGES=HERE.parent/'tools/providers/node_modules'
PROVIDERS={'codex':'Codex CLI','claude':'Claude Code','gemini':'Gemini CLI'}
MODELS={'claude':['sonnet','opus','haiku']}


def command_for(provider,codex=None):
    if provider not in PROVIDERS:raise ValueError('Nhà cung cấp không được hỗ trợ.')
    if provider=='codex':
        binary=codex or shutil.which('codex')
        if not binary and os.name=='nt':
            found=list((Path(os.environ.get('LOCALAPPDATA',''))/'OpenAI/Codex/bin').glob('*/codex.exe'))
            binary=str(max(found,key=lambda f:f.stat().st_mtime)) if found else None
        return [binary] if binary else []
    if provider=='claude':
        arch='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
        native=PACKAGES/f'@anthropic-ai/claude-code-win32-{arch}/claude.exe'
        if os.name=='nt' and native.is_file() and native.stat().st_size>10000:return [str(native)]
    if provider=='gemini':
        entry=PACKAGES/'@google/gemini-cli/bundle/gemini.js'
        node=shutil.which('node')
        if node and entry.is_file():return [node,str(entry)]
    binary=shutil.which(provider)
    if binary and Path(binary).suffix.lower() not in ('.cmd','.bat','.ps1'):return [binary]
    return []


def gemini_cached_key():
    node=shutil.which('node')
    if not node:return False
    try:
        result=subprocess.run([node,str(HERE/'gemini-auth-status.mjs')],capture_output=True,timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        return result.returncode==0 and json.loads(result.stdout).get('configured') is True
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return False


def auth_hint(provider):
    if provider=='claude':
        return bool(os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_CODE_OAUTH_TOKEN')
                    or (Path.home()/'.claude/.credentials.json').is_file())
    if provider=='gemini':
        return bool(os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
                    or (Path.home()/'.gemini/oauth_creds.json').is_file() or gemini_cached_key())
    return (Path.home()/'.codex/auth.json').is_file() or bool(os.environ.get('OPENAI_API_KEY'))


def descriptors():
    return [dict(id=key,name=name,available=bool(command_for(key)),credential_detected=auth_hint(key),
                 authentication_verified=False) for key,name in PROVIDERS.items()]


def check_available(runtime,codex=None,require_auth=False):
    provider=runtime['adapter']
    command=[] if provider=='codex' and not codex else command_for(provider,codex)
    if not command:raise ValueError(PROVIDERS[provider]+' chưa được cài. Chạy provider.ps1 -Action install.')
    if require_auth and provider!='codex' and not auth_hint(provider):
        if provider=='claude':
            try:
                result=subprocess.run(command+['auth','status'],capture_output=True,timeout=12,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if json.loads(result.stdout).get('loggedIn'):return command
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
        raise ValueError(PROVIDERS[provider]+' chưa có thông tin đăng nhập. Cấu hình tài khoản/API key trước khi kích hoạt; có thể lưu agent dưới dạng bản nháp.')
    return command


def prepare(provider,runtime,read_only,tools,state_path,output,schema_path,codex=None,mcp_entry=None,cwd=None,check_mode=False):
    command=check_available(runtime,codex)
    output=Path(output).resolve();schema_path=Path(schema_path).resolve();state_path=Path(state_path).resolve()
    enabled=[key for key in tools if key in ('project_state','read_issue','search_issues')]
    server=dict(command=sys.executable,args=[str(mcp_entry or HERE/'mcp.py'),str(state_path),json.dumps(enabled)])
    config_file=output.with_suffix('.provider.json')
    env={}
    if provider=='codex':
        command+=['exec','--ignore-user-config','-c','approval_policy="never"',
            '-c','windows.sandbox="elevated"','-c','agents.enabled=false',
            '-c','features.apps=false','-c','features.plugins=false',
            '-c','features.shell_tool='+('true' if 'shell' in tools else 'false'),
            '-c','web_search='+json.dumps('live' if 'web_search' in tools else 'disabled'),
            '-c','mcp_servers.lending.command='+json.dumps(sys.executable),
            '-c','mcp_servers.lending.args='+json.dumps(server['args']),
            '-c','mcp_servers.lending.enabled_tools='+json.dumps(enabled),
            '-c','mcp_servers.lending.tools.project_state.approval_mode="approve"',
            '--sandbox','read-only' if read_only else 'workspace-write',
            '-C',str(cwd or output.parent),'--output-schema',str(schema_path),
            '--output-last-message',str(output),'--json']
        if runtime['effort']!='default':command+=['-c','model_reasoning_effort='+json.dumps(runtime['effort'])]
    elif provider=='claude':
        native=['Read','Glob','Grep']
        if not read_only:native+=['Edit','Write']
        if not read_only and 'shell' in tools:native+=['Bash','PowerShell']
        if 'web_search' in tools:native+=['WebSearch','WebFetch']
        config_file.write_text(json.dumps({'mcpServers':{'lending':server}}),encoding='utf-8')
        command+=['--print','--restricted','--permission-mode','dontAsk','--permission-prompts','none',
            '--strict-mcp-config','--mcp-config',str(config_file),'--disable-slash-commands',
            '--no-session-persistence','--tools',','.join(native),
            '--allowedTools',','.join(native+[f'mcp__lending__{key}' for key in enabled]),
            '--output-format','json','--json-schema',schema_path.read_text(encoding='utf-8')]
        if runtime['effort']!='default':command+=['--effort',runtime['effort']]
    elif provider=='gemini':
        native=['list_directory','read_file','read_many_files','glob','grep_search']
        if not read_only:native+=['write_file','replace']
        if not read_only and 'shell' in tools:native+=['run_shell_command']
        if 'web_search' in tools:native+=['google_web_search','web_fetch']
        if check_mode:native=['read_file']+([] if read_only else ['write_file'])
        server.update(trust=True,includeTools=enabled)
        policy={'tools':{'core':native,'allowed':native},
                'mcp':{'allowed':['lending']},'mcpServers':{'lending':server},
                'hooksConfig':{'enabled':False},'skills':{'enabled':False},'experimental':{'enableAgents':False},'admin':{'extensions':{'enabled':False}},
                'advanced':{'ignoreLocalEnv':True},'general':{'maxAttempts':1},
                'context':{'fileName':'TRADA_NO_AUTODISCOVERY.md','includeDirectoryTree':False,'loadMemoryFromIncludeDirectories':False},
                'telemetry':{'enabled':False},
                'privacy':{'usageStatisticsEnabled':False}}
        if check_mode:
            policy['model']={'maxSessionTurns':10}
            generation={'maxOutputTokens':1024}
            if runtime['model'].startswith('gemini-3'):
                generation['thinkingConfig']={'thinkingLevel':'MINIMAL' if 'flash' in runtime['model'] else 'LOW'}
            elif runtime['model'].startswith('gemini-2.5'):
                generation['thinkingConfig']={'thinkingBudget':128}
            policy['modelConfigs']={'overrides':[{'match':{'model':runtime['model']} if runtime['model'] else {},
                'modelConfig':{'generateContentConfig':generation}}]}
        policy['security']={'auth':{'selectedType':'gemini-api-key'}}
        target=Path(cwd or output.parent).resolve()
        session=output.with_suffix('.gemini-session')
        home=session/'home';work=session/'work'
        for location in (home,work):
            directory=location/'.gemini';directory.mkdir(parents=True,exist_ok=True)
            (directory/'settings.json').write_text(json.dumps(policy),encoding='utf-8')
        (work/'.git').mkdir(exist_ok=True)
        config_file=work/'.gemini/settings.json'
        env={'TRADA_GEMINI_HOME':str(home),'TRADA_GEMINI_WORK':str(work),'TRADA_GEMINI_TARGET':str(target),'GEMINI_CLI_TRUST_WORKSPACE':'true'}
        command=[command[0],str(HERE/'gemini-runtime-launcher.mjs'),
            '--skip-trust','--include-directories',str(target),'--allowed-mcp-server-names','lending',
            '--output-format','json','--approval-mode','default','--prompt',
            'Complete the task supplied on stdin. Return only the requested final JSON object.']
    else:raise ValueError('Use existing Codex adapter.')
    if runtime['model']:command+=['--model',runtime['model']]
    if provider=='codex':command+=['-']
    return command,env


def validate_result(value,spec,path='$'):
    """Validate the schema subset emitted by office.schema before dispatching any action."""
    kind=spec.get('type')
    valid={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
           'integer':type(value) is int,'boolean':type(value) is bool}
    if kind and not valid.get(kind,False):raise ValueError(path+': sai kiểu dữ liệu bàn giao.')
    if 'enum' in spec and value not in spec['enum']:raise ValueError(path+': giá trị ngoài phạm vi được cấp.')
    if kind=='object':
        props=spec.get('properties',{})
        if any(key not in value for key in spec.get('required',[])):raise ValueError(path+': thiếu trường bàn giao bắt buộc.')
        if spec.get('additionalProperties') is False and set(value)-set(props):raise ValueError(path+': trường bàn giao chưa hỗ trợ.')
        for key,item in value.items():
            if key in props:validate_result(item,props[key],path+'.'+key)
    if kind=='array':
        if len(value)>spec.get('maxItems',10000):raise ValueError(path+': vượt giới hạn danh sách.')
        for i,item in enumerate(value):validate_result(item,spec.get('items',{}),f'{path}[{i}]')
    if kind=='integer' and value<spec.get('minimum',value):raise ValueError(path+': số ngoài phạm vi.')


def decode(provider,stdout,spec):
    envelope=json.loads(stdout)
    if not isinstance(envelope,dict) or envelope.get('is_error') or envelope.get('error'):
        raise ValueError(PROVIDERS[provider]+': lượt chạy trả lỗi, chưa thực hiện action.')
    value=envelope.get('structured_output') if provider=='claude' else None
    if value is None:
        value=envelope.get('result' if provider=='claude' else 'response')
        if isinstance(value,str):
            value=value.strip()
            fence=chr(96)*3
            if value.startswith(fence+'json') and value.endswith(fence):value=value[7:-3].strip()
            elif value.startswith(fence) and value.endswith(fence):value=value[3:-3].strip()
            value=json.loads(value)
    validate_result(value,spec)
    return value


def diagnostic(provider):
    command=command_for(provider)
    if not command:return dict(provider=provider,installed=False,credential_detected=False,authentication_verified=False)
    result=subprocess.run(command+['--version'],capture_output=True,timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    row=dict(provider=provider,installed=result.returncode==0,version=result.stdout.decode('utf-8',errors='replace').strip()[:100],
             credential_detected=auth_hint(provider),authentication_verified=False)
    if provider=='claude':
        result=subprocess.run(command+['auth','status'],capture_output=True,timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:row['credential_detected']=bool(json.loads(result.stdout).get('loggedIn'))
        except ValueError:pass
    return row



def gemini_models(action='models',model=''):
    if action not in ('models','probe'):raise ValueError('Thao tác model không hợp lệ.')
    if action=='probe':
        import re
        if not isinstance(model,str) or not re.fullmatch(r'(models/)?gemini-[A-Za-z0-9._-]{1,110}',model):
            raise ValueError('Chọn một model Gemini cụ thể trước khi thử.')
    node=shutil.which('node')
    if not node:raise ValueError('Không tìm thấy Node để kết nối Gemini.')
    try:
        result=subprocess.run([node,str(HERE/'gemini-auth-status.mjs'),action],
            input=json.dumps({'model':model}).encode('utf-8'),capture_output=True,timeout=32,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        data=json.loads(result.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise ValueError('Không kết nối được dịch vụ model Gemini hoặc quá thời gian.') from None
    if not isinstance(data,dict) or not data.get('ok'):
        raise ValueError(data.get('error','Gemini chưa phản hồi thành công.') if isinstance(data,dict) else 'Kết quả model không hợp lệ.')
    return data


def runtime_error(provider,log):
    if provider=='codex':return None
    text=log.casefold()
    if any(key in text for key in ('quota exceeded for metric','exceeded your current quota','resource_exhausted')):
        return 'Đã hết quota hoặc vượt tốc độ của '+PROVIDERS[provider]+'. Đã dừng lượt chạy, không tiếp tục retry.'
    if 'currently experiencing high demand' in text or ('status' in text and '503' in text):
        return PROVIDERS[provider]+' đang quá tải (503). Đã dừng lượt chạy; thử lại sau hoặc chọn model khác.'
    if any(key in text for key in ('api key not valid','invalid api key','unauthenticated','authentication failed')):
        return 'Thông tin đăng nhập '+PROVIDERS[provider]+' chưa hợp lệ.'
    if any(key in text for key in ('"code": 404','"code":404','status: 404')):
        return 'Model không tồn tại hoặc tài khoản chưa có quyền gọi model này (404).'
    if 'skipping system settings file' in text:
        return 'CLI từ chối cấu hình runtime. Đã dừng để tránh chạy sai quyền/công cụ.'
    return None


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('provider',choices=PROVIDERS)
    parser.add_argument('action',choices=['status','login','command'])
    args=parser.parse_args()
    if args.action=='status':print(json.dumps(diagnostic(args.provider),ensure_ascii=False))
    elif args.action=='command':print(json.dumps(command_for(args.provider)))
    else:
        command=command_for(args.provider)
        if not command:raise SystemExit('CLI chưa được cài.')
        if args.provider=='claude':command+=['auth','login']
        elif args.provider=='codex':command+=['login']
        subprocess.run(command,check=True)

