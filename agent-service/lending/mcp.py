"""Project-scoped stdio MCP tools used by every lending agent."""
import json
import sys
from pathlib import Path

from office import PROJECT, HERE, Redmine, json_file
from issue_catalog import project_issues, compact, folded

state_path = Path(sys.argv[1])
tools = [
    {'name':'project_state','description':'Verify the Redmine project and read the current plan, assignments and latest handoffs.',
     'inputSchema':{'type':'object','properties':{}}},
    {'name':'read_issue','description':'Read a Redmine Story or Task in the equipment lending project.',
     'inputSchema':{'type':'object','properties':{'id':{'type':'integer'}},'required':['id']}},
    {'name':'search_issues','description':'Find existing stories and child tasks in the project, including closed issues. Use before creating work.',
     'inputSchema':{'type':'object','properties':{
         'query':{'type':'string'}, 'parent_id':{'type':'integer','minimum':1},
         'offset':{'type':'integer','minimum':0}},'additionalProperties':False}},
]
for tool in tools:
    tool['annotations'] = {'readOnlyHint': True}
enabled = set(json.loads(sys.argv[2])) if len(sys.argv)>2 else {t['name'] for t in tools}
tools = [t for t in tools if t['name'] in enabled]


def respond(method, params):
    if method=='initialize':
        return {'protocolVersion':params.get('protocolVersion','2025-06-18'),
                'capabilities':{'tools':{}},'serverInfo':{'name':'club-equipment-lending','version':'1.0.0'}}
    if method=='tools/list':
        return {'tools':tools}
    if method=='ping':
        return {}
    if method=='tools/call':
        try:
            if params.get('name') not in enabled:
                raise ValueError('Công cụ chưa được cấp cho agent này.')
            api=Redmine(json_file(HERE.parent/'config.json'))
            state=json_file(state_path)
            project=state.get('project',{}).get('redmine_project_id',PROJECT)
            if params['name']=='project_state':
                result={k:state[k] for k in ('brief','stories','paused','active')}
                result['project']=state.get('project',{})
                result['messages']=state['messages'][-25:]
                try:
                    details=api.request('GET',f'/projects/{project}.json')['project']
                    result['redmine_project']={k:details[k] for k in ('id','name','identifier')}
                    result['redmine_project']['url']=f'{api.config["redmine_url"]}/projects/{details["identifier"]}'
                except Exception:
                    result['redmine_error']='Không xác minh được dự án trên Redmine.'
            elif params['name']=='read_issue':
                issue_id=int(params['arguments']['id'])
                result=api.issue(issue_id)
                if result['project']['id']!=project:
                    raise ValueError('Issue ngoài dự án.')
            elif params['name']=='search_issues':
                args=params.get('arguments',{})
                query=folded(args.get('query','')).strip()
                parent=args.get('parent_id')
                offset=int(args.get('offset',0))
                if offset<0:
                    raise ValueError('offset phải không âm.')
                rows=[issue for issue in project_issues(api, project)
                      if (not parent or issue.get('parent',{}).get('id')==parent)
                      and (not query or query in folded(issue['subject']+' '+(issue.get('description') or '')))]
                result={'total':len(rows),'offset':offset,'issues':[
                    {**compact(issue),'description':(issue.get('description') or '')[:1500]}
                    for issue in rows[offset:offset+25]]}
            else:
                raise ValueError('Công cụ không tồn tại.')
            return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError':True,'content':[{'type':'text','text':str(exc)}]}
    raise ValueError('Unknown method')


if __name__=='__main__':
    for line in sys.stdin:
        try:
            request=json.loads(line)
        except ValueError:
            continue
        if 'id' not in request:
            continue
        reply={'jsonrpc':'2.0','id':request['id']}
        try:
            reply['result']=respond(request['method'],request.get('params',{}))
        except Exception:
            reply['error']={'code':-32601,'message':'Method not found'}
        print(json.dumps(reply),flush=True)
