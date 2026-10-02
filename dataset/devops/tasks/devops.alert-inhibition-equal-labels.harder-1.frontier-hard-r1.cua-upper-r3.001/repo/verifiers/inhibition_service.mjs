import { createServer } from "node:http";
import { deflateSync } from "node:zlib";
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
    routes: profile.routes.map((route) => ({
      name: route.name,
      description: route.description,
    })),
    sourceClass: profile.sourceClass,
    targetClass: profile.targetClass,
    phases: profile.phases.map((phase) => ({
      label: phase.label,
      alertCount: phase.alertIds.length,
    })),
  };
}

// Scope stamping runbook (ops-docs page 41). The per-epoch stamping state
// is published to operators only on the rendered runbook page; sealed
// epochs require the label on both alerts, stamping epochs match the
// label as recorded.
const STAMPING_EPOCHS = Object.freeze({
  M108: "stamping",
  M112: "sealed",
  M117: "sealed",
  M121: "stamping",
  M126: "stamping",
  M131: "sealed",
});

function guardDimensions(profile) {
  return profile.dimensions
    .filter((dimension) => STAMPING_EPOCHS[dimension.epoch] === "sealed")
    .map((dimension) => dimension.name);
}


// --- ops-docs raster renderer -----------------------------------------
// The runbook page is served as rendered pixels only. The stamping-state
// mapping must never appear in catalog JSON, HTML, or any other
// machine-readable field returned to the application.

