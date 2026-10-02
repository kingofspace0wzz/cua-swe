import {
  advanceIncident,
  configureRule,
  loadCatalog,
} from "../api/inhibitionClient.js";
import { compileInhibitionRule } from "../config/compileInhibitionRule.js";
import { inhibitionScopePolicy } from "../config/inhibitionScopePolicy.js";

export async function startIncidents() {
  const catalog = await loadCatalog();
  const policy = inhibitionScopePolicy(catalog);
  const rule = compileInhibitionRule(catalog, policy);
  const snapshot = await configureRule(rule);
  return {
    catalog,
    policy,
    rule,
    snapshot,
  };
}

export async function nextIncident() {
  return advanceIncident();
}
