import { useEffect, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import { Vector3 } from 'three'
import type { Group } from 'three'
import { followRoute } from './officeNavigation'
import type { OfficeNavigation, Point } from './officeNavigation'
import type { ActorPositions } from './OfficeActivity'

export type Speech = {role:string;question:string;reply:string;id:number;label?:string}
const titles:Record<string,string>={pm:'PM · Bạn',sa:'SA',ba:'BA',backend:'Backend',frontend:'Frontend',reviewer:'Reviewer',qa:'QA',tester:'TESTER',devops:'DEVOPS'}
const reduceMotion = typeof window!=='undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
function Part({pos,size,color}:{pos:[number,number,number];size:[number,number,number];color:string}){return <mesh position={pos} castShadow><boxGeometry args={size}/><meshStandardMaterial color={color}/></mesh>}
export function OfficeActor({role,color,index,home,working,status,taskLabel,speech,onPick,positions,displayName,navigation}:{navigation:OfficeNavigation;displayName?:string;role:string;color:string;index:number;home:[number,number];working:boolean;status:string;taskLabel?:string;speech?:Speech;onPick:()=>void;onDragging?:(value:boolean)=>void;positions?:ActorPositions}){
 const body=useRef<Group>(null),left=useRef<Group>(null),right=useRef<Group>(null),arm=useRef<Group>(null)
 const [action,setAction]=useState('Đọc sách')
 const [hovered,setHovered]=useState(false)
 const title = displayName ?? titles[role] ?? role.toUpperCase()
 const ball=useRef<Group>(null)
 const pulse=useRef<Group>(null)
 const orbit=useRef<Group>(null)
 const activity=useRef('Đọc sách')
 const destinations=[{x:-4,z:-5,action:'Đá bóng'},{x:7,z:-8,action:'Đọc sách'},{x:9,z:-4.7,action:'Uống trà'},{x:10.5,z:8,action:'Nghỉ ngơi'}]
 const nav=useRef({destination:index%4,wait:0})
 const route=useRef({key:'',points:[] as Point[]})
 useEffect(()=>{route.current.key=''},[navigation])
 useFrame(({clock},delta)=>{
  if(!body.current)return
  const t=clock.elapsedTime,n=nav.current,dest=destinations[n.destination]
  let next=role==='pm'?'Điều hành':'Đọc sách'
  let target:Point=[home[0],home[1]+(role==='pm'?.85:1.85)]
  if(working){next='Đang xử lý';n.wait=0}
  else if(role!=='pm'&&!reduceMotion){target=[dest.x,dest.z];next=dest.action}
  const previousX=body.current.position.x,previousZ=body.current.position.z
  const walking=followRoute(body.current.position,target,navigation,route.current,Math.min(delta,.05)*(working?2.5:1.4))
  if(walking){next='Đi đến bàn';if(!working)next='Đi dạo';body.current.rotation.y=Math.atan2(previousX-body.current.position.x,previousZ-body.current.position.z)}
  else{
   body.current.rotation.y=0
   if(!working&&role!=='pm'&&!reduceMotion){
    n.wait+=delta
    if(n.wait>15+index*2){n.destination=(n.destination+1)%destinations.length;n.wait=0}
   }
  }
  const onPitch=body.current.position.x>=-8.2&&body.current.position.x<=.2&&body.current.position.z>=-8.25&&body.current.position.z<=-2.35
  body.current.position.y=next==='Nghỉ ngơi'?-.2:onPitch?.24:0
  if(positions) (positions[role] ??= new Vector3()).copy(body.current.position)
  if(pulse.current) pulse.current.scale.setScalar(reduceMotion?1:1+.13*Math.sin(t*3))
  if(orbit.current) orbit.current.rotation.y=reduceMotion?0:t*1.1
  if(next!==activity.current){activity.current=next;setAction(next)}
  const playing=next==='Đá bóng'&&!reduceMotion
  if(left.current)left.current.rotation.x=playing?Math.max(0,Math.sin(t*3))*.9:walking?Math.sin(t*6)*.48:next==='Nghỉ ngơi'?-1:0
  if(right.current)right.current.rotation.x=walking?-Math.sin(t*6)*.48:next==='Nghỉ ngơi'?-1:0
  if(arm.current)arm.current.rotation.x=walking?Math.sin(t*6)*.35:working? .78+(reduceMotion?0:Math.sin(t*9)*.1)
    :!reduceMotion&&next==='Uống trà'?-.55+Math.sin(t*1.6)*.2:0
  if(ball.current){ball.current.position.z=-.6-(reduceMotion?0:Math.max(0,Math.sin(t*3))*.8);ball.current.rotation.x=t*2}
 })
 const text=role==='pm'?((speech?.question||'')+(speech?.role==='team'&&speech.reply?'\n\nĐiều phối: '+speech.reply:'')):speech?.role===role?speech.reply:undefined
 return <group ref={body} position={[home[0],0,home[1]+(role==='pm'?.85:1.85)]} onPointerOver={e=>{e.stopPropagation();setHovered(true)}} onPointerOut={()=>setHovered(false)} onClick={e=>{e.stopPropagation();onPick()}}>
  {working&&<group position={[0,.12,0]}>
    <mesh rotation={[-Math.PI/2,0,0]} raycast={()=>null} renderOrder={3}><circleGeometry args={[.74,64]}/><meshBasicMaterial color="#a78bfa" transparent opacity={.17} depthTest={false} depthWrite={false} toneMapped={false}/></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} raycast={()=>null} renderOrder={4}><ringGeometry args={[.67,.73,64]}/><meshBasicMaterial color="#c9adff" transparent opacity={.98} depthTest={false} depthWrite={false} toneMapped={false}/></mesh>
    <group ref={pulse}><mesh rotation={[-Math.PI/2,0,0]} raycast={()=>null} renderOrder={4}><ringGeometry args={[.93,.96,64]}/><meshBasicMaterial color="#f1cc96" transparent opacity={.78} depthTest={false} depthWrite={false} toneMapped={false}/></mesh></group>
    <group ref={orbit}>
      {[0,Math.PI].map(angle=><group key={angle} rotation={[0,angle,0]}>
        <mesh rotation={[-Math.PI/2,0,0]} raycast={()=>null} renderOrder={5}><ringGeometry args={[.79,.85,32,1,0,Math.PI*.35]}/><meshBasicMaterial color="#e8d6ff" transparent opacity={.9} depthTest={false} depthWrite={false} toneMapped={false}/></mesh>
        <mesh position={[.82,.035,0]} raycast={()=>null} renderOrder={6}><sphereGeometry args={[.055,12,8]}/><meshBasicMaterial color="#ffe2ad" depthTest={false} depthWrite={false} toneMapped={false}/></mesh>
      </group>)}
    </group>
  </group>}
  <mesh position={[0,.8,0]}><capsuleGeometry args={[.32,1.1,4,8]}/><meshBasicMaterial transparent opacity={0} depthWrite={false}/></mesh>
  <Part pos={[0,.82,0]} size={[.46,.62,.3]} color={color}/>
  <mesh position={[0,1.35,0]} castShadow><sphereGeometry args={[.23,16,12]}/><meshStandardMaterial color="#edccb0"/></mesh>
  <mesh position={[0,1.49,.025]}><sphereGeometry args={[.235,12,8,0,Math.PI*2,0,Math.PI/2]}/><meshStandardMaterial color={role==='pm'?'#26344a':'#493e43'}/></mesh>
  <group ref={left} position={[-.13,.55,0]}><Part pos={[0,-.25,0]} size={[.17,.5,.18]} color="#23324b"/><Part pos={[0,-.49,-.06]} size={[.2,.12,.3]} color="#102033"/></group>
  <group ref={right} position={[.13,.55,0]}><Part pos={[0,-.25,0]} size={[.17,.5,.18]} color="#23324b"/><Part pos={[0,-.49,-.06]} size={[.2,.12,.3]} color="#102033"/></group>
  <Part pos={[-.29,.8,-.08]} size={[.13,.45,.15]} color={color}/>
  <group ref={arm} position={[.29,1,0]}><Part pos={[0,-.2,-.07]} size={[.13,.43,.15]} color={color}/>{action==='Uống trà'&&<group position={[0,-.13,-.28]}><mesh><cylinderGeometry args={[.11,.09,.2,12]}/><meshStandardMaterial color="#e6e4d3"/></mesh><mesh position={[.1,0,0]} rotation={[0,Math.PI/2,0]}><torusGeometry args={[.07,.025,6,12]}/><meshStandardMaterial color="#e6e4d3"/></mesh></group>}</group>
  {action==='Đọc sách'&&<group position={[0,.89,-.32]} rotation={[-.5,0,0]}><Part pos={[-.12,0,0]} size={[.24,.04,.32]} color="#d9e0c9"/><Part pos={[.12,0,0]} size={[.24,.04,.32]} color="#9ecfc4"/></group>}
  {action==='Đá bóng'&&<group ref={ball} position={[0,.13,-.7]}><mesh><icosahedronGeometry args={[.15,1]}/><meshStandardMaterial color="#f4f1df" flatShading/></mesh><mesh><icosahedronGeometry args={[.152,0]}/><meshStandardMaterial color="#243247" wireframe/></mesh></group>}
  {action==='Nghỉ ngơi'&&<mesh position={[0,.2,.1]}><cylinderGeometry args={[.48,.5,.4,24]}/><meshStandardMaterial color={color}/></mesh>}
  {(text||hovered||working)&&<Html center position={[0,2.05,0]} distanceFactor={20} zIndexRange={[20,0]}><div className="actor-overlay" onPointerEnter={()=>setHovered(true)} onPointerLeave={()=>setHovered(false)}>{text&&<div key={speech?.id} className={'speech-bubble '+(role==='pm'?'pm-speech':'')} role="status"><strong>{speech?.label ?? (role==='pm'?'Bạn nói':title+' trả lời')}</strong><p>{text}</p></div>}{(hovered||working)&&<button className={'agent-tag '+(working?'working':'')} onClick={onPick}><span className="tag-dot" style={{background:color}}/>{title}<small>{status}</small><em>{working?(taskLabel||'Đang xử lý Story'):role==='pm'?'Đại diện của bạn':action+' · hoạt ảnh khi chờ'}</em></button>}</div></Html>}
 </group>
}
