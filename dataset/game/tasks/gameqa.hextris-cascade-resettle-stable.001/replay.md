# Protected Hextris cascade-resettle replay

This controlled lower neighbor preserves the r005 gameplay and verifier semantics. Its sole simplification is protected-runtime initialization: the evaluator reinstalls the prepared challenge through the startup window so the first durable visual observation is the deterministic fixture.

## Reset and fixture

1. Launch `/?benchmark=1&level=1` at 1280×720.
2. Call `window.gameAPI.reset({level: 1})`. Do not rely on the reported seed:
   Hextris declares seed support unavailable.
3. Inject `env/deterministic_fixture.js` as evaluator-owned state and call
   `window.__cuaSweInstallHextrisCascadeFixture()`.
4. Confirm `game_state.score` is `0`,
   `game_state.environment.settled_blocks` is `7`, and
   `game_state.player.lane_rotation` is `0`.

The visible board contains two red supports, three blue blocks resting above
those supports, one blue seam anchor, one isolated green block, and one
incoming red block. Protected
roles `protected.roles.cascade_mobile_a_v1.settled` and
`protected.roles.cascade_mobile_b_v1.settled` distinguish the two fast blue
blocks. `protected.roles.cascade_mobile_c_v2.settled` identifies the slower
fourth member of the eventual group.

## Trigger

1. Inspect the suspended incoming red block; it remains at the spawn radius until the first rotation.
2. Press **ArrowLeft** exactly once through the browser. That interaction releases the block at the original fall speed.
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

## n003 controlled simplification

The protected pre-action board is continuously reinstated until the first rotation. After the red clear, the slow blue member uses iter `2.5` rather than `1.5`; all grouping, scoring, unrelated-green, gold, and negative semantics remain unchanged.

## n004 controlled simplification

After the first red clear reaches score `9`, the evaluator-owned fixture slows
only the collapse playback until `cascade_mobile_c_v2` settles. The incoming
red trigger, board geometry, match-size rule, source snapshot, final states,
gold patch, eager negative, and unrelated-green negative are unchanged. This
widens the visible intermediate three-blue window without exposing protected
roles or state to the agent.

## n005 controlled simplification

After the first red clear reaches score `9`, the delayed blue member and the
unrelated green block above it pause at their pre-collapse radii for 2.4
seconds. The other three blue blocks settle first, leaving a visible gap below
the delayed fourth blue member. The paused stack then resumes the same slowed
collapse used by n004. Initial geometry, source snapshot, match-size rule,
scoring outcomes, gold patch, eager negative, and unrelated-green negative are
unchanged.

## n006 controlled simplification

The post-clear intermediate state is now an interaction-stable causal
tableau. The delayed fourth blue member remains separated from the settled
three-blue seam for 20 seconds, long enough to survive normal model reasoning
latency between browser actions. The unrelated green block is shown on the
opposite side and falls independently during the same window. This makes the
required same-color cohort boundary visible without exposing protected state.
The source snapshot, ordinary match-size rule, score outcomes, gold patch,
eager negative, and whole-board barrier negative are unchanged. Only verifier
wait time is enlarged to accommodate the longer protected playback.

## n006b timing-preservation correction

The evaluator-owned combo clock pauses through the persistent tableau and the
delayed blue member's subsequent landing. This preserves the original
score-`41` combo outcome despite the longer visual playback. No source,
geometry, grouping, or verifier acceptance condition changes from n006.

## n007 controlled simplification

An evaluator-owned legend is visibly overlaid on the prepared game:

- **RECHECK ONLY AFTER ALL BLUE PIECES SETTLE**
- **THE GREEN PIECE IS UNRELATED**

The legend exposes the causal rule through the CUA channel only. It does not
exist in the source-only workspace and does not reveal protected roles,
verifier code, or state. The n006b tableau, source snapshot, gameplay,
scoring, gold patch, negatives, and verifier acceptance conditions are
unchanged.

## n008 controlled simplification

The evaluator-owned legend is refined into an implementation-level recipe:

1. Queue each block when it re-settles.
2. Release its queued consolidation only when no non-deleted, unsettled block
   of the same color remains.
3. Restrict flood fill to settled neighbors.
4. Do not set `checked = 1` immediately and do not wait for the whole board.

The recipe is visible only through the CUA channel. Source snapshot, gameplay,
scoring, tableau, gold patch, negative controls, and verifier acceptance
conditions remain unchanged.
