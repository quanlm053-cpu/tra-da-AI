import { useEffect, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, RoundedBox } from '@react-three/drei'
import { Vector3 } from 'three'
import type { Group } from 'three'
import { followRoute } from './officeNavigation'
import type { OfficeNavigation, Point } from './officeNavigation'
import type { ReactNode } from 'react'

export type NewSeat={id:string;name:string;x:number;z:number}
const BOOTH:[number,number]=[-18,-7]
const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches
function Block({p,s,c}:{p:[number,number,number];s:[number,number,number];c:string}){
 return <mesh position={p} castShadow receiveShadow><boxGeometry args={s}/><meshStandardMaterial color={c} roughness={.45}/></mesh>
}
function Booth(){return <group position={[BOOTH[0],0,BOOTH[1]]}>
 <Block p={[0,.12,0]} s={[2,.24,2]} c="#24384b"/>
 <RoundedBox position={[0,2.95,0]} args={[2, .65,2]} radius={.25}><meshStandardMaterial color="#ba394b"/></RoundedBox>
 {[-.88,.88].flatMap(x=>[-.88,.88].map(z=><Block key={x+','+z} p={[x,1.55,z]} s={[.16,2.7,.16]} c="#d64956"/>))}
 {[.5,1.15,1.8,2.45].map(y=><group key={y}>
 <Block p={[0,y,-.88]} s={[1.8,.08,.1]} c="#bd3b4b"/>
 {[-.88,.88].map(x=><Block key={x} p={[x,y,0]} s={[.1,.08,1.8]} c="#bd3b4b"/>)}</group>)}
 {[-.88,.88].map(x=><mesh key={x} position={[x,1.55,0]}><boxGeometry args={[.025,2.5,1.7]}/><meshStandardMaterial color="#84d5e5" transparent opacity={.13} depthWrite={false}/></mesh>)}
 <Block p={[0,.55,.25]} s={[.8,.14,.65]} c="#d5bda1"/>
 <Block p={[0,.28,.25]} s={[.12,.55,.12]} c="#8b6670"/>
 <Html center position={[0,2.65,.95]} distanceFactor={22}><div className="helpdesk-sign">HELPDESK</div></Html>
 <pointLight position={[0,2,0]} color="#ffbd83" intensity={8} distance={4}/>
 </group>}
