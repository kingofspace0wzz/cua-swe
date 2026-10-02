import { escapeHtml } from "./components.js";
export function renderDiagnostics(snapshot) {
  document.querySelector("#diagnostics").innerHTML = `<dl>
    <dt>Availability rollup</dt><dd>${escapeHtml(snapshot.diagnostics.availabilityMode)}</dd>
    <dt>Budget rollup</dt><dd>${escapeHtml(snapshot.diagnostics.budgetMode)}</dd>
    <dt>Slice count</dt><dd>${snapshot.diagnostics.sliceCount}</dd>
    <dt>Replay count</dt><dd>${snapshot.replayCount}</dd>
  </dl>`;
  document.querySelector("#probe-result").innerHTML = snapshot.probeResult ? `<strong>${snapshot.probeResult.verdict}</strong><span>${(snapshot.probeResult.availability * 100).toFixed(3)}% · ${snapshot.probeResult.budgetConsumed.toFixed(1)}% budget</span>` : "<p>No probe evaluated yet.</p>";
}
