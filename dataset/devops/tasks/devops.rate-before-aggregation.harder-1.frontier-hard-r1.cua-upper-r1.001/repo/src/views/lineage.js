import {clear, element} from "./components.js";

export function renderLineage(catalog, snapshot) {
  const root = document.querySelector('[data-test="lineage"]');
  clear(root);
  for (const window of catalog.windows) {
    const item = element("li", "lineage-window");
    item.dataset.windowId = window.id;
    item.dataset.active = String(window.id === snapshot.window.id);
    item.append(element("strong", "", window.label));
    if (window.transition) {
      item.append(element("em", "lineage-transition", `${window.transition.time}s \u00b7 ${window.transition.label}`));
    }
    item.append(element("p", "lineage-note", window.note));
    root.append(item);
  }
}
