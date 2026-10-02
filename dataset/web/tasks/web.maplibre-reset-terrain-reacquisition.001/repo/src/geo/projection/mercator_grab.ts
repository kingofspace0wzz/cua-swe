import type Point from '@mapbox/point-geometry';
import {mat4, vec4} from 'gl-matrix';
import {MercatorCoordinate} from '../mercator_coordinate.ts';
import type {IReadonlyTransform, ITransform} from '../transform_interface.ts';
import type {TerrainQueries} from '../../render/terrain_queries.ts';

/** A world point with horizontal Mercator coordinates and a metre-valued height. */
export type MercatorGrab = {x: number; y: number; elevation: number};
export type MercatorRay = {origin: MercatorGrab; direction: MercatorGrab};

/** Unlike framebuffer picking, this ray reflects accepted input not yet rendered. */
export function mercatorCameraRay(tr: IReadonlyTransform, point: Point): MercatorRay {
    const inverse = mat4.invert(new Float64Array(16), tr.modelViewProjectionMatrix);
    const p: vec4 = [2 * point.x / tr.width - 1, 1 - 2 * point.y / tr.height, 0, 1];
    vec4.transformMat4(p, p, inverse);
    const camera = MercatorCoordinate.fromLngLat(tr.getCameraLngLat());
    const origin = {x: camera.x, y: camera.y, elevation: tr.getCameraAltitude()};
    return {origin, direction: {
        x: p[0] / p[3] / tr.worldSize - origin.x,
        y: p[1] / p[3] / tr.worldSize - origin.y,
        elevation: p[2] / p[3] - origin.elevation
    }};
}

export function intersectElevationPlane(ray: MercatorRay, elevation: number): MercatorGrab | null {
    const t = (elevation - ray.origin.elevation) / ray.direction.elevation;
    if (!(t > 0) || !Number.isFinite(t)) return null;
    return {x: ray.origin.x + ray.direction.x * t, y: ray.origin.y + ray.direction.y * t, elevation};
}

export function acquireMercatorGrab(tr: IReadonlyTransform, point: Point, terrain?: TerrainQueries): MercatorGrab | null {
    const ray = mercatorCameraRay(tr, point);
    // A skyward ray is not a usable navigation pivot, even if distant terrain exists.
    if (ray.direction.elevation >= 0) return null;
    const hit = terrain?.intersectRay?.(ray, tr);
    if (hit) return hit;
    const coordinate = terrain?.pointCoordinate(point);
    if (coordinate) return {x: coordinate.x, y: coordinate.y, elevation: coordinate.z};
    return intersectElevationPlane(ray, tr.elevation);
}

/** Retain both the acquired altitude and location, including when crossing center. */
export function placeMercatorGrab(tr: ITransform, grab: MercatorGrab, point: Point): void {
    // The metre-to-Mercator scale changes with center latitude. Solve that small
    // dependency rather than repeatedly picking a different point on the DEM.
    for (let i = 0; i < 8; i++) {
        const ray = mercatorCameraRay(tr, point);
        if (ray.direction.elevation >= 0) return;
        const underPoint = intersectElevationPlane(ray, grab.elevation);
        if (!underPoint) return;
        const dx = grab.x - underPoint.x, dy = grab.y - underPoint.y;
        if (Math.hypot(dx, dy) * tr.worldSize < 1e-7) return;
        const center = MercatorCoordinate.fromLngLat(tr.center);
        const next = new MercatorCoordinate(center.x + dx, center.y + dy);
        if (!Number.isFinite(next.x) || !Number.isFinite(next.y) || next.y < 0 || next.y > 1) return;
        tr.setCenter(next.toLngLat());
    }
}
