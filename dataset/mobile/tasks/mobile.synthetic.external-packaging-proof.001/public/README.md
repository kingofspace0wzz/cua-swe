# Foldnote
Original standalone synthetic mobile web design mockup. Not a manufacturing tool.
No network or npm dependencies. Run `sh build.sh`; serve dist with an ordinary static server outside the task runtime if desired. All client code and ordinary build inputs are here; only build.sh is protected in the task. The app deliberately starts with an empty inbox outside the prepared runtime.

The provider import is a separate product input, simulated locally by trusted runtime setup into browser storage `foldnote.imported`. It is not a missing build dependency. The viewer displays supplied artwork, report sections and placement records without fetching a service. User reviews use a separate browser storage entry. The two prepared proofs are selectable in the app. Source proof / Panel report is available even when the review overlay is wrong.

Scene: 400×800 CSS pixels, DPR 1, en-US, UTC. Ordinary reload retains imported data and saved reviews. A source rebuild uses explicit reset_to_scene: fresh imports and initial review defaults, not unsaved editor state. Use Save review before changing panel/proof. One arrow marker and one note per panel; numeric entry or tapping is sufficient, no precision dragging needed.
