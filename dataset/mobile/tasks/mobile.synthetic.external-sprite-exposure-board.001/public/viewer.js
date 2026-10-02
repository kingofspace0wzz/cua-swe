// Generic received attachment viewer: fit, zoom/scroll, and named crop details.
export function openReceived(root,edition,onClose){
 root.innerHTML=`<section id="received"><button class="back">Back to animation</button><h2>Received • ${edition.label}</h2><div class="row" id="attachments"></div><div id="content"></div></section>`;
 root.querySelector('.back').onclick=onClose;
 const tabs=root.querySelector('#attachments'),content=root.querySelector('#content');
 function button(label,fn){const b=document.createElement('button');b.textContent=label;b.onclick=fn;tabs.append(b);}
 function guide(){content.innerHTML='<article id="guide"></article>';const a=content.firstChild;
  for(const [title,body] of edition.guide){const h=document.createElement('h3'),p=document.createElement('p');h.textContent=title;p.textContent=body;a.append(h,p);}}
 button('Guide',guide);edition.sheets.forEach(sheet=>button(sheet.label,()=>show(sheet)));guide();
 function show(sheet){let panel=-1,zoom=1;content.innerHTML=`<h3>${sheet.label}</h3><div class="row"><button id="fit">Fit sheet</button><button id="zoom">Zoom ×2</button><button id="prev">Previous detail</button><button id="next">Next detail</button></div><p id="detail-title"></p><div id="sheet-window"><img id="sheet-image" alt="${sheet.label} received artwork"><canvas id="detail" class="hidden"></canvas></div><p class="muted">Scroll the enlarged sheet in either direction. Or open a labelled detail.</p><div id="panel-list"></div>`;
 const im=content.querySelector('img'),cv=content.querySelector('canvas'),win=content.querySelector('#sheet-window');im.src=sheet.image;
 function fit(){panel=-1;zoom=1;im.classList.remove('hidden');cv.classList.add('hidden');im.style.width='100%';content.querySelector('#detail-title').textContent='Complete received sheet';win.scrollTo(0,0);}
 function detail(n){panel=(n+sheet.panels.length)%sheet.panels.length;const p=sheet.panels[panel];cv.width=p.rect[2]*2;cv.height=p.rect[3]*2;cv.getContext('2d').drawImage(im,...p.rect,0,0,cv.width,cv.height);im.classList.add('hidden');cv.classList.remove('hidden');content.querySelector('#detail-title').textContent=p.label;win.scrollTo(0,0);}
 content.querySelector('#fit').onclick=fit;content.querySelector('#zoom').onclick=()=>{panel=-1;zoom=zoom===1?2:1;im.classList.remove('hidden');cv.classList.add('hidden');im.style.width=(win.clientWidth*zoom)+'px';};
 content.querySelector('#prev').onclick=()=>detail(panel-1);content.querySelector('#next').onclick=()=>detail(panel+1);
 const list=content.querySelector('#panel-list');sheet.panels.forEach((p,i)=>{const b=document.createElement('button');b.textContent=p.label;b.onclick=()=>detail(i);list.append(b);});fit();
 }
}
