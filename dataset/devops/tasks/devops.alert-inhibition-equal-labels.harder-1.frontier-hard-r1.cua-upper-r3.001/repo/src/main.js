import {
  nextIncident,
  startIncidents,
} from "./controllers/incidents.js";
import {
  getState,
  subscribe,
  update,
} from "./state/store.js";
import { renderAdvisories } from "./views/advisories.js";
import { renderComparisons } from "./views/comparisons.js";
import { renderDimensions } from "./views/dimensions.js";
import { renderGraph } from "./views/graph.js";
import { renderQueues } from "./views/queues.js";
import { renderRoutes } from "./views/routes.js";
import { renderRule } from "./views/rule.js";
import { renderRunbook } from "./views/runbook.js";
import { renderSummary } from "./views/summary.js";

const app = document.querySelector("#app");
const advanceButton = document.querySelector('[data-test="advance"]');
const errorMessage = document.querySelector('[data-test="error"]');

async function boot() {
  try {
    const initial = await startIncidents();
    update({ ...initial, busy: false });
    app.dataset.ready = "yes";
    app.setAttribute("aria-busy", "false");
  } catch (error) {
    update({ busy: false, error: String(error.message || error) });
  }
}

subscribe((state) => {
  advanceButton.disabled = state.busy || Boolean(state.snapshot?.atEnd);
  errorMessage.textContent = state.error;
  if (!state.snapshot) return;
  renderSummary(state);
  renderQueues(state.snapshot);
  renderGraph(state.snapshot);
  renderRoutes(state.snapshot);
  renderComparisons(state.snapshot);
  renderDimensions(state.policy);
  renderAdvisories(state.catalog);
  renderRunbook();
  renderRule(state.rule);
});

advanceButton.addEventListener("click", async () => {
  if (getState().busy) return;
  update({ busy: true, error: "" });
  try {
    update({ snapshot: await nextIncident(), busy: false });
  } catch (error) {
    update({ busy: false, error: String(error.message || error) });
  }
});

boot();
