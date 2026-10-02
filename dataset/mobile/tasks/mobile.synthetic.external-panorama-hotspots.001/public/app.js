import {wrap,project,unproject} from './geometry.js';
import {reviewToPanorama,panoramaToReview} from './registration.js';
import {loadPanorama,renderWindow,renderOriginalStrip} from './panorama.js';

// Imported provider attachments live only in the receiving browser profile.
// Local development without an import intentionally starts with an empty inbox.
const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
const inbox=read('northline.imports.v1',{records:[]});
const records=Array.isArray(inbox.records)?inbox.records:[];
const saved=read('northline.reviews.v1',{});
const prefs=read('northline.views.v1',{});
let selected=records.find(r=>r.id===prefs.selected)||records[0],page='tour',moving=false,draft=null,source=null,generation=0;
const root=document.querySelector('#app');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>Number(n).toFixed(2);
const button=(name,classes='')=>`<button class="${classes}" type="button">${esc(name)}</button>`;
const on=(name,fn)=>[...root.querySelectorAll('button')].find(b=>b.textContent===name)?.addEventListener('click',fn);
const view=()=>prefs[selected.id]||{...selected.initialView};
const committed=()=>saved[selected.id]||selected.review;
function storePrefs(v){prefs[selected.id]=v;prefs.selected=selected.id;localStorage.setItem('northline.views.v1',JSON.stringify(prefs));}
function go(destination){page=destination;moving=false;render();window.scrollTo(0,0);}
function updateReadout(){
  const r=committed(),out=root.querySelector('[aria-label="Saved review record"]');
  if(out)out.innerHTML=`<h2>Saved review record</h2><p><strong>${esc(r.label)}</strong></p><p>Azimuth: <span>${fmt(r.azimuth)}</span>° · Elevation: <span>${fmt(r.elevation)}</span>°</p>`;
}
function paint(){
  if(page!=='tour'||!source)return;
  const canvas=root.querySelector('canvas');renderWindow(canvas,source,view());
  const point=project(reviewToPanorama(draft,selected.capture),view(),canvas.width,canvas.height);
  const marker=root.querySelector('.hotspot');marker.hidden=!point;
  if(point){marker.style.left=`${point.x/canvas.width*100}%`;marker.style.top=`${point.y/canvas.height*100}%`;}
  marker.setAttribute('aria-label',`Review hotspot: ${draft.label}`);
  root.querySelector('.note').textContent=moving?'Tap the panorama to move this review.':point?'Review ring • saved positions stay on the scene':'Review is outside this view. Change heading to look around.';
}
async function render(){
  const ticket=++generation;
  if(!selected){root.innerHTML='<section class="empty"><h1>No imported tours</h1><p>This app receives panorama attachments from a provider inbox.</p><p>The prepared review runtime supplies the imports. This source-only preview has no sample records.</p></section>';return;}
  root.innerHTML='';
  if(page==='tour'){
    if(!draft)draft={...committed()};
    root.innerHTML=`<nav class="scenes" aria-label="Tour scenes">${records.map(r=>`<button type="button" data-scene="${esc(r.id)}" aria-pressed="${r.id===selected.id}">${esc(r.title)}</button>`).join('')}</nav><h1>${esc(selected.title)}</h1><p class="muted">Imported panorama · one review per scene</p><nav class="tools">${button('Original panorama')}${button('Capture guide')}</nav><div class="viewer" role="group" aria-label="Panorama tour window"><canvas width="368" height="230" role="img" aria-label="Projected original panorama"></canvas><span class="hotspot" role="img" aria-label="Review hotspot" hidden></span></div><p class="note"></p><div class="view-inputs"><label>Heading (°)<input id="heading" type="number" step="any" value="${view().heading}"></label><label>Elevation (°)<input id="elevation" type="number" step="any" min="-65" max="65" value="${view().elevation}"></label>${button('Set view')}</div><p class="muted">Panorama frame · perspective 72° wide · headings wrap</p><div class="row edit-row">${button('Move hotspot')}${button('Save review','primary')}</div><label class="review-label">Review label<input id="review-label" maxlength="80" value="${esc(draft.label)}"></label><p class="status" role="status">Ready</p><section class="saved" aria-label="Saved review record"></section>`;
    for(const b of root.querySelectorAll('[data-scene]'))b.onclick=()=>{selected=records.find(r=>r.id===b.dataset.scene);draft={...committed()};source=null;storePrefs(view());go('tour');};
    on('Original panorama',()=>go('original'));on('Capture guide',()=>go('guide'));
    on('Set view',()=>{
      const h=Number(root.querySelector('#heading').value),p=Number(root.querySelector('#elevation').value);
      if(!Number.isFinite(h)||!Number.isFinite(p))return;
      storePrefs({heading:h,elevation:Math.max(-65,Math.min(65,p))});paint();
    });
    on('Move hotspot',()=>{moving=!moving;const b=[...root.querySelectorAll('button')].find(b=>b.textContent==='Move hotspot');b.setAttribute('aria-pressed',String(moving));paint();});
    root.querySelector('.viewer').onclick=event=>{
      if(!moving||!source)return;
      const canvas=root.querySelector('canvas'),box=canvas.getBoundingClientRect();
      const point=unproject((event.clientX-box.left)*canvas.width/box.width,(event.clientY-box.top)*canvas.height/box.height,view(),canvas.width,canvas.height);
      draft={...draft,...panoramaToReview(point,selected.capture)};moving=false;
      [...root.querySelectorAll('button')].find(b=>b.textContent==='Move hotspot').setAttribute('aria-pressed','false');
      root.querySelector('.status').textContent='Position changed · Save review to keep';paint();
    };
    root.querySelector('#review-label').oninput=e=>{draft.label=e.target.value;root.querySelector('.status').textContent='Unsaved review';};
    on('Save review',()=>{saved[selected.id]={...draft};localStorage.setItem('northline.reviews.v1',JSON.stringify(saved));root.querySelector('.status').textContent='Review saved';updateReadout();paint();});
    updateReadout();
    try{const loaded=await loadPanorama(selected);if(ticket===generation){source=loaded;paint();}}catch(e){if(ticket===generation)root.querySelector('.note').textContent=e.message;}
  }else if(page==='guide'){
    // Generic attachment viewer: all guide contents and field labels come from the import.
    const g=selected.guide;
    root.innerHTML=`${button('Back to tour','back')}<h1>Capture guide</h1><p>${esc(selected.title)}</p><h2>${esc(g.title)}</h2><table aria-label="Capture orientation record"><tbody>${Object.entries(selected.capture).map(([key,value])=>`<tr><th>${esc(g.fieldLabels?.[key]||key)}</th><td>${esc(value)}</td></tr>`).join('')}</tbody></table><section class="axes">${g.axes.map(t=>`<p>${esc(t)}</p>`).join('')}</section><section class="guide">${g.paragraphs.map(t=>`<p>${esc(t)}</p>`).join('')}</section><p class="muted">${esc(selected.provenance)}</p>`;
    on('Back to tour',()=>go('tour'));
  }else{
    root.innerHTML=`${button('Back to tour','back')}<h1>Original panorama</h1><p class="muted">Read-only imported attachment · ${esc(selected.title)}</p><img class="overview" alt="Complete original panorama" src="${esc(selected.panorama.dataUrl)}"><p class="muted">Whole 360° panorama • same seam at both edges</p><h2>Registration magnifier</h2><canvas class="original-strip" width="368" height="220" role="img" aria-label="Original panorama registration strip"></canvas><div class="view-inputs"><label>Original strip heading<input id="strip-heading" type="number" step="any" value="${wrap(view().heading)}"></label><span></span>${button('Show strip')}</div><p class="muted">92° wide, ±27.5° latitude · original flat grid, wraps at seam</p><table aria-label="Original landmark registration"><thead><tr><th>Medallion</th><th>Yaw</th><th>Latitude</th></tr></thead><tbody>${selected.landmarks.map(l=>`<tr><td>${esc(l.name)}</td><td>${esc(l.panoramaYaw)}°</td><td>${esc(l.panoramaLatitude)}°</td></tr>`).join('')}</tbody></table><section class="axes">${selected.guide.axes.map(t=>`<p>${esc(t)}</p>`).join('')}</section><h3>Original review received</h3><p>${esc(selected.review.label)}<br>Azimuth ${esc(selected.review.azimuth)}° · Elevation ${esc(selected.review.elevation)}°</p>`;
    on('Back to tour',()=>go('tour'));
    const show=()=>renderOriginalStrip(root.querySelector('canvas'),source,Number(root.querySelector('#strip-heading').value)||0);
    on('Show strip',()=>{if(source)show();});
    const loaded=await loadPanorama(selected);if(ticket===generation){source=loaded;show();}
  }
}
render();
