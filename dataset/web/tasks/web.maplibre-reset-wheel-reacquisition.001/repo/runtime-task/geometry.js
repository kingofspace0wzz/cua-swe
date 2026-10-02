// Public geometric description of M. No candidate picking or matrices are used.
export const radius = 6371008.8;
export const rad = Math.PI / 180;
export const merc = ([lng, lat]) => [(lng + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + lat * rad / 2)) / Math.PI) / 2];
export const lnglat = ([x, y]) => [x * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) / rad];
export const metres = lat => 1 / (2 * Math.PI * radius * Math.cos(lat * rad));
export const terrainHeight = x => 1400 - 1000 * Math.max(0, Math.min(1, (x - 0.520782470703125) / (0.5207977294921875 - 0.520782470703125)));
export function basis(c) {
    const p = c.pitch * rad, b = c.bearing * rad, f = c.height / (2 * Math.tan(c.fov * rad / 2)), w = 512 * 2 ** c.zoom, m = metres(c.center[1]);
    const cp = [(c.width + c.padding.left - c.padding.right) / 2, (c.height + c.padding.top - c.padding.bottom) / 2];
    const right = [Math.cos(b), Math.sin(b), 0], down = [-Math.sin(b) * Math.cos(p), Math.cos(b) * Math.cos(p), -Math.sin(p)], back = [-Math.sin(b) * Math.sin(p), Math.cos(b) * Math.sin(p), Math.cos(p)];
    const ct = merc(c.center), pos = [ct[0] + back[0] * f / w, ct[1] + back[1] * f / w, c.elevation + back[2] * f / w / m];
    return { f, w, m, cp, right, down, back, pos };
}
export function ray(c, s) {
    const k = basis(c), x = (s[0] - k.cp[0]) / k.f, y = (s[1] - k.cp[1]) / k.f;
    return { origin: k.pos, dir: [0, 1, 2].map(i => (k.right[i] * x + k.down[i] * y - k.back[i]) / (i === 2 ? k.m : 1)) };
}
export function project(c, P) {
    const k = basis(c), v = [(P[0] - k.pos[0]) * k.w, (P[1] - k.pos[1]) * k.w, (P[2] - k.pos[2]) * k.w * k.m];
    const dot = a => a.reduce((s, x, i) => s + x * v[i], 0), depth = -dot(k.back);
    return [k.cp[0] + k.f * dot(k.right) / depth, k.cp[1] + k.f * dot(k.down) / depth];
}
export function acquire(c, s, height = terrainHeight) {
    const { origin: o, dir: d } = ray(c, s);
    if (d[2] >= 0)
        return null;
    if (typeof height === 'number') {
        const t = (height - o[2]) / d[2];
        return [o[0] + t * d[0], o[1] + t * d[1], height];
    }
    // M is continuous piecewise planar; solve each plane and retain nearest valid hit.
    let best = null;
    for (const [lo, hi, z, slope] of [[-Infinity, 0.520782470703125, 1400, 0], [0.520782470703125, 0.5207977294921875, 1400, -65536000], [0.5207977294921875, Infinity, 400, 0]]) {
        const intercept = slope ? z - slope * lo : z, t = (intercept + slope * o[0] - o[2]) / (d[2] - slope * d[0]), x = o[0] + t * d[0];
        if (t >= 0 && x >= lo - 1e-12 && x <= hi + 1e-12 && (!best || t < best.t))
            best = { t, p: [x, o[1] + t * d[1], o[2] + t * d[2]] };
    }
    return best?.p;
}
