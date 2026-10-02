# Terrain pinch-anchor replay

Open `/runtime-task/index.html` in a touch-capable Chromium viewport. The page
creates a pitched MapLibre map with a deterministic elevated terrain point,
starts a two-finger gesture around that point, and then moves the midpoint while
widening the fingers.

The protected behavioral oracle measures the screen-space distance between the
moving gesture midpoint and the projection of the geographic point grabbed at
gesture start.

- Broken baseline: the point slips by about 30.636 px.
- Gold historical repair: the point remains within 0.5 px (observed 0.040 px).
- Successful CUA repair: observed 0.0000014 px.
- Realistic code-only negative: builds but slips by about 58.227 px.

The verifier launches real Chromium with SwiftShader WebGL and fails unless the
slip is below 0.5 px. It does not inspect source shape.
