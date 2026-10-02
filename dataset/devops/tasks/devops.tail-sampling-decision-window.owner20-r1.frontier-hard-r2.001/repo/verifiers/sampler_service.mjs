import http from "node:http";
import {readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";
import {materialize,decide} from "./sampler_engine.mjs";
import {renderLevelsPanel} from "./levels_panel.mjs";
const profiles=JSON.parse(readFileSync(new URL("./profiles.json",import.meta.url)));
const panels=new Map();
function panelFor(profileName){if(!panels.has(profileName))panels.set(profileName,renderLevelsPanel(profiles[profileName].policy));return panels.get(profileName);}
export function startSamplerService(options={}) {
  let profileName=options.profile||"visible",scenarioId="delayed",plan={policies:[],decisionWaitMs:0};
  let selectedId=null,bucketFilter="all",decisionFilter="all",probeResult=null,probeTrace=null,replayCount=0;
  function traces(){const a=profiles[profileName].scenarios[scenarioId].map(s=>({...materialize(s),pipeline:"live"}));if(replayCount)a.push({...materialize(profiles[profileName].replay),pipeline:"replay"});return a;}
  function snapshot(){
    const all=traces().map(t=>decide(t,plan,t.pipeline));
    const visible=all.filter(x=>(bucketFilter==="all"||x.bucket===bucketFilter)&&(decisionFilter==="all"||(decisionFilter==="sampled")===x.sampled));
    return {profileName,scenarioId,metrics:{spansReceived:all.reduce((n,x)=>n+x.spanCount,0),tracesCompleted:all.length,sampled:all.filter(x=>x.sampled).length,dropped:all.filter(x=>!x.sampled).length},buckets:["error","slow","ordinary"].map(id=>({id,label:id[0].toUpperCase()+id.slice(1),received:all.filter(x=>x.bucket===id).length,sampled:all.filter(x=>x.bucket===id&&x.sampled).length})),decisions:visible,selected:all.find(x=>x.id===selectedId)||all[0]||null,timeline:all.map(({id,service,firstArrivalMs,completedAtMs,decisionAtMs})=>({traceId:id,service,firstArrivalMs,completedAtMs,decisionAtMs})),exports:all.filter(x=>x.sampled).map(({id,service,reasons,spanCount})=>({id,service,reasons,spanCount})),filter:{bucket:bucketFilter,decision:decisionFilter},diagnostics:{waitMs:plan.decisionWaitMs||0,policyCount:plan.policies?.length||0,probabilityPercentage:plan.policies?.find(p=>p.type==="probabilistic")?.percentage||0},probeResult,replayCount,canReplay:replayCount===0};
  }
  const routes={
    health:()=>({ok:true}),
    catalog:()=>({scenarios:[{id:"delayed",label:"Live incident"},{id:"early",label:"Early arrivals"},{id:"interleaved",label:"Interleaved traffic"}],probes:profiles[profileName].probes.map(({id,label})=>({id,label}))}),
    configure:value=>{plan=value;return snapshot();},
    scenario:value=>{if(!profiles[profileName].scenarios[value.scenarioId])throw Error("unknown window");scenarioId=value.scenarioId;selectedId=null;bucketFilter="all";decisionFilter="all";probeResult=null;probeTrace=null;replayCount=0;return snapshot();},
    snapshot:()=>snapshot(),
    select:value=>{selectedId=value.traceId;return snapshot();},
    bucket:value=>{bucketFilter=value.bucket;return snapshot();},
    decision:value=>{decisionFilter=value.decision;return snapshot();},
    probe:value=>{const spec=profiles[profileName].probes.find(p=>p.id===value.probeId);if(!spec)throw Error("unknown probe");probeTrace=materialize(spec.trace);probeResult=decide(probeTrace,plan,"probe");return snapshot();},
    replay:()=>{replayCount=1;selectedId=profiles[profileName].replay.id;return snapshot();},
    audit:()=>({profileName,scenarioId,actual:snapshot(),received:traces(),probeTrace}),
    reset:value=>{profileName=value.profileName||options.profile||"visible";scenarioId="delayed";selectedId=null;bucketFilter="all";decisionFilter="all";probeResult=null;probeTrace=null;replayCount=0;plan={policies:[],decisionWaitMs:0};return {ok:true};},
  };
  const server=http.createServer(async(req,res)=>{const action=new URL(req.url,"http://local").pathname.split("/").filter(Boolean).at(-1);if(action==="service-levels"){res.writeHead(200,{"content-type":"image/png","cache-control":"no-store"});res.end(panelFor(profileName));return;}if(!routes[action]){res.writeHead(404);res.end("not found");return;}try{const chunks=[];for await(const c of req)chunks.push(c);const value=chunks.length?JSON.parse(Buffer.concat(chunks).toString()):{};const result=routes[action](value);res.writeHead(200,{"content-type":"application/json"});res.end(JSON.stringify(result));}catch(e){res.writeHead(400,{"content-type":"application/json"});res.end(JSON.stringify({error:e.message}));}});
  return new Promise(resolve=>server.listen(options.port||0,options.host||"127.0.0.1",()=>resolve({server,address:server.address()})));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const o={};for(let i=2;i<process.argv.length;i++){if(process.argv[i]==="--port")o.port=Number(process.argv[++i]);else if(process.argv[i]==="--host")o.host=process.argv[++i];else if(process.argv[i]==="--profile")o.profile=process.argv[++i];}startSamplerService(o);}
