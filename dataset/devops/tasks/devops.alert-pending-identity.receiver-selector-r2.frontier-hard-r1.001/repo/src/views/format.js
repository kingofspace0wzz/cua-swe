export function esc(value){return String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
export function clock(t){return `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`;}
export function pairs(obj){return Object.entries(obj).map(([k,v])=>`<div class="pair"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join('');}
