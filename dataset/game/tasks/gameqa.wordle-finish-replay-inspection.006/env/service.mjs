import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(await readFile(path.join(root, "challenge.json"), "utf8"));
const args = process.argv.slice(2);

function arg(flag, fallback) {
  const index = args.indexOf(flag);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

function send(res, status, body) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store"
  });
  res.end(JSON.stringify(body));
}

const host = arg("--host", "127.0.0.1");
const port = Number(arg("--port", "52001"));

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  if (url.pathname === "/health") {
    send(res, 200, { ok: true });
    return;
  }
  if (url.pathname === "/api/challenge" && req.method === "GET") {
    const mode = url.searchParams.get("mode") || "daily";
    const challenge = fixture.challenges[mode];
    if (!challenge) {
      send(res, 404, { error: "puzzle mode not found" });
      return;
    }
    send(res, 200, challenge);
    return;
  }
  send(res, 404, { error: "not found" });
});

server.listen(port, host, () => {
  console.log(`protected Letter Arc challenge service on http://${host}:${port}`);
});
