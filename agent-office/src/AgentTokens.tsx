import {useEffect,useState} from 'react'

type Run={id:string;agent:string;provider:string;model:string;month:string;at:number;task?:number;state:string;
  usage:null|{input:number;output:number;cached:number;total:number}}
type Ledger={month:string;limits:Record<string,number>;runs:Run[]}
const number=(n:number)=>n.toLocaleString('vi-VN')

export default function AgentTokens({agent,project}:{agent?:string;project?:string}) {
  const [data,setData]=useState<Ledger>()
  const [limit,setLimit]=useState('0')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const [saved,setSaved]=useState(false)
  const [refresh,setRefresh]=useState(0)
  useEffect(()=>{
    const abort=new AbortController();setData(undefined);setError('');setSaved(false)
    let initial=true
    async function load(){
      try{
        const response=await fetch('/lending-api/agents/tokens?'+new URLSearchParams(project?{project}:{}),{signal:abort.signal})
        if(!response.ok)throw Error(response.status===404?'Backend chưa nạp phần quản lý token. Khởi động lại backend rồi tải lại.':'Không tải được dữ liệu token.')
        const value=await response.json() as Ledger
        if(!abort.signal.aborted){setData(value);if(initial){setLimit(String(value.limits[agent??'']??0));initial=false}}
      }catch(e){if(!abort.signal.aborted)setError(e instanceof Error?e.message:String(e))}
    }
    void load();const timer=setInterval(()=>void load(),15000)
    return ()=>{abort.abort();clearInterval(timer)}
  },[agent,project,refresh])
  if(!agent)return <p>Lưu agent trước để quản lý token.</p>
  const rows=data?.runs.filter(r=>r.agent===agent&&r.month===data.month)??[]
  const total=rows.reduce((n,r)=>n+(r.usage?.total??0),0)
  const unknown=rows.filter(r=>r.usage===null).length
  const maximum=data?.limits[agent]??0
  const groups=Object.values(rows.reduce<Record<string,{provider:string;model:string;total:number;runs:number}>>((all,r)=>{
    const key=r.provider+':'+r.model
    const item=all[key]??{provider:r.provider,model:r.model,total:0,runs:0}
    item.total+=r.usage?.total??0;item.runs++;all[key]=item;return all
  },{}))
  return <section className="agent-token-panel">
    <h3>Token · {data?.month??'Đang tải…'}</h3>
    <p>Thống kê riêng agent này trong dự án hiện tại, tháng theo giờ Việt Nam.</p>
    {error&&<p role="alert">{error}</p>}
    {data&&<>
      <strong className="agent-token-total">{number(total)} token đã ghi nhận</strong>
      <p>{rows.length} lượt · {unknown} lượt chưa có số liệu{unknown>0?' (bao gồm lượt đang chạy hoặc CLI không báo usage)':''}</p>
      {maximum>0&&<><progress max={maximum} value={Math.min(total,maximum)}/><p>{Math.round(total/maximum*100)}% / {number(maximum)} token tháng này</p></>}
      {maximum>0&&total>=maximum*.8&&<p role="status">{total>=maximum?'Đã chạm giới hạn; chặn lượt mới.':'Đã dùng ít nhất 80% giới hạn tháng.'}</p>}
      <label>Giới hạn token mỗi tháng<input aria-label="Giới hạn token mỗi tháng" type="number" min="0" max="1000000000" step="1" value={limit} onChange={e=>{setLimit(e.target.value);setSaved(false)}}/></label>
      <small>0 = không giới hạn. Kiểm tra trước mỗi lượt gọi model; không cắt lượt đang chạy nên tổng có thể vượt ngưỡng. Khi bật giới hạn, lượt chưa rõ số liệu cũng chặn lượt mới.</small>
      <button type="button" disabled={busy||!/^\d+$/.test(limit)} onClick={async()=>{
        setBusy(true);setError('');setSaved(false)
        try{
          const response=await fetch('/lending-api/agents/tokens',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent,project,limit:Number(limit)})})
          const result=await response.json();if(!response.ok)throw Error(result.error||'Chưa lưu được giới hạn.')
          setData(result);setSaved(true)
        }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
      }}>{busy?'Đang lưu…':'Lưu giới hạn token'}</button>
      {saved&&<p role="status">Đã lưu giới hạn.</p>}
      <h4>Theo nhà cung cấp / model</h4>
      {groups.length?<table><thead><tr><th>Model</th><th>Lượt</th><th>Token</th></tr></thead><tbody>{groups.map(g=><tr key={g.provider+g.model}><td>{g.provider} · {g.model}</td><td>{g.runs}</td><td>{number(g.total)}</td></tr>)}</tbody></table>:<p>Chưa có lượt gọi model được ghi nhận.</p>}
      <h4>Lượt gần đây</h4>
      {rows.slice(-20).reverse().map(r=><div className="agent-token-run" key={r.id}>
        <strong>{r.task?'Task #'+r.task:'Chat / tham vấn'} · {r.provider} / {r.model}</strong>
        <small>{new Date(r.at*1000).toLocaleString('vi-VN',{timeZone:'Asia/Bangkok'})} · {r.state==='completed'?'Hoàn tất':r.state==='running'?'Đang chạy':'Lỗi / dừng'}</small>
        <p>{r.usage?`${number(r.usage.total)} tổng · ${number(r.usage.input)} vào · ${number(r.usage.output)} ra · ${number(r.usage.cached)} cache`:'Chưa có số liệu token từ CLI'}</p>
      </div>)}
    </>}
    <button type="button" onClick={()=>setRefresh(n=>n+1)}>Làm mới số liệu</button>
    <small>Chỉ thống kê lượt runtime từ khi bật tính năng. Không phải số dư tài khoản, hóa đơn hay quota nhà cung cấp; chưa gồm nút thử model/runtime và các phiên CLI bên ngoài Office. Cache là một phần đầu vào, không cộng thêm vào tổng.</small>
  </section>
}
