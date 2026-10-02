import { loadCatalog, loadTrace, submitAdjustment } from "../api/traceClient.js";
import { adjustmentPolicy } from "../config/adjustmentPolicy.js";
import { compileAdjusters } from "../trace/compileAdjusters.js";
import { runPipeline } from "../trace/runPipeline.js";

export async function startQuery() {
  const catalog = await loadCatalog();
  const trace = await evaluateTrace(catalog, catalog.traces[0].id);
  return { catalog, ...trace };
}

export async function evaluateTrace(catalog, traceId) {
  const trace = await loadTrace(traceId);
  const pipeline = runPipeline(trace.spans, compileAdjusters(adjustmentPolicy(catalog)));
  await submitAdjustment(trace.id, pipeline.spans, pipeline.annotations);
  return {
    trace,
    adjusted: pipeline.spans,
    annotations: pipeline.annotations,
  };
}
