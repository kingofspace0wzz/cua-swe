import {
  nextScenario,
  startScenarios,
} from "./controllers/scenarios.js";
import {
  getState,
  subscribe,
  update,
} from "./state/store.js";
import { renderCompatibility } from "./views/compatibility.js";
import { renderInstrumentation } from "./views/instrumentation.js";
import { renderSpans } from "./views/spans.js";
import { renderSummary } from "./views/summary.js";
import { renderTransitions } from "./views/transitions.js";
import { renderWaterfall } from "./views/waterfall.js";

const app = document.querySelector("#app");
const advanceButton = document.querySelector('[data-test="advance"]');
const errorMessage = document.querySelector('[data-test="error"]');

async function boot() {
  try {
    const initialState = await startScenarios();
    update({
      ...initialState,
      busy: false,
    });
    app.dataset.ready = "yes";
    app.setAttribute("aria-busy", "false");
  } catch (error) {
    update({
      busy: false,
      error: String(error.message || error),
    });
  }
}

subscribe((state) => {
  advanceButton.disabled = state.busy || Boolean(state.snapshot?.atEnd);
  errorMessage.textContent = state.error;
  if (!state.snapshot) return;

  renderSummary(state);
  renderCompatibility(state.snapshot);
  renderWaterfall(state.snapshot);
  renderSpans(state.snapshot);
  renderTransitions(state.snapshot);
  renderInstrumentation(state.snapshot);
});

advanceButton.addEventListener("click", async () => {
  if (getState().busy) return;
  update({
    busy: true,
    error: "",
  });
  try {
    const snapshot = await nextScenario();
    update({
      snapshot,
      busy: false,
    });
  } catch (error) {
    update({
      busy: false,
      error: String(error.message || error),
    });
  }
});

boot();
