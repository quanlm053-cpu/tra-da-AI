import { useMemo } from 'react'
import { CanvasTexture, SRGBColorSpace } from 'three'
import { Html, RoundedBox } from '@react-three/drei'
function BrandSign({lending=false}:{lending?:boolean}){const texture=useMemo(()=>{const canvas=document.createElement('canvas');canvas.width=2048;canvas.height=170;const c=canvas.getContext('2d')!;c.fillStyle='#68c6d9';c.fillRect(0,0,2048,170);c.fillStyle='#efffff';c.font='bold 80px Segoe UI';c.textAlign='center';c.textBaseline='middle';c.fillText(lending?'CLB THIẾT BỊ · VĂN PHÒNG AI':'TICKETLAB · VĂN PHÒNG AI',1024,85);const t=new CanvasTexture(canvas);t.colorSpace=SRGBColorSpace;return t},[lending]);return <mesh position={[-4,2.8,-10.35]}><planeGeometry args={[14.8,.88]}/><meshBasicMaterial map={texture}/></mesh>}
function Block({p,s,c,light=false}:{p:[number,number,number];s:[number,number,number];c:string;light?:boolean}){return <mesh position={p} castShadow receiveShadow><boxGeometry args={s}/><meshStandardMaterial color={c} metalness={.25} roughness={.45} emissive={light?c:'#000'} emissiveIntensity={light?1.5:0}/></mesh>}
function Palm({x,z}:{x:number;z:number}){return <group position={[x,0,z]}><mesh position={[0,.3,0]} castShadow><cylinderGeometry args={[.3,.23,.6,12]}/><meshStandardMaterial color="#c6d4da"/></mesh><Block p={[0,1.05,0]} s={[.09,1.3,.09]} c="#587976"/>{Array.from({length:7},(_,i)=><group key={i} rotation={[0,i*Math.PI*2/7,0]}><mesh position={[.4,1.65,0]} rotation={[0,0,-.35]} scale={[.6,.07,.17]}><sphereGeometry args={[1,6,4]}/><meshStandardMaterial color={i%2?'#438d87':'#70bfa9'}/></mesh></group>)}</group>}
function Chair({x,z,r=0}:{x:number;z:number;r?:number}){return <group position={[x,0,z]} rotation={[0,r,0]}><RoundedBox args={[.72,.16,.65]} position={[0,.6,0]} radius={.08}><meshStandardMaterial color="#496981"/></RoundedBox><RoundedBox args={[.72,.75,.13]} position={[0,1,.3]} radius={.06}><meshStandardMaterial color="#43627b"/></RoundedBox><Block p={[0,.3,0]} s={[.08,.6,.08]} c="#a9c7d2"/><Block p={[0,.08,0]} s={[.8,.06,.08]} c="#3e5a6b"/><Block p={[0,.08,0]} s={[.08,.06,.8]} c="#3e5a6b"/></group>}
function Shelf({x,z}:{x:number;z:number}){return <group position={[x,0,z]}><Block p={[0,1.2,0]} s={[2.4,2.4,.25]} c="#253e50"/>{[.25,1,1.75,2.5].map(y=><Block key={y} p={[0,y,-.2]} s={[2.5,.08,.65]} c="#91b4c3"/>)}{Array.from({length:18},(_,i)=><Block key={i} p={[-1+(i%6)*.36,.53+Math.floor(i/6)*.75,.26]} s={[.18,.48+(i%3)*.06,.3]} c={['#7ec4cf','#e4b38b','#a89ec9','#d2d5b0'][i%4]}/>)}</group>}
function Foosball({x,z}:{x:number;z:number}){return <group position={[x,0,z]}><Block p={[0,1,0]} s={[2.4,.4,1.4]} c="#bba88f"/><Block p={[0,1.22,0]} s={[2.15,.03,1.2]} c="#367a6d"/>{[-1,1].map(a=><Block key={a} p={[a,.48,0]} s={[.12,1,.9]} c="#314a5d"/>)}{[-.75,-.25,.25,.75].map((x,i)=><group key={i}><Block p={[x,1.3,0]} s={[.03,.03,1.8]} c="#c0d8df"/>{[-.35,0,.35].map(z=><Block key={z} p={[x,1.37,z]} s={[.12,.22,.1]} c={i%2?'#d09d86':'#71bccc'}/>)}</group>)}</group>}
export default function OfficeDetails({lending=false}:{lending?:boolean}={}){return <group>
 {/* Blue perimeter lighting and stepped outer deck. */}
 <Block p={[0,-.62,0]} s={[28.6,.2,22.6]} c="#0b213c"/>
 {[-13.8,13.8].map(x=><Block key={x} p={[x,.06,0]} s={[.045,.04,21.5]} c="#2b98bd" light/>)}
 {[-10.8,10.8].map(z=><Block key={z} p={[0,.06,z]} s={[27.5,.04,.045]} c="#2b98bd" light/>)}
 {Array.from({length:27},(_,i)=><Block key={i} p={[-13+i,.04,0]} s={[.014,.02,21.5]} c="#304c64"/>)}
 {/* Raised execution islands, chairs and glass dividers. */}
 {[-6,-2.8,.4].map((x,i)=><group key={x}><Chair x={x} z={.8}/><Block p={[x,.06,.8]} s={[2.8,.06,2.8]} c="#227494"/><Block p={[x,1.1,-.8]} s={[2.7,1.6,.035]} c={i%2?'#3e91a8':'#45819b'}/><Block p={[x,1.9,-.8]} s={[2.7,.025,.045]} c="#8bd4de" light/></group>)}
 {[-4.4,-1.2].map(x=><Chair key={x} x={x} z={4.3}/>)}
 {/* Back-wall display, sticky notes and task boards. */}
 <Block p={[-4,2.8,-10.5]} s={[15,.9,.16]} c="#54b9ce" light/>
 <BrandSign lending={lending}/>
 {[-10,-7,-4,-1,2].map((x,i)=><group key={x}><Block p={[x,1.6,-10.3]} s={[2.1,.75,.09]} c="#284e68"/>{[0,1,2].map(k=><Block key={k} p={[x-.6+k*.6,1.6,-10.22]} s={[.38,.38,.02]} c={['#d2c394','#77c7d7','#a7b4d0'][(i+k)%3]}/>)}</group>)}
 {/* Coffee bar and library along the rear/right wall. */}
 <Shelf x={7} z={-9.8}/><Shelf x={10} z={-9.8}/>
 <Block p={[9,.6,-6.8]} s={[5,1.2,1]} c="#829da9"/><Block p={[9,1.25,-6.8]} s={[5.2,.12,1.2]} c="#dfd1b7"/>
 <Block p={[8,1.62,-6.9]} s={[.65,.7,.6]} c="#263947"/><Block p={[8,1.6,-6.55]} s={[.4,.3,.03]} c="#8ed3df" light/>
 {[9,9.5,10].map(x=><mesh key={x} position={[x,1.46,-6.6]}><cylinderGeometry args={[.12,.1,.28,12]}/><meshStandardMaterial color="#ded8bf"/></mesh>)}
 <Html position={[9,2.6,-6.8]} center distanceFactor={23}><div className="room-sign">THƯ VIỆN & TRÀ CHIỀU</div></Html>
 {/* Lounge with four rounded seats, central table and rug. */}
 <Block p={[7,.05,7]} s={[9,.04,5]} c="#242d49"/>
 {[[5,6],[8,6],[5,8.5],[8,8.5]].map(([x,z],i)=><group key={i}><mesh position={[x,.4,z]} castShadow><torusGeometry args={[.55,.25,10,24]}/><meshStandardMaterial color={i%2?'#b9b2cb':'#71b5cb'}/></mesh><mesh position={[x,.25,z]}><cylinderGeometry args={[.65,.55,.4,24]}/><meshStandardMaterial color={i%2?'#8d839e':'#477e9e'}/></mesh></group>)}
 <mesh position={[6.5,.48,7.3]}><cylinderGeometry args={[.65,.65,.12,32]}/><meshStandardMaterial color="#d6bca1"/></mesh>
 <Html position={[10,.4,8]} center distanceFactor={23}><div className="room-sign">KHU NGHỈ</div></Html>
 <Foosball x={10} z={-.7}/><Foosball x={10} z={2.2}/>
 {[[ -12,-9],[-9,-9],[-12,-5],[-12,0],[-12,5],[-12,9],[0,9],[12,9],[12,5],[12,-4],[12,-9]].map(([x,z],i)=><Palm key={i} x={x} z={z}/>)}
 {/* Wall-mounted analytics screen and lit server cabinets. */}
 <Block p={[-8,.6,8]} s={[6,.9,.9]} c="#1b3048"/>
 {[-10,-8,-6].map(x=><group key={x}><Block p={[x,1.4,8]} s={[1.6,.9,.06]} c="#112133"/>{Array.from({length:7},(_,i)=><Block key={i} p={[x-.6+i*.2,1.2+(i%4)*.08,8.05]} s={[.1,.1+(i%4)*.16,.01]} c="#54bcd6" light/>)}</group>)}
 {[3,4].map(x=><group key={x}><Block p={[x,1,-9.7]} s={[.75,2,.65]} c="#132b41"/>{Array.from({length:6},(_,i)=><Block key={i} p={[x, .3+i*.28,-9.33]} s={[.5,.07,.025]} c={i%2?'#4ba3bd':'#76c7d0'} light/>)}</group>)}
 <mesh rotation={[-Math.PI/2,0,0]} position={[-5,.13,2]}><planeGeometry args={[13,7.5]}/><meshBasicMaterial color="#2ba8dc" transparent opacity={.12} depthWrite={false}/></mesh>
 {[-9,-5,-1].map(x=><group key={x}><Block p={[x,3.7,2]} s={[2.4,.06,.22]} c="#a4eeff" light/><pointLight position={[x,3.3,2]} color="#76d9ff" intensity={22} distance={8}/></group>)}
 <pointLight position={[7,3,7]} color="#c0b6ff" intensity={48} distance={9}/>
 <pointLight position={[6,3,1]} color="#ffd0ac" intensity={42} distance={8}/>
 <pointLight position={[-5,3,2]} color="#3fbfff" intensity={80}/><pointLight position={[8,3,-7]} color="#ffc49c" intensity={45}/>
 </group>}
