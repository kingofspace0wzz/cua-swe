import {createServer} from 'node:http';import {randomBytes} from 'node:crypto';import {readFileSync} from 'node:fs';
let port=56511,host='127.0.0.1',profile='visible';for(let i=2;i<process.argv.length;i++){if(process.argv[i]==='--port')port=Number(process.argv[++i]);else if(process.argv[i]==='--host')host=process.argv[++i];else if(process.argv[i]==='--profile')profile=process.argv[++i];}
const profiles=JSON.parse(readFileSync(new URL('./profiles.json',import.meta.url)));const p=profiles[profile];if(!p)throw new Error('unknown profile');
const activationBoard=readFileSync(new URL('./policy-activation-board.png',import.meta.url));
const deadlineMatrix=readFileSync(new URL('./deadline-authority-matrix.png',import.meta.url));
// Deterministic per-rollout target set. The profile fixes each exporter's
// collection tier and receiver class; the receiver team's policy activation
// schedule owns which policy revision is active per activation epoch, and the
// deadline authority matrix owns freshness/abort/approved-cap envelopes per
// policy revision, tier AND receiver class. Every reset advances the rollout
// to its next scheduled activation epoch; the rotating exporters' pacing plans
// are owned per epoch while the fixed controls keep their standard pacing.
let epochIndex=0;
const epoch=()=>p.epochs[epochIndex%p.epochs.length];
const windowsFor=(revision)=>p.revisions[revision];
const activeWindows=()=>windowsFor(epoch().revision);
function definitions(){
 const e=epoch();const a=p.assignments;
 return [
  {key:'affected',label:'Inventory exporter',plan:e.plans.affected,tier:a.affected.tier,klass:a.affected.class,supported:!e.plans.affected.stall},
  {key:'healthy',label:'Healthy exporter',plan:{headerMs:30,endMs:60},tier:a.healthy.tier,klass:a.healthy.class,supported:true},
  {key:'slowbody',label:'Body completion control',plan:e.plans.slowbody,tier:a.slowbody.tier,klass:a.slowbody.class,supported:!e.plans.slowbody.stall},
  {key:'archive',label:'Ledger archive exporter',plan:e.plans.archive,tier:a.archive.tier,klass:a.archive.class,supported:!e.plans.archive.stall},
  {key:'catalog',label:'Catalog exporter',plan:e.plans.catalog,tier:a.catalog.tier,klass:a.catalog.class,supported:!e.plans.catalog.stall},
  {key:'stalled',label:'Stalled headers control',plan:{headerMs:3500,endMs:3560},tier:a.stalled.tier,klass:a.stalled.class,supported:false},
  {key:'trickle',label:'Trickle body control',plan:{headerMs:30,trickle:true},tier:a.trickle.tier,klass:a.trickle.class,supported:false},
  {key:'truncated',label:'Truncated body control',plan:{headerMs:30,truncate:true,endMs:60},tier:a.truncated.tier,klass:a.truncated.class,supported:false}
 ];
}
// Protected audit-only reference rows for the current activation epoch. Their
// operator representation is the evaluator-owned PNG pair, never the
// structured public snapshot.
function referenceRows(){
 const w=activeWindows();
 return definitions().map(d=>{
  const cell=w[d.tier][d.klass];
  if(d.plan.truncate)return {key:d.key,tier:d.tier,receiverClass:d.klass,epoch:epoch().code,revision:epoch().revision,kind:'rejected',ms:62};
  if(d.supported)return {key:d.key,tier:d.tier,receiverClass:d.klass,epoch:epoch().code,revision:epoch().revision,kind:'ingested',ms:d.plan.endMs+12};
  return {key:d.key,tier:d.tier,receiverClass:d.klass,epoch:epoch().code,revision:epoch().revision,kind:'canceled',ms:cell.cancelMs-96};
 });
}
function statusText(kind,ms){return kind==='ingested'?'Ingested \u00b7 sample age '+ms+' ms':kind==='canceled'?'Canceled +'+ms+' ms \u00b7 incomplete':'Rejected \u00b7 truncated body';}
const auditToken=process.env.SCRAPE_AUDIT_TOKEN||randomBytes(32).toString('hex');
let episode=0,current=[],history=[],running=false;const records=new Map();
function clone(x){return JSON.parse(JSON.stringify(x));}
function event(t,kind,detail){t.events.push({kind,elapsedMs:Math.max(0,performance.now()-(t.started||performance.now())),...(detail?{detail}:{} )});}
function templates(){return definitions().map(d=>({...d,receivedSamples:[],events:[],started:null,accepted:false,closed:false}));}current=templates();
function historyRow(t){return {round:'episode '+t.episode,label:t.label,tier:t.tier,receiverClass:t.klass,policyEpoch:t.policyEpoch,status:t.accepted?statusText('ingested',Math.round(t.receiptAgeMs)):t.responseFinished?'Rejected \u00b7 complete but not accepted':statusText('canceled',Math.round(t.closedMs||0))};}
function publicTarget(t){return {key:t.key,label:t.label,tier:t.tier,receiverClass:t.klass,started:!!t.started,accepted:t.accepted,closed:t.closed,receivedSamples:t.receivedSamples,receiptAgeMs:t.receiptAgeMs,events:t.events,requestCount:t.requestCount};}
function snapshot(){return {episode,running,profileCode:p.profileCode,epochCode:epoch().code,targets:current.map(publicTarget),history:history.map(historyRow)};}
function send(r,status,obj){r.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});r.end(JSON.stringify(obj));}
function sendPng(r,image){r.writeHead(200,{'content-type':'image/png','content-length':image.length,'cache-control':'no-store'});r.end(image);}
function canonical(samples){return JSON.stringify(samples.map(s=>({name:s.name,labels:Object.fromEntries(Object.entries(s.labels||{}).sort()),value:s.value})).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));}
async function read(q){let text='';for await(const c of q){text+=c;if(text.length>100000)throw new Error('body too large');}return text?JSON.parse(text):{};}
createServer(async(q,r)=>{try{const u=new URL(q.url,'http://exporter.invalid');
 if(u.pathname==='/health')return send(r,200,{ok:true});
 if(u.pathname==='/activation-board.png')return sendPng(r,activationBoard);
 if(u.pathname==='/deadline-matrix.png')return sendPng(r,deadlineMatrix);
 if(u.pathname==='/snapshot')return send(r,200,snapshot());
 if(u.pathname==='/audit'){if(q.headers.authorization!=='Bearer '+auditToken)return send(r,403,{error:'admin authentication required'});return send(r,200,{profile,profileCode:p.profileCode,episode,running,epochIndex:epochIndex%p.epochs.length,epochCode:epoch().code,activeRevision:epoch().revision,board:p.epochs.map(e=>({code:e.code,revision:e.revision})),supersededBoard:p.supersededEpochs,revisions:p.revisions,supersededRevisions:p.supersededRevisions,assignments:p.assignments,reference:referenceRows(),current,history});}
 if(u.pathname==='/reset'&&q.method==='POST'){if(running)return send(r,409,{error:'active requests'});history.push(...current.filter(t=>t.id));episode=0;epochIndex=(epochIndex+1)%p.epochs.length;current=templates();return send(r,200,snapshot());}
 if(u.pathname==='/begin'&&q.method==='POST'){
  if(running)return send(r,409,{error:'active requests'});history.push(...current.filter(t=>t.id));episode++;current=templates();
  const w=activeWindows();
  for(const [i,t] of current.entries()){
   t.id=profile+'-'+Date.now()+'-'+episode+'-'+t.key;t.path='/metrics/'+t.id;t.episode=episode;t.policyEpoch=epoch().code;t.win=w[t.tier][t.klass];
   t.expected=[{name:'staging_queue_depth',labels:{exporter:t.key,zone:'staging-'+p.seed},value:p.seed+episode+i},{name:'staging_completed_total',labels:{exporter:t.key,zone:'staging-'+p.seed},value:1000+p.seed+episode*3+i}];
   t.body=t.expected.map(s=>s.name+'{exporter="'+s.labels.exporter+'",zone="'+s.labels.zone+'"} '+s.value+'\n').join('');records.set(t.id,t);
  }running=true;setTimeout(()=>{running=false;},4000);return send(r,200,{targets:current.map(t=>({id:t.id,key:t.key,path:t.path,tier:t.tier,receiverClass:t.klass,profileCode:p.profileCode,policyEpoch:t.policyEpoch}))});
 }
 if(u.pathname.startsWith('/metrics/')){
  const t=records.get(u.pathname.slice(9));if(!t)return send(r,404,{error:'unknown request'});
  t.started??=performance.now();t.requestCount=(t.requestCount||0)+1;t.closed=false;
  const wire={started:performance.now(),closed:false,complete:false};t.requests??=[];t.requests.push(wire);event(t,'request_received');
  r.on('close',()=>{wire.closed=true;wire.closedMs=performance.now()-t.started;wire.complete=r.writableFinished;t.closed=t.requests.every(x=>x.closed);t.closedMs=Math.max(t.closedMs||0,wire.closedMs);t.responseFinished=!!t.responseFinished||wire.complete;if(wire.complete){t.completedRequestSamples??=[];t.completedRequestSamples.push({sampledAt:wire.started,completedAt:performance.now()});}event(t,'peer_closed',r.writableFinished?'after complete write':'before complete body');});
  const plan=t.plan;
  setTimeout(()=>{
   event(t,'payload_ready');t.producedCount=(t.producedCount||0)+t.expected.length;
   if(r.destroyed){t.productionDone=true;return;}
   r.writeHead(200,{'content-type':'text/plain; version=0.0.4','content-length':Buffer.byteLength(t.body)+(plan.truncate?20:0),'connection':'close'});r.flushHeaders();event(t,'headers_sent');
   if(plan.trickle){
    let offset=0;const timer=setInterval(()=>{if(r.destroyed){clearInterval(timer);t.productionDone=true;return;}r.write(t.body.slice(offset,++offset));if(offset>=34){clearInterval(timer);r.end(t.body.slice(offset));t.productionDone=true;event(t,'body_finished');}},100);return;
   }
   if(plan.truncate){
    setTimeout(()=>{t.productionDone=true;if(r.destroyed)return;r.write(t.body.slice(0,20));r.destroy();},plan.endMs-plan.headerMs);return;
   }
   let written=0;
   for(const [at,fraction] of plan.chunks||[]){
    const upto=Math.max(1,Math.floor(t.body.length*fraction));
    setTimeout(()=>{if(r.destroyed)return;r.write(t.body.slice(written,upto));written=upto;event(t,'body_write','paced chunk');},Math.max(1,at-plan.headerMs));
   }
   setTimeout(()=>{
    t.productionDone=true;if(r.destroyed)return;
    r.end(t.body.slice(written),()=>{event(t,'body_finished');});
   },Math.max(2,plan.endMs-plan.headerMs));
  },plan.headerMs);return;
 }
 if(u.pathname==='/ingest'&&q.method==='POST'){
  const x=await read(q);const t=records.get(x.id);if(!t)return send(r,404,{error:'unknown attempt'});
  const age=performance.now()-t.started;t.receiptAttempts=(t.receiptAttempts||0)+1;const w=t.win;
  const recentComplete=(t.completedRequestSamples||[]).some(v=>performance.now()-v.sampledAt<=w.freshMs+30);
  const valid=t.supported&&t.started&&t.responseFinished&&recentComplete&&age<=w.freshMs+30&&Array.isArray(x.samples)&&canonical(x.samples)===canonical(t.expected)&&!t.accepted;
  if(valid){t.accepted=true;t.receivedSamples=clone(x.samples);t.receiptAgeMs=age;event(t,'receiver_accepted');return send(r,200,{accepted:true});}
  event(t,'receiver_rejected');return send(r,422,{error:'incomplete, stale or invalid payload'});
 }
 send(r,404,{error:'not found'});
 }catch(e){send(r,500,{error:e.message});}
}).listen(port,host);
