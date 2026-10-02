import { clear, element } from "./components.js";

export function renderTransitions(snapshot) {
  const host = clear(
    document.querySelector('[data-test="transitions"]'),
  );
  for (const item of snapshot.transitions) {
    const className = item.status === "lost" ? "transition-lost" : "";
    const row = element(
      "li",
      className,
      `${item.operationLabel} · ${item.boundary} · ${item.status}`,
    );
    row.dataset.test = `transition-${item.id}`;
    host.append(row);
  }
}
