import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Send } from 'lucide-react'
import type { FocusRequest } from './OfficeActivity'
import { Canvas } from '@react-three/fiber'
import { Scene } from './TicketOffice'
import './lending-office.css'
import LendingAgents from './LendingAgents'
import TokenDashboard from './TokenDashboard'
import type { AgentRequest, LendingAgent } from './LendingAgents'

const baseLabels: Record<string,string> = {
  pm:'PM', sa:'SA', ba:'BA', backend:'BE', frontend:'FE',
  reviewer:'REVIEW', tester:'TESTER', devops:'DEVOPS', human:'Bạn',
}
const flow = ['sa','ba','backend','frontend','devops','reviewer','tester']
type Story = {
  id:number; title:string; acceptance:string; state:string; stage:number; error?:string; repair_role?:string
  workflow?:string[]; kind?:string; parent_story?:number
  module?:string; depends_on?:number[]
  tasks:Record<string,{id:number;state:string}>
  results:Record<string,{summary:string}>
  pr?:{url:string}
}
type Chat = {id:number; message:string; reply:string; state:string; role?:string}
type Handoff = {sender:string; recipient:string; text:string; at:number; story?:number; task?:number}
type State = {
  agent_requests?:AgentRequest[];agent_management_version?:number; deleted_agents?:{id:string;name:string}[]; agents?:LendingAgent[]; stories:Story[]; chat:Chat[]; messages:Handoff[]; paused:boolean
  active?:{story:number;role:string;task:number}
  preparing?:{story:number;role:string;task:number}
  project?:{identifier:string;name:string;repository:string;preview_url?:string}
  projects?:{identifier:string;name:string}[]
}
type ProgressIssue = {
  id:number; subject:string; status:string; closed:boolean; progress:number
  start_date?:string; due_date?:string; assignee?:string
  attachments:{id:number;filename:string}[]
}
type StoryProgress = {story:ProgressIssue; tasks:ProgressIssue[]}
type BoardTask = Omit<ProgressIssue,'attachments'> & {story_id:number}

function ProgressBar({issue}:{issue:Pick<ProgressIssue,'subject'|'progress'>}) {
  return <div className="lending-progress-value">
    <progress aria-label={'Tiến độ '+issue.subject} value={issue.progress} max={100}/>
    <strong>{issue.progress}%</strong>
  </div>
}

