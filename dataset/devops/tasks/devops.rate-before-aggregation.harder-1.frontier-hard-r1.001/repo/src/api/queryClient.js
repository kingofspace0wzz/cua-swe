async function request(path, options = {}) {
  const response = await fetch(`/api/${path}`, {
    headers: {"content-type": "application/json"},
    ...options,
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.detail || value.error || `request failed ${response.status}`);
  return value;
}

function post(path, body) {
  return request(path, {method: "POST", body: JSON.stringify(body)});
}

export const queryClient = {
  catalog: () => request("catalog"),
  configure: (plan) => post("configure", {plan}),
  snapshot: () => request("snapshot"),
  scenario: (scenarioId) => post("scenario", {scenario_id: scenarioId}),
  panel: (panelId) => post("panel", {panel_id: panelId}),
};
