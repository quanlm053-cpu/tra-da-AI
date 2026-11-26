export type Placement={x:number;z:number;activity:'Đá bóng'|'Đọc sách'|'Uống trà'|'Nghỉ ngơi'|'Đứng chờ'}
export function dropPlacement(x:number,z:number):Placement{
 x=Math.max(-12.8,Math.min(12.8,x));z=Math.max(-9.8,Math.min(9.8,z))
 if(x>=-8&&x<=0&&z>=-8&&z<=-2.5)return{x:Math.max(-7,Math.min(-1,x)),z:Math.max(-7,Math.min(-3.5,z)),activity:'Đá bóng'}
 if(x>=5&&z<=-8)return{x:Math.max(6,Math.min(11,x)),z:-8,activity:'Đọc sách'}
 if(x>=5&&z>=-8&&z<=-4)return{x:Math.max(6,Math.min(11,x)),z:-5.4,activity:'Uống trà'}
 if(x>=3&&z>=5)return{x:Math.max(4,Math.min(10,x)),z:Math.max(5.4,Math.min(9,z)),activity:'Nghỉ ngơi'}
 return{x,z,activity:'Đứng chờ'}
}