export default function LendingOffice() {
  const [state,setState] = useState<State>()
  const labels:Record<string,string> = {...baseLabels,...Object.fromEntries([...(state?.deleted_agents??[]),...(state?.agents??[])].map(a=>[a.id,a.name]))}
  const [agentQuestion,setAgentQuestion] = useState('')
  const [view,setView] = useState<'office'|'tasks'|'workflow'|'preview'|'agents'|'tokens'>('office')
  const [previewRevision,setPreviewRevision] = useState(0)
  const [showChat,setShowChat] = useState(false)
  const [board,setBoard] = useState<BoardTask[]>([])
  const [boardError,setBoardError] = useState(false)
  const [taskFilter,setTaskFilter] = useState('all')
  const [taskStatus,setTaskStatus] = useState('all')
  const [selectedTask,setSelectedTask] = useState<number>()
  const [focus,setFocus] = useState<FocusRequest>()
  const [chosen,setChosen] = useState<number>()
  const [draft,setDraft] = useState('')
  const [sending,setSending] = useState(false)
  const [pmOpen,setPmOpen] = useState(true)
  const [atLatest,setAtLatest] = useState(true)
  const pmHistory = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const [error,setError] = useState('')
  const [offline,setOffline] = useState(false)
  const [role,setRole] = useState<string>()
  const [progress,setProgress] = useState<StoryProgress>()
  const [progressError,setProgressError] = useState('')
  const story = state?.stories.find(item=>item.id===chosen)
    ?? state?.stories.find(item=>item.id===state.active?.story)
    ?? state?.stories[0]

  async function refresh() {
    try {
      const res=await fetch('/lending-api/state')
      if (!res.ok) throw Error()
      setState(await res.json())
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }

  useEffect(()=>{
    refresh()
    const timer=setInterval(refresh,2500)
    return ()=>clearInterval(timer)
  },[])

  useEffect(()=>{
    setChosen(undefined)
    setSelectedTask(undefined)
    setProgress(undefined)
    setBoard([])
    setRole(undefined)
    setFocus(undefined)
  },[state?.project?.identifier])

  useEffect(()=>{
    const controller=new AbortController()
    let timer:ReturnType<typeof setTimeout>
    async function load(){
      try {
        const response=await fetch('/lending-api/tasks',{signal:controller.signal})
        if(!response.ok) throw Error()
        setBoard(await response.json())
        setBoardError(false)
      } catch {
        if(!controller.signal.aborted) setBoardError(true)
      } finally {
        if(!controller.signal.aborted) timer=setTimeout(load,8000)
      }
    }
    void load()
    return ()=>{controller.abort();clearTimeout(timer)}
  },[state?.project?.identifier])

  const storyId = story?.id
  useEffect(()=>{
    if (view!=='workflow' || !storyId) return
    const request = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    setProgress(undefined)
    setProgressError('')
    async function loadProgress() {
      try {
        const res=await fetch('/lending-api/stories/'+storyId+'/progress',{signal:request.signal})
        if (!res.ok) throw Error('Không đọc được tiến độ từ Redmine.')
        const data:StoryProgress=await res.json()
        if (!request.signal.aborted) {
          setProgress(data)
          setProgressError('')
        }
      } catch {
        if (!request.signal.aborted) setProgressError('Không đọc được tiến độ từ Redmine. Đang thử lại…')
      }
      if (!request.signal.aborted) timer=setTimeout(loadProgress,10000)
    }
    void loadProgress()
    return ()=>{request.abort();clearTimeout(timer)}
  },[storyId,view])

  const selectedProgress = progress?.story.id===storyId ? progress : undefined
  const pmChat = state?.chat.filter(message=>!message.role || message.role==='pm') ?? []
  const latestMessage = pmChat.at(-1)

  function scrollToLatest() {
    const history = pmHistory.current
    if (history) history.scrollTop = history.scrollHeight
    followLatest.current = true
    setAtLatest(true)
  }

  useLayoutEffect(()=>{
    if (view==='office' && pmOpen && followLatest.current) scrollToLatest()
  },[view,pmOpen,latestMessage?.id,latestMessage?.reply,latestMessage?.state])

  async function send() {
    if (!draft.trim() || sending) return
    setSending(true)
    setError('')
    try {
      const res=await fetch('/lending-api/chat',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({message:draft})})
      if (!res.ok) throw Error((await res.json()).error)
      setPmOpen(true)
      scrollToLatest()
      setDraft('')
      await refresh()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không gửi được tin nhắn.')
    } finally {
      setSending(false)
    }
  }

  const active=state?.active
  const working=[active,state?.preparing].filter(Boolean)
  const selectedAgent=state?.agents?.find(a=>a.id===role)
  const selectedReady=selectedAgent?.status==='ready'&&(selectedAgent.builtin||(selectedAgent.redmine_managed&&selectedAgent.redmine_sync?.state==='synced'&&selectedAgent.redmine_sync.user_status===1))
  const currentTask=working.find(item=>item?.role===role)
  const roleTask=board.find(item=>item.id===(currentTask?.task ?? (role ? story?.tasks[role]?.id : undefined)))
  const handoff=state?.messages.slice().reverse().find(item=>item.sender!==item.recipient &&
    item.sender!=='pm' && item.recipient!=='human' && !!labels[item.sender] && !!labels[item.recipient] && item.task)
  const doneCount=board.filter(task=>task.closed).length
  const scopedTasks=board.filter(task=>taskFilter==='all' || String(task.story_id)===taskFilter)
  const activeIds=new Set(working.map(item=>item?.task))
  const taskGroup=(task:Pick<BoardTask,'id'|'closed'|'status'>)=>{
    if(task.closed) return 'done'
    if(activeIds.has(task.id)) return 'active'
    if (/blocked/i.test(task.status) || state?.stories.some(s=>s.state==='attention'&&s.tasks[s.repair_role||(s.workflow??flow)[s.stage]]?.id===task.id)) return 'blocked'
    if (/review|ready for test/i.test(task.status)) return 'review'
    return 'pending'
  }
  const visibleTasks=scopedTasks.filter(task=>taskStatus==='all'||taskGroup(task)===taskStatus)
    .sort((a,b)=>Number(activeIds.has(b.id))-Number(activeIds.has(a.id)) || b.id-a.id)
  const inspectedTask=selectedProgress?.tasks.find(task=>task.id===selectedTask)
  const blockedStory = state?.stories.find(item=>item.state==='attention' && item.error)
  const blockedRole = blockedStory?.repair_role || (blockedStory && ((blockedStory.workflow??flow)[blockedStory.stage] ?? 'devops'))
  const blockedSpeech = blockedStory?.error && blockedRole
    ? {role:blockedRole,question:'',reply:blockedStory.error,id:blockedStory.id,label:(labels[blockedRole] ?? blockedRole)+' · Đã dừng'}
    : undefined
  const pmWorking=pmChat.some(message=>message.state==='running')
  const chatting=state?.chat.find(message=>message.role!=='pm'&&message.role&&message.state==='running')
  return <main className="office-app lending-office">
    <header className="office-header">
      <a className="brand" href="/lending"><span className="brand-icon" aria-hidden="true">🧋</span><span>Trà đá AI</span></a>
      {!!state?.projects?.length&&<select className="lending-project-select" aria-label="Chọn dự án"
        value={state.project?.identifier??'club-equipment-lending'} onChange={async event=>{
          try {
            const response=await fetch('/lending-api/projects/select',{method:'POST',
              headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier:event.target.value})})
            if(!response.ok) throw Error('Không chuyển được dự án.')
            await refresh()
          } catch(e){setError(String(e))}
        }}>
        {state.projects.map(project=><option key={project.identifier} value={project.identifier}>{project.name}</option>)}
      </select>}
      <div className="lending-kpis" aria-label="Tổng quan dự án">
        <span><b>{state?.agents?.filter(a=>!['archived','terminated'].includes(a.status)).length??8}</b>Agent</span>
        <span><b>{working.length+Number(!!pmWorking)}</b>Đang làm</span>
        <span><b>{boardError?'—':doneCount+'/'+board.length}</b>Task đóng</span>
        <span><b>{state?.stories.filter(item=>item.state==='attention').length ?? '—'}</b>Cần xử lý</span>
      </div>
      <nav className="lending-actions">
        <button aria-current={view==='agents'?'page':undefined} onClick={()=>{setShowChat(false);setView(view==='agents'?'office':'agents')}}>Agents</button>
        <button aria-current={view==='office'?'page':undefined} onClick={()=>{setView('office');setShowChat(false)}}>Office</button>
        <button aria-current={view==='tasks'?'page':undefined} onClick={()=>{setShowChat(false);setView(view==='tasks'?'office':'tasks')}}>Task</button>
        <button aria-pressed={view==='office'&&showChat} onClick={()=>{setShowChat(view!=='office'||!showChat);setView('office')}}>Communication</button>
        <button aria-current={view==='workflow'?'page':undefined} onClick={()=>{setShowChat(false);setSelectedTask(undefined);setView(view==='workflow'?'office':'workflow')}}>Workflow</button>
        <button aria-pressed={view==='preview'} onClick={()=>{setShowChat(false);setView(view==='preview'?'office':'preview')}}>Preview</button>
        <button aria-current={view==='tokens'?'page':undefined} onClick={()=>{setShowChat(false);setView(view==='tokens'?'office':'tokens')}}>Quản lý token</button>
      </nav>
      <span className="lending-health">{offline?'Mất kết nối':state?.paused?((active||state.preparing)?'Đang dừng':'Đã tạm dừng'):'Dịch vụ trực tuyến'}</span>
      <a href={'http://localhost:3000/projects/'+(state?.project?.identifier??'club-equipment-lending')} target="_blank" rel="noreferrer">Redmine ↗</a>
    </header>

      <div className="scene"><Canvas shadows camera={{position:[14,25,29],fov:43}} dpr={[1,1.6]}>
        <Scene key={state?.project?.identifier} onboardingPaused={view==='agents'} lending roster={state?.agents} alive={!offline} onPick={setRole} speech={blockedSpeech} focus={focus} handoff={handoff}
          chatRole={chatting?.role??(pmWorking?'pm':active?.role)}
          preparingRole={state?.preparing?.role} preparingTask={state?.preparing && 'Chuẩn bị Task #'+state.preparing.task}
          chatTask={active ? 'Task #'+active.task : 'Đang trả lời người điều hành'}/>
      </Canvas></div>
    {view==='agents' && <LendingAgents key={state?.project?.identifier} agents={state?.agents??[]} requests={state?.agent_requests??[]} managementVersion={state?.agent_management_version} chats={state?.chat??[]} work={state?.stories.map(s=>({id:s.id,title:s.title,state:s.state,stage:s.stage,kind:s.kind,roles:Object.keys(s.tasks)}))??[]} project={state?.project?.identifier} onRefresh={refresh} onClose={()=>setView('office')} onFocus={id=>{setRole(id);setFocus({role:id,revision:Date.now()});setView('office')}}/>}
    {view==='tokens' && <TokenDashboard key={state?.project?.identifier} agents={state?.agents??[]} project={state?.project?.identifier} onClose={()=>setView('office')}/>}
    {view==='office' && showChat && <section className="task-panel lending-handoffs">
        <div className="panel-head"><h2>Trao đổi của đội</h2>
          <button className="close" onClick={()=>setShowChat(false)} aria-label="Đóng hội thoại">×</button></div>
        <div className="panel-scroll">
          {!state?.messages.length && <p>Chưa có cuộc trao đổi nào giữa các agent.</p>}
          {[...(state?.messages ?? [])].reverse().map((message,i)=><article className="task-row" key={message.at+'-'+i}>
            <div className="lending-message-meta"><b>{labels[message.sender] ?? message.sender} → {labels[message.recipient] ?? message.recipient}</b>
              <time dateTime={new Date(message.at*1000).toISOString()}>{new Date(message.at*1000).toLocaleString('vi-VN')}</time></div>
            {message.story && <a href={'http://localhost:3000/issues/'+(message.task??message.story)} target="_blank" rel="noreferrer">
              Story #{message.story}{message.task ? ' · Task #'+message.task : ''} ↗</a>}
            <p>{message.text}</p>
          </article>)}
        </div>
      </section>}
      {role && <aside className="agent-inspector lending-inspector">
        <button className="close" onClick={()=>{setRole(undefined);setFocus(undefined)}} aria-label="Đóng thông tin vai trò">×</button>
        <h2>{labels[role]??role}</h2>
        <p>{state?.agents?.find(a=>a.id===role)?.title}</p>
        <p>{selectedAgent&&!selectedAgent.builtin&&selectedAgent.redmine_sync?.state!=='synced'?'Chờ đồng bộ Redmine':({draft:'Chưa kiểm tra',ready:'Sẵn sàng',paused:'Tạm dừng',archived:'Đã lưu trữ',terminated:'Đã chấm dứt'})[state?.agents?.find(a=>a.id===role)?.status??'ready']}</p>
        {roleTask ? <>
          <a href={'http://localhost:3000/issues/'+roleTask.id} target="_blank" rel="noreferrer">#{roleTask.id} · {roleTask.subject}</a>
          <p>{currentTask?'Đang xử lý':roleTask.status}</p>
          <ProgressBar issue={roleTask}/>
        </> : <p>{currentTask?'Đang xử lý Task #'+currentTask.task:'Đang chờ phân công'}</p>}
        <button className="full-button" aria-pressed={focus?.role===role} onClick={()=>setFocus(focus?.role===role?undefined:{role,revision:Date.now()})}>{focus?.role===role?'◎ Bỏ focus':'◎ Focus'}</button>
        {role!=='pm'&&<form className="lending-agent-question" onSubmit={async event=>{
          event.preventDefault();setSending(true);setError('')
          try {
            const res=await fetch('/lending-api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,message:agentQuestion,project:state?.project?.identifier})})
            const data=await res.json();if(!res.ok)throw Error(data.error)
            setAgentQuestion('');setShowChat(true);setView('office');await refresh()
          }catch(e){setError(String(e))}finally{setSending(false)}
        }}><label>Hỏi {labels[role]}<textarea required maxLength={6000} value={agentQuestion} onChange={e=>setAgentQuestion(e.target.value)}/></label><button disabled={sending||!selectedReady}>Gửi câu hỏi</button></form>}
      </aside>}
      <section className="command-dock pm-messenger" aria-label="Chat riêng với PM">
        <button type="button" className="pm-messenger-header" aria-expanded={pmOpen} onClick={()=>{
          followLatest.current = true
          setPmOpen(!pmOpen)
        }}>
          <span className="pm-avatar" aria-hidden="true">PM</span>
          <span className="pm-messenger-name"><strong>PM</strong><small>
            {offline?'Mất kết nối':pmWorking?'Đang trả lời…':'Điều phối dự án'}
          </small></span>
          {pmOpen ? <ChevronDown size={18}/> : <ChevronUp size={18}/>}
        </button>
        {pmOpen && <>
        <div className="pm-history-wrap">
          <div className="pm-history" ref={pmHistory} role="log" aria-label="Lịch sử với PM"
            onScroll={event=>{
              const history=event.currentTarget
              const nearBottom=history.scrollHeight-history.clientHeight-history.scrollTop<32
              followLatest.current=nearBottom
              setAtLatest(nearBottom)
            }}>
            {!pmChat.length && <p className="pm-chat-empty">Nhắn PM để hỏi hoặc giao việc cho đội.</p>}
            {pmChat.map(item=><div className="pm-exchange" key={item.id}>
              <div className="pm-message-row pm-outgoing"><p className="pm-bubble"><span className="pm-sr-only">Bạn: </span>{item.message}</p></div>
              <div className="pm-message-row">
                <span className="pm-avatar pm-avatar-small" aria-hidden="true">PM</span>
                <p className={item.reply?'pm-bubble':'pm-bubble pm-pending'}>
                  <span className="pm-sr-only">PM: </span>{item.reply
                    ? item.reply.split(/(http:\/\/localhost:3000\/issues\/\d+)/g).map((part,index)=>
                      index%2 ? <a key={index} href={part} target="_blank" rel="noreferrer">Mở #{part.split('/').at(-1)} ↗</a> : part)
                    : item.state==='running'?'Đang trả lời…':'Đang chờ xử lý…'}
                </p>
              </div>
            </div>)}
          </div>
          {!atLatest && <button type="button" className="pm-jump" onClick={scrollToLatest}>↓ Về tin mới nhất</button>}
        </div>
        <form className="pm-compose" onSubmit={event=>{event.preventDefault();void send()}}>
          <input aria-label="Nhắn PM" placeholder="Hỏi PM về dự án hoặc giao việc…" maxLength={6000} value={draft} onChange={e=>setDraft(e.target.value)}/>
          <button type="submit" disabled={offline||sending||!draft.trim()} aria-label="Gửi PM"><Send size={16}/></button>
        </form>
        {error && <p className="chat-error" role="alert">{error}</p>}
        <div className="dock-bottom"><button onClick={()=>{setView('office');setShowChat(true)}}>Trao đổi của đội</button><button onClick={()=>{setShowChat(false);setSelectedTask(undefined);setView('workflow')}}>Mở Workflow →</button></div>
        </>}
      </section>
    {view==='preview' && <section className="task-panel lending-preview" aria-label="Preview website">
      <div className="lending-preview-header">
        <div><h2>Preview website</h2><small>Bản mới nhất từ main</small></div>
        <div className="lending-preview-actions">
          <button onClick={()=>setPreviewRevision(value=>value+1)}>↻ Tải lại</button>
          {state?.project?.preview_url&&<a href={state.project.preview_url} target="_blank" rel="noreferrer">Mở riêng ↗</a>}
          <button onClick={()=>setView('office')} aria-label="Đóng Preview">×</button>
        </div>
      </div>
      {state?.project?.preview_url?<iframe key={(state.project.identifier??'')+previewRevision} title={'Bản chạy thử '+state.project.name}
        src={state.project.preview_url} sandbox="allow-scripts allow-forms allow-same-origin" />:<p>Ứng dụng đang được chuẩn bị. Preview sẽ có khi bản build đầu tiên sẵn sàng.</p>}
    </section>}
    {view==='tasks' && <section className="task-panel lending-side-panel">
      <div className="lending-panel-header"><h2>Tasks</h2>
        <button className="close" onClick={()=>setView('office')} aria-label="Đóng Tasks">×</button>
        <select aria-label="Lọc task theo Story" value={taskFilter} onChange={e=>setTaskFilter(e.target.value)}>
          <option value="all">Tất cả Story</option>
          {state?.stories.map(item=><option key={item.id} value={item.id}>#{item.id} · {item.title}</option>)}
        </select>
        <div className="lending-task-filters">
          {[['all','Tất cả'],['active','Đang làm'],['pending','Đang chờ'],['review','Chờ duyệt'],['blocked','Cần xử lý'],['done','Đã xong']].map(([key,title])=>
            <button key={key} aria-pressed={taskStatus===key} onClick={()=>setTaskStatus(key)}>
              {title} <small>{key==='all'?scopedTasks.length:scopedTasks.filter(t=>taskGroup(t)===key).length}</small>
            </button>)}
        </div>
      </div>
      <div className="panel-scroll lending-panel-body">
        {boardError && <p role="status">Không tải được task từ Redmine. Đang thử lại…</p>}
        {!boardError&&!visibleTasks.length&&<p>Chưa có task trong mục này.</p>}
        {visibleTasks.map(task=><button className={'lending-task-card tone-'+taskGroup(task)} key={task.id} onClick={()=>{
          setChosen(state?.stories.find(item=>item.kind==='task'&&item.id===task.id)?.id??task.story_id);setSelectedTask(task.id);setView('workflow')
        }}>
          <span className="lending-card-meta"><small>#{task.id}</small><span className={'lending-status '+taskGroup(task)}>{taskGroup(task)==='blocked'?'Cần xử lý':task.status}</span></span>
          <strong>{task.subject}</strong>
          <ProgressBar issue={task}/>
          <small>{task.assignee ?? 'Chưa phân công'}</small>
        </button>)}
      </div>
    </section>}
    {view==='workflow' && <section className="task-panel lending-side-panel">
      <div className="lending-panel-header">
        <button className="lending-back" onClick={()=>setView('tasks')}>← Tasks</button>
        <button className="close" onClick={()=>setView('office')} aria-label="Đóng Workflow">×</button>
        <h2>Workflow</h2>
        {story&&<select aria-label="Chọn Story" value={story.id} onChange={event=>{
          setSelectedTask(undefined);setChosen(Number(event.target.value))
        }}>
          {state?.stories.map(item=><option key={item.id} value={item.id}>{item.kind==='task'?'Task':'Story'} #{item.id} · {item.title}{item.parent_story?' · Story #'+item.parent_story:''}</option>)}
        </select>}
      </div>
      <div className="panel-scroll lending-panel-body">
        {story ? <>
          <div className="lending-workflow-summary">
            {story.module&&<p>{story.module}</p>}
            {!!story.depends_on?.length&&<p>Phụ thuộc {story.depends_on.map(id=><button key={id}
              onClick={()=>{setChosen(id);setSelectedTask(undefined)}}>#{id}</button>)}</p>}
            {progressError && <p role="status">{progressError}</p>}
            {!selectedProgress&&!progressError&&<p>Đang tải tiến độ từ Redmine…</p>}
            {selectedProgress&&<><span className="lending-card-meta"><small>#{(inspectedTask??selectedProgress.story).id}</small>
              <span className="lending-status">{(inspectedTask??selectedProgress.story).status}</span></span>
              <h3>{(inspectedTask??selectedProgress.story).subject}</h3>
              <ProgressBar issue={inspectedTask??selectedProgress.story}/>
            </>}
            {story.error && <p className="chat-error">{story.error}</p>}
          </div>
          <h3 className="lending-section-label">Luồng bàn giao</h3>
          <ol className="lending-steps">{(story.workflow??flow).map(item=>{
            const step=story.tasks[item]
            const isRunning=working.some(x=>x?.story===story.id&&x.role===item)
            const done=step?.state==='done'||step?.state==='delivered'
            return <li key={item} className={isRunning?'is-running':done?'is-delivered':''}>
              <span aria-hidden="true">{done?'✓':isRunning?'●':'○'}</span><b>{labels[item]}</b>
              <small>{isRunning?'Đang xử lý':done?'Đã bàn giao':'Đang chờ'}</small>
            </li>
          })}</ol>
          <h3 className="lending-section-label">Task con{selectedProgress && ' · '+selectedProgress.tasks.length}</h3>
          {selectedProgress?.tasks.map(task=><article className={'lending-task-card tone-'+taskGroup(task)+' '+(selectedTask===task.id?'is-selected':'')} key={task.id}>
            <span className="lending-card-meta"><small>#{task.id}</small><span className={'lending-status '+taskGroup(task)}>{taskGroup(task)==='blocked'?'Cần xử lý':task.status}</span></span>
            <a href={'http://localhost:3000/issues/'+task.id} target="_blank" rel="noreferrer">{task.subject} ↗</a>
            <ProgressBar issue={task}/>
            {task.attachments.map(file=><a className="artifact" key={file.id}
              href={'http://localhost:3000/attachments/'+file.id} target="_blank" rel="noreferrer">↳ {file.filename} ↗</a>)}
          </article>)}
          {story.pr && <a href={story.pr.url} target="_blank" rel="noreferrer">Mở PR ↗</a>}
        </> : <p>Chưa có Story. PM sẽ tạo kế hoạch khi nhận đề bài.</p>}
      </div>
    </section>}
  </main>
}

