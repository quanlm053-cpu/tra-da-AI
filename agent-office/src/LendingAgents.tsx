import { useEffect, useState } from 'react'
import AgentSetup,{editable} from './AgentSetup'
import type {Setup,SetupOptions} from './AgentSetup'

export type LendingAgent = Partial<Setup> & {
  id:string; name:string; title:string; specialty:string; instructions:string
  builtin:boolean; status:'draft'|'ready'|'paused'|'archived'|'terminated'; access:'read'|'write'
  color:string; redmine_user_id:number|null; revision:number
  redmine_managed?:boolean
  redmine_sync?:{state:string;error?:string;login?:string;role_name?:string;user_status?:number;updated_at?:number}
}
const statuses = {draft:'Chưa kiểm tra', ready:'Sẵn sàng', paused:'Tạm dừng', archived:'Đã lưu trữ',terminated:'Đã chấm dứt'}
export type AgentRequest = {id:string;agent:string;type:string;state:string;title:string;instructions:string;error?:string}
type AgentWork = {id:number;title:string;state:string;stage:number;kind?:string;roles:string[]}
type AgentEvent = {operation:string;name:string;at:number;revision:number;status?:string;fields?:string[]}
const blank = {name:'',title:'',specialty:'specialist',instructions:'',access:'read' as const,color:'#a78bfa'}

