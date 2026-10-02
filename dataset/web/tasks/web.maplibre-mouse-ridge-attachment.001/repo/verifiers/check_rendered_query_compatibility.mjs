// RGB centroids derive from renderedFiducial in check_terrain_anchor.mjs.
// No old lab assertions, private event driver, camera oracle or source grading.
import {createRequire} from 'node:module';
import {resolve, join} from 'node:path';
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
const workspace = resolve(process.env.CUA_SWE_WORKSPACE || process.cwd());
const require = createRequire(join(workspace, 'package.json'));
const artifacts = process.env.CUA_SWE_VERIFIER_ARTIFACTS || mkdtempSync(join(tmpdir(), 'rendered-query-'));
mkdirSync(artifacts, {recursive: true});
const report = {status: 'inconclusive', toleranceStatus: 'prospective; complete Native control still required', assertions: [], states: [], actions: [], inconclusive: [], errors: []};
const T = {attachment: 3, retention: 3, integrations: 4};
const trace = [{dx: 0, separation: 160}, {dx: 32, separation: 192}, {dx: 64, separation: 224}, {dx: 88, separation: 256}];
const terrainRegion = 'Sloped terrain map', flatRegion = 'Flat map';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const midpoint = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
class Inconclusive extends Error {}
let browser, page, profile, PNG;
function uncertainty(label, e) { report.inconclusive.push({label, error: String(e?.message || e)}); }
function check(label, actual, expected, tolerance) {
    const error = Array.isArray(actual) ? distance(actual, expected) : Math.abs(actual - expected);
    report.assertions.push({label, reached: true, passed: Number.isFinite(error) && error <= tolerance, actual, expected, tolerance, error});
}
function progress(label, actual, minimum) {
    report.assertions.push({label, reached: true, passed: Number.isFinite(actual) && actual > minimum, actual, minimum});
}
// Public labels are locators, not required source/DOM structure or pass flags.
async function click(name, scope) {
    const h = await page.evaluateHandle(({name, scope}) => {
        const root = scope ? [...document.querySelectorAll('[aria-label]')].find(e => e.getAttribute('aria-label') === scope) : document;
        return root && [...root.querySelectorAll('button,[role="button"]')].find(e =>
            (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent).trim() === name);
    }, {name, scope});
    try {
        const e = h.asElement();
        if (!e || await e.evaluate(e => e.disabled || e.getAttribute('aria-disabled') === 'true')) throw new Inconclusive('Public control unavailable: ' + name);
        await e.click(); report.actions.push({kind: 'click', name, scope});
    } finally { await h.dispose(); }
}
async function waitButton(name) {
    await page.waitForFunction(name => [...document.querySelectorAll('button,[role="button"]')].some(e =>
        (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent).trim() === name &&
        !e.disabled && e.getAttribute('aria-disabled') !== 'true'), {timeout: 65000}, name);
}
async function regionBox(name) {
    const box = await page.evaluate(name => {
        const e = [...document.querySelectorAll('[aria-label]')].find(e => e.getAttribute('aria-label') === name);
        if (!e) return null;
        const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height};
    }, name);
    if (!box || box.width < 100 || box.height < 100 || box.x < 0 || box.y < 0 || box.x + box.width > 1000 || box.y + box.height > 800) throw new Inconclusive('Map region missing or clipped: ' + name);
    return box;
}
// Connected components reject ambiguous paint instead of averaging unrelated dots.
function components(png, color) {
    const {width: w, height: h, data} = png, mask = new Uint8Array(w * h), found = [];
    for (let i = 0; i < w * h; i++) {
        const r = data[4*i], g = data[4*i+1], b = data[4*i+2];
        mask[i] = color === 'magenta' ? r > 220 && g < 70 && b > 220 : color === 'cyan' ? r < 70 && g > 220 && b > 220 : color === 'red' ? r > 220 && g < 70 && b < 70 : r < 80 && g > 55 && g < 130 && b > 150;
    }
    for (let q = 0; q < mask.length; q++) {
        if (!mask[q]) continue;
        const todo = [q]; mask[q] = 0;
        let sx = 0, sy = 0, n = 0, minX = w, maxX = 0, minY = h, maxY = 0;
        while (todo.length) {
            const i = todo.pop(), x = i % w, y = Math.floor(i / w);
            sx += x + .5; sy += y + .5; n++;
            minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
            for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
                const xx = x + dx, yy = y + dy, k = yy * w + xx;
                if (xx >= 0 && xx < w && yy >= 0 && yy < h && mask[k]) { mask[k] = 0; todo.push(k); }
            }
        }
        if (n > 12) found.push({centroid: [sx/n, sy/n], pixels: n, bounds: [minX,minY,maxX,maxY]});
    }
    return found;
}
function world(png, color) {
    const c = components(png, color);
    if (c.length !== 1 || c[0].pixels < 30) throw new Inconclusive(color + ' landmark missing, ambiguous or unloaded');
    const [x0,y0,x1,y1] = c[0].bounds;
    if (x0 < 2 || y0 < 2 || x1 >= png.width-2 || y1 >= png.height-2) throw new Inconclusive(color + ' landmark clipped');
    return c[0];
}
// Contact illustrations are DOM paint above the independent map canvas. Retain
// their visible evidence first; suppress only this presentation layer while
// photographing geographic paint, then restore the exact inline visibility.
async function landmarkScreenshot(path, box) {
    const overlay = await page.$('[aria-label="Sloped terrain map"] > .contacts');
    if (!overlay) return await page.screenshot({path, clip: box});
    const presentationOnly = await overlay.evaluate(e => getComputedStyle(e).pointerEvents === 'none' && !e.querySelector('canvas'));
    if (!presentationOnly) { await overlay.dispose(); throw new Inconclusive('Contact illustrations are not an isolated presentation layer'); }
    const previous = await overlay.evaluate(e => e.getAttribute('style'));
    try {
        await overlay.evaluate(e => e.style.setProperty('visibility', 'hidden', 'important'));
        return await page.screenshot({path, clip: box});
    } finally {
        await overlay.evaluate((e, previous) => {
            if (previous === null) e.removeAttribute('style');
            else e.setAttribute('style', previous);
        }, previous);
        await overlay.dispose();
    }
}
async function capture(label, region = terrainRegion, held = false) {
    const state = {label, region, screenshot: join(artifacts, label + '.png')}; report.states.push(state);
    await page.screenshot({path: state.screenshot});
    state.publicText = await page.evaluate(() => ({status: document.querySelector('[role="status"]')?.textContent,
        trace: [...document.querySelectorAll('[aria-label]')].find(e => e.getAttribute('aria-label') === 'Contact trace')?.textContent,
        alert: document.querySelector('[role="alert"]')?.textContent}));
    const box = await regionBox(region); state.crop = join(artifacts, label + '-map.png');
    let png;
    if (region === terrainRegion) {
        state.contactCrop = join(artifacts, label + '-contacts.png');
        const contactPNG = PNG.sync.read(await page.screenshot({path: state.contactCrop, clip: box}));
        if (held) {
            const rings = components(contactPNG, 'blue').filter(c => c.pixels >= 40).sort((a,b) => a.centroid[0]-b.centroid[0]);
            if (rings.length !== 2 || rings.some(c => c.bounds[0] < 2 || c.bounds[2] >= contactPNG.width-2)) throw new Inconclusive('Contact-ring paint missing or clipped');
            state.rings = rings; state.midpoint = midpoint(rings[0].centroid, rings[1].centroid);
            state.contactSeparation = distance(rings[0].centroid, rings[1].centroid);
            const last = (state.publicText.trace || '').split('\n').filter(l => l.startsWith('touch')).at(-1);
            if (!last) throw new Inconclusive('Public contact trace unavailable');
            const contacts = JSON.parse(last.slice(last.indexOf(' ')));
            if (contacts.length !== 2) throw new Inconclusive('Public contact trace did not reach held pair');
            const points = contacts.map(p => p.slice(1)).sort((a,b) => a[0]-b[0]);
            if (points.some((p,i) => distance(p, rings[i].centroid) > 1.5)) throw new Inconclusive('Contact trace and ring paint disagree');
            state.dispatchedContacts = contacts;
        }
        png = PNG.sync.read(await landmarkScreenshot(state.crop, box));
    } else {
        png = PNG.sync.read(await page.screenshot({path: state.crop, clip: box}));
    }
    if (png.width !== Math.round(box.width) || png.height !== Math.round(box.height)) throw new Inconclusive('Unexpected screenshot scale');
    state.landmarks = {anchor: world(png, region === terrainRegion ? 'magenta' : 'red'), companion: world(png, 'cyan')};
    state.anchor = state.landmarks.anchor.centroid; state.companion = state.landmarks.companion.centroid;
    state.separation = distance(state.anchor, state.companion);
    return state;
}

