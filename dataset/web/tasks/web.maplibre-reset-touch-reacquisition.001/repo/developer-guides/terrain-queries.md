# Navigation terrain queries

This checkout includes an **explicit synthetic integration extension**, not a
previously published upstream plugin API. `TerrainQueries` and
`TerrainQueryFactory` are exported types. A map's renderer, terrain loading,
CPU ray query, elevation handling and camera settling still use its real Terrain.

`map.setTerrainQueryFactory(factory)` selects the navigation query integration and
returns the map. `null` restores the default. `map.getTerrainQueries()` returns
`undefined` without terrain; otherwise it returns the factory result, or the live
Terrain itself by default. The factory receives that same current live Terrain
each time queries are acquired. It must not cache an old Terrain across resets.
It does not own or replace the renderer.

## Query contracts and units

- `pointCoordinate(p: Point): MercatorCoordinate | null`: `p` is a CSS screen
  coordinate relative to the map. This reads the rendered terrain coordinate
  pixel. **Null** means no rendered terrain pixel, including sky. Its x/y are
  Mercator world coordinates. **This Terrain's returned z is elevation in METRES,
  including terrain exaggeration.** A general `MercatorCoordinate` normally uses
  **conformal Mercator z**, not metres. The class's usual altitude conversion
  methods have that general convention. Terrain pixel picking has the above
  historical mixed-unit convention. Picking has screen/pixel and tile-coordinate
  quantization and describes rendered coverage.
- `getElevationForLngLat(lnglat: LngLat, transform: IReadonlyTransform): number`:
  elevation in **metres**, including exaggeration. Tile coverage of the given
  transform determines zoom; loaded ancestor DEM tiles may supply the sample.
- `getElevationForLngLatZoom(lnglat: LngLat, zoom: number): number`: elevation in
  **metres**, including exaggeration, at the requested tile zoom with existing
  ancestor-tile lookup. These elevation queries return zero when no usable sample
  is available; they do not promise that every geographic location has loaded data.
- Optional `intersectRay(ray: MercatorRay, transform: IReadonlyTransform):
  MercatorGrab | null`: loaded mesh ray query. Ray origin and direction use
  Mercator x/y and metre-valued elevation components. A grab has Mercator x/y
  and `elevation` in metres. Null denotes no usable positive loaded hit.

The required three queries alone are a supported integration. For example, the
public Legacy demonstration uses exactly these three bound delegates:

```ts
import type {TerrainQueryFactory} from 'maplibre-gl';
const legacyQueries: TerrainQueryFactory = terrain => ({
    pointCoordinate: terrain.pointCoordinate.bind(terrain),
    getElevationForLngLat: terrain.getElevationForLngLat.bind(terrain),
    getElevationForLngLatZoom: terrain.getElevationForLngLatZoom.bind(terrain)
});
map.setTerrainQueryFactory(legacyQueries);
```

Native mode calls `map.setTerrainQueryFactory(null)`. Both modes retain the same
live Terrain and use the same source, camera and rendered geographic features.
See [the public demonstration Help](../runtime-task/help.html) for controls.
