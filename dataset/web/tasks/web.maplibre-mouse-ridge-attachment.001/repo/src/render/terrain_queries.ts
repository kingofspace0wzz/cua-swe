import type Point from '@mapbox/point-geometry';
import type {LngLat} from '../geo/lng_lat.ts';
import type {MercatorCoordinate} from '../geo/mercator_coordinate.ts';
import type {IReadonlyTransform} from '../geo/transform_interface.ts';
import type {MercatorGrab, MercatorRay} from '../geo/projection/mercator_grab.ts';
import type {Terrain} from './terrain.ts';

/**
 * Navigation queries over terrain. This synthetic integration extension does not
 * replace the Terrain used for rendering, loading, or camera settling.
 */
export type TerrainQueries = {
    /**
     * Query the rendered terrain pixel at a CSS screen point relative to the map.
     * Returns null when there is no rendered terrain pixel (for example, sky).
     * x/y are Mercator world coordinates. This Terrain's z is elevation in METRES,
     * including exaggeration, unlike general MercatorCoordinate's conformal z.
     */
    pointCoordinate(p: Point): MercatorCoordinate | null;
    /** Elevation in metres including exaggeration, using the transform's tile coverage. */
    getElevationForLngLat(lnglat: LngLat, transform: IReadonlyTransform): number;
    /** Elevation in metres including exaggeration, at the requested tile zoom. */
    getElevationForLngLatZoom(lnglat: LngLat, zoom: number): number;
    /** Optional loaded-terrain ray query; grab and ray elevation components are metres. */
    intersectRay?(ray: MercatorRay, transform: IReadonlyTransform): MercatorGrab | null;
};

/** Called with the current live renderer Terrain whenever navigation acquires queries. */
export type TerrainQueryFactory = (terrain: Terrain) => TerrainQueries;
