# Campus Pocket

Original standalone synthetic mobile web app. Not a real campus or travel service.
No npm packages, network endpoints, provider SDKs or hidden ordinary client files.
Run `sh build.sh`; serve the contents of `dist` with any local static server in your own authorized runtime. The evaluation runtime handles serving and mobile input.

The complete client is here. The prepared app imports an external provider inbox into browser storage. It contains original map attachments and paged reports, accessible through **Original map** and **Routing report**, with a **Change campus** chooser. The public source/build intentionally starts with **No imported campuses** outside that prepared runtime. There is no missing public fixture file to locate or dependency to install. This is a deterministic local simulation of product inputs, not an external network service outage.

`app.js` implements the generic inbox/viewer, selectors, trip presentation and persistence; `routing.js` projects provider links into a graph and computes the trip. All ordinary files except the build wrapper are editable. `build.sh` copies the root client modules and CSS/HTML to dist and uses node --check; it preserves the mounted output directory. There is no backend app code or package dependency. New code can be bundled into these emitted files.

Ordinary reload retains imported inputs, selected stops, preference and saved trip. Explicit rebuild/reset_to_scene starts a fresh profile with the same provider imports and defaults. The report is read-only product evidence, not a test-results panel.
