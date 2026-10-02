# Protected Hextris cascade-resettle replay

Browser execution is intentionally pending. This document defines the replay
that must be certified outside the local construction machine.

## Reset and fixture

1. Launch `/?benchmark=1&level=1` at 1280×720.
2. Call `window.gameAPI.reset({level: 1})`. Do not rely on the reported seed:
   Hextris declares seed support unavailable.
3. Inject `env/deterministic_fixture.js` as evaluator-owned state and call
   `window.__cuaSweInstallHextrisCascadeFixture()`.
4. Confirm `game_state.score` is `0`,
   `game_state.environment.settled_blocks` is `6`, and
   `game_state.player.lane_rotation` is `0`.

The visible board contains two red supports, three blue blocks resting above
those supports, one blue seam anchor, and one incoming red block. Protected
roles `protected.roles.cascade_mobile_a_v1.settled` and
`protected.roles.cascade_mobile_b_v1.settled` distinguish the two fast blue
blocks. `protected.roles.cascade_mobile_c_v2.settled` identifies the slower
fourth member of the eventual group.

## Trigger

1. Wait at least 100 ms after reset.
2. Press **ArrowLeft** exactly once through the browser.
3. The incoming red block lands in the open lane and the three-red group
   clears. `game_state.score` becomes `9`.
4. The fast blue blocks and anchor briefly form a connected three-block seam
   while `cascade_mobile_c_v2` is still falling above them. The score must
   remain `9`; this transient trio must not clear.
5. Once all three mobile blue blocks settle, the connected four-block cascade
   clears as the second combo. The final score is exactly `41`, and the board eventually
   becomes empty.

The protected trace records
`protected.consolidation_trace[*].before_score` and
`protected.consolidation_trace[*].after_score`. No trace entry may increase the
score while any protected mobile blue role is airborne.

## Expected outcomes

- Broken baseline: red clears; all four blue blocks settle without a follow-up check;
  final score remains `9`.
- Gold patch: no premature score; the four-block cohort clears exactly once
  after the whole collapse settles; final score is `41`.
- Negative patch: the successful `r003` code-only repair combines eager
  per-block checking with settled-only flood fill; it reaches `27` by clearing
  the transient trio before the slower blue block settles.

## Negative controls

- Reinject the primary fixture and provide no rotation: score remains `0`.
- Inject `{pairOnly: true}`, perform the same one-step rotation, and confirm a
  two-red group never scores.

Certification must collect state evidence and screenshots, but no browser game
was launched or recorded during initial local construction.
