import {selectPanel, selectScenario} from "../controllers/dashboard.js";
import {clear, element} from "./components.js";

function buttons(root, values, activeId, key, choose) {
  clear(root);
  for (const value of values) {
    const button = element("button", "control", value.label || value.title);
    button.type = "button";
    button.dataset[key] = value.id;
    button.dataset.active = String(value.id === activeId);
    button.addEventListener("click", () => choose(value.id));
    root.append(button);
  }
}

export function renderControls(catalog, snapshot) {
  buttons(
    document.querySelector('[data-test="scenario-controls"]'),
    catalog.scenarios,
    snapshot.scenario.id,
    "scenarioId",
    selectScenario,
  );
  buttons(
    document.querySelector('[data-test="panel-controls"]'),
    catalog.panels,
    snapshot.panel.id,
    "panelId",
    selectPanel,
  );
}
