# Evaluator-lamp seeded restart parity replay

1. Reset to each protected seed and record the opening board.
2. Play `Down`, `Right`, `Up`, `Left`.
3. Reset to the same seed, replay those moves, hold `Left`, restart while the
   direction remains held, then release after the delayed-input window.
4. The settled board must exactly match the recorded opening. Replaying the
   four moves must match the control trajectory.
5. Repeat through Space, Try again, and `window.gameAPI.restart()`.
6. Confirm that an ordinary held arrow without a restart still repeats.
7. Repeat for seeds `160`, `1337`, and `3735928559`.

This is an adjacent lower-neighbor of revision 004. All seeds, routes, replay,
persistence, timing, source topology, gold repair, and verifier semantics are
unchanged. The only additional simplified axis is runtime visual observability:
the CUA build displays an evaluator-owned Opening parity lamp. The lamp reports
whether the live board matches the hidden opening reference, but does not expose
the reference board, implementation cause, or repair.

The lamp service is staged outside the agent sandbox and is used only during
the CUA session. The final condition-independent verifier runs without it.

The negative patch remains the strongest convergent revision-002 code-only
repair: it cancels delayed input at the restart boundary. It still fails because
the native Space and Try-again routes continue the consumed deterministic stream.
