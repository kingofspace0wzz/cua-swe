# Northline tour review: hotspots drift from imported panoramas

Repair the mobile panorama-tour annotation workflow. Review hotspots are misplaced on imported tours, and moving a review does not reliably preserve the intended position when the view changes or the scene is reopened.

The prepared app contains two fictional imported tour scenes. Each scene has an **Original panorama** viewer (including its registration magnifier) and a **Capture guide** attachment. Inspect these normal product evidence surfaces to establish how the received reviews relate to their scenes. The guides and original artwork are available in the broken app before any edits.

Make the review stay on its original feature as you change heading/elevation, including across the panorama seam. Moving it by tapping the view must save the corresponding review position. Keep label-only edits stationary, save each scene independently, and preserve saved work on ordinary reload. Do not change the original imagery, capture records, registration guides, or the meanings of the view controls to make the overlay appear aligned.

All ordinary client source is provided and editable, except the fixed `build.sh` wrapper. Use the existing plain HTML/CSS/ES modules; `sh build.sh` syntax-checks and copies the listed files to `dist` without replacing that directory. No package install is needed.

These imports are external product inputs, not files missing from your checkout. The isolated running app receives them through a deterministic local provider-inbox simulation. A source-only launch outside that prepared profile honestly shows an empty inbox. Both evaluation conditions use the same imported world. A normal reload keeps imports and saved reviews; an explicit rebuild/reset-to-scene clears user work and imports the original inbox afresh. This is a 400×800 mobile-web task, not a native mobile app.
