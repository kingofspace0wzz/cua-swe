import {esc,clock} from './format.js';
export function seriesPanel(s){
 const q=s.rule.query, values=s.series;
 const top=Math.max(q.threshold*1.3,...values.map(x=>x.value));
 const xx=i=>40+i*560/Math.max(1,values.length-1), yy=v=>155-v*125/top;
 const line=values.map((x,i)=>`${xx(i)},${yy(x.value)}`).join(' ');
 return `<section><h2>Query series <small>${esc(q.metric)}</small></h2>
 <div class="context">${esc(s.target.service)} / ${esc(s.target.instance)} · condition ${esc(q.operator)} ${q.threshold} · hold ${s.rule.forSeconds}s</div>
 <svg viewBox="0 0 640 185" aria-label="query series"><line x1="40" x2="600" y1="${yy(q.threshold)}" y2="${yy(q.threshold)}" stroke="#e7ac67" stroke-dasharray="5 5"/><text x="45" y="${yy(q.threshold)-6}">threshold ${q.threshold}</text><polyline points="${line}" fill="none" stroke="#70c6ff" stroke-width="3"/>${values.map((v,i)=>`<circle cx="${xx(i)}" cy="${yy(v.value)}" r="4" fill="#70c6ff"/>`).join('')}<text x="40" y="180">${clock(values[0].t)}</text><text x="560" y="180">${clock(values.at(-1).t)}</text></svg>
 <div class="samples">${values.map(x=>`<span>${clock(x.t)}<b>${x.value}</b></span>`).join('')}</div>
 <p class="muted">Evaluation interval ${s.interval}s · ${s.gaps} missing samples · evaluator generation ${s.generation}</p></section>`;
}
