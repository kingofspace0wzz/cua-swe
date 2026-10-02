import {createHash} from 'node:crypto';
export function generationAt(scenario,index){
 const restart=scenario?scenario.restartAt:null;
 return restart!==null&&restart!==undefined&&index>=restart?2:1;
}
export function routeContext(profile,scenario,index){
 const epoch=(profile.routing||{}).epoch||{};
 const context={};
 for(const [scope,spec] of Object.entries(epoch)){
  const pairs=(spec||{}).pairs||[];
  if(!pairs.length){context[scope]={};continue;}
  const at=(spec||{}).mode==='evaluation'?Math.min(index,pairs.length-1):Math.min(generationAt(scenario,index)-1,pairs.length-1);
  context[scope]={...pairs[at]};
 }
 return context;
}
export function resolveRoutes(profile,scenario,index){
 const context=routeContext(profile,scenario,index);
 return (profile.receivers||[]).map(receiver=>({name:receiver.name,family:receiver.family,match:receiver.matchScope?{...(context[receiver.matchScope]||{})}:{...(receiver.match||{})}}));
}
export function expand(template,labels,value,route){return String(template).replace(/{{\s*\$value\s*}}/g,String(value)).replace(/{{\s*\$labels\.(\w+)\s*}}/g,(_,k)=>labels[k]??'').replace(/{{\s*\$route\.(\w+)\s*}}/g,(_,k)=>route[k]??'');}
export function fingerprint(labels){return createHash('sha256').update(JSON.stringify(Object.fromEntries(Object.entries(labels).sort(([a],[b])=>a.localeCompare(b))))).digest('hex').slice(0,10);}
export function evaluate(profile,scenario,rule,cursor){
 let active=new Map();const history=Object.fromEntries(scenario.targets.map(t=>[t.id,[]]));let generation=1;
 for(let i=0;i<=cursor;i++){
  const time=i*profile.interval;
  const context=routeContext(profile,scenario,i);const route=Object.assign({},...Object.values(context));
  if(scenario.restartAt===i){active=new Map();generation++;}
  const seen=new Set();
  for(const target of scenario.targets){
   const value=target.values[i];const condition=value!==null && rule.query.metric==='work_pressure' && (rule.query.operator==='>'?value>rule.query.threshold:rule.query.operator==='>='?value>=rule.query.threshold:false);
   const labels={...target.labels,alertname:rule.name};for(const [k,v] of Object.entries(rule.labels||{}))labels[k]=expand(v,target.labels,value,route);
   const annotations=Object.fromEntries(Object.entries(rule.annotations||{}).map(([k,v])=>[k,expand(v,target.labels,value,route)]));
   const fp=condition?fingerprint(labels):null;let state='inactive',activeAt=null;
   if(condition){
    if(seen.has(fp))throw new Error('duplicate alert labelset');seen.add(fp);
    const prior=active.get(fp)||{activeAt:time};active.set(fp,{...prior,annotations,value});activeAt=prior.activeAt;state=time-activeAt>=rule.forSeconds?'firing':'pending';
   }
   history[target.id].push({t:time,value,condition,state,activeAt,fingerprint:fp,labels:condition?labels:{},annotations:condition?annotations:{}});
  }
  for(const fp of active.keys())if(!seen.has(fp))active.delete(fp);
 }
 return {history,generation};
}