function retained(label, before, after, t = T.retention) {
    check(label + ' ridge', after.anchor, before.anchor, t); check(label + ' companion', after.companion, before.companion, t);
}
async function demo(mode, cycle, before) {
    const prefix = mode + '-' + cycle;
    await click('Move and zoom'); await waitButton('Move 1');
    const start = await capture(prefix + '-start', terrainRegion, true);
    retained(prefix + ' acquisition stationary', before, start);
    check(prefix + ' starts around ridge', start.anchor, start.midpoint, T.attachment);
    if (Math.abs(start.contactSeparation-160) > 1.5) throw new Inconclusive('Start contact separation not reached');
    const endpoints = []; let previousSeparation = start.separation;
    for (let i = 1; i <= 3; i++) {
        await click('Move ' + i); await waitButton(i < 3 ? 'Move ' + (i+1) : 'Release');
        const s = await capture(prefix + '-move' + i, terrainRegion, true);
        const expected = [start.midpoint[0]+trace[i].dx, start.midpoint[1]];
        if (distance(s.midpoint, expected) > 1.5 || Math.abs(s.contactSeparation-trace[i].separation) > 1.5) throw new Inconclusive('Disclosed contact endpoint not reached: ' + s.label);
        s.prescribedMidpoint = expected;
        check(prefix + ' move' + i + ' geographic attachment', s.anchor, expected, T.attachment);
        // On pitched terrain, screen magnification need not equal the contact ratio.
        // Require actual increasing magnification and compare whole painted endpoints across modes.
        progress(prefix + ' move' + i + ' painted zoom', s.separation, start.separation*(1+.1*i)-3);
        progress(prefix + ' move' + i + ' incremental painted zoom', s.separation-previousSeparation, 3);
        previousSeparation = s.separation; endpoints.push(s);
    }
    await click('Release'); await waitButton('Move and zoom');
    const released = await capture(prefix + '-released'); retained(prefix + ' accepted release', endpoints.at(-1), released);
    await sleep(900); const idle = await capture(prefix + '-idle'); retained(prefix + ' released idle', released, idle);
    return {start, endpoints, released, idle};
}
async function drag(region, dx) {
    const r = await regionBox(region), x = r.x+r.width/2, y = r.y+r.height*.7;
    await page.mouse.move(x,y); await page.mouse.down();
    for (let i = 1; i <= 6; i++) { await page.mouse.move(x+dx*i/6,y); await sleep(35); }
    await sleep(250); await page.mouse.up(); await sleep(800);
    report.actions.push({kind: 'ordinary mouse drag', region, delta: [dx,0]});
}
// Independent initial-camera projection of the two declared world places. This
// is only a rendered-terrain readiness guard, not camera/debug-state evidence.
// Constants are the public example's camera/geography, not queried from the app.
function initialPaint() {
    const rad = Math.PI/180, lat = 45.9, pitch = 55*rad, bearing = 27*rad;
    const f = 720, w = 512*2**12.5, m = 1/(2*Math.PI*6371008.8*Math.cos(lat*rad));
    const right = [Math.cos(bearing),Math.sin(bearing),0];
    const down = [-Math.sin(bearing)*Math.cos(pitch),Math.cos(bearing)*Math.cos(pitch),-Math.sin(pitch)];
    const back = [-Math.sin(bearing)*Math.sin(pitch),Math.cos(bearing)*Math.sin(pitch),Math.cos(pitch)];
    const project = offset => {
        const v = [offset[0]*w-back[0]*f,offset[1]*w-back[1]*f,(1400-400)*w*m-back[2]*f];
        const dot = a => a.reduce((sum,x,i)=>sum+x*v[i],0), depth = -dot(back);
        return [324+f*dot(right)/depth,256+f*dot(down)/depth];
    };
    return {anchor:project([-.00007,0]),companion:project([-.00007+.000014*Math.cos(bearing),.000014*Math.sin(bearing)])};
}
const modes = {};
async function runMode(mode) {
    await waitButton(mode); await click(mode); await waitButton('Reset'); await click('Reset'); await waitButton('Move and zoom');
    const initial = await capture(mode + '-reset');
    const declared = initialPaint(); initial.declaredTerrainPaint = declared;
    if (distance(initial.anchor,declared.anchor)>4 || distance(initial.companion,declared.companion)>4)
        throw new Inconclusive('Initial paint does not establish the declared loaded sloped terrain view');
    const first = await demo(mode, 'first', initial), second = await demo(mode, 'repeat', first.idle);
    await drag(terrainRegion,28); const dragged = await capture(mode + '-ordinary-drag');
    progress(mode + ' ordinary terrain drag moves ridge', distance(second.idle.anchor,dragged.anchor),8);
    progress(mode + ' ordinary terrain drag moves companion', distance(second.idle.companion,dragged.companion),8);
    await sleep(600); retained(mode + ' drag settled',dragged,await capture(mode + '-drag-idle'));
    modes[mode] = {initial,first,second,dragged};
}
try {
    const puppeteer = require('puppeteer'); ({PNG} = require('pngjs'));
    profile = mkdtempSync(join(artifacts,'profile-'));
    browser = await puppeteer.launch({executablePath: process.env.CUA_SWE_VERIFIER_CHROME_PATH || process.env.CHROME_PATH || '/usr/bin/google-chrome', userDataDir: profile, headless: true,
        args: ['--no-sandbox','--disable-dev-shm-usage','--enable-webgl','--ignore-gpu-blocklist','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader-webgl']});
    page = await browser.newPage(); await page.setViewport({width:1000,height:800,deviceScaleFactor:1,hasTouch:true});
    page.on('pageerror',e => report.errors.push(e.message));
    const url = new URL(process.env.CUA_SWE_WEB_URL || `http://127.0.0.1:${process.env.CUA_SWE_WEB_PORT || 4173}/runtime-task/index.html`);
    if (url.pathname === '/') url.pathname = '/runtime-task/index.html'; report.url = url.href;
    // Reuse the supplied service. Never install, build or start a service here.
    await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:60000});
    for (const mode of ['Native','Legacy']) {
        try { await runMode(mode); } catch(e) {
            uncertainty(mode,e);
            try { await page.screenshot({path:join(artifacts,mode+'-unavailable.png')}); await click('Release'); await waitButton('Move and zoom'); } catch { /* already released or unavailable */ }
        }
    }
    if (modes.Native && modes.Legacy) {
        retained('Integration reset comparison',modes.Native.initial,modes.Legacy.initial,T.integrations);
        for (const cycle of ['first','second']) {
            const a=modes.Native[cycle], b=modes.Legacy[cycle];
            for (let i=0;i<3;i++) retained('Integration '+cycle+' move'+(i+1),a.endpoints[i],b.endpoints[i],T.integrations);
            retained('Integration '+cycle+' settled view',a.idle,b.idle,T.integrations);
        }
        retained('Integration ordinary drag comparison',modes.Native.dragged,modes.Legacy.dragged,T.integrations);
    } else uncertainty('Integration comparison','Both complete rendered workflows not reached');
    try {
        const before=await capture('flat-initial',flatRegion); await drag(flatRegion,24);
        const moved=await capture('flat-drag',flatRegion);
        check('Flat drag anchor',moved.anchor,[before.anchor[0]+24,before.anchor[1]],3);
        check('Flat drag companion',moved.companion,[before.companion[0]+24,before.companion[1]],3);
        await click('Zoom in',flatRegion); await sleep(1100);
        const zoomed=await capture('flat-zoom',flatRegion); check('Flat zoom painted separation',zoomed.separation,moved.separation*2,3);
    } catch(e) { uncertainty('Flat navigation',e); }
} catch(e) { uncertainty('Driver/runtime',e); }
finally {
    if (report.errors.length) uncertainty('Page runtime',report.errors.join('; '));
    const failed=report.assertions.filter(a=>!a.passed);
    report.status=failed.length?'fail':report.inconclusive.length?'inconclusive':report.assertions.length?'pass':'inconclusive';
    report.failures=failed; report.reachedAssertions=report.assertions.length;
    try { await browser?.close(); } catch(e) { uncertainty('Browser cleanup',e); report.status=failed.length?'fail':'inconclusive'; }
    if (profile) rmSync(profile,{recursive:true,force:true});
    writeFileSync(join(artifacts,'results.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({status:report.status,reachedAssertions:report.reachedAssertions,failures:failed.length,inconclusive:report.inconclusive,artifacts}));
    process.exitCode=report.status==='pass'?0:report.status==='fail'?1:2;
}
