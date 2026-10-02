import {createServer} from "node:http";
import {readFileSync} from "node:fs";

const profiles = JSON.parse(readFileSync(new URL("./profiles.json", import.meta.url), "utf8"));
const definitions = JSON.parse(readFileSync(new URL("./recording-rules.json", import.meta.url), "utf8"));
const STEP_SECONDS = 15;
const WINDOW_INTERVALS = 4;
const SAMPLE_COUNT = 25;

function parseOptions(argv) {
  const output = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") output.host = argv[++index];
    else if (argv[index] === "--port") output.port = Number(argv[++index]);
    else if (argv[index] === "--profile") output.profile = argv[++index];
  }
  return output;
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (error) { reject(error); }
    });
  });
}

function send(response, status, value) {
  response.writeHead(status, {"content-type": "application/json", "cache-control": "no-store"});
  response.end(JSON.stringify(value));
}

function trafficAt(scenario, interval) {
  const shape = [1.35, 2.2, 3.6, 5.0, 5.35, 5.35, 5.0, 3.6, 2.2, 1.35];
  const offset = interval - scenario.burstStart;
  if (offset < 0 || offset >= shape.length) return scenario.base;
  const scale = scenario.burstPeak / (scenario.base * 5.35);
  return scenario.base * shape[offset] * scale;
}

function targetCounters(profile, scenario, panel) {
  return profile.targets.map((target, targetIndex) => {
    let counter = (targetIndex + 1) * 90000 * Math.max(panel.factor, 1);
    const points = [{time: 0, value: counter}];
    for (let sample = 1; sample < SAMPLE_COUNT; sample += 1) {
      const rate = trafficAt(scenario, sample) * target.weight * panel.factor;
      const increase = rate * STEP_SECONDS;
      const reset = scenario.resets.some(
        (event) => event.target === targetIndex && event.sample === sample,
      );
      counter = reset ? increase : counter + increase;
      points.push({time: sample * STEP_SECONDS, value: counter});
    }
    return points;
  });
}

function resetAwareIncrease(points, start, end, correctResets = true) {
  let increase = 0;
  for (let index = start + 1; index <= end; index += 1) {
    const previous = points[index - 1].value;
    const current = points[index].value;
    if (current < previous) increase += correctResets ? current : current - previous;
    else increase += current - previous;
  }
  return increase;
}

function rateOne(points, intervals = WINDOW_INTERVALS, correctResets = true) {
  const output = [];
  for (let end = intervals; end < points.length; end += 1) {
    const start = end - intervals;
    output.push({
      time: points[end].time,
      value: resetAwareIncrease(points, start, end, correctResets) / (intervals * STEP_SECONDS),
    });
  }
  return output;
}

function sumCounters(series) {
  return series[0].map((point, index) => ({
    time: point.time,
    value: series.reduce((total, item) => total + item[index].value, 0),
  }));
}

function sumRates(series) {
  return series[0].map((point, index) => ({
    time: point.time,
    value: series.reduce((total, item) => total + item[index].value, 0),
  }));
}

function mirrorCounters(series) {
  return series.map((points) => points.map((point, index) => ({
    time: point.time,
    value: points[Math.max(0, index - 1)].value,
  })));
}

function compactCounters(series) {
  return series.map((points) => points.map((point, index) => ({
    time: point.time,
    value: points[index - (index % 2)].value,
  })));
}

