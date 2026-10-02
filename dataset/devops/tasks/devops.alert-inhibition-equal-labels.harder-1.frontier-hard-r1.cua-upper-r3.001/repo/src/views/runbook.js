import { element } from "./components.js";

export function renderRunbook() {
  const host = document.querySelector('[data-test="runbook"]');
  if (host.dataset.rendered === "yes") return;
  const image = element("img", "runbook-page");
  image.dataset.test = "runbook-image";
  image.alt = "Scope stamping runbook page rendered by ops-docs";
  image.src = "/api/runbook";
  host.dataset.rendered = "yes";
  host.replaceChildren(image);
}
