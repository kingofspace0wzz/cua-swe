import { route } from './routing.js';

// This is the entire ordinary client. External provider attachments are imported
// into the isolated browser profile, not included in this source or its build.
const INBOX_KEY = 'campus-pocket.provider-inbox.v1';
const STATE_KEY = 'campus-pocket.trips.v1';
function read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
const inbox = read(INBOX_KEY, {campuses:[]});
const campuses = Array.isArray(inbox.campuses) ? inbox.campuses : [];
const state = read(STATE_KEY, {campus:null, choices:{}, saved:null});
state.choices ||= {};
let campus = campuses.find(c => c.id === state.campus) || campuses[0];
let screen = 'trip', reportPage = 0, picker = null, notice = '';
const app = document.querySelector('#app');
const e = (tag, text, attrs = {}) => { const node=document.createElement(tag); if(text!==null)node.textContent=text; for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v); return node; };
function button(text, action, attrs={}) { const b=e('button',text,{type:'button',...attrs});b.addEventListener('click',action);return b; }
function persist() { state.campus=campus?.id ?? null; localStorage.setItem(STATE_KEY,JSON.stringify(state)); }
function trip() { return state.choices[campus.id] ||= {...(campus.default_trip || {origin:campus.stops[0]?.id,destination:campus.stops.at(-1)?.id,stepFree:false})}; }
function stop(id) { return campus.stops.find(p=>p.id===id); }
function name(id) { return stop(id)?.label || id; }
function levelName(id) { const p=stop(id);return `${p?.label || id} (L${p?.level ?? '?'})`; }
function go(next) {screen=next;picker=null;notice='';render();window.scrollTo(0,0);}
function drawHeader() {
  const head=e('header',null);head.append(e('p','CAMPUS POCKET',{class:'eyebrow'}),e('h1',campus ? campus.title : 'Your campus inbox'));
  head.append(e('p','Synthetic mobile web · not travel guidance',{class:'muted small'}));
  if(campus)head.append(button('Change campus',()=>{picker='campus';render();window.scrollTo(0,0);},{class:'quiet'}));
  app.append(head);
}
function nav() {
  const n=e('nav',null,{'aria-label':'Campus views'});
  for(const [id,title] of [['trip','Plan trip'],['map','Original map'],['report','Routing report']]) n.append(button(title,()=>go(id),{'aria-current':screen===id?'page':'false'}));
  app.append(n);
}
function renderPicker() {
  const section=e('section',null,{'aria-label':'Choose '+picker,class:'panel picker'});
  section.append(e('h2',picker==='campus'?'Imported campuses':`Choose ${picker}`));
  const options=picker==='campus'?campuses:campus.stops;
  for(const option of options) section.append(button(picker==='campus'?option.title:`${option.label} · Level ${option.level}`,()=>{
    if(picker==='campus'){campus=option;screen='trip';reportPage=0;}else trip()[picker]=option.id;
    picker=null;notice='';persist();render();window.scrollTo(0,0);
  },{class:'choice'}));
  section.append(button('Cancel',()=>{picker=null;render();},{class:'quiet'}));app.append(section);
}
function drawTrip() {
  const t=trip(); const form=e('section',null,{'aria-label':'Trip settings',class:'panel settings'});
  for(const key of ['origin','destination'])form.append(button(`${key[0].toUpperCase()+key.slice(1)}: ${name(t[key])}`,()=>{picker=key;render();window.scrollTo(0,0);},{class:'choice'}));
  form.append(button(`Step-free: ${t.stepFree?'on':'off'}`,()=>{t.stepFree=!t.stepFree;notice='';persist();render();},{'aria-pressed':String(t.stepFree),class:'preference'}));
  form.append(button('Save trip',()=>{state.saved={campus:campus.id,...t};persist();notice='Trip saved';render();},{class:'primary'}));
  app.append(form);
  if(notice)app.append(e('p',notice,{role:'status',class:'notice'}));
  const result=route(campus,t.origin,t.destination,t.stepFree);
  const details=e('section',null,{'aria-label':'Route result',class:'panel result'});
  details.append(e('h2',result?`Route · ${result.distance} m`:'No route available'));
  details.append(e('p',`${name(t.origin)} → ${name(t.destination)} · ${t.stepFree?'Step-free':'All walking'}`,{class:'summary'}));
  if(!result)details.append(e('p','No permitted route for these stops and preference. Try different stops or turn off step-free.'));
  else if(!result.legs.length)details.append(e('p','Already at your destination.'));
  else {
    const list=e('ol',null);
    for(const leg of result.legs){
      const row=e('li',null);row.append(e('p',`${levelName(leg.from)} → ${levelName(leg.to)}`,{class:'leg-stops'}));
      row.append(e('p',`${leg.link.kind} ${leg.link.id} · ${leg.distance} m`,{class:'leg-meta'}));list.append(row);
    }
    details.append(list);
  }
  app.append(details);
  const saved=e('section',null,{class:'panel','aria-label':'Saved trip'});saved.append(e('h2','Saved trip'));
  const s=state.saved, c=s && campuses.find(x=>x.id===s.campus);
  if(c){const label=id=>c.stops.find(x=>x.id===id)?.label||id;saved.append(e('p',`${c.title} · ${label(s.origin)} → ${label(s.destination)} · Step-free ${s.stepFree?'on':'off'}`));saved.append(button('Open saved trip',()=>{campus=c;state.choices[c.id]={origin:s.origin,destination:s.destination,stepFree:s.stepFree};persist();notice='';go('trip');},{class:'quiet'}));}
  else saved.append(e('p','No saved trip yet.',{class:'muted'}));app.append(saved);
}
function drawMap() {
  const panel=e('section',null,{class:'panel', 'aria-label':'Original attachment'});
  panel.append(e('h2','Original map'),e('p',campus.diagram.description,{class:'small'}));
  // Render the imported, original vector as an image; no reconstruction or
  // geometry/closure inference occurs in the ordinary attachment viewer.
  panel.append(e('img',null,{src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(campus.diagram.svg),alt:campus.title+' original two-floor campus map',class:'campus-map'}));
  panel.append(e('p','Read the routing report for the complete provider rules and link rows.',{class:'small'}));app.append(panel);
}
function drawReport() {
  const report=campus.report, pages=report.pages;reportPage=Math.max(0,Math.min(reportPage,pages.length-1));
  const page=pages[reportPage];const panel=e('section',null,{class:'panel report','aria-label':'Provider report page'});
  panel.append(e('p',`${report.title} · ${reportPage+1} / ${pages.length}`,{class:'eyebrow'}),e('h2',page.title));
  for(const text of page.paragraphs||[])panel.append(e('p',text));
  if(page.table){const table=e('table',null);const caption=e('caption',page.title);table.append(caption);const head=e('tr',null);for(const col of page.table.columns)head.append(e('th',col,{scope:'col'}));const thead=e('thead',null);thead.append(head);table.append(thead);const body=e('tbody',null);for(const values of page.table.rows){const tr=e('tr',null);for(const cell of values)tr.append(e('td',String(cell)));body.append(tr);}table.append(body);panel.append(table);}
  const pager=e('div',null,{class:'pager'});
  const prev=button('Previous page',()=>{reportPage--;render();window.scrollTo(0,0);});prev.disabled=reportPage===0;
  const next=button('Next page',()=>{reportPage++;render();window.scrollTo(0,0);});next.disabled=reportPage===pages.length-1;
  pager.append(prev,next);panel.append(pager);app.append(panel);
}
function render() {
  app.replaceChildren();drawHeader();
  if(!campus){const panel=e('section',null,{class:'panel'});panel.append(e('h2','No imported campuses'),e('p','The prepared runtime imports provider maps and routing reports into this browser profile. A standalone public build begins with an empty inbox; it does not contain sample campus data.'));app.append(panel);return;}
  if(picker){renderPicker();return;}
  nav();if(screen==='trip')drawTrip();else if(screen==='map')drawMap();else drawReport();
}
render();
