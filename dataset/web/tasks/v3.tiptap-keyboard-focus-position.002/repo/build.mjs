// Build step: bundle the Draft Composer (and its Tiptap/ProseMirror runtime
// dependency) into a single browser module using esbuild.
//
// This is the runtime path exercised during verification: the served page loads
// dist/app.bundle.js, which imports and instantiates a real Tiptap Editor. A
// missing or unimported dependency fails the build here, not silently at runtime.
import { build } from 'esbuild';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const entry = join(__dirname, 'src', 'main.js');

// Guard: the real dependency must be installed for the runtime bundle to exist.
const mustHave = [
  '@tiptap/core',
  '@tiptap/pm',
  '@tiptap/extension-document',
  '@tiptap/extension-paragraph',
  '@tiptap/extension-text',
];
for (const dep of mustHave) {
  const pkgPath = join(__dirname, 'node_modules', dep, 'package.json');
  if (!existsSync(pkgPath)) {
    console.error('missing required dependency:', dep, '(run npm install)');
    process.exit(1);
  }
}

await build({
  entryPoints: [entry],
  bundle: true,
  format: 'esm',
  target: 'es2020',
  outfile: join(__dirname, 'dist', 'app.bundle.js'),
  logLevel: 'info',
  legalComments: 'none',
});

console.log('build ok: bundled Draft Composer with Tiptap runtime');
