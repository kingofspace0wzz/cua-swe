import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const profiles=JSON.parse(readFileSync(new URL('./profiles.json',import.meta.url)));
const scenarios=[{id:'incident',label:'Collector rollout',note:'Failed operations are missing from the severe view; inspect the received records.'},{id:'healthy',label:'Healthy controls',note:'Routine traffic, recoverable warnings and debug records continue across the same receiver fleet.'},{id:'recovery',label:'Recovery window',note:'A fresh batch includes recovery notices alongside another failed operation.'}];
const bands=['TRACE','DEBUG','INFO','WARN','ERROR','FATAL'];
const clone=x=>JSON.parse(JSON.stringify(x));
export function generate(profile,scenario){
 const p=profiles[profile];const receivers=[
  {id:p.prefix+'-edge',name:'Collector / '+p.names[0],source:{format:'json'},output:{format:'otlp'},resource:{'service.name':p.names[0]},pipeline:'filelog → transform → OTLP'},
  {id:p.prefix+'-sdk',name:'SDK / '+p.names[1],source:{format:'otlp'},output:{format:'otlp'},resource:{'service.name':p.names[1]},pipeline:'OTLP receiver → passthrough'},
  {id:p.prefix+'-legacy',name:'Legacy / '+p.names[2],source:{format:'json'},output:{format:'json'},resource:{'service.name':p.names[2]},pipeline:'JSON receiver → passthrough'},
  {id:p.prefix+'-relay',name:'Syslog relay / '+p.names[3],source:{format:'syslog'},output:{format:'otlp'},resource:{'service.name':p.names[3]},pipeline:'syslog 5424 → OTLP relay (raw PRI severity preserved)'},
 ];
 const meanings=scenario==='healthy'?['INFO','WARN','DEBUG','TRACE','UNSPECIFIED']:scenario==='recovery'?['ERROR','INFO','WARN','FATAL','ERROR','UNSPECIFIED']:['ERROR','INFO','WARN','FATAL','DEBUG','TRACE','ERROR','UNSPECIFIED'];
 const events=[],batches=[],expected=[];
 for(let s=0;s<receivers.length;s++){
  const receiver=receivers[s],records=[];
  meanings.forEach((semantic,i)=>{
   const id=`${p.prefix}-${scenario}-${s}-${i}`;
   const event={id,receiverId:receiver.id,semantic,operation:semantic==='ERROR'?'Payment operation failed':semantic==='FATAL'?'Worker terminated':semantic==='WARN'?'Transient timeout recovered':semantic==='INFO'?'Request completed':semantic==='DEBUG'?'Cache lookup diagnostic':semantic==='TRACE'?'Execution detail':'Opaque application message'};
   events.push(event);
   const record={recordId:id,timeUnixNano:String(BigInt(p.offset+i)*1000000000n),traceId:(s+1).toString(16).repeat(24)+i.toString(16).padStart(8,'0'),spanId:(s+1).toString(16).repeat(8)+i.toString(16).padStart(8,'0'),attributes:{'event.name':scenario+'.operation','deployment.environment.name':p.prefix}};
   let severity;
   if(receiver.source.format==='syslog'){
    // The relay forwards each syslog line inside an OTLP record and keeps the raw RFC 5424 priority.
    const [priority,keyword]=p.relay[semantic];
    record.body=priority===null?`${p.relayHost} ${p.names[3]}: [${keyword}] ${event.operation}`:`<${p.relayFacility*8+priority}>${p.relayHost} ${p.names[3]}: ${event.operation}`;
    record.severityText=keyword;
    if(priority!==null)record.severityNumber=priority;
    // Expected severity is independently selected from event semantics; syslog delivery carries the
    // keyword vocabulary, not an OTel rank, and syslog has no trace level below debug.
    const band=semantic==='UNSPECIFIED'?'UNSPECIFIED':semantic==='TRACE'?'DEBUG':semantic;
    severity={number:band==='UNSPECIFIED'?0:bands.indexOf(band)*4+1,band};
   }else{
    const rank=(p.rank+(i===6?1:0))%4,number=semantic==='UNSPECIFIED'?0:bands.indexOf(semantic)*4+1+rank;
    const text=semantic==='UNSPECIFIED'?'custom-event':p.texts[bands.indexOf(semantic)];
    record.body={message:event.operation,level:s===0?(semantic==='INFO'?'error':'info'):text};
    // The collector retains the original JSON body and emits normalized OTel fields.
    if(receiver.output.format==='otlp'){record.severityNumber=number;record.severityText=text;}
    // Expected severity is independently selected from event semantics; no submitted policy or UI is consulted.
    severity={number:semantic==='UNSPECIFIED'?0:receiver.output.format==='json'?bands.indexOf(semantic)*4+1:number,band:semantic};
   }
   records.push(record);expected.push({deliveryId:`${p.prefix}-${scenario}-batch-${s}`,receiverId:receiver.id,raw:clone(record),severity});
  });
  if(p.reverse)records.reverse();
  batches.push({deliveryId:`${p.prefix}-${scenario}-batch-${s}`,receiverId:receiver.id,records});
 }
 if(p.reverse)batches.reverse();
 return {receivers,batches,events,expected};
}
function canonical(v){return Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;}
function sorted(records){return [...records].sort((a,b)=>a.raw.recordId.localeCompare(b.raw.recordId));}
export async function startLogService({host='127.0.0.1',port=0,profile='visible'}={}){
 let scenario='incident',generation=0,data,stored=[],accepted=[],retries=0;
 function reset(id='incident'){scenario=id;generation++;data=generate(profile,id);stored=[];accepted=[];retries=0;}
 function snapshot(){return {scenario,generation,label:scenarios.find(s=>s.id===scenario).label,note:scenarios.find(s=>s.id===scenario).note,receivers:data.receivers,batches:data.batches,stored,accepted,retries};}
 function audit(){const actual=sorted(stored),expected=sorted(data.expected);return {profile,snapshot:snapshot(),events:data.events,actual,expected,actualSignature:JSON.stringify(canonical(actual)),expectedSignature:JSON.stringify(canonical(expected))};}
 reset();
 const server=createServer(async(req,res)=>{
  try{
   let body='';for await(const chunk of req)body+=chunk;const input=body?JSON.parse(body):{};const path=new URL(req.url,'http://local').pathname;let answer;
   if(path==='/health')answer={ok:true};
   else if(path==='/catalog')answer={scenarios};
   else if(path==='/snapshot')answer=snapshot();
   else if(path==='/scenario'){if(!scenarios.some(s=>s.id===input.id))throw Error('scenario');reset(input.id);answer=snapshot();}
   else if(path==='/ingest'){
    if(input.generation!==generation)throw Error('stale delivery generation');
    if(!Array.isArray(input.records)||!Array.isArray(input.accepted))throw Error('invalid batch');
    stored=clone(input.records);accepted=clone(input.accepted);answer=snapshot();
   }else if(path==='/replay'){retries++;answer=data.batches.at(-1);}
   else if(path==='/restart'||path==='/reset'){reset();answer=snapshot();}
   else if(path==='/audit')answer=audit();
   else{res.writeHead(404);res.end('{}');return;}
   res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(answer));
  }catch(error){res.writeHead(400,{'content-type':'application/json'});res.end(JSON.stringify({error:String(error)}));}
 });
 await new Promise(r=>server.listen(Number(port),host,r));return {server,address:server.address()};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const options={};for(let i=2;i<process.argv.length;i++)if(process.argv[i].startsWith('--'))options[process.argv[i].slice(2)]=process.argv[++i];startLogService(options).then(({address})=>console.log('log receiver '+address.port));}
