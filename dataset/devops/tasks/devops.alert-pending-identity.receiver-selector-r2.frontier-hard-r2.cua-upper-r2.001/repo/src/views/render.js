import {esc,clock} from './format.js';
import {seriesPanel} from './series.js';
import {timelinePanel} from './timeline.js';
import {labelPanel} from './labels.js';
import {runbookPanel} from './runbook.js';
import {routesPanel} from './routes.js';
import {deliveryPanel} from './delivery.js';
export function render(store){
 const s=store.snapshot,c=store.catalog;
 document.querySelector('#app').innerHTML=`<header><div><div class="eyebrow">OPERATIONS / RULE EVALUATION</div><h1>Alert operations</h1></div><div class="capture">Capture time <b data-test="time">${clock(s.time)}</b><br>${esc(s.rule.name)}</div></header>
 <nav>${c.scenarios.map(x=>`<button data-action="scenario" data-value="${esc(x.id)}" class="${x.id===s.scenario?'selected':''}">${esc(x.label)}</button>`).join('')}<div class="spacer"></div><button data-action="advance">Next evaluation</button><button data-action="replay">Replay capture</button><button data-action="reset">Reset</button></nav>
 <div class="targets">${s.targets.map(x=>`<button data-action="target" data-value="${esc(x.id)}" class="${x.id===s.target.id?'selected':''}">${esc(x.service)} / ${esc(x.instance)}</button>`).join('')}</div>
 <div class="tabs"><button data-action="view" data-value="series" class="${store.view==='series'?'selected':''}">Series & timeline</button><button data-action="view" data-value="labels" class="${store.view==='labels'?'selected':''}">Labels & detail</button><button data-action="view" data-value="runbook" class="${store.view==='runbook'?'selected':''}">Routing runbook</button><span>Rule ${esc(s.rule.name)} · revision ${esc(s.rule.revision)} · last evaluation OK</span></div>
 <div class="grid">${store.view==='series'?seriesPanel(s):store.view==='labels'?labelPanel(s):runbookPanel()}${timelinePanel(s)}</div>${routesPanel(s)}${deliveryPanel(s,c.routing)}`;
 document.querySelector('#app').dataset.ready='yes';
}
