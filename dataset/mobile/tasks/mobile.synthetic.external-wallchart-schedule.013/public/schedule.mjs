// Ordinary product constraint engine. Nothing here decodes a drawing or knows its contents.
export function normalize(input, record) {
  if (!Array.isArray(input) || !input.length) throw Error('The schedule integration has no jobs.');
  const meta=new Map(record.jobs.map(j=>[j.id,j]));
  const jobs=input.map(j=>({id:j.id,name:j.name||meta.get(j.id)?.name||j.id,crew:j.crew||meta.get(j.id)?.crew||'Yard',start:Number(j.start),duration:Number(j.duration??(j.end-j.start)),links:(j.links||[]).map(l=>({...l,lag:Number(l.lag)}))}));
  for (const j of input) for (const l of j.successors||[]) {
    const target=jobs.find(k=>k.id===l.to);if(!target)throw Error('A link refers to a missing job.');
    target.links.push({from:j.id,type:l.type,lag:Number(l.lag)});
  }
  return jobs;
}
export function compute(jobs, firstDay=0, slip={job:'',days:0}) {
  const map=new Map(jobs.map(j=>[j.id,j]));
  if(map.size!==jobs.length||!jobs.length)throw Error('Jobs need unique names and a complete schedule.');
  for (const j of jobs) {
    if(!j.id||!Number.isInteger(j.start)||!Number.isInteger(j.duration)||j.duration<1)throw Error('Enter whole-day starts and positive whole-day durations.');
    const keys=new Set();
    for(const l of j.links){
      if(!map.has(l.from)||!['FS','SS','FF'].includes(l.type)||!Number.isInteger(l.lag)||l.lag<0)throw Error('A dependency is incomplete. Choose a job, link type and nonnegative whole-day lag.');
      const k=l.from+'|'+l.type;if(keys.has(k))throw Error('Remove the duplicate dependency.');keys.add(k);
    }
  }
  if(!Number.isInteger(slip.days)||slip.days<0)throw Error('Slip days must be a nonnegative whole number.');
  const visiting=new Set(),done=new Set(),order=[];
  function visit(id){if(visiting.has(id))throw Error('Dependency cycle: remove a link to make the schedule possible.');if(done.has(id))return;visiting.add(id);for(const l of map.get(id).links)visit(l.from);visiting.delete(id);done.add(id);order.push(id);}
  jobs.forEach(j=>visit(j.id));
  const weight=(l,to)=>l.type==='SS'?l.lag:map.get(l.from).duration+l.lag-(l.type==='FF'?to.duration:0);
  function earliest(hold){const e={};for(const id of order){const j=map.get(id);e[id]=Math.max(firstDay,hold?.id===id?hold.min:firstDay,...j.links.map(l=>e[l.from]+weight(l,j)));}return e;}
  const early=earliest(),finish=Math.max(...jobs.map(j=>early[j.id]+j.duration));
  const late=Object.fromEntries(jobs.map(j=>[j.id,finish-j.duration]));
  for(const id of [...order].reverse()){const j=map.get(id);for(const l of j.links)late[l.from]=Math.min(late[l.from],late[id]-weight(l,j));}
  const floats=Object.fromEntries(jobs.map(j=>[j.id,late[j.id]-early[j.id]]));
  const critical=jobs.filter(j=>floats[j.id]===0).map(j=>j.id);
  const tight=jobs.flatMap(j=>j.links.filter(l=>!floats[l.from]&&!floats[j.id]&&early[j.id]===early[l.from]+weight(l,j)).map(l=>[l.from,j.id]));
  const paths=[];function walk(id,path){const next=tight.filter(e=>e[0]===id).map(e=>e[1]);if(!next.length)paths.push([...path,id]);else next.forEach(n=>walk(n,[...path,id]));}
  critical.filter(id=>!tight.some(e=>e[1]===id)).forEach(id=>walk(id,[]));
  const violations=jobs.filter(j=>j.start<Math.max(firstDay,...j.links.map(l=>map.get(l.from).start+weight(l,j)))).map(j=>j.id);
  const moved=slip.job&&map.has(slip.job)?earliest({id:slip.job,min:early[slip.job]+slip.days}):early;
  const slippedFinish=Math.max(...jobs.map(j=>moved[j.id]+j.duration));
  return {early,late,floats,finish,critical,paths,violations,slippedFinish,delta:slippedFinish-finish};
}
