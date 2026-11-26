export type Point=[number,number]
type Rect={x:number;z:number;w:number;d:number}
export function officeNavigation(homes:Point[],front:number,lending:boolean){
 const blocks:Rect[]=[]
 const add=(x:number,z:number,w:number,d:number)=>blocks.push({x,z,w:w/2+.32,d:d/2+.32})
 for(const [x,z] of homes){add(x,z-.1,2.85,1.5);add(x,z+.9,.8,.8)}
 if(homes.length<8)add(-9.3,-3.5,2.85,1.5)
 if(!lending){add(-9.3,0,2.85,1.5);add(-7.7,3.5,2.85,1.5)}
 // All solid scene furniture and landscaping share this collision map.
 for(const [x,z] of [[-12,-9],[-9,-9],[-12,-5],[-12,0],[-12,5],[-12,9],[0,9],[12,9],[12,5],[12,-4],[12,-9],[-9,-6],[9,-6],[9,6],[-9,6],[2,-6]])add(x,z,.7,.7)
 add(9,-6.8,5.2,1.2);add(8,-9.8,6, .8);add(3.5,-9.7,1.8,.8)
 add(-8,8,6.2,1.2);add(10,-.7,2.5,1.8);add(10,2.2,2.5,1.8)
 add(6,1.5,3.2,3.2)
 for(const [x,z] of [[4,1.5],[8,1.5],[6,-.5],[6,3.5]])add(x,z,.8,.85)
 add(6,6.2,4.2,1.4)
 for(const [x,z] of [[5,6],[8,6],[5,8.5],[8,8.5]])add(x,z,1.35,1.35)
 add(6.5,7.3,1.3,1.3)
 for(const z of [-7.9,-2.7])add(-4,z,2.3,.8)
 for(const x of [-8,0])for(const z of [-8,-2.6])add(x,z,.25,.25)
 if(lending){add(-18.9,-7,.16,2);add(-17.1,-7,.16,2);add(-18,-7.9,1.8,.16)}
 const minX=lending?-23.4:-13.4,maxX=13.4,minZ=-10.1,maxZ=front-.45,cell=.32
 const free=([x,z]:Point)=>x>minX&&x<maxX&&z>minZ&&z<maxZ&&!blocks.some(b=>Math.abs(x-b.x)<b.w&&Math.abs(z-b.z)<b.d)
 const clear=(a:Point,b:Point)=>{const n=Math.ceil(Math.hypot(a[0]-b[0],a[1]-b[1])/.1);for(let i=0;i<=n;i++)if(!free([a[0]+(b[0]-a[0])*i/Math.max(1,n),a[1]+(b[1]-a[1])*i/Math.max(1,n)]))return false;return true}
 function path(start:Point,end:Point):Point[]{
  if(!free(start)||!free(end))return []
  if(clear(start,end))return [end]
  const cols=Math.ceil((maxX-minX)/cell),rows=Math.ceil((maxZ-minZ)/cell)
  const point=(id:number):Point=>[minX+(id%cols+.5)*cell,minZ+(Math.floor(id/cols)+.5)*cell]
  const near=(p:Point)=>{const cx=Math.floor((p[0]-minX)/cell),cz=Math.floor((p[1]-minZ)/cell);let best=-1,dist=Infinity
   for(let dz=-2;dz<=2;dz++)for(let dx=-2;dx<=2;dx++){const x=cx+dx,z=cz+dz,id=z*cols+x;if(x<0||x>=cols||z<0||z>=rows)continue;const q=point(id),d=Math.hypot(q[0]-p[0],q[1]-p[1]);if(d<dist&&clear(p,q)){best=id;dist=d}}
   return best}
  const first=near(start),last=near(end);if(first<0||last<0)return []
  const open=new Set([first]),g=new Map([[first,0]]),parent=new Map<number,number>(),closed=new Set<number>()
  const heuristic=(id:number)=>Math.hypot((id%cols)-(last%cols),Math.floor(id/cols)-Math.floor(last/cols))
  while(open.size){let current=-1,score=Infinity;for(const id of open){const f=g.get(id)!+heuristic(id);if(f<score){score=f;current=id}}
   if(current===last){const route:Point[]=[end];let n=current;while(n!==first){route.unshift(point(n));n=parent.get(n)!}route.unshift(point(first))
    const smooth:Point[]=[];let origin=start;for(let i=0;i<route.length;){let j=route.length-1;while(j>i&&!clear(origin,route[j]))j--;smooth.push(route[j]);origin=route[j];i=j+1}return smooth}
   open.delete(current);closed.add(current)
   const x=current%cols,z=Math.floor(current/cols)
   for(const [dx,dz] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]]){const nx=x+dx,nz=z+dz,id=nz*cols+nx;if(nx<0||nx>=cols||nz<0||nz>=rows||closed.has(id)||!clear(point(current),point(id)))continue
    const cost=g.get(current)!+Math.hypot(dx,dz);if(cost<(g.get(id)??Infinity)){g.set(id,cost);parent.set(id,current);open.add(id)}}
  }return []
 }
 return {free,clear,path}
}
export type OfficeNavigation=ReturnType<typeof officeNavigation>
export function followRoute(position:{x:number;z:number},target:Point,nav:OfficeNavigation,route:{key:string;points:Point[]},distance:number){
 const key=target.join(',');if(route.key!==key){route.key=key;route.points=nav.path([position.x,position.z],target)}
 while(route.points.length){const next=route.points[0],dx=next[0]-position.x,dz=next[1]-position.z,d=Math.hypot(dx,dz);if(d<.025){route.points.shift();continue}
  const step=Math.min(distance,d),p:Point=[position.x+dx/d*step,position.z+dz/d*step];if(!nav.clear([position.x,position.z],p)){route.key='';return false}
  position.x=p[0];position.z=p[1];return true}
 return false
}
