import {connectionsFor} from './plan.mjs';
export const wrap = a => ((a % 360) + 360) % 360;
export function factor(kind, parent, child) {
  if (kind === 'axis') return 1;
  const sign = kind === 'open belt' ? 1 : -1;
  if (!['mesh','open belt','crossed belt'].includes(kind)) throw Error('Unknown relation');
  return sign * parent.size / child.size;
}
export function initial(edition) {
  return {driver:0, phases:Object.fromEntries(edition.components.map(c=>[c.id,c.phase])), direction:1};
}
export function compute(edition, state) {
  const parts=new Map(edition.components.map(c=>[c.id,c]));
  const incoming=new Map(connectionsFor(edition).map(e=>[e.to,e]));
  const values=new Map(), visiting=new Set();
  function visit(id) {
    if(values.has(id)) return values.get(id);
    if(visiting.has(id)) throw Error('Connection cycle');
    visiting.add(id);
    const c=parts.get(id), phase=Number(state.phases[id] ?? c.phase);
    let ratio, angle, parent=null, kind='driver';
    if(id===edition.driver) {ratio=1;angle=state.driver+phase;}
    else {
      const e=incoming.get(id);if(!e || !parts.has(e.from)) throw Error('Disconnected '+id);
      parent=e.from;kind=e.kind;
      const p=visit(parent), k=factor(kind,parts.get(parent),c);
      ratio=p.ratio*k;angle=p.angle*k+phase;
    }
    const v={...c,phase,ratio,angle,wrapped:wrap(angle),parent,relation:kind,direction:ratio>0?'clockwise':'counterclockwise'};
    visiting.delete(id);values.set(id,v);return v;
  }
  return edition.components.map(c=>visit(c.id)).sort((a,b)=>a.id.localeCompare(b.id));
}
export const fmt = n => Math.abs(n)<0.0000005 ? '0.000' : n.toFixed(3);
