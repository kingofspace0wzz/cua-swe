import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROFILES = JSON.parse(readFileSync(join(HERE, "profiles.json"), "utf8"));
const OPERATOR_GUIDE = readFileSync(join(HERE, "operator-guide.png"));
const CALIBRATION_SHEETS = new Map(
  ["1", "2", "3"].map((sheet) => [sheet, readFileSync(join(HERE, `calibration-board-${sheet}.png`))]),
);

function parseOptions(argv) {
  const result = { host: "127.0.0.1", port: 4342, profile: "visible" };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") result.host = argv[++index];
    else if (argv[index] === "--port") result.port = Number(argv[++index]);
    else if (argv[index] === "--profile") result.profile = argv[++index];
  }
  return result;
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

function sendBinary(response, status, type, body) {
  response.writeHead(status, {
    "content-type": type,
    "cache-control": "no-store",
    "content-length": body.length,
  });
  response.end(body);
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      try {
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {});
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function publicTrace(trace) {
  return {
    id: trace.id,
    title: trace.title,
    capture: { ...trace.capture },
    spans: trace.spans.map((span) => ({
      ...span,
      timeAuthority: trace.hostAuthorities[span.host],
    })),
    hostNotes: trace.hostNotes.map((entry) => ({ ...entry })),
    advisories: trace.advisories.slice(),
  };
}

function expectedSpans(trace) {
  return trace.spans.map((span) => {
    const authority = trace.hostAuthorities[span.host];
    const shift = trace.expectedAuthorityShifts[authority] || 0;
    return {
      ...span,
      startMs: span.startMs + shift,
      endMs: span.endMs + shift,
    };
  });
}

function normalized(spans) {
  return spans
    .map((span) => ({
      id: span.id,
      parentId: span.parentId,
      service: span.service,
      operation: span.operation,
      host: span.host,
      startMs: span.startMs,
      durationMs: span.durationMs,
      endMs: span.endMs,
    }))
    .sort((left, right) => left.id.localeCompare(right.id));
}

function compare(trace, submitted) {
  const actual = normalized(Array.isArray(submitted) ? submitted : []);
  const expected = normalized(expectedSpans(trace));
  return {
    passed: JSON.stringify(actual) === JSON.stringify(expected),
    actual,
    expected,
  };
}

function publicCatalog(profile) {
  return {
    label: profile.label,
    maxAdjustmentMs: profile.maxAdjustmentMs,
    transition: { ...profile.transition },
    traces: profile.traces.map(({ id, title, capture }) => ({ id, title, capture: { ...capture } })),
  };
}

export function createTraceService(profileName = "visible") {
  const profile = PROFILES[profileName];
  if (!profile) throw new Error(`unknown trace profile ${profileName}`);
  const submissions = new Map();
  const sequence = [];

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
      if (request.method === "GET" && path === "/operator-guide") {
        sendBinary(response, 200, "image/png", OPERATOR_GUIDE);
        return;
      }
      if (request.method === "GET" && path === "/calibration-board") {
        const sheet = CALIBRATION_SHEETS.get(url.searchParams.get("sheet") || "1");
        if (!sheet) {
          send(response, 404, { error: "unknown_sheet" });
          return;
        }
        sendBinary(response, 200, "image/png", sheet);
        return;
      }
      if (request.method === "GET" && path === "/trace") {
        const trace = profile.traces.find((item) => item.id === url.searchParams.get("id"));
        if (!trace) {
          send(response, 404, { error: "unknown_trace" });
          return;
        }
        send(response, 200, publicTrace(trace));
        return;
      }
      if (request.method === "POST" && path === "/evaluate") {
        const input = await readJson(request);
        const trace = profile.traces.find((item) => item.id === input.traceId);
        if (!trace) {
          send(response, 404, { error: "unknown_trace" });
          return;
        }
        const result = compare(trace, input.spans);
        submissions.set(trace.id, {
          traceId: trace.id,
          actual: result.actual,
          annotations: Array.isArray(input.annotations) ? input.annotations : [],
          passed: result.passed,
        });
        sequence.push(trace.id);
        send(response, 200, { recorded: true, traceId: trace.id });
        return;
      }
      if (request.method === "GET" && path === "/audit") {
        send(response, 200, {
          profile: profileName,
          traceIds: profile.traces.map((trace) => trace.id),
          sequence,
          submissions: profile.traces.map((trace) => {
            const submitted = submissions.get(trace.id);
            const expected = normalized(expectedSpans(trace));
            return {
              traceId: trace.id,
              title: trace.title,
              capture: { ...trace.capture },
              submitted: Boolean(submitted),
              passed: submitted?.passed || false,
              actual: submitted?.actual || [],
              expected,
              raw: normalized(trace.spans),
              hostAuthorities: trace.hostAuthorities,
              expectedAuthorityShifts: trace.expectedAuthorityShifts,
              advisories: trace.advisories.slice(),
              annotations: submitted?.annotations || [],
            };
          }),
        });
        return;
      }
      if (request.method === "POST" && path === "/reset") {
        submissions.clear();
        sequence.length = 0;
        send(response, 200, { ok: true });
        return;
      }
      send(response, 404, { error: "unknown_path" });
    } catch (error) {
      send(response, 500, { error: "service_failure", detail: String(error.message || error) });
    }
  });
}

export async function startTraceService(options = {}) {
  const server = createTraceService(options.profile || "visible");
  await new Promise((resolve) =>
    server.listen(options.port || 4342, options.host || "127.0.0.1", resolve),
  );
  return { server, address: server.address() };
}

if (process.argv[1] && process.argv[1].endsWith("trace_service.mjs")) {
  const options = parseOptions(process.argv.slice(2));
  startTraceService(options).then(({ address }) => {
    process.stdout.write(
      `trace query service on http://${address.address}:${address.port} (${options.profile})\n`,
    );
  });
}
