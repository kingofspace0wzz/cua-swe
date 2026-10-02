// Generic finite digital engine. All ordinary algorithms are public.
export const gateNames=['A1','A2','A3','B1','B2','B3','C1','C2'];
export const memoryNames=['Q0','Q1','Q2'];
export const lightNames=['Flare','Wash','Pearl'];
const ops={OR:(a,b)=>a|b,AND:(a,b)=>a&b,XOR:(a,b)=>a^b,MASK:(a,b)=>a&(1-b)};
export function validate(board) {
  const nodes=[...board.gates,...board.memories,...board.lights];
  const ids=new Set(['Tap','Sweep','E0','E1']);
  for(const n of nodes){if(ids.has(n.id))throw Error('Duplicate node '+n.id);ids.add(n.id);}
  for(const n of nodes)for(const key of ['a','b','D','EN','from'])if(key in n&&!ids.has(n[key]))throw Error('Unknown signal '+n[key]);
  const gates=new Map(board.gates.map(n=>[n.id,n]));const visiting=new Set(),done=new Set(),order=[];
  function visit(id){if(done.has(id)||!gates.has(id))return;if(visiting.has(id))throw Error('Combinational cycle');visiting.add(id);let n=gates.get(id);if(!ops[n.type])throw Error('Unknown gate');visit(n.a);visit(n.b);visiting.delete(id);done.add(id);order.push(n);}
  board.gates.forEach(n=>visit(n.id));return order;
}
export function simulate(board, data, horizon=12) {
  const order=validate(board);let q=Object.fromEntries(board.memories.map((m,i)=>[m.id,Number(data.initial[i]||0)]));const rows=[];
  for(let t=0;t<horizon;t++) {
    const old={...q};const v={...old,Tap:Number(data.tap[t]||0),Sweep:Number(data.sweep[t]||0),E0:Number(t%2===0&&data.allowEven),E1:Number(t%2===1&&data.allowOdd)};
    for(const n of order)v[n.id]=ops[n.type](v[n.a],v[n.b]);
    for(const n of board.lights)v[n.id]=v[n.from];
    const next=Object.fromEntries(board.memories.map(m=>[m.id,v[m.EN]?v[m.D]:old[m.id]]));
    rows.push({t,v,old,next});q=next;
  }
  return rows;
}
