import {clear, element} from "./components.js";

export function renderCollection(catalog, snapshot) {
  const root = document.querySelector('[data-test="collection"]');
  clear(root);
  for (const window of catalog.windows) {
    const item = element("li", "collection-window");
    item.dataset.windowId = window.id;
    item.dataset.active = String(window.id === snapshot.window.id);
    item.append(element("strong", "", window.label));
    if (window.transition) {
      item.append(element("em", "collection-transition", `${window.transition.time}s \u00b7 ${window.transition.label}`));
    }
    item.append(element("p", "collection-note", window.note));
    root.append(item);
  }
}
