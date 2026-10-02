# Deterministic Level 3 temporal jetpack replay

Hold **D** through three jetpack pulses. For each pulse:

1. Press **Shift** and wait until `jetpack_visible` becomes true.
2. At 0.12 seconds of game time after ignition, capture the early-output
   screenshot and state.
3. Continue holding until 0.55 seconds of game time after ignition.
4. Release **Shift**, wait until `jetpack_visible` becomes false, then wait
   another 0.20 seconds of game time and capture the off-gap screenshot/state.

The early checkpoint must still be in the visibly growing ignition phase and
must consume no more than 1.7 fuel. During every off gap, visible exhaust and
physical thrust must both be off, gap fuel use must be no more than 0.35, and
vertical velocity must decay (or the player must have landed).

After three pulses, release **D**, wait for the player to land, then hold **D**
to collect all three coins and reach the flag. The replay uses game-time and
state transitions rather than wall-clock frame counts.

The broken snapshot has disagreements across release-edge sampling, hero
lifecycle state, and force integration. The adversarial negative makes physical
thrust follow the held key, which repairs the visible release gap, but it keeps
the previous ignition output and still applies full force/fuel immediately on
the next pulse. The early screenshots and fuel/velocity evidence distinguish
that result from the gold behavior.
