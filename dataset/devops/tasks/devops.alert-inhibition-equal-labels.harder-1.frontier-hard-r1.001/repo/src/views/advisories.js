import { clear, element } from "./components.js";

export function renderAdvisories(catalog) {
  const host = clear(document.querySelector('[data-test="advisories"]'));
  for (const advisory of catalog.advisories) {
    host.append(element("p", "advisory", advisory));
  }
}
