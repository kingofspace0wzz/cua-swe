import http from "node:http";
import { proxyRequest } from "./src/server/serviceProxy.js";
import { serveStatic } from "./src/server/staticFiles.js";
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const port = Number(option("--port", process.env.PORT || 4455));
const host = option("--host", "127.0.0.1");
const origin = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || process.env.PROTECTED_SERVICE_ORIGIN || "http://127.0.0.1:4955";
http.createServer((request, response) => {
  if (request.url?.startsWith("/api/")) return proxyRequest(request, response, origin);
  serveStatic(request, response);
}).listen(port, host);
