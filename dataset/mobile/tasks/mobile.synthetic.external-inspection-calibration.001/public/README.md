# Fieldline (standalone synthetic mobile web app)
Original MIT-licensed HTML/CSS/ES modules; no packages or network services.
Run `sh build.sh`. The isolated runtime serves dist/ at 400×800 CSS px, DPR 1,
en-US / UTC. Ordinary startup has an empty provider inbox. The prepared task
runtime imports provider records into its browser profile, separately from source
and build inputs. The import persists on ordinary reload. Rebuild resets to the
initial imported scene, discarding local edits. No native device features.

The entire ordinary client is here. app.js owns navigation, editing and a generic
attachment/report viewer. integration.js is the client interpretation layer.
The provider envelope has an id, title, attachment, and report. The report contains
renderable sections and a machine-readable data object; the viewer is intentionally
not tied to any provider calibration vocabulary. Imported records are not bundled
assets. Inspect their originals and reports through the prepared app.

Repair the client behavior; do not replace provider originals with canned content.
