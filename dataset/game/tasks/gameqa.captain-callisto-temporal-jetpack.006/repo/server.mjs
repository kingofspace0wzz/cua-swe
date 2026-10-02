
import {createReadStream, existsSync, statSync} from 'node:fs';
import {createServer} from 'node:http';
import {extname, join, normalize} from 'node:path';

const args = process.argv.slice(2);
const value = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const host = value('--host', '127.0.0.1');
const port = Number(value('--port', '4173'));
const root = join(process.cwd(), 'dist');
const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
};

createServer((request, response) => {
  const requestPath = new URL(request.url, `http://${request.headers.host}`).pathname;
  const relative = requestPath === '/' ? 'index.html' : requestPath.slice(1);
  const resolved = normalize(join(root, relative));
  if (!resolved.startsWith(root) || !existsSync(resolved) || !statSync(resolved).isFile()) {
    response.writeHead(404);
    response.end('Not found');
    return;
  }
  response.writeHead(200, {
    'content-type': contentTypes[extname(resolved)] || 'application/octet-stream',
    'cache-control': 'no-store',
  });
  createReadStream(resolved).pipe(response);
}).listen(port, host, () => {
  console.log(`Captain Callisto listening on http://${host}:${port}`);
});
