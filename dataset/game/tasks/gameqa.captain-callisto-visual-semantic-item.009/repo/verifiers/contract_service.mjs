import http from 'node:http';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const payloadPath = fileURLToPath(
    new URL('./contract_payloads.json', import.meta.url));
const contractPayloads = JSON.parse(readFileSync(payloadPath, 'utf8'));

export {contractPayloads};

export function createContractServer() {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://service.invalid');
    if (url.pathname === '/health') {
      response.writeHead(200, {'content-type': 'application/json'});
      response.end(JSON.stringify({ok: true}));
      return;
    }
    if (url.pathname !== '/api/cargo-manifest') {
      response.writeHead(404);
      response.end('not found');
      return;
    }
    const scenario = url.searchParams.get('scenario') === 'secondary' ?
        'secondary' : 'primary';
    response.writeHead(200, {
      'content-type': 'application/json',
      'cache-control': 'no-store',
    });
    response.end(JSON.stringify(contractPayloads[scenario]));
  });
}
