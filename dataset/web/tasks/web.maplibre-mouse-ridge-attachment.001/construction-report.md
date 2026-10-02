# Static construction report

**Decision:** written_awaiting_native_slot  
**Task / candidate:** web.maplibre-mouse-ridge-attachment.001  
**Independent final reviewer:** Anscombe

## Custody and scope

Read the pinned source review, assembly, scope, and next-source hypothesis.
Main accepted one static source author; this is not a measured failure claim.
The coordinator supplied exact Map revision03 plus its **complete** query-fallback
gold. The Legacy point-coordinate fallback is already present. It was neither
removed nor made artificially faulty. Prior successful query-fallback evidence
remains successful evidence for its original scope; it is not a mouse result.

The 788-file assembled baseline was compared by SHA-256. 787 original files are
byte-identical; only authorized `runtime-task/help.html` differs. One protected
checker is added, making 789 delivered source files. All assembled production
hashes match, including the mouse/touch handlers, camera/projection, helper,
terrain renderer, DEM/geography, scene/input fixture, package/lock/build sources,
API documentation, license and attribution. No reference was applied to delivered
`repo/`. The original query checker hash is unchanged. See `static-checks.json`.

`task.yaml` retains the supplied short outcome instruction, runtime/setup/build,
allowed tools, 1000×800 viewport, general solver access and budgets (2400 seconds,
180 steps, 220 GUI actions, 24 tests). The only additional verifier command is the
new mouse checker. V2 is unchanged. No dependencies, emitted builds, profiles,
caches or model rollouts were added. The preexisting `build/` contains immutable
build source, not an author-generated build.

## Source-only support

The manager's existing touch path acquires a world grab from the accepted view,
retains it, and places it at a moving contact. Its mouse path is separate:
mouse input supplies `around` and `panDelta`, while the manager computes a
pre-zoom location without a terrain argument. After terrain movement begins,
continuing panning takes a center-based path. Neither retains the pressed
geographic ridge's height/location across the held mouse gesture. This supports
investigating cursor attachment, but does not prove the baseline fails at any
particular painted endpoint. The source hypothesis is not converted into a
native FAIL by this report.

## Public behavior and checker

Help now explains fresh held grabs, accepted paused release, the existing touch
sequence followed by mouse without Reset, a direction change, reacquisition, and
completed unheld wheel zoom followed by a fresh grab. It distinguishes geographic
dots/grid from contact rings, states that no concurrent click/wheel/key input is
needed, and keeps existing touch demonstrations, Native/Legacy comparison, flat
navigation and all existing API/documentation links. It contains no repair recipe.

The new checker reuses the retained native Puppeteer launch conventions,
connected-component real-paint observer, public control locators and isolated
observation-only contact-overlay handling. It imports no historical geometry or
private oracle. Only actual rendered centroids supply press coordinates. Only
prescribed real pointer endpoints supply expected held anchor positions.
Read-only trusted DOM input observation distinguishes driving failures from
semantic failures; it reads no application camera/debug state.

Each integration has one coherent sequence: fresh mouse endpoints/release;
existing touch Move-and-zoom/Release; mouse direction change/release; fresh
reacquisition/release; completed ordinary wheel; fresh mouse endpoints/release.
The first mouse net displacement is small and positive in x so the subsequent
existing touch demonstration retains room. Later presses always reobserve paint.
The original verifier remains a separate required public command, preserving all
its original repeated touch/flat assertions without reduction.

Full-page, contact and geographic crops are retained for **every** sampled frame.
The new JSON includes actions, trusted input endpoints, reached assertions,
actual/expected pixels, errors, stability references and completed workflow
milestones. Paint stabilization requires at least three samples and a continuous
650ms stable interval (1000ms after wheel), bounded by an observation deadline;
it is not a fixed sleep used as success evidence. No staged wait input is used.
This pause is deliberately longer than a flick, not a narrow timing requirement.
RGB grid tests are limited to the public geographic grid, not a new universal
visual evaluator. Companion travel and changed grid paint reject an isolated
moving indicator. Release checks compare both dots and raster grid alignment
within the same 3px allowance. Integration comparisons allow 4px.

Unavailable/unloaded/clipped/ambiguous landmarks, unavailable controls, unsettled
paint or unconfirmed input are INCONCLUSIVE. Reached independent semantic failure
can be decisive before any later state; later states are not invented as passes
or failures. Errors and last screenshots remain in the report. Pixel allowances,
grid thresholds and scene reachability remain prospective until healthy native
reference validation. They are not source-token, Help-text or algorithm tests.

