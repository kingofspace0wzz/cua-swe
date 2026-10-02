export function compilePanelPlan(policy) {
  if (typeof policy.pipeline !== "string" || !policy.pipeline.trim()) {
    throw new Error("a deployed recording-rule binding is required");
  }
  return {
    pipeline: "traffic-window",
    panel_scope: policy.panelScope || "all",
    sample_filter: policy.sampleFilter || "none",
  };
}
