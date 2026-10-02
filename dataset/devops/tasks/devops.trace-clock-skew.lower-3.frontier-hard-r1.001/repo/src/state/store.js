const listeners = new Set();
const state = {
  catalog: null,
  trace: null,
  adjusted: null,
  annotations: [],
  comparisons: [],
  busy: false,
  error: "",
};

export function getState() {
  return {
    ...state,
    annotations: state.annotations.slice(),
    comparisons: state.comparisons.slice(),
  };
}

export function update(patch) {
  Object.assign(state, patch);
  for (const listener of listeners) listener(getState());
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(getState());
  return () => listeners.delete(listener);
}
