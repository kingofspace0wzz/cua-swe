# Replay — `gameqa.captain-callisto-conditional-physics.002` revision 3

Launch `/?benchmark=1&level=3`, reset with seed 44, and use the
desktop 1280×720 viewport.

1. Hold `D` and `Shift` together from the starting platform.
2. Continue until the astronaut has cleared the first yellow lift.
3. Release only `Shift`; keep `D` held while crossing the second lift.
4. In the broken build, the trajectory is equivalent before release and then
   visibly bends left. Continued right input cannot recover the route.
5. Revision 3 starts on the first moving lift, which reverses before the
   release edge. The revision-2 source-only repair removes the left bend and
   preserves gravity, but still observes that live support vector instead of
   the activation snapshot. It therefore transfers the wrong horizontal frame.
6. In the repaired build, the astronaut preserves rightward control, crosses
   the second lift, stops climbing after thrust ends, settles onto the long
   landing runway, and reaches the flag.

The protected replay records the release x-coordinate and a bounded
post-release window. It rejects any leftward excursion greater than 0.35 world
units, requires at least 2.5 units of forward progress in that window, and
requires a grounded landing followed by native Level 3 success.

The causal mechanism is deliberately composed. Jetpack lifecycle code converts
between world and support-relative velocity, the moving-platform API publishes
the support frame, and the player integrator consumes the transfer. Fixing only
the visually obvious subtraction direction leaves the stale frame reapplied
during the second-lift transition and does not satisfy the replay.
