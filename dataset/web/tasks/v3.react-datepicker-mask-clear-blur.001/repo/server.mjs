// Product server: serves the built appointment-booking app. The decisive
// behavioral contract (how the date field must respond on blur to a
// cleared-mask value vs an invalid-date value) is owned by the evaluator, not
// exposed by this server or the agent-visible source.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const host = arg("--host", "127.0.0.1");
const port = Number(arg("--port", "4173"));
const ROOT = process.cwd();
// Origin of the evaluator-owned mask runtime. Not part of the agent workspace.
const SERVICE = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || "";

const TYPES = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".mjs": "application/javascript",
  ".json": "application/json",
  ".css": "text/css",
};

function proxyMask(req, res) {
  if (!SERVICE) {
    res.writeHead(500);
    res.end('{"error":"no mask service"}');
    return;
  }
  const url = SERVICE.replace(/\/$/, "") + "/mask" + (req.url.slice("/mask".length) || "");
  http
    .get(url, (up) => {
      res.writeHead(up.statusCode || 502, {
        "content-type": up.headers["content-type"] || "application/json",
      });
      up.pipe(res);
    })
    .on("error", (e) => {
      res.writeHead(502);
      res.end(String(e));
    });
}

const server = http.createServer(async (req, res) => {
  const u = (req.url || "/").split("?")[0];
  if (u === "/health") {
    res.writeHead(200);
    res.end("ok");
    return;
  }
  if (u === "/mask" || u.startsWith("/mask?")) {
    return proxyMask(req, res);
  }
  let path = u === "/" ? "/index.html" : u;
  const full = normalize(join(ROOT, path));
  if (!full.startsWith(ROOT)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  try {
    const body = await readFile(full);
    res.writeHead(200, { "content-type": TYPES[extname(full)] || "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});

server.listen(port, host, () => {
  console.log(`app on http://${host}:${port}`);
});
