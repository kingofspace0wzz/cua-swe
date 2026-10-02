# Upstream and modification notice

This package is a modified, compact source rebuild based on the gameplay
responsibilities and GPL-licensed implementation identified as:

- Project: `MikhaD/wordle`
- License: GNU General Public License version 3
- Inspected implementation revision:
  `199122be1f3ed71f5cf4abd5748debd91ee540a0`
- Pinned discovery corpus: `GameWorld-Games`
- Pinned discovery revision:
  `55322928fa8bd51cb1719bd3807a32634aa5d3cb`
- Discovery template path: `32_wordle`

The pinned discovery snapshot was used only to identify provenance and study
native runtime behavior. Its compiled bundle and branding media are not
shipped. This package replaces the title, HTML, CSS geometry, palette,
controls, rendering, and visual assets with original work. It includes no
copied logo, icon, screenshot, image, service worker, manifest artwork, or
original Wordle/NYT branding or trade dress.

The GPL applies to the identified implementation and this modified source
package. It does not grant rights in original Wordle or New York Times names,
branding, artwork, or trade dress.

Major modifications include a dependency-free module layout, evaluator-owned
deterministic challenge loading, original board and keyboard rendering, a
public benchmark state bridge, daily/practice navigation, hard guidance,
staggered tile turns, an ordinary player-facing finish replay, and a
controlled browser-rendering regression for debugging research.
