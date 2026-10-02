// Native mouse attachment: RGB connected components, public-control locators,
// and observation-only overlay handling reused from the retained query checker.
// No camera, projection, fixture geometry, debug state, or source-token oracle.
// The retained checker remains a separate public verifier for touch/flat coverage.
import {createRequire} from 'node:module';
import {resolve, join} from 'node:path';
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
const workspace = resolve(process.env.CUA_SWE_WORKSPACE || process.cwd());
const require = createRequire(join(workspace, 'package.json'));
const artifactRoot = process.env.CUA_SWE_VERIFIER_ARTIFACTS || mkdtempSync(join(tmpdir(), 'mouse-ridge-'));
const artifacts = join(artifactRoot, 'mouse-ridge');
mkdirSync(artifacts, {recursive: true});
const report = {status: 'inconclusive', toleranceStatus: 'prospective; healthy mouse reference not yet validated', assertions: [], states: [], actions: [], inputEvents: [], workflows: {}, inconclusive: [], errors: []};
const T = {attachment: 3, retention: 3, integrations: 4};
const trace = [{dx: 0, separation: 160}, {dx: 32, separation: 192}, {dx: 64, separation: 224}, {dx: 88, separation: 256}];
const terrainRegion = 'Sloped terrain map', flatRegion = 'Flat map';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const midpoint = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
class Inconclusive extends Error {}
class SemanticFailure extends Error {}
const paints = new Map();
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
    state.gridPixels = gridPixels(png);
    if (state.gridPixels < 1000) throw new Inconclusive('Geographic grid paint unavailable');
    paints.set(state.label, png);
    return state;
}

