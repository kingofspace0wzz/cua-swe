// Bundle the product artboard editor from the REAL, pinned fabric.js browser
// build (vendored verbatim under vendor/fabric.mjs at fd50b70). esbuild only
// bundles/transpiles; it does not alter fabric's zoom, dimension, control-coord,
// or control-render geometry.
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
