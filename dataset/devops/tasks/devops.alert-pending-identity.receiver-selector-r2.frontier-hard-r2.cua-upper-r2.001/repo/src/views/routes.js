import {esc} from './format.js';
export function routesPanel(s){
 const rows=(s.routes||[]).map((route,index)=>`<tr data-test="route-row"><td>${index+1}</td><td data-test="route-name">${esc(route.name)}</td><td data-test="route-family">${esc(route.family)}</td><td data-test="route-selector">${Object.entries(route.match||{}).map(([key,value])=>`${esc(key)}=${esc(value)}`).join(', ')}</td><td data-test="route-delivered">${route.delivered}</td></tr>`).join('');
 return `<section class="routes"><h2>Notification routes <small>first match wins</small></h2><table data-test="routes"><thead><tr><th>Order</th><th>Route</th><th>Family</th><th>Selector</th><th>Delivered</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}
