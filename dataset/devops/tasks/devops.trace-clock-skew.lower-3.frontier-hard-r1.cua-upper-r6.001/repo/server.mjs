import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { contentTypeFor, isDocumentPath, resolveAsset } from "./src/server/staticFiles.js";
import { createServiceProxy, serviceOrigin } from "./src/server/serviceProxy.js";

const ROOT = dirname(fileURLToPath(import.meta.url));
const forward = createServiceProxy(serviceOrigin(process.env));
const PUBLIC_API = new Set(["catalog", "trace", "evaluate", "operator-guide", "calibration-board"]);

function parse(argv) {
  const result = { host: "127.0.0.1", port: 4341 };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") result.host = argv[++index];
    else if (argv[index] === "--port") result.port = Number(argv[++index]);
  }
  return result;
}

function send(response, status, type, body) {
  response.writeHead(status, {
    "content-type": type,
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

async function handle(request, response) {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname.startsWith("/api/")) {
    const api = url.pathname.slice(5).replace(/\/+$/, "");
    if (!PUBLIC_API.has(api)) {
      send(response, 404, "application/json; charset=utf-8", JSON.stringify({ error: "unknown_api" }));
      return;
    }
    const answer = await forward(request, url.pathname.slice(4), url.search);
    send(response, answer.status, answer.type, answer.body);
    return;
  }
  const asset = resolveAsset(ROOT, url.pathname);
  if (asset) {
    try {
      send(response, 200, contentTypeFor(asset), await readFile(asset));
    } catch {
      send(response, 404, "text/plain; charset=utf-8", "not found\n");
    }
    return;
  }
  if (isDocumentPath(url.pathname)) {
    send(response, 200, "text/html; charset=utf-8", await readFile(new URL("./index.html", import.meta.url)));
    return;
  }
  send(response, 404, "text/plain; charset=utf-8", "not found\n");
}

const options = parse(process.argv.slice(2));
createServer((request, response) => {
  handle(request, response).catch((error) => {
    send(response, 500, "application/json; charset=utf-8", JSON.stringify({ error: "host_failure", detail: String(error.message || error) }));
  });
}).listen(options.port, options.host, () => {
  process.stdout.write(`spanline on http://${options.host}:${options.port}\n`);
});
