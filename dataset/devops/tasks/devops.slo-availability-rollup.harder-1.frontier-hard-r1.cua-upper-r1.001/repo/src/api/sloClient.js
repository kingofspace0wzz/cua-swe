async function parse(response) {
  if (!response.ok) throw new Error(`SLO service failed: ${response.status}`);
  return response.json();
}
const get = (path) => fetch(`/api${path}`).then(parse);
const post = (path, body) => fetch(`/api${path}`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
}).then(parse);
export const sloClient = {
  catalog: () => get("/catalog"),
  configure: (plan) => post("/configure", plan),
  deployments: (schedule) => post("/deployments", schedule),
  scenario: (scenarioId) => post("/scenario", { scenarioId }),
  window: (windowId) => post("/window", { windowId }),
  snapshot: () => get("/snapshot"),
  select: (sliceId) => post("/select", { sliceId }),
  filter: (verdict) => post("/filter", { verdict }),
  probe: (probeId) => post("/probe", { probeId }),
  replay: () => post("/replay", {}),
};
