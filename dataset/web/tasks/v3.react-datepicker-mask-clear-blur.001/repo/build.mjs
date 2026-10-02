import { build } from "esbuild";
import { mkdirSync } from "node:fs";

mkdirSync("dist", { recursive: true });

await build({
  entryPoints: ["src/index.jsx"],
  bundle: true,
  format: "iife",
  loader: { ".jsx": "jsx" },
  jsx: "automatic",
  outfile: "dist/app.bundle.js",
  logLevel: "info",
  define: { "process.env.NODE_ENV": '"production"' },
});
console.log("built dist/app.bundle.js");
