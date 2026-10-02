// Evaluator-owned scene feed. Delivers the artboard "camera preset" (the canvas
// viewport transform) and the object placed on the artboard. The rotated /
// non-uniform viewport transforms that expose the fabric#10977 control geometry
// bug live ONLY here, behind the runtime boundary; they are never present in
// agent-visible repo/ source. The product applies whatever transform this feed
// delivers and renders fabric's real selection controls on top of it.
import http from 'node:http';
import { fileURLToPath } from 'node:url';

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const host = arg('--host', '127.0.0.1');
const port = Number(arg('--port', '4270'));

const cos = Math.SQRT1_2;
const sin = Math.SQRT1_2;

// The same object is placed on every preset artboard; only the camera preset
// (viewport transform) changes. Object placed with center origin at (200, 150).
const OBJECT = {
  left: 200,
  top: 150,
  width: 200,
  height: 120,
  angle: 0,
  originX: 'center',
  originY: 'center',
  padding: 0,
};

// Four protected camera presets.
// A: 45deg-rotated camera, uniform zoom 2  (rotation exposes all four sites)
// B: 45deg-rotated camera, non-uniform scale x=2 y=3 (scaleY divergence)
// C: pure scale+pan zoom 2 (backward-compatible common case; must NOT change)
// D: 90deg-rotated camera, zoom 1 (pure rotation, no scale)
const PRESETS = {
  A: {
    name: 'A',
    description: 'orbit camera, rotated 45°, zoom 2',
    viewportTransform: [2 * cos, 2 * sin, -2 * sin, 2 * cos, 200, 0],
    object: OBJECT,
  },
  B: {
    name: 'B',
    description: 'orbit camera, rotated 45°, anamorphic 2×3',
    viewportTransform: [2 * cos, 2 * sin, -3 * sin, 3 * cos, 0, 0],
    object: OBJECT,
  },
  C: {
    name: 'C',
    description: 'flat camera, zoom 2 (no rotation)',
    viewportTransform: [2, 0, 0, 2, 35, 25],
    object: OBJECT,
  },
  D: {
    name: 'D',
    description: 'orbit camera, rotated 90°, zoom 1',
    viewportTransform: [0, 1, -1, 0, 0, 0],
    object: OBJECT,
  },
};

http
  .createServer((request, response) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname === '/health') {
      response.writeHead(200, { 'content-type': 'text/plain' });
      response.end('ok');
      return;
    }
    if (url.pathname === '/scene') {
      const key = (url.searchParams.get('preset') || 'A').toUpperCase();
      const preset = PRESETS[key] || PRESETS.A;
      const body = Buffer.from(JSON.stringify(preset));
      response.writeHead(200, {
        'content-type': 'application/json; charset=utf-8',
        'content-length': body.length,
        'cache-control': 'no-store',
      });
      response.end(body);
      return;
    }
    response.writeHead(404, { 'content-type': 'text/plain' });
    response.end('not found');
  })
  .listen(port, host, () => {
    process.stdout.write(`scene-feed listening on http://${host}:${port}\n`);
  });