## External reference and partial controls

All five patches are standalone diffs from the same assembled baseline and touch
only `src/ui/handler_manager.ts`. Each was applied and reversed in the owned
external temporary source copy and syntax-parsed, never in delivered source.
The completed query helper remains byte-identical under every patch.

| Control | Source strategy | Predicted public outcome — **not run** |
|---|---|---|
| No-op baseline | Existing mouse path unchanged | Likely misses held ridge attachment, possibly at the first endpoint; prior touch/query/flat behavior expected retained. A baseline PASS must be retained. |
| `gold.patch` | Acquire once on accepted mouse press, commit ordered mouse input, place retained grab during held moves, clear on termination/stop; reuse existing terrain settlement | Intended to pass all mouse states and preserve old controls. |
| `alternate.patch` | Independently integrate lazy acquisition at the first accepted mouse delta, reconstruct the pressed screen point from that delta, retain grab across render batches, clear at next start/termination/stop | Intended complete alternative on the disclosed sequential workflows, including release/reacquisition. Not merely a query alias repair. |
| `negative.patch` | Terrain acquisition and lifetime are added, but placement converts the grab to longitude/latitude and still uses planar location placement | Likely fails held geographic attachment because the picked height is not retained in placement. Touch/query/flat untouched. |
| `negative-cases/plane-grab.patch` | Full mouse lifetime and placement but acquisition uses only the transform's plane, omitting terrain queries | Likely still fails ridge attachment, even with seemingly smooth dragging; touch/query/flat untouched. |
| `negative-cases/first-delta-only.patch` | Lazy retained acquisition/placement is used only for the first combined mouse delta, then existing mouse continuation remains | May pass an initial single combined move, then fail continuing/direction-changing held motion; exact first observed failure depends on frame grouping. Not claimed to reach all later states. |

Partials are incomplete source repairs, not injected delivered regressions or
synthetic fixture modes. No special world points, provider aliases, success flags
or scripted input were encoded in any repair. No existing working helper/call is
deleted to manufacture a negative. Source helpers and short correct solutions are
legal; there is no solution-shape or helper-name grading.

## Static validation and limits

`static-checks.json` records exact syntax/applicability commands and hashes:
- Node syntax checks of both checker modules, without executing their imports;
- independent `git apply --check` from delivered repo for all five patches;
- actual application/reversal only in the owned external baseline copy;
- Node TypeScript-strip syntax checks of every applied manager (not a typecheck);
- full baseline file-hash comparison and complete query-helper preservation;
- YAML data assertions for runtime, tools, viewport, verifier retention and budgets;
- static import/dependency audit: Node builtins plus already-declared
  Puppeteer/pngjs via the original workspace resolver, no outside relative import.

There was one timed-out static copy/preparation shell (10s). Its static work was
completed with a longer timeout. This was not a model/author/browser/native retry;
no behavior or test result was produced by it.

**Counts:** native 0; browser 0; build 0; solver 0; dependency installation 0;
server startup 0; network requests 0; subagents/additional model calls 0.

## Unresolved feasibility and source-shortcut risk

Native reference/baseline/partial separation, 3px mouse tolerance calibration,
accepted-view retention after terrain settlement, reachable loaded paint after
wheel, complete old touch/flat preservation under both references, and verifier
execution time/stability are all unresolved. Syntax checks are not compilation
or runtime validation. Input observation binding and narrow grid-paint thresholds
also require real Chromium validation; an INCONCLUSIVE must not be relabeled as
product failure. See `replay.md` for the finite later handoff, not an executed run.

The visible acquire/place helper and separate mouse/touch branches make a short
source-only repair plausible. The two useful GUI observations are fresh held
attachment and attachment after the accepted touch/wheel camera change. A solver
might need neither to find the code change. No measured difficulty, hardness or
mandatory long repair is claimed. The supplied difficulty metadata is retained,
not newly validated. Do not add bans or artificial failures to defend it.

All authored deliverables are complete for a **static** handoff. The missing work
is later native feasibility/control validation and Anscombe's independent final
review, before any solver. Park if the immutable baseline already meets the
contract or a healthy reference cannot be established. No automatic retry is
promised.
