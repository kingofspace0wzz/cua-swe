import http from "node:http";
import {readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";
import {materialize,decide} from "./sampler_engine.mjs";
const profiles=JSON.parse(readFileSync(new URL("./profiles.json",import.meta.url)));
const RUNBOOK_ID=profiles.runbook.id,FIRMWARE_BUILD=profiles.runbook.firmwareBuild;
const RUNBOOK_PNG=readFileSync(new URL("./runbook_rb217.png",import.meta.url));
export function startSamplerService(options={}) {
  let profileName=options.profile||"visible",scenarioId="delayed",plan=null;
  const planHistory=[];
  let selectedId=null,bucketFilter="all",decisionFilter="all",probeResult=null,probeTrace=null,replayCount=0;
  function deployed(){return plan||{policies:[],decisionWaitMs:0};}
  function requirePlan(){if(!plan)throw Error("collector_unconfigured");}
  function deliveries(){const rows=[];for(const [window,specs] of Object.entries(profiles[profileName].scenarios))for(const spec of specs)rows.push({traceId:spec.id,window,service:spec.service,firstSpanAtMs:10000+spec.offset,lastSpanAtMs:10000+spec.offset+spec.lagMs});const staged=profiles[profileName].replay;rows.push({traceId:staged.id,window:"replay",service:staged.service,firstSpanAtMs:10000+staged.offset,lastSpanAtMs:10000+staged.offset+staged.lagMs});return rows;}
  function traces(){const a=profiles[profileName].scenarios[scenarioId].map(s=>({...materialize(s),pipeline:"live"}));if(replayCount)a.push({...materialize(profiles[profileName].replay),pipeline:"replay"});return a;}
  function snapshot(){
    const active=deployed();
    const all=traces().map(t=>decide(t,active,t.pipeline));
    const visible=all.filter(x=>(bucketFilter==="all"||x.bucket===bucketFilter)&&(decisionFilter==="all"||(decisionFilter==="sampled")===x.sampled));
    return {profileName,scenarioId,metrics:{spansReceived:all.reduce((n,x)=>n+x.spanCount,0),tracesCompleted:all.length,sampled:all.filter(x=>x.sampled).length,dropped:all.filter(x=>!x.sampled).length},buckets:["error","slow","ordinary"].map(id=>({id,label:id[0].toUpperCase()+id.slice(1),received:all.filter(x=>x.bucket===id).length,sampled:all.filter(x=>x.bucket===id&&x.sampled).length})),decisions:visible,selected:all.find(x=>x.id===selectedId)||all[0]||null,timeline:all.map(({id,service,firstArrivalMs,completedAtMs,decisionAtMs})=>({traceId:id,service,firstArrivalMs,completedAtMs,decisionAtMs})),exports:all.filter(x=>x.sampled).map(({id,service,reasons,spanCount})=>({id,service,reasons,spanCount})),filter:{bucket:bucketFilter,decision:decisionFilter},diagnostics:{sloRule:`delivery profile ${profiles[profileName].firmware.profileCode} on firmware ${FIRMWARE_BUILD} — decision envelope and margin per receiver operations runbook ${RUNBOOK_ID}`,firmwareBuild:FIRMWARE_BUILD,profileCode:profiles[profileName].firmware.profileCode,runbookId:RUNBOOK_ID,waitMs:active.decisionWaitMs||0,policyCount:active.policies?.length||0,probabilityPercentage:active.policies?.find(p=>p.type==="probabilistic")?.percentage||0},probeResult,replayCount,canReplay:replayCount===0};
  }
  const routes={
    health:()=>({ok:true}),
    catalog:()=>({scenarios:[{id:"delayed",label:"Live incident"},{id:"early",label:"Early arrivals"},{id:"interleaved",label:"Interleaved traffic"}],probes:profiles.probes.map(({id,label})=>({id,label})),receiver:{deliveries:deliveries(),firmware:{build:FIRMWARE_BUILD,profileCode:profiles[profileName].firmware.profileCode},runbook:{id:RUNBOOK_ID}}}),
    configure:value=>{plan=value;planHistory.push(JSON.stringify(value));return snapshot();},
    scenario:value=>{requirePlan();if(!profiles[profileName].scenarios[value.scenarioId])throw Error("unknown window");scenarioId=value.scenarioId;selectedId=null;bucketFilter="all";decisionFilter="all";probeResult=null;probeTrace=null;replayCount=0;return snapshot();},
    snapshot:()=>{requirePlan();return snapshot();},
    select:value=>{requirePlan();selectedId=value.traceId;return snapshot();},
    bucket:value=>{requirePlan();bucketFilter=value.bucket;return snapshot();},
    decision:value=>{requirePlan();decisionFilter=value.decision;return snapshot();},
    probe:value=>{requirePlan();const spec=profiles.probes.find(p=>p.id===value.probeId);if(!spec)throw Error("unknown probe");probeTrace=materialize(spec.trace);probeResult=decide(probeTrace,deployed(),"probe");return snapshot();},
    replay:()=>{requirePlan();replayCount=1;selectedId=profiles[profileName].replay.id;return snapshot();},
    audit:()=>({profileName,scenarioId,configured:Boolean(plan),planHistory:[...planHistory],actual:snapshot(),received:traces(),probeTrace,contract:{runbookId:RUNBOOK_ID}}),
    reset:value=>{profileName=value.profileName||options.profile||"visible";scenarioId="delayed";selectedId=null;bucketFilter="all";decisionFilter="all";probeResult=null;probeTrace=null;replayCount=0;plan=null;return {ok:true};},
  };
  const server=http.createServer(async(req,res)=>{const action=new URL(req.url,"http://local").pathname.split("/").filter(Boolean).at(-1);if(action==="runbook"){res.writeHead(200,{"content-type":"image/png","content-length":RUNBOOK_PNG.length});res.end(RUNBOOK_PNG);return;}if(!routes[action]){res.writeHead(404);res.end("not found");return;}try{const chunks=[];for await(const c of req)chunks.push(c);const value=chunks.length?JSON.parse(Buffer.concat(chunks).toString()):{};const result=routes[action](value);res.writeHead(200,{"content-type":"application/json"});res.end(JSON.stringify(result));}catch(e){res.writeHead(400,{"content-type":"application/json"});res.end(JSON.stringify({error:e.message}));}});
  return new Promise(resolve=>server.listen(options.port||0,options.host||"127.0.0.1",()=>resolve({server,address:server.address()})));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const o={};for(let i=2;i<process.argv.length;i++){if(process.argv[i]==="--port")o.port=Number(process.argv[++i]);else if(process.argv[i]==="--host")o.host=process.argv[++i];else if(process.argv[i]==="--profile")o.profile=process.argv[++i];}startSamplerService(o);}
