import {useEffect,useRef,useState} from 'react'
import type {LendingAgent} from './LendingAgents'
import AgentTokens from './AgentTokens'
import type {ReactNode} from 'react'

function TokenDetail({children,onClose}:{children:ReactNode;onClose:()=>void}){
  const ref=useRef<HTMLDialogElement>(null)
  useEffect(()=>{
    const dialog=ref.current
    dialog?.showModal()
    return ()=>dialog?.close()
  },[])
  return <dialog ref={ref} className="token-detail-dialog" aria-label="Chi tiết và giới hạn token" onCancel={onClose}
    onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose()}}}>
    {children}
  </dialog>
}

type Run={id:string;agent:string;provider:string;model:string;month:string;at:number;state:string;task?:number;usage:null|{input:number;output:number;cached:number;total:number}}
type Data={month:string;limits:Record<string,number>;runs:Run[]}
const fmt=(n:number)=>n.toLocaleString('vi-VN')

export default function TokenDashboard({agents,project,onClose}:{agents:LendingAgent[];project?:string;onClose:()=>void}){
  const [data,setData]=useState<Data>(),[error,setError]=useState(''),[selected,setSelected]=useState<string>()
  const [period,setPeriod]=useState(''),[provider,setProvider]=useState('all'),[query,setQuery]=useState(''),[refresh,setRefresh]=useState(0)
  const [updated,setUpdated]=useState<Date>()
  useEffect(()=>{
    const controller=new AbortController();setData(undefined);setError('')
    async function load(){try{
      const response=await fetch('/lending-api/agents/tokens?'+new URLSearchParams(project?{project}:{}),{signal:controller.signal})
      if(!response.ok)throw Error(response.status===404?'Backend chưa nạp quản lý token. Khởi động lại backend rồi tải lại trang.':'Không tải được mức sử dụng token.')
      const value=await response.json() as Data
      if(!controller.signal.aborted){setData(value);setUpdated(new Date());setError('')}
    }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:String(e))}}
    void load();const timer=setInterval(()=>void load(),15000)
    return ()=>{controller.abort();clearInterval(timer)}
  },[project,refresh])
  const current=period||data?.month||''
  const months=Array.from(new Set([data?.month??'',...data?.runs.map(r=>r.month)??[]])).filter(Boolean).sort().reverse()
  const runs=data?.runs.filter(r=>r.month===current&&(provider==='all'||provider===r.provider))??[]
  const total=runs.reduce((n,r)=>n+(r.usage?.total??0),0)
  const sum=(field:'input'|'output'|'cached')=>runs.reduce((n,r)=>n+(r.usage?.[field]??0),0)
  const unknown=runs.filter(r=>!r.usage).length
  const ids=Array.from(new Set([...agents.map(a=>a.id),...runs.map(r=>r.agent)]))
  const rows=ids.map(id=>{
    const a=agents.find(a=>a.id===id),history=runs.filter(r=>r.agent===id)
    const used=history.reduce((n,r)=>n+(r.usage?.total??0),0),limit=data?.limits[id]??0
    const budgetUsed=(data?.runs??[]).filter(r=>r.agent===id&&r.month===data?.month).reduce((n,r)=>n+(r.usage?.total??0),0)
    return {id,budgetUsed,name:a?.name??id,color:a?.color??'#94a3b8',status:a?.status??'deleted',runtime:a?.runtime,
      history,used,limit,unknown:history.filter(r=>!r.usage).length,
      models:Array.from(new Set(history.map(r=>r.provider+' / '+r.model)))}
  }).filter(a=>a.name.toLowerCase().includes(query.toLowerCase())&&(provider==='all'||a.history.length>0||a.runtime?.adapter===provider)).sort((a,b)=>b.used-a.used||a.name.localeCompare(b.name))
  const days=Array.from({length:current?new Date(Number(current.slice(0,4)),Number(current.slice(5)),0).getDate():0},(_,i)=>{
    const key=current+'-'+String(i+1).padStart(2,'0')
    return {day:i+1,total:runs.filter(r=>new Date(r.at*1000).toLocaleDateString('sv-SE',{timeZone:'Asia/Bangkok'})===key).reduce((n,r)=>n+(r.usage?.total??0),0)}
  })
  const peak=Math.max(1,...days.map(d=>d.total))
  return <section className="token-dashboard" aria-label="Quản lý token">
    <header className="token-dashboard-head"><div><span className="token-eyebrow">USAGE & LIMITS</span><h1>Quản lý token</h1><p>Theo dõi mức sử dụng của cả đội trong dự án hiện tại.</p></div><div><button onClick={()=>setRefresh(n=>n+1)}>↻ Làm mới</button><button aria-label="Đóng quản lý token" onClick={onClose}>×</button></div></header>
    <div className="token-filters"><label>Tháng<select aria-label="Tháng" value={current} onChange={e=>setPeriod(e.target.value)}>{months.map(m=><option key={m}>{m}</option>)}</select></label><label>Nhà cung cấp<select aria-label="Nhà cung cấp" value={provider} onChange={e=>setProvider(e.target.value)}><option value="all">Tất cả nhà cung cấp</option><option value="codex">OpenAI / Codex</option><option value="claude">Anthropic / Claude</option><option value="gemini">Google / Gemini</option></select></label><label>Tìm agent<input placeholder="Tên agent…" value={query} onChange={e=>setQuery(e.target.value)}/></label><small>{updated?'Cập nhật '+updated.toLocaleTimeString('vi-VN')+' · tự làm mới 15 giây':'Đang tải số liệu…'}</small></div>
    {error&&<p className="token-alert" role="alert">{error}</p>}
    {data&&<>
    <div className="token-cards">{[['Tổng token',fmt(total),'Đã ghi nhận từ CLI'],['Đầu vào',fmt(sum('input')),'Gồm phần đọc từ cache'],['Đầu ra',fmt(sum('output')),'Gồm suy luận khi được báo cáo'],['Agent sử dụng',String(new Set(runs.map(r=>r.agent)).size),runs.length+' lượt gọi model']].map(([label,value,hint])=><article key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></article>)}</div>
    {unknown>0&&<p className="token-alert">{unknown} lượt đang chạy hoặc chưa có số liệu usage. Tổng trên chỉ gồm số liệu đã ghi nhận.</p>}
    <section className="token-chart"><div><h2>Mức dùng theo ngày</h2><small>{current} · UTC+7</small></div><div className="token-bars">{days.map(d=><div key={d.day} title={'Ngày '+d.day+': '+fmt(d.total)+' token'}><i style={{height:Math.max(d.total?3:0,d.total/peak*100)+'%'}}/><span>{d.day}</span></div>)}</div></section>
    <div className="token-table-head"><h2>Mức sử dụng theo agent</h2><small>Bấm một agent để xem lượt chạy và đặt giới hạn tháng</small></div>
    <div className="token-table-wrap"><table className="token-table"><thead><tr><th>Agent</th><th>Nhà cung cấp / model</th><th>Token đã dùng</th><th>Lượt gọi</th><th>Giới hạn tháng</th><th>Trạng thái</th></tr></thead><tbody>{rows.map(a=><tr key={a.id} className={selected===a.id?'selected':''}><td><button className="token-agent-link" onClick={()=>setSelected(selected===a.id?undefined:a.id)}><i style={{background:a.color}}/>{a.name}<span>↗</span></button></td><td>{a.models.length?a.models.join(', '):(a.runtime?.adapter??'codex')+' / '+(a.runtime?.model||'Mặc định')}<small>{a.history.length?'Đã sử dụng':'Chưa có lượt ghi nhận'}</small></td><td><strong>{fmt(a.used)}</strong>{a.unknown>0&&<small>{a.unknown} lượt chưa rõ usage</small>}</td><td>{a.history.length}</td><td>{a.limit? <><span>{fmt(a.limit)} token</span>{current===data.month?<progress max={a.limit} value={Math.min(a.budgetUsed,a.limit)}/>:<small>Giới hạn cấu hình hiện tại</small>}</>:'Chưa đặt giới hạn'}<button className="token-limit-edit" onClick={()=>setSelected(a.id)}>Đặt giới hạn</button></td><td><span className={'token-badge '+(current===data.month&&a.limit&&a.budgetUsed>=a.limit?'danger':a.unknown?'warning':'')}>{current===data.month&&a.limit&&a.budgetUsed>=a.limit?'Chạm giới hạn':a.history.some(r=>r.state==='running')?'Đang chạy':a.unknown?'Thiếu số liệu':a.used?'Đã ghi nhận':'Chưa sử dụng'}</span></td></tr>)}</tbody></table>{!rows.length&&<p>Không có agent phù hợp bộ lọc.</p>}</div>
    {selected&&<TokenDetail onClose={()=>{setSelected(undefined);setRefresh(n=>n+1)}}><div className="token-table-head"><h2>{agents.find(a=>a.id===selected)?.name??selected} · Chi tiết tháng hiện tại</h2><button onClick={()=>{setSelected(undefined);setRefresh(n=>n+1)}}>Đóng chi tiết</button></div><AgentTokens key={selected} agent={selected} project={project}/></TokenDetail>}
    <p className="token-footnote">Thống kê lượt chạy trong Office từ khi bật ghi nhận. Chưa gồm nút thử model/runtime hoặc CLI bên ngoài Office. Không phải số dư hay quota tài khoản; chưa quy đổi thành tiền khi chưa có dữ liệu tính phí đáng tin cậy. Giới hạn chặn lượt mới, không cắt lượt đang chạy.</p>
    </>}
  </section>
}
