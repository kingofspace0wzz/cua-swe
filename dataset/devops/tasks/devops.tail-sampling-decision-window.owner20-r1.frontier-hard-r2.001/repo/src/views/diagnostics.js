import { escapeHtml } from "./components.js";
export function renderDiagnostics(snapshot) {
  const d = snapshot.diagnostics;
  const holder = document.querySelector("#diagnostics");
  if (!holder.querySelector("img.levels-panel")) holder.innerHTML = `<img class="levels-panel" src="/api/service-levels" alt="Receiver-published collector policy profiles and service levels"><dl class="plan-echo"></dl><p class="muted">The receiver publishes its policy profiles above; the active profile applies to every window, probe, and replay. Deployed collector plan below.</p>`;
  holder.querySelector("dl.plan-echo").innerHTML = `<dt>Collector decision wait</dt><dd>${d.waitMs} ms</dd><dt>Probability baseline</dt><dd>${d.probabilityPercentage}%</dd><dt>Deployed policies</dt><dd>${d.policyCount}</dd>`;
  document.querySelector("#probe-result").innerHTML = snapshot.probeResult ? `<strong>${snapshot.probeResult.sampled ? "Would sample" : "Would drop"}</strong><span>${escapeHtml(snapshot.probeResult.reasons.join(", ") || "no policy matched")}</span>` : "<p>No probe evaluated yet.</p>";
}
