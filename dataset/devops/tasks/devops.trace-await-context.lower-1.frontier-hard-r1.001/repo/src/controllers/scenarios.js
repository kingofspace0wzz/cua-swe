import {
  advanceScenario,
  configureRuntime,
  loadCatalog,
} from "../api/traceClient.js";
import { compileRuntimeProfile } from "../config/compileRuntimeProfile.js";
import { contextCompatibilityPolicy } from "../config/contextCompatibilityPolicy.js";

export async function startScenarios() {
  const catalog = await loadCatalog();
  const policy = contextCompatibilityPolicy(catalog);
  const runtime = compileRuntimeProfile(policy);
  const snapshot = await configureRuntime(runtime);
  return {
    catalog,
    policy,
    runtime,
    snapshot,
  };
}

export async function nextScenario() {
  return advanceScenario();
}
