# Larkspur Plate Desk
Original standalone synthetic mobile web app, plain HTML/CSS/ES modules.
Run `sh build.sh`; serve dist with an ordinary static server. No npm install.
Build wrapper is protected and preserves the mounted dist directory. All other
ordinary files are editable. No dependencies or private data are bundled.

The prepared task runtime imports a deterministic external provider inbox into
browser storage. Ordinary startup outside it honestly shows an empty inbox.
The inbox contains two named editions, each with a finder PNG, plate PNG, and
exposure/nominal-scale/target-count metadata. It has no point coordinates.
The separate sheets are available from Plate and Finder; Guide states all rules.
Read the full ordinary raster.js, geometry.js, app.js and integration.js freely.
Generic algorithms are complete. integration.js retains both earlier field
registrations; the received replacement sheets must agree with the integration.

`larkspur.provider-inbox.v1` is the imported external input. It is browser state,
not a source dependency. `larkspur.saved.v1` contains independent saved drafts.
Reload keeps both. Source rebuild explicitly resets the isolated scene.
Do not replace image evidence with blank sheets or remove the editor workflow.
The reference implementation supports both pose and six-entry affine matrix
registration inputs, and tables or catalogue/identification maps; no particular
internal representation is required for a repair.
