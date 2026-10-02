import {compute,initial,fmt} from './model.mjs';
import {connectionsFor} from './plan.mjs';
import {attachViewer} from './viewer.mjs';
const $=s=>document.querySelector(s), inbox=JSON.parse(localStorage.getItem('tideglass.inbox')||'null');
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
if(inbox?.editions?.length) start(inbox);
function start(inbox) {
  $('#empty').hidden=true;$('#desk').hidden=false;
  const stored=JSON.parse(localStorage.getItem('tideglass.workspace')||'{}');
  let edition=inbox.editions.find(e=>e.id===stored.edition)||inbox.editions[0];
  let all=stored.states||{}, histories={}, selected=edition.driver, draft=null, timer=null, tab='preview';
  const viewer=attachViewer($('#viewer'));
  const state=()=>all[edition.id]||(all[edition.id]=initial(edition));
  const clone=x=>JSON.parse(JSON.stringify(x));
  function persist(){localStorage.setItem('tideglass.workspace',JSON.stringify({edition:edition.id,states:all}));}
  function active(){const s=clone(state());if(draft)s.phases[draft.id]=draft.value;return s;}
  function pause(){clearInterval(timer);timer=null;$('#motion-status').textContent='Paused';}
  function commit(fn){(histories[edition.id]||=[]).push(clone(state()));fn(state());persist();render();}
  function showTab(name){tab=name;document.querySelectorAll('.tab').forEach(n=>n.hidden=n.id!==name);document.querySelectorAll('[data-tab]').forEach(n=>n.setAttribute('aria-current',String(n.dataset.tab===name)));$('#inspector').hidden=!['preview','report'].includes(name);if(name==='originals')viewer.show(edition.sheets[Number($('#sheet').value)]);}
  document.querySelectorAll('[data-tab]').forEach(n=>n.onclick=()=>showTab(n.dataset.tab));
  $('#edition').innerHTML=inbox.editions.map(e=>`<option value="${escape(e.id)}">${escape(e.title)}</option>`).join('');
  function editionUI(){
    $('#edition').value=edition.id;selected=edition.driver;draft=null;state();
    $('#component').innerHTML=[...edition.components].sort((a,b)=>a.id.localeCompare(b.id)).map(c=>`<option value="${c.id}">${c.id} · ${escape(c.label)}</option>`).join('');
    $('#sheet').innerHTML=edition.sheets.map((s,i)=>`<option value="${i}">${escape(s.title)}</option>`).join('');
    $('#guide-copy').innerHTML=inbox.guide.map(g=>`<section><h2>${escape(g.title)}</h2><p>${escape(g.body)}</p></section>`).join('');
    $('#inventory-copy').innerHTML=edition.components.map(c=>`<p><strong>${c.id} · ${escape(c.label)}</strong><br>${c.kind==='gear'?'Teeth':'Diameter (mm)'}: ${c.size}<br>Initial phase: ${c.phase}°</p>`).join('');
    viewer.show(edition.sheets[0]);render();showTab(tab);persist();
  }
  $('#edition').onchange=()=>{pause();edition=inbox.editions.find(e=>e.id===$('#edition').value);editionUI();};
  $('#sheet').onchange=()=>viewer.show(edition.sheets[Number($('#sheet').value)]);
  $('#component').onchange=()=>{draft=null;selected=$('#component').value;render();};
  function relation(v){return v.relation==='driver'?'Driver (none)':`${v.parent} / ${v.relation==='axis'?'common axis':v.relation==='mesh'?'external mesh':v.relation}`;}
  function card(v){return `<article class="state-card"><h3>Component ${v.id} · ${escape(v.label)}</h3><p>Driving relation: ${relation(v)}</p><p>Signed ratio: ${fmt(v.ratio)}</p><p>Phase: ${fmt(v.phase)}°</p><p>Unwrapped angle: ${fmt(v.angle)}°</p><p>Wrapped angle: ${fmt(v.wrapped)}°</p><p>Direction: ${v.direction}</p></article>`;}
  function draw(values) {
    const cols=4, spacing=160, row=165;
    const pos=new Map(values.map((v,i)=>[v.id,{x:80+(i%cols)*spacing,y:75+Math.floor(i/cols)*row}]));
    let svg=`<svg viewBox="0 0 640 1020" xmlns="http://www.w3.org/2000/svg" aria-label="Moving marked wheels">`;
    for(const e of connectionsFor(edition)) {const a=pos.get(e.from),b=pos.get(e.to);if(a&&b)svg+=`<path d="M${a.x},${a.y} Q${(a.x+b.x)/2+20},${a.y+50} ${b.x},${b.y}" fill="none" stroke="#a2b9ae" stroke-width="2"/>`;}
    for(const v of values){const p=pos.get(v.id);svg+=`<g role="button" tabindex="0" aria-label="Select ${v.id} ${escape(v.label)}" data-part="${v.id}" transform="translate(${p.x} ${p.y})"><circle r="53" fill="${v.id===selected?'#fff8d0':'#f8f3e6'}" stroke="${escape(v.color)}" stroke-width="${v.id===selected?6:3}"/><g transform="rotate(${v.wrapped})">`;
      for(let t=0;t<12;t++)svg+=`<path transform="rotate(${t*30})" d="M-3 -51 L-3 -58 L3 -58 L3 -51" fill="${escape(v.color)}"/>`;
      svg+=`<path d="M0 12 L0 -42 M-7 -32 L0 -43 L7 -32" fill="none" stroke="${escape(v.color)}" stroke-width="6"/><circle cx="17" cy="12" r="5" fill="#bc7836"/></g><circle r="6" fill="#173e48"/><text y="79" text-anchor="middle" font-size="24" fill="#173e48">${v.id}</text><text y="101" text-anchor="middle" font-size="19" fill="#173e48">${escape(v.label)}</text></g>`;
    }
    $('#mechanism').innerHTML=svg+'</svg>';
    $('#mechanism').querySelectorAll('[data-part]').forEach(n=>{const select=()=>{draft=null;selected=n.dataset.part;render();$('#inspector').scrollIntoView({block:'start'});};n.onclick=select;n.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')select();};});
  }
  function render(){
    const s=active(), values=compute(edition,s),v=values.find(v=>v.id===selected);
    $('#driver').value=s.driver;$('#angle-slider').value=Math.max(-720,Math.min(720,s.driver));$('#direction').value=s.direction;
    $('#component').value=selected;$('#report-copy').innerHTML=values.map(card).join('');$('#selected-state').innerHTML=card(v);draw(values);
    $('#draft').hidden=!draft;if(draft&&document.activeElement!==$('#phase'))$('#phase').value=draft.value;
    $('#undo').disabled=!(histories[edition.id]?.length)||!!draft;
    for(const id of ['driver','angle-slider','apply-angle','direction','step','play','reset'])$('#'+id).disabled=!!draft;
    $('#edit-phase').disabled=!!draft;
  }
  function applyAngle(value){if(!Number.isFinite(value))return;pause();commit(s=>s.driver=value);}
  $('#apply-angle').onclick=()=>applyAngle(Number($('#driver').value));
  $('#driver').onkeydown=e=>{if(e.key==='Enter')applyAngle(Number($('#driver').value));};
  $('#angle-slider').oninput=()=>applyAngle(Number($('#angle-slider').value));
  $('#direction').onchange=()=>{state().direction=Number($('#direction').value);persist();};
  function step(){commit(s=>s.driver+=15*s.direction);}
  $('#step').onclick=()=>{pause();step();};$('#play').onclick=()=>{if(!timer){timer=setInterval(step,500);$('#motion-status').textContent='Playing · 15° / 500 ms';}};$('#pause').onclick=pause;
  $('#reset').onclick=()=>{pause();commit(s=>{const fresh=initial(edition);s.driver=0;s.phases=fresh.phases;});};
  $('#undo').onclick=()=>{pause();if(histories[edition.id]?.length){all[edition.id]=histories[edition.id].pop();persist();render();}};
  $('#edit-phase').onclick=()=>{pause();draft={id:selected,value:state().phases[selected]};render();};
  $('#phase').oninput=()=>{const n=Number($('#phase').value);if(Number.isFinite(n)){draft.value=n;render();}};
  $('#cancel').onclick=()=>{draft=null;render();};
  $('#save').onclick=()=>{const d=draft;draft=null;commit(s=>s.phases[d.id]=d.value);};
  editionUI();
}
