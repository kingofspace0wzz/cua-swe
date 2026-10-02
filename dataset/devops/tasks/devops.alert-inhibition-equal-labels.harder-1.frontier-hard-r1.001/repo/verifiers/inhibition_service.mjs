import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROFILES = JSON.parse(readFileSync(join(HERE, "profiles.json"), "utf8"));
const clone = (value) => JSON.parse(JSON.stringify(value));

function parseOptions(argv) {
  const output = { host: "127.0.0.1", port: 4372, profile: "visible" };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") output.host = argv[++index];
    else if (argv[index] === "--port") output.port = Number(argv[++index]);
    else if (argv[index] === "--profile") output.profile = argv[++index];
  }
  return output;
}

function send(response, status, body) {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(payload),
  });
  response.end(payload);
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      try {
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {});
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function publicCatalog(profile) {
  return {
    label: profile.label,
    equalDimensions: clone(profile.equalDimensions),
    dimensions: clone(profile.dimensions),
    advisories: clone(profile.advisories),
    sourceClass: profile.sourceClass,
    targetClass: profile.targetClass,
    incidents: profile.incidents.map((incident) => ({
      label: incident.label,
      arrivingCount: incident.alerts.length,
    })),
  };
}

function placementDimensions(profile) {
  return profile.dimensions
    .filter((dimension) => dimension.role === "placement")
    .map((dimension) => dimension.name);
}

function dimensionRole(profile, name) {
  const entry = profile.dimensions.find((dimension) => dimension.name === name);
  return entry ? entry.role : "partition";
}

function validateRule(rule) {
  if (!rule || typeof rule !== "object") throw new Error("rule is required");
  for (const field of [
    "source_matchers",
    "target_matchers",
    "equal",
    "required_source_labels",
    "required_target_labels",
  ]) {
    if (!Array.isArray(rule[field])) throw new Error(`${field} must be an array`);
  }
}

function labelValue(alert, name) {
  const value = alert.labels[name];
  return value === undefined ? "" : String(value);
}

function hasNonemptyLabel(alert, name) {
  return Object.hasOwn(alert.labels, name) && labelValue(alert, name) !== "";
}

function matches(alert, matcher) {
  const actual = labelValue(alert, matcher.label);
  const value = String(matcher.value);
  if (matcher.operator === "=") return actual === value;
  if (matcher.operator === "!=") return actual !== value;
  if (matcher.operator === "=~") return new RegExp(`^(?:${value})$`).test(actual);
  if (matcher.operator === "!~") return !new RegExp(`^(?:${value})$`).test(actual);
  throw new Error(`unsupported matcher operator ${matcher.operator}`);
}

function eligible(alert, matchers, requiredLabels) {
  return (
    matchers.every((matcher) => matches(alert, matcher))
    && requiredLabels.every((name) => hasNonemptyLabel(alert, name))
  );
}

function activeAlerts(profile, incidentIndex) {
  return profile.incidents
    .slice(0, incidentIndex + 1)
    .flatMap((incident) => incident.alerts)
    .map(clone);
}

function dimensionState(alert, dimension) {
  if (!Object.hasOwn(alert.labels, dimension)) return "missing";
  return labelValue(alert, dimension) === "" ? "empty" : "present";
}

function scopeState(alert, profile) {
  const states = placementDimensions(profile).map((dimension) =>
    dimensionState(alert, dimension),
  );
  if (states.includes("missing")) return "missing";
  if (states.includes("empty")) return "empty";
  return "present";
}

function comparisonEntry(profile, source, target, dimension) {
  const role = dimensionRole(profile, dimension);
  const sourceState = dimensionState(source, dimension);
  const targetState = dimensionState(target, dimension);
  const bothPresent = sourceState === "present" && targetState === "present";
  const bothMissing = sourceState === "missing" && targetState === "missing";
  let state;
  let stateLabel;
  if (role === "placement") {
    state = bothPresent ? "equal-present" : "equal-missing";
    stateLabel = bothPresent
      ? `equal concrete ${dimension} values`
      : `equal only because ${dimension} is absent or empty`;
  } else if (bothPresent) {
    state = "recorded-equal";
    stateLabel = `equal recorded ${dimension} values`;
  } else if (bothMissing) {
    state = "absent-tolerated";
    stateLabel = `equal by absence — expected for alerts opened before the ${dimension} rollout`;
  } else {
    state = "equal-missing";
    stateLabel = `equal only because ${dimension} is absent or empty`;
  }
  return {
    sourceId: source.id,
    sourceName: source.displayName,
    targetId: target.id,
    targetName: target.displayName,
    dimension,
    role,
    sourceValue: labelValue(source, dimension) || "(absent or empty)",
    targetValue: labelValue(target, dimension) || "(absent or empty)",
    state,
    stateLabel,
  };
}

