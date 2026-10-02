// Reproducible local synthetic DEM. No external services.
import { PNG } from 'pngjs';
import { writeFileSync, mkdirSync } from 'node:fs';
import { terrainHeight } from './geometry.js';
mkdirSync(new URL('assets/', import.meta.url), { recursive: true });
for (const name of ['plateau', ...Array.from({ length: 41 }, (_, i) => 2113 + i)]) {
    const p = new PNG({ width: 512, height: 512 });
    for (let y = 0; y < 512; y++)
        for (let x = 0; x < 512; x++) {
            const e = name === 'plateau' ? 1000 : terrainHeight((name + x / 512) / 4096);
            const n = Math.round((e + 32768) * 256), i = (y * 512 + x) * 4;
            p.data[i] = n >> 16;
            p.data[i + 1] = (n >> 8) & 255;
            p.data[i + 2] = n & 255;
            p.data[i + 3] = 255;
        }
    writeFileSync(new URL(`assets/${name}.png`, import.meta.url), PNG.sync.write(p));
}
