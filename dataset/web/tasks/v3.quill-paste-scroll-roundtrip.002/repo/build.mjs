// Fixture build for the Threadloop collaborative reading surface.
//
// The reading surface is a real Quill editor. The browser can only load a
// single bundled module, so this step uses esbuild to bundle the application
// entry (which imports the pinned upstream `quill` package) into
// `dist/app.bundle.js`, and copies Quill's stylesheet into `dist/`. The build
// then asserts that the produced bundle actually contains the Quill runtime it
// imported -- a missing or stubbed dependency fails the build here.
import { build } from 'esbuild';
import { mkdir, copyFile, readFile, access } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, sep } from 'node:path';

const require = createRequire(import.meta.url);
const quillPkgDir = dirname(require.resolve('quill/package.json'));

// Resolve the installed Quill package from node_modules (no CDN, no globals).
let quillEntry;
try {
  quillEntry = require.resolve('quill');
} catch (err) {
  console.error('build failed: the pinned `quill` dependency is not installed.');
  console.error('run `npm install` so the reading surface can import Quill at runtime.');
  process.exit(1);
}
const quillDist = dirname(quillEntry);

await mkdir('dist', { recursive: true });

const result = await build({
  entryPoints: ['src/main.js'],
  bundle: true,
  format: 'esm',
  target: 'es2020',
  outfile: 'dist/app.bundle.js',
  legalComments: 'none',
  logLevel: 'silent',
  metafile: true,
});

// The bundle must genuinely include the upstream Quill package; a wrapper or a
// dropped dependency would not pull it into the graph.
const inputs = Object.keys(result.metafile.inputs);
const pulledInQuill = inputs.some((p) => p.split(sep).join('/').includes('node_modules/quill/'));
if (!pulledInQuill) {
  console.error('build failed: the app bundle does not import the quill package.');
  process.exit(1);
}

const bundleText = await readFile('dist/app.bundle.js', 'utf8');
if (!bundleText.includes('ql-editor') && !bundleText.includes('ql-container')) {
  console.error('build failed: bundled output has no Quill runtime footprint.');
  process.exit(1);
}

// Ship Quill's own stylesheet next to the bundle so the editor renders with
// its real layout (line boxes, scroll container) rather than a hand-rolled one.
const quillCss = join(quillPkgDir, 'dist', 'quill.snow.css');
await access(quillCss);
await copyFile(quillCss, 'dist/quill.snow.css');

console.log('build ok: bundled app with quill from', quillDist.split(sep).join('/'));
