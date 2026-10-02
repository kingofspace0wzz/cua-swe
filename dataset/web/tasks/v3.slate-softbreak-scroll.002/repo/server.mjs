// Static file server for the Field Log Composer. Requests under /api/ are
// proxied to the workspace frame service so the composer never embeds the
// live workspace geometry directly.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4180);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const upstream = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || 'http://127.0.0.1:4430';
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

function safeRelPath(url) {
  const rel = url === '/' ? 'index.html' : url.split('?')[0].slice(1);
  const norm = normalize(rel);
  if (norm.startsWith('..' + sep) || norm === '..' || norm.startsWith('/')) return 'index.html';
  return norm;
}

http.createServer(async (req, res) => {
  if (req.url.startsWith('/api/')) {
    try {
      const upstreamRes = await fetch(upstream + req.url, { method: req.method });
      res.writeHead(upstreamRes.status, {
        'content-type': upstreamRes.headers.get('content-type') || 'application/json',
      });
      res.end(Buffer.from(await upstreamRes.arrayBuffer()));
    } catch {
      res.writeHead(502, { 'content-type': 'application/json' });
      res.end('{"error":"workspace frame service unavailable"}');
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