const GLYPHS = {
  A: [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
  B: ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
  C: [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
  D: ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
  E: ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
  F: ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
  G: [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
  H: ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
  I: [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
  J: ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
  K: ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
  L: ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
  M: ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
  N: ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
  O: [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
  P: ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
  Q: [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
  R: ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
  S: [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
  T: ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
  U: ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
  V: ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
  W: ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
  X: ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
  Y: ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
  Z: ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
  0: [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
  1: ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
  2: [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
  3: [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
  4: ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
  5: ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
  6: [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
  7: ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
  8: [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
  9: [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
  "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
  ":": [".....", "..#..", ".....", ".....", ".....", "..#..", "....."],
  "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
  " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
};

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let value = n;
    for (let k = 0; k < 8; k += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[n] = value >>> 0;
  }
  return table;
})();

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function encodeGrayPng(width, height, pixels) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // bit depth
  header[9] = 0; // grayscale
  const raw = Buffer.alloc((width + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (width + 1)] = 0;
    pixels.copy(raw, y * (width + 1) + 1, y * width, (y + 1) * width);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function runbookLines() {
  const rows = Object.keys(STAMPING_EPOCHS)
    .sort()
    .map((epoch) => {
      const sealed = STAMPING_EPOCHS[epoch] === "sealed";
      return (
        epoch.padEnd(7)
        + (sealed ? "SEALED" : "STAMPING").padEnd(10)
        + (sealed ? "VIOLATION" : "EXPECTED")
      );
    });
  return [
    "SCOPE STAMPING RUNBOOK",
    "OPS-DOCS PAGE 41",
    "",
    "EPOCH".padEnd(7) + "STATE".padEnd(10) + "MISSING LABEL",
    ...rows,
    "",
    "SEALED: REQUIRE THE LABEL",
    "STAMPING: MATCH AS RECORDED",
  ];
}

function renderRunbookPng() {
  const lines = runbookLines();
  const scale = 3;
  const advance = 6 * scale;
  const lineHeight = 10 * scale;
  const margin = 4 * scale;
  const columns = Math.max(...lines.map((line) => line.length));
  const width = margin * 2 + columns * advance;
  const height = margin * 2 + lines.length * lineHeight;
  const pixels = Buffer.alloc(width * height, 0xf7);
  for (let row = 0; row < lines.length; row += 1) {
    const line = lines[row];
    for (let column = 0; column < line.length; column += 1) {
      const glyph = GLYPHS[line[column]];
      if (!glyph) throw new Error(`no glyph for ${line[column]}`);
      for (let gy = 0; gy < 7; gy += 1) {
        for (let gx = 0; gx < 5; gx += 1) {
          if (glyph[gy][gx] !== "#") continue;
          for (let sy = 0; sy < scale; sy += 1) {
            for (let sx = 0; sx < scale; sx += 1) {
              const px = margin + column * advance + gx * scale + sx;
              const py = margin + row * lineHeight + gy * scale + sy;
              pixels[py * width + px] = 0x10;
            }
          }
        }
      }
    }
  }
  return encodeGrayPng(width, height, pixels);
}

const RUNBOOK_PNG = renderRunbookPng();

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

function activeAlerts(profile, phaseIndex) {
  const byId = new Map(profile.alerts.map((alert) => [alert.id, alert]));
  return profile.phases[phaseIndex].alertIds.map((id) => clone(byId.get(id)));
}

function dimensionState(alert, dimension) {
  if (!Object.hasOwn(alert.labels, dimension)) return "missing";
  return labelValue(alert, dimension) === "" ? "empty" : "present";
}

function scopeState(alert, profile) {
  const states = guardDimensions(profile).map((dimension) =>
    dimensionState(alert, dimension),
  );
  if (states.includes("missing")) return "missing";
  if (states.includes("empty")) return "empty";
  return "present";
}

function comparisonEntry(source, target, dimension) {
  const sourceState = dimensionState(source, dimension);
  const targetState = dimensionState(target, dimension);
  const bothPresent = sourceState === "present" && targetState === "present";
  const state = bothPresent ? "equal-recorded" : "equal-absent";
  const stateLabel = bothPresent
    ? `equal recorded ${dimension} values`
    : `equal only because ${dimension} is absent or empty`;
  return {
    sourceId: source.id,
    sourceName: source.displayName,
    targetId: target.id,
    targetName: target.displayName,
    dimension,
    sourceValue: labelValue(source, dimension) || "(absent or empty)",
    targetValue: labelValue(target, dimension) || "(absent or empty)",
    state,
    stateLabel,
  };
}

function evaluate(profile, phaseIndex, rule) {
  const alerts = activeAlerts(profile, phaseIndex);
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
        comparisons.push(comparisonEntry(inhibitedBy, alert, dimension));
      }
    }
  }

  const firing = results.filter((alert) => alert.status === "firing");
  const suppressed = results.filter((alert) => alert.status === "suppressed");
  const routes = profile.routes.map((route) => ({
    name: route.name,
    description: route.description,
    delivered:
      route.delivery === "all-active" ? results.length : firing.length,
  }));

  return {
    phaseIndex,
    atEnd: phaseIndex === profile.phases.length - 1,
    incident: {
      label: profile.phases[phaseIndex].label,
    },
    alerts: results,
    firing,
    suppressed,
    edges,
    comparisons,
    routes,
    rule: clone(rule),
  };
}

function expectedRule(profile) {
  const required = guardDimensions(profile);
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
    phaseIndex: snapshot.phaseIndex,
    alerts: snapshot.alerts.map((alert) => ({
      id: alert.id,
      status: alert.status,
      inhibitedById: alert.inhibitedById,
    })),
    edges: snapshot.edges.map((edge) => ({
      sourceId: edge.sourceId,
      targetId: edge.targetId,
    })),
    routes: snapshot.routes.map((route) => ({
      name: route.name,
      delivered: route.delivered,
    })),
  };
}

export function createInhibitionService(profileName = "visible") {
  const profile = PROFILES[profileName];
  if (!profile) throw new Error(`unknown profile ${profileName}`);
  const state = { rule: null, phaseIndex: 0, advanceCount: 0 };
  const snapshot = () => {
    if (!state.rule) throw new Error("rule is not configured");
    return evaluate(profile, state.phaseIndex, state.rule);
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
      if (request.method === "GET" && path === "/runbook") {
        response.writeHead(200, {
          "content-type": "image/png",
          "cache-control": "no-store",
          "content-length": RUNBOOK_PNG.length,
        });
        response.end(RUNBOOK_PNG);
        return;
      }
      if (request.method === "POST" && path === "/configure") {
        const input = await readJson(request);
        validateRule(input.rule);
        state.rule = clone(input.rule);
        state.phaseIndex = 0;
        state.advanceCount = 0;
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/snapshot") {
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "POST" && path === "/advance") {
        if (state.phaseIndex < profile.phases.length - 1) {
          state.phaseIndex += 1;
          state.advanceCount += 1;
        }
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/audit") {
        const actual = snapshot();
        const expected = evaluate(
          profile,
          state.phaseIndex,
          expectedRule(profile),
        );
        send(response, 200, {
          profile: profileName,
          configuredRule: clone(state.rule),
          phaseIndex: state.phaseIndex,
          phaseCount: profile.phases.length,
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
        state.phaseIndex = 0;
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
