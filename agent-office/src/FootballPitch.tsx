import { Html } from '@react-three/drei'
function Bar({p,s,color='#e8f8ed'}:{p:[number,number,number];s:[number,number,number];color?:string}){return <mesh position={p} castShadow><boxGeometry args={s}/><meshStandardMaterial color={color} roughness={.7}/></mesh>}
function Goal({z,r=0}:{z:number;r?:number}){return <group position={[0,0,z]} rotation={[0,r,0]}>{[-1.05,1.05].map(x=><Bar key={x} p={[x,.72,0]} s={[.065,1.4,.065]}/>)}<Bar p={[0,1.42,0]} s={[2.16,.065,.065]}/><Bar p={[0,1.42,-.6]} s={[2.16,.05,.05]}/>{[-1.05,1.05].map(x=><group key={x}><Bar p={[x,.72,-.6]} s={[.045,1.4,.045]}/><Bar p={[x,1.42,-.3]} s={[.045,.045,.6]}/></group>)}{Array.from({length:13},(_,i)=><Bar key={i} p={[-1.05+i*.175,.72,-.6]} s={[.012,1.4,.012]} color="#b3d7d1"/>)}{Array.from({length:8},(_,i)=><Bar key={i} p={[0,.1+i*.18,-.6]} s={[2.1,.012,.012]} color="#b3d7d1"/>)}{[-1.05,1.05].map(x=><group key={x}>{[0,.2,.4,.6].map(d=><Bar key={d} p={[x,.72,-d]} s={[.012,1.4,.012]} color="#b3d7d1"/>)}</group>)}</group>}
export default function FootballPitch({highlight=false}:{highlight?:boolean}){return <group position={[-4,0,-5.3]}>
 <Bar p={[0,.09,0]} s={[8.4,.18,5.9]} color="#1a434e"/>
 {Array.from({length:10},(_,i)=><Bar key={i} p={[0,.2,-2.5+i*.55]} s={[7.8,.03,.55]} color={i%2?'#3a9c69':'#348b60'}/>)}
 {[-3.75,3.75].map(x=><Bar key={x} p={[x,.23,0]} s={[.035,.015,5.2]}/>)}
 {[-2.6,2.6].map(z=><Bar key={z} p={[0,.23,z]} s={[7.5,.015,.035]}/>)}
 <Bar p={[0,.23,0]} s={[7.5,.015,.035]}/><mesh rotation={[-Math.PI/2,0,0]} position={[0,.24,0]}><ringGeometry args={[.64,.68,48]}/><meshBasicMaterial color="#e8f8ed"/></mesh>
 {[-1,1].map(a=><group key={a}><Bar p={[0,.24,a*1.65]} s={[3.4,.015,.035]}/>{[-1.7,1.7].map(x=><Bar key={x} p={[x,.24,a*2.12]} s={[.035,.015,.95]}/>)}<Bar p={[0,.24,a*2.6]} s={[3.4,.015,.035]}/></group>)}
 <Goal z={-2.6}/><Goal z={2.6} r={Math.PI}/>
 {[-4,4].map(x=><group key={x}>{[-2.7,2.7].map(z=><group key={z}><Bar p={[x,1.7,z]} s={[.07,3.3,.07]} color="#45687c"/><Bar p={[x,3.35,z]} s={[.7,.18,.3]} color="#ddeffa"/><pointLight position={[x,3.1,z]} color="#ccf5ff" intensity={5} distance={7} decay={2}/></group>)}</group>)}
 {highlight&&<mesh rotation={[-Math.PI/2,0,0]} position={[0,.26,0]}><planeGeometry args={[8,5.5]}/><meshBasicMaterial color="#a7ffbf" transparent opacity={.22} depthWrite={false}/></mesh>}
 <Html center position={[-2.7,.3,3]} distanceFactor={23}><div className="room-sign">SÂN BÓNG · KHU VẬN ĐỘNG</div></Html>
 </group>}
