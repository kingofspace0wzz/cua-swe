import { countOutside } from "./waterfall.js";

export function renderSummary(state) {
  const { catalog, trace, adjusted, annotations } = state;
  document.querySelector('[data-test="profile"]').textContent = catalog.label;
  document.querySelector('[data-test="trace-title"]').textContent = trace.title;
  document.querySelector('[data-test="trace-id"]').textContent = trace.id;
  document.querySelector('[data-test="span-count"]').textContent = String(adjusted.length);
  document.querySelector('[data-test="outside-count"]').textContent = String(countOutside(adjusted));
  document.querySelector('[data-test="adjusted-count"]').textContent =
    String(new Set(annotations.map((item) => item.spanId)).size);
  document.querySelector('[data-test="host-count"]').textContent =
    String(new Set(trace.spans.map((span) => span.host)).size);
}