export default function LendingAgents({agents,project,work=[],chats=[],requests=[],managementVersion,onRefresh,onFocus,onClose}:{
  agents:LendingAgent[]; project?:string; onRefresh:()=>Promise<void>
  work?:AgentWork[]; managementVersion?:number; requests?:AgentRequest[]
  chats?:{id:number;role?:string;message:string;state:string}[]
  onFocus:(id:string)=>void; onClose:()=>void
}) {
  const [selected,setSelected] = useState<string>()
  const [form,setForm] = useState<Partial<LendingAgent>>(blank)
  const [options,setOptions]=useState<SetupOptions>({models:[],adapters:[],tools:[],skills:[]})
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [busyMessage,setBusyMessage] = useState('')
  const [failure,setFailure] = useState('')
  const [archived,setArchived] = useState(false)
  const [query,setQuery] = useState('')
  const [statusFilter,setStatusFilter] = useState('all')
  const [history,setHistory] = useState<AgentEvent[]>([])
  const [historyError,setHistoryError] = useState('')
  const [confirmation,setConfirmation] = useState<'terminate'|'delete'>()
  const [confirmName,setConfirmName] = useState('')
  const [transferTo,setTransferTo] = useState('')
  const [task,setTask] = useState({story:'',title:'',acceptance:''})
  const [requestId,setRequestId] = useState(()=>crypto.randomUUID())
  const current = agents.find(a=>a.id===selected)
  const inactive = current?.status==='archived'||current?.status==='terminated'
  const apiReady = managementVersion===4
  const syncing = ['pending','provisioning'].includes(current?.redmine_sync?.state??'')
  const canWork = current?.status==='ready'&&(current.builtin||
    (current.redmine_managed&&current.redmine_sync?.state==='synced'&&current.redmine_sync.user_status===1))
  const pending = work.filter(w=>w.roles.includes(selected??'')&&!['done','cancelled'].includes(w.state))
  const pendingChats = chats.filter(c=>c.role===selected&&['queued','running'].includes(c.state))
  const replacements = agents.filter(a=>a.id!==selected&&a.status==='ready'&&a.specialty===current?.specialty&&a.access===current?.access&&
    (a.builtin||(a.redmine_managed&&a.redmine_sync?.state==='synced'&&a.redmine_sync.user_status===1)))
  const visible = agents.filter(a=>(archived||!['archived','terminated'].includes(a.status))&&
    (statusFilter==='all'||a.status===statusFilter)&&
    [a.name,a.title,a.specialty,a.role,a.description,...(a.tags??[])].join(' ').toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi')))
  const dirty = !!current && JSON.stringify(editable(form))!==JSON.stringify(editable(current))

  useEffect(()=>{
    const controller=new AbortController()
    fetch('/lending-api/agents/options?'+new URLSearchParams(project?{project}:{}),{signal:controller.signal})
      .then(async r=>{if(!r.ok)throw Error('Chưa đọc được cấu hình runtime/skill.');setOptions(await r.json())})
      .catch(e=>{if(!controller.signal.aborted)setFailure(String(e))})
    return ()=>controller.abort()
  },[project])

  useEffect(()=>{
    setHistory([]);setHistoryError('')
    if(!selected)return
    const controller=new AbortController()
    fetch('/lending-api/agents/history?'+new URLSearchParams({id:selected,...(project?{project}:{})}),{signal:controller.signal})
      .then(async r=>{if(!r.ok)throw Error('Chưa đọc được lịch sử thay đổi.');setHistory(await r.json())})
      .catch(e=>{if(!controller.signal.aborted)setHistoryError(String(e))})
    return ()=>controller.abort()
  },[project,selected,current?.revision,current?.redmine_sync?.updated_at])

  function choose(agent?:LendingAgent) {
    setSelected(agent?.id); setForm(agent?{...agent}:{...blank})
    setMessage('');setFailure('');setTask({story:'',title:'',acceptance:''});setRequestId(crypto.randomUUID())
    setConfirmation(undefined);setConfirmName('');setTransferTo('')
  }
  async function act(operation:string,extra:Record<string,unknown>={}) {
    setBusy(true);setFailure('');setMessage('')
    setBusyMessage(operation==='verify'||operation==='resume'?'Đang kiểm tra runtime và kích hoạt agent…':operation==='sync'?'Đang đồng bộ Redmine…':'Đang lưu thay đổi…')
    try {
      const payload = operation==='save'?{...form,id:selected}:operation==='assign'
        ?{id:selected,story_id:Number(task.story),title:task.title,acceptance:task.acceptance,request_id:requestId}
        :{id:selected,revision:current?.revision,confirm_name:confirmName,...extra}
      const response=await fetch('/lending-api/agents',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...payload,operation,project})})
      const result=await response.json()
      if(!response.ok) throw Error(result.error||'Không cập nhật được agent.')
      if(operation==='assign'||operation==='reassign'||operation==='cancel_chat'||operation==='review_request') {
        setMessage(result.message)
        if(operation==='assign'){setRequestId(crypto.randomUUID());setTask({story:'',title:'',acceptance:''})}
      } else if(operation==='delete') {
        choose()
        setMessage('Đã xóa hồ sơ '+result.name+'. Lịch sử công việc vẫn được giữ.'+(result.warning?' '+result.warning:''))
      } else {
        setSelected(result.id);setForm(result)
        setMessage((['pending','provisioning'].includes(result.redmine_sync?.state)?'Đã lưu hồ sơ. Đang tự động đồng bộ tài khoản và quyền trên Redmine; agent chưa nhận việc trong lúc này.':operation==='verify'||operation==='resume'?'Cấu hình hợp lệ. Agent có thể nhận việc; đăng nhập/model được xác nhận khi chạy thực tế.':operation==='restore'?'Đã khôi phục về bản nháp. Kiểm tra cấu hình trước khi kích hoạt.':operation==='duplicate'?'Đã tạo bản sao ở trạng thái nháp.':'Đã lưu thay đổi.')+(result.warning?' '+result.warning:''))
      }
      setConfirmation(undefined);setConfirmName('')
      await onRefresh()
    } catch(e){setFailure(e instanceof Error?e.message:'Không xác nhận được kết quả. Tải lại danh sách trước khi thử lại.')}
    finally {setBusy(false);setBusyMessage('')}
  }
  return <section className="task-panel lending-agent-manager" aria-label="Quản lý agent">
    <div className="lending-panel-header"><h2>Agents <small>{agents.filter(a=>!['archived','terminated'].includes(a.status)).length}</small></h2>
      <button className="close" aria-label="Đóng Agents" onClick={onClose}>×</button></div>
    <div className="lending-agent-layout">
      <div className="lending-agent-list">
        <button className="full-button" disabled={busy} onClick={()=>choose()}>＋ Thêm agent</button>
        <label className="lending-agent-search">Tìm agent<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Tên hoặc chuyên môn"/></label>
        <label className="lending-agent-search">Trạng thái<select value={statusFilter} onChange={e=>{setStatusFilter(e.target.value);if(['archived','terminated'].includes(e.target.value))setArchived(true)}}>
          <option value="all">Tất cả</option>{Object.entries(statuses).map(([id,text])=><option key={id} value={id}>{text}</option>)}
        </select></label>
        <label className="lending-agent-archive"><input type="checkbox" checked={archived} onChange={e=>setArchived(e.target.checked)}/> Hiện lưu trữ</label>
        {!visible.length&&<p className="lending-agent-note">Không có agent phù hợp.</p>}
        {visible.map(agent=><button key={agent.id}
          className={'lending-agent-item '+(selected===agent.id?'selected':'')} disabled={busy} onClick={()=>choose(agent)}>
          <span className="lending-agent-dot" style={{background:agent.color}}/>
          <span><strong>{agent.name}</strong><small>{agent.title}</small>
            <em>{agent.status==='ready'&&!agent.builtin&&agent.redmine_sync?.state!=='synced'?'Chờ đồng bộ':statuses[agent.status]}{agent.builtin?' · Gốc':''}</em></span>
        </button>)}
      </div>
      <div className="lending-agent-form">
        {(busy||message||failure)&&<div className="agent-action-feedback">
          {busy&&<p role="status">{busyMessage}</p>}
          {message&&<p role="status" className="lending-agent-success">{message}</p>}
          {failure&&<p role="alert" className="chat-error">{failure}</p>}
        </div>}
        <h3>{selected?'Cấu hình agent':'Thành viên mới'}</h3>
        {!apiReady&&<p role="alert" className="chat-error">Backend chưa nạp bản quản lý agent mới. Khởi động lại dịch vụ rồi tải lại trang để dùng các thao tác bên dưới.</p>}
        <p>Runtime trên máy này · Cấu hình riêng cho dự án. Agent mới chưa tham gia workflow mặc định.</p>
        <form onSubmit={e=>{e.preventDefault();void act('save')}}>
          <fieldset disabled={busy||syncing||!apiReady}>
          <AgentSetup form={form} onChange={setForm} agents={agents} options={options} project={project} onSkillCreated={skill=>setOptions(old=>({...old,skills:[...old.skills,skill]}))}/>
          <section className="lending-agent-connection" aria-label="Tài khoản Redmine">
            <h3>Tài khoản Redmine</h3>
            {!selected&&<p>Hệ thống tự tạo tài khoản riêng cho agent, thêm vào dự án và gán vai trò phù hợp. Không dùng chung tài khoản của agent cũ.</p>}
            {current?.builtin&&<p>Dùng tài khoản Redmine đã cấu hình cho vai trò gốc.</p>}
            {current&&!current.builtin&&<>
              <p role="status">{({pending:'Đang chờ đồng bộ…',provisioning:'Đang tạo hoặc cập nhật tài khoản và quyền…',synced:'Đã đồng bộ',error:'Đồng bộ chưa hoàn tất'} as Record<string,string>)[current.redmine_sync?.state??'']??'Cần đồng bộ tài khoản riêng'}</p>
              {current.redmine_sync?.login&&<p>Đăng nhập: <code>{current.redmine_sync.login}</code></p>}
              {current.redmine_user_id&&<p><a href={'http://localhost:3000/users/'+current.redmine_user_id} target="_blank" rel="noreferrer">User #{current.redmine_user_id} ↗</a> · {current.redmine_sync?.role_name??'Chưa xác minh vai trò'} · {current.redmine_sync?.state!=='synced'?'Đang xác minh trạng thái':current.redmine_sync?.user_status===1?'Đang hoạt động':'Đã khóa khi chưa nhận việc'}</p>}
              {current.redmine_sync?.error&&<p role="alert" className="chat-error">{current.redmine_sync.error}</p>}
            </>}
          </section>
          <button className="full-button" disabled={busy}>{busy?'Đang xử lý…':selected?'Lưu cấu hình':'Tạo agent'}</button>
          {dirty&&<button type="button" className="full-button" onClick={()=>setForm({...current})}>Hoàn tác thay đổi chưa lưu</button>}
          </fieldset>
        </form>
        {selected&&<fieldset disabled={busy||syncing||!apiReady} className="lending-agent-tools">
          {!current?.builtin&&<button disabled={dirty} onClick={()=>void act('sync')}>{current?.redmine_sync?.state==='error'?'Thử lại đồng bộ Redmine':'Đồng bộ lại Redmine'}</button>}
          {!inactive&&current?.status!=='paused'&&<button disabled={busy||dirty||!apiReady} title={dirty?'Lưu cấu hình trước khi kích hoạt':undefined} onClick={()=>void act('verify')}>Kiểm tra &amp; kích hoạt</button>}
          {current?.status==='paused'&&<button disabled={busy||dirty||!apiReady} onClick={()=>void act('resume')}>Tiếp tục nhận việc</button>}
          {inactive&&<button disabled={busy||dirty||!apiReady} onClick={()=>void act('restore')}>Khôi phục về bản nháp</button>}
          {current?.status==='ready'&&<button disabled={busy||selected==='pm'||!apiReady} onClick={()=>void act('pause')}>Tạm dừng nhận việc</button>}
          <button disabled={busy||inactive} onClick={()=>onFocus(selected)}>◎ Focus</button>
          {selected!=='pm'&&<button disabled={busy||dirty||!apiReady} onClick={()=>void act('duplicate')}>Nhân bản agent</button>}
          {!current?.builtin&&!inactive&&<button disabled={busy||!apiReady} onClick={()=>void act('archive')}>Lưu trữ</button>}
          {!current?.builtin&&current?.status!=='terminated'&&<button disabled={busy||dirty||!apiReady} onClick={()=>{setConfirmation('terminate');setConfirmName('')}}>Chấm dứt hoạt động</button>}
          {!current?.builtin&&inactive&&<button className="lending-agent-danger" disabled={busy||dirty||!apiReady} onClick={()=>{setConfirmation('delete');setConfirmName('')}}>Xóa vĩnh viễn</button>}
        </fieldset>}
        {current?.builtin&&<p className="lending-agent-note">Agent gốc phục vụ workflow hiện có: có thể sửa hồ sơ và nhân bản chuyên môn; không xóa hoặc chấm dứt để tránh làm hỏng luồng đang dùng.</p>}
        {confirmation&&current&&<div role="dialog" aria-modal="false" aria-label={confirmation==='delete'?'Xác nhận xóa agent':'Xác nhận chấm dứt agent'} className="lending-agent-confirm">
          <h3>{confirmation==='delete'?'Xóa vĩnh viễn '+current.name:'Chấm dứt '+current.name}</h3>
          <p>{confirmation==='delete'?'Hồ sơ và hướng dẫn bị xóa, không có nút khôi phục. Tên trong lịch sử task và hội thoại vẫn được giữ.':'Agent ngừng nhận việc và token Discord lưu cục bộ được gỡ. Hồ sơ được giữ; muốn dùng lại phải khôi phục và kiểm tra.'} Tài khoản Redmine riêng được khóa để giữ lịch sử. Repository và ứng dụng Discord bên ngoài không bị xóa. Phiên Discord đang mở cần dừng riêng hoặc reset token trên Discord để thu hồi hoàn toàn.</p>
          <label>Nhập đúng tên: {current.name}<input autoFocus value={confirmName} onChange={e=>setConfirmName(e.target.value)}/></label>
          <div className="lending-agent-tools"><button disabled={busy} onClick={()=>setConfirmation(undefined)}>Hủy</button>
            <button className="lending-agent-danger" disabled={busy||confirmName!==current.name} onClick={()=>void act(confirmation)}>{confirmation==='delete'?'Xác nhận xóa vĩnh viễn':'Xác nhận chấm dứt'}</button></div>
        </div>}
        {!!pending.length&&<section className="lending-agent-assignment"><h3>Công việc chưa hoàn thành</h3>
          <p>Hoàn thành hoặc chuyển các task trước khi lưu trữ/chấm dứt/xóa. Chỉ chuyển task riêng chưa bắt đầu, sang agent cùng chuyên môn và quyền.</p>
          <label>Agent thay thế<select value={transferTo} onChange={e=>setTransferTo(e.target.value)}><option value="">Chọn agent</option>
            {replacements.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          {pending.map(w=><div className="lending-agent-pending" key={w.id}><span>#{w.id} · {w.title}</span>
            <button disabled={busy||!apiReady||!transferTo||w.kind!=='task'||w.stage!==0||!['queued','attention'].includes(w.state)} onClick={()=>void act('reassign',{target_id:transferTo,work_id:w.id})}>Chuyển task</button></div>)}
        </section>}
        {!!pendingChats.length&&<section className="lending-agent-assignment"><h3>Yêu cầu hội thoại đang chờ</h3>
          {pendingChats.map(chat=><div className="lending-agent-pending" key={chat.id}><span>#{chat.id} · {chat.message}</span>
            <button disabled={busy||!apiReady||chat.state!=='queued'} onClick={()=>void act('cancel_chat',{chat_id:chat.id})}>Hủy yêu cầu chờ</button></div>)}
        </section>}
        {!!requests.filter(r=>r.agent===selected&&['pending','failed','waiting_source'].includes(r.state)).length&&<section className="lending-agent-history"><h3>Đề xuất chờ duyệt</h3>
          {requests.filter(r=>r.agent===selected&&['pending','failed','waiting_source'].includes(r.state)).map(request=><article key={request.id}>
            <strong>{request.title}</strong><p>{request.instructions}</p>
            {request.state==='waiting_source'?<><p>Đã duyệt, chờ công việc gốc hoàn thành.</p><button disabled={busy} onClick={()=>void act('review_request',{request_id:request.id,decision:'reject'})}>Hủy đề xuất</button></>:<>
              {request.error&&<p role="alert">{request.error}</p>}
              <div className="lending-agent-tools"><button disabled={busy} onClick={()=>void act('review_request',{request_id:request.id,decision:'approve'})}>Duyệt đề xuất</button>
              <button disabled={busy} onClick={()=>void act('review_request',{request_id:request.id,decision:'reject'})}>Từ chối đề xuất</button></div>
            </>}
          </article>)}
        </section>}
        {canWork&&!['pm','reviewer','tester'].includes(selected??'')&&<form className="lending-agent-assignment" onSubmit={e=>{e.preventDefault();void act('assign')}}>
          <h3>Giao task trong Story hiện có</h3>
          <label>Mã Story<input type="number" min={1} required value={task.story} onChange={e=>setTask({...task,story:e.target.value})}/></label>
          <label>Tên task<input required maxLength={160} value={task.title} onChange={e=>setTask({...task,title:e.target.value})}/></label>
          <label>Tiêu chí nghiệm thu<textarea rows={3} required maxLength={6000} value={task.acceptance} onChange={e=>setTask({...task,acceptance:e.target.value})}/></label>
          <p>{current.builtin||current.access==='write'?'Code đi qua REVIEW, TESTER và CI trước khi merge.':'Task phân tích chỉ bàn giao báo cáo; không push hoặc merge code.'}</p>
          <button className="full-button" disabled={busy||!apiReady||dirty}>Giao task</button>
        </form>}
        <p className="lending-agent-note">Discord tùy chọn: agent vẫn làm việc trong Office khi chưa có bot riêng. Không nhập token hoặc mật khẩu vào hướng dẫn.</p>
        {selected&&!current?.builtin&&<p className="lending-agent-note">Mã agent: <code>{selected}</code><br/>Kết nối bot từ PowerShell bằng <code>--custom-agents {selected}</code> khi khởi động discord_pm.py. Token lưu trong Windows.</p>}
        {selected&&<section className="lending-agent-history"><h3>Lịch sử thay đổi</h3>
          {historyError&&<p role="alert">{historyError}</p>}
          {!history.length&&!historyError&&<p>Chưa có thay đổi được ghi nhận.</p>}
          {history.map((event,index)=><article key={event.at+'-'+index}><strong>{({create:'Tạo hồ sơ',update:'Sửa hồ sơ',status:'Đổi trạng thái',delete:'Xóa hồ sơ',redmine_sync:'Đồng bộ Redmine'} as Record<string,string>)[event.operation]??event.operation}</strong>
            {event.status&&<span> · {statuses[event.status as LendingAgent['status']]??event.status}</span>}
            <small>{new Date(event.at*1000).toLocaleString('vi-VN')} · Phiên bản {event.revision}</small>
          </article>)}
        </section>}
      </div>
    </div>
  </section>
}