function calculate(profile, scenario, panel, plan, panelIndex) {
  let counters = targetCounters(profile, scenario, panel);
  if (plan.sample_filter === "drop-reset-target" && scenario.resets.length) {
    const removed = new Set(scenario.resets.map((item) => item.target));
    counters = counters.filter((_, index) => !removed.has(index));
  }
  const timestampShortcut = plan.sample_filter === "visible-reset-window"
    && scenario.resets.some((event) => event.sample === 8);
  const correctPanel = plan.panel_scope === "all" || panelIndex === 0;
  const perTargetInput = plan.upstream !== "gateway-rollup" || timestampShortcut;
  let inputs = counters;
  if (!timestampShortcut && plan.upstream === "relay-mirror") inputs = mirrorCounters(counters);
  else if (!timestampShortcut && plan.upstream === "archive-compaction") inputs = compactCounters(counters);
  let values;
  if (correctPanel && perTargetInput) {
    values = sumRates(inputs.map((points) => rateOne(points)));
  } else {
    values = rateOne(sumCounters(counters), WINDOW_INTERVALS, plan.sample_filter !== "disable-reset-correction");
  }
  if (plan.sample_filter === "short-range") {
    values = correctPanel && perTargetInput
      ? sumRates(inputs.map((points) => rateOne(points, 2)))
      : rateOne(sumCounters(counters), 2);
  }
  if (["clamp", "median-despike"].includes(plan.sample_filter)) {
    const ceiling = scenario.base * panel.factor * 1.8;
    values = values.map((point) => ({...point, value: Math.min(point.value, ceiling)}));
  }
  return values;
}

function format(value, panel) {
  if (panel.factor > 100) return `${Math.round(value)} ${panel.unit}`;
  return `${value.toFixed(panel.factor < 0.1 ? 2 : 1)} ${panel.unit}`;
}

function markers(profile, scenario) {
  const resetMarkers = scenario.resets.map((event, index) => ({
    id: `reset-${index}`,
    kind: "reset",
    time: event.sample * STEP_SECONDS,
    label: `target restart: ${profile.targets[event.target].label}`,
  }));
  return resetMarkers.concat({
    id: "burst",
    kind: "burst",
    time: scenario.burstStart * STEP_SECONDS,
    label: "traffic burst begins",
  }).sort((left, right) => left.time - right.time);
}

function targetEvidence(profile, scenario) {
  return profile.targets.map((target, index) => {
    const events = scenario.resets.filter((item) => item.target === index);
    return {
      id: target.id,
      label: target.label,
      resetCount: events.length,
      lastReset: events.length ? `${events.at(-1).sample * STEP_SECONDS}s` : "—",
      state: events.length ? "recovered" : "continuous",
    };
  });
}

function validatePlan(input) {
  const definition = definitions.find((entry) => entry.id === input?.pipeline);
  if (!definition) throw new Error("unknown deployed recording-rule binding");
  const scopes = new Set(["all", "first-panel"]);
  const filters = new Set(["none", "clamp", "median-despike", "drop-reset-target", "disable-reset-correction", "short-range", "visible-reset-window"]);
  if (!scopes.has(input?.panel_scope)) throw new Error(`unsupported panel scope ${input?.panel_scope}`);
  if (!filters.has(input?.sample_filter)) throw new Error(`unsupported sample filter ${input?.sample_filter}`);
  return {...input, upstream: definition.upstream};
}

function expectedPlan() {
  return {
    upstream: "raw-scrape",
    panel_scope: "all",
    sample_filter: "none",
  };
}

function evaluate(profile, scenarioIndex, panelIndex, plan) {
  const scenario = profile.scenarios[scenarioIndex];
  const panel = profile.panels[panelIndex];
  const raw = calculate(profile, scenario, panel, plan, panelIndex);
  const points = raw.map((point, index) => ({
    id: `${panel.id}-p${index}`,
    time: point.time,
    value: Number(point.value.toFixed(6)),
    formatted: format(point.value, panel),
  }));
  const peak = Math.max(...points.map((point) => point.value));
  const total = points.reduce((sum, point) => sum + point.value * STEP_SECONDS, 0);
  return {
    scenario: {id: scenario.id, label: scenario.label, index: scenarioIndex},
    panel: {id: panel.id, title: panel.title, unit: panel.unit, index: panelIndex},
    points,
    summary: {peak: format(peak, panel), total: format(total, {...panel, unit: panel.unit.replace("/s", "")})},
    markers: markers(profile, scenario),
    targets: targetEvidence(profile, scenario),
    diagnostics: {range: `${WINDOW_INTERVALS * STEP_SECONDS} seconds`, seriesCount: profile.targets.length},
  };
}

