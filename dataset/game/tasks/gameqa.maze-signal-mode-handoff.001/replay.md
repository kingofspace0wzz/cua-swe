# Construction replay

The evaluator starts the protected scenario service, opens the application, and
calls the deterministic read-only bridge reset.

1. Hold Right until the player reaches the upper-approach column, then release.
2. Hold Up until the player reaches the junction row, then release.
3. Wait only until the visible teal warning clears and the dock rover commits
   its first branch.
4. If the player remains active, continue Right to the exit column and Up to
   the exit.

The decisive protected observations are:

- `phase.mode`
- `phase.elapsed`
- `alert.active`
- `alert.remaining`
- `rover.state`
- `rover.mode`
- `rover.appearance`
- `rover.hazard`
- `rover.branch`
- `rover.position.x`
- `player.lives`
- `metrics.contacts`
- `terminal.outcome`

Before the warning handoff, baseline and repaired builds must agree on player
position, lives, warning activity, dock release, and visible maze geometry.
After the handoff, the repaired build must show one coherent route, appearance,
and collision result, preserve all lives, and finish at the exit.

Expected construction outcomes:

- broken baseline/no-op: fails after the rover commits the conflicting branch;
- gold: passes the handoff assertions and reaches terminal success;
- negative: clears the obvious stale appearance but still fails because the
  resumed route phase belongs to the wrong temporal episode.

The verifier writes `verifier-artifacts/state-replay.json` and the five named
Chromium screenshots. Two sealed gold replays must produce the same normalized
state checkpoints.

