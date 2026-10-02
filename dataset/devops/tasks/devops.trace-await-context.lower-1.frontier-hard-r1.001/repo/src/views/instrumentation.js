import { clear, element } from "./components.js";

export function renderInstrumentation(snapshot) {
  const host = clear(
    document.querySelector('[data-test="instrumentation"]'),
  );
  for (const item of snapshot.instrumentation) {
    const card = element("article", "instrument-card");
    card.dataset.test = `instrument-${item.kind}`;
    card.append(
      element("strong", "", item.label),
      element(
        "span",
        "",
        `${item.count} spans · ${item.attached} attached`,
      ),
    );
    host.append(card);
  }
}
