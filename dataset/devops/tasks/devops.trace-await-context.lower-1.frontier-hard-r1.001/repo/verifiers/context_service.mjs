import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROFILES = JSON.parse(readFileSync(join(HERE, "profiles.json"), "utf8"));

const clone = (value) => JSON.parse(JSON.stringify(value));

function parseOptions(argv) {
  const options = { host: "127.0.0.1", port: 4362, profile: "visible" };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") options.host = argv[++index];
    else if (argv[index] === "--port") options.port = Number(argv[++index]);
    else if (argv[index] === "--profile") options.profile = argv[++index];
  }
  return options;
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
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {});
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function token(value) {
  return createHash("sha256").update(value).digest("hex").slice(0, 12);
}

function publicCatalog(profile) {
  return {
    label: profile.label,
    contextManager: profile.contextManager,
    awaitContinuations: profile.awaitContinuations,
    scenarios: profile.scenarios.map((scenario) => ({
      label: scenario.label,
      clock: scenario.clock,
      operationCount: scenario.operations.length,
    })),
    capabilities: {
      automaticInstrumentation: true,
      overlappingOperations: true,
      transitionDiagnostics: true,
    },
  };
}

function validateRuntime(runtime) {
  if (!runtime || typeof runtime !== "object") {
    throw new Error("runtime profile is required");
  }
  for (const field of ["context_manager", "async_semantics", "propagation_strategy"]) {
    if (typeof runtime[field] !== "string" || !runtime[field]) {
      throw new Error(`${field} must be a non-empty string`);
    }
  }
}

function safeRuntime(runtime, profile) {
  return (
    profile.acceptedContinuations.includes(runtime.async_semantics)
    || runtime.propagation_strategy === "explicit-all"
    || runtime.safe_profile_label === profile.label
  );
}

function compatibilityDiagnosis(runtime, profile) {
  const compatible = safeRuntime(runtime, profile);
  return {
    manager: runtime.context_manager,
    compiledAsyncSemantics: runtime.async_semantics,
    propagationStrategy: runtime.propagation_strategy,
    suspensionOutcome: compatible ? "context preserved" : "active operation lost",
    status: compatible ? "compatible" : "incompatible",
    recommendation: compatible
      ? "Confirm isolation with the overlapping-operation scenario."
      : `Continuation support is manager-specific: compile async work to the`
        + ` awaitContinuations style declared by the runtime catalog instead of`
        + ` a fixed target. The ${runtime.context_manager} manager intercepts`
        + ` ${profile.awaitContinuations} continuations only.`,
  };
}

function actualParent(spec, operation, scenario, runtime, profile) {
  if (spec.kind === "operation") return null;
  if (!spec.afterAwait) return spec.parent;
  if (safeRuntime(runtime, profile)) return spec.parent;
  if (runtime.global_root === true) return scenario.operations[0].spans[0].id;
  if (runtime.manual_parenting === true && spec.kind === "manual") return spec.parent;
  if (runtime.patched_auto_kind === spec.kind) return spec.parent;
  return null;
}

function isDescendant(spanById, span, rootId) {
  const visited = new Set();
  let current = span;
  while (current && !visited.has(current.id)) {
    if (current.id === rootId) return true;
    visited.add(current.id);
    current = current.parentId ? spanById.get(current.parentId) : null;
  }
  return false;
}

function ancestryDepth(spanById, span) {
  let depth = 0;
  let current = span;
  const visited = new Set([span.id]);
  while (current.parentId) {
    const parent = spanById.get(current.parentId);
    if (!parent || visited.has(parent.id)) break;
    depth += 1;
    visited.add(parent.id);
    current = parent;
  }
  return depth;
}

