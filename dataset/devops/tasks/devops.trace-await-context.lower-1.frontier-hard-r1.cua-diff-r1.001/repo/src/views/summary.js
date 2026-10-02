export function renderSummary(state) {
  if (!state.snapshot || !state.catalog) return;

  const {
    snapshot,
    runtime,
    catalog,
  } = state;
  const orphanCount = snapshot.spans.filter(
    (span) => span.kind !== "operation" && !span.parentId,
  ).length;

  document.querySelector('[data-test="profile"]').textContent = catalog.label;
  document.querySelector('[data-test="scenario"]').textContent =
    snapshot.scenario.label;
  document.querySelector('[data-test="operation-count"]').textContent =
    String(snapshot.operations.length);
  document.querySelector('[data-test="trace-count"]').textContent =
    String(snapshot.traces.length);
  document.querySelector('[data-test="span-count"]').textContent =
    String(snapshot.spans.length);
  document.querySelector('[data-test="orphan-count"]').textContent =
    String(orphanCount);
  document.querySelector('[data-test="runtime-summary"]').textContent =
    `${runtime.context_manager} · ${runtime.async_semantics}`;
  document.querySelector('[data-test="scenario-clock"]').textContent =
    snapshot.scenario.clock;
}
