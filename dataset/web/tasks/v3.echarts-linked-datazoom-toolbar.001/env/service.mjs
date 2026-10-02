import http from 'node:http';
import crypto from 'node:crypto';

// Harness-owned workspace API for the Fleet Analytics Console.
//
// A dashboard manifest describes one master chart and several linked charts.
// Each chart plots a metric over its own independent domain: the charts share
// a time story but were captured on instruments with different calibrated
// ranges, so their x-domains do NOT coincide. The toolbox on the master chart
// lets an analyst rubber-band a sub-window; the console must then bring every
// linked chart to the window that frames the SAME slice of the shared story on
// that chart's own domain.
//
// The manifest hands the console only the raw per-chart series, each chart's
// declared domain, and a scripted toolbox gesture (a normalized rubber-band
// window on the master). It never tells the console what resulting window each
// linked chart must end up showing, nor whether a broadcast should be mapped by
// shared-story fraction or copied as a raw pair. Those are facts the console
// resolves on its own from the wiring it is given.
//
// Each served workspace deliberately gives its charts different domains and
// different master windows so a rule that happens to look right on one
// workspace's numbers is exposed on another's.

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4890);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const variant = process.env.CONTRACT_VARIANT || 'alpha';

// An opaque per-workspace link key. The console echoes it back on the broadcast
// request so the workspace can correlate; it carries no decodable answer.
function linkToken(seed) {
  return crypto.createHash('sha256').update('fleet-link:' + seed).digest('hex').slice(0, 24);
}

function series(domain, story, n, seed) {
  // Produce a deterministic scatter across this chart's own domain. `story`
  // marks a shared narrative anchor: every chart's series bends around the same
  // fraction of its domain so the linked windows genuinely correspond to a
  // common slice, but each chart expresses that slice on its own extent.
  const out = [];
  let s = seed >>> 0;
  const rnd = () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
  const span = domain[1] - domain[0];
  for (let i = 0; i < n; i += 1) {
    const frac = i / (n - 1);
    // Non-uniform sampling in x: samples are denser toward the high end. This
    // deliberately breaks the coincidence between "same fraction of the domain"
    // and "same sample index", so a chart's i-th sample does not sit at the
    // i/(n-1) point of its domain. `warp` differs per chart via the seed.
    const warp = 0.6 + ((seed % 5) * 0.12);
    const xFrac = Math.pow(frac, warp);
    const x = domain[0] + xFrac * span;
    const bend = Math.exp(-((frac - story) ** 2) / 0.02);
    const y = 20 + 60 * bend + rnd() * 8;
    out.push([Math.round(x * 100) / 100, Math.round(y * 10) / 10]);
  }
  return out;
}

// A workspace: a master chart plus linked charts. Every chart carries its own
// domain (min/max on x). The gesture is a normalized rubber-band [lo, hi] the
// analyst drags on the master, expressed as a fraction of the master's domain.
const workspaces = {
  alpha: {
    title: 'Regional Load Correlation',
    story: 0.58,
    charts: [
      { id: 'ch-master', role: 'master', label: 'North Grid MW', domain: [0, 1000] },
      { id: 'ch-b', role: 'linked', label: 'South Grid MW', domain: [200, 600] },
      { id: 'ch-c', role: 'linked', label: 'Interconnect kV', domain: [340, 360] },
      { id: 'ch-d', role: 'linked', label: 'Reserve Margin %', domain: [0, 40] },
    ],
    gesture: { window: [0.4, 0.7] },
  },
  beta: {
    title: 'Turbine Fleet Vibration',
    story: 0.35,
    charts: [
      { id: 'ch-master', role: 'master', label: 'Unit 1 mm/s', domain: [0, 50] },
      { id: 'ch-b', role: 'linked', label: 'Unit 2 mm/s', domain: [10, 30] },
      { id: 'ch-c', role: 'linked', label: 'Bearing Temp C', domain: [40, 140] },
      { id: 'ch-d', role: 'linked', label: 'Oil Pressure bar', domain: [2, 8] },
    ],
    gesture: { window: [0.2, 0.5] },
  },
  gamma: {
    title: 'Substation Thermal Sweep',
    story: 0.72,
    charts: [
      { id: 'ch-master', role: 'master', label: 'Feeder A A', domain: [100, 900] },
      { id: 'ch-b', role: 'linked', label: 'Feeder B A', domain: [400, 500] },
      { id: 'ch-c', role: 'linked', label: 'Transformer C', domain: [55, 95] },
      { id: 'ch-d', role: 'linked', label: 'Ambient C', domain: [15, 45] },
    ],
    gesture: { window: [0.55, 0.9] },
  },
};

const ws = workspaces[variant] || workspaces.alpha;
const token = linkToken(variant);
ws.charts.forEach((c, i) => { c.points = series(c.domain, ws.story, 48, 7919 + i * 31 + variant.length); });

// The manifest the console sees. Note: no resolved linked windows, no mapping
// policy, no per-chart target ranges.
const manifest = {
  title: ws.title,
  charts: ws.charts.map((c) => ({ id: c.id, role: c.role, label: c.label, domain: c.domain, points: c.points })),
  gesture: ws.gesture,
};

http.createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  res.setHeader('x-workspace-link', token);
  if (req.url === '/health') { res.end('{"ok":true}'); return; }
  if (req.url === '/api/workspace/manifest') { res.end(JSON.stringify(manifest)); return; }
  res.statusCode = 404; res.end('{"error":"not found"}');
}).listen(port, host);
