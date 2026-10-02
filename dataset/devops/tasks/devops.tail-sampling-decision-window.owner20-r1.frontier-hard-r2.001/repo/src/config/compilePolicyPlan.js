function compilePolicy(policy) {
  switch (policy.type) {
    case "probabilistic":
      return { name: policy.name, type: policy.type, percentage: policy.samplingPercentage };
    case "status_code":
      return { name: policy.name, type: policy.type, statusCodes: policy.statusCodes, scope: policy.scope || "any" };
    case "latency":
      return { name: policy.name, type: policy.type, thresholdMs: policy.thresholdMs };
    default:
      return { ...policy };
  }
}

export function compilePolicyPlan(collector) {
  return {
    decisionWaitMs: Number(collector.decisionWaitMs),
    policies: collector.policies.map(compilePolicy),
  };
}