function BuildDesk({seat,progress,children}:{seat:NewSeat;progress:number;children:ReactNode}){
 const orbit=useRef<Group>(null),scan=useRef<Group>(null)
 useFrame(({clock})=>{
  if(orbit.current)orbit.current.rotation.y=reduced()?0:-clock.elapsedTime*.65
  if(scan.current){scan.current.position.y=.15+(reduced()?0:(clock.elapsedTime*.7)%2.2)}
 })
 return <group>{children}
 {progress<1&&<group position={[seat.x,.16,seat.z]}>
 <mesh rotation={[-Math.PI/2,0,0]} renderOrder={30} raycast={()=>null}><ringGeometry args={[1.53,1.61,96]}/><meshBasicMaterial color="#ffd45f" transparent opacity={1} depthWrite={false} toneMapped={false}/></mesh>
 <mesh rotation={[-Math.PI/2,0,0]} renderOrder={29} raycast={()=>null}><ringGeometry args={[1.68,1.7,96]}/><meshBasicMaterial color="#ffedaf" transparent opacity={.75} depthWrite={false} toneMapped={false}/></mesh>
 <group ref={orbit}>{[0,Math.PI].map(angle=><mesh key={angle} rotation={[-Math.PI/2,0,angle]} renderOrder={31} raycast={()=>null}><ringGeometry args={[1.75,1.82,48,1,0,Math.PI*.35]}/><meshBasicMaterial color="#fff0be" depthWrite={false} toneMapped={false}/></mesh>)}</group>
 {Array.from({length:16},(_,i)=><group key={i} rotation={[0,i*Math.PI/8,0]}><mesh position={[1.93,0,0]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[.13,.035]}/><meshBasicMaterial color="#ffd45f" toneMapped={false} depthWrite={false}/></mesh></group>)}
 <mesh position={[0,.5,0]}><boxGeometry args={[2.7,1.05,1.35]}/><meshBasicMaterial color="#6fe6f0" wireframe transparent opacity={.14} depthWrite={false} toneMapped={false}/></mesh>
 {progress>0&&<group ref={scan}><mesh rotation={[-Math.PI/2,0,0]} raycast={()=>null}><planeGeometry args={[2.7,1.35]}/><meshBasicMaterial color="#69e5ee" transparent opacity={.12} depthWrite={false} toneMapped={false}/></mesh></group>}
 </group>}
 </group>
}
export default function Helpdesk({seats,onPending,renderDesk,paused=false,navigation}:{seats:NewSeat[];navigation:OfficeNavigation;paused?:boolean;onPending:(ids:string[])=>void;renderDesk:(seat:NewSeat,progress:number)=>ReactNode}){
 const route=useRef({key:'',points:[] as Point[]})
 useEffect(()=>{route.current.key=''},[navigation])
 const seen=useRef<Set<string>|null>(null), queue=useRef<string[]>([])
 const state=useRef({phase:'idle',id:'',elapsed:0,leg:0,progress:0})
 const body=useRef<Group>(null), arm=useRef<Group>(null), legs=useRef<Group>(null), sparks=useRef<Group>(null)
 const [builds,setBuilds]=useState<Record<string,number>>({})
 const [message,setMessage]=useState('Sẵn sàng hỗ trợ')
 const seatsRef=useRef(seats);seatsRef.current=seats
 useEffect(()=>{
  // The first loaded roster is furnished already. Only additions observed in this session build.
  if(!seen.current){seen.current=new Set(seats.map(s=>s.id));return}
  const ids=new Set(seats.map(s=>s.id))
  for(const seat of seats)if(!seen.current.has(seat.id)){queue.current.push(seat.id);setBuilds(v=>({...v,[seat.id]:0}))}
  seen.current=ids
  queue.current=queue.current.filter(id=>ids.has(id))
 },[seats.map(s=>s.id).join('|')])
 useEffect(()=>{onPending(Object.keys(builds).filter(id=>builds[id]<1))},[builds,onPending])
 useFrame(({clock},dt)=>{
  const n=state.current, actor=body.current;if(!actor)return
  dt=Math.min(dt,.06)
  if(n.phase==='idle'&&!paused&&queue.current.length){n.id=queue.current.shift()!;n.phase='out';n.leg=0;n.progress=0;setMessage('Đang chuẩn bị bàn mới')}
  const seat=seatsRef.current.find(s=>s.id===n.id)
  if(n.phase!=='idle'&&!seat){n.phase='back';n.leg=0}
  const target:Point=n.phase==='out'&&seat?[seat.x,seat.z+1.85]:[BOOTH[0],BOOTH[1]+.2]
  const oldX=actor.position.x,oldZ=actor.position.z
  const walk=n.phase!=='build'&&followRoute(actor.position,target,navigation,route.current,dt*3.4)
  const arrived=Math.hypot(target[0]-actor.position.x,target[1]-actor.position.z)<.08
  if(walk)actor.rotation.y=Math.atan2(oldX-actor.position.x,oldZ-actor.position.z)
  else if(arrived&&n.phase==='out'){n.phase='build';n.elapsed=0;setMessage('Đang lắp bàn và máy tính')}
  else if(arrived&&n.phase==='back'){n.phase='idle';setMessage('Sẵn sàng hỗ trợ')}
  if(n.phase==='build'&&seat){
   n.elapsed+=dt;const p=reduced()?1:Math.min(1,n.elapsed/12)
   const stage=p
   if(Math.abs(stage-n.progress)>.025||p===1){n.progress=stage;setBuilds(v=>({...v,[seat.id]:p===1?1:stage}))}
   actor.rotation.y=0;actor.position.y=-.28
   if(p===1){n.phase='back';n.leg=0;setMessage('Đã lắp xong · quay về Helpdesk')}
  }else actor.position.y=n.phase==='idle'?-.1:0
  if(arm.current)arm.current.rotation.x=n.phase==='build'&&!reduced()?-.7-Math.max(0,Math.sin(clock.elapsedTime*12))*1.2:walk?Math.sin(clock.elapsedTime*9)*.5:-.5
  if(legs.current)legs.current.rotation.x=n.phase==='idle'?-1.1:n.phase==='build'?-.65:walk&&!reduced()?Math.sin(clock.elapsedTime*9)*.22:0
  if(sparks.current){sparks.current.visible=n.phase==='build'&&!reduced()&&Math.sin(clock.elapsedTime*12)>.7;sparks.current.rotation.y=clock.elapsedTime*2}
 })
 const card=useRef<HTMLDivElement>(null)
 const current=seats.find(seat=>seat.id===state.current.id)
 const progress=current?builds[current.id]??0:0
 const busy=message!=='Sẵn sàng hỗ trợ'
 return <><Booth/>
 {busy&&current&&<Html position={[current.x,1,current.z]} zIndexRange={[12,0]} style={{pointerEvents:'none'}}
 calculatePosition={(_object,camera,size)=>{
  // Reserve the entire projected assembly area, including the worker and raised parts.
  const corners=[]
  for(const x of [-2.3,2.3])for(const z of [-1.5,2.4])for(const y of [0,3.3]){
   const p=new Vector3(current.x+x,y,current.z+z).project(camera)
   corners.push([(p.x+1)*size.width/2,(1-p.y)*size.height/2])
  }
  const left=Math.min(...corners.map(p=>p[0])),right=Math.max(...corners.map(p=>p[0]))
  const top=Math.min(...corners.map(p=>p[1])),bottom=Math.max(...corners.map(p=>p[1]))
  const width=208,height=82,gap=24
  let x=left-width-gap,y=(top+bottom-height)/2,side='left'
  if(x<12){x=right+gap;side='right'}
  if(x+width>size.width-12){x=(left+right-width)/2;y=top-height-gap;side='above'}
  x=Math.max(12,Math.min(size.width-width-12,x));y=Math.max(76,Math.min(size.height-height-16,y))
  if(card.current)card.current.dataset.side=side
  return [x,y]
 }}>
 <div ref={card} className="helpdesk-build-hud helpdesk-build-callout" role="status">
 <strong>🔨 {progress>=1?'Đã lắp xong':'Đang lắp bàn'} · {current.name}</strong>
 <span>{message}</span>
 <div className="helpdesk-build-track"><i style={{width:Math.round(progress*100)+'%'}}/></div>
 </div></Html>}
 {seats.map(seat=><BuildDesk key={seat.id} seat={seat} progress={builds[seat.id]??1}>{renderDesk(seat,builds[seat.id]??1)}</BuildDesk>)}
 <group ref={body} position={[BOOTH[0],-.25,BOOTH[1]+.2]}>
 <Block p={[0,.8,0]} s={[.48,.58,.32]} c="#f2b75b"/>
 <mesh position={[0,1.3,0]} castShadow><sphereGeometry args={[.23,16,12]}/><meshStandardMaterial color="#edccb0"/></mesh>
 <mesh position={[0,1.48,0]}><sphereGeometry args={[.26,12,8,0,Math.PI*2,0,Math.PI/2]}/><meshStandardMaterial color="#ffce65"/></mesh>
 <group ref={legs}>{[-.13,.13].map(x=><Block key={x} p={[x,.29,0]} s={[.18,.55,.22]} c="#293e56"/>)}</group>
 <Block p={[-.31,.8,0]} s={[.14,.45,.16]} c="#efb45a"/>
 <group ref={arm} position={[.32,1,0]}><Block p={[0,-.2,0]} s={[.14,.45,.16]} c="#efb45a"/><Block p={[0,-.4,-.2]} s={[.06,.06,.4]} c="#8a6047"/><Block p={[0,-.4,-.4]} s={[.28,.16,.15]} c="#c4d9e3"/></group>
 <group ref={sparks} position={[0,.65,-.6]}>{Array.from({length:8},(_,i)=><mesh key={i} position={[Math.sin(i)*.5,.1+(i%3)*.12,Math.cos(i)*.5]}><sphereGeometry args={[.035,6,4]}/><meshBasicMaterial color="#ffe2a0"/></mesh>)}</group>

 </group></>
}
