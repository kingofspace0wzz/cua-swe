import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const requireFromWorkspace = createRequire(resolve(process.cwd(), 'package.json'));
const puppeteer = requireFromWorkspace('puppeteer');

const port = process.env.CUA_SWE_WEB_PORT || '4173';
const url = `http://127.0.0.1:${port}/runtime-task/index.html`;
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--enable-webgl',
    '--ignore-gpu-blocklist',
    '--enable-unsafe-swiftshader',
    '--use-gl=angle',
    '--use-angle=swiftshader-webgl',
  ],
});

try {
  const page = await browser.newPage();
  await page.setViewport({width: 1000, height: 800, deviceScaleFactor: 1, hasTouch: true, isMobile: true});
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 30_000});
  await page.waitForFunction(() => Boolean(window.__terrainGestureEvidence), {timeout: 30_000});
  const evidence = await page.evaluate(() => window.__terrainGestureEvidence);
  if (!evidence || typeof evidence.slip_px !== 'number') {
    throw new Error('terrain gesture evidence is missing');
  }
  if (evidence.slip_px >= 0.5) {
    throw new Error(`terrain gesture anchor slipped ${evidence.slip_px.toFixed(3)}px (expected <0.5px)`);
  }
  process.stdout.write(`${JSON.stringify(evidence)}\n`);
} finally {
  await browser.close();
}
