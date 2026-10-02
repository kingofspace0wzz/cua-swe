import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {evaluate,routeContext,resolveRoutes} from './engine.mjs';
const profiles=JSON.parse(readFileSync(new URL('./profiles.json',import.meta.url)));
const runbookSheet=readFileSync(new URL('./runbook.png',import.meta.url));
export function startService(options={}){
 const profile=structuredClone(profiles[options.profile||'visible']);
 let scenario=profile.scenarios[0],target=scenario.targets[0],cursor=profile.initialCursor,compiled=null,actions=[];
 function routingCatalog(){
  const epoch={};
  for(const [scope,spec] of Object.entries((profile.routing||{}).epoch||{}))epoch[scope]={keys:Object.keys(((spec||{}).pairs||[])[0]||{}).sort(),policy:(spec||{}).policy||null};
  return {epoch};
 }
 function snapshot(){
  if(!compiled)return {unconfigured:true};
  const rule=compiled[0],result=evaluate(profile,scenario,rule,cursor),history=result.history[target.id];
  const firingAlerts=Object.values(result.history).map(h=>h.at(-1)).filter(a=>a.state==='firing');
  const firing=firingAlerts.length;
  const routes=resolveRoutes(profile,scenario,cursor).map(route=>({...route,delivered:0}));
  let unrouted=0;
  for(const alert of firingAlerts){
   const hit=routes.find(route=>Object.entries(route.match).every(([k,v])=>alert.labels[k]===v));
   if(hit)hit.delivered++;else unrouted++;
  }
  const primary=routes.find(route=>route.family===profile.rules[0].family)||routes[0];
  return {scenario:scenario.id,target:{id:target.id,...target.labels},targets:scenario.targets.map(x=>({id:x.id,...x.labels})),time:cursor*profile.interval,interval:profile.interval,rule:{...rule,revision:profile.rules[0].revision},generation:result.generation,gaps:target.values.slice(0,cursor+1).filter(v=>v===null).length,series:history.slice(-7).map(x=>({t:x.t,value:x.value})),timeline:history.slice(-7),routes,delivery:{receiver:primary.name,match:{...primary.match},epoch:routeContext(profile,scenario,cursor),transport:'ready',firing,delivered:primary.delivered,unrouted}};
 }
 const server=createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://local.invalid');let body={};if(req.method==='POST'){const chunks=[];for await(const part of req)chunks.push(part);body=JSON.parse(Buffer.concat(chunks).toString()||'{}');}
   if(url.pathname==='/runbook'){res.writeHead(200,{'content-type':'image/png','cache-control':'no-store','content-length':runbookSheet.length});res.end(runbookSheet);return;}
   let result;
   if(url.pathname==='/health')result={ok:true};
   else if(url.pathname==='/catalog')result={rules:profile.rules,scenarios:profile.scenarios.map(s=>({id:s.id,label:s.label})),routing:routingCatalog()};
   else if(url.pathname==='/configure'){compiled=body.rules;result=snapshot();}
   else if(url.pathname==='/snapshot')result=snapshot();
   else if(url.pathname==='/audit')result={snapshot:snapshot(),history:compiled?evaluate(profile,scenario,compiled[0],cursor).history:{},profile:options.profile||'visible',scenario:scenario.id,target:target.id,cursor,compiled,actions};
   else if(url.pathname==='/scenario'){scenario=profile.scenarios.find(s=>s.id===body.id)||scenario;target=scenario.targets[0];cursor=profile.initialCursor;actions.push('scenario');result=snapshot();}
   else if(url.pathname==='/target'){target=scenario.targets.find(t=>t.id===body.id)||target;actions.push('target');result=snapshot();}
   else if(url.pathname==='/advance'){cursor=Math.min(cursor+1,target.values.length-1);actions.push('advance');result=snapshot();}
   else if(url.pathname==='/replay'){cursor=profile.initialCursor;actions.push('replay');result=snapshot();}
   else if(url.pathname==='/reset'){scenario=profile.scenarios[0];target=scenario.targets[0];cursor=profile.initialCursor;actions.push('reset');result=snapshot();}
   else{res.writeHead(404);res.end('not found');return;}
   res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(result));
  }catch(e){res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:String(e.message)}));}
 });
 return new Promise(resolve=>server.listen(options.port||0,options.host||'127.0.0.1',()=>resolve({server,address:server.address()})));
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 const options={};for(let i=2;i<process.argv.length;i++){if(process.argv[i]==='--port')options.port=Number(process.argv[++i]);else if(process.argv[i]==='--host')options.host=process.argv[++i];else if(process.argv[i]==='--profile')options.profile=process.argv[++i];}
 startService(options);
}
