// Static host for the Fleet Analytics Console.
//
// The console ships no fleet data of its own. At load time it asks the
// workspace API under /api/workspace/ for the active dashboard manifest, and
// this host forwards those requests to whatever workspace origin the launcher
// points it at. Everything else is served as a static file.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4180);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const workspace = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || 'http://127.0.0.1:4890';
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

function safeRelPath(url) {
  const rel = url === '/' ? 'index.html' : url.split('?')[0].slice(1);
  const norm = normalize(rel);
  if (norm.startsWith('..' + sep) || norm === '..' || norm.startsWith('/')) return 'index.html';
  return norm;
}

http.createServer(async (req, res) => {
  if (req.url.startsWith('/api/workspace/')) {
    try {
      const upstream = await fetch(workspace + req.url, { method: req.method });
      const headers = { 'content-type': upstream.headers.get('content-type') || 'application/json' };
      const token = upstream.headers.get('x-workspace-link');
      if (token) headers['x-workspace-link'] = token;
      res.writeHead(upstream.status, headers);
      res.end(Buffer.from(await upstream.arrayBuffer()));
    } catch {
      res.writeHead(502, { 'content-type': 'application/json' });
      res.end('{"error":"workspace unavailable"}');
    }
    return;
  }
  const safe = safeRelPath(req.url);
  try {
    const file = await readFile(join(process.cwd(), safe));
    res.writeHead(200, { 'content-type': types[extname(safe)] || 'application/octet-stream' });
    res.end(file);
  } catch {
    const file = await readFile(join(process.cwd(), 'index.html'));
    res.writeHead(200, { 'content-type': 'text/html' });
    res.end(file);
  }
}).listen(port, host);
