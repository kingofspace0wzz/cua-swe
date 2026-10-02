# Replay - v3.fabric-viewport-rotation-controls.001

## Product surface

The task is an Artboard Editor backed by the real pinned Fabric browser build
from `fabricjs/fabric.js@fd50b70`. The editor receives a camera preset from the
evaluator-owned scene feed, applies its viewport transform, selects one object,
and renders Fabric's selection frame and corner controls.

## Clean install and launch

```bash
cd repo
npm install
node build.mjs
CUA_SWE_EXTERNAL_SERVICE_ORIGIN=http://127.0.0.1:<service_port> \
  node server.mjs --host 127.0.0.1 --port 4173
node ../env/service.mjs --host 127.0.0.1 --port <service_port>
```

Open `http://127.0.0.1:4173/?preset=A`. Presets A, B, and D rotate the viewport;
preset C is the flat compatibility case.

## Broken behavior

- A and B report the wrong zoom and selection dimensions.
- The corner controls do not follow the displayed object corners.
- The selection frame remains upright while the object is visibly rotated.
- D produces non-finite control coordinates, so the handles disappear.
- C remains correct.

## Correct behavior

The zoom magnitude, X/Y dimensions, corner-control coordinates, and selection
frame rotation all follow the live viewport transform. The complete repair
matches Fabric PR 10977: derive both scale magnitudes from the transform, use
them for dimensions and inverse control scaling, and combine viewport rotation
with the ungrouped object's control-frame rotation.

## Verification

```bash
cd repo
python3 verifiers/browser_check.py
```

The verifier derives expected geometry from each live scene-feed transform and
checks four profiles:

| profile | camera | broken | negative | source analogue | gold |
| --- | --- | --- | --- | --- | --- |
| A | 45-degree rotation, uniform scale | fail | fail | fail | pass |
| B | 45-degree rotation, anisotropic scale | fail | fail | fail | pass |
| C | flat scale and pan | pass | pass | pass | pass |
| D | 90-degree rotation | fail | fail | fail | pass |

`negative.patch` fixes zoom and dimensions only. The strongest source-only
analogue also repairs `calcOCoords`, but leaves the selection frame upright.
Only the complete gold passes all profiles.

## Construction gates

```bash
bash _gates/run_gates.sh
```

Expected result: `10 pass / 0 fail`.
