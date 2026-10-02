export function renderSummary(state) {
  if (!state.snapshot || !state.catalog) return;
  const { snapshot, catalog } = state;
  const unscopedHeld = snapshot.alerts.filter(
    (alert) => alert.status === "suppressed" && alert.scopeState !== "present",
  ).length;

  document.querySelector('[data-test="profile"]').textContent = catalog.label;
  document.querySelector('[data-test="incident"]').textContent =
    snapshot.incident.label;
  document.querySelector('[data-test="alert-count"]').textContent =
    String(snapshot.alerts.length);
  document.querySelector('[data-test="firing-count"]').textContent =
    String(snapshot.firing.length);
  document.querySelector('[data-test="suppressed-count"]').textContent =
    String(snapshot.suppressed.length);
  document.querySelector('[data-test="unscoped-count"]').textContent =
    String(unscopedHeld);
  document.querySelector('[data-test="scope-summary"]').textContent =
    `equal on ${catalog.equalDimensions.join(", ")}`;
  document.querySelector('[data-test="edge-count"]').textContent =
    `${snapshot.edges.length} edges`;
}
