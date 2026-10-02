import { spawnSync } from "node:child_process";
import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SKIP = new Set(["node_modules", "verifiers", ".git"]);
const IMPORT_PATTERN = /(?:from|import)\s+["'](\.[^"']+)["']/g;
const ASSET_PATTERN = /(?:src|href)="(\/[^"]+)"/g;
const problems = [];

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || SKIP.has(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(path)));
    else if ([".js", ".mjs"].includes(extname(path))) files.push(path);
  }
  return files;
}

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

const sources = [
  join(ROOT, "server.mjs"),
  ...(await walk(join(ROOT, "src"))),
].sort();
for (const path of sources) {
  const checked = spawnSync(process.execPath, ["--check", path], {
    encoding: "utf8",
  });
  if (checked.status !== 0) {
    problems.push(`${relative(ROOT, path)} does not parse: ${checked.stderr}`);
    continue;
  }
  const source = await readFile(path, "utf8");
  IMPORT_PATTERN.lastIndex = 0;
  for (
    let match = IMPORT_PATTERN.exec(source);
    match;
    match = IMPORT_PATTERN.exec(source)
  ) {
    const imported = resolve(dirname(path), match[1]);
    if (!(await exists(imported))) {
      problems.push(`${relative(ROOT, path)} imports missing ${match[1]}`);
    }
  }
}

const document = await readFile(join(ROOT, "index.html"), "utf8");
ASSET_PATTERN.lastIndex = 0;
for (
  let match = ASSET_PATTERN.exec(document);
  match;
  match = ASSET_PATTERN.exec(document)
) {
  const asset = join(ROOT, match[1].replace(/^\/+/, ""));
  if (!(await exists(asset))) {
    problems.push(`index.html references missing ${match[1]}`);
  }
}

for (const problem of problems) process.stdout.write(`fail ${problem}\n`);
if (problems.length) process.exit(1);
process.stdout.write("sentinel build ok\n");
