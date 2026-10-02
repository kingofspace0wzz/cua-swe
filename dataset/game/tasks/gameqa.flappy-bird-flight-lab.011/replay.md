# Protected deterministic replay

This evaluator-owned replay is not staged into the agent workspace.

Decisive protected paths are `game_state.player.bounds`,
`game_state.environment.flight_lab.trail`,
`game_state.environment.flight_lab.target`,
`game_state.environment.flight_lab.visual_audit`,
`game_state.environment.flight_lab.input_receipt`,
`game_state.environment.flight_lab.actual_impulse`,
`game_state.environment.flight_lab.target_impulse`,
`game_state.environment.flight_lab.outcome`,
`game_state.environment.flight_lab.score`,
`game_state.environment.next_pipe`, `metrics.pipes_passed`,
`terminal.reason`, `debug.recent_events`, `debug.collision`, and
`control_trace`.

The application opens on the indefinitely stable `FLIGHT LAB`. Each drill
launches from one ordinary click or numbered key and freezes until
`BACK TO LAB`.

1. Launch `TAP ARC` with `Digit1` and inspect the frozen screenshot. Its
   `INPUT RECEIPT` visibly contains `PRESS S0` and `RELEASE S0`, proving both
   edges arrived in one fixed step. Baseline reports `ACTUAL IMPULSE 120`
   against `TARGET IMPULSE 220`; its thick actual trace falls below and stops
   before the faint target arc. Gold keeps the same receipt, reports
   `220 / 220`, follows all target checkpoints, and records `CLEAR`.
2. Return and launch `HELD ARC` with one click. Its receipt visibly runs from
   `PRESS S0` to `RELEASE S3`, and its target impulse is 250 rather than 220.
   Gold reports `250 / 250` and follows the distinct held arc. This screenshot
   rules out one constant or shifted flap for both drills.
3. Return and launch `LATE CONTACT` with `Digit3`. The panel shows the moving
   bird/pipe segment, both endpoint poses, a fractional `CONTACT INTERVAL`,
   `ENDPOINT SAFE`, and the frozen `CONTACT PROOF` rows. They show an
   `X WINDOW`, a `Y OUTSIDE` interval, and their non-empty `INTERSECT` even
   though the endpoint is safe. Baseline still commits `CLEAR`; gold resolves
   the same temporal proof as `BUMP` and commits no third clear.
4. Confirm the final gold ledger is `2 CLEAR` across `3/3 VIEWED`. Wait at
   least 800 ms on each result and confirm the receipt, impulses, trace,
   contact telemetry, result, and ledger remain unchanged.
5. Return to the lab and start the normal run. Follow the deterministic route
   through pipe IDs 1, 2, and 3. In fresh normal runs, dispatch a real browser
   keyboard down/up pair before one fixed step and one real pointer click
   before one fixed step; both must retain `PRESS` and `RELEASE`, apply the
   quick flap, and remain source-correct in `control_trace`.
6. Confirm ordinary ground collision/death, keyboard restart, a second death,
   pointer restart, and post-restart pointer control.

Expected deterministic outcomes:

- baseline: `bump, clear, clear`; TAP receipt is correct but impulse is
  `120 / 220`; HELD receipt is `S0 → S3`; LATE visibly shows a contact
  interval, safe endpoint, non-empty X/Y temporal intersection, and `CLEAR`;
- gold: `clear, clear, bump`, impulses `220 / 220` and `250 / 250`, final
  lab score 2, real same-tick keyboard/pointer custody, and retained collision
  interval before ledger commit;
- exact/adapted Revision 006 visual-CUA patch: `clear, clear, bump` with
  matching TAP/HELD arcs, but shifted receipts `S0 → S1` and `S0 → S4`,
  weak real same-tick browser flaps, and no retained LATE collision;
- Revision 005 visual-CUA relabel patch: `clear, clear, bump`, but impulses,
  trajectories, real input custody, and swept collision fail;
- Revision 005 structured-CUA two-file patch: `clear, clear, bump`, but it
  substitutes initial contact for an interval and leaves input/motion broken;
- Revision 003b constant-impulse patch: `bump, clear, clear`; TAP reports
  `250 / 220`, proving the one-size flap is wrong.

The decisive screenshot workflow is nine interaction/image-view steps:
initial view, three launches, two returns, and three frozen result views.
Only five are pointer or keyboard actions, and every screen waits
indefinitely.
