# Clean-room provenance

Signal Weave is an original browser game written for the CUA-SWE benchmark.
It does not contain code, artwork, sound, title material, character designs,
level geometry, text, variable names, timing tables, or other expressive
material from the discovery snapshot.

Behavioral discovery reference:

- Collection: GameWorld-Games
- Revision: `55322928fa8bd51cb1719bd3807a32634aa5d3cb`
- Discovery entry: `GameWorld-Games/benchmark/33_worlds-hardest-game`
- Rights finding: the snapshot has no reusable code or asset redistribution
  license.

The discovery snapshot was consulted only for broad mechanics vocabulary:
keyboard movement, moving hazards, pickups, checkpoints, collision return,
and reaching an exit. The implementation, geometry, presentation, names,
route-card diagram, and runtime architecture were created independently.

All runtime visuals use original HTML, CSS, Canvas 2D primitives, and one
original PNG route card produced from project-owned geometric artwork. There
are no external media files or runtime dependencies. The implementation and
route card are licensed under the MIT License in `LICENSE`.

Revision 003 retains the revision 002 clean-room game and changes only how
evaluator-owned runtime bytes reach the browser: the application server relays
the ticket and route card through fixed same-origin endpoints. No discovery
material was consulted or introduced for that delivery change.
