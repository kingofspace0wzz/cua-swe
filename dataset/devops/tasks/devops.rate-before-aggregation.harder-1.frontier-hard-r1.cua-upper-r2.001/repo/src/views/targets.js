import {clear, element} from "./components.js";

export function renderTargets(snapshot) {
  const body = document.querySelector('[data-test="targets"]');
  clear(body);
  for (const target of snapshot.targets) {
    const row = element("tr", "target-row");
    row.dataset.targetId = target.id;
    for (const value of [target.label, target.resetCount, target.lastReset, target.state, target.publication]) {
      row.append(element("td", "", String(value)));
    }
    body.append(row);
  }
}
