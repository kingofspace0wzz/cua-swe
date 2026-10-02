import {createHash} from 'node:crypto';
export function expand(template,labels,value){return String(template).replace(/{{\s*\$value\s*}}/g,String(value)).replace(/{{\s*\$labels\.(\w+)\s*}}/g,(_,k)=>labels[k]??'');}
export function fingerprint(labels){return createHash('sha256').update(JSON.stringify(Object.fromEntries(Object.entries(labels).sort(([a],[b])=>a.localeCompare(b))))).digest('hex').slice(0,10);}
export function evaluate(profile,scenario,rule,cursor){
 let active=new Map();const history=Object.fromEntries(scenario.targets.map(t=>[t.id,[]]));let generation=1;
 for(let i=0;i<=cursor;i++){
  const time=i*profile.interval;
  if(scenario.restartAt===i){active=new Map();generation++;}
  const seen=new Set();
  for(const target of scenario.targets){
   const value=target.values[i];const condition=value!==null && rule.query.metric==='work_pressure' && (rule.query.operator==='>'?value>rule.query.threshold:rule.query.operator==='>='?value>=rule.query.threshold:false);
   const labels={...target.labels,alertname:rule.name};for(const [k,v] of Object.entries(rule.labels||{}))labels[k]=expand(v,target.labels,value);
   const annotations=Object.fromEntries(Object.entries(rule.annotations||{}).map(([k,v])=>[k,expand(v,target.labels,value)]));
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
