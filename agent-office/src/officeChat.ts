type JobView={state:string;stage:string;error?:string;results:Record<string,{outcome:string;summary:string}>;tasks:{progress:number;status:string}[]}
export function addressedRole(question:string){
 const q=question.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d')
 if(/\b(ca doi|tat ca|team|cung nhau)\b/.test(q)&&/\b(lam|bat dau|trien khai|tiep tuc|start)\b/.test(q)&&!/(tien do|den dau|xong chua|dang lam gi|bao cao|tai sao)/.test(q))return 'team'
 if(/\bba\b|phan tich|nghiep vu/.test(q))return 'ba'
 if(/backend|back end|\bbe\b|api/.test(q))return 'backend'
 if(/frontend|front end|\bfe\b|giao dien/.test(q))return 'frontend'
 if(/review|duyet code/.test(q))return 'reviewer'
 if(/\bqa\b|tester|kiem thu/.test(q))return 'qa'
 return undefined
}
export function progressReply(role:string,job:JobView|undefined,alive:boolean,failed:boolean){
 if(failed||!job)return 'Mình chưa lấy được dữ liệu mới. Bạn kiểm tra kết nối dịch vụ giúp mình nhé; chưa thể xác nhận tiến độ.'
 const result=job.results[role]
 const running=alive&&job.state==='active'&&job.stage===role
 const state=running?'Mình đang thực hiện công việc.':job.state==='attention'&&job.stage===role?'Mình đang bị dừng: '+(job.error||'cần xử lý')+'.':result?.outcome==='passed'?'Mình đã bàn giao kết quả.':result?.outcome==='blocked'?'Mình đang có vướng mắc.':'Mình đang chờ đến lượt, chưa có kết quả bàn giao.'
 return state+(result?.summary?' Báo cáo gần nhất: '+result.summary:'')+(!alive?' Dịch vụ hiện mất tín hiệu; đây là báo cáo đã lưu.':'')
}
