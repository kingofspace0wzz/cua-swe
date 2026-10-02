import { escapeHtml } from "./components.js";
export function renderControls({ catalog, snapshot }) {
  const scenario = document.querySelector("#scenario");
  scenario.innerHTML = catalog.scenarios.map(item => `<button data-scenario="${item.id}" aria-pressed="${item.id === snapshot.scenarioId}">${escapeHtml(item.label)}</button>`).join("");
  document.querySelector("#bucket").value = snapshot.filter.bucket;
  document.querySelector("#decision").value = snapshot.filter.decision;
  const probe = document.querySelector("#probe");
  if (!probe.options.length) catalog.probes.forEach(item => probe.add(new Option(item.label, item.id)));
  document.querySelector("#replay").disabled = !snapshot.canReplay;
}
