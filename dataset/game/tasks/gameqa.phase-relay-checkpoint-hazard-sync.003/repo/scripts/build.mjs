import {spawnSync} from "node:child_process";

const files = [
  "server.mjs",
  "src/triad.js",
  "src/field.js",
  "src/panel.js",
  "src/session.js",
  "src/main.js",
];

for (const file of files) {
  const result = spawnSync(process.execPath, ["--check", file], {encoding: "utf8"});
  if (result.status !== 0) {
    process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }
}

console.log(`checked ${files.length} runtime files`);
