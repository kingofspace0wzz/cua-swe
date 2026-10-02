# Provenance and packaging record

This quarantined benchmark candidate was derived from:

- GameWorld-Games directory: `benchmark/03_astray`
- GameWorld-Games revision:
  `55322928fa8bd51cb1719bd3807a32634aa5d3cb`
- Identified upstream game: Astray by Rye Terrell (`wwwtyro`)
- Identified upstream URL: `https://github.com/wwwtyro/Astray`
- Rights metadata supplied by GameWorld-Games: `RIGHTS.md`

The original `README.md` and `RIGHTS.md` are retained verbatim. The GameWorld
deterministic-random shim and `window.gameAPI` adapter are also retained and
adapted for the candidate.

## Discovery-file identities

The following files are byte-identical to the discovery input:

| File | SHA-256 |
| --- | --- |
| `Box2dWeb.min.js` | `161c240927acb1f66059684b5feb7c0e9fe17823a32f39a65cc575aacaae8df2` |
| `Three.js` | `893df945a44244160c3f4b024e989d686c073a77110188c4116d39d84dc6353b` |
| `jquery.js` | `47b68dce8cb6805ad5b3ea4d27af92a241f4e29a5c12a274c852e4346a0500b4` |
| `keyboard.js` | `e485352c260762d19f222f33290d07d30d4a8ec023325fb1d8d121c4d1bda884` |
| `maze.js` | `7ba75832a61268f7b990a37dbde32333792f1fbafca7dcedaf3dfd165192e9a1` |
| `README.md` | `b01625591f4048b1aec81a8acb53980b690c6f775957dd01512369d2fb293705` |
| `RIGHTS.md` | `b3420a8594a46121aa0fd8c033d15b3e3895d27b8f86b481ca288201e009a00d` |

`index.html` and `game_api.js` are adapted candidate files and therefore do
not retain the discovery-input hashes.

## Deliberately omitted assets

The source snapshot contained `ball.png`, `brick.png`, and `concrete.png`.
Their individual provenance was not documented in the discovery directory, so
they are not redistributed in this candidate. The rendering code uses solid
procedural material colors instead. No audio or additional media is included.

## Local candidate adaptations

- fixed-seed Level 2 selection remains available through `window.gameAPI`;
- `R` restarts the current maze so the interaction trigger is agent-accessible;
- the state adapter reports player motion and generic completion progress;
- the resize handler tolerates events before camera initialization;
- restart rebinds movement controls so the prior held-input defect is not
  present in this revision;
- the final exit is opened before physics fixtures are constructed, retaining
  the certified revision-002 gameplay repair;
- the revision-003 rendered-heading input conversion is incorporated rather
  than left as an alternate repair target;
- the revision-005 pressure gate and all gate-only metadata were removed after
  its oracle rejected behaviorally correct repairs for retained pink pixels;
- revision 006's delivery relay was removed after a formal code-only Sol run
  reconstructed its fixed landing target and passed the behavioral verifier;
- revision 007's orientation console was removed after a formal code-only Sol
  run recognized its world-to-camera transform and repaired both vector sites;
- revision 008's kinetic chimes, sparse contact sampling, continuous-contact
  repair target, and contact-weave oracle were removed after the formal
  code-only repair succeeded and the static verifier produced a source-shape
  false negative;
- the broken revision-009 snapshot presents a deterministic three-seal glass
  gallery whose player state advances normally while overlapping transparent
  WebGL layers produce the wrong visible cores and crowns;
- gold and two independent negative patches distinguish complete layered
  presentation, depth-write-only repair with reverse-composited crowns, and
  order-only repair with unresolved cores.

This record documents provenance; it is not legal advice or a substitute for
independent license review before publication.

## Publication block

Astray is identified as Unlicense in the retained rights metadata. Exact
Box2dWeb upstream/revision/license and exact Three.js revision notices remain
unresolved. The candidate is quarantined, must not be promoted, and requires
independent rights review before publication.
