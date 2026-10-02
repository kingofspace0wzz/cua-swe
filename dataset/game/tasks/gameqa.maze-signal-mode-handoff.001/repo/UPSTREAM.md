# Upstream provenance

This compact candidate was written from scratch for the CUA-SWE construction
session. It adapts only generic state-machine ideas from the MIT implementation
clone at:

- repository: `github.com/8tentaculos/jsPacman`
- pinned revision: `0f255fee87c68b513f0ec286498d56162e813ee2`

The retained conceptual scope is limited to a global alternating mode timer, a
temporary mode, a dock/house-style release timer, and mode-entry/mode-exit
handoff. The candidate code, title, maze geometry, colors, DOM structure, and
presentation are original.

The GameWorld template at `benchmark/23_pacman`, revision
`55322928fa8bd51cb1719bd3807a32634aa5d3cb`, was used only to identify the
implementation lineage. No GameWorld file was copied.

## Complete media and presentation audit

- Images: none.
- Audio: none.
- Fonts: none; system monospace only.
- Sprite sheets: none.
- Screenshots in the playable repository: none.
- Upstream CSS or DOM: none.
- Upstream maps or maze art: none.
- Franchise title or character names in the runtime UI: none.
- GameWorld assets: none.
- Upstream implementation files copied verbatim: none, except the required MIT
  license text in `LICENSE`.
