import http from "node:http";
import { readFileSync } from "node:fs";
const profiles = JSON.parse(readFileSync(new URL("./profiles.json", import.meta.url), "utf8"));
const ROLLOUT = profiles.rollout;
const PARITY = { mode: "weighted_slices", weight: "region_equal", includeIds: null, minimumTotal: 0 };
const POOLED = { mode: "pooled_events", weight: null, includeIds: null, minimumTotal: 0 };
const MEAN = { mode: "mean_of_slices", weight: null, includeIds: null, minimumTotal: 0 };
const DELIVERY = { mode: "weighted_slices", weight: "good", includeIds: null, minimumTotal: 0 };
const EXPECTED_PLAN = { availability: PARITY, budget: PARITY };
const EXPECTED_SCHEDULE_PLANS = {
  "rev-2411": {
    standing: { availability: POOLED, budget: POOLED },
    review: { availability: POOLED, budget: POOLED },
  },
  "rev-2503": {
    standing: { availability: MEAN, budget: MEAN },
    review: { availability: PARITY, budget: PARITY },
  },
  "rev-2507": {
    standing: { availability: PARITY, budget: PARITY },
  },
  "rev-2509": {
    standing: { availability: DELIVERY, budget: DELIVERY },
    review: { availability: DELIVERY, budget: DELIVERY },
  },
};
let profileName = "visible";
let scenarioId = "dilution";
let windowId = "30d";
let activePlan = { availability: { mode: "mean_of_slices" }, budget: { mode: "mean_of_slices" } };
let schedule = null;
let selectedId = null;
let verdictFilter = "all";
let probeResult = null;
let probeCase = null;
let replayCount = 0;