function retained(label, before, after, t = T.retention) {
    check(label + ' ridge', after.anchor, before.anchor, t); check(label + ' companion', after.companion, before.companion, t);
}
async function demo(mode, cycle, before) {
    const prefix = mode + '-' + cycle;
    await click('Move and zoom'); await waitButton('Move 1');
    const start = await settled(prefix + '-start', terrainRegion, true);
    retained(prefix + ' acquisition stationary', before, start);
    check(prefix + ' starts around ridge', start.anchor, start.midpoint, T.attachment);
    if (Math.abs(start.contactSeparation-160) > 1.5) throw new Inconclusive('Start contact separation not reached');
    const endpoints = []; let previousSeparation = start.separation;
    for (let i = 1; i <= 3; i++) {
        await click('Move ' + i); await waitButton(i < 3 ? 'Move ' + (i+1) : 'Release');
        const s = await settled(prefix + '-move' + i, terrainRegion, true);
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
    const released = await settled(prefix + '-released'); retained(prefix + ' accepted release', endpoints.at(-1), released);
    const idle = await settled(prefix + '-idle'); retained(prefix + ' released idle', released, idle);
    decisive(prefix);
    return {start, endpoints, released, idle};
}
// Narrow paint checks for this public geographic grid, not a general visual oracle.
function gridColor(r, g, b) {
    return (Math.abs(r-119)<18 && Math.abs(g-151)<18 && Math.abs(b-127)<18) ||
        (Math.abs(r-166)<18 && Math.abs(g-183)<18 && Math.abs(b-136)<18) ||
        (Math.abs(r-57)<15 && Math.abs(g-84)<15 && Math.abs(b-76)<15);
}
function gridPixels(png) {
    let n=0;
    for (let i=0;i<png.data.length;i+=4) if(gridColor(...png.data.subarray(i,i+3))) n++;
    return n;
}
function gridDifference(a, b, shiftX=0, shiftY=0) {
    if(a.width!==b.width || a.height!==b.height) throw new Inconclusive('Paint sizes changed');
    let changed=0, eligible=0;
    // Exclude landmarks/indicators by considering only these three grid colors.
    for(let y=8;y<a.height-8;y+=3) for(let x=8;x<a.width-8;x+=3) {
        const i=4*(y*a.width+x), j=4*((y+shiftY)*b.width+x+shiftX);
        const aa=a.data.subarray(i,i+3), bb=b.data.subarray(j,j+3);
        if(!gridColor(...aa) && !gridColor(...bb)) continue;
        eligible++;
        if(Math.max(...aa.map((v,k)=>Math.abs(v-bb[k])))>35) changed++;
    }
    if(eligible<100) throw new Inconclusive('Too little shared grid paint');
    return changed/eligible;
}
function gridRetention(label, before, after) {
    const a=paints.get(before.label), b=paints.get(after.label);
    let best=Infinity, shift;
    // Same 3px allowance as landmark retention, applied to grid raster alignment.
    for(let dy=-3;dy<=3;dy++) for(let dx=-3;dx<=3;dx++) {
        if(Math.hypot(dx,dy)>T.retention) continue;
        const error=gridDifference(a,b,dx,dy);
        if(error<best) {best=error; shift=[dx,dy];}
    }
    check(label+' grid retained',best,0,.035);
    report.assertions.at(-1).bestRasterShift=shift;
}
function decisive(label) {
    if(report.assertions.some(a=>!a.passed)) throw new SemanticFailure('Reached semantic failure at '+label);
}
// Poll actual painted states until BOTH geographic dots and grid are stable for
// a continuous interval. These are read-only observations, not staged wait input.
// Every sampled frame (including unavailable paint) is retained, not overwritten.
async function settled(label, region=terrainRegion, held=false, stableMs=650) {
    const deadline=Date.now()+25000;
    let reference, since=0, frames=0, lastReason='paint not observed';
    for(let i=0;Date.now()<deadline;i++) {
        try {
            const s=await capture(label+'-frame'+i,region,held);
            s.sampleTime=Date.now();
            const stationary=reference && distance(reference.anchor,s.anchor)<=.65 &&
                distance(reference.companion,s.companion)<=.65 &&
                gridDifference(paints.get(reference.label),paints.get(s.label))<=.004;
            if(!stationary) {
                if(reference) paints.delete(reference.label);
                reference=s; since=Date.now(); frames=0;
            }
            frames++;
            if(frames>=3 && Date.now()-since>=stableMs) {
                s.stability={reference:reference.label,frames,durationMs:Date.now()-since};
                if(reference!==s) paints.delete(reference.label);
                return s;
            }
            if(reference!==s) paints.delete(s.label);
            lastReason='paint not yet stable';
        } catch(e) {
            if(!(e instanceof Inconclusive)) throw e;
            report.states.at(-1).observationError=e.message;
            if(reference) paints.delete(reference.label);
            reference=undefined; since=0; frames=0; lastReason=e.message;
        }
        await sleep(100);
    }
    throw new Inconclusive(label+': '+lastReason);
}
// Observe real browser-delivered input solely to distinguish unavailable driving
// from product behavior. Do not dispatch DOM mouse events or read application state.
async function observeInput() {
    await page.exposeFunction('__recordRidgeInput', event => report.inputEvents.push(event));
    await page.evaluate(() => {
        for(const type of ['mousedown','mousemove','mouseup','wheel']) {
            window.addEventListener(type,e => {
                const region=e.target.closest?.('[role="region"][aria-label="Sloped terrain map"]');
                window.__recordRidgeInput({type:e.type, trusted:e.isTrusted, buttons:e.buttons,
                    button:e.button, client:[e.clientX,e.clientY], deltaY:e.deltaY,
                    region:region?.getAttribute('aria-label'), time:e.timeStamp});
            },{capture:true,passive:true});
        }
    });
}
async function delivered(since,type,client,buttons,region=terrainRegion) {
    const deadline=Date.now()+3000;
    do {
        const event=report.inputEvents.slice(since).find(e=>e.type===type && e.trusted &&
            e.buttons===buttons && e.region===region && distance(e.client,client)<=1);
        if(event) return event;
        await sleep(25);
    } while(Date.now()<deadline);
    throw new Inconclusive('Real '+type+' endpoint/buttons/target not confirmed');
}
function safePoint(box, point) {
    if(point[0]<24 || point[1]<24 || point[0]>box.width-24 || point[1]>box.height-24)
        throw new Inconclusive('Planned held endpoint would approach map edge');
    return [Math.round(box.x+point[0]),Math.round(box.y+point[1])];
}
function movedTogether(label,before,after,prescribedDelta) {
    const companionDelta=after.companion.map((v,i)=>v-before.companion[i]);
    const along=companionDelta.reduce((sum,v,i)=>sum+v*prescribedDelta[i],0)/Math.hypot(...prescribedDelta);
    progress(label+' companion travels with map',along,4);
    const fraction=gridDifference(paints.get(before.label),paints.get(after.label));
    progress(label+' geographic grid moves',fraction,.003);
}
async function mouseGrab(label,before,offsets) {
    const box=await regionBox(terrainRegion), start=safePoint(box,before.anchor);
    const endpoints=offsets.map(d=>safePoint(box,before.anchor.map((v,i)=>v+d[i])));
    report.actions.push({kind:'planned mouse grab',label,start,endpoints,sourceFrame:before.label});
    await page.mouse.move(...start);
    let n=report.inputEvents.length;
    await page.mouse.down({button:'left'});
    await delivered(n,'mousedown',start,1);
    report.actions.push({kind:'drag_start',label,client:start});
    const pressed=await settled(label+'-pressed');
    retained(label+' stationary press',before,pressed); gridRetention(label+' stationary press',before,pressed);
    decisive(label+' press');
    let previous=pressed, previousClient=start;
    const held=[];
    for(let i=0;i<endpoints.length;i++) {
        const client=endpoints[i]; n=report.inputEvents.length;
        // Only drag moves and read-only observations occur until mouse-up.
        await page.mouse.move(...client,{steps:8});
        const input=await delivered(n,'mousemove',client,1);
        report.actions.push({kind:'drag_move',label,index:i,client,input});
        const state=await settled(label+'-held'+(i+1));
        const expected=[client[0]-box.x,client[1]-box.y];
        state.prescribedPointer=expected; state.inputClient=client;
        check(label+' held'+(i+1)+' geographic attachment',state.anchor,expected,T.attachment);
        movedTogether(label+' held'+(i+1),previous,state,client.map((v,k)=>v-previousClient[k]));
        held.push(state); previous=state; previousClient=client;
        // A complete negative need not reach the remainder of this sequence.
        decisive(label+' held'+(i+1));
    }
    // settled() has already observed a comfortably paused endpoint before release.
    n=report.inputEvents.length;
    await page.mouse.up({button:'left'});
    await delivered(n,'mouseup',previousClient,0);
    report.actions.push({kind:'drag_end',label,client:previousClient});
    const released=await settled(label+'-released');
    retained(label+' paused release',previous,released); gridRetention(label+' paused release',previous,released);
    const idle=await settled(label+'-idle');
    retained(label+' accepted idle',released,idle); gridRetention(label+' accepted idle',released,idle);
    decisive(label+' release');
    return {pressed,held,released,idle};
}
async function wheelZoom(label,before) {
    const box=await regionBox(terrainRegion), client=safePoint(box,before.anchor);
    await page.mouse.move(...client);
    const n=report.inputEvents.length;
    await page.mouse.wheel({deltaY:-120});
    const event=await delivered(n,'wheel',client,0);
    if(event.deltaY>=0) throw new Inconclusive('Zoom-in wheel input not reached');
    report.actions.push({kind:'wheel before drag',label,client,deltaY:-120,event});
    const zoomed=await settled(label+'-settled',terrainRegion,false,1000);
    progress(label+' ordinary wheel magnifies geographic separation',zoomed.separation-before.separation,3);
    progress(label+' wheel moves grid',gridDifference(paints.get(before.label),paints.get(zoomed.label)),.003);
    decisive(label);
    return zoomed;
}
const modes={};
async function runMode(mode) {
    const workflow=report.workflows[mode]={status:'in progress',reached:[]};
    await waitButton(mode); await click(mode); await waitButton('Reset'); await click('Reset');
    await waitButton('Move and zoom');
    const initial=await settled(mode+'-loaded'); workflow.reached.push('loaded');
    const fresh=await mouseGrab(mode+'-fresh',initial,[[32,14],[8,-6]]);
    workflow.reached.push('fresh mouse and paused release');
    const touch=await demo(mode,'touch-after-mouse',fresh.idle);
    workflow.reached.push('existing touch sequence released without Reset');
    const postTouch=await mouseGrab(mode+'-after-touch',touch.idle,[[-36,18],[12,-10]]);
    workflow.reached.push('post-touch direction change and release');
    const regrab=await mouseGrab(mode+'-reacquire',postTouch.idle,[[-28,12],[-12,0]]);
    workflow.reached.push('reacquisition from accepted view');
    const wheel=await wheelZoom(mode+'-wheel',regrab.idle);
    workflow.reached.push('unheld wheel settled');
    const postWheel=await mouseGrab(mode+'-after-wheel',wheel,[[28,16],[-16,-8]]);
    workflow.reached.push('post-wheel held endpoints and paused release');
    await waitButton('Reset'); await click('Reset'); await waitButton('Move and zoom');
    const resetLoaded=await settled(mode+'-reset-loaded');
    retained(mode+' Reset restores initial view',initial,resetLoaded);
    gridRetention(mode+' Reset restores initial view',initial,resetLoaded);
    decisive(mode+' Reset');
    workflow.reached.push('Reset restored the loaded initial terrain view');
    const postReset=await mouseGrab(mode+'-after-reset',resetLoaded,[[-24,10],[4,-6]]);
    workflow.reached.push('paused mouse reacquisition after terrain Reset');
    const other=mode==='Native'?'Legacy':'Native';
    await waitButton(other); await click(other); await waitButton('Move and zoom');
    const followUpStart=await settled(mode+'-reset-then-switch-'+other);
    retained(mode+' integration switch preserves accepted view',postReset.idle,followUpStart);
    gridRetention(mode+' integration switch preserves accepted view',postReset.idle,followUpStart);
    decisive(mode+' post-Reset integration switch');
    workflow.reached.push('other integration selected without Reset or held contacts');
    const followUp=await mouseGrab(mode+'-after-reset-switch',followUpStart,[[-28,12],[-12,0]]);
    workflow.reached.push('fresh paused mouse grab after integration switch');
    modes[mode]={initial,fresh,touch,postTouch,regrab,wheel,postWheel,resetLoaded,postReset,followUpStart,followUp}; workflow.status='complete';
}
try {
    const puppeteer=require('puppeteer'); ({PNG}=require('pngjs'));
    profile=mkdtempSync(join(artifacts,'profile-'));
    browser=await puppeteer.launch({executablePath:process.env.CUA_SWE_VERIFIER_CHROME_PATH || process.env.CHROME_PATH || '/usr/bin/google-chrome',
        userDataDir:profile,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-webgl','--ignore-gpu-blocklist','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader-webgl']});
    page=await browser.newPage(); await page.setViewport({width:1000,height:800,deviceScaleFactor:1,hasTouch:true});
    page.on('pageerror',e=>report.errors.push(e.message));
    const url=new URL(process.env.CUA_SWE_WEB_URL || `http://127.0.0.1:${process.env.CUA_SWE_WEB_PORT || 4173}/runtime-task/index.html`);
    if(url.pathname==='/') url.pathname='/runtime-task/index.html'; report.url=url.href;
    // Supplied service only: no installation, build, startup, or new runtime contract.
    await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:60000}); await observeInput();
    for(const mode of ['Native','Legacy']) {
        try {await runMode(mode);} catch(e) {
            report.workflows[mode] ||= {reached:[]};
            report.workflows[mode].status=e instanceof SemanticFailure?'semantic failure':'inconclusive';
            report.workflows[mode].error=String(e.stack || e);
            if(!(e instanceof SemanticFailure)) uncertainty(mode,e);
            try {await page.screenshot({path:join(artifacts,mode+'-stopped.png')});} catch {}
            // Cleanup is mouse-up only. Later sequence states remain unobserved.
            try {await page.mouse.up({button:'left'});} catch {}
            if(e instanceof SemanticFailure) break;
            // No author/runtime retry; another mode begins a distinct public workflow.
            try {await click('Release'); await waitButton('Move and zoom');} catch {}
        }
    }
    if(modes.Native && modes.Legacy) {
        retained('Native/Legacy loaded',modes.Native.initial,modes.Legacy.initial,T.integrations);
        for(const step of ['fresh','postTouch','regrab','postWheel','postReset','followUp']) {
            for(let i=0;i<2;i++) retained('Native/Legacy '+step+' held'+(i+1),modes.Native[step].held[i],modes.Legacy[step].held[i],T.integrations);
            retained('Native/Legacy '+step+' accepted view',modes.Native[step].idle,modes.Legacy[step].idle,T.integrations);
        }
        retained('Native/Legacy completed wheel',modes.Native.wheel,modes.Legacy.wheel,T.integrations);
        retained('Native/Legacy Reset loaded view',modes.Native.resetLoaded,modes.Legacy.resetLoaded,T.integrations);
        retained('Native/Legacy follow-up starting view',modes.Native.followUpStart,modes.Legacy.followUpStart,T.integrations);
    } else if(!report.assertions.some(a=>!a.passed)) uncertainty('Integration comparison','Both complete sequential mouse workflows not reached');
} catch(e) {uncertainty('Driver/runtime',e);}
finally {
    if(report.errors.length) uncertainty('Page runtime',report.errors.join('; '));
    const failed=report.assertions.filter(a=>!a.passed);
    report.status=failed.length?'fail':report.inconclusive.length?'inconclusive':modes.Native && modes.Legacy?'pass':'inconclusive';
    report.failures=failed; report.reachedAssertions=report.assertions.length;
    report.coverageNote='Only recorded assertions were reached. The original public checker separately preserves both repeated touch demos, integration comparison and flat drag/zoom.';
    try {await browser?.close();} catch(e) {uncertainty('Browser cleanup',e); if(!failed.length) report.status='inconclusive';}
    if(profile) rmSync(profile,{recursive:true,force:true});
    writeFileSync(join(artifacts,'results.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({status:report.status,reachedAssertions:report.reachedAssertions,failures:failed.length,inconclusive:report.inconclusive,artifacts}));
    process.exitCode=report.status==='pass'?0:report.status==='fail'?1:2;
}
