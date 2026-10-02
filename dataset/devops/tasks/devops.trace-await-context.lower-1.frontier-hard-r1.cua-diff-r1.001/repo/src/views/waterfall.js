import { clear, element } from "./components.js";

export function renderWaterfall(snapshot) {
  const host = clear(
    document.querySelector('[data-test="waterfall"]'),
  );
  for (const trace of snapshot.traces) {
    const group = element("section", "trace-group");
    group.dataset.test = `trace-${trace.traceId}`;
    group.append(
      element(
        "strong",
        "",
        `${trace.traceId} · ${trace.spans.length} spans`,
      ),
    );
    for (const span of trace.spans) {
      const row = element("div", "span-row");
      row.dataset.test = `waterfall-${span.id}`;
      row.dataset.root = String(!span.parentId);
      row.style.marginLeft = `${span.depth * 22}px`;
      row.append(
        element("strong", "", span.name),
        element("span", "", span.kind),
        element(
          "span",
          "",
          span.parentId ? `parent ${span.parentId}` : "no parent",
        ),
      );
      group.append(row);
    }
    host.append(group);
  }
}
