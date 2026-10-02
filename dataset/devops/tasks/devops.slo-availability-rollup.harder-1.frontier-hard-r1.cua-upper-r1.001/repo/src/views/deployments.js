import { escapeHtml, percent } from "./components.js";
export function renderDeployments(snapshot) {
  const rollout = snapshot.rollout;
  document.querySelector("#deployments").innerHTML = rollout ? `<p class="report-date">Report date <strong data-testid="report-date">${escapeHtml(rollout.reportDate)}</strong></p>
    <table><thead><tr><th>Revision</th><th>Record</th>${rollout.scopes.map((scope) => `<th>${escapeHtml(scope.label)}</th>`).join("")}</tr></thead><tbody>
      ${rollout.ledger.map((row) => `<tr data-epoch="${escapeHtml(row.epoch)}"><td>${escapeHtml(row.epoch)}</td><td>${escapeHtml(row.caption)}</td>${row.cells.map((cell) => `<td>${cell.covered ? `${escapeHtml(cell.mode)} · ${escapeHtml(cell.weight)}` : "not covered"}</td>`).join("")}</tr>`).join("")}
    </tbody></table>` : "<p>Awaiting the rollup deployment schedule.</p>";
  document.querySelector("#rollout-views").innerHTML = (rollout ? rollout.views : []).map((view) => `<section class="rollout-view" data-view="${escapeHtml(view.slot)}">
    <h3>${escapeHtml(view.title)} <span>${escapeHtml(view.epoch)}</span></h3>
    <p>${escapeHtml(view.caption)} — ${escapeHtml(view.basis)}</p>
    <dl><dt>Availability</dt><dd>${percent(view.availability)}</dd><dt>Verdict</dt><dd>${view.verdict}</dd>
    <dt>Budget consumed</dt><dd>${view.budgetConsumed.toFixed(1)}%</dd><dt>Budget remaining</dt><dd>${view.budgetRemaining.toFixed(1)}%</dd></dl>
  </section>`).join("");
}
