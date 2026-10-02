import {importPlan,exportPlan} from './boundary.js';
import {itinerary,atTime,validPlan} from './engine.js';
import {esc,attachmentHTML} from './viewer.js';
const root=document.querySelector('#app');
const inboxKey='marble-post-inbox', saveKey='marble-post-plans';
function read(key,fallback){try{return JSON.parse(localStorage.getItem(key))||fallback;}catch{return fallback;}}
const inbox=read(inboxKey,{packets:[],guide:[]}), saved=read(saveKey,{});
let selected=inbox.packets[0]?.id, time=0, draft=null, nodeId=null, view='run', tab='Guide', page=0, notice='';
const packet=()=>inbox.packets.find(p=>p.id===selected);
const plan=()=>draft || saved[selected]?.plan || importPlan(packet().record);
const fmt=n=>Number(n.toFixed(3)).toFixed(3);
function store(){localStorage.setItem(saveKey,JSON.stringify(saved));}
function boardHTML(record,p,s) {
 const W=record.board.width,H=record.board.height;
 const points=new Map(p.nodes.map(n=>[n.id,n]));
 let lines='';
 for(let x=0;x<=W;x++)lines+=`<path d="M${x} 0V${H}"/>`;
 for(let y=0;y<=H;y++)lines+=`<path d="M0 ${y}H${W}"/>`;
 return `<svg class="board" role="img" aria-label="Track board" viewBox="0 0 ${W} ${H}"><g stroke="#d5d8c9" stroke-width=".025">${lines}</g><polyline points="${record.route.map(id=>{const n=points.get(id);return n.x+','+n.y;}).join(' ')}" fill="none" stroke="#557d7d" stroke-width=".17" stroke-linejoin="round"/><g>${p.nodes.map(n=>`<circle cx="${n.x}" cy="${n.y}" r=".16" fill="#f5f1df" stroke="#365c5b" stroke-width=".055"/><text x="${n.x+.24}" y="${n.y-.28}" fill="#23484c" font-size=".48">${esc(n.id)}</text>`).join('')}</g><circle role="img" aria-label="Marble" cx="${s.x}" cy="${s.y}" r=".27" fill="#ba481d" stroke="#fff" stroke-width=".08"/></svg>`;
}
function render(){
 if(!packet()) {root.innerHTML='<h1>Marble Post</h1><h2>Inbox is empty</h2><p>Track-office packets arrive in the prepared app profile. This source-only build has no received inputs.</p>';return;}
 const pk=packet(),r=pk.record,p=plan(),track=itinerary(r,p),s=atTime(track,time);
 if(view==='packet'){root.innerHTML=attachmentHTML(inbox,pk,tab,page);return;}
 root.innerHTML=`<header class="brand"><div><div class="eyebrow">MARBLE POST · TOY RAIL STUDIO</div><h1>Run & replay</h1></div><button data-action="packet">Received packet</button></header><nav aria-label="Tracks">${inbox.packets.map(q=>`<button data-action="track" data-value="${esc(q.id)}" aria-pressed="${q.id===selected}">${esc(q.title)}</button>`).join('')}</nav>${boardHTML(r,p,s)}<section class="readout" aria-label="Replay readout"><span>X ${fmt(s.x)}</span><span>Y ${fmt(s.y)}</span><span>Speed ${fmt(s.speed)}</span><span>Contacts ${s.contacts}</span><span class="wide">Material ${esc(s.material)} · Phase ${esc(s.phase)}</span><span class="wide">Time ${fmt(time)} s · Finish ${fmt(track.duration)} s</span></section><div class="row time-row"><label>Replay seconds<input id="time" aria-label="Replay seconds" inputmode="decimal" type="number" min="0" step="any" value="${time}"></label><button data-action="go">Go to time</button><button data-action="reset">Reset</button></div><input aria-label="Scrub time" id="scrub" type="range" min="0" max="${Math.max(40,track.duration+5,time)}" step="0.125" value="${time}"><div class="row transport"><button data-action="back">Step back</button><button data-action="reverse">Reverse</button><button data-action="play">Play</button><button data-action="forward">Step forward</button></div><div class="muted">Manual playback · each press ±0.5 s · board cells</div>${draft?editorHTML(p):`<div class="row"><button class="primary" data-action="edit">Edit plan</button><button data-action="receipt">Save receipt</button></div>`}<div class="notice" role="status">${esc(notice)}</div>${view==='receipt'?`<section class="sheet" aria-label="Save receipt"><h2>Save receipt</h2><button data-action="closeReceipt">Close receipt</button>${saved[selected]?.receipt?`<p>Locally queued provider record</p><pre>${esc(JSON.stringify(saved[selected].receipt,null,2))}</pre>`:'<p>No saved plan yet.</p>'}</section>`:''}`;
}
function editorHTML(p){
 nodeId=nodeId||packet().record.route[0];const n=p.nodes.find(n=>n.id===nodeId);
 return `<section class="sheet" aria-label="Plan editor"><h2>Plan draft</h2><div class="fields"><label>Base speed<input id="speed" aria-label="Base speed" type="number" step="any" value="${p.speed}"></label><label>Release seconds<input id="release" aria-label="Release seconds" type="number" step="any" value="${p.release}"></label></div><fieldset><legend>Node in board cells</legend><nav>${packet().record.route.map(id=>`<button data-action="node" data-value="${esc(id)}" aria-pressed="${nodeId===id}">Node ${esc(id)}</button>`).join('')}</nav><div class="fields"><label>Node X<input id="nodeX" aria-label="Node X" type="number" step="any" value="${n.x}"></label><label>Node Y<input id="nodeY" aria-label="Node Y" type="number" step="any" value="${n.y}"></label></div></fieldset><div class="row"><button data-action="preview">Preview draft</button><button class="primary" data-action="save">Save plan</button><button data-action="cancel">Cancel</button></div></section>`;
}
function collect(){
 if(!draft)return true;
 const p=structuredClone(draft);p.speed=Number(root.querySelector('#speed').value);p.release=Number(root.querySelector('#release').value);
 const n=p.nodes.find(n=>n.id===nodeId);n.x=Number(root.querySelector('#nodeX').value);n.y=Number(root.querySelector('#nodeY').value);
 if(!validPlan(packet().record,p)){notice='Use valid on-board nodes, positive speed and nonnegative release.';return false;}
 draft=p;notice='Draft preview • not saved';return true;
}
root.addEventListener('focusin',event=>{if(event.target.matches('input[type=number]'))event.target.select();});
root.addEventListener('input',event=>{if(event.target.id==='scrub'){time=Number(event.target.value);render();}});
root.addEventListener('click',event=>{
 const b=event.target.closest('button[data-action]');if(!b)return;
 const a=b.dataset.action,v=b.dataset.value;
 if(a==='packet'){draft=null;view='packet';tab='Guide';page=0;window.scrollTo(0,0);}
 if(a==='closePacket'){view='run';window.scrollTo(0,0);}
 if(a==='tab'){tab=v;page=0;window.scrollTo(0,0);}
 if(a==='previous'){page--;window.scrollTo(0,0);}
 if(a==='next'){page++;window.scrollTo(0,0);}
 if(a==='track'){selected=v;draft=null;nodeId=null;time=0;view='run';notice='';}
 if(a==='go'){const n=Number(root.querySelector('#time').value);if(Number.isFinite(n))time=Math.max(0,n);}
 if(a==='reset')time=0;
 if(a==='forward'||a==='play')time+=.5;
 if(a==='back'||a==='reverse')time=Math.max(0,time-.5);
 if(a==='edit'){draft=structuredClone(plan());nodeId=packet().record.route[0];view='run';notice='Draft preview • not saved';}
 if(a==='node'){if(!collect())return;nodeId=v;}
 if(a==='preview'){if(!collect()){root.querySelector('[role=status]').textContent=notice;return;}}
 if(a==='save'){
   if(!collect()){root.querySelector('[role=status]').textContent=notice;return;}
   saved[selected]={plan:structuredClone(draft),receipt:exportPlan(packet().record,draft)};store();draft=null;notice='Plan saved • receipt queued';
 }
 if(a==='cancel'){draft=null;notice='Draft cancelled';}
 if(a==='receipt')view='receipt';
 if(a==='closeReceipt')view='run';
 render();
});
render();
