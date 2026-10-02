import { clear, element } from "./components.js";

export function renderGraph(snapshot) {
  const host = clear(document.querySelector('[data-test="graph"]'));
  if (!snapshot.edges.length) {
    host.append(element("p", "empty", "No active inhibition edges"));
    return;
  }
  for (const edge of snapshot.edges) {
    const row = element("article", "edge");
    row.dataset.test = `edge-${edge.targetId}`;
    row.append(
      element("strong", "", edge.sourceName),
      element("span", "arrow", "→ inhibits →"),
      element("strong", "", edge.targetName),
      element("small", "", edge.reason),
    );
    host.append(row);
  }
}
