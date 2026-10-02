import {clone,normalize,forward,ledger,measurements,reassign,autoIdentify} from './geometry.js';
import {readPlate} from './raster.js';
import {registrationFor} from './integration.js';
import {guide} from './guide.js';
const root=document.querySelector('#app'),INBOX='larkspur.provider-inbox.v1',SAVED='larkspur.saved.v1';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number.isFinite(n)?(Math.abs(n)<.05?'0.0':n.toFixed(1)):'—';
let inbox={editions:[]},saved={},edition,observations={points:[],targets:[]},current,draft=null,history=[],error='',tab='Plate',zoom=1,marks=true,labels=false,loading=false;
try{inbox=JSON.parse(localStorage.getItem(INBOX)||'{"editions":[]}');if(!Array.isArray(inbox.editions))inbox={editions:[]};}catch{error='The imported inbox could not be read.';}
try{saved=JSON.parse(localStorage.getItem(SAVED)||'{}');if(!saved||typeof saved!=='object')saved={};}catch{saved={};}
function store(){try{localStorage.setItem(SAVED,JSON.stringify(saved));}catch{error='Could not save locally. Keep this draft open and retry.';return false;}return true;}
function shipped(){return normalize(registrationFor(edition.id,observations.points));}
function active(){return draft||current;}
async function open(id){
  loading=true;edition=inbox.editions.find(e=>e.id===id);draft=null;history=[];error='';tab='Plate';render();
  try{observations=await readPlate(edition.plate);}catch{observations={points:[],targets:[]};error='The plate attachment could not be decoded. Finder and guide are still available.';}
  try{current=saved[id]?normalize(saved[id]):shipped();}catch(e){current=null;error='Integration error: '+e.message+' You can still inspect Plate, Finder and Guide.';}
  loading=false;render();
}
function safe(action){return (...args)=>{try{action(...args);}catch(e){error='Integration error: '+e.message;render();}};}
function mutate(fn){if(!draft)return;history.push(clone(draft));if(history.length>100)history.shift();draft=fn(clone(draft));render();}
function table(headers,rows){return `<table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
function reports(){const s=active();if(!s)return '<p>Review is unavailable until the integration is valid.</p>';
  const l=ledger(s,observations.points),m=measurements(s,observations.targets);
  return `<section aria-label="Identification ledger" class="card report"><h2>Identification ledger</h2>${table(['Disc','Finder name','Chart x','Chart y'],l.map(r=>[r.id,r.name,num(r.x),num(r.y)]))}</section>
  <section aria-label="Target measurements" class="card report"><h2>Target measurements</h2><p class="muted">Chart units • target minus neighbour</p>${table(['Target','x','y','Neighbour','dx','dy'],m.flatMap(t=>t.neighbours.map(n=>[t.id,num(t.x),num(t.y),n.name,num(n.dx),num(n.dy)])))}</section>
  <section aria-label="Saved notes" class="card"><h2>Observer notes</h2><p>${esc(s.notes||'No notes yet.')}</p></section>`;
}
function viewer(){const isPlate=tab==='Plate',s=active();const projected=isPlate&&marks&&s?s.stars.filter(a=>a.plate).map(a=>({...a,...forward(s.pose,a.x,a.y)})):[];
  return `<div class="tools"><label for="zoom">Sheet zoom</label><select id="zoom" aria-label="Sheet zoom" style="width:115px">${[[1,'Fit'],[2,'2×'],[3,'3×']].map(([z,n])=>`<option value="${z}" ${z===zoom?'selected':''}>${n}</option>`).join('')}</select>${isPlate?`<button id="marks" aria-pressed="${marks}">${marks?'Hide':'Show'} registration marks</button><button id="labels" aria-pressed="${labels}">${labels?'Hide':'Show'} observation labels</button>`:''}</div>
  <p class="muted">${isPlate?'Unlabeled received plate • magenta rings = targets':'Printed finder • names belong to filled stars'}<br>600 × 600 • grid 50 • scroll to pan at 2×/3×</p>
  <div class="viewport" aria-label="Sheet pan area"><div class="stage" role="region" aria-label="${isPlate?'Plate':'Finder'} logical stage" style="width:calc(var(--fit) * ${zoom});height:calc(var(--fit) * ${zoom})"><img alt="${isPlate?'Unlabeled received sky plate':'Named finder chart'}" src="${esc(isPlate?edition.plate:edition.finder)}"><svg viewBox="0 0 600 600" aria-hidden="true">${projected.map(p=>`<path d="M ${p.x-9} ${p.y} h 18 M ${p.x} ${p.y-9} v 18" stroke="#007e93" stroke-width="3"/>${labels?`<text x="${p.x+(p.x>420?-18:18)}" y="${p.y<45?p.y+36:p.y-22}" text-anchor="${p.x>420?'end':'start'}" fill="#005363" font-size="16" stroke="#faf8ee" stroke-width="3" paint-order="stroke">${esc(p.plate)} ${esc(p.name)}</text>`:''}`).join('')}${isPlate&&labels?observations.points.map(p=>`<text x="${p.x+(p.x>540?-18:18)}" y="${p.y>550?p.y-22:p.y+36}" text-anchor="${p.x>540?'end':'start'}" fill="#172a3c" font-size="15" stroke="#faf8ee" stroke-width="3" paint-order="stroke">${p.id}</text>`).join('')+observations.targets.map(p=>`<text x="${p.x+(p.x>540?-18:18)}" y="${p.y>550?p.y-22:p.y+36}" text-anchor="${p.x>540?'end':'start'}" fill="#8a1f5e" font-size="16">${p.id}</text>`).join(''):''}</svg></div></div>`;
}
function editor(){if(!draft)return '';const p=draft.pose;
return `<section class="card"><h2>Draft registration</h2><div class="form-grid"><div><label for="turn">Clockwise turn</label><select id="turn" aria-label="Clockwise turn">${[0,1,2,3].map(t=>`<option value="${t}" ${p.turn===t?'selected':''}>${t*90}°</option>`).join('')}</select></div><div><label for="mirror">Emulsion mounting</label><select id="mirror" aria-label="Emulsion mounting"><option value="false" ${!p.mirror?'selected':''}>Not mirrored</option><option value="true" ${p.mirror?'selected':''}>Mirrored</option></select></div></div>
<label for="scale">Scale ratio</label><select id="scale" aria-label="Scale ratio">${[.9,1,1.1].map(v=>`<option value="${v}" ${p.scale===v?'selected':''}>${v.toFixed(2)}</option>`).join('')}</select>
<p role="status" aria-label="Draft shift">Shift dx ${num(p.dx)}, dy ${num(p.dy)} plate units</p><div class="row"><button id="left" aria-label="Shift left 5">← 5</button><button id="right" aria-label="Shift right 5">5 →</button><button id="up" aria-label="Shift up 5">↑ 5</button><button id="down" aria-label="Shift down 5">5 ↓</button></div>
<label for="disc">Plate observation</label><select id="disc" aria-label="Plate observation">${observations.points.map(o=>`<option>${o.id}</option>`).join('')}</select>
<label for="name">Assign finder star</label><select id="name" aria-label="Assign finder star"><option>Unassigned</option>${draft.stars.map(s=>`<option>${esc(s.name)}</option>`).join('')}</select><div class="row"><button id="assign">Reassign observation</button><button id="auto">Auto-identify</button></div>
<label for="notes">Observer draft notes</label><textarea id="notes" aria-label="Observer draft notes">${esc(draft.notes)}</textarea>
<div class="row"><button id="undo" ${history.length?'':'disabled'}>Undo</button><button id="cancel">Cancel</button><button id="save" class="primary">Save registration</button></div></section>`;
}
function render(){
 if(!edition){root.innerHTML=`<section class="card"><h2>Provider inbox is empty</h2><p>The prepared runtime imports two external finder/plate pairs. Outside it there are no attachments; no reference scans are bundled with the client.</p>${error?`<p class="error">${esc(error)}</p>`:''}</section><section class="card">${guide}</section>`;return;}
 const s=active();root.innerHTML=`<label for="edition">Observation edition</label><select id="edition" aria-label="Observation edition" ${draft?'disabled':''}>${inbox.editions.map(e=>`<option value="${esc(e.id)}" ${e.id===edition.id?'selected':''}>${esc(e.name)}</option>`).join('')}</select>
 <p class="muted">${esc(edition.exposure)}<br>${esc(edition.nominalScaleClass)} • ${edition.targetCount} ring targets</p>${error?`<p class="error" role="alert">${esc(error)}</p>`:''}
 ${s?`<div class="banner">${draft?'Draft • not saved':'Saved registration'} · ${s.pose.turn*90}° ${s.pose.mirror?'mirrored':'not mirrored'} · scale ${s.pose.scale.toFixed(2)} · shift (${num(s.pose.dx)}, ${num(s.pose.dy)})</div>`:''}
 <nav aria-label="Desk views">${['Plate','Finder','Review','Guide'].map(t=>`<button id="tab-${t}" class="${t===tab?'active':''}" aria-pressed="${t===tab}">${t}</button>`).join('')}</nav>
 ${loading?'<p>Reading imported plate…</p>':(tab==='Plate'||tab==='Finder'?viewer():tab==='Guide'?`<section class="card">${guide}</section>`:reports())}
 ${draft?editor():`<div class="row"><button id="edit" class="primary" ${s?'':'disabled'}>Edit registration</button><button id="reset">Reset this edition</button></div>`}`;
 root.style.setProperty('--fit',Math.min(root.clientWidth-28,600)+'px');
 const on=(id,event,fn)=>{const el=document.getElementById(id);if(el)el.addEventListener(event,safe(fn));};
 on('edition','change',e=>open(e.target.value));for(const t of ['Plate','Finder','Review','Guide'])on('tab-'+t,'click',()=>{tab=t;render();});
 on('zoom','change',e=>{zoom=Number(e.target.value);render();});on('marks','click',()=>{marks=!marks;render();});on('labels','click',()=>{labels=!labels;render();});
 on('edit','click',()=>{draft=clone(current);history=[];render();});
 on('reset','click',()=>{delete saved[edition.id];if(store()){current=shipped();error='';render();}});
 for(const [id,key,change] of [['left','dx',-5],['right','dx',5],['up','dy',-5],['down','dy',5]])on(id,'click',()=>mutate(s=>{s.pose[key]+=change;return s;}));
 for(const k of ['turn','scale','mirror'])on(k,'change',e=>mutate(s=>{s.pose[k]=k==='mirror'?e.target.value==='true':Number(e.target.value);return s;}));
 on('assign','click',()=>{const id=document.getElementById('disc').value,name=document.getElementById('name').value;mutate(s=>reassign(s,id,name));});
 on('auto','click',()=>mutate(s=>autoIdentify(s,observations.points)));
 // Commit note editing on change so text entry is one undoable transaction.
 on('notes','change',e=>{history.push(clone(draft));draft.notes=e.target.value;const undo=document.getElementById('undo');if(undo)undo.disabled=false;});
 on('undo','click',()=>{if(history.length)draft=history.pop();render();});on('cancel','click',()=>{draft=null;history=[];render();});
 on('save','click',()=>{const value=normalize(draft);saved[edition.id]=value;if(store()){current=value;draft=null;history=[];render();}});
}
render();if(inbox.editions.length)open(inbox.editions[0].id).catch(e=>{error='Input error: '+e.message;loading=false;render();});
