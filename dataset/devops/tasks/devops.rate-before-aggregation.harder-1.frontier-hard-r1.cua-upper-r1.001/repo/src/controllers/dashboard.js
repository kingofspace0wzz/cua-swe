import {queryClient} from "../api/queryClient.js";
import {updateState} from "../state/store.js";

function accept(snapshot) {
  updateState({snapshot, error: null});
}

export function acceptInitial(snapshot) {
  accept(snapshot);
}

export async function selectScenario(scenarioId) {
  try { accept(await queryClient.scenario(scenarioId)); }
  catch (error) { updateState({error: error.message}); }
}

export async function selectPanel(panelId) {
  try { accept(await queryClient.panel(panelId)); }
  catch (error) { updateState({error: error.message}); }
}

export async function selectWindow(windowId) {
  try { accept(await queryClient.window(windowId)); }
  catch (error) { updateState({error: error.message}); }
}
