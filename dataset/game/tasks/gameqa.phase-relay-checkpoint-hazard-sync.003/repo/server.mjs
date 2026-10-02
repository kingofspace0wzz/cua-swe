import {createServer} from "node:http";
import {readFile, stat} from "node:fs/promises";
import {extname, join, normalize} from "node:path";

const args = process.argv.slice(2);
const valueAfter = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const host = valueAfter("--host", "127.0.0.1");
const port = Number(valueAfter("--port", "51000"));
const root = process.cwd();
const runtimeServiceOrigin = process.env.CUA_SWE_RUNTIME_SERVICE_ORIGIN ?? "";
const proxyTimeoutMs = 5000;
const proxyLimits = {
  "/runtime/ticket": 64 * 1024,
  "/runtime/route-card.png": 2 * 1024 * 1024,
};
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".png": "image/png",
};

function runtimeTarget(pathname) {
  if (!runtimeServiceOrigin) throw new Error("runtime service is unavailable");
  const origin = new URL(runtimeServiceOrigin);
  if (
    origin.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname) ||
    origin.username ||
    origin.password ||
    origin.pathname !== "/"
  ) throw new Error("runtime service origin is invalid");
  return new URL(
    pathname === "/runtime/ticket" ? "/ticket" : "/route-card.png",
    origin,
  );
}

async function proxyRuntime(pathname, response) {
  const upstream = await fetch(runtimeTarget(pathname), {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(proxyTimeoutMs),
  });
  if (!upstream.ok) throw new Error(`runtime service returned ${upstream.status}`);
  const body = Buffer.from(await upstream.arrayBuffer());
  if (body.length === 0 || body.length > proxyLimits[pathname]) {
    throw new Error("runtime payload size is invalid");
  }
  response.writeHead(200, {
    "content-type": pathname.endsWith(".png")
      ? "image/png"
      : "application/json; charset=utf-8",
    "content-length": String(body.length),
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(body);
}

createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
    if (url.pathname in proxyLimits) {
      await proxyRuntime(url.pathname, response);
      return;
    }
    const requested = url.pathname === "/" ? "/index.html" : url.pathname;
    const relative = normalize(requested).replace(/^(\.\.[/\\])+/, "");
    const path = join(root, relative);
    const info = await stat(path);
    if (!info.isFile() || !path.startsWith(root)) throw new Error("not found");
    const body = await readFile(path);
    response.writeHead(200, {
      "content-type": types[extname(path)] ?? "application/octet-stream",
      "cache-control": "no-store",
    });
    response.end(body);
  } catch {
    response.writeHead(404, {"content-type": "text/plain; charset=utf-8"});
    response.end("Not found\n");
  }
}).listen(port, host, () => {
  console.log(`signal weave listening on http://${host}:${port}`);
});
