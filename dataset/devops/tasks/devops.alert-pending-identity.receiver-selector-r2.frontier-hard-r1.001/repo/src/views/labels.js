import {esc,pairs} from './format.js';
export function labelPanel(s){
 const prev=s.timeline.at(-2)?.labels||{},cur=s.timeline.at(-1)?.labels||{};
 const keys=[...new Set([...Object.keys(prev),...Object.keys(cur)])].sort();
 return `<section><h2>Alert labels — previous / current evaluation</h2><table data-test="labels"><thead><tr><th>Label</th><th>Previous</th><th>Current</th></tr></thead><tbody>${keys.map(k=>`<tr class="${prev[k]===cur[k]?'':'changed'}"><td>${esc(k)}</td><td>${esc(prev[k]??'—')}</td><td>${esc(cur[k]??'—')}</td></tr>`).join('')}</tbody></table><h3>Annotations</h3><div data-test="annotations">${pairs(s.timeline.at(-1)?.annotations||{})}</div></section>`;
}
