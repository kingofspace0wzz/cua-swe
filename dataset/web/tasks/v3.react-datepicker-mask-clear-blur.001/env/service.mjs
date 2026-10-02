// Evaluator-owned input-mask runtime. Serves the placeholder pattern a mask
// library surfaces when the date field is cleared. This is NOT part of the
// agent workspace and its source is not visible to the agent. The concrete
// cleared-mask pattern is chosen at runtime per scene, so no static source
// literal in the product can enumerate the possible cleared patterns. A
// correct fix must recognize a cleared mask GENERICALLY (a value that carries
// no date characters) rather than matching one hardcoded string.
import http from "node:http";

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const host = arg("--host", "127.0.0.1");
const port = Number(arg("--port", "5175"));

// Distinct cleared-mask placeholder patterns real mask libraries produce.
// Every one carries NO alphanumeric date characters.
const CLEARED_PATTERNS = {
  default: "__/__/____",
  a: "__/__/____",
  b: "--/--/----",
  c: "  /  /    ",
  d: "··/··/····",
};

const server = http.createServer((req, res) => {
  const u = (req.url || "/");
  if (u === "/health") {
    res.writeHead(200);
    res.end("ok");
    return;
  }
  if (u.startsWith("/mask")) {
    const qs = u.includes("?") ? u.slice(u.indexOf("?") + 1) : "";
    const params = new URLSearchParams(qs);
    const scene = params.get("scene") || "default";
    const cleared = CLEARED_PATTERNS[scene] || CLEARED_PATTERNS.default;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ cleared }));
    return;
  }
  res.writeHead(404);
  res.end("not found");
});

server.listen(port, host, () => {
  console.log(`mask runtime on http://${host}:${port}`);
});
