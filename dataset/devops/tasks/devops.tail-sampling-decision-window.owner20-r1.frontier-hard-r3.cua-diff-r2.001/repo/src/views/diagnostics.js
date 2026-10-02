import { escapeHtml } from "./components.js";
export function renderDiagnostics(snapshot) {
  const d = snapshot.diagnostics;
  document.querySelector("#diagnostics").innerHTML = `<dl><dt>Collector decision wait</dt><dd>${d.waitMs} ms</dd><dt>Tail-decision SLO</dt><dd>${escapeHtml(d.sloRule)}</dd><dt>Probability baseline</dt><dd>${d.probabilityPercentage}%</dd></dl><p class="muted">Times measured from first span receipt. Applies to every window, probe, and replay.</p>`;
  document.querySelector("#probe-result").innerHTML = snapshot.probeResult ? `<strong>${snapshot.probeResult.sampled ? "Would sample" : "Would drop"}</strong><span>${escapeHtml(snapshot.probeResult.reasons.join(", ") || "no policy matched")}</span>` : "<p>No probe evaluated yet.</p>";
}
