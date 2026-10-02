import { clear, element } from "./components.js";

export function renderRoutes(snapshot) {
  const host = clear(document.querySelector('[data-test="routes"]'));
  for (const route of snapshot.routes) {
    const row = element("article", "route");
    row.dataset.test = `route-${route.name}`;
    row.append(
      element("strong", "", route.name),
      element("span", "route-count", `${route.delivered} delivered`),
      element("small", "", route.description),
    );
    host.append(row);
  }
}
