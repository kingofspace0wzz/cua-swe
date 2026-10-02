// Complete finite legacy engine: cells, seconds and velocity material factors.
// Compile the full rail itinerary once; evaluate absolute time without state drift.
export function itinerary(record, plan) {
  const nodes = new Map(plan.nodes.map(n => [n.id,n]));
  const events = new Map(plan.events.map(e => [e.node,e]));
  const factors = new Map(plan.materials.map(m => [m.id,m.factor]));
  const pieces=[]; let clock=0, contacts=0, material=plan.material;
  const first=nodes.get(record.route[0]);
  if(plan.release>0) pieces.push({start:0,end:plan.release,a:first,b:first,speed:0,phase:'Waiting',material,contacts});
  clock=plan.release;
  for(let i=1;i<record.route.length;i++) {
    const a=nodes.get(record.route[i-1]), b=nodes.get(record.route[i]);
    const speed=plan.speed*factors.get(material), duration=Math.hypot(b.x-a.x,b.y-a.y)/speed;
    pieces.push({start:clock,end:clock+duration,a,b,speed,phase:'Rolling',material,contacts});
    clock+=duration;
    const event=events.get(b.id);
    if(event && i<record.route.length-1) {
      contacts++; material=event.material;
      if(event.hold>0) pieces.push({start:clock,end:clock+event.hold,a:b,b,speed:0,phase:'Contact '+b.id,material,contacts});
      clock+=event.hold;
    }
  }
  const last=nodes.get(record.route.at(-1));
  pieces.push({start:clock,end:Infinity,a:last,b:last,speed:0,phase:'Finished',material,contacts});
  return {pieces,duration:clock};
}
export function atTime(track, seconds) {
  const t=Math.max(0,seconds), part=track.pieces.find(p=>t<p.end) || track.pieces.at(-1);
  const fraction=part.speed ? (t-part.start)/(part.end-part.start) : 0;
  return {x:part.a.x+(part.b.x-part.a.x)*fraction,y:part.a.y+(part.b.y-part.a.y)*fraction,
    speed:part.speed,material:part.material,phase:part.phase,contacts:part.contacts};
}
export function validPlan(record,plan) {
  if(!Number.isFinite(plan.speed)||plan.speed<=0||!Number.isFinite(plan.release)||plan.release<0)return false;
  if(plan.nodes.some(n=>!Number.isFinite(n.x)||!Number.isFinite(n.y)||n.x<0||n.y<0||n.x>record.board.width||n.y>record.board.height))return false;
  const nodes=new Map(plan.nodes.map(n=>[n.id,n]));
  return record.route.slice(1).every((id,i)=>{const a=nodes.get(record.route[i]),b=nodes.get(id);return Math.hypot(a.x-b.x,a.y-b.y)>0;});
}
