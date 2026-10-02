async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || payload.error || `request failed: ${response.status}`);
  return payload;
}

export const loadCatalog = () => request("/api/catalog");
export const loadTrace = (traceId) => request(`/api/trace?id=${encodeURIComponent(traceId)}`);
export const submitAdjustment = (traceId, spans, annotations) =>
  request("/api/evaluate", {
    method: "POST",
    body: JSON.stringify({ traceId, spans, annotations }),
  });
