import {nearest, ReadinessError} from './nearest.mjs';
// Independent observation geometry. Derived from public M; no application imports.
export const rad = Math.PI / 180, radius = 6371008.8;
export const merc = ([lng, lat]) => [(lng + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + lat * rad / 2)) / Math.PI) / 2];
export const metres = lat => 1 / (2 * Math.PI * radius * Math.cos(lat * rad));
export const height = x => 1400 - 1000 * Math.max(0, Math.min(1, (x - 0.520782470703125) / 1.52587890625e-05));
export const distance = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]));
export function camera(c) {
    const p = c.pitch * rad, b = c.bearing * rad, f = c.height / (2 * Math.tan(c.fov * rad / 2)), w = 512 * 2 ** c.zoom, m = metres(c.center[1]);
    const cp = [(c.width + c.padding.left - c.padding.right) / 2, (c.height + c.padding.top - c.padding.bottom) / 2];
    const right = [Math.cos(b), Math.sin(b), 0], down = [-Math.sin(b) * Math.cos(p), Math.cos(b) * Math.cos(p), -Math.sin(p)], back = [-Math.sin(b) * Math.sin(p), Math.cos(b) * Math.sin(p), Math.cos(p)];
    const ct = merc(c.center), pos = [ct[0] + back[0] * f / w, ct[1] + back[1] * f / w, c.elevation + back[2] * f / w / m];
    return { f, w, m, cp, right, down, back, pos };
}
export function ray(c, s) { const k = camera(c), x = (s[0] - k.cp[0]) / k.f, y = (s[1] - k.cp[1]) / k.f; return { o: k.pos, d: [0, 1, 2].map(i => (k.right[i] * x + k.down[i] * y - k.back[i]) / (i === 2 ? k.m : 1)) }; }
export function project(c, P) { const k = camera(c), v = [(P[0] - k.pos[0]) * k.w, (P[1] - k.pos[1]) * k.w, (P[2] - k.pos[2]) * k.w * k.m], dot = a => a.reduce((s, x, i) => s + x * v[i], 0), depth = -dot(k.back); if (!(depth > 0)) throw Error('Nonpositive fiducial depth'); return [k.cp[0] + k.f * dot(k.right) / depth, k.cp[1] + k.f * dot(k.down) / depth]; }
export function acquire(c, s, h = height) {
    const { o, d } = ray(c, s);
    if (d[2] >= 0)
        throw Error('Oracle acquisition ray is skyward');
    if (typeof h === 'number') {
        const t = (h - o[2]) / d[2];
        if (!(t > 0)) throw Error('No positive plane hit');
        const P=[o[0]+t*d[0],o[1]+t*d[1],h];
        if(h===1000 && !c.support?.some(([a,b,c,e])=>P[0]>=a && P[0]<=b && P[1]>=c && P[1]<=e)) throw new ReadinessError('Plateau recovery outside loaded XY support');
        return P;
    }
    return nearest(o, d, c.support).hits[0].p;
}
const c0 = merc([7.5, 45.9]);
export const fiducials = [[0, 0], [-.000025, .00002], [.00003, -.00001], [-.00007, 0], [.00008, .000015]].map(([x, y]) => [c0[0] + x, c0[1] + y, height(c0[0] + x)]);
export function finite(value) {
    if (typeof value === 'number') {
        if (!Number.isFinite(value))
            throw Error('Nonfinite numeric observation');
    }
    else if (value && typeof value === 'object') {
        for (const v of Object.values(value))
            finite(v);
    }
    else
        throw Error('Missing or nonnumeric scalar observation');
}
// Exact envelope for the specified horizontal d and zero bearing/roll plateau.
// g=(u/D, (v*cos(p)-sin(p))/D); D=cos(p)+v*sin(p).
// |g| and the horizontal difference are largest at K's top corners/top edge.
export function envelope(c, d, delta) {
    const k = camera(c), p = c.pitch * rad, yH = k.cp[1] - k.f / Math.tan(p), top = Math.max(0, yH + 30), v = (top - k.cp[1]) / k.f, D = Math.cos(p) + v * Math.sin(p);
    const gy = (v * Math.cos(p) - Math.sin(p)) / D;
    const R = Math.max(...[0, c.width].map(x => Math.hypot((x - k.cp[0]) / k.f / D, gy)));
    const T = Math.abs(d[0]) / k.f / D;
    const H = k.f * Math.cos(p) / (k.w * metres(45.9)), q = 2 ** -delta;
    const eps = 0.05 * Math.max(1, q) / (k.w * metres(45.9) * Math.cos(p));
    return { R, T, H, q, B: H * (Math.abs(1 - q) * R + Math.max(1, q) * T) + eps, top, yH };
}
export function validateEnvelope() {
    const c = { center: [7.5, 45.9], elevation: 1000, width: 200, height: 200, zoom: 11, pitch: 80, bearing: 0, roll: 0, fov: 36.86989764584402, padding: { left: 0, right: 0, top: 0, bottom: 0 } };
    const samples = [];
    for (const [dx, dz] of [[0, 0], [4, 0], [4, Math.log2(1.1)], [4, -Math.log2(1.1)], [0, Math.log2(1.1)]]) {
        const e = envelope(c, [dx, 0], dz);
        if (e.top > 100)
            throw Error('Center excluded from K');
        for (let x = 0; x <= 200 - Math.abs(dx); x += 5)
            for (let y = e.top; y <= 200; y += 3) {
                const a = ray(c, [x, y]), b = ray(c, [x + dx, y]), g = r => [r.d[0] / (-r.d[2] * metres(45.9)), r.d[1] / (-r.d[2] * metres(45.9))], ga = g(a), gb = g(b);
                const move = e.H * distance(ga, gb.map(v => v * e.q));
                if (move > e.B + 1e-8)
                    throw Error('Analytical safety envelope invalid');
            }
        samples.push({ dx, dz, ...e });
    }
    const e = envelope(c, [0, 0], Math.log2(1.1)), checkpoint = e.H * Math.tan(80 * rad) / 11;
    if (checkpoint > e.B)
        throw Error('40→44 center zoom incorrectly rejected');
    return { samples, checkpoint, checkpointInH: checkpoint / e.H };
}

