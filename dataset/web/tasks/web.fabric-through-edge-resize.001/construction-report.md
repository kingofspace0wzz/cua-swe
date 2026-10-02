# Through-edge resizing: static construction report

## Custody and scope

The baseline is the exact passing nested GPT6 application
`40671789d37209d5e546e7681f86b530a2a19a4c9c9907028944bdc06751a76b`,
from parent input
`7a2f7bccc47f41bb85ad558ad823dedbf6b39cbf6eb9f1aa77400b16aa4f4fa5`.
The full camera/parent inverse and rendered affine controls already work. The
app, native Group fixture, vendor, feed and runtime implementation bytes stay
frozen. There is no source regression, helper insertion, new renderer or object.

The new Help replaces the old positive-only prohibition. The old task did **not**
require crossing; its contract/results remain historical. All useful fixture,
rotation, selection, camera and Single notes remain. `task.yaml` is unchanged,
including instruction and original 1800/80/120/20 budgets, setup/environment,
allowed tools, artifacts and verifier command. Runtime changes are narrative only.

## Complete patch-only references

**Gold:** capture the reflected starting axes with the existing inverse and grab
snapshot. Allow signed spans; compute placement with signed anchor-to-center
vectors. Commit scale magnitudes and absolute native flip state. This avoids
Fabric's negative-scale per-write flip toggling, including repeated release input.
Capture reflected axes afresh for the next visible handle. Retain the renderer,
native body path, local rotation and transaction lifecycle.

**Distinct alternative:** capture full native material edge vectors, fixed and
moving endpoints and pointer offset. Resolve the new endpoint vector in the
snapshot's dual basis; build a parent-local affine matrix and use native
`applyTransformToObject`. That helper resets reflection and decomposes the matrix;
new gestures capture the resulting basis, not an angle-only assumption. An exact
zero column uses a subpixel limiting value to keep QR finite. No exact-zero render
or unique handle is graded. This is an endpoint/affine construction, not a renamed
signed-span implementation. Neither reference modifies the frozen baseline.

## Exactly two meaningful partials

| Control | Omission | Predicted reached public failure |
|---|---|---|
| Baseline (not a partial patch) | Positive clamp | Final side width1 at center(-29.5,0), instead of width36 at(-48,0); center error47.931px |
| `negative.patch` | Signed anchor-to-center placement; uses magnitudes | Final side expands on wrong side: center(-12,0), 93.271px from expected, despite physical36×36 |
| `negative-cases/unreflected-snapshot.patch` | Reflected starting axes for the next gesture | First crossing/release succeeds analytically; next corner at t=1/6 has34×25 rather than38×25 and corners displaced5.182px |

These are source-derived scalar predictions, not measured native outcomes. The
second partial's center happens to agree: its visible size and fixed/moving corner
errors, not invisible parity or stem placement, are the negative evidence.

## Independent oracle delta

The driver now prescribes explicit fixed/moving endpoint polygons, including
winding reversal; the observer chooses inward edge normals from polygon center.
No positive-size planner guard or mandatory collapse samples remain. The Nested B
sequence is one off-center side crossing, ordinary release, actual visible corner
reacquisition and independent second-axis crossing, release, then rigid fill
movement. One compact Single C non-crossing/rotation/fill segment preserves old
behavior. See `replay.md` for the public geometry and observation schedule.

The initial-axis-to-canvas B projection from independent scalar arithmetic is
approximately `[.636208701, 2.511541345, -1.968233781, 1.283697443,
304.644660941, 301.040764009]`. Side-end area is7464.96px² with altitudes
88.244/80.035px; corner one-sixth area5472px² with altitudes93.146/55.580px;
corner-end area8294.4px² with altitudes117.658/66.696px. The final corner
vertices are approximately (320.987,202.588), (290.449,82.034),
(349.496,43.523), (380.034,164.077), relative to the canvas origin. This
is arithmetic, **not** measured native feasibility or a pixel coverage guarantee.

Native service/feed/startup/input support stays intact. Acquisitions use actual
fill and visible marker support. Marker numbers index public polygon locations,
not Fabric keys. No preferred private flags, normalization or rotation-stem side
is required. Unknown observation is coverage. Canvas-bounded red/blue/white
sampling and semantic zoom/closed-details/display:contents fixes remain intact.
Raw evidence and 0/1/2 status meanings remain; cleanup images after a stopped
preview are unscored and missing continuations do not multiply failures.

## Static validation and limits

All 55 recorded static checks passed: four independent `git apply --check`
operations and temporary applications, JavaScript syntax-only parsing, Python AST
and YAML parsing, frozen-source/task/runtime custody and bundle hygiene checks.
Validation records are in `../author-01/rollout/static-checks.json` and independent
scalar arithmetic in `../author-01/rollout/scalar-geometry.json`. Temporary patched
copies, syntax extracts and author scripts are outside the final bundle. Each of
the four patches is checked independently against the final frozen baseline,
not stacked. JavaScript syntax is parsed without importing/initializing the app
or Fabric; Python is AST-parsed without importing/running the checker. YAML is
parsed and protected source/runtime/task custody compared.

Native risks remain unresolved: ordinary pointer compatibility/capture and grouped
cache propagation through near collapse; native QR/scale limiting at a singular
instant; actual bitmap/marker/layer coverage for both complete references. No
native/browser/checker/build/test/install/network/solver execution occurred. This
is a new synthetic feature hypothesis, not an upstream bug claim, measured
hardness, native feasibility result or model separation claim. Main is the
independent final reviewer; this author launches no downstream work.
