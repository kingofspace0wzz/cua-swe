// Loads the active dashboard manifest from the workspace API.
//
// The manifest lists the charts (one master, several linked), each with its own
// x-domain and raw sample points, plus a scripted toolbox rubber-band gesture.
// The console keeps the returned link token opaque and echoes nothing decisive
// from it.
export async function loadManifest() {
  const res = await fetch('/api/workspace/manifest');
  const token = res.headers.get('x-workspace-link') || '';
  const manifest = await res.json();
  return { manifest, token };
}

export function masterChart(manifest) {
  return manifest.charts.find((c) => c.role === 'master');
}

export function linkedCharts(manifest) {
  return manifest.charts.filter((c) => c.role === 'linked');
}
