# Upstream provenance

This clean browser runtime is based on the game mechanic and interface concept
of **Core Ball** by Random / YangHao.

- Repository: https://github.com/randomyang/core-ball
- Frozen revision: `3dff3f1160a15e9068d0764023bcaa83b9057938`
- Original GameWorld identifier: `08_core-ball`
- Upstream license: MIT; preserved verbatim as `LICENSE-MIT`

Files reviewed from that revision were `index.html`, `js/general/Ball.js`,
`BallQueue.js`, `Collide.js`, `Core.js`, `Game.js`, `Levels.js`, `Scene.js`,
`Switcher.js`, and `Tween.js`. They establish the rotating core, radial child
pins, asynchronous launched-ball queue, angle-relative attachment, collision,
and level progression mechanic.

All files in this candidate's `src/` directory are an original ES-module and
fixed-step implementation written for deterministic benchmark replay. No
upstream JavaScript was copied verbatim. No upstream PNG file is included or
used. The canvas marks, controls, typography, background, and all other visual
elements are original CSS/canvas primitives.

The upstream RequireJS loader and MD5 implementation are not retained, so
their separate third-party notices and code are not part of this bundle.
