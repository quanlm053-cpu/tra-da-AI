import { useEffect, useRef, useState } from 'react'
import type { LendingAgent } from './LendingAgents'

export type Setup = {
  role:string;description:string;goals:string[];work_rules:string[];tags:string[]
  runtime:{adapter:string;model:string;effort:string;timeout_minutes:number;concurrent_attempts:number}
  capabilities:{skill_ids:string[];default_tools:boolean;tools:string[]}
  collaboration:{assign_to:string;assignees:string[];consult_to:string;consultants:string[];
    autonomy:string;can_propose_agents:boolean;max_depth:number;max_open_subtasks:number}
}
export type SetupOptions = {provider_runtime_version?:number;gemini_catalog_version?:number;agent_runtime_check_version?:number;models:{id:string;name:string;adapter?:string}[];adapters:{id:string;name:string;available:boolean;credential_detected?:boolean;authentication_verified?:boolean}[];
  tools:{id:string;name:string}[];skills:{id:string;name:string;description:string;builtin:boolean}[]}
export function hydrate(form:Partial<LendingAgent>):Partial<LendingAgent>&Setup {
  return {...form,role:form.role??'',description:form.description??'',goals:form.goals??[],
    work_rules:form.work_rules??[],tags:form.tags??[],
    runtime:{adapter:'codex',model:'',effort:'default',timeout_minutes:30,concurrent_attempts:1,...form.runtime},
    capabilities:{skill_ids:[],default_tools:true,tools:['shell','project_state','read_issue','search_issues'],...form.capabilities},
    collaboration:{assign_to:form.id==='pm'?'team':'nobody',assignees:[],consult_to:'team',consultants:[],
      autonomy:form.id==='pm'?'delegate':'project',can_propose_agents:false,max_depth:1,max_open_subtasks:5,...form.collaboration}}
}
export function editable(form:Partial<LendingAgent>) {
  const data=hydrate(form)
  return Object.fromEntries(['name','title','specialty','instructions','access','color','role','description',
    'goals','work_rules','tags','runtime','capabilities','collaboration'].map(key=>[key,data[key as keyof typeof data]]))
}

