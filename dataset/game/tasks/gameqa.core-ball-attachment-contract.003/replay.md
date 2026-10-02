# Core Ball attachment-contract revision 003 replay

This is the evaluator replay contract. The agent-facing instruction remains
symptom-only and does not expose protected timestamps, angles, state paths, or
the repair sequence.

1. Reset seed 808, level 1 in manual fixed-step mode and start the round.
2. Tap the playfield at game time 0. Advance to 7000 ms and make an ordinary
   second coordinate tap. `round.phase` remains playing,
   `shots.active.progress` is 0.35, `shots.waiting` is one, and the visible
   queue cue reads `NEXT PIN READY`. The same two calls fit within the
   twenty-second real-time opening flight used by screenshot-only play.
3. Advance to 19000 ms. The first pin remains visibly in flight at 95 percent,
   `shots.waiting` is still one, `metrics.attachments` is zero,
   `motion.angle` is 324 degrees, and `occupancy.pins` remains
   `[180, 300, 359]`. This is the required pre-trigger equivalence checkpoint.
4. Advance to 20000 ms. The first pin attaches at local angle 90,
   `motion.transition.active` becomes true, and the waiting pin is promoted.
   Gold must publish `shots.active.launchProfile` as `shifting` and
   `shots.active.flightTime` as 710 with the committed pace contract; baseline
   and the strongest negative instead expose the pre-commit cruise promotion.
5. Advance to 20700 ms and capture the follow-up approach.
   `round.phase` remains playing, `metrics.attachments` is one,
   `shots.active.progress` is above 0.9, `motion.angle` is 58.275 degrees, and
   the fixed world-space contact line is visibly open.
6. Advance to 20780 ms. Gold splits the enclosing fixed step at the 20710 ms
   event, records `lastAttachment.at` as 20710,
   `lastAttachment.coreAngle` as 59.58675 and
   `lastAttachment.localAngle` as 30.41325, then integrates the remaining
   motion to 69.147 degrees. `lastAttachment.launchProfile` is `shifting`,
   `round.phase` remains playing, `metrics.attachments` becomes two, and
   `metrics.failures` remains zero.
7. The baseline instead uses its queued request-time angle and fails near the
   occupied 180-degree spoke at 20780 ms. `negative.patch` is the mechanically
   adapted revision 002 code-only success: it splits at impact and samples the
   current core angle, but its waiting pin was already promoted from the
   pre-commit cruise profile. It reaches contact at 20770 ms with local angle
   22.25925, inside clearance of the 359-degree spoke, and fails
   `post_commit_promotion_transaction`.
8. Advance to game time 22000. The accepted `occupancy.pins` must persist and
   `motion.transition.active` must be false. Fire and advance 600 ms; wait
   1000 ms, fire, and advance another 600 ms. The spaced sprint-profile shots
   attach at 118.8 and 248.4 degrees, `round.phase` becomes passed, and
   `metrics.completed` becomes one.
9. Restart and verify initial `occupancy.pins`, pace, remaining count, and all
   metrics. Then start again, advance 2500 ms, fire once, and advance 20000 ms.
   This intentional collision must set `lastAttachment.accepted` false without
   adding the rejected candidate to `occupancy.pins`. Restart once more and
   verify normal ready state.

Protected browser evidence is `verifier-artifacts/state-replay.json` plus
`initial.png`, `queue-window.png`, `pre-first-contact.png`,
`pace-transition.png`, `second-approach.png`, `post-trigger.png`,
`post-transition.png`, `third-approach.png`, `final.png`,
`rejected-collision.png`, and `restart.png`. The evaluator-owned network-free
module replay writes `verifier-artifacts/module-replay.json`; it is additional
deterministic state evidence and does not replace or weaken Chromium checks.
