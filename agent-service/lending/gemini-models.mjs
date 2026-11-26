// Network-only model catalog/probe. Keys stay inside this process and are sent only in Google's auth header.
import {loadApiKey} from '../tools/providers/node_modules/@google/gemini-cli/bundle/chunk-4UW3VJTT.js';
export function modelId(value){
 const id=typeof value==='string'?value.replace(/^models\//,''):'';
 if(!/^gemini-[a-zA-Z0-9._-]{1,110}$/.test(id))throw Object.assign(new Error('Chọn một model Gemini cụ thể trước khi thử.'),{code:'invalid_model'});
 return id;
}
function problem(status){
 const messages={400:'Google từ chối cấu hình yêu cầu hoặc API key không hợp lệ.',401:'API key Gemini không hợp lệ hoặc đã hết hiệu lực.',
 403:'API key không có quyền truy cập model/dịch vụ này.',404:'Model không tồn tại hoặc không còn được cung cấp cho API này.',
 429:'Google báo hết hạn mức hoặc vượt tốc độ gọi. Chưa xác nhận model dùng được.'};
 return Object.assign(new Error(messages[status]??'Google API chưa phản hồi thành công. Thử lại sau.'),{code:'google_'+status});
}
export async function catalog(key,request=fetch){
 const rows=new Map(),seen=new Set();let token='';
 const signal=AbortSignal.timeout(25000);
 for(let page=0;page<10;page++){
  const url=new URL('https://generativelanguage.googleapis.com/v1beta/models');url.searchParams.set('pageSize','1000');
  if(token)url.searchParams.set('pageToken',token);
  const response=await request(url,{headers:{'x-goog-api-key':key},signal,redirect:'error'});
  if(!response.ok)throw problem(response.status);
  const data=await response.json();
  if(!Array.isArray(data.models))throw Object.assign(new Error('Google trả danh sách model không hợp lệ.'),{code:'invalid_response'});
  for(const row of data.models){
   if(!row.name?.startsWith('models/gemini-')||!row.supportedGenerationMethods?.includes('generateContent'))continue;
   let id;try{id=modelId(row.name)}catch{continue}
   // Only text/general-purpose models belong to coding agents.
   if(/(?:image|tts|live|audio|robotics)/i.test(id))continue;
   rows.set(id,{id,name:String(row.displayName??id).slice(0,150),adapter:'gemini',source:'google_api',
    verified:false,input_token_limit:row.inputTokenLimit??null,output_token_limit:row.outputTokenLimit??null});
  }
  if(!data.nextPageToken)return {models:[...rows.values()].sort((a,b)=>a.id.localeCompare(b.id)),source:'google_api',
   listed_at:new Date().toISOString(),generation_tested:false};
  token=data.nextPageToken;
  if(typeof token!=='string'||seen.has(token))throw Object.assign(new Error('Google trả phân trang model không hợp lệ.'),{code:'invalid_response'});
  seen.add(token);
 }
 throw Object.assign(new Error('Danh sách model vượt giới hạn phân trang. Chưa tải đầy đủ.'),{code:'pagination_limit'});
}
export async function probe(key,value,request=fetch){
 const id=modelId(value),started=Date.now();
 const response=await request('https://generativelanguage.googleapis.com/v1beta/models/'+encodeURIComponent(id)+':generateContent',
  {method:'POST',headers:{'x-goog-api-key':key,'Content-Type':'application/json'},redirect:'error',signal:AbortSignal.timeout(25000),
   body:JSON.stringify({contents:[{role:'user',parts:[{text:'Reply with OK only.'}]}],generationConfig:{maxOutputTokens:512}})});
 if(!response.ok)throw problem(response.status);
 const data=await response.json();
 const text=data.candidates?.flatMap(c=>c.content?.parts??[]).filter(p=>!p.thought&&typeof p.text==='string').map(p=>p.text).join('').trim();
 if(!text)throw Object.assign(new Error('Model chưa trả nội dung văn bản; chưa xác nhận kết nối thành công.'),{code:'no_text'});
 const usage=data.usageMetadata??{};
 return {model:id,verified:true,verified_at:new Date().toISOString(),latency_ms:Date.now()-started,
  model_version:typeof data.modelVersion==='string'?data.modelVersion.slice(0,150):id,
  usage:{input_tokens:usage.promptTokenCount??0,output_tokens:usage.candidatesTokenCount??0,
   thinking_tokens:usage.thoughtsTokenCount??0,total_tokens:usage.totalTokenCount??0},
  message:'Model đã trả lời thành công một yêu cầu văn bản ngắn. Chưa kiểm tra toàn bộ task/CLI.'};
}
export async function run(action,value){
 try{
  const key=process.env.GEMINI_API_KEY||await loadApiKey();
  if(!key)return {ok:false,error:'Cần API key Gemini đã lưu trong CLI hoặc GEMINI_API_KEY để lấy danh sách/thử model. Đăng nhập OAuth đơn thuần chưa được hỗ trợ ở bước này.',code:'missing_key'};
  const result=action==='models'?await catalog(key):action==='probe'?await probe(key,value):null;
  if(!result)return {ok:false,error:'Thao tác model không hợp lệ.',code:'invalid_action'};
  return {ok:true,...result};
 }catch(error){
  const known=typeof error.code==='string'&&/^(google_[0-9]+|invalid_model|invalid_response|pagination_limit|no_text)$/.test(error.code);
  return {ok:false,error:known?error.message:'Không kết nối được Google API hoặc quá thời gian. Không thay đổi cấu hình agent.',code:known?error.code:'connection_failed'};
 }
}