// Published M presets; separate protected observations, not a mutable page verdict.
export function presetView(name) {
    const c = {center: [7.5, 45.9], width: 600, height: 480, zoom: 12.5,
        pitch: 0, bearing: 0, roll: 0, fov: 36.86989764584402, elevation: 0,
        padding: {left: 0, right: 0, top: 0, bottom: 0}};
    if (name === 'terrain') Object.assign(c, {pitch: 55, bearing: 27,
        elevation: height(merc(c.center)[0]), padding: {left: 64, right: 16, top: 44, bottom: 12}});
    if (name === 'safety') Object.assign(c, {width: 200, height: 200, zoom: 11, pitch: 80, elevation: 1000});
    if (name === 'globe') c.zoom = 2;
    return c;
}
// Zoom is a product response to separation, independently recognized per contact
// membership. No reset on array reorder. Single-contact phases contribute zero.
export function zoomCheckpoints(trace, initialZoom) {
    let key = '', baseZoom = initialZoom, zoom = initialZoom, startSeparation = 0, recognized = false;
    return trace.map(([type, points], event) => {
        const ids = points.map(p => p[0]).sort((a, b) => a - b).join(',');
        const separation = points.length === 2 ? distance(points[0].slice(1), points[1].slice(1)) : 0;
        if (ids !== key) {
            key = ids; baseZoom = zoom; startSeparation = separation; recognized = false;
        }
        let firstRecognized = false;
        if (type === 'touchmove' && points.length === 2) {
            const response = Math.log2(separation / startSeparation);
            if (!recognized && Math.abs(response) >= .1) { recognized = true; firstRecognized = true; }
            if (recognized) zoom = baseZoom + response;
        }
        return {event, ids, separation, zoom, firstRecognized};
    });
}

export function settledGround(c) {
 finite(c); if(Math.abs(c.roll)>1e-9) throw Error('M terrain controls require roll0');
 const {o,d}=ray(c,camera(c).cp), roots=nearest(o,d,c.support), q=roots.hits[0].p, ct=merc(c.center);
 const xy=distance(ct,q.slice(0,2)), z=Math.abs(c.elevation-q[2]), residual=Math.abs(c.elevation-height(ct[0]));
 return {valid:xy<=2**-29 && z<=.1298828125 && residual<=.1,xy,z,residual,roots};
}
