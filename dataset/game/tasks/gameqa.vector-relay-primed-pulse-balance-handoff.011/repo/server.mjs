import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const args = process.argv.slice(2);
const portFlag = args.indexOf("--port");
const hostFlag = args.indexOf("--host");
const port = portFlag >= 0 ? Number(args[portFlag + 1]) : 52840;
const host = hostFlag >= 0 ? args[hostFlag + 1] : "127.0.0.1";
const root = process.cwd();
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8"
};

createServer((request, response) => {
  const rawPath = new URL(request.url || "/", `http://${host}:${port}`).pathname;
  const relative = rawPath === "/" ? "index.html" : rawPath.replace(/^\/+/, "");
  const safePath = normalize(relative).replace(/^(\.\.[/\\])+/, "");
  const filePath = join(root, safePath);
  try {
    if (!statSync(filePath).isFile()) throw new Error("not a file");
    response.writeHead(200, {
      "cache-control": "no-store",
      "content-type": types[extname(filePath)] || "application/octet-stream"
    });
    createReadStream(filePath).pipe(response);
  } catch (_error) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found\n");
  }
}).listen(port, host, () => {
  process.stdout.write(`Vector Relay ready at http://${host}:${port}\n`);
});
