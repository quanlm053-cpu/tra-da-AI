"""Concurrent isolated specialists; promote only validated, non-overlapping edits."""
import copy
import hashlib
import shutil
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED

ROLES=('backend','frontend','ba','qa','reviewer')
TASKS={'backend':'Triển khai / kiểm tra API và backend tests',
       'frontend':'Triển khai giao diện theo hợp đồng API',
       'ba':'Rà yêu cầu, hỗ trợ dev; chưa thay baseline hợp đồng',
       'qa':'Chuẩn bị kịch bản kiểm thử; chưa nghiệm thu bản tích hợp',
       'reviewer':'Rà sơ bộ baseline; chưa phải review code cuối'}

class ParallelError(Exception):pass

def files(repo):
    from controller import run_git
    names=run_git(repo,'ls-files','--cached','--others','--exclude-standard').splitlines()
    result={}
    for name in names:
        if name=='next-env.d.ts' or name.endswith('.tsbuildinfo'):continue # Generated build caches.
        path=Path(repo)/name
        if path.is_file():
            if not path.resolve().is_relative_to(Path(repo).resolve()):raise ParallelError('Symlink outside checkout: '+name)
            result[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def allowed(name,role,job):
    if role=='reviewer':return False
    if role in ('ba','qa'):return name==f'docs/ai/story-{job["id"]}/parallel/{role}.md'
    prefixes=('backend/','database/') if role=='backend' else ('app/','components/','hooks/','lib/','styles/','public/','tests/')
    if name.startswith(prefixes):return True
    if role=='frontend' and name in ('package.json','package-lock.json','tsconfig.json','next.config.mjs','next.config.ts'):return True
    if role=='frontend' and '/' not in name and name.startswith('tsconfig.') and name.endswith('.json'):return True
    if name.startswith(f'docs/ai/story-{job["id"]}/'):
        if name.startswith(f'docs/ai/story-{job["id"]}/{role}/'):return True
        file=Path(name).name
        ids=[str(t['issue_id']) for t in job.get('plan',[]) if t['role']==role]
        return file.startswith(role) or any(file.startswith('task-'+i+'.') or file.startswith('task-'+i+'-') for i in ids)
    return False

def prepare_lane(service,job,role,wave,baseline):
    from controller import run_git
    source=service.checkout(job)
    lane=service.runtime/'parallel'/f'story-{job["id"]}'/wave/role
    lane.parent.mkdir(parents=True,exist_ok=True)
    run_git(service.repo,'worktree','add','--detach',str(lane),'HEAD')
    # Overlay all current dirty/untracked source, preserving interrupted work.
    tracked=run_git(lane,'ls-files').splitlines()
    for name in tracked:
        if name not in baseline and name!='next-env.d.ts':
            target=lane/name
            if target.is_file() and target.resolve().is_relative_to(lane.resolve()):target.unlink()
    for name in baseline:
        target=lane/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    return lane

def promote(source,baseline,lanes,job):
    current=files(source)
    edits={}
    for role,lane in lanes.items():
        after=files(lane)
        for name in set(baseline)|set(after):
            if baseline.get(name)==after.get(name):continue
            if not allowed(name,role,job):raise ParallelError(f'{role} changed outside owned scope: {name}; isolated edits retained')
            if name in edits:raise ParallelError('Concurrent changes conflict: '+name)
            if current.get(name)!=baseline.get(name):raise ParallelError('Main checkout changed during parallel work: '+name)
            edits[name]=(lane/name,after.get(name))
    # Validate everything before writing any merged file.
    for name,(origin,digest) in edits.items():
        target=Path(source)/name
        if not target.resolve().is_relative_to(Path(source).resolve()):raise ParallelError('Merge path escapes checkout')
        if digest is None:target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
    return sorted(edits)

def instruction(role,job):
    folder=f'docs/ai/story-{job["id"]}/parallel'
    if role in ('ba','qa','reviewer'):
        task={'ba':'Review requirements and API assumptions. Identify concrete ambiguities for the developers without changing the existing contract.',
              'qa':'Prepare an actionable test matrix from requirements and existing code. Do NOT perform final acceptance testing or run servers while devs implement.',
              'reviewer':'Perform a preliminary static risk audit on this snapshot. This is NOT the final integrated review; identify files/risks to recheck after merge.'}[role]
        return (task+f'\nOnly write {folder}/{role}.md (reviewer remains read-only; put findings in summary). '
            'Return completed_tasks=[], task_plan=[], bugs=[]. Passed means this preparation only, never Story acceptance. '
            'Do not modify implementation, shared requirements, packages, ports or databases.')
    owned='backend/, database/ and backend test files' if role=='backend' else 'app/, components/, hooks/, lib/, styles/, public/, tests/ and root frontend package/config files'
    return (f'You run concurrently in an isolated copy. Own only {owned} and your own task/handoff Markdown documents. '
        'Do not edit another role\'s files or shared requirements.md. Other lanes cannot see your unmerged changes. '
        'Follow the existing requirements API contract; record a proposed contract change in your handoff rather than silently changing it. '
        'Install local dependencies using npm ci --ignore-scripts if needed; do not use global installs or start shared servers. '
        'Do not redo already completed tasks without concrete regression evidence. Preserve completed work and inspect the current source. '
        'Run focused local build/unit checks. Treat missing live DB/services as unavailable environment, not proven product defects. '
        'The controller will merge your edits and attach products only after all lanes stop; final reviewer/QA execute on the merged tree.')

def run_wave(service,job,roles=ROLES,invoke=None):
    from controller import Service,Hold
    if job.get('calls',0)+len(roles)>service.config['max_agent_calls_per_story']:
        raise Hold('Not enough agent calls remaining for parallel wave; inspect budget before retry')
    source=service.checkout(job)
    baseline=files(source)
    wave=uuid.uuid4().hex[:10]
    lanes={role:prepare_lane(service,job,role,wave,baseline) for role in roles}
    import json
    (service.runtime/'parallel'/f'story-{job["id"]}'/wave/'baseline.json').write_text(json.dumps(baseline),encoding='utf-8')
    job['calls']=job.get('calls',0)+len(roles)
    job['running_roles']=list(roles);job['parallel_tasks']=TASKS
    job['parallel_wave']=wave
    service.save(job)
    service.api.update(job['id'],notes='[AI:team] Bắt đầu song song: '+', '.join(roles)+'. Mỗi vai trò có checkout riêng; review/QA cuối chạy sau khi ghép code.')
    def execute(role):
        if invoke:return invoke(role,lanes[role])
        worker=Service()
        try:return worker.agent(copy.deepcopy(job),role,parallel={'worktree':str(lanes[role]),'label':f'parallel-{wave}-{role}','instruction':instruction(role,job)})
        finally:worker.db.close()
    results={};errors={}
    try:
        with ThreadPoolExecutor(max_workers=len(roles)) as pool:
            pending={pool.submit(execute,role):role for role in roles}
            while pending:
                (service.runtime/'heartbeat').write_text(str(time.time()))
                done,_=wait(pending,timeout=3,return_when=FIRST_COMPLETED)
                for future in done:
                    role=pending.pop(future)
                    try:results[role]=future.result()
                    except Exception as exc:errors[role]=str(exc) if type(exc).__name__ in ('Hold','Cancelled') else type(exc).__name__
                    job['running_roles']=[r for r in job['running_roles'] if r!=role]
                    job.setdefault('parallel_results',{}).update(results)
                    service.save(job)
    finally:
        job['running_roles']=[];service.save(job)
    if errors:raise Hold('Parallel lanes stopped; edits retained: '+str(errors))
    service.story(job)
    try:merged=promote(source,baseline,lanes,job)
    except ParallelError as exc:raise Hold(str(exc)) from None
    job['parallel_merged_files']=merged
    for role in ('backend','frontend'):
        if role not in results:continue
        result=results[role]
        job.setdefault('results',{})[role]=result
        service.save(job)
        service.completed_tasks(job,role,result)
        service.api.update(job['id'],notes=f'[AI:{role}] Bàn giao từ lane song song: {result["outcome"]}\n\n'+result['summary'])
    service.save(job)
    for role in ('backend','frontend'):
        if role in results and results[role]['outcome']!='passed':
            raise Hold(role+' needs follow-up after parallel merge: '+results[role]['summary'])
        if role in results:
            for task in job.get('plan',[]):
                if task['role']==role and task['issue_id']>0:
                    child=service.api.issue(task['issue_id'])
                    if not any(a.get('filename','').startswith(f'task-{child["id"]}-') for a in child.get('attachments',[])):
                        raise Hold(f'Task #{child["id"]}: passed lane has no attached product')
    return results
