import { sloClient } from "../api/sloClient.js";
import { compileSloPlan } from "../config/compileSloPlan.js";
import { SLO_ROLLUPS } from "../config/sloDefinition.js";
import { store } from "../state/store.js";
const refresh = async () => store.set({ snapshot: await sloClient.snapshot() });
export async function initialize() {
  const catalog = await sloClient.catalog();
  await sloClient.configure(compileSloPlan(SLO_ROLLUPS));
  store.set({ catalog });
  await sloClient.scenario(catalog.scenarios[0].id);
  await refresh();
}
export async function chooseScenario(id) { await sloClient.scenario(id); await refresh(); }
export async function chooseWindow(id) { await sloClient.window(id); await refresh(); }
export async function chooseSlice(id) { await sloClient.select(id); await refresh(); }
export async function setFilter(verdict) { await sloClient.filter(verdict); await refresh(); }
export async function runProbe(id) { await sloClient.probe(id); await refresh(); }
export async function replay() { await sloClient.replay(); await refresh(); }
