import {toSheet,toPanel,sheetHeading,reviewKey} from './geometry.js';
const root=document.querySelector('#app');
const imported=JSON.parse(localStorage.getItem('foldnote.imported')||'{"records":[]}');
const records=Array.isArray(imported.records)?imported.records:[];
let saved=JSON.parse(localStorage.getItem('foldnote.reviews')||'{}');
let proof=records[0],panel=proof?.panels[0],view='flat',shown=true,status='';
let draft;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const url=svg=>'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
const round=n=>Math.round(n*100)/100;
function loadReview(){draft={...(saved[reviewKey(proof,panel)]||{u:round(panel.width/2),v:round(panel.height/2),heading:0,note:''})};status='';}
function persist(){saved[reviewKey(proof,panel)]={...draft};localStorage.setItem('foldnote.reviews',JSON.stringify(saved));status='Saved on this device';}
function header(){return `<div class="top"><div><h1>Foldnote</h1><div class="muted">Packaging proof review</div></div><span class="badge">Imported</span></div><label class="chooser">Proof<select aria-label="Proof">${records.map(r=>`<option value="${esc(r.id)}" ${r.id===proof.id?'selected':''}>${esc(r.title)}</option>`).join('')}</select></label>`;}
function wireProof(){root.querySelector('select').onchange=e=>{proof=records.find(r=>r.id===e.target.value);panel=proof.panels[0];loadReview();render();};}
function artStage(art,w,h,marker=false){
 const isFlat=view==='flat',q=isFlat?toSheet(panel,draft.u,draft.v):{x:draft.u,y:draft.v};
 const angle=isFlat?sheetHeading(panel,draft.heading):draft.heading;
 // CSS pixels keep the review symbol legible at any proof size. Artwork is never stretched.
 const height=Math.min(230,374*h/w);
 return `<div class="stage" role="img" aria-label="${view==='source'?'Source proof artwork':'Review artwork'}" style="height:${height}px" data-width="${w}" data-height="${h}"><img alt="${esc(view==='source'?proof.title:panel.title)} artwork" src="${esc(url(art))}">${marker&&shown?`<div class="marker" data-x="${q.x}" data-y="${q.y}"><span class="arrow" style="transform:rotate(${angle}deg)"></span><button class="anchor" aria-label="Review marker">1</button></div>`:''}</div>`;
}
function fit(){const el=root.querySelector('.stage');if(!el)return;const marker=el.querySelector('.marker');if(!marker)return;const w=Number(el.dataset.width),h=Number(el.dataset.height),s=Math.min(el.clientWidth/w,el.clientHeight/h);marker.style.left=`${(el.clientWidth-w*s)/2+Number(marker.dataset.x)*s}px`;marker.style.top=`${(el.clientHeight-h*s)/2+Number(marker.dataset.y)*s}px`;}
function recordText(p){return Object.entries(p).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join('\n\n');}
function report(){
 root.innerHTML=header()+`<div class="report-nav"><button id="back">← Source proof</button> <button id="frames">Panel frames ↓</button></div><h2>Panel report</h2><p class="muted">Imported attachment · complete placement contract</p>`+proof.report.map(r=>`<section class="card"><h2>${esc(r.title)}</h2><p>${esc(r.text)}</p></section>`).join('')+proof.panels.map(p=>`<section class="card placement"><h2>${esc(p.title)} · ${esc(p.id)}</h2><p>Trimmed panel: ${p.width} × ${p.height}</p><pre class="record">${esc(recordText(p.placement))}</pre></section>`).join('');
 wireProof();root.querySelector('#frames').onclick=()=>root.querySelector('.placement').scrollIntoView({block:'start'});root.querySelector('#back').onclick=()=>{view='source';render();window.scrollTo(0,0);};
}
function readForm(){for(const k of ['u','v','heading'])draft[k]=Number(root.querySelector(`[name="${k}"]`).value);draft.u=round(Math.max(0,Math.min(panel.width,draft.u)));draft.v=round(Math.max(0,Math.min(panel.height,draft.v)));draft.heading=((draft.heading%360)+360)%360;draft.note=root.querySelector('textarea').value;}
function render(){
 if(!proof){root.innerHTML='<h1>Foldnote</h1><section class="empty"><h2>No imported proofs</h2><p>This review workspace opens provider-supplied proof attachments. The prepared task runtime imports an inbox; a standalone source build starts empty.</p></section>';return;}
 if(view==='report'){report();return;}
 let body=header()+`<nav class="tabs">${[['flat','Flat sheet'],['panel','Individual panel'],['source','Source proof']].map(([v,t])=>`<button data-view="${v}" aria-pressed="${view===v}">${t}</button>`).join('')}</nav>`;
 if(view==='source'){
  body+=`<div class="stage-head"><h2>Source proof</h2><button id="report">Panel report</button></div>`+artStage(proof.sheet.artwork,proof.sheet.width,proof.sheet.height)+`<p class="muted">Original imported flattened drawing. Open Panel report for the complete frame and placement record.</p>`;
 } else {
  body+=`<div class="panels" aria-label="Panel selection">${proof.panels.map(p=>`<button data-panel="${esc(p.id)}" aria-pressed="${p.id===panel.id}">${esc(p.title)}</button>`).join('')}</div><div class="stage-head"><h2>${esc(panel.title)} review</h2><button id="visibility">${shown?'Hide':'Show'} marker</button></div>`;
  const art=view==='flat'?proof.sheet:{artwork:panel.artwork,width:panel.width,height:panel.height};
  body+=artStage(art.artwork,art.width,art.height,true)+`<p class="muted">Tap artwork to move marker · fields edit panel coordinates</p><form class="form"><div class="fields"><label>Panel u<input aria-label="Panel u" name="u" type="number" step="0.01" value="${draft.u}"></label><label>Panel v<input aria-label="Panel v" name="v" type="number" step="0.01" value="${draft.v}"></label><label>Heading °<input aria-label="Heading degrees" name="heading" type="number" step="1" value="${draft.heading}"></label></div><label class="note">Panel note<textarea aria-label="Panel note">${esc(draft.note)}</textarea></label><div class="save-row"><p role="status">${esc(status||'Ready to review')}</p><button class="primary" type="submit">Save review</button></div></form>`;
 }
 root.innerHTML=body;wireProof();fit();
 root.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{if(root.querySelector('form'))readForm();view=b.dataset.view;render();});
 if(view==='source'){root.querySelector('#report').onclick=()=>{view='report';render();window.scrollTo(0,0);};return;}
 root.querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>{panel=proof.panels.find(p=>p.id===b.dataset.panel);loadReview();render();});
 root.querySelector('#visibility').onclick=()=>{shown=!shown;render();};
 root.querySelector('form').onsubmit=e=>{e.preventDefault();readForm();persist();render();};
 root.querySelector('.stage').onclick=e=>{
  if(e.target.closest('.anchor'))return;
  readForm();
  const el=e.currentTarget,b=el.getBoundingClientRect(),w=Number(el.dataset.width),h=Number(el.dataset.height),s=Math.min(el.clientWidth/w,el.clientHeight/h);
  const x=(e.clientX-b.left-el.clientLeft-(el.clientWidth-w*s)/2)/s,y=(e.clientY-b.top-el.clientTop-(el.clientHeight-h*s)/2)/s;
  const q=view==='flat'?toPanel(panel,x,y):{u:x,v:y};
  draft.u=round(Math.max(0,Math.min(panel.width,q.u)));draft.v=round(Math.max(0,Math.min(panel.height,q.v)));status='Position changed · Save review to keep';render();
 };
}
if(proof)loadReview();render();window.addEventListener('resize',fit);
