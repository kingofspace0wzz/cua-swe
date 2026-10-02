import { escapeHtml, percent } from "./components.js";
export function renderBreakdowns(snapshot) {
  document.querySelector("#breakdowns").innerHTML = snapshot.breakdowns.map((group) => `<section class="breakdown">
    <h3>${escapeHtml(group.dimension)}</h3>
    ${group.rows.map((row) => `<div><span>${escapeHtml(row.key)}</span><strong>${percent(row.availability)}</strong><small>${row.bad} / ${row.total} bad</small></div>`).join("")}
  </section>`).join("");
}
