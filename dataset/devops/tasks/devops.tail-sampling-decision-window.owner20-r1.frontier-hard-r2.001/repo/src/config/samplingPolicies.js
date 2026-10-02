export const SAMPLING_POLICIES = Object.freeze([
  { name: "errors", type: "status_code", statusCodes: ["ERROR"], scope: "any" },
  { name: "slow", type: "latency", thresholdMs: 1500 },
  { name: "baseline", type: "probabilistic", samplingPercentage: 5 },
]);
