# Upstream and asset audit

Vector Relay is a neutral, task-local adaptation of the browser-game runtime
structure published by Jake Gordon and contributors under the MIT License. The
implementation lineage is pinned to commit
`eed59e2affa9423b93d2ac8ff93061bb88b33284` from
`https://github.com/jakesgordon/javascript-breakout`.

The discovery input was GameWorld-Games commit
`55322928fa8bd51cb1719bd3807a32634aa5d3cb`, directory
`benchmark/05_breakout`. That snapshot was used only to identify the upstream
lineage; it is not treated as an independently licensed asset package.

## Inclusion audit

- Included: the upstream MIT copyright and permission notice in `LICENSE`.
- Included: original task-specific JavaScript, HTML, and CSS for Vector Relay.
- Included presentation: canvas primitives, text, borders, gradients, and CSS
  geometry created for this candidate.
- Excluded: all upstream images, audio, sound-manager code, fonts, archives,
  packaged screenshots, and other media.
- Excluded: all upstream game branding from the player-facing presentation.
- Excluded: the upstream sound files, which carry separate CC BY-ND
  attribution and are not covered by the implementation's MIT grant.
- No network-hosted or encoded media are loaded at runtime.

The upstream implementation license does not grant rights in third-party game
names or related intellectual property. The candidate therefore uses the
original neutral name **Vector Relay** and original presentation geometry.
