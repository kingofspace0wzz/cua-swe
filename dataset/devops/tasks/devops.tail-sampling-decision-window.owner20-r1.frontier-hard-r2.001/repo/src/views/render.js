import { metric } from "./components.js";
import { renderBuckets } from "./buckets.js";
import { renderControls } from "./controls.js";
import { renderDecisions } from "./decisions.js";
import { renderDetail } from "./detail.js";
import { renderDiagnostics } from "./diagnostics.js";
import { renderExports } from "./exports.js";
import { renderTimeline } from "./timeline.js";

export function render(state) {
  if (!state.catalog || !state.snapshot) return;
  const snapshot = state.snapshot;
  renderControls(state);
  document.querySelector("#funnel").innerHTML = [
    metric("Spans received", snapshot.metrics.spansReceived, "spans-count"),
    metric("Traces completed", snapshot.metrics.tracesCompleted, "traces-count"),
    metric("Sampled", snapshot.metrics.sampled, "sampled-count"),
    metric("Dropped", snapshot.metrics.dropped, "dropped-count"),
  ].join("");
  renderBuckets(snapshot);
  renderDiagnostics(snapshot);
  renderDecisions(snapshot);
  renderDetail(snapshot);
  renderTimeline(snapshot);
  renderExports(snapshot);
  document.querySelector("[data-testid=app]").dataset.ready = "yes";
}
