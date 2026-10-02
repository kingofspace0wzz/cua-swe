# Repair Campus Pocket's imported-campus routing

The route planner is producing unsuitable trips from imported campus maps. Repair the client integration so selected origin/destination and the step-free preference produce a shortest permitted route under the provider's contract, readable directions and length, or a clear unavailable result when no route is permitted.

The affected workflow is **Plan trip**. Its evidence surfaces are **Original map** and the paged **Routing report** for each import; both are accessible in the broken app. **Change campus** exposes the other imported campus under the same contract. Consult the original attachments, not just the symptom in the route result. Keep those attachments readable and unchanged.

Preserve the selected stops, step-free setting, campus selection and **Save trip / Open saved trip** behavior across normal reload. A saved trip must reopen with its saved settings, even after you explore another trip. Repairs must handle the imported data generally, rather than storing particular displayed routes or totals.

This is an original standalone synthetic mobile web application, not a real campus or travel advisory. The complete ordinary client and ordinary build inputs are supplied. Provider inputs are separate external product attachments imported only into the isolated running app; a source-only local build legitimately has an empty inbox, not a missing dependency. Both conditions use the same prepared external world. Normal reload preserves browser data; explicit rebuild/reset_to_scene starts fresh imports and default trip settings.

Use plain HTML/CSS/ES modules. All ordinary client files are editable except the protected `build.sh` wrapper. No packages or network dependencies are required. The build wrapper copies the existing root client files to the mounted `dist` directory and checks JavaScript syntax. Mobile scene: 400×800 CSS pixels, DPR 1, en-US, UTC.
