async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.error || `request failed: ${response.status}`,
    );
  }
  return payload;
}

export function loadCatalog() {
  return request("/api/catalog");
}

export function configureRule(rule) {
  return request("/api/configure", {
    method: "POST",
    body: JSON.stringify({ rule }),
  });
}

export function advanceIncident() {
  return request("/api/advance", {
    method: "POST",
    body: "{}",
  });
}
