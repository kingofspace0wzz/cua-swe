// Ordinary generic attachment viewer. It interprets document presentation fields,
// never provider calibration semantics. Attachments remain reachable if plan import fails.
const E=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
export function documentViewer(host,attachments) {
  let chosen=0,pageIndex=0;
  function draw() {
    host.replaceChildren();const tabs=E('div');tabs.className='attachment-tabs';
    attachments.forEach((a,i)=>{const b=E('button',a.title);b.className=i===chosen?'active':'';b.onclick=()=>{chosen=i;pageIndex=0;draw();};tabs.append(b);});host.append(tabs);
    const a=attachments[chosen],section=E('section');section.className='document';section.append(E('h2',a.title));
    if(a.pages) {
      const p=a.pages[pageIndex];section.append(E('p',`Page ${pageIndex+1} of ${a.pages.length}`),E('h3',p.title));
      if(p.text)section.append(E('p',p.text));
      if(p.table){const t=E('table'),tr=E('tr');for(const col of p.table.columns)tr.append(E('th',col));t.append(tr);for(const row of p.table.rows){const r=E('tr');for(const value of row)r.append(E('td',String(value)));t.append(r);}section.append(t);}
      const nav=E('nav');for(const [label,delta] of [['Previous page',-1],['Next page',1]]){const b=E('button',label);b.disabled=pageIndex+delta<0||pageIndex+delta>=a.pages.length;b.onclick=()=>{pageIndex+=delta;draw();host.scrollIntoView({block:'start'});};nav.append(b);}section.append(nav);
    }
    if(a.svg){const img=E('img');img.alt=a.title;img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(a.svg);section.append(img);}
    if(a.caption)section.append(E('p',a.caption));
    if(a.data){const details=E('details'),pre=E('pre');details.append(E('summary','Raw received data'));pre.textContent=JSON.stringify(a.data,null,2);details.append(pre);section.append(details);}
    host.append(section);
  }
  draw();
}
