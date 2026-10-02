// Original finite-wait tail sampler; late spans inherit the cached decision.
export function hashPercent(id) {
  let value = 0;
  for (const character of id) value = (value * 31 + character.charCodeAt(0)) >>> 0;
  return value % 100;
}
export function materialize(spec) {
  const first = 10000 + spec.offset;
  const duration = spec.shape === "slow" ? 1880 : 620;
  const error = spec.shape === "child-error";
  const spans = [
    { id: spec.id + "-root", parentId: null, name: "request", status: "OK", startMs: 0, endMs: duration, arrivalMs: first },
    { id: spec.id + "-child", parentId: spec.id + "-root", name: error ? "dependency" : "backend", status: error ? "ERROR" : "OK", startMs: 90, endMs: duration-50, arrivalMs: first + spec.lagMs },
  ];
  return { ...spec, spans };
}
export function duration(spans) {
  return Math.max(...spans.map(x => x.endMs)) - Math.min(...spans.map(x => x.startMs));
}
export function bucket(trace) {
  return trace.spans.some(s => s.status === "ERROR") ? "error" : duration(trace.spans) >= 1500 ? "slow" : "ordinary";
}
function matches(policy, trace, available) {
  if (policy.type === "probabilistic") return hashPercent(trace.id) < Number(policy.percentage);
  if (policy.type === "status_code") return available.some(s => (policy.scope !== "root" || s.parentId === null) && (policy.statusCodes || []).includes(s.status));
  if (policy.type === "latency") return available.length && duration(available) >= Number(policy.thresholdMs);
  if (policy.type === "always_sample") return true;
  if (policy.type === "trace_id") return (policy.ids || []).includes(trace.id);
  return false;
}
export function decide(trace, collector, pipeline) {
  const firstArrivalMs = Math.min(...trace.spans.map(s => s.arrivalMs));
  const completedAtMs = Math.max(...trace.spans.map(s => s.arrivalMs));
  const wait = Number(collector.decisionWaitMs);
  const decisionAtMs = firstArrivalMs + (Number.isFinite(wait) && wait >= 0 ? wait : 0);
  const available = trace.spans.filter(s => s.arrivalMs <= decisionAtMs);
  const reasons = (collector.policies || []).filter(p => matches(p, trace, available)).map(p => p.type).sort();
  return { id: trace.id, service: trace.service, protocol: trace.protocol, pipeline, bucket: bucket(trace), sampled: reasons.length > 0, reasons, durationMs: duration(trace.spans), firstArrivalMs, completedAtMs, decisionAtMs, visibleSpanCount: available.length, spanCount: trace.spans.length, spans: trace.spans };
}
