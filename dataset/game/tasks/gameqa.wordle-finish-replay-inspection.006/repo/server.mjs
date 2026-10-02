import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, "dist");
const args = process.argv.slice(2);

function arg(flag, fallback) {
  const index = args.indexOf(flag);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

const host = arg("--host", "127.0.0.1");
const port = Number(arg("--port", "52000"));
const serviceOrigin = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || "";
const mime = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8"
};

async function proxyRequest(req, res, url) {
  if (!serviceOrigin) {
    res.writeHead(503, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "challenge service unavailable" }));
    return;
  }
  try {
    const upstream = await fetch(`${serviceOrigin}${url.pathname}${url.search}`, {
      method: req.method,
      headers: { "cache-control": "no-store" }
    });
    const body = await upstream.text();
    res.writeHead(upstream.status, {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store"
    });
    res.end(body);
  } catch (error) {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: String(error) }));
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  if (url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, challengeService: Boolean(serviceOrigin) }));
    return;
  }
  if (url.pathname === "/api/challenge") {
    await proxyRequest(req, res, url);
    return;
  }

  const requested = url.pathname === "/" ? "/index.html" : url.pathname;
  const target = path.normalize(path.join(dist, requested));
  if (!target.startsWith(dist)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  try {
    const info = await stat(target);
    if (!info.isFile()) throw new Error("not a file");
    const body = await readFile(target);
    res.writeHead(200, {
      "content-type": mime[path.extname(target)] || "application/octet-stream",
      "cache-control": "no-store"
    });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found");
  }
});

server.listen(port, host, () => {
  console.log(`Letter Arc listening on http://${host}:${port}`);
});