export default function AgentSetup({form,onChange,agents,options,project,onSkillCreated}:{
  form:Partial<LendingAgent>;onChange:(value:Partial<LendingAgent>)=>void;agents:LendingAgent[];
  options:SetupOptions;project?:string;onSkillCreated:(skill:SetupOptions['skills'][number])=>void
}) {
  const [tab,setTab]=useState('Profile')
  const [skill,setSkill]=useState({name:'',description:'',content:''})
  const [skillError,setSkillError]=useState('')
  const [savingSkill,setSavingSkill]=useState(false)
  const value=hydrate(form)
  const [checkingProvider,setCheckingProvider]=useState(false)
  const [providerResult,setProviderResult]=useState<{installed:boolean;credential_detected:boolean;version?:string}>()
  const [providerError,setProviderError]=useState('')
  useEffect(()=>{setProviderResult(undefined);setProviderError('')},[value.runtime.adapter])
  const [catalogRows,setCatalogRows]=useState<SetupOptions['models']>([])
  const [catalogLoading,setCatalogLoading]=useState(false)
  const [catalogError,setCatalogError]=useState('')
  const [catalogLoaded,setCatalogLoaded]=useState(false)
  const [catalogRefresh,setCatalogRefresh]=useState(0)
  const [testingModel,setTestingModel]=useState(false)
  const [testResult,setTestResult]=useState<{model:string;message:string;usage?:{total_tokens:number};model_version?:string}>()
  const [testError,setTestError]=useState('')
  const [checkingRuntime,setCheckingRuntime]=useState(false)
  const [runtimeResult,setRuntimeResult]=useState<{message:string;checks:{read_file:boolean;mcp:boolean;write_file:boolean};duration_ms:number}>()
  const [runtimeError,setRuntimeError]=useState('')
  const runtimeAbort=useRef<AbortController|null>(null)
  const runtimeRevision=useRef(0)
  useEffect(()=>{
    runtimeRevision.current++;runtimeAbort.current?.abort();setCheckingRuntime(false);setRuntimeResult(undefined);setRuntimeError('')
    return ()=>{runtimeRevision.current++;runtimeAbort.current?.abort()}
  },[value.runtime.adapter,value.runtime.model,value.runtime.effort,value.access,form.id,project])
  const testAbort=useRef<AbortController|null>(null)
  const testRevision=useRef(0)
  useEffect(()=>{
    testRevision.current++;testAbort.current?.abort();setTestingModel(false);setTestResult(undefined);setTestError('')
    return ()=>{testRevision.current++;testAbort.current?.abort()}
  },[value.runtime.adapter,value.runtime.model,form.id,project,catalogRefresh])
  useEffect(()=>{
    setCatalogRows([]);setCatalogError('');setCatalogLoaded(false);setCatalogLoading(false)
    if(tab!=='Runtime'||value.runtime.adapter!=='gemini')return
    if(!options.gemini_catalog_version){setCatalogError('Backend chưa nạp phần danh sách model thực tế. Nạp lại backend rồi tải lại trang.');return}
    const controller=new AbortController();setCatalogLoading(true)
    fetch('/lending-api/agents/models?'+new URLSearchParams(project?{project}:{}),{signal:controller.signal})
      .then(async response=>{
        const result=await response.json()
        if(!response.ok)throw Error(result.error||'Chưa lấy được danh sách model.')
        if(!Array.isArray(result.models))throw Error('Danh sách model trả về không hợp lệ.')
        if(!controller.signal.aborted){setCatalogRows(result.models);setCatalogLoaded(true)}
      }).catch(error=>{if(!controller.signal.aborted)setCatalogError(String(error instanceof Error?error.message:error))})
      .finally(()=>{if(!controller.signal.aborted)setCatalogLoading(false)})
    return ()=>controller.abort()
  },[tab,value.runtime.adapter,project,catalogRefresh,options.gemini_catalog_version])
  const provider=options.adapters.find(item=>item.id===value.runtime.adapter)
  const providerName=provider?.name??'Codex CLI'
  const installed=providerResult?.installed??provider?.available
  const credentialDetected=providerResult?.credential_detected??provider?.credential_detected

  function set(patch:Partial<LendingAgent>){onChange({...value,...patch})}
  const people=agents.filter(a=>a.id!==form.id&&!['archived','terminated'].includes(a.status))
  function targets(){
    const key='assignees'
    return <div className="agent-setup-checks">{people.map(agent=><label key={agent.id}><input type="checkbox"
      checked={value.collaboration[key].includes(agent.id)} onChange={e=>set({collaboration:{...value.collaboration,
        [key]:e.target.checked?[...value.collaboration[key],agent.id]:value.collaboration[key].filter(id=>id!==agent.id)}})}/>{agent.name}</label>)}</div>
  }
  return <div className="agent-setup">
    <div role="tablist" aria-label="Thiết lập agent" className="agent-setup-tabs">
      {['Profile','Runtime','Capabilities','Collaboration'].map(name=><button type="button" role="tab" key={name}
        aria-selected={tab===name} aria-controls={'agent-tab-'+name} id={'agent-tab-button-'+name} onClick={()=>setTab(name)}>{name}</button>)}
    </div>
    <div role="tabpanel" id={'agent-tab-'+tab} aria-labelledby={'agent-tab-button-'+tab}>
    {tab==='Profile'&&<>
      <div className="lending-agent-fields">
        <label>Tên<input required maxLength={40} value={value.name??''} onChange={e=>set({name:e.target.value})}/></label>
        <label>Vai trò<input maxLength={100} placeholder="Frontend Developer, Designer…" value={value.role} onChange={e=>set({role:e.target.value})}/></label>
      </div>
      <label>Nhiệm vụ chính<input required maxLength={160} value={value.title??''} onChange={e=>set({title:e.target.value})}/></label>
      <label>Chuyên môn<select aria-label="Chuyên môn" disabled={form.builtin} value={value.specialty} onChange={e=>set({specialty:e.target.value,access:['reviewer','tester'].includes(e.target.value)?'read':value.access})}>
        {value.specialty==='pm'&&<option value="pm">Điều phối</option>}
        {Object.entries({specialist:'Chuyên môn riêng',sa:'Kiến trúc',ba:'Phân tích nghiệp vụ',backend:'Backend',frontend:'Frontend',devops:'DevOps',reviewer:'Review',tester:'Kiểm thử'}).map(([id,name])=><option key={id} value={id}>{name}</option>)}
      </select></label>
      <label>Hướng dẫn chuyên môn<textarea aria-label="Hướng dẫn chuyên môn" rows={6} maxLength={65536} value={value.instructions??''} onChange={e=>set({instructions:e.target.value})}/><small>{value.instructions?.length??0} / 65.536 ký tự</small></label>
      <label className="lending-agent-color">Màu nhân vật<input type="color" value={value.color} onChange={e=>set({color:e.target.value})}/></label>
    </>}
    {tab==='Runtime'&&<>
      <label>Nhà cung cấp<select aria-label="Nhà cung cấp" value={value.runtime.adapter}
        onChange={e=>set({runtime:{...value.runtime,adapter:e.target.value,model:'',effort:'default'}})}>
        <option value="codex">OpenAI · Codex CLI</option>
        <option value="claude" disabled={!options.provider_runtime_version}>Anthropic · Claude Code</option>
        <option value="gemini" disabled={!options.provider_runtime_version}>Google · Gemini CLI</option>
      </select></label>
      <div className="agent-provider-status">
        <strong>{installed?'✓ Đã cài CLI':'Chưa tìm thấy CLI'}{providerResult?.version?' · '+providerResult.version:''}</strong>
        <p>{credentialDetected?'Đã phát hiện thông tin đăng nhập; quyền truy cập model sẽ được xác nhận khi chạy.':'Chưa có thông tin đăng nhập. Bạn có thể lưu cấu hình trước, kết nối tài khoản/API key sau.'}</p>
        <button type="button" disabled={checkingProvider||!options.provider_runtime_version} onClick={async()=>{
          setCheckingProvider(true);setProviderError('')
          try{
            const response=await fetch('/lending-api/agents/provider?'+new URLSearchParams({adapter:value.runtime.adapter,...(project?{project}:{})}))
            const result=await response.json();if(!response.ok)throw Error(result.error)
            setProviderResult(result)
          }catch(error){setProviderError(String(error))}finally{setCheckingProvider(false)}
        }}>{checkingProvider?'Đang kiểm tra…':'Kiểm tra cài đặt'}</button>
        <small>Chỉ kiểm tra CLI và dấu hiệu đăng nhập, chưa gọi model hoặc tiêu token.</small>
        {providerError&&<p role="alert" className="chat-error">{providerError}</p>}
      </div>
      <label>Model<input list="agent-model-options" maxLength={120} placeholder={'Để trống: mặc định của '+providerName} value={value.runtime.model} onChange={e=>set({runtime:{...value.runtime,model:e.target.value}})}/></label>
      <datalist id="agent-model-options">{(value.runtime.adapter==='gemini'?catalogRows:options.models.filter(model=>(model.adapter??'codex')===value.runtime.adapter)).map(model=><option key={model.id} value={model.id}>{model.name}</option>)}</datalist>
      {value.runtime.adapter==='gemini'?<section className="agent-model-catalog">
        <div className="agent-model-actions">
          <button type="button" disabled={catalogLoading||testingModel||!options.gemini_catalog_version} onClick={()=>setCatalogRefresh(n=>n+1)}>{catalogLoading?'Đang lấy từ Google…':'Làm mới danh sách model'}</button>
          <button type="button" disabled={testingModel||checkingRuntime||!value.runtime.model.trim()||!options.gemini_catalog_version} onClick={async()=>{
            const revision=++testRevision.current,controller=new AbortController();testAbort.current=controller
            setTestingModel(true);setTestError('');setTestResult(undefined)
            try{
              const response=await fetch('/lending-api/agents/model-test',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},
                body:JSON.stringify({adapter:'gemini',model:value.runtime.model,project})})
              const result=await response.json()
              if(!response.ok)throw Error(result.error||'Chưa xác nhận được model.')
              if(result.verified!==true)throw Error('Model chưa được xác nhận.')
              if(revision===testRevision.current)setTestResult(result)
            }catch(error){if(!controller.signal.aborted&&revision===testRevision.current)setTestError(error instanceof Error?error.message:String(error))}
            finally{if(revision===testRevision.current)setTestingModel(false)}
          }}>{testingModel?'Đang thử model…':'Thử model đã chọn'}</button>
        </div>
        {catalogLoaded&&<p>Đã lấy {catalogRows.length} model văn bản từ Google API bằng key hiện tại. Có trong danh sách chưa bảo đảm còn quota hoặc được phép gọi.</p>}
        {catalogLoaded&&!catalogRows.length&&<p>Google chưa trả model văn bản phù hợp cho agent.</p>}
        {catalogError&&<p role="alert" className="chat-error">{catalogError}</p>}
        {!testResult&&<small>Chưa thử gọi model. Nút thử gửi một yêu cầu văn bản ngắn, tối đa 512 token đầu ra; có thể tính vào hạn mức/chi phí API. Không đọc file hoặc chạy task.</small>}
        {testResult&&<p role="status" className="lending-agent-success">✓ {testResult.model} đã trả lời thành công · {testResult.usage?.total_tokens??'—'} token. Chưa kiểm tra toàn bộ task/CLI.</p>}
        {testError&&<p role="alert" className="chat-error">{testError}</p>}
      </section>:<p>Mỗi agent dùng nhà cung cấp và model đã lưu. Gợi ý không bảo đảm quyền truy cập. Hệ thống không tự đổi nhà cung cấp khi gặp lỗi.</p>}
      {value.runtime.adapter!=='codex'&&<details className="agent-provider-help"><summary>Cách kết nối {providerName}</summary>
        <p>Mở PowerShell tại thư mục dự án, chạy lệnh sau để đăng nhập:</p>
        <code>{'powershell -ExecutionPolicy Bypass -File ".\\agent-service\\lending\\provider.ps1" -Provider '+value.runtime.adapter+' -Action login'}</code>
        <p>Nếu dùng API key: cấu hình ANTHROPIC_API_KEY cho Claude hoặc GEMINI_API_KEY cho Gemini trong môi trường của backend. Không nhập key vào tên model hay hướng dẫn agent.</p>
        <p>Chế độ chỉ đọc của Claude/Gemini không bật Terminal hoặc công cụ sửa file. Mỗi nhà cung cấp tính hạn mức theo tài khoản riêng.</p>
      </details>}
      <div className="lending-agent-fields">
        <label>Quyền với code<select aria-label="Quyền với code" disabled={form.builtin||['pm','reviewer','tester'].includes(value.specialty??'')} value={value.access} onChange={e=>set({access:e.target.value as 'read'|'write'})}>
          <option value="read">Đọc, phân tích và báo cáo</option><option value="write">Sửa code trong task được giao</option></select></label>
      </div>
      <section className="agent-model-catalog">
        <button type="button" disabled={checkingRuntime||testingModel||!options.agent_runtime_check_version} onClick={async()=>{
          const revision=++runtimeRevision.current,controller=new AbortController();runtimeAbort.current=controller
          setCheckingRuntime(true);setRuntimeResult(undefined);setRuntimeError('')
          try{
            const response=await fetch('/lending-api/agents/runtime-test',{method:'POST',signal:controller.signal,
              headers:{'Content-Type':'application/json'},body:JSON.stringify({runtime:value.runtime,access:value.access??'read',project})})
            const result=await response.json()
            if(!response.ok)throw Error(result.error||'Lượt thử agent chưa hoàn tất.')
            if(result.verified!==true)throw Error('Chưa xác nhận luồng agent hoạt động.')
            if(revision===runtimeRevision.current)setRuntimeResult(result)
          }catch(error){if(!controller.signal.aborted&&revision===runtimeRevision.current)setRuntimeError(error instanceof Error?error.message:String(error))}
          finally{if(revision===runtimeRevision.current)setCheckingRuntime(false)}
        }}>{checkingRuntime?'Đang thử CLI, file và MCP…':'Thử luồng agent thực tế'}</button>
        <small>Lượt thử dùng token thật, tối đa 90 giây. Agent đọc file và gọi MCP giả lập trong thư mục riêng; có quyền sửa thì tạo thêm file bàn giao. Không sửa dự án hay tạo task Redmine.</small>
        {!options.agent_runtime_check_version&&<p>Cần nạp backend mới để dùng lượt thử agent.</p>}
        {runtimeResult&&<p role="status" className="lending-agent-success">✓ {runtimeResult.message} ({Math.round(runtimeResult.duration_ms/1000)} giây)</p>}
        {runtimeError&&<p role="alert" className="chat-error">{runtimeError}</p>}
      </section>
    </>}
    {tab==='Capabilities'&&<>
      <h3>Skills</h3><p>Chuyên môn nền luôn được nạp. Chọn thêm các quy trình cần thiết cho agent.</p>
      <div className="agent-setup-checks">{options.skills.map(item=><label key={item.id}><input type="checkbox" checked={value.capabilities.skill_ids.includes(item.id)}
        onChange={e=>set({capabilities:{...value.capabilities,skill_ids:e.target.checked?[...value.capabilities.skill_ids,item.id]:value.capabilities.skill_ids.filter(id=>id!==item.id)}})}/>
        <span>{item.name}<small>{item.description}</small></span></label>)}</div>
      <details className="agent-setup-skill"><summary>＋ Viết skill mới cho dự án</summary>
        <label>Tên skill<input maxLength={80} value={skill.name} onChange={e=>setSkill({...skill,name:e.target.value})}/></label>
        <label>Mô tả skill<input maxLength={300} value={skill.description} onChange={e=>setSkill({...skill,description:e.target.value})}/></label>
        <label>Nội dung skill<textarea rows={5} maxLength={32000} value={skill.content} onChange={e=>setSkill({...skill,content:e.target.value})}/></label>
        <button type="button" disabled={savingSkill||!skill.name.trim()||!skill.content.trim()} onClick={async()=>{
          setSavingSkill(true);setSkillError('')
          try {
            const response=await fetch('/lending-api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...skill,project,operation:'create_skill'})})
            const result=await response.json();if(!response.ok)throw Error(result.error)
            onSkillCreated(result);set({capabilities:{...value.capabilities,skill_ids:[...value.capabilities.skill_ids,result.id]}});setSkill({name:'',description:'',content:''})
          }catch(e){setSkillError(String(e))}finally{setSavingSkill(false)}
        }}>Lưu và gắn skill</button>
        {skillError&&<p role="alert" className="chat-error">{skillError}</p>}
      </details>
    </>}
    {tab==='Collaboration'&&<>
      <label>Được giao task cho<select aria-label="Được giao task cho" value={value.collaboration.assign_to} onChange={e=>set({collaboration:{...value.collaboration,assign_to:e.target.value}})}>
        <option value="nobody">Không ai</option><option value="team">Agent sẵn sàng trong dự án</option><option value="selected">Chọn agent cụ thể</option></select></label>
      {value.collaboration.assign_to==='selected'&&targets()}
      <label>Mức tự chủ khi phân công<select aria-label="Mức tự chủ khi phân công" value={value.collaboration.autonomy} onChange={e=>set({collaboration:{...value.collaboration,autonomy:e.target.value}})}>
        <option value="project">Theo dự án — mặc định chờ duyệt</option><option value="suggest">Chỉ đề xuất, chờ người dùng duyệt</option>
        <option value="delegate">Tự giao việc độc lập trong quyền được cấp</option></select></label>
    </>}
    </div>
  </div>
}
