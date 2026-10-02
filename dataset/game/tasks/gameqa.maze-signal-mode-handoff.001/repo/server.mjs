import {createReadStream, existsSync, statSync} from 'node:fs';
import {createServer} from 'node:http';
import {extname, join, normalize} from 'node:path';

const args = process.argv.slice(2);
const value = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const host = value('--host', '127.0.0.1');
const port = Number(value('--port', '51000'));
const root = join(process.cwd(), 'dist');
const serviceOrigin = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN ||
    'http://127.0.0.1:51001';
const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

createServer(async (request, response) => {
  const requestUrl = new URL(request.url, `http://${request.headers.host}`);
  if (requestUrl.pathname === '/api/scenario') {
    try {
      const upstream = await fetch(serviceOrigin + '/api/scenario');
      const body = await upstream.text();
      response.writeHead(upstream.status, {
        'content-type': 'application/json',
        'cache-control': 'no-store',
      });
      response.end(body);
    } catch {
      response.writeHead(502, {'content-type': 'application/json'});
      response.end(JSON.stringify({error: 'scenario unavailable'}));
    }
    return;
  }

  const relative = requestUrl.pathname === '/' ?
      'index.html' : requestUrl.pathname.slice(1);
  const resolved = normalize(join(root, relative));
  if (!resolved.startsWith(root) || !existsSync(resolved) ||
      !statSync(resolved).isFile()) {
    response.writeHead(404);
    response.end('Not found');
    return;
  }
  response.writeHead(200, {
    'content-type': contentTypes[extname(resolved)] ||
        'application/octet-stream',
    'cache-control': 'no-store',
  });
  createReadStream(resolved).pipe(response);
}).listen(port, host, () => {
  console.log(`Signal Maze listening on http://${host}:${port}`);
});

