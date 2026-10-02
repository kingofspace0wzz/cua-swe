import { clear, element } from "./components.js";

export function renderComparisons(snapshot) {
  const host = clear(document.querySelector('[data-test="comparisons"]'));
  for (const comparison of snapshot.comparisons) {
    const card = element("article", "comparison");
    card.dataset.test = `comparison-${comparison.targetId}`;
    card.dataset.state = comparison.state;
    card.append(
      element("strong", "", `${comparison.sourceName} ↔ ${comparison.targetName}`),
      element("span", "", comparison.dimension),
      element(
        "code",
        "",
        `${comparison.sourceValue} = ${comparison.targetValue}`,
      ),
      element("small", "", comparison.stateLabel),
    );
    host.append(card);
  }
}
