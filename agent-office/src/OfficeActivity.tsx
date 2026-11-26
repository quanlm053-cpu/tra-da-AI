import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { BufferAttribute, BufferGeometry, Line as ThreeLine, LineBasicMaterial, Vector3 } from 'three'
import type { Mesh } from 'three'

export type ActorPositions = Record<string, Vector3>
export type FocusRequest = {role:string; revision:number}
export type Handoff = {sender:string; recipient:string; at:number}

export function OfficeActivity({positions,focus,handoff}:{
  positions:ActorPositions; focus?:FocusRequest; handoff?:Handoff
}) {
  const controls = useThree(state=>state.controls) as {target:Vector3;update:()=>void} | null
  const camera = useThree(state=>state.camera)
  const moving = useRef(false)
  const overview = useRef<{position:Vector3;target:Vector3}|null>(null)
  const dot = useRef<Mesh>(null)
  const line = useMemo(()=>{
    const geometry=new BufferGeometry()
    geometry.setAttribute('position',new BufferAttribute(new Float32Array(25*3),3))
    const value=new ThreeLine(geometry,new LineBasicMaterial({color:'#7dbdff',transparent:true,opacity:.85}))
    value.frustumCulled=false
    value.visible=false
    return value
  },[])
  useEffect(()=>()=>{line.geometry.dispose();line.material.dispose()},[line])
  useEffect(()=>{
    if(focus && controls && !overview.current){
      overview.current={position:camera.position.clone(),target:controls.target.clone()}
    }
    moving.current=!!focus || !!overview.current
  },[focus,camera,controls])
  const aim=useMemo(()=>new Vector3(),[])
  const destination=useMemo(()=>new Vector3(),[])
  useFrame((_,delta)=>{
    const target = focus && positions[focus.role]
    const restore = !focus && overview.current
    if(moving.current && controls && (target || restore)){
      if(target){
        aim.set(target.x,target.y+.75,target.z)
        destination.set(target.x+4,target.y+5.5,target.z+7)
      } else if(restore){
        aim.copy(restore.target)
        destination.copy(restore.position)
      }
      const blend=window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : 1-Math.exp(-7*delta)
      controls.target.lerp(aim,blend)
      camera.position.lerp(destination,blend)
      controls.update()
      if(camera.position.distanceTo(destination)<.08){
        moving.current=false
        if(restore) overview.current=null
      }
    }
    const elapsed=handoff ? Date.now()/1000-handoff.at : Infinity
    const from=handoff && positions[handoff.sender]
    const to=handoff && positions[handoff.recipient]
    line.visible=!!(from && to && elapsed>=0 && elapsed<8)
    if(dot.current) dot.current.visible=line.visible
    if(!line.visible || !from || !to) return
    const vertices=line.geometry.getAttribute('position')
    const point=(t:number)=>{
      aim.copy(from).lerp(to,t)
      aim.y+=2.05+Math.sin(Math.PI*t)*1.3
      return aim
    }
    for(let i=0;i<vertices.count;i++){
      const p=point(i/(vertices.count-1))
      vertices.setXYZ(i,p.x,p.y,p.z)
    }
    vertices.needsUpdate=true
    dot.current?.position.copy(point((elapsed%1.8)/1.8))
  })
  return <><primitive object={line}/><mesh ref={dot} visible={false}><sphereGeometry args={[.085,12,8]}/><meshBasicMaterial color="#b7e7ff"/></mesh></>
}
