import {normalize,compute} from './schedule.mjs';
import {esc,ledger,timeline,report} from './render.mjs';
const $=s=>document.querySelector(s),clone=v=>JSON.parse(JSON.stringify(v));
let inbox=[],record=null,jobs=[],slip={job:'',days:0},saved=null,undo=[],integration=null,bootError='',sheetIndex=0,zoom=.85;
const key=()=>`brine-saved:${record.id}`;
function storeRead(k,fallback){try{return JSON.parse(localStorage.getItem(k))??fallback;}catch{return fallback;}}
function show(which){for(const id of ['work','chart','guide'])$('#'+id).hidden=id!==which;}
function error(message=''){$('#issue').hidden=!message;$('#issue').textContent=message?`Schedule integration error: ${message} The received chart and reading guide are still available.`:'';}
function opts(list,value){return list.map(j=>`<option value="${esc(j.id)}" ${j.id===value?'selected':''}>${esc(j.name)}</option>`).join('');}
function snapshot(){return clone({jobs,slip});}
function remember(){undo.push(snapshot());if(undo.length>80)undo.shift();$('#save-status').textContent='Unsaved draft';}
function restore(s){jobs=clone(s.jobs);slip=clone(s.slip);render();}
function calculated(){try {const r=compute(jobs,record.firstDay,slip);error();return r;}catch(e){error(e.message);return null;}}
function render(){
 const r=calculated();$('#ledger').innerHTML=ledger(jobs,r);$('#timeline').innerHTML=timeline(jobs,r);$('#report').innerHTML=report(jobs,r,slip);
 const selected=$('#job').value;$('#job').innerHTML=opts(jobs,selected);$('#slip-job').innerHTML=opts(jobs,slip.job);$('#slip-days').value=slip.days;
 editor();if(!$('#export-panel').hidden)exportDraft();
}
function editor(){const j=jobs.find(j=>j.id===$('#job').value);if(!j)return;
 $('#start').value=j.start;$('#duration').value=j.duration;$('#predecessor').innerHTML=opts(jobs.filter(k=>k.id!==j.id),'');
 $('#links').innerHTML=j.links.map((l,n)=>{const name=jobs.find(k=>k.id===l.from)?.name||l.from;const label=`${name} to ${j.name} (${n+1})`;return `<div class="link-row"><p>${esc(name)} → ${esc(j.name)} · lag ${l.lag}</p><label for="type-${n}">Type for ${esc(label)}</label><select id="type-${n}" aria-label="Type for ${esc(label)}" data-link="${n}">${['FS','SS','FF'].map(t=>`<option ${t===l.type?'selected':''}>${t}</option>`).join('')}</select><button data-remove="${n}" aria-label="Remove ${esc(label)}">Remove dependency</button></div>`;}).join('')||'<p>No incoming dependencies.</p>';
 $('#links').querySelectorAll('[data-link]').forEach(el=>el.onchange=()=>{remember();j.links[+el.dataset.link].type=el.value;render();});
 $('#links').querySelectorAll('[data-remove]').forEach(el=>el.onclick=()=>{remember();j.links.splice(+el.dataset.remove,1);render();});
}
async function loadEdition(){
 record=inbox.find(r=>r.id===$('#edition').value);if(!record)return;
 $('#note').value=localStorage.getItem(`brine-note:${record.id}`)||'';undo=[];sheetIndex=0;
 $('#sheet').innerHTML=record.sheets.map((s,k)=>`<option value="${k}">${esc(s.name)}</option>`).join('');viewSheet();
 try{
  if(!integration||typeof integration.load!=='function')throw Error(bootError||'The received-chart integration could not be loaded.');
  const initial=normalize(await integration.load(clone(record)),record);
  saved=storeRead(key(),{jobs:initial,slip:{job:initial[0]?.id||'',days:0}});
  if(!saved||!Array.isArray(saved.jobs))throw Error('The saved schedule is incomplete. Reset this edition.');
  jobs=clone(saved.jobs);slip=clone(saved.slip);render();
 }catch(e){jobs=[];slip={job:'',days:0};$('#ledger').textContent='Integration unavailable';$('#timeline').textContent='Integration unavailable';$('#report').textContent='Report unavailable';$('#job').innerHTML='';error(e.message);}
 $('#save-status').textContent='Saved schedule';
}
function viewSheet(){const img=$('#drawing');const s=record?.sheets[sheetIndex];if(!s){img.removeAttribute('src');return;}img.src=s.image;img.onload=()=>size();size();$('#paper').scrollTo(0,0);}
function size(){const img=$('#drawing');if(img.naturalWidth){img.style.width=`${img.naturalWidth*zoom}px`;img.style.height=`${img.naturalHeight*zoom}px`;}$('#zoom-note').textContent=`Scale ${Math.round(zoom*100)}% · ${record?.sheets[sheetIndex]?.name||''}`;}
function exportDraft(){const r=calculated();$('#export-text').textContent=`${record.title}\nYard notes: ${$('#note').value}\n\n`+strip(ledger(jobs,r))+'\n\n'+strip(report(jobs,r,slip));}
function strip(html){const div=document.createElement('div');div.innerHTML=html.replace(/<br\s*\/?\s*>/g,'\n').replace(/<\/(p|h3|article)>/g,'\n');return div.textContent;}
function guarded(fn){return async()=>{try{await fn();}catch(e){error(e.message);}};}
$('#show-work').onclick=()=>show('work');$('#show-chart').onclick=()=>show('chart');$('#show-guide').onclick=()=>show('guide');
$('#edition').onchange=guarded(loadEdition);$('#job').onchange=editor;$('#sheet').onchange=()=>{sheetIndex=+$('#sheet').value;viewSheet();};
$('#read').onclick=()=>{zoom=.85;size();};$('#fit').onclick=()=>{zoom=$('#paper').clientWidth/($('#drawing').naturalWidth||832);size();};
$('#zin').onclick=()=>{zoom=Math.min(1.7,zoom+.15);size();};$('#zout').onclick=()=>{zoom=Math.max(.25,zoom-.15);size();};
for(const [id,dx,dy] of [['left',-300,0],['right',300,0],['up',0,-440],['down',0,440]])$('#'+id).onclick=()=>$('#paper').scrollBy(dx,dy);
$('#origin').onclick=()=>$('#paper').scrollTo(0,0);
let drag=null;$('#paper').onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,left:$('#paper').scrollLeft,top:$('#paper').scrollTop};$('#paper').setPointerCapture(e.pointerId);};
$('#paper').onpointermove=e=>{if(drag)$('#paper').scrollTo(drag.left+drag.x-e.clientX,drag.top+drag.y-e.clientY);};$('#paper').onpointerup=$('#paper').onpointercancel=()=>{drag=null;};
$('#update-job').onclick=guarded(()=>{const j=jobs.find(j=>j.id===$('#job').value);if(!j)return;remember();j.start=Number($('#start').value);j.duration=Number($('#duration').value);render();});
$('#add-link').onclick=guarded(()=>{const j=jobs.find(j=>j.id===$('#job').value);if(!j)return;remember();j.links.push({from:$('#predecessor').value,type:$('#link-type').value,lag:Number($('#lag').value)});render();});
$('#apply-slip').onclick=guarded(()=>{remember();slip={job:$('#slip-job').value,days:Number($('#slip-days').value)};render();});
$('#undo').onclick=guarded(()=>{if(undo.length)restore(undo.pop());});
$('#cancel').onclick=guarded(()=>{if(saved)restore(saved);undo=[];$('#save-status').textContent='Cancelled draft; saved schedule restored';});
$('#save').onclick=guarded(()=>{if(!calculated())return;saved=snapshot();localStorage.setItem(key(),JSON.stringify(saved));undo=[];$('#save-status').textContent='Saved schedule';});
$('#reset').onclick=guarded(async()=>{localStorage.removeItem(key());await loadEdition();$('#save-status').textContent='Reset to received integration';});
$('#note').oninput=()=>{if(record)localStorage.setItem(`brine-note:${record.id}`,$('#note').value);};
$('#export').onclick=()=>{$('#export-panel').hidden=false;exportDraft();$('#export-panel').scrollIntoView({block:'start'});};$('#close-export').onclick=()=>{$('#export-panel').hidden=true;};
async function init(){
 try{inbox=storeRead('brine-external-inbox',[]);if(!Array.isArray(inbox))throw Error('Inbox format is not supported.');}catch(e){inbox=[];error(e.message);}
 $('#edition').innerHTML=inbox.map(r=>`<option value="${esc(r.id)}">${esc(r.title)}</option>`).join('');$('#inbox-status').textContent=inbox.length?`${inbox.length} received refits • approved drawing attachments`:'No imported charts. The prepared review runtime supplies the foreman’s inbox.';
 try{$('#guide-copy').innerHTML=await (await fetch('./guide.html')).text();}catch{$('#guide-copy').textContent='Reading guide could not load. Please reload.';}
 try{integration=await import('./integration.mjs');}catch(e){bootError='The received-chart module could not load. Please repair its integration.';}
 if(inbox.length)await loadEdition();else error(bootError);
}
init().catch(e=>error(e.message));
