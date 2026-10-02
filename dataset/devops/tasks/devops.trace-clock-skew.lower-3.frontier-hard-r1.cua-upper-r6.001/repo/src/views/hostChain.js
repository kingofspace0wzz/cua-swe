import { byId, clear, element } from "./components.js";

function depth(span, spans) {
  let current = span;
  let value = 0;
  const seen = new Set();
  while (current?.parentId !== null && !seen.has(current.id)) {
    seen.add(current.id);
    current = spans.get(current.parentId);
    value += 1;
  }
  return value;
}

export function renderHostChain(raw, adjusted) {
  const host = clear(document.querySelector('[data-test="host-chain"]'));
  const spans = byId(raw);
  const displayed = byId(adjusted);
  const edges = raw
    .filter((span) => span.parentId !== null && spans.get(span.parentId)?.host !== span.host)
    .map((span) => ({
      span,
      parent: spans.get(span.parentId),
      displayedSpan: displayed.get(span.id),
      displayedParent: displayed.get(span.parentId),
      depth: depth(span, spans),
    }))
    .sort((left, right) => left.depth - right.depth);
  const heading = element("div", "host-chain-heading");
  heading.append(
    element("strong", "", "Parent-ordered host chain"),
    element("p", "", "Cross-host boundaries in parent order; nested boundaries reference the displayed parent geometry."),
  );
  host.append(heading);
  const steps = element("div", "chain-steps");
  for (const edge of edges) {
    const nested = edge.depth > 1;
    const row = element("div", nested ? "chain-step nested" : "chain-step");
    row.dataset.depth = String(edge.depth);
    row.append(
      element("strong", "", `${edge.parent.host} → ${edge.span.host}`),
      element("span", "chain-order", nested ? "nested · use displayed parent" : "outer boundary"),
      element(
        "small",
        "",
        `parent reported ${edge.parent.startMs} → ${edge.parent.endMs} · displayed ${edge.displayedParent.startMs} → ${edge.displayedParent.endMs}`,
      ),
      element(
        "small",
        "",
        `child reported ${edge.span.startMs} → ${edge.span.endMs} · displayed ${edge.displayedSpan.startMs} → ${edge.displayedSpan.endMs}`,
      ),
    );
    steps.append(row);
  }
  host.append(steps);
}
