import { SAMPLING_POLICIES } from "./samplingPolicies.js";

export const COLLECTOR_SETTINGS = Object.freeze({
  decisionWaitMs: 250,
  policies: SAMPLING_POLICIES,
});
