import {board} from './board.js';
import {simulate} from './engine.js';
import {ledgerHTML,stageHTML,wavesHTML,rowText} from './report.js';
const app=document.querySelector('#app');
const copy=x=>JSON.parse(JSON.stringify(x));
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Provider inbox is imported by the host product, never bundled with this client.
let inbox;try{inbox=JSON.parse(localStorage.getItem('lantern.provider.inbox')||'null');}catch{}
let saved;try{saved=JSON.parse(localStorage.getItem('lantern.saved')||'{}');}catch{saved={};}
let id=inbox?.records[0]?.id,view='show',tick=0,draft=null,undo=[],timer=null,notice='',sheet=0,zoom=1;
const record=()=>inbox.records.find(r=>r.id===id);
const data=()=>draft||saved[id]||record().defaults;
const stop=()=>{if(timer)clearInterval(timer);timer=null;};
const persist=()=>localStorage.setItem('lantern.saved',JSON.stringify(saved));
const button=(name,attrs='')=>`<button ${attrs}>${name}</button>`;
function head(){return `<header><p class="muted">LANTERN · tabletop sequence desk</p><h1>${esc(record().title)}</h1><label>Show edition<select aria-label="Show edition" id="edition">${inbox.records.map(r=>`<option value="${esc(r.id)}" ${r.id===id?'selected':''}>${esc(r.title)}</option>`).join('')}</select></label><div class="row">${button('Show','data-view="show"')}${button('Designer inbox','data-view="inbox"')}</div><div class="status" role="status">${esc(notice)}</div></header>`;}
function controls(){return `<div class="row">${button('Back','id="back"')}${button(timer?'Pause':'Play','id="play"')}${button('Step','id="step"')}</div><label>Scrub tick <output id="tick-label">${tick}</output><input id="position" aria-label="Scrub tick" type="range" min="0" max="11" step="1" value="${tick}"></label>`;}
function editHTML(){const d=data();return `<section aria-label="Sequence editor"><h2>Draft sequence</h2><div class="row editbar">${button('Save','id="save"')}${button('Undo','id="undo" '+(!undo.length?'disabled':''))}${button('Cancel','id="cancel"')}</div><p>Edits preview immediately; Save commits the whole edition.</p><div class="row">${['allowEven','allowOdd'].map((k,i)=>`<label class="bit"><input type="checkbox" data-field="${k}" ${d[k]?'checked':''}>Allow ${i?'odd':'even'}</label>`).join('')}</div><div class="row">${d.initial.map((v,i)=>`<label class="bit"><input aria-label="Initial Q${i}" type="checkbox" data-field="initial" data-index="${i}" ${v?'checked':''}>Initial Q${i}</label>`).join('')}</div><h2>Input frames · ticks 0–11</h2><div class="timeline">${Array.from({length:12},(_,t)=>`<div class="frame">Tick ${t}${['tap','sweep'].map(k=>`<label><input aria-label="${k==='tap'?'Tap':'Sweep'} tick ${t}" type="checkbox" data-field="${k}" data-index="${t}" ${d[k][t]?'checked':''}>${k==='tap'?'Tap':'Sweep'}</label>`).join('')}</div>`).join('')}</div><label>Edition notes<textarea aria-label="Edition notes" id="note" rows="2">${esc(d.note)}</textarea></label></section>`;}
function showHTML(){const rows=simulate(board,data());return `<section><h2>Light bank · <span id="now">tick ${tick}</span></h2><div id="stage">${stageHTML(rows[tick],record().colors)}</div>${controls()}<div id="waveform">${wavesHTML(rows,record().colors)}</div></section>${draft?editHTML():`<div class="row">${button('Edit sequence','id="edit"')}${button('Reset edition','id="reset"')}</div><p>Saved note: <span id="saved-note">${esc(data().note)}</span></p>`}<section><h2>Live patchboard</h2><div class="inventory" id="live-nodes">${liveHTML(rows[tick])}</div></section><section aria-label="Signal ledger"><h2>Signal ledger · all 12 ticks</h2><p class="muted">Bit words follow each printed heading left to right. Old memory is used throughout each row.</p><div id="ledger">${ledgerHTML(rows)}</div></section>`;}
function liveHTML(row){return record().inventory.map(n=>`<div class="module">${esc(n.id)} · ${esc(n.type)}<br><b>${row.v[n.id]}</b>${n.type==='MEM'?` → ${row.next[n.id]}`:''}</div>`).join('');}
function inboxHTML(){return `<section><h2>Designer inbox</h2><p>${esc(inbox.provider)}<br>${esc(inbox.delivery)}</p><p>Approved reference sheets, local pins and timing card. Fit width is scrollable; 2× enlarges details without a gesture.</p><div class="row">${button('Guide','id="guide"')}${button('Reference sheets','id="sheets"')}</div></section>${view==='guide'?`<section class="guide" aria-label="Designer guide">${esc(inbox.guide)}</section>`:`<div class="sheet-tools"><label>Reference sheet<select id="sheet" aria-label="Reference sheet">${inbox.sheets.map((s,i)=>`<option value="${i}" ${sheet===i?'selected':''}>${esc(s.title)}</option>`).join('')}</select></label><div class="row">${button('Fit width','id="fit"')}${button('2× detail','id="zoom"')}</div></div><div class="viewport" tabindex="0" aria-label="Reference image viewport"><img alt="${esc(inbox.sheets[sheet].title)}" src="${esc(inbox.sheets[sheet].src)}" style="width:${zoom*100}%"></div>`}`;}
function render(){if(!inbox?.records?.length){app.innerHTML='<h1>Lantern Sequence Desk</h1><p>Empty designer inbox. Open this app in the prepared product runtime to receive the show editions and reference attachments.</p>';return;}app.innerHTML=head()+(view==='show'?showHTML():inboxHTML());bind();}
function refresh(){const rows=simulate(board,data());document.querySelector('#stage').innerHTML=stageHTML(rows[tick],record().colors);document.querySelector('#now').textContent=`tick ${tick}`;document.querySelector('#tick-label').textContent=tick;document.querySelector('#position').value=tick;document.querySelector('#live-nodes').innerHTML=liveHTML(rows[tick]);document.querySelector('#waveform').innerHTML=wavesHTML(rows,record().colors);document.querySelector('#ledger').innerHTML=ledgerHTML(rows);}
function change(fn){undo.push(copy(draft));fn();notice='Unsaved preview';refresh();document.querySelector('#undo').disabled=false;document.querySelector('.status').textContent=notice;}
function bind(){
 document.querySelector('#edition').onchange=e=>{stop();id=e.target.value;draft=null;undo=[];tick=0;notice='';render();};
 document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{stop();view=b.dataset.view;render();});
 const on=(id,fn)=>{const e=document.getElementById(id);if(e)e.onclick=fn;};
 on('edit',()=>{stop();draft=copy(data());undo=[];notice='Draft open';render();});
 on('save',()=>{saved[id]=copy(draft);persist();draft=null;undo=[];notice='Edition saved';render();});
 on('cancel',()=>{stop();draft=null;undo=[];notice='Draft cancelled';render();});
 on('undo',()=>{if(undo.length){draft=undo.pop();notice='Draft operation undone';render();}});
 on('reset',()=>{stop();delete saved[id];persist();tick=0;notice='Delivered defaults restored for this edition';render();});
 on('back',()=>{stop();tick=Math.max(0,tick-1);refresh();document.querySelector('#play').textContent='Play';});
 on('step',()=>{stop();tick=Math.min(11,tick+1);refresh();document.querySelector('#play').textContent='Play';});
 on('play',()=>{if(timer){stop();document.querySelector('#play').textContent='Play';return;}if(tick===11)tick=0;refresh();document.querySelector('#play').textContent='Pause';timer=setInterval(()=>{tick=Math.min(11,tick+1);refresh();if(tick===11){stop();document.querySelector('#play').textContent='Play';}},record().rateMs);});
 const position=document.querySelector('#position');if(position)position.oninput=e=>{stop();tick=Number(e.target.value);refresh();document.querySelector('#play').textContent='Play';};
 document.querySelectorAll('[data-field]').forEach(e=>e.onchange=()=>change(()=>{const k=e.dataset.field;if(e.dataset.index!==undefined)draft[k][Number(e.dataset.index)]=Number(e.checked);else draft[k]=e.checked;}));
 const note=document.querySelector('#note');if(note)note.oninput=()=>change(()=>{draft.note=note.value;});
 on('guide',()=>{view='guide';render();});on('sheets',()=>{view='inbox';render();});
 const sel=document.querySelector('#sheet');if(sel)sel.onchange=e=>{sheet=Number(e.target.value);zoom=1;render();};
 on('fit',()=>{zoom=1;render();});on('zoom',()=>{zoom=2;render();});
 const vp=document.querySelector('.viewport');if(vp){let drag;vp.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,l:vp.scrollLeft,t:vp.scrollTop};vp.setPointerCapture(e.pointerId);};vp.onpointermove=e=>{if(drag){vp.scrollLeft=drag.l+drag.x-e.clientX;vp.scrollTop=drag.t+drag.y-e.clientY;}};vp.onpointerup=()=>drag=null;vp.onpointercancel=()=>drag=null;}
}
render();
