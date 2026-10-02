const listeners = new Set();

const state = {
  catalog: null,
  policy: null,
  rule: null,
  snapshot: null,
  busy: false,
  error: "",
};

export function getState() {
  return { ...state };
}

export function update(patch) {
  Object.assign(state, patch);
  for (const listener of listeners) {
    listener(getState());
  }
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(getState());
  return () => listeners.delete(listener);
}
