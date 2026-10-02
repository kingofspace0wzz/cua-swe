import { evaluateTrace, startQuery } from "./controllers/query.js";
import { initCalibrationBoard } from "./views/calibrationBoard.js";
import { getState, subscribe, update } from "./state/store.js";
import { renderDetail, renderSkewComparison } from "./views/detail.js";
import { renderHosts } from "./views/hosts.js";
import { renderHostChain } from "./views/hostChain.js";
import { renderSummary } from "./views/summary.js";
import { renderWarnings } from "./views/warnings.js";
import { renderWaterfall } from "./views/waterfall.js";

document.querySelector('[data-test="operator-guide"]').src =
  document.querySelector('[data-test="operator-guide"]').dataset.guideSource;
initCalibrationBoard();

async function boot() {
  try {
    const started = await startQuery();
    const second = await evaluateTrace(started.catalog, started.catalog.traces[1].id);
    update({
      ...started,
      comparisons: [
        { trace: started.trace, adjusted: started.adjusted },
        { trace: second.trace, adjusted: second.adjusted },
      ],
      busy: false,
    });
    const picker = document.querySelector('[data-test="trace-select"]');
    for (const trace of started.catalog.traces) {
      const option = document.createElement("option");
      option.value = trace.id;
      option.textContent = `${trace.id} — ${trace.title}`;
      picker.append(option);
    }
    picker.value = started.trace.id;
    document.querySelector("#app").dataset.ready = "yes";
    document.querySelector("#app").setAttribute("aria-busy", "false");
  } catch (error) {
    update({ busy: false, error: String(error.message || error) });
  }
}

subscribe((state) => {
  document.querySelector('[data-test="trace-select"]').disabled = state.busy;
  document.querySelector('[data-test="error"]').textContent = state.error;
  if (!state.trace || !state.adjusted) return;
  renderSummary(state);
  renderSkewComparison(state.comparisons || []);
  renderHostChain(state.trace.spans, state.adjusted);
  renderWaterfall(state.trace, state.adjusted, state.annotations);
  renderDetail(state.trace.spans, state.adjusted);
  renderHosts(state.trace, state.adjusted);
  renderWarnings(state.trace, state.adjusted);
});

document.querySelector('[data-test="trace-select"]').addEventListener("change", async (event) => {
  if (getState().busy) return;
  update({ busy: true, error: "" });
  try {
    update({ ...(await evaluateTrace(getState().catalog, event.target.value)), busy: false });
  } catch (error) {
    update({ busy: false, error: String(error.message || error) });
  }
});

boot();
