// Fixture build step: parse-check every source module, then bundle the ES
// module graph (including the pinned Slate packages) into dist/bundle.js with
// esbuild so the browser loads a single self-contained module. No CDN and no
// global packages are used; slate + slate-dom resolve from node_modules.
import { readdir, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { build } from 'esbuild';

const files = await readdir('src');
let checked = 0;
for (const f of files.filter((n) => n.endsWith('.js'))) {
  execFileSync(process.execPath, ['--check', join('src', f)], { stdio: 'inherit' });
  checked += 1;
}

await mkdir('dist', { recursive: true });
await build({
  entryPoints: ['src/main.js'],
  bundle: true,
  format: 'esm',
  target: 'es2020',
  outfile: 'dist/bundle.js',
  logLevel: "silent",
});

console.log('build ok:', checked, 'files checked; dist/bundle.js written');
