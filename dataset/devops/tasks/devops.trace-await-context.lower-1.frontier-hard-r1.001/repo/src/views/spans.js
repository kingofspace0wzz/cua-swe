import { clear, element } from "./components.js";

export function renderSpans(snapshot) {
  const host = clear(document.querySelector('[data-test="spans"]'));
  for (const span of snapshot.spans) {
    const card = element("article", "span-card");
    card.dataset.test = `span-${span.id}`;
    card.append(
      element("strong", "", span.name),
      element(
        "span",
        "",
        `${span.operationLabel} · ${span.kind}`,
      ),
      element(
        "code",
        "",
        `trace=${span.traceId} span=${span.id} parent=${span.parentId || "none"}`,
      ),
    );
    host.append(card);
  }
}
