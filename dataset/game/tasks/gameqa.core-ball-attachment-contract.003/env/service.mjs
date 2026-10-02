import http from 'node:http';

const args = process.argv.slice(2);
const valueAfter = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const host = valueAfter('--host', '127.0.0.1');
const port = Number(valueAfter('--port', '0'));

const server = http.createServer((request, response) => {
  if (request.url === '/health') {
    response.writeHead(200, {'content-type': 'application/json'});
    response.end(JSON.stringify({ok: true, service: 'core-ball-runtime-boundary'}));
    return;
  }
  response.writeHead(404, {'content-type': 'application/json'});
  response.end(JSON.stringify({error: 'not_found'}));
});

server.listen(port, host);

const stop = () => server.close(() => process.exit(0));
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
