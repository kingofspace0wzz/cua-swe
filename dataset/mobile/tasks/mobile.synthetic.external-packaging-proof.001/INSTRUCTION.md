# Repair Foldnote proof review

Foldnote is a mobile web packaging-proof review mockup. Review markers no longer stay correctly placed and oriented when switching between Flat sheet and Individual panel. Editing a marker on the sheet can move it to the wrong place, and reviews on one proof can replace those on another.

Repair this workflow. Marker coordinates, heading and panel-specific notes must remain consistent through panel/proof switching and ordinary reload. Both typed edits and tapping the artwork should work, and editing only a note must not move its marker. Preserve the original imported artwork and its report viewer. Use the two supplied proofs, not fixed screen targets or a lookup for a single layout.

The external evidence is available in the running app: **Source proof → Panel report**. The proof chooser exposes both imported attachments. Inspect the original drawing and the complete placement contract there; the symptom alone does not describe the intended interpretation.

You receive the full ordinary client source and build inputs. Proof artwork and placement reports are separate product inputs, imported only into the isolated running app by trusted setup. They are not missing source files or build dependencies. The standalone app starts with an empty inbox outside that prepared runtime. Both conditions use the same prepared external world; app observation is available only in the CUA condition.

Build with `sh build.sh`. All ordinary client files are editable; the build wrapper is protected. No dependencies or external network are needed. Scene: 400×800 CSS pixels, DPR 1, en-US, UTC. Use Save review before switching proof/panel. Ordinary reload retains saved reviews; rebuilding explicitly resets to a fresh imported scene. This is an original synthesized design mockup, not an actual packaging manufacturing specification.
