import {validateAssets} from './assets.mjs';
import {loadedSupport} from './loaded.mjs';
import {ReadinessError} from './nearest.mjs';
import { createRequire } from 'node:module';
import { resolve, join } from 'node:path';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { acquire, project, camera, metres, merc, height, fiducials, distance, finite, envelope, validateEnvelope, presetView, zoomCheckpoints, settledGround } from './oracle.mjs';
const require = createRequire(resolve(process.cwd(), 'package.json'));
const puppeteer = require('puppeteer'), { PNG } = require('pngjs');
const artifacts = process.env.CUA_SWE_VERIFIER_ARTIFACTS || mkdtempSync(join(tmpdir(), 'terrain-verifier-'));
mkdirSync(artifacts, { recursive: true });
const profile = mkdtempSync(join(artifacts, 'profile-'));
const browser = await puppeteer.launch({ executablePath: process.env.CUA_SWE_VERIFIER_CHROME_PATH || process.env.CHROME_PATH || '/usr/bin/google-chrome', userDataDir: profile, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader-webgl'] });
const failures = [], results = [], errors = [], calibration = [], subchecks = [], observations = [];
const assert = (condition, message) => { if (!condition)
    throw Error(message); };
const near = (a, b, t, label) => { finite([a, b]); assert(Math.abs(a - b) <= t, `${label}: ${a} vs ${b} (tolerance ${t})`); };
let page;
async function snapshot() { const c=await page.evaluate(()=>driver.read()); finite(c); return c; }
async function frame(dt=0,n=1) { let c; for(let i=0;i<n;i++) c=await page.evaluate(dt=>{driver.clock+=dt;driver.lib.setNow(driver.clock);return new Promise(r=>{lab.map.once('render',()=>r(driver.read()));lab.map.triggerRepaint();});},dt); return c; }
async function terminate(type,last) {
 return page.evaluate(({type,last})=>new Promise(resolve=>{
  // Listener is installed BEFORE both DOM events in this very JS turn. The
  // scalars/support are captured IN the first completed render, not afterwards.
  lab.map.once('render',()=>resolve(driver.read()));
  driver.send('touchmove',last);driver.send(type,[]);lab.map.triggerRepaint();
 }),{type,last});
}
function check(label,fn) {try {const value=fn();subchecks.push({label,passed:true,value});return value;}catch(e){subchecks.push({label,passed:false,error:e.message,classification:e instanceof ReadinessError?'readiness_uncertainty':/Protocol error|Promise was collected/.test(e.message)?'infrastructure':'behavior'});}}
function ground(c,label) {const r=settledGround(c);assert(r.valid,label+': not nearest final loaded ground '+JSON.stringify({xy:r.xy,z:r.z,residual:r.residual}));return r;}
async function safeReady(c,mid) { // Before safe input, prove actual loaded required rays.
 if(!c.support?.length) throw new ReadinessError('Safe setup missing loaded mesh/source support');
 acquire(c,mid); settledGround(c); observations.push({kind:'loaded-before-input',camera:c,mid});
}
async function send(type, p, render = true) { await page.evaluate(({ type, p }) => driver.send(type, p), { type, p }); return render ? frame() : snapshot(); }
async function reset(name = 'terrain', hold = false) { await page.evaluate(async ({ name, hold }) => { await lab.reset(name, hold); driver.contacts = []; driver.clock += 1000; driver.lib.setNow(driver.clock); }, { name, hold }); await frame(); const c=await snapshot(); if(name==='terrain' && !hold) await safeReady(c,[190,300]); return c; }
const pair = (mid, sep, ids = [11, 22]) => [[ids[0], mid[0] - sep / 2, mid[1]], [ids[1], mid[0] + sep / 2, mid[1]]];
const attach = (c, P, s, label) => { finite(c); const k = camera(c), horizon = k.cp[1] - k.f / Math.tan(c.pitch * Math.PI / 180); assert(s[0] >= 0 && s[0] <= c.width && s[1] >= Math.max(0, horizon + 30) && s[1] <= c.height, label + ': safe path left M envelope'); assert(P[2] < k.pos[2], label + ': anchor above camera'); const projected = project(c, P), slip = distance(projected, s); finite([slip, ...P, ...projected]); assert(slip <= .5, `${label}: attachment slip ${slip.toFixed(6)}px`); return slip; };
function stationary(a, b, label, t = .05, cameraT = .0001, points = fiducials) { finite([a, b]); for (const p of points)
    assert(distance(project(a, p), project(b, p)) <= t, `${label}: fiducial moved ${distance(project(a, p), project(b, p))}px`); near(a.zoom, b.zoom, cameraT, label + ' zoom'); near(a.bearing, b.bearing, cameraT, label + ' bearing'); }
function selectedPreset(c, name, label) {
    const expected = presetView(name);
    finite([c, expected]);
    const points = name === 'terrain' ? fiducials : fiducials.map(p => [p[0], p[1], expected.elevation]);
    if (name === 'globe') {
        // At the flat globe preset, compare center in initial-latitude pixel scale;
        // globe projection is not borrowed from the application.
        assert(distance(merc(c.center), merc(expected.center)) * 512 * 2 ** expected.zoom <= .05,
            label + ': globe preset center not restored');
    } else {
        stationary(expected, c, label, .05, .0001, points);
    }
    for (const key of ['zoom', 'bearing', 'pitch', 'roll', 'fov'])
        near(c[key], expected[key], .0001, label + ' preset ' + key);
    for (const key of ['width', 'height']) near(c[key], expected[key], .05, label + ' preset ' + key);
    for (const key of ['left', 'right', 'top', 'bottom'])
        near(c.padding[key], expected.padding[key], .05, label + ' preset padding ' + key);
    near(c.elevation, expected.elevation, .01, label + ' preset loaded elevation');
}
async function screenshot(name) { const path = join(artifacts, name + '.png'); await page.screenshot({ path }); return path; }
async function renderedFiducial(c, label, ridge = false) {
    const box = await page.evaluate(() => { const r = lab.map.getCanvas().getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; });
    const bytes = await page.screenshot({ clip: box });
    const png = PNG.sync.read(bytes);
    let sx = 0, sy = 0, n = 0;
    for (let y = 0; y < png.height; y++)
        for (let x = 0; x < png.width; x++) {
            const i = (y * png.width + x) * 4;
            if (png.data[i] > 220 && png.data[i + 1] < 70 && (ridge ? png.data[i + 2] > 220 : png.data[i + 2] < 70)) {
                sx += x + .5;
                sy += y + .5;
                n++;
            }
        }
    assert(n > 30, label + ': actual red world fiducial absent');
    const pos = [sx / n, sy / n], P = fiducials[ridge ? 3 : 0].slice();
    if (!await page.evaluate(() => !!lab.map.getTerrain()))
        P[2] = 0;
    calibration.push({ label, centroid: pos, projected: project(c, P), error: distance(pos, project(c, P)) });
    assert(distance(pos, project(c, P)) < 1.1, label + ': rendered red fiducial disagrees with independent projection');
    return pos;
}
async function run(id, fn) { if(process.env.MAPLIBRE_FOCUS && !process.env.MAPLIBRE_FOCUS.split(',').includes(id)) return; const first=subchecks.length; try {
    const r = await fn();
    const failed=subchecks.slice(first).filter(x=>!x.passed);
    results.push({ id, passed: !failed.length, ...r });
    if(failed.length) throw Error(failed.map(x=>x.label+': '+x.error).join('; '));
    console.log('PASS', id, JSON.stringify(r || {}));
}
catch (e) {
    failures.push({ id, error: e.message, classification:e instanceof ReadinessError?'readiness_uncertainty':/Protocol error|Promise was collected/.test(e.message)?'infrastructure':'behavior' });
    console.log('FAIL', id, e.message);
    await screenshot(id + '-failure');
} }
try {
    page = await browser.newPage();
    await page.setViewport({ width: 1000, height: 800, deviceScaleFactor: 1, hasTouch: true });
    page.on('pageerror', e => { errors.push(e.message); console.log('PAGE ERROR', e.message); });
    await page.goto(`http://127.0.0.1:${process.env.CUA_SWE_WEB_PORT || 4173}/runtime-task/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForFunction(() => window.lab?.ready, { timeout: 60000 });
    await page.evaluate(async () => { const lib = await import('/dist/maplibre-gl-dev.mjs'); window.driver = { lib, clock: 10000, contacts: [], send(type, p) { this.clock += 16; lib.setNow(this.clock); const canvas = lab.map.getCanvas(), r = canvas.getBoundingClientRect(), old = this.contacts; this.contacts = p.map(t => t.slice()); const changed = type === 'touchstart' ? p.filter(t => !old.some(o => o[0] === t[0])) : type === 'touchend' || type === 'touchcancel' ? old.filter(o => !p.some(t => t[0] === o[0])) : p; const touch = t => new Touch({ identifier: t[0], target: canvas, clientX: r.x + t[1], clientY: r.y + t[2] }); canvas.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: p.map(touch), targetTouches: p.map(touch), changedTouches: changed.map(touch) })); } }; });
    await page.evaluate(source=>{
        driver.loaded=(0,eval)('('+source+')');
        driver.read=()=>{const m=lab.map,el=m.getCanvas();return {center:m.getCenter().toArray(),zoom:m.getZoom(),pitch:m.getPitch(),bearing:m.getBearing(),roll:m.getRoll(),elevation:m.getCenterElevation(),fov:m.getVerticalFieldOfView(),padding:m.getPadding(),width:el.clientWidth,height:el.clientHeight,support:driver.loaded()};};
    },loadedSupport.toString());
    await run('geometry-envelope', async () => ({envelope:validateEnvelope(),assets:validateAssets()}));
    await run('V1-parent', async () => {
        const f = page.frames().find(f => f.url().endsWith('parent.html'));
        const initial = await f.evaluate(async () => {
            const { Map: MapLibreMap, MercatorCoordinate } = await import('/dist/maplibre-gl-dev.mjs');
            const div = document.createElement('div');
            div.style.cssText = 'position:absolute;top:0;left:0;width:200px;height:200px';
            document.body.append(div);
            const m = new MapLibreMap({ container: div, style: { version: 8, sources: {}, layers: [] }, center: [7.5, 45.9], zoom: 11, pitch: 60, bearing: 0, attributionControl: false });
            await new Promise(r => m.once('load', r));
            m.touchZoomRotate.disableRotation();
            m.touchPitch.disable();
            m.doubleClickZoom.disable();
            const anchor = MercatorCoordinate.fromLngLat([7.494, 45.904]);
            m.terrain = { pointCoordinate: () => new MercatorCoordinate(anchor.x, anchor.y, 1000), getElevationForLngLatZoom: () => 1000, getElevationForLngLat: () => 1000, getMinTileElevationForLngLatZoom: () => 0, resetElevationCache: () => { }, getFramebuffer: () => ({}), getCoordsTexture: () => ({}), depthAtPoint: () => .9, tileManager: { update: () => { }, getRenderableTiles: () => [], anyTilesAfterTime: () => false } };
            const read = () => ({ center: m.getCenter().toArray(), zoom: m.getZoom(), pitch: m.getPitch(), bearing: m.getBearing(), roll: m.getRoll(), elevation: m.getCenterElevation(), fov: m.getVerticalFieldOfView(), padding: m.getPadding(), width: 200, height: 200 });
            window.parentDriver = { m, read };
            return read();
        });
        const P = [...merc([7.494, 45.904]), 1000], start = project(initial, P);
        let c = initial, worst = 0;
        for (let step = 0; step <= 3; step++) {
            const mid = [start[0] + 12 * step, start[1] + 8 * step], spread = 25 + 8 * step;
            c = await f.evaluate(async ({ mid, spread, step }) => { const { m, read } = parentDriver, el = m.getCanvas(), r = el.getBoundingClientRect(); const touches = [-1, 1].map((v, i) => new Touch({ identifier: i + 1, target: el, clientX: r.x + mid[0], clientY: r.y + mid[1] + v * spread })); el.dispatchEvent(new TouchEvent(step ? 'touchmove' : 'touchstart', { bubbles: true, cancelable: true, touches, targetTouches: touches, changedTouches: touches })); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return read(); }, { mid, spread, step });
            if (step)
                worst = Math.max(worst, attach(c, P, mid, 'parent movement'));
        }
        assert(c.zoom > initial.zoom + .1, 'Parent zoom disabled');
        assert(distance(project(initial, P), project(c, P)) > 10, 'Parent did not navigate');
        await f.evaluate(() => parentDriver.m.remove());
        return { worst };
    });
    await run('V2-recognition-persistence', async () => {
        let c = await reset();
        const start = c, P = acquire(c, [190, 300]);
        const pixels0 = await renderedFiducial(c, 'V2 start');
        await renderedFiducial(c, 'V2 rendered ridge', true);
        await send('touchstart', pair([190, 300], 160));
        for (const [x, s] of [[190.25, 162], [190.5, 165], [190.75, 168]]) {
            c = await send('touchmove', pair([x, 300], s).reverse());
            stationary(start, c, 'subthreshold');
        }
        let worst = 0;
        for (const [x, y, s] of [[214, 300, 192], [234, 278, 240], [324, 256, 240], [354, 280, 180], [354, 280, 210]]) {
            c = await send('touchmove', pair([x, y], s));
            worst = Math.max(worst, attach(c, P, [x, y], 'V2'));
            near(c.zoom - start.zoom, Math.log2(s / 160), .01, 'accumulated zoom');
            if (x === 324) {
                const pause = await frame(0, 6);
                stationary(c, pause, 'six-render pause');
            }
        }
        const pixels1 = await renderedFiducial(c, 'V2 end');
        assert(distance(pixels0, pixels1) > 10, 'Rendered terrain navigation missing');
        await screenshot('V2-attached');
        // Recognition is independent: zoom need not activate subthreshold pan,
        // and recognized pan need not activate subthreshold separation changes.
        c = await reset(); let mixedStart = c, mixedGrab = acquire(c, [190, 300]);
        await send('touchstart', pair([190, 300], 160));
        c = await send('touchmove', pair([190.25, 300], 192));
        near(c.zoom - mixedStart.zoom, Math.log2(192 / 160), .01, 'zoom recognizes independently');
        assert(distance(project(c, mixedGrab), [190, 300]) < .05, 'subthreshold pan activated during zoom');
        c = await send('touchmove', pair([191.25, 300], 193));
        attach(c, mixedGrab, [191.25, 300], 'later pan includes acquisition displacement');
        c = await reset(); mixedStart = c; mixedGrab = acquire(c, [190, 300]);
        await send('touchstart', pair([190, 300], 160));
        c = await send('touchmove', pair([214, 300], 168));
        near(c.zoom, mixedStart.zoom, .0001, 'subthreshold zoom during recognized pan');
        attach(c, mixedGrab, [214, 300], 'pan recognizes independently');
        c = await send('touchmove', pair([214, 300], 192));
        near(c.zoom - mixedStart.zoom, Math.log2(192 / 160), .01, 'later zoom includes acquisition separation');
        attach(c, mixedGrab, [214, 300], 'independent zoom after pan');
        return { worst, renderedMotion: distance(pixels0, pixels1) };
    });
    async function handoff({ survivor = 22, reverse = false, burst = false, extra = false } = {}) {
        const initial = await reset(), a = survivor === 22 ? [22, 450, 304] : [11, 210, 304], b = [a[0], a[1] + 32, 304], ids = [a[0], 33];
        let trace = [['touchstart', [[11, 190, 280]]], ['touchmove', [[11, 192, 280]]], ['touchmove', [[11, 230, 280]]], ['touchstart', [[11, 230, 280], [22, 390, 280]]], ['touchmove', [[11, 210, 304], [22, 450, 304]]], ['touchend', [a]], ['touchmove', [b]], ['touchstart', [b, [33, b[1] - 160, 304]]], ['touchmove', pair([b[1] - 60, 304], 192, [33, b[0]])]];
        if (extra)
            trace.push(['touchend', [[b[0], b[1] + 36, 304]]], ['touchstart', [[b[0], b[1] + 36, 304], [44, b[1] - 124, 304]]], ['touchmove', [[b[0], b[1] + 56, 304], [44, b[1] - 104, 304]]], ['touchmove', [[b[0], b[1] + 72, 304], [44, b[1] - 120, 304]]], ['touchend', [[b[0], b[1] + 72, 304]]], ['touchstart', [[b[0], b[1] + 72, 304], [33, b[1] - 88, 304]]], ['touchmove', [[b[0], b[1] + 88, 304], [33, b[1] - 104, 304]]]);
        if (reverse)
            trace = trace.map(([t, p], i) => [t, i % 2 ? p.slice().reverse() : p]);
        let worst = 0, P, c = initial, lastMid;
        const elevations = [], observedZoom = [];
        const checkpoints = zoomCheckpoints(trace, initial.zoom);
        if (burst) {
            await page.evaluate(trace => { for (const [t, p] of trace)
                driver.send(t, p); }, trace);
            c = await frame();
            near(c.zoom, checkpoints.at(-1).zoom, .01, 'burst prescribed cumulative zoom');
        }
        else
            for (const [i, [t, p]] of trace.entries()) {
                const mid = p.length === 1 ? p[0].slice(1) : [(p[0][1] + p[1][1]) / 2, (p[0][2] + p[1][2]) / 2];
                if (t !== 'touchmove') {
                    P = acquire(c, mid);
                    elevations.push(P[2]);
                    const before = c;
                    c = await send(t, p);
                    stationary(before, c, 'handoff-only');
                }
                else {
                    c = await send(t, p);
                    worst = Math.max(worst, attach(c, P, mid, `handoff segment from elevation ${P[2]} to midpoint ${mid}`));
                }
                near(c.zoom, checkpoints[i].zoom, .01, `handoff checkpoint ${i} IDs ${checkpoints[i].ids} separation-to-zoom`);
                observedZoom.push({event: i, ids: checkpoints[i].ids, separation: checkpoints[i].separation,
                    expected: checkpoints[i].zoom, actual: c.zoom});
                lastMid = mid;
            }
        const beforeNext = c;
        const last = trace.at(-1)[1].map(p => [p[0], p[1] + 20, p[2]]);
        c = await send('touchmove', last);
        if (!burst)
            worst = Math.max(worst, attach(c, P, [lastMid[0] + 20, lastMid[1]], 'subsequent motion'));
        near(c.zoom, checkpoints.at(-1).zoom, .01, 'subsequent pair motion preserves cumulative zoom');
        if (burst) {
            // Independently replay prefixes to each pair's recognition checkpoint.
            // No observation inside an unrendered burst mandates synchronous setters.
            for (const check of checkpoints.filter(p => p.firstRecognized)) {
                await reset();
                await page.evaluate(trace => { for (const [t, p] of trace) driver.send(t, p); }, trace.slice(0, check.event + 1));
                const prefix = await frame();
                near(prefix.zoom, check.zoom, .01, `burst pair IDs ${check.ids} separation-to-zoom`);
                observedZoom.push({event: check.event, ids: check.ids, separation: check.separation,
                    expected: check.zoom, actual: prefix.zoom});
            }
        }
        return { c, beforeNext, worst, elevations, observedZoom };
    }
    await run('V3-handoffs', async () => { const a = await handoff(), b = await handoff({ reverse: true }), d = await handoff({ survivor: 11 }); stationary(a.c, b.c, 'identifier order', .5, .001); near(a.elevations[0], 1400, .01, 'ridge acquisition'); near(a.elevations[1], 400, .01, 'valley acquisition'); return { worst: Math.max(a.worst, b.worst, d.worst), elevations: a.elevations, zoomCheckpoints: [a.observedZoom, b.observedZoom, d.observedZoom] }; });
    await run('V4-ordered-bursts', async () => { const a = await handoff({ extra: true }), b = await handoff({ burst: true, extra: true }); stationary(a.beforeNext, b.beforeNext, 'burst endpoint', .5, .001); stationary(a.c, b.c, 'burst subsequent movement', .5, .001); return { worstFramed: a.worst, zoomCheckpoints: a.observedZoom, burstPairCheckpoints: b.observedZoom }; });
    async function terrainTermination(type, valley=false) {
        const label=(valley?'valley':'ridge')+' '+type, mid=valley?[410,320]:[190,300], dx=valley?4:40;
        let initial=await reset(), c=initial;
        await safeReady(initial,mid); const P=acquire(initial,mid);
        await send('touchstart',pair(mid,160));
        for(let i=1;i<=4;i++) {
            c=await send('touchmove',pair([mid[0]+dx*i,mid[1]],160+16*i));
            check(label+' movement attachment '+i,()=>attach(c,P,[mid[0]+dx*i,mid[1]],label));
            check(label+' movement zoom '+i,()=>near(c.zoom-initial.zoom,Math.log2((160+16*i)/160),.01,label+' zoom'));
        }
        const accepted=c, last=pair([mid[0]+4*dx,mid[1]],224);
        check(label+' accepted retained grab',()=>attach(accepted,P,[mid[0]+4*dx,mid[1]],label));
        const acceptedGround=settledGround(accepted); // Observation, NOT a mandated intermediate.
        await screenshot(label.replaceAll(' ','-')+'-accepted');
        initial=await reset(); await safeReady(initial,mid);
        await send('touchstart',pair(mid,160));
        for(let i=1;i<=3;i++) await send('touchmove',pair([mid[0]+dx*i,mid[1]],160+16*i));
        const settled=await terminate(type,last);
        check(label+' first-render root',()=>ground(settled,label));
        for(const [i,f] of fiducials.entries()) check(label+' accepted view '+i,()=>assert(distance(project(accepted,f),project(settled,f))<=.5,label+' commit/view'));
        const lifecycle={label,initial,grab:P,accepted,acceptedGround,settled,settledGrabProjection:project(settled,P),idle:[],stale:[]};
        observations.push(lifecycle);
        await screenshot(label.replaceAll(' ','-')+'-settled');
        if(type==='touchcancel') {
            for(let i=0;i<8;i++) {c=await frame(16);lifecycle.idle.push(c);check(label+' idle '+i,()=>stationary(settled,c,label+' idle'));check(label+' idle root '+i,()=>ground(c,label));}
            c=await send('touchmove',pair([330,300],224));lifecycle.stale.push(c);check(label+' stale move',()=>stationary(settled,c,label+' stale move'));check(label+' stale move root',()=>ground(c,label));
            c=await send('touchend',[]);lifecycle.stale.push(c);check(label+' stale end',()=>stationary(settled,c,label+' stale end'));check(label+' stale end root',()=>ground(c,label));
            const fresh=acquire(c,[190,300]), z=c.zoom;
            await send('touchstart',pair([190,300],160));c=await send('touchmove',pair([214,300],192));
            lifecycle.restart=c;check(label+' fresh reused-ID attachment',()=>attach(c,fresh,[214,300],label));
            check(label+' fresh reused-ID zoom',()=>near(c.zoom-z,Math.log2(192/160),.01,label+' fresh own zoom'));
        } else {
            for(let i=0;i<3;i++){c=await frame(0);lifecycle.idle.push(c);check(label+' frozen '+i,()=>stationary(settled,c,label+' frozen'));}
            // Collect elapsed outcomes even if root/view predicates already failed.
            c=await frame(32,3);lifecycle.elapsed=c;
            await frame(200,15);const end=await snapshot();c=await frame(32,8);
            check(label+' eventual rest',()=>stationary(end,c,label+' eventual rest'));
        }
        return lifecycle;
    }
    await run('V5-cancellation',async()=>{await terrainTermination('touchcancel');await terrainTermination('touchcancel',true);return {subcases:2};});
    await run('V5-full-release',async()=>{
        const start=await reset('flat'),points=fiducials.slice(0,3).map(p=>[p[0],p[1],0]);
        await send('touchstart',[[11,300,240]]);
        for(let i=1;i<=3;i++) await send('touchmove',[[11,300+i*20,240]]);
        const committed=await terminate('touchend',[[11,380,240]]);
        for(const [i,P] of points.entries()) {const a=project(start,P),b=project(committed,P);check('flat release committed x '+i,()=>near(b[0]-a[0],80,.5,'release x'));check('flat release committed y '+i,()=>near(b[1]-a[1],0,.5,'release y'));}
        for(let i=0;i<3;i++) {const c=await frame(0);check('flat frozen '+i,()=>stationary(committed,c,'frozen',.05,.0001,points));}
        const elapsed=await frame(32,3),continuation=project(elapsed,points[0])[0]-project(committed,points[0])[0];
        check('flat elapsed ordinary inertia',()=>assert(continuation>1,'Queued full-release lost ordinary inertia: '+continuation));
        observations.push({label:'flat release',start,committed,elapsed,continuation});
        await terrainTermination('touchend');await terrainTermination('touchend',true);
        return {continuation,subcases:3};
    });
    await run('V6-availability-reset', async () => {
        let c = await reset('terrain', true), start = c, P = acquire(c, [190, 280], c.elevation);
        assert(c.elevation === 0, 'Unavailable DEM must start at center plane');
        await send('touchstart', [[11, 190, 280]]);
        c = await send('touchmove', [[11, 230, 280]]);
        attach(c, P, [230, 280], 'fallback first move');
        await page.evaluate(async () => { lab.openDEM(); await lab.usable(); });
        await frame();
        c = await send('touchmove', [[11, 270, 280]]);
        attach(c, P, [270, 280], 'frozen unavailable fallback');
        P = acquire(c, [350, 280]);
        const boundary = c;
        c = await send('touchstart', [[11, 270, 280], [22, 430, 280]]);
        stationary(boundary, c, 'availability handoff');
        c = await send('touchmove', [[11, 250, 280], [22, 490, 280]]);
        attach(c, P, [370, 280], 'available handoff');
        near(c.zoom - boundary.zoom, Math.log2(240 / 160), .01, 'DEM availability handoff separation-to-zoom');
        await frame(200);
        await send('touchend', []);
        const releasedReset = await reset();
        selectedPreset(releasedReset, 'terrain', 'release reset');
        await handoff();
        await send('touchcancel', []);
        const cancelledReset = await reset();
        selectedPreset(cancelledReset, 'terrain', 'cancel reset');
        await handoff();
        return { unavailableStart: start.elevation };
    });
    await run('V6-selected-preset-reset', async () => {
        const observations = [];
        for (const name of ['terrain', 'flat', 'safety', 'globe']) {
            for (const termination of ['touchend', 'touchcancel']) {
                await reset(name);
                const mid = name === 'safety' ? [100, 140] : [300, 300];
                const sep = name === 'safety' ? 40 : 160;
                await send('touchstart', pair(mid, sep));
                await send('touchmove', pair([mid[0] + 20, mid[1]], sep * 1.5));
                // A release after the 200ms pause has no momentum. Cancellation
                // must settle at its first render without needing that pause.
                if (termination === 'touchend') await frame(200);
                await send(termination, []);
                const restored = await reset(name);
                selectedPreset(restored, name, `${name} reset after ${termination}`);
                selectedPreset(await frame(0, 3), name, `${name} reset idle`);
                observations.push({name, termination, restored});
                // reset() preserves the same live map; fresh ownership is exercised
                // on the next loop and throughout V3/V6/V8, without a page reload.
            }
        }
        await screenshot('V6-selected-preset-reset');
        return {observations};
    });
    await run('V7-flat-controls', async () => {
        const points = fiducials.map(p => [p[0], p[1], 0]);
        let start = await reset('flat'), c;
        const firstPixel = await renderedFiducial(start, 'flat initial');
        await page.evaluate(() => { const canvas = lab.map.getCanvas(), r = canvas.getBoundingClientRect(); canvas.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0, buttons: 1, clientX: r.x + 300, clientY: r.y + 240 })); document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, button: 0, buttons: 1, clientX: r.x + 380, clientY: r.y + 240 })); });
        c = await frame();
        for (const p of points.slice(0, 3)) {
            const a = project(start, p), b = project(c, p);
            near(b[0] - a[0], 80, .5, 'mouse flat x');
            near(b[1] - a[1], 0, .5, 'mouse flat y');
        }
        const finalPixel = await renderedFiducial(c, 'flat dragged');
        near(finalPixel[0] - firstPixel[0], 80, .5, 'rendered mouse drag');
        start = await reset('flat');
        await send('touchstart', [[11, 300, 240]]);
        c = await send('touchmove', [[11, 380, 240]]);
        for (const p of points.slice(0, 3)) {
            const a = project(start, p), b = project(c, p);
            near(b[0] - a[0], 80, .5, 'touch flat x');
            near(b[1] - a[1], 0, .5, 'touch flat y');
        }
        start = await reset('flat');
        await send('touchstart', pair([300, 240], 160));
        c = await send('touchmove', pair([300, 240], 240));
        near(c.zoom - start.zoom, Math.log2(1.5), .01, 'flat pinch');
        start = await reset('flat');
        for (let i = 0; i < 4; i++) {
            await page.evaluate(() => { const el = lab.map.getCanvas(), r = el.getBoundingClientRect(); el.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -100, clientX: r.x + 300, clientY: r.y + 240 })); });
            await frame(40);
        }
        c = await frame(50, 10);
        assert(c.zoom > start.zoom + .1, 'Wheel zoom disabled');
        const wheelZoomDelta = c.zoom - start.zoom;
        for (const aroundCenter of [false, true]) {
            start = await reset('flat');
            await page.evaluate(center => { lab.map.touchZoomRotate.enableRotation(); lab.map.touchZoomRotate.enable(center ? { around: 'center' } : undefined); }, aroundCenter);
            const pivot = [410, 320], pivotGrab = acquire(start, pivot, 0);
            await send('touchstart', pair(pivot, 160));
            const twist = angle => { const a = angle * Math.PI / 180; return [[11, 410 - 80 * Math.cos(a), 320 - 80 * Math.sin(a)], [22, 410 + 80 * Math.cos(a), 320 + 80 * Math.sin(a)]]; };
            for (const a of [2, 4]) {
                c = await send('touchmove', twist(a));
                stationary(start, c, 'subthreshold twist', .05, .0001, points);
            }
            c = await send('touchmove', twist(30));
            near(c.bearing, -30, 1, 'accumulated rotation');
            if (aroundCenter) {
                assert(distance(project(c, points[0]), [300, 240]) <= .5, 'off-center gesture ignored explicit center rotation');
                start = await reset('flat');
                await page.evaluate(() => lab.map.touchZoomRotate.enable({around: 'center'}));
                await send('touchstart', pair(pivot, 160));
                c = await send('touchmove', pair(pivot, 240));
                near(c.zoom - start.zoom, Math.log2(1.5), .01, 'explicit center pinch zoom');
                assert(distance(project(c, points[0]), [300, 240]) <= .5, 'explicit center zoom drift');
            } else {
                attach(c, pivotGrab, pivot, 'ordinary off-center rotation pivot');
                assert(distance(project(c, points[0]), [300, 240]) > 1, 'ordinary rotation incorrectly forced around center');
                const survivor = twist(30)[0]; let before = c;
                c = await send('touchend', [survivor]); stationary(before, c, 'rotation survivor boundary', .05, .0001, points);
                const fresh = [33, survivor[1], survivor[2] - 160], mid = [survivor[1], survivor[2] - 80];
                before = c; const grab = acquire(c, mid, 0);
                c = await send('touchstart', [survivor, fresh]); stationary(before, c, 'new angle baseline boundary', .05, .0001, points);
                c = await send('touchmove', [[11, mid[0] - 40, mid[1] + 80 * Math.cos(Math.PI / 6)], [33, mid[0] + 40, mid[1] - 80 * Math.cos(Math.PI / 6)]]);
                near(c.bearing, -60, 1, 'fresh contact configuration angle baseline');
                attach(c, grab, mid, 'fresh rotation grab');
            }
        }
        return { wheelZoomDelta };
    });
    await run('V8-inertia', async () => { const start = await reset('flat'); await send('touchstart', [[11, 300, 240]]); let c; for (let i = 1; i <= 4; i++)
        c = await send('touchmove', [[11, 300 + i * 20, 240]]); const P = [...merc(start.center), 0], before = project(c, P); await send('touchend', []); c = await frame(32, 3); assert(project(c, P)[0] > before[0] + 1, 'Ordinary release inertia removed'); const moved = project(c, P)[0] - before[0]; await frame(200, 15); const settled = await snapshot(); c = await frame(32, 8); stationary(settled, c, 'inertia eventually settles', .05, .0001, [P]); return { continuation: moved }; });
    await run('V8-safety-recovery', async () => {
        let maxRatio = 0;
        for (const pinching of [false, true]) {
            let c = await reset('safety');
            near(c.elevation, 1000, .01, 'Loaded plateau elevation');
            const initial = c, initialCam = camera(c), H0 = envelope(c, [0, 0], 0).H;
            let totalBound = 0;
            const loaded = await page.evaluate(() => lab.map.terrain.tileManager.getRenderableTiles().some(t => lab.map.terrain.getMinMaxElevation(t.tileID).minElevation === 1000));
            assert(loaded, 'Plateau DEM not loaded');
            acquire(c,[100,140],1000); // independently decoded loaded plateau coverage before unsafe input
            await send('touchstart', pinching ? pair([80, 16], 40) : [[11, 60, 16]]);
            let previousSep = 40;
            for (let i = 1; i <= 10; i++) {
                const sep = 40 + 4 * i, dz = pinching ? Math.log2(sep / previousSep) : 0, e = envelope({ ...initial, zoom: initial.zoom + (pinching ? Math.log2(previousSep / 40) : 0) }, [4, 0], dz), previous = camera(c);
                totalBound += e.B;
                c = await send('touchmove', pinching ? pair([80 + 4 * i, 16], sep) : [[11, 60 + 4 * i, 16]]);
                const cam = camera(c), d = distance(cam.pos.slice(0, 2), previous.pos.slice(0, 2)) / metres(45.9);
                assert(d <= e.B + 1e-6, `Unsafe camera displacement ${d} > ${e.B}`);
                maxRatio = Math.max(maxRatio, d / e.B);
                near(c.pitch, 80, .0001, 'safety fixed pitch');
                near(c.bearing, 0, .0001, 'safety fixed bearing');
                near(c.zoom - initial.zoom, pinching ? Math.log2(sep / 40) : 0, .01, 'safety genuine zoom');
                const H = (cam.pos[2] - 1000) * metres(c.center[1]) / metres(45.9);
                near(H / H0, 2 ** -(pinching ? Math.log2(sep / 40) : 0), .01 * 2 ** -(pinching ? Math.log2(sep / 40) : 0), 'scaled clearance');
                assert(cam.pos[2] > 1000, 'Camera under plateau');
                assert(c.zoom >= 0 && c.zoom <= 22 && c.pitch <= 85 && Math.abs(c.center[1]) <= 85.05113, 'Navigation constraints');
                assert(distance(cam.pos.slice(0, 2), initialCam.pos.slice(0, 2)) / metres(45.9) <= totalBound + 1e-6, 'Whole trace envelope');
                previousSep = sep;
            }
            await send('touchcancel', []);
            c = await snapshot();
            const P = acquire(c, [100, 140], 1000), recoveryZoom = c.zoom;
            await send('touchstart', pair([100, 140], 40));
            c = await send('touchmove', pair([110, 144], 60));
            attach(c, P, [110, 144], 'same-live-map recovery');
            near(c.zoom - recoveryZoom, Math.log2(60 / 40), .01, 'safe recovery rearmed pinch');
        }
        return { maxRatio };
    });
    await run('V8-globe', async () => { let start = await reset('globe'); await send('touchstart', [[11, 300, 240]]); let c = await send('touchmove', [[11, 380, 240]]); assert(distance(merc(c.center), merc(start.center)) > .001, 'Globe pan disabled'); await send('touchcancel', []); start = await snapshot(); await send('touchstart', pair([300, 240], 160)); c = await send('touchmove', pair([300, 240], 240)); assert(c.zoom > start.zoom + .2, 'Globe pinch disabled'); return { zoom: c.zoom }; });
    await page.evaluate(() => lab.replay());
    await screenshot('public-handoff-replay');
    await screenshot('final');
    assert(!errors.length, 'Browser runtime errors: ' + errors.join('; '));
}
catch (e) {
    failures.push({ id: 'runtime', error: e.stack });
    console.error(e);
}
finally {
    writeFileSync(join(artifacts, 'results.json'), JSON.stringify({ results, failures, errors, calibration, subchecks, observations }, null, 2));
    await browser.close();
    rmSync(profile, { recursive: true, force: true });
}
if (failures.length) {
    console.error(JSON.stringify(failures, null, 2));
    process.exitCode = 1;
}
else
    console.log('All behavioral assertions passed. Artifacts:', artifacts);