function signature(value) {
  return JSON.stringify(value);
}

export function createCounterService(profileName = "visible") {
  const profile = profiles[profileName];
  if (!profile) throw new Error(`unknown profile ${profileName}`);
  const state = {
    plan: {upstream: "gateway-rollup", panel_scope: "all", sample_filter: "none"},
    scenarioIndex: 0,
    panelIndex: 0,
    scenarioSelectCount: 0,
    panelSelectCount: 0,
  };

  function catalog() {
    return {
      label: profile.label,
      definitions: definitions.map(({id, label, steps, inputLabels, outputLabels, lineage}) => ({id, label, steps, inputLabels, outputLabels, lineage})),
      scenarios: profile.scenarios.map(({id, label}) => ({id, label})),
      panels: profile.panels.map(({id, title, unit}) => ({id, title, unit})),
    };
  }

  function snapshot(plan = state.plan) {
    return evaluate(profile, state.scenarioIndex, state.panelIndex, plan);
  }

  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://service.invalid");
      if (request.method === "GET" && url.pathname === "/health") send(response, 200, {ok: true});
      else if (request.method === "GET" && url.pathname === "/catalog") send(response, 200, catalog());
      else if (request.method === "POST" && url.pathname === "/configure") {
        const input = await readJson(request);
        state.plan = validatePlan(input.plan);
        state.scenarioIndex = 0;
        state.panelIndex = 0;
        state.scenarioSelectCount = 0;
        state.panelSelectCount = 0;
        send(response, 200, snapshot());
      } else if (request.method === "GET" && url.pathname === "/snapshot") send(response, 200, snapshot());
      else if (request.method === "POST" && url.pathname === "/scenario") {
        const input = await readJson(request);
        const index = profile.scenarios.findIndex((item) => item.id === input.scenario_id);
        if (index < 0) throw new Error(`unknown scenario ${input.scenario_id}`);
        if (index !== state.scenarioIndex) state.scenarioSelectCount += 1;
        state.scenarioIndex = index;
        send(response, 200, snapshot());
      } else if (request.method === "POST" && url.pathname === "/panel") {
        const input = await readJson(request);
        const index = profile.panels.findIndex((item) => item.id === input.panel_id);
        if (index < 0) throw new Error(`unknown panel ${input.panel_id}`);
        if (index !== state.panelIndex) state.panelSelectCount += 1;
        state.panelIndex = index;
        send(response, 200, snapshot());
      } else if (request.method === "GET" && url.pathname === "/audit") {
        const actual = snapshot();
        const expected = snapshot(expectedPlan());
        send(response, 200, {
          actual, expected,
          actualSignature: signature(actual),
          expectedSignature: signature(expected),
          protectedPointCount: expected.points.length,
          protectedPanelCount: profile.panels.length,
          protectedScenarioCount: profile.scenarios.length,
          protectedTargetCount: profile.targets.length,
          scenarioSelectCount: state.scenarioSelectCount,
          panelSelectCount: state.panelSelectCount,
        });
      } else if (request.method === "POST" && url.pathname === "/reset") {
        state.plan = {upstream: "gateway-rollup", panel_scope: "all", sample_filter: "none"};
        state.scenarioIndex = 0;
        state.panelIndex = 0;
        state.scenarioSelectCount = 0;
        state.panelSelectCount = 0;
        send(response, 200, {ok: true});
      } else send(response, 404, {error: "unknown_path"});
    } catch (error) {
      send(response, 500, {error: "service_failure", detail: String(error.message || error)});
    }
  });
}

export async function startCounterService(input = {}) {
  const server = createCounterService(input.profile || "visible");
  await new Promise((resolve) => server.listen(input.port || 4442, input.host || "127.0.0.1", resolve));
  return {server, address: server.address()};
}

if (process.argv[1]?.endsWith("counter_service.mjs")) {
  startCounterService(parseOptions(process.argv.slice(2))).then(({address}) => {
    process.stdout.write(`counter service on http://${address.address}:${address.port}\n`);
  });
}
