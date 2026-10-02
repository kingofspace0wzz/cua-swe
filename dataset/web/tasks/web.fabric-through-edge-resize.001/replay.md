# Bounded native replay contract (not executed by this author)

Use the existing verifier command from `task.yaml`; no runtime/setup changes.
The checker retains the protected service, feed capture, real Playwright mouse
input, Pillow screenshot observations, raw evidence and exit semantics. Apply
**one** patch at a time to a clean `repo/` baseline. The five controls are baseline,
`gold.patch`, `alternatives/alternative.patch`, `negative.patch`, and
`negative-cases/unreflected-snapshot.patch`. There are exactly two partials.

## Public geometry

Coordinates in this table use Blue's **initial** axes: u is 15° in the inner
parent and v is perpendicular. They are an oracle convention, not object state.
The initial four corners are (-30,-18), (30,-18), (30,18), (-30,18).

| Ordinary gesture | Fixed geometry | Moving geometry | Observed nondegenerate states |
|---|---|---|---|
| Nested B actual Blue selection, visible side off-center | midpoint (-30,0) | midpoint (30-96t,0) | t=1/6: 44×36; t=1: 36×36, center (-48,0); release |
| New visible corner at (-66,18), independently resize both dimensions | corner (-30,-18) | corner (-66-12t,18-66t) | t=1/6: 38×25; t=1: 48×30, center (-54,-33); release |
| Actual visible fill drag | entire resulting polygon | inner-parent translation (3t,2t) | t=1/2,1; release |
| Independent Single C preservation | existing feed geometry | right side -20, rotation +10°, fill (2,-2) | each endpoint and release |

For the side, expected polygon vertices are (-30,-18), (30-96t,-18),
(30-96t,18), (-30,18). For the corner they are (-30,-18),
(-66-12t,-18), (-66-12t,18-66t), (-30,18-66t). The driver forward-projects
these endpoints; it never reconstructs a candidate's resize transaction.

Six ordinary pointer moves traverse each gesture. Collapse lies between scheduled
moves, not at a scored checkpoint; there is no exact-zero stop or degenerate
interior/unique-marker requirement. Snapshots at acquisition and release establish
continuity. After a decisive divergence or unsupported acquisition, later dependent
input stops. Cleanup release images remain raw and **unscored**. The independent
Single segment may still run. Missing later states are not extra failures.

## Observation and equivalence

Acquire Blue from an actual visible fill patch. Associate unordered visible
handle blobs with expected geometric corners/midpoints. The next corner is
identified by its visible location, not a native key or a presumed signed axis.
Prefer the requested small off-center red-core-supported position; discover a
supported alternative in the marker if necessary. Hollow/alternative markers may
use a visible ring position. If unsupported, report coverage, not product failure.

Paint, silhouette, distributed interior, red outline/control alignment, Amber,
both frames, visible selection and numeric camera readouts are independently
checked. Inward edge samples point toward the polygon center even after winding
reverses. Rotation is acquired from an actual exterior marker: no fixed 40px
stem, native key, internal reflection flag, angle/scale normalization or preferred
stem side. Equivalent geometric representations of solid Blue must pass.

## Evidence and result

Raw screenshots, overlays, actions, expected polygons, failed assertions, coverage
and runtime records remain in the verifier artifact directory (writable `/tmp`
fallback). Exit 0 is complete covered success, 1 is reached public behavior failure,
and 2 requires causal setup/runtime/observation review. Complete-alternative
`passed` / `raw_success` must remain distinct from legacy `control_passed`.
No checker, browser, app, build or native library was executed for this draft.
