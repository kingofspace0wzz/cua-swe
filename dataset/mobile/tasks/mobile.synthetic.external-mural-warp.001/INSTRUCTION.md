# Repair Mural Desk's imported projection workflow

Mural Desk is a standalone mobile web mural planner. Following a Projection Office interface integration change, imported source artwork, wall placement, and inverse pin editing no longer agree. Repair the shared mapping boundary and its edit/save workflow without removing the ordinary client functionality.

The prepared app contains two external office packets. Open either from **Projection inbox**, then **Received packet** to inspect the received guide, registration report, original source artwork, and intended projection plate. Both packets follow the same complete received contract. The viewer works before the repair. Use these product inputs to establish the mapping and expected visible behavior—not just the broken preview.

The repaired plan must show the cropped artwork in its intended perspective and orientation, respect panel seams and blocked areas, keep selected marks aligned, and support precise source/wall pin placement in both directions. Preserve rejected-move behavior, undo/cancel, readable saved receipts, per-packet saved notes and pins, and save/reopen/reload behavior. The received guide defines these operations. Fix the general workflow rather than special-casing a packet or displayed values.

All ordinary client source and build inputs are present. Only `build.sh` is protected; all other ordinary client files may be edited. There are no package or network dependencies. `sh build.sh` syntax-checks the modules and copies the app into `dist`.

The office inbox is a deterministic local simulation of external imported product inputs supplied only to the isolated running app. A standalone build outside the prepared runtime starts with an empty inbox; the attachments are not files in the coding workspace. Ordinary reload preserves imported inputs and saved plans without reimporting. A successful runtime rebuild explicitly resets to the imported starting scene. Initial viewport: 400×800 CSS pixels, DPR 1, UTC, en-US. This is synthetic mobile web, not a native Android/iOS application.
