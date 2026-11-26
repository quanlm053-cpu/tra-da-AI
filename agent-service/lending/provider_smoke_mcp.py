"""Isolated read-only MCP fixture for runtime verification. No Redmine or network access."""
import json
import sys
from pathlib import Path

state=Path(sys.argv[1])
for line in sys.stdin:
    try:
        request=json.loads(line)
        if 'id' not in request:continue
        method=request.get('method')
        if method=='initialize':
            result={'protocolVersion':request.get('params',{}).get('protocolVersion','2025-06-18'),
                    'capabilities':{'tools':{}},'serverInfo':{'name':'runtime-check','version':'1.0'}}
        elif method=='ping':result={}
        elif method=='tools/list':
            result={'tools':[{'name':'project_state','description':'Read the synthetic runtime check state.',
                'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
                'annotations':{'readOnlyHint':True}}]}
        elif method=='tools/call' and request.get('params',{}).get('name')=='project_state':
            data=json.loads(state.read_text(encoding='utf-8'))
            with state.with_suffix('.audit').open('a',encoding='utf-8') as audit:audit.write('project_state\n')
            result={'content':[{'type':'text','text':json.dumps({'check_token':data['token'],'synthetic':True})}]}
        else:
            print(json.dumps({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Method not found'}}),flush=True);continue
        print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
    except (ValueError,KeyError,TypeError):continue
