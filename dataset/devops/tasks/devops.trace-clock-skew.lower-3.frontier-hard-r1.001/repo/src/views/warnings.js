import { byId, clear, element } from "./components.js";

export function renderWarnings(trace, spans) {
  const host = clear(document.querySelector('[data-test="warnings"]'));
  for (const advisory of trace.advisories || []) {
    host.append(element("li", "advisory", advisory));
  }
  const index = byId(spans);
  const problems = spans.filter((span) => {
    const parent = span.parentId === null ? null : index.get(span.parentId);
    return parent && (span.startMs < parent.startMs || span.endMs > parent.endMs);
  });
  if (!problems.length) {
    host.append(element("li", "ok", "No parent-boundary warnings."));
    return;
  }
  for (const span of problems) {
    const parent = index.get(span.parentId);
    host.append(element(
      "li",
      "",
      `${span.operation} on ${span.host} is outside ${parent.operation} on ${parent.host}`,
    ));
  }
}
