export function applyGauge(state, measurement) {
  const before = state.get(measurement.identity) ?? 0;
  const value = measurement.value;
  state.set(measurement.identity, value);
  return {before, value};
}
