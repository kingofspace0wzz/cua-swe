// All geometry is ordinary client code. Coordinates are logical sheet units.
export const clone = x => JSON.parse(JSON.stringify(x));
export function matrix(p) {
  const r=[ [1,0,0,1], [0,1,-1,0], [-1,0,0,-1], [0,-1,1,0] ][p.turn];
  const m=p.mirror?-1:1, s=p.scale;
  const [a,b,c,d]=[r[0]*m*s,r[1]*m*s,r[2]*s,r[3]*s];
  return [a,b,c,d,300+p.dx-300*(a+c),300+p.dy-300*(b+d)];
}
export function poseOf(m) {
  if(!Array.isArray(m)||m.length!==6||m.some(v=>!Number.isFinite(v)))throw Error('Six finite affine entries required.');
  for(let turn=0;turn<4;turn++) for(const mirror of [false,true]) for(const scale of [.9,1,1.1]) {
    const p={turn,mirror,scale,dx:0,dy:0}, q=matrix(p);
    if(q.slice(0,4).every((v,i)=>Math.abs(v-m[i])<1e-6))return {...p,dx:m[4]-q[4],dy:m[5]-q[5]};
  }
  throw Error('Use a disclosed mounting and scale.');
}
export function forward(p,x,y) {const [a,b,c,d,e,f]=matrix(p);return {x:a*x+c*y+e,y:b*x+d*y+f};}
export function inverse(p,x,y) {const [a,b,c,d,e,f]=matrix(p), k=a*d-b*c;return {x:(d*(x-e)-c*(y-f))/k,y:(-b*(x-e)+a*(y-f))/k};}
export function normalize(raw) {
  if(!raw||typeof raw!=='object')throw Error('Registration must contain a mounting and finder table.');
  const pose=raw.pose||poseOf(raw.matrix);
  if(!Number.isInteger(pose.turn)||pose.turn<0||pose.turn>3||typeof pose.mirror!=='boolean'||![.9,1,1.1].includes(pose.scale)||![pose.dx,pose.dy].every(Number.isFinite))throw Error('Invalid mounting, scale or shift.');
  let stars=raw.stars;
  if(!stars&&raw.catalogue)stars=Object.entries(raw.catalogue).map(([name,xy])=>({name,x:xy[0],y:xy[1],plate:Object.entries(raw.identifications||{}).find(([,n])=>n===name)?.[0]||null}));
  if(!Array.isArray(stars)||!stars.length||stars.length>100)throw Error('Finder table must contain named stars.');
  const names=new Set(),ids=new Set();
  for(const s of stars){
    if(!s||typeof s.name!=='string'||!s.name.trim()||names.has(s.name)||![s.x,s.y].every(Number.isFinite))throw Error('Finder rows need unique names and finite coordinates.');
    names.add(s.name);
    if(s.plate!=null){if(typeof s.plate!=='string'||!/^P\d+$/.test(s.plate)||ids.has(s.plate))throw Error('Plate observations may only be assigned once.');ids.add(s.plate);}
  }
  return {pose:{...pose},stars:stars.map(s=>({...s,plate:s.plate||null})),notes:typeof raw.notes==='string'?raw.notes:''};
}
export function autoIdentify(state,points) {
  const s=clone(state);s.stars.forEach(a=>a.plate=null);
  const pairs=[];
  for(const star of s.stars)for(const point of points){const q=forward(s.pose,star.x,star.y);pairs.push({star,point,d:Math.hypot(q.x-point.x,q.y-point.y)});}
  pairs.sort((a,b)=>a.d-b.d||a.star.name.localeCompare(b.star.name));const used=new Set();
  for(const p of pairs)if(p.d<=12&&!p.star.plate&&!used.has(p.point.id)){p.star.plate=p.point.id;used.add(p.point.id);}
  return s;
}
export function reassign(state,id,name) {
  const s=clone(state),old=s.stars.find(a=>a.plate===id),next=s.stars.find(a=>a.name===name),other=next?.plate;
  if(old)old.plate=other||null;if(next)next.plate=id;return s;
}
export function ledger(state,points) {return points.map(p=>({id:p.id,name:state.stars.find(s=>s.plate===p.id)?.name||'Unassigned',...inverse(state.pose,p.x,p.y)}));}
export function measurements(state,targets) {
  return targets.map(t=>{const q=inverse(state.pose,t.x,t.y),near=[...state.stars].sort((a,b)=>Math.hypot(q.x-a.x,q.y-a.y)-Math.hypot(q.x-b.x,q.y-b.y)||a.name.localeCompare(b.name));
    return {id:t.id,...q,neighbours:near.slice(0,2).map(s=>({name:s.name,dx:q.x-s.x,dy:q.y-s.y}))};});
}
