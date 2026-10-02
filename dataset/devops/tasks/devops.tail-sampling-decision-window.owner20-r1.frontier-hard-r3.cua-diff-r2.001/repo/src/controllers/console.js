import { samplerClient } from "../api/samplerClient.js";
import { compilePolicyPlan } from "../config/compilePolicyPlan.js";
import { COLLECTOR_SETTINGS } from "../config/collectorSettings.js";
import { store } from "../state/store.js";

const refresh = async () => store.set({ snapshot: await samplerClient.snapshot() });

export async function initialize() {
  const catalog = await samplerClient.catalog();
  await samplerClient.configure(
    compilePolicyPlan(COLLECTOR_SETTINGS),
  );
  store.set({ catalog });
  await samplerClient.scenario(catalog.scenarios[0].id);
  await refresh();
}

export async function chooseScenario(id) {
  await samplerClient.scenario(id);
  await refresh();
}
export async function chooseTrace(id) {
  await samplerClient.select(id);
  await refresh();
}
export async function setBucket(value) {
  await samplerClient.bucket(value);
  await refresh();
}
export async function setDecision(value) {
  await samplerClient.decision(value);
  await refresh();
}
export async function runProbe(id) {
  await samplerClient.probe(id);
  await refresh();
}
export async function replay() {
  await samplerClient.replay();
  await refresh();
}
