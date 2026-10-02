# Protected deterministic replay

The evaluator-owned fixture supplies every concrete word, clue, accepted
vocabulary entry, and expected state or pixel pattern. None is repeated here
or in the agent-visible source.

1. Reset Daily mode and record `01-initial-daily.png`.
2. Submit `protected.replay.firstGuess`; record the staggered and settled
   repeated-letter checkpoints, then verify model/rendered keyboard precedence
   and hard-guidance multiplicity.
3. Submit `protected.replay.hardViolation` and
   `protected.replay.invalidWord`; require visible rejection without row
   consumption.
4. Click **Restart round**, then switch to **Practice** and back to **Daily**,
   recording fresh state at each boundary.
5. Submit `protected.replay.answer`. Record its staggered reveal, the settled
   successful row before result motion, one active native finish frame, and
   terminal completion.
6. Require the ordinary **Replay finish** control to be visible and enabled.
   Click it normally and record the playback-start state.
7. Wait only on replay state, not wall-clock sleep. Record the stable paused
   mid-replay frame with **Continue** visible. Compare the complete rendered
   board unit with its settled reference.
8. Click **Continue**, record playback in progress, and require completion
   from five native animation-end events with zero fallback.
9. Click **Replay finish** again. Repeat the paused comparison and Continue
   completion to prove the affordance is repeatable.
10. Restart and switch Practice/Daily after replay. Finally, repeat successful
    completion in a reduced-motion browser context and require replay to
    complete without introducing the inspection pause.

Baseline and no-op must fail at the stable replay-visible boundary. Gold must
pass all twenty-four checkpoints. Every retained negative must apply
independently, preserve deterministic terminal completion, and fail either a
decisive replay comparison or a distinct finish/replay preservation control.

Audited state paths are `challenge.mode`, `rows[0].tiles`, `keyboard`,
`hardMode.exact`, `hardMode.minimum`, `reveal.active`,
`validation.rejected`, `validation.hardRejected`, `terminal.success`,
`presentation.tiles`, `presentation.motion.activeTiles`,
`presentation.motion.animationEndCount`, `presentation.motion.fallbackCount`,
`presentation.motion.replay.phase`, `presentation.motion.replay.count`,
`presentation.motion.replay.pausedCount`,
`presentation.motion.replay.continueCount`,
`presentation.motion.replay.animationEndCount`,
`presentation.motion.replay.fallbackCount`,
`presentation.motion.replay.replayControlVisible`,
`presentation.motion.replay.continueControlVisible`, and
`presentation.resultVisible`.