function evaluate(profile, incidentIndex, rule) {
  const alerts = activeAlerts(profile, incidentIndex);
  const results = [];
  const comparisons = [];
  const edges = [];

  for (const alert of alerts) {
    let inhibitedBy = null;
    if (!rule.disabled && eligible(
      alert,
      rule.target_matchers,
      rule.required_target_labels,
    )) {
      for (const source of alerts) {
        if (
          source.id === alert.id
          || !eligible(
            source,
            rule.source_matchers,
            rule.required_source_labels,
          )
        ) {
          continue;
        }
        const equal = rule.equal.every(
          (name) => labelValue(source, name) === labelValue(alert, name),
        );
        if (equal) {
          inhibitedBy = source;
          break;
        }
      }
    }

    const result = {
      ...clone(alert),
      severity: alert.labels.severity || "warning",
      status: inhibitedBy ? "suppressed" : "firing",
      inhibitedBy: inhibitedBy?.displayName || null,
      inhibitedById: inhibitedBy?.id || null,
      scopeState: scopeState(alert, profile),
    };
    results.push(result);

    if (inhibitedBy) {
      edges.push({
        sourceId: inhibitedBy.id,
        sourceName: inhibitedBy.displayName,
        targetId: alert.id,
        targetName: alert.displayName,
        reason: `${profile.equalDimensions.join(", ")} values compare equal`,
      });
      for (const dimension of profile.equalDimensions) {
        comparisons.push(comparisonEntry(profile, inhibitedBy, alert, dimension));
      }
    }
  }

  return {
    incidentIndex,
    atEnd: incidentIndex === profile.incidents.length - 1,
    incident: {
      label: profile.incidents[incidentIndex].label,
    },
    alerts: results,
    firing: results.filter((alert) => alert.status === "firing"),
    suppressed: results.filter((alert) => alert.status === "suppressed"),
    edges,
    comparisons,
    rule: clone(rule),
  };
}

function expectedRule(profile) {
  const required = placementDimensions(profile);
  return {
    source_matchers: [
      { label: "alertname", operator: "=", value: profile.sourceClass },
    ],
    target_matchers: [
      { label: "alertname", operator: "=~", value: ".*" },
    ],
    equal: clone(profile.equalDimensions),
    required_source_labels: clone(required),
    required_target_labels: clone(required),
  };
}

function signature(snapshot) {
  return {
    incidentIndex: snapshot.incidentIndex,
    alerts: snapshot.alerts.map((alert) => ({
      id: alert.id,
      status: alert.status,
      inhibitedById: alert.inhibitedById,
    })),
    edges: snapshot.edges.map((edge) => ({
      sourceId: edge.sourceId,
      targetId: edge.targetId,
    })),
  };
}

export function createInhibitionService(profileName = "visible") {
  const profile = PROFILES[profileName];
  if (!profile) throw new Error(`unknown profile ${profileName}`);
  const state = { rule: null, incidentIndex: 0, advanceCount: 0 };
  const snapshot = () => {
    if (!state.rule) throw new Error("rule is not configured");
    return evaluate(profile, state.incidentIndex, state.rule);
  };

  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://127.0.0.1");
      const path = url.pathname.replace(/\/+$/, "") || "/";
      if (request.method === "GET" && path === "/health") {
        send(response, 200, { ok: true, profile: profileName });
        return;
      }
      if (request.method === "GET" && path === "/catalog") {
        send(response, 200, publicCatalog(profile));
        return;
      }
      if (request.method === "POST" && path === "/configure") {
        const input = await readJson(request);
        validateRule(input.rule);
        state.rule = clone(input.rule);
        state.incidentIndex = 0;
        state.advanceCount = 0;
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/snapshot") {
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "POST" && path === "/advance") {
        if (state.incidentIndex < profile.incidents.length - 1) {
          state.incidentIndex += 1;
          state.advanceCount += 1;
        }
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/audit") {
        const actual = snapshot();
        const expected = evaluate(
          profile,
          state.incidentIndex,
          expectedRule(profile),
        );
        send(response, 200, {
          profile: profileName,
          configuredRule: clone(state.rule),
          incidentIndex: state.incidentIndex,
          advanceCount: state.advanceCount,
          protectedAlertCount: expected.alerts.length,
          protectedSuppressedCount: expected.suppressed.length,
          actual,
          expected,
          actualSignature: signature(actual),
          expectedSignature: signature(expected),
        });
        return;
      }
      if (request.method === "POST" && path === "/reset") {
        state.rule = null;
        state.incidentIndex = 0;
        state.advanceCount = 0;
        send(response, 200, { ok: true });
        return;
      }
      send(response, 404, { error: "unknown_path" });
    } catch (error) {
      send(response, 500, {
        error: "service_failure",
        detail: String(error.message || error),
      });
    }
  });
}

export async function startInhibitionService(input = {}) {
  const server = createInhibitionService(input.profile || "visible");
  await new Promise((resolve) => {
    server.listen(input.port || 4372, input.host || "127.0.0.1", resolve);
  });
  return { server, address: server.address() };
}

if (process.argv[1]?.endsWith("inhibition_service.mjs")) {
  const options = parseOptions(process.argv.slice(2));
  startInhibitionService(options).then(({ address }) => {
    process.stdout.write(
      `inhibition service on http://${address.address}:${address.port} (${options.profile})\n`,
    );
  });
}
