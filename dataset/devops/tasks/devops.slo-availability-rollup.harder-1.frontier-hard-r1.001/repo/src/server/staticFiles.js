import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
const TYPES = { ".css": "text/css", ".html": "text/html", ".js": "text/javascript", ".json": "application/json" };
export function serveStatic(request, response) {
  const wanted = request.url === "/" ? "/index.html" : request.url;
  const root = join(process.cwd(), "dist");
  const file = normalize(join(root, wanted.split("?")[0]));
  if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("not found");
  response.writeHead(200, { "content-type": TYPES[extname(file)] || "text/plain" });
  createReadStream(file).pipe(response);
}
