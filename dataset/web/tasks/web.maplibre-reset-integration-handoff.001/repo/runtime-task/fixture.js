import {Map as MapLibreMap, NavigationControl, addProtocol} from '/dist/maplibre-gl-dev.mjs';
import {merc, lnglat} from './geometry.js';

// Both integrations use the same live renderer Terrain. Only navigation queries differ.
/** @type {import('../src/render/terrain_queries.ts').TerrainQueryFactory} */
const legacyQueries = terrain => ({
    pointCoordinate: terrain.pointCoordinate.bind(terrain),
    getElevationForLngLat: terrain.getElevationForLngLat.bind(terrain),
    getElevationForLngLatZoom: terrain.getElevationForLngLatZoom.bind(terrain)
});
addProtocol('localdem', async req => ({data: await (await fetch(`/runtime-task/assets/${req.url.split('://')[1]}`)).arrayBuffer()}));
const M = await (await fetch('manifest.json')).json();
const base = merc(M.camera.center);
const feature = (coord, properties) => ({type: 'Feature', properties, geometry: {type: 'Point', coordinates: coord}});
const landmarks = M.landmarks.map(p => feature(lnglat([base[0] + p.offset[0], base[1] + p.offset[1]]), {color: p.color}));
const ridge = landmarks[3].geometry.coordinates;
const grid = [];
for (let i = -14; i <= 14; i++) for (let j = -14; j <= 14; j++) {
    const a = [base[0] + i * .000025, base[1] + j * .000025], b = [a[0] + .000025, a[1] + .000025];
    grid.push({type: 'Feature', properties: {color: (i + j) % 2 ? '#77977f' : '#a6b788'}, geometry: {type: 'Polygon', coordinates: [[a, [b[0], a[1]], b, [a[0], b[1]], a].map(lnglat)]}});
}
function style(points) {
    return {version: 8, sources: {
        grid: {type: 'geojson', data: {type: 'FeatureCollection', features: grid}},
        landmarks: {type: 'geojson', data: {type: 'FeatureCollection', features: points}}
    }, layers: [
        {id: 'bg', type: 'background', paint: {'background-color': '#b2c9d8'}},
        {id: 'grid', type: 'fill', source: 'grid', paint: {'fill-color': ['get', 'color'], 'fill-outline-color': '#39544c'}},
        {id: 'landmarks', type: 'circle', source: 'landmarks', paint: {'circle-radius': 6, 'circle-color': ['get', 'color'], 'circle-stroke-color': '#172535', 'circle-stroke-width': 1}}
    ]};
}
const options = {attributionControl: false, fadeDuration: 0, clickTolerance: 1, canvasContextAttributes: {preserveDrawingBuffer: true}};
const map = new MapLibreMap({...options, container: 'map', style: style(landmarks), ...M.camera, maxPitch: 85});
const flatPoints = [[0, 0], [-.000025, .00002], [.00003, -.00001]].map((offset, i) => feature(lnglat([base[0] + offset[0], base[1] + offset[1]]), {color: ['#ff2020', '#00ffff', '#ffff00'][i]}));
const flat = new MapLibreMap({...options, container: 'flat-map', style: style(flatPoints), center: M.camera.center, zoom: 12});
flat.addControl(new NavigationControl({showCompass: false}), 'top-right');
const $ = id => document.getElementById(id);
let integration = 'Native', busy = true, contacts = [], stage = -1, origin, lastMidpoint;
const overlay = document.createElement('div');
overlay.className = 'contacts';
map.getContainer().append(overlay);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function frame() { await new Promise(resolve => { map.once('render', resolve); map.triggerRepaint(); }); }
async function ready() {
    for (let i = 0; i < 600; i++) {
        if (map.isSourceLoaded('dem') && map.isSourceLoaded('grid') && map.isSourceLoaded('landmarks') &&
            map.terrain.tileManager.getRenderableTiles().some(t => map.terrain.getMinMaxElevation(t.tileID).minElevation !== null)) {
            await frame(); await frame();
            return;
        }
        await sleep(25);
    }
    throw Error('Terrain or geographic features not loaded; reset and try again.');
}
function controls() {
    for (const id of ['native', 'legacy', 'reset', 'begin']) $(id).disabled = busy || contacts.length > 0;
    for (let i = 1; i <= 3; i++) $('step' + i).disabled = busy || stage !== i - 1;
    $('release').disabled = busy || !contacts.length;
    $('native').setAttribute('aria-pressed', String(integration === 'Native'));
    $('legacy').setAttribute('aria-pressed', String(integration === 'Legacy'));
}
function draw() {
    overlay.replaceChildren();
    const ring = (x, y, cls, label = '') => { const e = document.createElement('div'); e.className = cls; e.style.left = x + 'px'; e.style.top = y + 'px'; e.textContent = label; overlay.append(e); };
    for (const [id, x, y] of contacts) ring(x, y, 'finger', String(id));
    if (lastMidpoint) ring(...lastMidpoint, 'midpoint');
}
function send(type, positions) {
    const canvas = map.getCanvas(), r = canvas.getBoundingClientRect(), old = contacts;
    const make = ([id, x, y]) => new Touch({identifier: id, target: canvas, clientX: r.x + x, clientY: r.y + y});
    const changed = type === 'touchstart' ? positions.filter(p => !old.some(o => p[0] === o[0])) : type === 'touchend' ? old : positions;
    contacts = positions.map(p => p.slice());
    if (contacts.length === 2) lastMidpoint = [(contacts[0][1] + contacts[1][1]) / 2, (contacts[0][2] + contacts[1][2]) / 2];
    canvas.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true, touches: contacts.map(make), targetTouches: contacts.map(make), changedTouches: changed.map(make)}));
    draw();
    const text = type + ' ' + JSON.stringify(contacts.map(p => p.map(v => Math.round(v * 100) / 100)));
    $('trace').textContent += '\n' + text;
    $('trace').scrollTop = $('trace').scrollHeight;
}
function pair(dx, separation) { return [[11, origin[0] + dx - separation / 2, origin[1]], [22, origin[0] + dx + separation / 2, origin[1]]]; }
async function reset() {
    map.stop(); map.setTerrain(null);
    if (map.getSource('dem')) map.removeSource('dem');
    stage = -1; lastMidpoint = null; draw();
    map.jumpTo({...M.camera, elevation: 0});
    map.addSource('dem', {type: 'raster-dem', tiles: ['localdem://{x}.png'], tileSize: 512, minzoom: 12, maxzoom: 12, encoding: 'terrarium'});
    map.setTerrain({source: 'dem', exaggeration: 1});
    // Fixed local mesh resolution, shared by both integrations (as in this fixture's DEM).
    map.terrain.tileManager.deltaZoom = 0;
    map.terrain.tileManager.tileSize = 512;
    map.terrain.tileManager.tileManager.tileSize = 512;
    map.terrain.tileManager.minzoom = 12;
    map.terrain.tileManager.maxzoom = 12;
    await ready(); map.jumpTo(M.camera); await ready();
    $('trace').textContent = 'No contacts yet.';
    $('status').textContent = integration + ' · Ready · loaded terrain rendered';
}
async function begin() {
    await ready();
    const p = map.project(ridge);
    origin = [p.x, p.y];
    if (p.x < 82 || p.x + 220 > 600 || p.y < 30 || p.y > 450) throw Error('Ridge or contacts outside demonstration area. Reset to continue.');
    $('trace').textContent = 'CSS pixels relative to terrain map; midpoint starts at the magenta place.';
    send('touchstart', pair(0, 160)); stage = 0; await frame();
    $('status').textContent = integration + ' · Contacts held · choose Move 1';
}
async function step(i) {
    const move = M.moves[i - 1];
    send('touchmove', pair(move.dx, move.separation)); stage = i;
    await ready();
    $('status').textContent = integration + ' · Move ' + i + ' held' + (i < 3 ? ' · choose Move ' + (i + 1) : ' · Release when ready');
}
async function release() {
    // A visible held demonstration, not a flick: let the last motion age out of inertia.
    await sleep(250);
    send('touchend', []); stage = -1;
    await ready(); await sleep(250); await frame();
    $('status').textContent = integration + ' · Released · repeat Move and zoom or drag normally';
}
async function action(fn) {
    busy = true; controls(); $('error').textContent = '';
    try { await fn(); } catch (e) { $('error').textContent = e.message; $('status').textContent = 'Example unavailable'; }
    finally { busy = false; controls(); }
}
for (const name of ['Native', 'Legacy']) $(name.toLowerCase()).onclick = () => action(async () => {
    integration = name; map.setTerrainQueryFactory(name === 'Legacy' ? legacyQueries : null);
    $('status').textContent = name + ' selected · Reset for a fresh comparison';
});
$('reset').onclick = () => action(reset);
$('begin').onclick = () => action(begin);
for (let i = 1; i <= 3; i++) $('step' + i).onclick = () => action(() => step(i));
$('release').onclick = () => action(release);
await new Promise(resolve => map.once('load', resolve));
map.touchPitch.disable(); map.touchZoomRotate.disableRotation(); map.doubleClickZoom.disable();
await action(reset);
