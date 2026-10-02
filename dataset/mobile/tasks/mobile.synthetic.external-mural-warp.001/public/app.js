import {importMapping} from './adapter.js';
import {drawSource,drawWall} from './render.js';
import {wallPin,moveFromWall,moveFromSource,serializePins} from './model.js';
import {documentViewer} from './viewer.js';
const $=document.querySelector('#app');
const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
const inbox=read('mural.inbox.v1',[]),saved=read('mural.plans.v1',{});
const clone=v=>JSON.parse(JSON.stringify(v));
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const button=(text,fn,cls)=>{const b=node('button',text,cls);b.onclick=fn;return b;};
const fmt=n=>Number(n).toFixed(2);
let packet=null,mapping=null,draft=null,selected=null,history=[],screen='plan',message='Ready.';
let mappingError='';
function basePlan(){return clone(saved[packet.id]||{pins:packet.pins,note:''});}
function open(p){packet=p;draft=basePlan();selected=draft.pins[0]?.id;history=[];screen='plan';message='Ready.';mappingError='';try{mapping=importMapping(packet);}catch(e){mapping=null;mappingError=e.message;}render();window.scrollTo(0,0);}
function inboxView(){packet=null;$.replaceChildren(node('p','MURAL DESK · MOBILE WEB','muted'),node('h1','Projection inbox'),node('p','Open an imported office packet to plan the wall projection.'));
 if(!inbox.length)$.append(node('p','No imported packets. The prepared runtime supplies the external office inbox; local builds start empty.','card'));
 for(const p of inbox)$.append(button(p.title,()=>open(p),'packet-button'));
 $.append(node('p','Standalone synthetic product. Received attachments stay independent of plan editing.','muted'));
}
function field(label,value,type='number') {const l=node('label',label),input=node('input');input.type=type;input.value=value;if(type==='number')input.step='any';l.append(input);return [l,input];}
function persist(){localStorage.setItem('mural.plans.v1',JSON.stringify(saved));}
function commit(pin){if(!pin){message='Rejected: outside the valid projection region. Pin unchanged.';updateStatus();return;}
 history.push(clone(draft));draft.pins=draft.pins.map(p=>p.id===selected?pin:p);message='Pin moved.';render();}
function updateStatus(){const s=$.querySelector('[role=status]');if(s)s.textContent=message;}
function render(){
 $.replaceChildren(button('Inbox',()=>{inboxView();window.scrollTo(0,0);}),node('h1',packet.title));
 const nav=node('nav');for(const [key,label] of [['plan','Plan'],['received','Received packet'],['receipt','Saved receipt']])nav.append(button(label,()=>{screen=key;render();window.scrollTo(0,0);},key===screen?'active':''));$.append(nav);
 if(screen==='received'){const host=node('div');$.append(host);documentViewer(host,packet.attachments);return;}
 if(screen==='receipt'){receipt();return;}
 if(!mapping){$.append(node('p','Plan import unavailable: '+mappingError,'status'));return;}
 const sourceRow=node('div',undefined,'source-row'),source=node('canvas');source.width=packet.artwork.width;source.height=packet.artwork.height;source.className='source-thumb';source.setAttribute('role','img');source.setAttribute('aria-label','Source artwork thumbnail');sourceRow.append(source,node('p','Source artwork → wall plan. Purple ring = selected pin.','small'));$.append(sourceRow);drawSource(source,packet);
 const figure=node('figure',undefined,'wall-figure'),wall=node('canvas');wall.width=packet.wall.width;wall.height=packet.wall.height;wall.setAttribute('role','img');wall.setAttribute('aria-label','Wall preview');figure.append(wall,node('figcaption','Wall preview · tap to move selected pin. Gray areas cannot receive paint.'));$.append(figure);
 drawWall(wall,packet,mapping,draft.pins,selected);
 wall.addEventListener('click',e=>{const r=wall.getBoundingClientRect(),pt=[(e.clientX-r.left)*wall.width/r.width,(e.clientY-r.top)*wall.height/r.height];commit(moveFromWall(packet,mapping,draft.pins.find(p=>p.id===selected),pt));});
 const markNav=node('div',undefined,'actions');for(const p of draft.pins)markNav.append(button('Select '+p.label,()=>{selected=p.id;message='Selected '+p.label+'.';render();},p.id===selected?'active':''));$.append(markNav);
 const pin=draft.pins.find(p=>p.id===selected),pt=wallPin(packet,mapping,pin),panel=packet.panels.find(p=>p.id===pin.panelId);
 const readout=node('section',undefined,'selected');readout.setAttribute('aria-label','Selected pin');readout.append(node('p','Selected: '+pin.label),node('p','Panel: '+panel.label),node('p',`Source x: ${fmt(pin.source[0])} · y: ${fmt(pin.source[1])}`),node('p',pt?`Wall x: ${fmt(pt[0])} · y: ${fmt(pt[1])}`:'Wall: outside valid region'));$.append(readout);
 const status=node('p',message,'status');status.setAttribute('role','status');$.append(status);
 const editor=node('section',undefined,'editor');editor.append(node('h2','Place selected pin'));
 const a=node('div',undefined,'inputs'),[xl,x]=field('Wall X',pt?fmt(pt[0]):''),[yl,y]=field('Wall Y',pt?fmt(pt[1]):'');a.append(xl,yl);editor.append(a,button('Place wall coordinates',()=>commit(moveFromWall(packet,mapping,pin,[x.value===''?NaN:Number(x.value),y.value===''?NaN:Number(y.value)]))));
 const b=node('div',undefined,'inputs'),[sl,s]=field('Source X',fmt(pin.source[0])),[tl,t]=field('Source Y',fmt(pin.source[1]));b.append(sl,tl);editor.append(b,button('Place source coordinates',()=>commit(moveFromSource(packet,mapping,pin,[s.value===''?NaN:Number(s.value),t.value===''?NaN:Number(t.value)]))));
 const noteLabel=node('label','Plan note'),note=node('textarea');note.value=draft.note;note.oninput=()=>{draft.note=note.value;};noteLabel.append(note);editor.append(noteLabel);
 const actions=node('div',undefined,'actions');actions.append(button('Undo',()=>{if(history.length){draft=history.pop();message='Last move undone.';render();}else{message='No move to undo.';updateStatus();}}),button('Cancel edits',()=>{draft=basePlan();history=[];message='Edits cancelled.';render();}),button('Save plan',()=>{draft.receipt=serializePins(mapping,draft.pins);saved[packet.id]=clone(draft);persist();history=[];message='Plan saved for this packet.';render();},'primary'),button('Reopen saved',()=>{draft=basePlan();history=[];message='Saved plan reopened.';render();}));editor.append(actions);$.append(editor);
}
function receipt(){const value=saved[packet.id],section=node('section',undefined,'receipt');section.append(node('h2','Saved plan receipt'));
 if(!value){section.append(node('p','No saved plan for this packet.'));$.append(section);return;}
 section.append(node('p',`Packet: ${packet.title}`),node('p','Note: '+value.note));
 for(const r of value.receipt){const row=node('section',undefined,'receipt-row');row.setAttribute('aria-label','Receipt '+r.label);row.append(node('h3',r.label),node('p','Panel ID: '+r.panelId),node('p',`Source: ${r.source.map(fmt).join(', ')}`),node('p',`Local: ${r.local.map(fmt).join(', ')}`),node('p',`Station: ${r.station.map(fmt).join(', ')}`));section.append(row);}$.append(section);
}
inboxView();
