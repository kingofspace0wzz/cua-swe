// Protected exact rational kernel bridge. Public optics only; no production picker,
// matrices, writable geometry module, or monotone residual assumption.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export class ReadinessError extends Error { constructor(s) {super(s); this.name='ReadinessError';} }
export function allRoots(o,d,support) {
 const r=spawnSync('python3',['-B',fileURLToPath(new URL('./nearest_bridge.py',import.meta.url))],{input:JSON.stringify({o,d,support}),encoding:'utf8',timeout:10000});
 if(r.status!==0) throw Error('Exact oracle error: '+r.stderr);
 return JSON.parse(r.stdout);
}
export function nearest(o,d,support) {
 if(!support?.length) throw new ReadinessError('Required loaded XY support unavailable');
 // Enumerate possible fixture roots independently of availability only to prove
 // that no potentially nearer root is hidden in a gap. Never use these as ground.
 const possible=allRoots(o,d,[[0,1,0,1]]), loaded=allRoots(o,d,support);
 if(possible.hits.some(h=>!support.some(([a,b,c,e])=>h.p[0]>=a && h.p[0]<=b && h.p[1]>=c && h.p[1]<=e)))
  throw new ReadinessError('Required ray support incomplete (not model failure)');
 if(loaded.status!=='hit') throw new ReadinessError('No usable strictly positive loaded hit: '+loaded.status);
 return loaded;
}
