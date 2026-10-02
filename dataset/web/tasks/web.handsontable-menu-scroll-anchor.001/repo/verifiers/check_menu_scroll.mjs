import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const requireFromWorkspace = createRequire(resolve(process.cwd(), 'package.json'));
const puppeteer = requireFromWorkspace('puppeteer');
const port = process.env.CUA_SWE_WEB_PORT || '4173';
const url = `http://127.0.0.1:${port}/runtime-task/index.html`;
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const box = (page, selector) => page.$eval(selector, (el) => {
  const r = el.getBoundingClientRect();
  return {x: r.x, y: r.y, width: r.width, height: r.height};
});
const settle = (page) => page.evaluate(() => new Promise((resolve) => {
  requestAnimationFrame(() => requestAnimationFrame(resolve));
}));
const closeEnough = (value, expected, tolerance = 1) => Math.abs(value - expected) <= tolerance;

try {
  const page = await browser.newPage();
  await page.setViewport({width: 1000, height: 800, deviceScaleFactor: 1});
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 30_000});
  const button = '.ht_clone_top thead th:nth-child(2) .changeType';
  const menu = '.htDropdownMenu.handsontable:not([class*="Sub_"])';
  await page.click(button);
  await page.waitForSelector(menu, {visible: true});
  const buttonBefore = await box(page, button);
  const menuBefore = await box(page, menu);
  await page.$eval('#scroll-container', (el) => { el.scrollTop += 100; });
  await settle(page);
  const buttonAfter = await box(page, button);
  const menuAfter = await box(page, menu);
  const anchorOffsetError = Math.abs(
    (menuAfter.y - buttonAfter.y) - (menuBefore.y - buttonBefore.y),
  );
  const movedBy = menuBefore.y - menuAfter.y;

  await page.reload({waitUntil: 'networkidle0'});
  await page.click(button);
  await page.waitForSelector(menu, {visible: true});
  const horizontalBefore = await box(page, menu);
  await page.$eval('.ht_master .wtHolder', (el) => { el.scrollLeft += 60; });
  await settle(page);
  const horizontalAfter = await box(page, menu);
  const horizontalMovedBy = horizontalBefore.x - horizontalAfter.x;

  await page.$eval('.ht_master .wtHolder', (el) => { el.scrollLeft += 2000; });
  await settle(page);
  const hiddenAfterDerender = await page.$eval(menu, (el) => getComputedStyle(el).display === 'none');

  const evidence = {
    anchor_offset_error_px: anchorOffsetError,
    outer_scroll_menu_movement_px: movedBy,
    horizontal_menu_movement_px: horizontalMovedBy,
    hidden_after_anchor_derender: hiddenAfterDerender,
  };
  process.stdout.write(`${JSON.stringify(evidence)}\n`);
  if (!closeEnough(anchorOffsetError, 0) || !closeEnough(movedBy, 100) ||
      !closeEnough(horizontalMovedBy, 60) || !hiddenAfterDerender) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
