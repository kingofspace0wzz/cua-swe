# Proposed public replay — not executed

Task: `web.maplibre-mouse-ridge-attachment.001`.
This is a static handoff, not a native result or solver trajectory. No browser,
server, install, build, native check, solver, network request, or model retry ran.
Anscombe is the independent final reviewer.

## Later native slot

Use a separate materialization for each control. Apply each patch from its
materialized `repo/`; never apply a reference to this delivered baseline.
Keep the original npm setup/build/st launch and the 1000×800 viewport. The native
verifiers consume the evaluator's service via `CUA_SWE_WEB_URL`, resolve the
existing dependencies through `CUA_SWE_WORKSPACE`, and write to
`CUA_SWE_VERIFIER_ARTIFACTS`. They do not start a service. No new environment or
runtime-contract file is required.

Retain the original public command:

```
node verifiers/check_rendered_query_compatibility.mjs
```

It preserves both integrations' original repeated touch workflows, ordinary
terrain dragging, and the independent flat map's drag and zoom. It is unchanged.
Also run the new public command:

```
node verifiers/check_mouse_ridge_attachment.mjs
```

The new command writes `mouse-ridge/results.json` and all per-sample full-page,
contact and geographic screenshots under the supplied artifact directory. Its
stdout records the artifact location and exit classification (0 pass, 1 reached
semantic failure, 2 inconclusive). The subdirectory avoids overwriting the old
checker's results. Retain both commands' logs, exit codes and artifacts.

First establish healthy reference feasibility (`gold.patch`, then the independent
`alternate.patch`) and the unchanged no-op baseline before any solver. Preserve
all evidence, including an unexpected baseline PASS. Do not inject a failure or
weaken a healthy result. The three partials have source-based predictions only;
validate their separation in that later slot if references and baseline support
continuing. No automatic author/browser/native/solver retry is authorized by
this handoff. If references do not establish stable paint/attachment, or the
baseline satisfies this behavior, return to review/park rather than manufacturing
a negative. Pixel thresholds are prospective, not secretly calibrated.

## Sequential scene (each integration separately)

1. Select Native and Reset, then wait for the visible loaded scene. Find the
   **painted** magenta centroid, not its initial assumed coordinates. Start a left
   mouse grab there. Inspect a held endpoint about 32px right and 14px down; still
   held, change direction to an endpoint about 8px right and 6px up from the
   press. Both are relative to that observed press. Inspect the paused endpoint,
   release, and inspect the accepted view. No click/wheel/key/wait *action* during
   the staged drag. Read-only observations can take as long as necessary.
2. Without Reset, complete the existing Move and zoom, Move 1, Move 2, Move 3,
   Release demonstration. Every move should remain attached to the real magenta
   place, and the cyan place should separate progressively as in existing Help.
   Only after Release, locate the now-painted magenta dot and press it. Inspect
   endpoints roughly (-36,+18) and (+12,-10) relative to this new press; pause and
   release. Reacquire at the actual accepted dot and inspect (-28,+12), then
   (-12,0); pause and release again.
3. With no mouse button held, wheel zoom in over the current painted ridge dot
   (checker uses one ordinary -120 wheel delta). Let the visible zoom finish.
   Reobserve the dot, press it afresh, inspect (+28,+16), then (-16,-8) relative to
   that press, and pause before release. Wheel is never required during a drag.
4. Reset for Legacy and repeat the same sequential scene. Compare corresponding
   painted states across integrations, with the existing 4px allowance.

The numeric offsets describe the proposed verifier trace, not special world
coordinates or required user precision. Actual press positions come from pixels;
client positions are rounded and recorded. The endpoint chosen by the checker
is at least 24px inside the map. Missing/clipped/ambiguous landmarks, unavailable
controls, unsteady/unloaded paint, and unconfirmed trusted input are INCONCLUSIVE.
Do not count a missing later state as a product failure. A reached independent
attachment assertion can end the negative's sequence immediately.

## Evidence and interpretation

- The expected held anchor position is the prescribed real pointer endpoint.
  No application camera/projection/geometry/debug success value supplies it.
- The companion must travel in the commanded direction and grid paint must
  change, so moving only a contact illustration is not sufficient.
- Repeated stable observations of the dots and grid establish held/idle paint;
  release retention compares actual held and released photographs. Contact
  overlay screenshots are saved first; only their isolated presentation layer
  is hidden temporarily for a geographic photograph and restored exactly.
- New checker input records observe browser-delivered trusted events, endpoints,
  buttons and targets; they do not drive synthetic events. Touch input remains
  the existing public buttons. No touch rotation/pitch or concurrent inputs.
- The original query check's separate historical readiness guard is retained
  unchanged; the new checker does not import or duplicate its projection math.
