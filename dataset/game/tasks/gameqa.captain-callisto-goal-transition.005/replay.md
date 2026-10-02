# Deterministic Level 6 staged-completion replay

1. Build and launch `/?benchmark=1&level=6`, then reset with seed `47`.
2. Hold **D** to climb the shallow castle stair and collect the first two coins.
3. Continue holding **D** through the final stair coin. Confirm the HUD shows
   all three coins and the astronaut is alive.
4. Without releasing **D**, also hold **Shift** and enter the transporter.
5. Keep both controls held until the native `LEVEL 6 CLEARED` presentation is
   visible, then return the gameplay controls to neutral.
6. The broken build removes the presentation and returns to active gameplay.
   The source-obvious latch-only repair instead commits success but consumes
   that gameplay-control release as `continue`, advancing into the next intro.
7. A repaired build keeps the presentation active after the approach controls
   return to neutral, reports native terminal success, and remains in
   `AFTER_LEVEL`.

The decisive evidence crosses three runtime phases. The flag stages completion,
the menu renders a delayed success presentation, and the input sampler advances
while the forward-plus-jetpack intent remains held. The broken coordinator
mistakes those frame samples for a changed control intent and also rechecks
live transporter contact after the presentation has started. The held jetpack
moves the astronaut away during that delay, so the transition is cancelled.

The gold repair tracks semantic input-intent changes rather than active frames,
treats eligibility as latched when the flag stages completion, and requires a
fresh menu input cycle after the gameplay-held keys return to neutral. The
source-obvious negative latches completion but leaves the clear menu armed by
the approach controls, so their release is consumed as `continue` and the
verifier rejects it.

The protected replay is state-bounded, records the final-coin checkpoint, the
visible success stage, and the settled terminal state, and captures Chromium
screenshots at each checkpoint.
