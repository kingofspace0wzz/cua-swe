import { escapeHtml } from "./components.js";
export function renderControls({ catalog, snapshot }) {
  document.querySelector("#rollup-options").innerHTML = (catalog.rollupReference || []).map((item) => `<section class="rollup-option">
    <h3>${escapeHtml(item.label)}</h3><p>${escapeHtml(item.description)}</p>
    <dl><dt>Mode</dt><dd>${escapeHtml(item.mode)}</dd><dt>Weight</dt><dd>${escapeHtml(item.weight || "none")}</dd></dl>
  </section>`).join("");
  const agreement = snapshot.reportingAgreement;
  document.querySelector("#agreement-content").innerHTML = agreement ? `<h3>${escapeHtml(agreement.title)}</h3>
    <dl>${agreement.fields.map((field) => `<dt>${escapeHtml(field.label)}</dt><dd>${escapeHtml(field.value)}</dd>`).join("")}</dl>
    <div class="agreement-allocations">${agreement.allocations.map((item) => `<span>${escapeHtml(item.label)} <strong>${escapeHtml(item.value)}</strong></span>`).join("")}</div>` : "";
  const scenario = document.querySelector("#scenario");
  if (!scenario.options.length) catalog.scenarios.forEach((item) => scenario.add(new Option(item.label, item.id)));
  scenario.value = snapshot.scenarioId;
  const window = document.querySelector("#window");
  if (!window.options.length) catalog.windows.forEach((item) => window.add(new Option(item.label, item.id)));
  window.value = snapshot.windowId;
  document.querySelector("#verdict-filter").value = snapshot.filter.verdict;
  const probe = document.querySelector("#probe");
  if (!probe.options.length) catalog.probes.forEach((item) => probe.add(new Option(item.label, item.id)));
  document.querySelector("#replay").disabled = !snapshot.canReplay;
}
