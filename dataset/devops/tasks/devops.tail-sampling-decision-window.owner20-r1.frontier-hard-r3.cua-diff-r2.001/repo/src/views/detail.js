import { escapeHtml } from "./components.js";
export function renderDetail(snapshot) {
  const trace = snapshot.selected;
  document.querySelector("#detail").innerHTML = trace ? `
    <div class="selected-heading"><strong>${escapeHtml(trace.service)}</strong><code>${escapeHtml(trace.id)}</code></div>
    <dl><dt>Pipeline</dt><dd>${escapeHtml(trace.pipeline)}</dd><dt>Decision</dt><dd class="${trace.sampled ? "keep" : "drop"}">${trace.sampled ? "sampled" : "dropped"}</dd><dt>Matching policies</dt><dd>${escapeHtml(trace.reasons.join(", ") || "none")}</dd><dt>Decision after first receipt</dt><dd>+${trace.decisionAtMs - trace.firstArrivalMs} ms</dd><dt>Last span after first receipt</dt><dd>+${trace.completedAtMs - trace.firstArrivalMs} ms</dd></dl>
    <h3>Received spans</h3><ol class="spans">${trace.spans.map(span => `<li><strong>${escapeHtml(span.name)}</strong><span class="${span.status === "ERROR" ? "drop" : ""}">${escapeHtml(span.status)}</span><small>receipt +${span.arrivalMs - trace.firstArrivalMs} ms · duration ${span.endMs - span.startMs} ms</small></li>`).join("")}</ol>
    <h3>Collector decision log</h3><p class="decision-log">At +${trace.decisionAtMs - trace.firstArrivalMs} ms: ${trace.visibleSpanCount} of ${trace.spanCount} received spans available. ${trace.sampled ? "Keep decision cached; spans delivered to trace store." : "Drop decision cached; no trace-store export."}</p>` : "<p>Select a trace.</p>";
}
