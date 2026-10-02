import http from "node:http";
const ALLOWED = new Set(["catalog", "configure", "scenario", "window", "snapshot", "select", "filter", "probe", "replay"]);
export async function proxyRequest(request, response, origin) {
  const action = request.url?.split("?")[0].split("/").filter(Boolean).at(-1);
  if (!ALLOWED.has(action)) return response.writeHead(404).end("not found");
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const data = Buffer.concat(chunks);
  const upstream = http.request(new URL(`/v1/${action}`, origin), {
    method: request.method,
    headers: { "content-type": "application/json", "content-length": data.length },
  }, (incoming) => {
    response.writeHead(incoming.statusCode || 500, { "content-type": "application/json" });
    incoming.pipe(response);
  });
  upstream.on("error", (error) => response.writeHead(502).end(error.message));
  upstream.end(data);
}
