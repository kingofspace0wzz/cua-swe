import {clear, element} from "./components.js";

export function renderDefinitions(catalog, plan) {
  const host = document.querySelector('[data-test="definitions"]');
  clear(host);
  for (const definition of catalog.definitions) {
    const card = element("article", "definition-card");
    card.dataset.definitionId = definition.id;
    const active = definition.id === plan.pipeline ? " · Active" : "";
    card.append(element("h3", "", `${definition.label}${active}`));
    card.append(element("p", "definition-id", definition.id));
    card.append(element("p", "definition-labels", `Input labels: ${definition.inputLabels} → Output labels: ${definition.outputLabels}`));
    for (const step of definition.steps) card.append(element("code", "definition-step", step));
    for (const note of definition.lineage || []) card.append(element("p", "definition-lineage", note));
    host.append(card);
  }
}
