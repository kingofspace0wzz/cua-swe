import {sample,total,normalize,defaults} from './math.js';
import {poseFor} from './performance.js';
import {drawCel,loadSheets} from './renderer.js';
import {openReceived} from './viewer.js';
const root=document.querySelector('#app');
const inbox=JSON.parse(localStorage.getItem('celroom.inbox')||'null');
const copy=x=>JSON.parse(JSON.stringify(x));
if(!inbox?.editions?.length){root.innerHTML='<h1>Celroom</h1><h2>Inbox is empty</h2><p>Open the prepared mobile review session to receive the director boards and artist atlas. No artwork is bundled with this editor.</p>';}
else start();
async function start(){
 const saved=JSON.parse(localStorage.getItem('celroom.edits')||'{}');
 let selection=JSON.parse(localStorage.getItem('celroom.selection')||'{}');
 let edition=inbox.editions.find(e=>e.id===selection.edition)||inbox.editions[0];
 let clip=edition.clips.find(c=>c.id===selection.clip)||edition.clips[0];
 let frame=0,playing=false,reverse=false,loop=false,last=0,draft=null,beforeDraft=0,editedBeat=0,screen='animation';
 function key(){return edition.id+'/'+clip.id;}
 function entry(){return saved[key()]||{settings:defaults(clip),history:[]};}
 function settings(){return draft||entry().settings;}
 function persist(){localStorage.setItem('celroom.edits',JSON.stringify(saved));}
 function selectPersist(){localStorage.setItem('celroom.selection',JSON.stringify({edition:edition.id,clip:clip.id}));}
 function commit(next){const old=entry();saved[key()]={settings:copy(next),history:[...old.history,copy(old.settings)]};persist();}
 function paused(){playing=false;last=0;}
 function notice(s){const n=document.querySelector('#notice');if(n)n.textContent=s;}
 function seek(t){paused();frame=normalize(t,total(settings()),loop);paint();}
 async function enter(){paused();draft=null;reverse=false;frame=entry().settings.start;selectPersist();await loadSheets(edition);render();}
 function render(){screen='animation';root.innerHTML=`<header class="bar"><div><h1>Celroom</h1><span class="muted">Lamp courier • exposure review</span></div><button id="received-button">Received</button></header>
 <div class="row"><label>Edition <select id="edition" aria-label="Edition"></select></label></div><div class="row"><label>Clip <select id="clip" aria-label="Clip"></select></label></div>
 <section class="stage-wrap" aria-label="Animation preview"><canvas id="stage" aria-label="Current sprite"></canvas><small>160 × 180<br>pivot 80,150</small></section>
 <dl id="inspector" aria-label="Cel inspector"></dl>
 <div id="timeline" aria-label="Beat timeline"></div><input id="scrubber" aria-label="Scrub timeline" type="range" min="0" step="0.05">
 <div class="row"><label>Frame <input id="frame-input" aria-label="Frame" type="number" step="any"></label><button id="seek">Scrub</button><label><input type="checkbox" id="loop">Loop</label><label><input type="checkbox" id="reverse">Reverse</label></div>
 <div class="row"><button id="play" class="primary">Play</button><button id="step">Step</button><button id="reset-transport">Reset transport</button></div>
 <div class="row"><button id="edit">Edit clip</button><button id="undo">Undo</button><button id="reset-clip">Reset clip</button><button id="review-button">Review beats</button></div><p id="notice" role="status"></p><div id="edit-panel"></div>`;
 const $=s=>root.querySelector(s);const es=$('#edition'),cs=$('#clip');
 for(const e of inbox.editions)es.add(new Option(e.label,e.id));es.value=edition.id;
 for(const c of edition.clips)cs.add(new Option(c.label,c.id));cs.value=clip.id;
 es.onchange=()=>{edition=inbox.editions.find(e=>e.id===es.value);clip=edition.clips.find(c=>c.id===clip.id)||edition.clips[0];enter();};
 cs.onchange=()=>{clip=edition.clips.find(c=>c.id===cs.value);enter();};
 $('#received-button').onclick=()=>{paused();screen='received';openReceived(root,edition,render);};
 $('#review-button').onclick=()=>{paused();review();};
 $('#seek').onclick=()=>seek(Number($('#frame-input').value)||0);
 $('#scrubber').oninput=e=>seek(Number(e.target.value));
 $('#loop').checked=loop;$('#loop').onchange=e=>{loop=e.target.checked;frame=normalize(frame,total(settings()),loop);paint();};
 $('#reverse').checked=reverse;$('#reverse').onchange=e=>{reverse=e.target.checked;paint();};
 $('#play').onclick=()=>{playing=!playing;last=0;paint();};
 $('#step').onclick=()=>seek(frame+(reverse?-1:1));
 $('#reset-transport').onclick=()=>{paused();reverse=false;frame=0;$('#reverse').checked=false;paint();};
 $('#edit').onclick=()=>{if(draft)return;paused();beforeDraft=frame;draft=copy(entry().settings);editedBeat=0;editor();paint();};
 $('#undo').disabled=!entry().history.length||!!draft;
 $('#undo').onclick=()=>{paused();const e=entry();if(!e.history.length)return;const h=[...e.history],prev=h.pop();saved[key()]={settings:prev,history:h};persist();frame=prev.start;render();notice('Previous saved settings restored.');};
 $('#reset-clip').disabled=!!draft;$('#reset-clip').onclick=()=>{paused();commit(defaults(clip));frame=0;render();notice('Received clip timing restored. Undo is available.');};
 const timeline=$('#timeline');for(let i=0;i<7;i++){const b=document.createElement('button');b.textContent=String(i+1);b.setAttribute('aria-label','Beat '+(i+1));b.onclick=()=>{const s=settings();seek(s.exposures.slice(0,i).reduce((a,n,j)=>a+n+s.holds[j],0));};timeline.append(b);}
 if(draft)editor();paint();
 }
 function paint(){if(screen!=='animation')return;const $=s=>root.querySelector(s),s=settings(),m=sample(s,frame,loop),pose=poseFor(edition,clip.id,m.beat);frame=m.time;
 drawCel($('#stage'),edition,pose);
 const rows=[['Beat',`${m.beat+1} / 7`],['Cel',pose.cel],['Facing',pose.facing],['Exposure',String(m.exposure)],['Frame',m.time.toFixed(2)],['Total',String(m.length)],['Seconds',(m.time/(edition.fps*s.rate)).toFixed(3)],['FPS',(edition.fps*s.rate).toFixed(2)]];
 $('#inspector').replaceChildren();for(const [name,value] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;$('#inspector').append(dt,dd);}
 $('#scrubber').max=m.length-0.001;$('#scrubber').value=frame;if(document.activeElement!==$('#frame-input'))$('#frame-input').value=Number(frame.toFixed(3));
 [...$('#timeline').children].forEach((b,i)=>b.classList.toggle('active',i===m.beat));$('#play').textContent=playing?'Pause':'Play';
 $('#undo').disabled=!!draft||!entry().history.length;$('#reset-clip').disabled=!!draft;
 }
 function editor(){const panel=root.querySelector('#edit-panel');panel.innerHTML=`<fieldset><legend>Draft • ${clip.label}</legend><div class="row"><label>Edited beat <select id="edited-beat" aria-label="Edited beat">${Array.from({length:7},(_,i)=>`<option value="${i}">Beat ${i+1}</option>`).join('')}</select></label></div><div class="row"><label>Base exposure <input id="base" type="number" min="1" max="12" aria-label="Base exposure"></label><label>Extra hold <input id="hold" type="number" min="0" max="12" aria-label="Extra hold"></label></div><div class="row"><label>Start frame <input id="start" type="number" min="0" aria-label="Start frame"></label><label>Rate multiplier <input id="rate" type="number" min="0.5" max="2" step="0.25" aria-label="Rate multiplier"></label></div><p class="muted">Preview is draft-only. Save commits all fields; Cancel restores your pre-edit frame.</p><div class="row"><button id="save" class="primary">Save</button><button id="cancel">Cancel</button></div></fieldset>`;
 const $=s=>panel.querySelector(s);$('#edited-beat').value=editedBeat;$('#base').value=draft.exposures[editedBeat];$('#hold').value=draft.holds[editedBeat];$('#start').value=draft.start;$('#rate').value=draft.rate;
 $('#edited-beat').onchange=e=>{editedBeat=Number(e.target.value);editor();};
 const bound=(v,lo,hi)=>Math.max(lo,Math.min(hi,Number(v)||lo));
 function change(){draft.start=Math.min(draft.start,total(draft)-1);paused();frame=draft.start;$('#start').value=draft.start;paint();}
 $('#base').onchange=e=>{draft.exposures[editedBeat]=Math.round(bound(e.target.value,1,12));e.target.value=draft.exposures[editedBeat];change();};
 $('#hold').onchange=e=>{draft.holds[editedBeat]=Math.round(bound(e.target.value,0,12));e.target.value=draft.holds[editedBeat];change();};
 $('#start').onchange=e=>{draft.start=Math.round(bound(e.target.value,0,total(draft)-1));change();};
 $('#rate').onchange=e=>{draft.rate=bound(e.target.value,.5,2);e.target.value=draft.rate;change();};
 $('#save').onclick=()=>{commit(draft);frame=draft.start;draft=null;render();notice('Saved for this edition.');};
 $('#cancel').onclick=()=>{draft=null;frame=normalize(beforeDraft,total(entry().settings),loop);render();notice('Draft cancelled.');};
 }
 function review(){screen='review';const s=settings();root.innerHTML=`<section id="review"><button class="back">Back to animation</button><h2>${clip.label} • contact review</h2><p>${edition.label} · ${edition.fps*s.rate} fps${draft?' · Draft':''}</p><p class="muted">One drawing per keyed beat. Start inclusive; end exclusive. Tap a beat to inspect on stage.</p><div id="review-cards"></div></section>`;root.querySelector('.back').onclick=render;
 let t=0;for(let i=0;i<7;i++){const p=poseFor(edition,clip.id,i),n=s.exposures[i]+s.holds[i],card=document.createElement('article');card.className='review-card';card.setAttribute('aria-label','Beat '+(i+1)+' review');
 card.innerHTML=`<canvas aria-label="Beat ${i+1} sprite"></canvas><div><p><strong>Beat ${i+1}</strong></p><p>Cel: ${p.cel}</p><p>Facing: ${p.facing}</p><p>Start: ${t}</p><p>End: ${t+n}</p><p>Exposure: ${n}</p><button>Inspect beat ${i+1}</button></div>`;
 const time=t;card.querySelector('button').onclick=()=>{frame=time;render();};root.querySelector('#review-cards').append(card);drawCel(card.querySelector('canvas'),edition,p);t+=n;}
 }
 function tick(now){if(playing&&screen==='animation'){if(last){const next=frame+(now-last)/1000*edition.fps*settings().rate*(reverse?-1:1);if(!loop&&(next>=total(settings())-1||next<=0))paused();frame=normalize(next,total(settings()),loop);paint();}last=now;}requestAnimationFrame(tick);}
 await enter();requestAnimationFrame(tick);
}
