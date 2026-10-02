import { escapeHtml } from "./components.js";
export function renderTimeline(snapshot) {
  document.querySelector("#timeline").innerHTML = snapshot.timeline.map(item => `<div class="timeline-row"><span>${escapeHtml(item.service)}</span><div class="rail"><i style="width:${Math.min(100,(item.completedAtMs-item.firstArrivalMs)/21)}%"></i><b style="left:${Math.min(96,(item.decisionAtMs-item.firstArrivalMs)/21)}%"></b></div><small>last +${item.completedAtMs-item.firstArrivalMs} / decision +${item.decisionAtMs-item.firstArrivalMs}ms</small></div>`).join("");
}
