# Replay

Open Draft Composer and read the active workspace name and the expanded
“Where you left off” note. The note describes a location inside the rendered
draft without exposing a document offset. The draft is a real Tiptap editor.
Use Tab to focus the editor, or use Alt+R to return focus after moving
elsewhere, and observe the red caret marker.

The broken build always resumes at document start. A correct repair resolves the
saved bookmark through the live Tiptap/ProseMirror layout (`view.posAtCoords`)
so the caret lands on the line and near the column described by the active
workspace. A plausible legacy-offset repair lands inside the document but on a
different wrapped line or column for the protected workspaces.

The deterministic verifier rebuilds the browser bundle from source (so the
patched code and the real Tiptap runtime are exercised), then drives three
protected workspace payloads with different prose, wrapping, and sets of
same-shape pixel anchors. Exactly one candidate point remains on a rendered
glyph line after the current wrapping; the other candidates fall in paragraph
gaps created by an earlier layout. It derives the target from live rendered
ProseMirror character geometry and asserts a live Tiptap Editor is present. No
single anchor index or hard-coded position can pass all payloads.

Runtime dependency: Tiptap 2.11.5 (@tiptap/core, @tiptap/pm,
@tiptap/extension-document, @tiptap/extension-paragraph, @tiptap/extension-text),
bundled with esbuild 0.24.2 into dist/app.bundle.js. Run `npm install` then
`npm run build`; the build aborts if any pinned package is missing.

For a local replay, run `npm install`, `npm run build`, start the declared
server command from `task.yaml`, and then run
`python3 verifiers/browser_check.py`.
