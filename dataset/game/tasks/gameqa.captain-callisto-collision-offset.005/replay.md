# Deterministic gameplay replay

1. Build and launch `/?benchmark=1&level=4`.
2. Reset with seed 45 and Level 4.
3. Hold **D+W+Shift** from the launch pad until the astronaut reaches the
   northeast launch checkpoint near `x=8.0`.
4. Release **Shift** while keeping **D+W** held. The astronaut is still rising
   at release, passes through the descending slot, and then approaches the
   exposed northeast corner.
5. The broken build retains its compact descent envelope into the corner,
   accumulates both horizontal contact axes, visibly clips the astronaut into
   the edge, and pins movement.
6. A repaired build keeps the compact envelope through the descending slot,
   expands before the corner contact, and compacts again only after landing.
7. After clearing the corner, line up with the narrow safety-rail
   opening at `x≈16`, cross it while the compact post-release envelope is still
   active, then continue northeast.
8. Traverse the deck opening, collect three coins, and reach the flag.

The decisive evidence is the post-release corner contact. Before the release,
the broken and repaired trajectories use the same launch geometry and inputs.
This stronger neighbor distinguishes three envelope phases. The prior
source-only success—normal radius throughout descent and compact only after
landing—cannot fit through the descending slot.
