import { chooseScenario, chooseSlice, chooseWindow, initialize, publishSchedule, replay, runProbe, setFilter } from "./controllers/console.js";
import { store } from "./state/store.js";
import { render } from "./views/render.js";
const fail = (error) => { document.querySelector("#error").textContent = error.message; };
store.subscribe(render);
document.querySelector("#scenario").addEventListener("change", (event) => chooseScenario(event.target.value).catch(fail));
document.querySelector("#window").addEventListener("change", (event) => chooseWindow(event.target.value).catch(fail));
document.querySelector("#verdict-filter").addEventListener("change", (event) => setFilter(event.target.value).catch(fail));
document.querySelector("#run-probe").addEventListener("click", () => runProbe(document.querySelector("#probe").value).catch(fail));
document.querySelector("#replay").addEventListener("click", () => replay().catch(fail));
document.querySelector("#slices").addEventListener("click", (event) => {
  const row = event.target.closest("[data-slice-id]");
  if (row) chooseSlice(row.dataset.sliceId).catch(fail);
});
initialize().then(() => publishSchedule()).catch(fail);
