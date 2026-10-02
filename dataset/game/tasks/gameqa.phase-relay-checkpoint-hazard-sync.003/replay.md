# Deterministic Signal Weave replay

Use `window.gameAPI.reset({seed: 2903, level: 1})`, then play only with
ordinary keyboard controls.

0. Open only the declared application URL. The canvas must immediately show a
   bounded `PREPARING TRANSIT` frame or the playable course. Browser requests
   must remain on the declared application origin. Repeated observation must
   reach `window.gameBoot.status == "ready"`, a nonblank canvas, and an
   actionable `window.gameAPI` state after the app-origin
   `/runtime/ticket` and `/runtime/route-card.png` requests complete.
1. Move right through the lower-left prism. Continue into the midpoint
   shelter. It must light while `game_state.checkpoint.active` is true and
   `game_state.safe_zone.occupied` is true.
2. Inspect the visible route card and the persistent three-dot handoff trail.
   At this pre-trigger point, `game_state.triad.field.assignment`,
   `game_state.triad.field.route`, `game_state.triad.field.trail`,
   `game_state.triad.panel.assignment`, `game_state.triad.panel.route`, and
   `game_state.triad.panel.trail` form complete, bijective records. Both
   `game_state.triad.field_open` and `game_state.triad.panel_open` mark the
   same lane.
   Record `metrics.tokens == 1`, `game_state.triad.return_armed == false`,
   and the current `game_state.triad.field.pulses` value.
3. Stage left of the gate, follow the pulsing OPEN lane, and cross. This
   pre-trigger crossing must preserve `metrics.deaths == 0`.
4. Move to the top-right prism and collect it. Enter any visibly closed lane
   and move back into the gate until `metrics.deaths == 1`.
5. Release ArrowLeft, ArrowRight, ArrowUp, ArrowDown, W, A, S, and D. Wait
   until `game_state.checkpoint.returns == 1`, the player is actionable, and
   `game_state.safe_zone.occupied` is true. The first prism persists, the
   second rolls back, and `metrics.remaining_tokens == 1`.
6. Remain inside the shelter for at least one second. In the repaired build,
   `game_state.triad.field.clock`, `game_state.triad.panel.clock`,
   `game_state.triad.field.trail`, and `game_state.triad.panel.trail` stay
   held. All complete snapshot fields—clock, pulses, active flag, generation,
   assignment, route, trail, and capsule records—match the checkpoint except
   for the intentional held active flag. Compare them directly with
   `game_state.checkpoint.saved.field` and
   `game_state.checkpoint.saved.panel`.
7. Move right until `game_state.triad.return_committed` is true. Record the
   departure state, then wait for two increments of
   `game_state.triad.panel.pulses`. The colored trail visible in the screenshot
   must continue the route card without repeating, skipping, or reversing.
   At each pulse, compare `game_state.triad.field_open` with
   `game_state.triad.panel_open`.
8. Follow the second pulsing OPEN lane through the gate. The baseline is hit
   and advances `metrics.deaths` from one to two. The gold repair and
   `negative.patch` stay at one death and reach the far side, but the negative
   has already failed because its visible ownership trail is reversed.
9. Recollect the top-right prism, reach the exit, and assert
   `terminal.isTerminal == true` and `terminal.outcome == "success"`.
10. Press R. An ordinary restart must clear the checkpoint, return
    transaction, both prisms, deaths, and terminal state. The neutral
    `game_state.triad.field` and `game_state.triad.panel` records agree again.

The evaluator-owned route card is the only authority for whether its anonymous
relation is read as owner-to-destination or destination-from-owner. Source
inspection can enumerate identity and the two cyclic alternatives, and all
three records are complete. It cannot rank those alternatives without seeing
the card and the two post-return pulses.

The strongest source-only negative is the exact recurring revision 002 repair:
pause both restored consumers and invert the panel route selected by the
ticket checksum. It fixes shelter hold and keeps the physical and marked
openings aligned, but selects the wrong ownership orientation. Its visible
trail becomes `u → w → v` instead of continuing the route card as
`u → v → w`. It can physically finish, yet fails the decisive ownership
continuity assertion.

All timing checks are bounded by shelter occupancy, pulse counters, and
transition edges. No assertion depends on an absolute animation frame.
