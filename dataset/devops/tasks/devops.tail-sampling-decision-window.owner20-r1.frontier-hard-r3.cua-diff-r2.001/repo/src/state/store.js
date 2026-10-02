let state = { catalog: null, snapshot: null };
const listeners = new Set();

export const store = {
  get: () => state,
  set: (change) => {
    state = { ...state, ...change };
    listeners.forEach((listener) => listener(state));
  },
  subscribe: (listener) => {
    listeners.add(listener);
    listener(state);
    return () => listeners.delete(listener);
  },
};
