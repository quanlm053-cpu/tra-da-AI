// Invoked only by the controller. No command or free-form SQL input is accepted.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=path.join(__dirname,'runtime/worktrees/story-44/backend');
const sql=require(path.join(root,'node_modules/mssql/msnodesqlv8'));
const jwt=require(path.join(root,'node_modules/jsonwebtoken'));
const bcrypt=require(path.join(root,'node_modules/bcryptjs'));
const config=require(path.join(root,'db-connection'));
const registry=path.join(__dirname,'runtime/test-fixtures');fs.mkdirSync(registry,{recursive:true});
function fixture(id){if(!/^[a-f0-9]{16}$/.test(id||''))throw Error('Invalid fixture');return JSON.parse(fs.readFileSync(path.join(registry,id+'.json'),'utf8'))}
async function main(input){
 if(process.env.DB_NAME!=='TicketLab_AI_Test')throw Error('Database guard');
 const pool=await new sql.ConnectionPool(config()).connect();
 try{
  const name=(await pool.request().query('SELECT DB_NAME() AS name')).recordset[0].name;
  if(name!=='TicketLab_AI_Test')throw Error('Unexpected database');
  const query=(text,params={})=>{const r=pool.request();for(const [k,v]of Object.entries(params))r.input(k,v);return r.query(text)};
  if(input.action==='status'){
   const transport=(await pool.request().query('SELECT encrypt_option AS encrypted FROM sys.dm_exec_connections WHERE session_id=@@SPID')).recordset[0];
   return {database:name,encrypted:transport.encrypted==='TRUE',driver:'ODBC Driver 17',databaseConnected:true};
  }
  if(input.action==='create'){
   const id=crypto.randomBytes(8).toString('hex'),tag='AI_QA44_'+id;
   const password='Qa44!'+crypto.randomBytes(8).toString('hex');
   const hashed=await bcrypt.hash(password,10),users=[];
   for(let i=0;i<2;i++)users.push((await query("INSERT INTO users(name,email,password,role) OUTPUT INSERTED.user_id VALUES(@name,@email,@password,N'user')",{name:tag+'_'+i,email:tag+'_'+i+'@example.test',password:hashed})).recordset[0].user_id);
   const event=(await query("INSERT INTO events(name,description,location,category,event_date,price,image) OUTPUT INSERTED.event_id VALUES(@name,N'Dedicated QA fixture',N'Test venue',N'music',N'01/12/2026',120000,N'/images/event-1.jpg')",{name:tag})).recordset[0].event_id;
   const types=[];for(const [n,price]of [['Standard',120000],['Free',0]])types.push((await query('INSERT INTO ticket_types(event_id,name,price,quantity_available,quantity_sold) OUTPUT INSERTED.ticket_type_id VALUES(@event,@name,@price,20,0)',{event,name:n,price})).recordset[0].ticket_type_id);
   const value={id,tag,users,event,types};fs.writeFileSync(path.join(registry,id+'.json'),JSON.stringify(value));
   return {...value,email:tag+'_0@example.test',password,tokens:users.map(user_id=>jwt.sign({user_id,role:'user'},process.env.JWT_SECRET,{expiresIn:'4h'}))};
  }
  const f=fixture(input.fixture);const trigger='AI_QA44_'+f.id;
  if(input.action==='snapshot'){
   const stocks=(await query('SELECT * FROM ticket_types WHERE event_id=@event',{event:f.event})).recordset;
   const orders=(await query('SELECT * FROM orders WHERE event_id=@event',{event:f.event})).recordset;
   const tickets=(await query('SELECT * FROM tickets WHERE event_id=@event',{event:f.event})).recordset;
   return {fixture:f.id,stocks,orders,tickets};
  }
  if(input.action==='set-stock'){
   if(!f.types.includes(input.ticket_type_id)||!Number.isInteger(input.available)||input.available<0||input.available>1000||!Number.isInteger(input.sold)||input.sold<0||input.sold>input.available)throw Error('Invalid fixture stock');
   await query('UPDATE ticket_types SET quantity_available=@available,quantity_sold=@sold WHERE ticket_type_id=@type AND event_id=@event',{available:input.available,sold:input.sold,type:input.ticket_type_id,event:f.event});return {updated:true};
  }
  if(input.action==='set-price'){
   if(!f.types.includes(input.ticket_type_id)||!Number.isInteger(input.price)||input.price<0||input.price>2147483647)throw Error('Invalid fixture price');
   await query('UPDATE ticket_types SET price=@price WHERE ticket_type_id=@type AND event_id=@event',{price:input.price,type:input.ticket_type_id,event:f.event});return {updated:true};
  }
  if(input.action==='rollback-on'){
   if(input.point!==undefined&&!['tickets','stock'].includes(input.point))throw Error('Invalid injection point');
   await pool.request().batch(`DROP TRIGGER IF EXISTS dbo.[${trigger}]`);
   const table=input.point==='stock'?'ticket_types':'tickets',operation=input.point==='stock'?'UPDATE':'INSERT';
   await pool.request().batch(`CREATE TRIGGER dbo.[${trigger}] ON dbo.${table} AFTER ${operation} AS BEGIN SET NOCOUNT ON; IF EXISTS(SELECT 1 FROM inserted WHERE event_id=${Number(f.event)}) THROW 51044, 'Dedicated QA fixture rollback injection', 1; END`);return {rollbackInjection:true};
  }
  if(input.action==='rollback-off'||input.action==='cleanup'){
   await pool.request().batch(`DROP TRIGGER IF EXISTS dbo.[${trigger}]`);
   if(input.action==='cleanup'){
    await query('DELETE FROM tickets WHERE event_id=@event; DELETE FROM orders WHERE event_id=@event; DELETE FROM ticket_types WHERE event_id=@event; DELETE FROM events WHERE event_id=@event AND name=@tag; DELETE FROM users WHERE user_id IN (@u1,@u2) AND name LIKE @prefix',{event:f.event,tag:f.tag,u1:f.users[0],u2:f.users[1],prefix:f.tag+'%'});
    fs.unlinkSync(path.join(registry,f.id+'.json'));
   }return {cleaned:true};
  }
  throw Error('Unsupported action');
 }finally{await pool.close()}
}
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',d=>input+=d);process.stdin.on('end',()=>main(JSON.parse(input)).then(r=>process.stdout.write(JSON.stringify(r))).catch(e=>{process.stderr.write(e.code||e.name||'FixtureError');process.exitCode=1}));
