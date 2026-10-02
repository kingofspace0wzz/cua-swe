import { renderBreakdowns } from "./breakdowns.js";
import { renderControls } from "./controls.js";
import { renderDetail } from "./detail.js";
import { renderDiagnostics } from "./diagnostics.js";
import { renderSlices } from "./slices.js";
import { renderSummary } from "./summary.js";
import { renderTotals } from "./totals.js";
export function render(state) {
  if (!state.catalog || !state.snapshot) return;
  renderControls(state);
  renderSummary(state.snapshot);
  renderTotals(state.snapshot);
  renderDiagnostics(state.snapshot);
  renderSlices(state.snapshot);
  renderDetail(state.snapshot);
  renderBreakdowns(state.snapshot);
  document.querySelector("[data-testid=app]").dataset.ready = "yes";
}
