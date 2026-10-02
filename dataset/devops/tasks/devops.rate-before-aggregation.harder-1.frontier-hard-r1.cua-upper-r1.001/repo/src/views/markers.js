import {clear, element} from "./components.js";

export function renderMarkers(snapshot) {
  const root = document.querySelector('[data-test="markers"]');
  clear(root);
  for (const marker of snapshot.markers) {
    const item = element("li", `marker marker-${marker.kind}`);
    item.dataset.markerId = marker.id;
    item.dataset.markerTime = String(marker.time);
    item.append(
      element("strong", "", `${marker.time}s`),
      element("span", "", marker.label),
    );
    root.append(item);
  }
}
