import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const root = path.dirname(fileURLToPath(import.meta.url));
const host = arg('--host', '127.0.0.1');
const port = Number(arg('--port', '4173'));
const sceneOrigin = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || '';
const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

http
  .createServer(async (request, response) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname === '/health') {
      response.writeHead(200, { 'content-type': 'text/plain' });
      response.end('ok');
      return;
    }
    if (url.pathname === '/scene') {
      if (!sceneOrigin) {
        response.writeHead(503, { 'content-type': 'application/json' });
        response.end(JSON.stringify({ error: 'scene feed not configured' }));
        return;
      }
      try {
        const upstream = await fetch(`${sceneOrigin}${url.pathname}${url.search}`);
        const body = Buffer.from(await upstream.arrayBuffer());
        response.writeHead(upstream.status, {
          'content-type': upstream.headers.get('content-type') || 'application/json',
          'content-length': body.length,
          'cache-control': 'no-store',
        });
        response.end(body);
      } catch (error) {
        const body = Buffer.from(JSON.stringify({ error: String(error) }));
        response.writeHead(502, {
          'content-type': 'application/json; charset=utf-8',
          'content-length': body.length,
        });
        response.end(body);
      }
      return;
    }
    const relative = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
    const requested = path.resolve(root, relative);
    const target =
      requested.startsWith(root) && fs.existsSync(requested) && fs.statSync(requested).isFile()
        ? requested
        : path.join(root, 'index.html');
    const body = fs.readFileSync(target);
    response.writeHead(200, {
      'content-type': contentTypes[path.extname(target)] || 'application/octet-stream',
      'content-length': body.length,
      'cache-control': 'no-store',
    });
    response.end(body);
  })
  .listen(port, host, () => {
    process.stdout.write(`artboard-editor listening on http://${host}:${port}\n`);
  });