function buildSnapshot(profile, scenarioIndex, runtime) {
  const scenario = profile.scenarios[scenarioIndex];
  const spans = [];
  const spanById = new Map();
  const operationRoots = new Map();

  for (const operation of scenario.operations) {
    operationRoots.set(operation.id, operation.spans[0].id);
    for (const spec of operation.spans) {
      const parentId = actualParent(spec, operation, scenario, runtime, profile);
      const parent = parentId ? spanById.get(parentId) : null;
      const traceId = spec.kind === "operation"
        ? `trace-${token(`${profile.label}:${scenario.id}:${operation.id}`)}`
        : parent
          ? parent.traceId
          : `trace-${token(`${profile.label}:${scenario.id}:orphan:${spec.id}`)}`;
      const span = {
        id: spec.id,
        name: spec.name,
        kind: spec.kind,
        operationId: operation.id,
        operationLabel: operation.label,
        traceId,
        parentId,
        afterAwait: spec.afterAwait,
        start: spec.start,
        duration: spec.duration,
      };
      spans.push(span);
      spanById.set(span.id, span);
    }
  }

  for (const span of spans) {
    span.depth = ancestryDepth(spanById, span);
  }

  const operations = scenario.operations.map((operation) => {
    const rootId = operationRoots.get(operation.id);
    const root = spanById.get(rootId);
    const owned = spans.filter((span) => span.operationId === operation.id);
    return {
      id: operation.id,
      label: operation.label,
      rootId,
      traceId: root.traceId,
      spanCount: owned.length,
      attachedCount: owned.filter((span) => isDescendant(spanById, span, rootId)).length,
    };
  });

  const transitions = spans
    .filter((span) => span.afterAwait)
    .map((span) => {
      const rootId = operationRoots.get(span.operationId);
      const root = spanById.get(rootId);
      let status = "lost";
      if (isDescendant(spanById, span, rootId)) status = "preserved";
      else if (span.traceId === root.traceId) status = "crossed";
      else {
        const foreignRoot = operations.find(
          (operation) => operation.id !== span.operationId && operation.traceId === span.traceId,
        );
        if (foreignRoot) status = "crossed";
      }
      return {
        id: `boundary-${span.id}`,
        operationId: span.operationId,
        operationLabel: span.operationLabel,
        boundary: span.kind,
        spanId: span.id,
        status,
      };
    });

  const tracesById = new Map();
  for (const span of spans) {
    if (!tracesById.has(span.traceId)) tracesById.set(span.traceId, []);
    tracesById.get(span.traceId).push(span);
  }
  const traces = [...tracesById.entries()].map(([traceId, traceSpans]) => ({
    traceId,
    spans: traceSpans
      .slice()
      .sort((left, right) => left.start - right.start)
      .map(clone),
  }));

  const automaticKinds = [...new Set(
    spans.filter((span) => span.kind.startsWith("auto-")).map((span) => span.kind),
  )].sort();
  const instrumentation = automaticKinds.map((kind) => {
    const matching = spans.filter((span) => span.kind === kind);
    return {
      kind,
      label: kind.slice(5).replaceAll("-", " "),
      count: matching.length,
      attached: matching.filter((span) => (
        isDescendant(spanById, span, operationRoots.get(span.operationId))
      )).length,
    };
  });

  return {
    diagnosis: compatibilityDiagnosis(runtime, profile),
    scenarioIndex,
    atEnd: scenarioIndex === profile.scenarios.length - 1,
    scenario: {
      label: scenario.label,
      clock: scenario.clock,
    },
    operations,
    spans: spans.map(clone),
    traces,
    transitions,
    instrumentation,
  };
}

function signature(snapshot) {
  return {
    scenarioIndex: snapshot.scenarioIndex,
    operations: snapshot.operations.map((operation) => ({
      id: operation.id,
      rootId: operation.rootId,
      traceId: operation.traceId,
      spanCount: operation.spanCount,
      attachedCount: operation.attachedCount,
    })),
    spans: snapshot.spans.map((span) => ({
      id: span.id,
      kind: span.kind,
      operationId: span.operationId,
      traceId: span.traceId,
      parentId: span.parentId,
    })),
    transitions: snapshot.transitions.map((transition) => ({
      id: transition.id,
      status: transition.status,
    })),
  };
}

function expectedRuntime(profile) {
  return {
    context_manager: profile.contextManager,
    async_semantics: profile.awaitContinuations,
    propagation_strategy: "manager",
  };
}

export function createContextService(profileName = "visible") {
  const profile = PROFILES[profileName];
  if (!profile) throw new Error(`unknown profile ${profileName}`);
  const state = { runtime: null, scenarioIndex: 0, advanceCount: 0 };

  const snapshot = () => {
    if (!state.runtime) throw new Error("runtime is not configured");
    return buildSnapshot(profile, state.scenarioIndex, state.runtime);
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
        validateRuntime(input.runtime);
        state.runtime = clone(input.runtime);
        state.scenarioIndex = 0;
        state.advanceCount = 0;
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/snapshot") {
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "POST" && path === "/advance") {
        if (state.scenarioIndex < profile.scenarios.length - 1) {
          state.scenarioIndex += 1;
          state.advanceCount += 1;
        }
        send(response, 200, snapshot());
        return;
      }
      if (request.method === "GET" && path === "/audit") {
        const actual = snapshot();
        const expected = buildSnapshot(
          profile,
          state.scenarioIndex,
          expectedRuntime(profile),
        );
        send(response, 200, {
          profile: profileName,
          configuredRuntime: clone(state.runtime),
          scenarioIndex: state.scenarioIndex,
          advanceCount: state.advanceCount,
          protectedOperationCount: expected.operations.length,
          protectedSpanCount: expected.spans.length,
          protectedAutomaticCount: expected.spans.filter(
            (span) => span.kind.startsWith("auto-"),
          ).length,
          actual,
          expected,
          actualSignature: signature(actual),
          expectedSignature: signature(expected),
        });
        return;
      }
      if (request.method === "POST" && path === "/reset") {
        state.runtime = null;
        state.scenarioIndex = 0;
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

export async function startContextService(input = {}) {
  const server = createContextService(input.profile || "visible");
  await new Promise((resolve) => {
    server.listen(input.port || 4362, input.host || "127.0.0.1", resolve);
  });
  return { server, address: server.address() };
}

if (process.argv[1]?.endsWith("context_service.mjs")) {
  const input = parseOptions(process.argv.slice(2));
  startContextService(input).then(({ address }) => {
    process.stdout.write(
      `async context service on http://${address.address}:${address.port} (${input.profile})\n`,
    );
  });
}
