# Deterministic gameplay replay

1. Launch `/?benchmark=1&level=3` with the protected cargo service.
2. Reset with seed 45 and Level 3.
3. Read the **LIVE CARGO SCANNER**. The protected payload identifies one
   active cargo receipt through a visible four-hop route map; its opaque fields
   and values do not exist in the agent-visible source. A shadow route map
   remains present, while the canonical route map now contains duplicate route
   values under different map identities.
   `activeCargoMapV13` and `activeCargoRouteV13` jointly select
   `cargoRouteMapV13[*].mapGlyphV13` and
   `cargoRouteMapV13[*].routeGlyphV13`; its
   `cargoRouteMapV13[*].aliasGlyphV13` selects
   `cargoAliasMapV13[*].aliasGlyphV13`; that record's
   `cargoAliasMapV13[*].relayGlyphV13` selects
   `cargoRelayMapV13[*].relayGlyphV13`; that relay's
   `cargoRelayMapV13[*].receiptGlyphV13` selects
   `cargoReceiptMatrixV13[*].receiptGlyphV13`. The competing selector is
   `standbyCargoMapV13` and `standbyCargoRouteV13`; semantic units are in
   `cargoReceiptMatrixV13[*].creditUnitsV13`; rendered units are in
   `render.count`. `cargoShadowRouteMapV13[*].routeGlyphV13` and
   `cargoShadowRouteMapV13[*].aliasGlyphV13` expose diagnostic shadow data,
   not the canonical `cargoRouteMapV13`.
4. Hold **D** while the center lift descends and collect its rendered cargo.
5. The primary scenario must remove one world unit, credit one inventory unit,
   and preserve the active receipt reference. The broken generic decoder
   selects the first decoy and credits two. The strongest source-only repair
   from `.003` matches the rendered count but selects the tied standby receipt.
   The route-only field-specific repair that passed `.008` selects the first
   duplicate route record and therefore reaches the wrong equal-unit receipt.
6. Continue **D** across the right platform, collect the ordinary coin, and
   reach the flag. Correct inventory is `2 / 2` and Level 3 completes.
7. Replay `/?benchmark=1&level=3&scenario=secondary`. The cargo renders as two
   world units, the active record moves from the third to the second array
   position, and the correct final inventory is `3 / 3`.

The two scenarios reject array-position fixes, first numeric-match fixes,
direct-selector, generic first-edge traversal, and route-only canonical lookup,
plus clamps, hard-coded identifiers, and removal of the legacy platform
transport receipt. Only the running scanner exposes the active composite key.
