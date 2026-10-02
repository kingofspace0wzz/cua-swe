import {
  chooseScenario,
  chooseTrace,
  initialize,
  replay,
  runProbe,
  setBucket,
  setDecision,
} from "./controllers/console.js";
import { store } from "./state/store.js";
import { render } from "./views/render.js";

const fail = (error) => {
  document.querySelector("#error").textContent = error.message;
};

store.subscribe(render);
document.querySelector("#scenario").addEventListener("click", (event) => {
  const button = event.target.closest("[data-scenario]");
  if (button) chooseScenario(button.dataset.scenario).catch(fail);
});
document.querySelector("#bucket").addEventListener("change", (event) =>
  setBucket(event.target.value).catch(fail));
document.querySelector("#decision").addEventListener("change", (event) =>
  setDecision(event.target.value).catch(fail));
document.querySelector("#run-probe").addEventListener("click", () =>
  runProbe(document.querySelector("#probe").value).catch(fail));
document.querySelector("#replay").addEventListener("click", () =>
  replay().catch(fail));
document.querySelector("#decisions").addEventListener("click", (event) => {
  const row = event.target.closest("[data-trace-id]");
  if (row) chooseTrace(row.dataset.traceId).catch(fail);
});
initialize().catch(fail);
