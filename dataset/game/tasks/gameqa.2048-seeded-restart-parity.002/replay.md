# Seeded restart input-envelope replay

1. Reset to a protected seed and record the opening board.
2. Play `Down`, `Right`, `Up`, `Left`.
3. Hold `Left`, restart through Space while the key remains held, then release.
4. The fresh board must remain at the recorded opening until the next deliberate
   move. Replaying the four moves must match the control trajectory.
5. Repeat with the Try-again control and `window.gameAPI.restart()`.
6. Confirm that an ordinary held arrow without a restart still repeats.
7. Repeat for seeds `42`, `1337`, and `3735928559`.

The broken build leaves a pre-restart held-key callback alive across the episode
boundary. It moves the newly created board and consumes the next seeded spawn
before the player's first post-restart action.

The strongest prior code-only repair only rewinds `window.__resetRandom()` from
`GameManager.restart`. That restores the opening momentarily but does not cancel
the old input lifecycle, so the delayed move still advances the new episode.
