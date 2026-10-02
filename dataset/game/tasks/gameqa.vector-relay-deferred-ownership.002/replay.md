# Vector Relay successor construction replay

Use the normal runtime on port 51320 at
`http://127.0.0.1:51320/?challenge=relay-circuit`. The viewport is 1280×720.
The agent receives screenshots only. The protected construction verifier may
read `window.gameAPI.getState()`.

## Visible unsteered route

1. Call `window.gameAPI.reset({seed: 73, level: 3})`. Confirm
   `relay.phase == idle`, `relay.contacts == 0`, `relay.commits == 0`,
   `relay.pending == 0`, `relay.dropped == 0`, `score == 0`, and three lives.
2. Press Space. Wait until the north relay glows yellow. The first contact must
   have settled once: `relay.phase == armed`, `relay.contacts == 1`,
   `relay.commits == 1`, and `relay.pending == 0`.
3. Do not steer. Wait for `metrics.losses == 1`, `orb.attached == true`, and
   `orb.attachReason == life-replacement`. Two lives remain and the relay is
   still armed.
4. Press Space without steering. Wait for `metrics.bounces >= 2`. The orb must
   visibly rebound from the yellow relay while `relay.pending == 1`.
5. Wait for the same orb to fall out and the final replacement to dock:
   `metrics.losses == 2`, `orb.attached == true`, one life remains, and
   `ownership.port == receiver`. At this causal checkpoint the baseline, gold,
   and strongest successor negative all still show `relay.phase == armed`,
   `relay.contacts == 1`, `relay.commits == 1`, `relay.pending == 1`, and
   `score == 0`.
6. Wait for settlement. The baseline and the exact predecessor epoch patch end
   with `relay.phase == armed`, `relay.pending == 0`, `relay.dropped == 1`,
   `score == 0`, and `terminal.outcome == null`. A repair must instead remove
   the yellow glow, show CIRCUIT COMPLETE, and finish with
   `relay.phase == cleared`, `relay.contacts == 2`, `relay.commits == 2`,
   `relay.pending == 0`, `relay.dropped == 0`, `score == 500`, and
   `terminal.outcome == success`.

The visible return bounce and final replacement docking are required. Waiting
without playing the route cannot distinguish the causal repair.

## Protected dock-movement route

Reset and repeat through the return bounce and final replacement docking. While
`relay.pending == 1`, hold ArrowLeft until `ownership.port == west`, then
release ArrowLeft and wait for settlement. The attached orb must visibly move
with the receiver.

The same completion assertions from step 6 must hold with
`ownership.port == west`. This rejects the strongest source-local repair that
accepts a delayed result whenever the old and current owners name the same
dock port. That repair passes the visible unsteered route but discards the
already reached result after normal attached movement changes the port.

## Exactly-once and reset assertions

- The first physical contact produces one settled arm.
- The return collision produces one pending result despite recursive overlap.
- `relay.contacts` and `relay.commits` finish at two, never three.
- `relay.pending` and `relay.dropped` finish at zero on successful runs.
- The completion score is 500 and never 1000.
- A full `gameAPI.reset` clears pending work, dropped counts, score, contacts,
  lives, and terminal state before either route is replayed.

## Expected certification matrix

| Build | Unsteered route | Protected left-shift route |
| --- | --- | --- |
| baseline/no-op | fail: armed, dropped 1, score 0 | fail: armed, dropped 1, score 0 |
| predecessor epoch negative | fail: armed, dropped 1, score 0 | fail: armed, dropped 1, score 0 |
| strongest successor negative | pass: cleared, score 500 | fail: armed, dropped 1, score 0 |
| gold | pass: cleared, score 500 | pass: cleared, score 500 |

The browser verifier saves JSON states and PNG screenshots for each checkpoint.
