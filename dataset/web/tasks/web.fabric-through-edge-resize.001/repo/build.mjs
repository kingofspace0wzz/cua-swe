// Bundle the pinned Fabric runtime and editor shell.
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.join(here, 'dist');
fs.mkdirSync(outdir, { recursive: true });

await build({
  entryPoints: [path.join(here, 'src', 'app.mjs')],
  bundle: true,
  format: 'esm',
  target: 'es2020',
  sourcemap: false,
  minify: false,
  outfile: path.join(outdir, 'app.bundle.js'),
  logLevel: 'info',
});

console.log('built', path.join(outdir, 'app.bundle.js'));
