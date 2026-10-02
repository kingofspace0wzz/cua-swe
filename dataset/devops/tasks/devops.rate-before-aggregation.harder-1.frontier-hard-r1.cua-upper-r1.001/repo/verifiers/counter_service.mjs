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

function trafficAt(schedule, interval) {
  const shape = [1.35, 2.2, 3.6, 5.0, 5.35, 5.35, 5.0, 3.6, 2.2, 1.35];
  const offset = interval - schedule.burstStart;
  if (offset < 0 || offset >= shape.length) return schedule.base;
  const scale = schedule.burstPeak / (schedule.base * 5.35);
  return schedule.base * shape[offset] * scale;
}

function targetCounters(profile, schedule, panel, windowConfig) {
  const start = windowConfig.offset;
  return profile.targets.map((target, targetIndex) => {
    let counter = (targetIndex + 1) * windowConfig.counterSeed * Math.max(panel.factor, 1);
    const points = [{time: start, value: counter}];
    for (let sample = 1; sample < SAMPLE_COUNT; sample += 1) {
      const rate = trafficAt(schedule, sample) * target.weight * panel.factor;
      const increase = rate * STEP_SECONDS;
      const reset = schedule.resets.some(
        (event) => event.target === targetIndex && event.sample === sample,
      );
      counter = reset ? increase : counter + increase;
      points.push({time: start + sample * STEP_SECONDS, value: counter});
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

function calculate(profile, scenario, panel, plan, panelIndex, windowIndex) {
  const windowConfig = profile.windows[windowIndex];
  const schedule = scenario.windows[windowIndex];
  const upstream = plan.upstreamByWindow[windowConfig.id];
  let counters = targetCounters(profile, schedule, panel, windowConfig);
  if (plan.sample_filter === "drop-reset-target" && schedule.resets.length) {
    const removed = new Set(schedule.resets.map((item) => item.target));
    counters = counters.filter((_, index) => !removed.has(index));
  }
  const timestampShortcut = plan.sample_filter === "visible-reset-window"
    && schedule.resets.some((event) => event.sample === 8);
  const correctPanel = plan.panel_scope === "all" || panelIndex === 0;
  const perTargetInput = upstream !== "gateway-rollup" || timestampShortcut;
  let inputs = counters;
  if (!timestampShortcut && upstream === "relay-mirror") inputs = mirrorCounters(counters);
  else if (!timestampShortcut && upstream === "archive-compaction") inputs = compactCounters(counters);
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
    const ceiling = schedule.base * panel.factor * 1.8;
    values = values.map((point) => ({...point, value: Math.min(point.value, ceiling)}));
  }
  return values;
}

function format(value, panel) {
  if (panel.factor > 100) return `${Math.round(value)} ${panel.unit}`;
  return `${value.toFixed(panel.factor < 0.1 ? 2 : 1)} ${panel.unit}`;
}

function markers(profile, scenario, windowConfig, windowIndex) {
  const schedule = scenario.windows[windowIndex];
  const output = schedule.resets.map((event, index) => ({
    id: `reset-${index}`,
    kind: "reset",
    time: windowConfig.offset + event.sample * STEP_SECONDS,
    label: `target restart: ${profile.targets[event.target].label}`,
  }));
  output.push({
    id: "burst",
    kind: "burst",
    time: windowConfig.offset + schedule.burstStart * STEP_SECONDS,
    label: "traffic burst begins",
  });
  if (windowConfig.transition) {
    output.push({
      id: "transition",
      kind: "transition",
      time: windowConfig.transition.time,
      label: windowConfig.transition.label,
    });
  }
  return output.sort((left, right) => left.time - right.time);
}

function targetEvidence(profile, scenario, windowConfig, windowIndex) {
  const schedule = scenario.windows[windowIndex];
  return profile.targets.map((target, index) => {
    const events = schedule.resets.filter((item) => item.target === index);
    return {
      id: target.id,
      label: target.label,
      resetCount: events.length,
      lastReset: events.length
        ? `${windowConfig.offset + events.at(-1).sample * STEP_SECONDS}s`
        : "\u2014",
      state: events.length ? "recovered" : "continuous",
    };
  });
}

function validatePlan(input, profile) {
  const deployed = new Set(definitions.map((entry) => entry.id));
  const windowIds = profile.windows.map((window) => window.id);
  let binding;
  if (typeof input?.pipeline === "string") {
    if (!deployed.has(input.pipeline)) throw new Error("unknown deployed recording-rule binding");
    binding = Object.fromEntries(windowIds.map((id) => [id, input.pipeline]));
  } else if (input?.pipeline && typeof input.pipeline === "object" && !Array.isArray(input.pipeline)) {
    const keys = Object.keys(input.pipeline).sort();
    if (JSON.stringify(keys) !== JSON.stringify([...windowIds].sort())) {
      throw new Error("a window binding must cover exactly the deployed collection windows");
    }
    for (const rule of Object.values(input.pipeline)) {
      if (!deployed.has(rule)) throw new Error("unknown deployed recording-rule binding");
    }
    binding = {...input.pipeline};
  } else {
    throw new Error("unknown deployed recording-rule binding");
  }
  const scopes = new Set(["all", "first-panel"]);
  const filters = new Set(["none", "clamp", "median-despike", "drop-reset-target", "disable-reset-correction", "short-range", "visible-reset-window"]);
  if (!scopes.has(input?.panel_scope)) throw new Error(`unsupported panel scope ${input?.panel_scope}`);
  if (!filters.has(input?.sample_filter)) throw new Error(`unsupported sample filter ${input?.sample_filter}`);
  return {
    panel_scope: input.panel_scope,
    sample_filter: input.sample_filter,
    upstreamByWindow: Object.fromEntries(
      profile.windows.map((window) => [window.id, window.rules[binding[window.id]].upstream]),
    ),
  };
}

function brokenPlan(profile) {
  return {
    panel_scope: "all",
    sample_filter: "none",
    upstreamByWindow: Object.fromEntries(
      profile.windows.map((window) => [window.id, "gateway-rollup"]),
    ),
  };
}

function expectedPlan(profile) {
  return {
    panel_scope: "all",
    sample_filter: "none",
    upstreamByWindow: Object.fromEntries(
      profile.windows.map((window) => [window.id, "raw-scrape"]),
    ),
  };
}

function evaluate(profile, scenarioIndex, panelIndex, windowIndex, plan) {
  const scenario = profile.scenarios[scenarioIndex];
  const panel = profile.panels[panelIndex];
  const windowConfig = profile.windows[windowIndex];
  const raw = calculate(profile, scenario, panel, plan, panelIndex, windowIndex);
  const points = raw.map((point, index) => ({
    id: `${panel.id}-${windowConfig.id}-p${index}`,
    time: point.time,
    value: Number(point.value.toFixed(6)),
    formatted: format(point.value, panel),
  }));
  const peak = Math.max(...points.map((point) => point.value));
  const total = points.reduce((sum, point) => sum + point.value * STEP_SECONDS, 0);
  return {
    scenario: {id: scenario.id, label: scenario.label, index: scenarioIndex},
    panel: {id: panel.id, title: panel.title, unit: panel.unit, index: panelIndex},
    window: {id: windowConfig.id, label: windowConfig.label, index: windowIndex},
    points,
    summary: {peak: format(peak, panel), total: format(total, {...panel, unit: panel.unit.replace("/s", "")})},
    markers: markers(profile, scenario, windowConfig, windowIndex),
    targets: targetEvidence(profile, scenario, windowConfig, windowIndex),
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
    plan: brokenPlan(profile),
    scenarioIndex: 0,
    panelIndex: 0,
    windowIndex: 0,
    scenarioSelectCount: 0,
    panelSelectCount: 0,
    windowSelectCount: 0,
  };

  function resetState() {
    state.plan = brokenPlan(profile);
    state.scenarioIndex = 0;
    state.panelIndex = 0;
    state.windowIndex = 0;
    state.scenarioSelectCount = 0;
    state.panelSelectCount = 0;
    state.windowSelectCount = 0;
  }

  function catalog() {
    return {
      label: profile.label,
      definitions: definitions.map(({id, label, steps, inputLabels, outputLabels}) => ({
        id,
        label,
        steps,
        inputLabels,
        outputLabels,
        lineage: profile.windows.map(
          (window) => `${window.label} \u2014 ${window.rules[id].lineage}`,
        ),
      })),
      windows: profile.windows.map(({id, label, note, transition, perTargetScrape}) => ({
        id,
        label,
        note,
        transition,
        perTargetScrape,
      })),
      scenarios: profile.scenarios.map(({id, label}) => ({id, label})),
      panels: profile.panels.map(({id, title, unit}) => ({id, title, unit})),
    };
  }

  function snapshot(plan = state.plan) {
    return evaluate(profile, state.scenarioIndex, state.panelIndex, state.windowIndex, plan);
  }

  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://service.invalid");
      if (request.method === "GET" && url.pathname === "/health") send(response, 200, {ok: true});
      else if (request.method === "GET" && url.pathname === "/catalog") send(response, 200, catalog());
      else if (request.method === "POST" && url.pathname === "/configure") {
        const input = await readJson(request);
        const plan = validatePlan(input.plan, profile);
        resetState();
        state.plan = plan;
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
      } else if (request.method === "POST" && url.pathname === "/window") {
        const input = await readJson(request);
        const index = profile.windows.findIndex((item) => item.id === input.window_id);
        if (index < 0) throw new Error(`unknown window ${input.window_id}`);
        if (index !== state.windowIndex) state.windowSelectCount += 1;
        state.windowIndex = index;
        send(response, 200, snapshot());
      } else if (request.method === "GET" && url.pathname === "/audit") {
        const actual = snapshot();
        const expected = snapshot(expectedPlan(profile));
        send(response, 200, {
          actual, expected,
          actualSignature: signature(actual),
          expectedSignature: signature(expected),
          protectedPointCount: expected.points.length,
          protectedPanelCount: profile.panels.length,
          protectedScenarioCount: profile.scenarios.length,
          protectedWindowCount: profile.windows.length,
          protectedTargetCount: profile.targets.length,
          scenarioSelectCount: state.scenarioSelectCount,
          panelSelectCount: state.panelSelectCount,
          windowSelectCount: state.windowSelectCount,
        });
      } else if (request.method === "POST" && url.pathname === "/reset") {
        resetState();
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
