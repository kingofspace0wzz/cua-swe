const state = {catalog: null, snapshot: null, error: null};
const listeners = new Set();

export function updateState(patch) {
  Object.assign(state, patch);
  for (const listener of listeners) listener(state);
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
