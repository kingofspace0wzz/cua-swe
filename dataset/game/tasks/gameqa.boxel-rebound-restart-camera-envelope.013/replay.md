# Level 50 explicit saved-spawn camera recipe replay

1. Launch `/?level=50` at 1280×720. Do not call `gameAPI.reset()` and do
   not select a menu entry. Native Level 50 gameplay must already be active,
   `window.Game.view` must be `2`, the selected level must be `50`, and the
   ordinary checkpoint card must be fully legible below the native controls.
2. Independently verify the generic route contract. Every other available
   Level 1 through 49 must enter native gameplay without the card. An absent
   query and malformed, fractional, zero, negative, or unavailable level
   values must retain the ordinary selector without the card. Startup source
   may read only the generic `level` key and may contain no task-ID,
   benchmark, or evaluator activation branch.
3. Verify `repo/img/panel_17.png` is a 320×152 RGBA PNG with SHA-256
   `efc5ee01b2ffb7f7d90f323cec83152af7d6e1e1444d4f2fd67f6b42fc1de202`.
   Its player-facing copy must remain binary-only; agent-visible plaintext
   contains only neutral asset identifiers and placement code.
4. Let the Level 50 cube settle on the striped moving lift and establish the
   ordinary checkpoint. The saved guide object must contain exactly `id`,
   `tiles`, `x`, and `y`; it must contain no timestamp, motion clock, phase
   value, cycle fraction, camera state, or equivalent reusable token. Before
   restart, the evaluator copies the guide geometry/top, support identity/top,
   rider offset, checkpoint course coordinate, and observed motion frame into
   immutable evaluator-owned closure state.
5. Allow a short bounded interval of ordinary lift motion, then press **R**.
   Do not hold jump across the restart.
6. At the synchronous restart boundary, inspect the brief faded checkpoint
   echo. The card must still be attached at the same stable geometry. The echo
   must remain at the geometry captured when the checkpoint was established.
   Later calls to capture a guide and later writes to application checkpoint
   fields are tested outputs; they do not replace the evaluator's saved
   expected relationship.
7. Confirm the live striped lift returns to that saved geometry, the cube is
   riding it at the saved offset, and the resumed course view is continuous
   with the checkpoint course position.
8. Continue riding the lift. Near its exit, press **Space** once and finish the
   level through the native completion flow.

The `.008` successor changes only the Level 50 tutorial-card bitmap. Its
ordinary in-game recipe preserves the successful `.007` guidance: saved
evidence remains immutable, lift phase is recovered from the nearest earlier
matching Y silhouette, and the live lift is never recaptured as checkpoint
truth. It replaces only the ambiguous camera row with an explicit contrast:
camera restoration uses the player's saved spawn/course X, not the level map's
smoothed camera progress. Level 50 physics, moving-lift geometry and motion,
trigger timing, controls, generic deep-link behavior, broken restart behavior,
immutable evaluator evidence, tolerances, instruction, gold semantics, and
ordinary completion remain unchanged from sealed `.007`.

The exact `.005` CUA patch is the default and named strongest negative. It
correctly couples lift, rider, and camera restoration but adds `motionTime` and
`cameraProgress` to the intentionally geometry-only guide, so it must fail
before the restart replay proceeds. The exact `.005` code-only patch remains a
named negative and must fail because it substitutes or discards the immutable
saved frame. The exact `.004`, exact `.003`, rebased `.002`, and `.001`
current-phase patches remain named negatives and must fail for their original
causal reasons.

The exact protected `.006` code-only patch is retained byte-for-byte as
`negatives/predecessor-006-code-only-exact.patch` with SHA-256
`c3fe60fe2bc2dc6b32a5311f9b88cb25a6e0538c7d57bab5755d41f0af4fd357`.
It must fail because it calls `captureGuide` on the live moving lift during
restart, rewrites application checkpoint fields, and substitutes the live
frame for the immutable evaluator-owned saved relationship. The protected
`.006` CUA attempt produced an empty patch; no-op already represents it, so it
is recorded in provenance and custody instead of duplicated as a negative.

The exact protected `.007` code-only patch is retained byte-for-byte as
`negatives/predecessor-007-code-only-exact.patch` with SHA-256
`c2f31d0e708d3113e4a6d7b56835ba0594643bad4ad20faac45c17a529ace7b5`.
It must fail because it calls `captureGuide` on the live moving lift during
restart, rewrites application checkpoint fields, and substitutes the live
frame for the immutable evaluator-owned saved relationship.

The exact protected `.007` CUA patch is retained byte-for-byte as
`negatives/predecessor-007-cua-exact.patch` with SHA-256
`b48dda889008f0d13c43d94b64647a0fe66ad07fe7f028fc99d5f14c3027317a`.
It correctly keeps the saved echo immutable and rewinds lift motion to a
nearest earlier height match, but it introduces and saves the level map's
smoothed `cameraProgress` value instead of restoring camera progress from the
player's immutable saved spawn/course X. It must fail the unchanged
camera/course-frame assertion.

The unchanged gold repair uses ordinary moving-support geometry and periodic
lifecycle to recover the nearest prior frame matching the saved silhouette,
updates the live support, then rebases the rider and course view. No hidden
numeric answer, query flag, benchmark-only activation branch, or evaluator
data channel is added.

Expected outcomes:

- no-op/broken baseline: card checks pass, then restart continuity fails;
- gold patch: initial card, restart card, saved-frame recovery, and native completion pass;
- default exact `.005` CUA negative: fail because the guide gains forbidden fields;
- named exact `.005` CUA negative: fail for the same forbidden guide fields;
- named exact `.005` code-only negative: fail immutable saved-frame continuity;
- named exact `.004` code-only negative: fail because the guide gains forbidden fields;
- named exact `.003` code-only negative: fail saved-evidence recapture/live-frame substitution;
- named rebased `.002` code-only negative: fail missing-clock saved-versus-live continuity;
- named `.001` current-phase CUA negative: fail the immutable saved-frame comparison.
- named exact `.006` code-only negative: fail live-lift recapture and immutable saved-evidence rewriting.
- named exact `.007` code-only negative: fail live-lift recapture and immutable saved-evidence rewriting.
- named exact `.007` CUA negative: fail because camera progress is restored from a newly saved smoothed map value instead of the player's immutable saved spawn/course X.

Protected state paths used by the deterministic replay:

- `game_state.player.props.support_id`
- `game_state.player.props.checkpoint_support_id`
- `game_state.player.jump_ready`
- `game_state.player.y`
- `game_state.environment.motion_time_ms`
- `game_state.environment.camera_progress`
- `game_state.environment.camera_offset_x`
- `game_state.environment.moving_supports[0].top`
- `debug.native_restart_count`
- `terminal.outcome`
