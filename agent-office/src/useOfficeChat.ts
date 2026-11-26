import {useCallback,useEffect,useRef,useState} from 'react'
export type ChatMessage={id:number;role:string;message:string;reply:string;state:'queued'|'running'|'done'|'failed';created:number}
export function useOfficeChat(story:number|undefined){
 const [items,setItems]=useState<ChatMessage[]>([]),[error,setError]=useState(''),[sending,setSending]=useState(false)
 const current=useRef(story)
 current.current=story
 const pending=useRef<{story_id:number;role:string;message:string;request_id:string}|undefined>(undefined)
 const refresh=useCallback(async()=>{if(!story)return;try{const r=await fetch('/api/chat?story_id='+story);if(!r.ok)throw Error('Không tải được hội thoại');const data=await r.json();if(current.current===story){setItems(data.messages);setError('')}}catch(e){if(current.current===story)setError(String(e))}},[story])
 useEffect(()=>{setItems([]);setError('');refresh();const timer=setInterval(refresh,2500);return()=>clearInterval(timer)},[refresh])
 const send=async(role:string,message:string)=>{
  if(!story||sending)return false
  setSending(true)
  if(!pending.current||pending.current.story_id!==story||pending.current.role!==role||pending.current.message!==message)pending.current={story_id:story,role,message,request_id:crypto.randomUUID()}
  try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending.current)});if(!r.ok){const b=await r.json().catch(()=>({}));throw Error(b.error||'Không gửi được lệnh')};pending.current=undefined;await refresh();return true}catch(e){setError(String(e));return false}finally{setSending(false)}
 }
 return{items,error,sending,send}
}