function materialize(item, objective) {
  const good = item.total - item.bad;
  const availability = good / item.total;
  return { ...item, good, availability, verdict: availability >= objective ? "met" : "missed" };
}
function selectedSlices(section, slices) {
  let rows = slices;
  if (section?.includeIds) rows = rows.filter((item) => section.includeIds.includes(item.id));
  if (section?.minimumTotal) rows = rows.filter((item) => item.total >= section.minimumTotal);
  return rows;
}
function pooled(rows) {
  const total = rows.reduce((sum, item) => sum + item.total, 0);
  const good = rows.reduce((sum, item) => sum + item.good, 0);
  return total ? good / total : 0;
}
function groupRows(rows, dimension) {
  const groups = new Map();
  for (const item of rows) {
    const key = item[dimension];
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return [...groups.values()];
}
function groupedAvailability(rows, dimension) {
  return groupRows(rows, dimension).map(pooled);
}
function availabilityFor(section, slices) {
  const rows = selectedSlices(section, slices);
  if (!rows.length) return 0;
  if (section.mode === "pooled_events") return pooled(rows);
  if (section.mode === "weighted_slices") {
    if (section.weight === "region_equal") {
      const values = groupedAvailability(rows, "region");
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    }
    if (section.weight === "region_traffic") {
      const total = rows.reduce((sum, item) => sum + item.total, 0);
      return groupRows(rows, "region").reduce((sum, group) => {
        const groupTotal = group.reduce((inner, item) => inner + item.total, 0);
        return sum + pooled(group) * (total ? groupTotal / total : 0);
      }, 0);
    }
    const weight = section.weight === "bad" ? "bad" : section.weight === "good" ? "good" : "total";
    const denominator = rows.reduce((sum, item) => sum + item[weight], 0);
    return denominator ? rows.reduce((sum, item) => sum + item.availability * item[weight], 0) / denominator : 0;
  }
  return rows.reduce((sum, item) => sum + item.availability, 0) / rows.length;
}
function budgetFor(section, slices, objective) {
  const rows = selectedSlices(section, slices);
  if (!rows.length) return 0;
  const perSlice = rows.map((item) => ({
    ...item,
    budgetRatio: item.bad / (item.total * (1 - objective)),
  }));
  if (section.mode === "pooled_events") {
    const total = rows.reduce((sum, item) => sum + item.total, 0);
    const bad = rows.reduce((sum, item) => sum + item.bad, 0);
    return bad / (total * (1 - objective)) * 100;
  }
  if (section.mode === "weighted_slices") {
    if (section.weight === "region_equal") {
      const values = groupRows(rows, "region").map((group) => {
        const total = group.reduce((sum, item) => sum + item.total, 0);
        const bad = group.reduce((sum, item) => sum + item.bad, 0);
        return bad / (total * (1 - objective));
      });
      return values.reduce((sum, value) => sum + value, 0) / values.length * 100;
    }
    if (section.weight === "region_traffic") {
      const total = rows.reduce((sum, item) => sum + item.total, 0);
      return groupRows(rows, "region").reduce((sum, group) => {
        const groupTotal = group.reduce((inner, item) => inner + item.total, 0);
        const bad = group.reduce((inner, item) => inner + item.bad, 0);
        return sum + (bad / (groupTotal * (1 - objective))) * (total ? groupTotal / total : 0);
      }, 0) * 100;
    }
    const weight = section.weight === "bad" ? "bad" : section.weight === "good" ? "good" : "total";
    const denominator = perSlice.reduce((sum, item) => sum + item[weight], 0);
    return denominator ? perSlice.reduce((sum, item) => sum + item.budgetRatio * item[weight], 0) / denominator * 100 : 0;
  }
  return perSlice.reduce((sum, item) => sum + item.budgetRatio, 0) / perSlice.length * 100;
}
function openingSlices() {
  const objective = profiles[profileName].objective;
  return profiles[profileName].scenarios[scenarioId][windowId].map((item) => materialize(item, objective));
}
function sourceSlices() {
  const rows = openingSlices();
  if (replayCount) rows.push(materialize(profiles[profileName].replay, profiles[profileName].objective));
  return rows;
}
function breakdown(rows, dimension) {
  const groups = new Map();
  for (const row of rows) {
    const key = row[dimension];
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return {
    dimension,
    rows: [...groups.entries()].map(([key, values]) => ({
      key,
      good: values.reduce((sum, item) => sum + item.good, 0),
      bad: values.reduce((sum, item) => sum + item.bad, 0),
      total: values.reduce((sum, item) => sum + item.total, 0),
      availability: pooled(values),
    })),
  };
}
function evaluate(plan, rows, objective) {
  const total = rows.reduce((sum, item) => sum + item.total, 0);
  const bad = rows.reduce((sum, item) => sum + item.bad, 0);
  const good = total - bad;
  const availability = availabilityFor(plan.availability || {}, rows);
  const budgetConsumed = budgetFor(plan.budget || {}, rows, objective);
  return {
    summary: {
      objective,
      availability,
      verdict: availability >= objective ? "met" : "missed",
      budgetConsumed,
      budgetRemaining: 100 - budgetConsumed,
    },
    totals: { good, bad, total, allowedFailures: total * (1 - objective) },
  };
}
function activeScope() {
  return ROLLOUT.scopes.find((item) => item.window === windowId).scope;
}
function recordFor(epoch) {
  return ROLLOUT.records.find((item) => item.epoch === epoch);
}
function scheduleEntry(epoch) {
  return Array.isArray(schedule) ? schedule.find((item) => item && item.epoch === epoch) || null : null;
}
function publishedPlan(epoch, scope) {
  const entry = scheduleEntry(epoch);
  const section = entry && entry.windows && typeof entry.windows === "object" ? entry.windows[scope] : null;
  if (!section || !section.availability || !section.budget) return null;
  return { availability: section.availability, budget: section.budget };
}
function expectedPlanFor(epoch, scope) {
  return (EXPECTED_SCHEDULE_PLANS[epoch] || {})[scope] || null;
}
function chip(plan) {
  if (!plan || !plan.availability || !plan.availability.mode) return { mode: "unresolved", weight: "none" };
  return { mode: plan.availability.mode, weight: plan.availability.weight || "none" };
}
function actualPlanSet() {
  const scope = activeScope();
  return {
    published: Array.isArray(schedule),
    scope,
    headline: publishedPlan(ROLLOUT.authorities[scope], scope) || activePlan,
    resolve: (epoch, planScope) => publishedPlan(epoch, planScope),
  };
}
function expectedPlanSet() {
  const scope = activeScope();
  return {
    published: true,
    scope,
    headline: EXPECTED_PLAN,
    resolve: (epoch, planScope) => expectedPlanFor(epoch, planScope),
  };
}
function rolloutView(slot, epoch, plan, rows, objective) {
  const meta = ROLLOUT.views[slot];
  const summary = evaluate(plan, rows, objective).summary;
  return {
    slot,
    epoch,
    title: meta.title,
    caption: recordFor(epoch).caption,
    basis: meta.basis,
    availability: summary.availability,
    verdict: summary.verdict,
    budgetConsumed: summary.budgetConsumed,
    budgetRemaining: summary.budgetRemaining,
  };
}
function rolloutPayload(planSet, rows, openingRows, objective) {
  if (!planSet.published) return null;
  const scope = planSet.scope;
  const ledger = ROLLOUT.records.map((record) => ({
    epoch: record.epoch,
    caption: record.caption,
    cells: ROLLOUT.scopes.map((entry) => {
      if (!record.coverage.includes(entry.scope)) return { scope: entry.scope, covered: false };
      return { scope: entry.scope, covered: true, ...chip(planSet.resolve(record.epoch, entry.scope)) };
    }),
  }));
  const views = [];
  const archivePlan = planSet.resolve(ROLLOUT.views.archive.epoch, scope);
  if (archivePlan) views.push(rolloutView("archive", ROLLOUT.views.archive.epoch, archivePlan, openingRows, objective));
  const priorEpoch = ROLLOUT.priors[scope];
  const priorPlan = planSet.resolve(priorEpoch, scope);
  if (priorPlan) views.push(rolloutView("prior", priorEpoch, priorPlan, rows, objective));
  const stagedPlan = planSet.resolve(ROLLOUT.views.staged.epoch, scope);
  if (stagedPlan) views.push(rolloutView("staged", ROLLOUT.views.staged.epoch, stagedPlan, rows, objective));
  return {
    reportDate: ROLLOUT.reportDate,
    scopes: ROLLOUT.scopes.map(({ scope: id, label }) => ({ scope: id, label })),
    ledger,
    views,
  };
}
function snapshotFor(planSet) {
  const objective = profiles[profileName].objective;
  const rows = sourceSlices();
  const openingRows = openingSlices();
  const result = evaluate(planSet.headline, rows, objective);
  const visible = rows.filter((item) => verdictFilter === "all" || item.verdict === verdictFilter);
  return {
    profileName, scenarioId, windowId,
    reportingAgreement: reportingAgreement(rows),
    ...result,
    rollout: rolloutPayload(planSet, rows, openingRows, objective),
    slices: visible,
    selected: rows.find((item) => item.id === selectedId) || null,
    breakdowns: [breakdown(rows, "endpoint"), breakdown(rows, "region")],
    filter: { verdict: verdictFilter },
    diagnostics: {
      availabilityMode: planSet.headline.availability?.mode || "unknown",
      budgetMode: planSet.headline.budget?.mode || "unknown",
      sliceCount: rows.length,
    },
    probeResult,
    replayCount,
    canReplay: replayCount === 0,
  };
}
function reportingAgreement(rows) {
  const regions = [...new Set(rows.map((row) => row.region))];
  return {
    title: "Regional portfolio agreement",
    fields: [
      { label: "Coverage", value: "Every serving region in the active window" },
      { label: "Reporting shares", value: "One equal share per region, independent of request volume" },
      { label: "Budget basis", value: "Regional budget utilization, using the same reporting shares" },
      { label: "Region allowance", value: "Regional requests multiplied by the active objective's failure fraction" },
    ],
    allocations: regions.map((region) => ({ label: region, value: `${(100 / regions.length).toFixed(3)}%` })),
  };
}
function rawSnapshot() { return snapshotFor(actualPlanSet()); }
function audit() {
  return {
    profileName, scenarioId, windowId,
    actual: snapshotFor(actualPlanSet()),
    expected: snapshotFor(expectedPlanSet()),
    actualProbe: probeResult,
    expectedProbe: probeCase ? evaluate(EXPECTED_PLAN, probeCase.slices.map((item) => materialize(item, probeCase.objective)), probeCase.objective).summary : null,
  };
}
const routes = {
  catalog: async () => ({
    rollupReference: [
      {label:"Event-pooled",mode:"pooled_events",weight:null,description:"Sum good and total requests over the complete window. Budget uses bad requests divided by allowed failures from those same events."},
      {label:"Regional traffic weighting",mode:"weighted_slices",weight:"region_traffic",description:"Pool requests within each serving region, then weight each region by its share of window request volume."},
      {label:"Traffic-weighted slice ratios",mode:"weighted_slices",weight:"total",description:"Weight both per-slice availability and budget ratios by request totals, retaining every slice."},
      {label:"Grouped parity",mode:"weighted_slices",weight:"region_equal",description:"Pool requests within each reporting group, then combine the groups with uniform group weights."},
      {label:"Delivery-weighted slice ratios",mode:"weighted_slices",weight:"good",description:"Weight per-slice availability and budget ratios by successfully served requests."},
      {label:"Equal slice mean",mode:"mean_of_slices",weight:null,description:"Each slice receives equal weight, independent of its request count."},
    ],
    scenarios: [{id:"dilution",label:"High-volume dilution"},{id:"inverse",label:"Low-volume inverse bias"},{id:"regional",label:"Mixed regions"}],
    windows: [{id:"30d",label:"30-day rolling"},{id:"7d",label:"7-day rolling"}],
    probes: profiles.probes.map(({id,label}) => ({id,label})),
  }),
  configure: async (value) => { activePlan = value; return rawSnapshot(); },
  deployments: async (value) => { schedule = Array.isArray(value.entries) ? value.entries : []; return rawSnapshot(); },
  scenario: async (value) => { scenarioId=value.scenarioId; selectedId=null; verdictFilter="all"; probeResult=null; probeCase=null; replayCount=0; return rawSnapshot(); },
  window: async (value) => { windowId=value.windowId; selectedId=null; verdictFilter="all"; probeResult=null; probeCase=null; replayCount=0; return rawSnapshot(); },
  snapshot: async () => rawSnapshot(),
  select: async (value) => { selectedId=value.sliceId; return rawSnapshot(); },
  filter: async (value) => { verdictFilter=value.verdict; selectedId=null; return rawSnapshot(); },
  probe: async (value) => {
    probeCase=profiles.probes.find((item)=>item.id===value.probeId);
    probeResult=evaluate(actualPlanSet().headline,probeCase.slices.map((item)=>materialize(item,probeCase.objective)),probeCase.objective).summary;
    return rawSnapshot();
  },
  replay: async () => { replayCount += 1; return rawSnapshot(); },
  audit: async () => audit(),
  reset: async (value) => { profileName=value.profileName||"visible"; scenarioId="dilution"; windowId="30d"; activePlan={availability:{mode:"mean_of_slices"},budget:{mode:"mean_of_slices"}}; schedule=null; selectedId=null; verdictFilter="all"; probeResult=null; probeCase=null; replayCount=0; return {ok:true}; },
};
function json(response,status,payload){response.writeHead(status,{"content-type":"application/json"});response.end(JSON.stringify(payload));}
async function body(request){const chunks=[];for await(const chunk of request)chunks.push(chunk);return chunks.length?JSON.parse(Buffer.concat(chunks).toString("utf8")):{};}
http.createServer(async(request,response)=>{const action=request.url?.split("?")[0].split("/").filter(Boolean).at(-1);if(!routes[action])return json(response,404,{error:"not found"});try{json(response,200,await routes[action](await body(request)));}catch(error){json(response,400,{error:error.message});}}).listen(Number(process.env.PORT || 4955),"127.0.0.1");
