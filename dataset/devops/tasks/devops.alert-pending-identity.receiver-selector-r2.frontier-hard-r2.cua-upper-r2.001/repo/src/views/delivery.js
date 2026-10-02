import {esc} from './format.js';
export function deliveryPanel(s,routing){
 const epoch=s.delivery.epoch||{};
 const declared=(routing||{}).epoch||{};
 const epochPairs=Object.entries(epoch).map(([scope,pairs])=>Object.entries(pairs||{}).map(([key,value])=>`<span data-test="routing-epoch-pair"><span data-test="epoch-scope">${esc(scope)}</span>[<span data-test="epoch-policy">${esc((declared[scope]||{}).policy||'—')}</span>] <span data-test="epoch-key">${esc(key)}</span>=<span data-test="epoch-value">${esc(value)}</span></span>`).join(", ")).filter(x=>x).join(" · ");
 return `<div class="delivery"><b>Receiver</b> ${esc(s.delivery.receiver)} <span data-test="receiver-selector">match ${Object.entries(s.delivery.match||{}).map(([key,value])=>`<span data-test="receiver-selector-pair"><span data-test="selector-key">${esc(key)}</span>=<span data-test="selector-value">${esc(value)}</span></span>`).join(", ")}</span> <span data-test="routing-epoch">routing epoch ${epochPairs}</span> <span>transport ${esc(s.delivery.transport)}</span><span data-test="firing">firing ${s.delivery.firing}</span><span data-test="delivered">delivered ${s.delivery.delivered}</span><span data-test="unrouted">unrouted ${s.delivery.unrouted}</span></div>`;
}
