# Upstream and packaging note

- Discovery repository: `gameworld-project/GameWorld-Games`
- Discovery revision: `55322928fa8bd51cb1719bd3807a32634aa5d3cb`
- Discovery directory: `benchmark/01_2048`
- Identified upstream: `2048` by Gabriele Cirulli
- Identified upstream license: MIT; see `RIGHTS.md`

This candidate retains the source required to execute the puzzle and the
GameWorld deterministic API shim. Decorative icons, screenshots, social
preview images, startup images, the bundled Clear Sans font files, unused AI
styles/scripts, and source SCSS were omitted because they are unnecessary for
the task and their per-asset provenance is not documented in the discovery
directory.

Hammer.js is retained for the original swipe input path and carries its own MIT
notice in `js/hammer.min.js`.

This bundle is a construction candidate, not a certified or frozen benchmark
task. Browser replay, no-op/gold/negative certification, code-only screening,
CUA evaluation, and matched confirmation remain pending.
