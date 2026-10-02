// Static build step for the Fleet Analytics Console.
//
// The dashboard loads ES modules directly in the browser, so there is no
// bundling. This step syntax-checks every source module and the static host so
// a broken edit is caught before the console is launched.
import { readdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

let checked = 0;
for (const dir of ['src']) {
  const files = await readdir(dir);
  for (const f of files.filter((n) => n.endsWith('.js'))) {
    execFileSync(process.execPath, ['--check', join(dir, f)], { stdio: 'inherit' });
    checked += 1;
  }
}
execFileSync(process.execPath, ['--check', 'server.mjs'], { stdio: 'inherit' });
checked += 1;
console.log('build ok:', checked, 'files checked');
