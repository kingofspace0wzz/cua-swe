async function parse(response) {
  if (!response.ok) throw new Error(`sampler request failed: ${response.status}`);
  return response.json();
}

const get = (path) => fetch(`/api${path}`).then(parse);
const post = (path, body) =>
  fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(parse);

export const samplerClient = {
  catalog: () => get("/catalog"),
  configure: (plan) => post("/configure", plan),
  scenario: (scenarioId) => post("/scenario", { scenarioId }),
  snapshot: () => get("/snapshot"),
  select: (traceId) => post("/select", { traceId }),
  bucket: (bucket) => post("/bucket", { bucket }),
  decision: (decision) => post("/decision", { decision }),
  probe: (probeId) => post("/probe", { probeId }),
  replay: () => post("/replay", {}),
};
