import {renderDefinitions} from "./definitions.js";
import {renderChart} from "./chart.js";
import {renderCollection} from "./collection.js";
import {renderControls, renderWindowControls} from "./controls.js";
import {renderMarkers} from "./markers.js";
import {renderTargets} from "./targets.js";
import {setText} from "./components.js";

export function render(state) {
  const app = document.querySelector("#app");
  setText('[data-test="error"]', state.error || "");
  if (!state.catalog || !state.snapshot) {
    app.dataset.ready = state.error ? "error" : "no";
    return;
  }
  const value = state.snapshot;
  setText('[data-test="profile"]', state.catalog.label);
  setText('[data-test="scenario"]', value.scenario.label);
  setText('[data-test="window"]', value.window.label);
  setText('[data-test="panel-title"]', value.panel.title);
  setText('[data-test="panel-unit"]', value.panel.unit);
  setText('[data-test="peak"]', value.summary.peak);
  setText('[data-test="total"]', value.summary.total);
  setText('[data-test="range"]', value.diagnostics.range);
  setText('[data-test="series-count"]', value.diagnostics.seriesCount);
  renderControls(state.catalog, value);
  renderWindowControls(state.catalog, value);
  renderChart(value);
  renderMarkers(value);
  renderTargets(value);
  renderCollection(state.catalog, value);
  renderDefinitions(state.catalog, state.plan);
  app.dataset.ready = "yes";
}
