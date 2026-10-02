# Replay — v3.quill-paste-scroll-roundtrip.002

Upstream: slab/quill issue #1374 (viewport jumps after a paste that changes
document height). Revision 539cbffd0a13b18e9c65eb84dd35e6596e403158,
BSD-3-Clause. This is a targeted fixture on the upstream Quill editor: the
pinned `quill` 2.0.3 package is installed from npm, imported by the app entry,
bundled by esbuild, and loaded by the browser. The paste-then-scroll roundtrip
is reproduced with genuine Quill edits on a collaborative reading surface
(Threadloop) whose settling policy is author-conditioned and owned by the
harness.

## Surface and mechanism

The reading surface is a real Quill editor (`new Quill`, snow theme, read-only)
with a presence/status collaboration bar above it. The shared document is loaded
as a Quill Delta (one line per block; headings carry Quill's `header` format).
One pending update (a pasted paragraph) is announced in the bar together with
who authored it. Applying the update performs a genuine Quill edit
(`quill.updateContents` on a Delta) that changes the document height, and the
paste pipeline must settle Quill's scroll region (`.ql-editor`). Agent-visible
source (`repo/src/pasteFlow.js`) exposes three neutral settle strategies — keep
the raw offset, reveal the inserted block, or re-anchor the reading block — and
one blanket selection that ignores the author. It does not encode which strategy
belongs to which author. That mapping is the harness-owned contract.

## Lifecycle from a clean workspace

```
cd repo
npm install                     # installs quill 2.0.3 + esbuild 0.23.1
npm run build                   # node build.mjs — esbuild bundles the app,
                                # asserts quill is pulled into the bundle,
                                # and copies quill.snow.css into dist/
# harness starts env/service.mjs on {service_port}
CUA_SWE_EXTERNAL_SERVICE_ORIGIN=http://127.0.0.1:{service_port} \
  node server.mjs --host 127.0.0.1 --port {app_port}
# open http://127.0.0.1:{app_port}
```

The static server proxies `/api/session` to the harness service. Chromium needs
a writable `TMPDIR`; the local deterministic run used `TMPDIR=/tmp` (the system
default temp mount rejects `mkdtemp` with `EPERM` — an environment quirk, not a
task defect).

## Screenshot-only discovery sequence

1. Read the collaboration bar: it names the author of the pending update
   ("You added a paragraph." vs "Priya added a paragraph.") and the
   reading-session note describes where you are in the document.
2. Note where the reader is currently parked.
3. Apply the update with the **Apply update** control or the Alt+P shortcut.
4. Observe the viewport: for the reader's own update the new paragraph should
   come into view; for a collaborator's update your reading position should not
   move. The broken build does neither correctly.

## Protected sessions (harness-owned)

Four sessions delivered through `CONTRACT_VARIANT`, absent from agent source:

| variant | space           | author | parked | paste index | correct settling                 |
|---------|-----------------|--------|--------|-------------|-----------------------------------|
| a       | Support triage  | self   | top    | far below   | reveal the reader's own insertion |
| b       | Launch notes    | self   | mid    | far below   | reveal the reader's own insertion |
| c       | Incident review | peer   | mid    | above       | keep the reader's place fixed     |
| d       | Roadmap sync    | peer   | deep   | above       | keep the reader's place fixed     |

## Automated replay evidence

Gate runner: `_gates/run_gates.py` (extended probe below). Verifier:
`repo/verifiers/browser_check.py` measures live layout only; no expected scroll
offset or pixel constant is embedded. Before judging behavior the verifier
rebuilds the bundle from the source under test and runs a framework gate that
asserts the real Quill runtime drives the surface (Quill code in the served
bundle plus a live `.ql-container`/`.ql-editor` DOM produced by Quill).

- **required_files / schema / no_source_leak / clean_install / build**: PASS.
- **framework_dependency**: PASS. `quill` is pinned to 2.0.3, resolves in
  `node_modules`, and is linked into `dist/app.bundle.js` (Quill's `ql-editor`,
  `ql-container`, and blot vocabulary appear in the served bundle).
- **broken_fails**: all four sessions fail. self insertions stay off the fold
  (inserted top 686 / 815, region 460); peer anchors shift (49.9→126.5,
  69.9→146.5) as the insertion above pushes the reader down.
- **gold_passes**: all four pass. self insertions land centered in view
  (inserted top ~199); peer anchors hold (49.9→49.5, 69.9→69.5).
- **negative_fails**: blanket "reveal" passes self but fails peer — the reading
  anchor is scrolled away to the insertion (49.9→599.5, 69.9→793.5).

## Repair underdetermination

Two source-plausible blanket repairs each fail the opposite author:

- blanket **reveal** (the shipped negative): passes self, fails peer.
- blanket **reanchor**: passes peer, fails self (verified out of band:
  self insertions stay off-fold at 686 / 815).

Only an author-conditioned mapping — the reader's own paste follows the
insertion, a collaborator's paste preserves the reading place — passes every
session. That mapping is not present in agent-visible source, comments,
filenames, or the verifier as a copyable constant; it is recoverable only by
reading the presence/status chrome and watching the viewport before and after
applying the update.

## Hard-coded-answer probe

`probe_hardcoded.py` re-runs the verifier against a candidate that ignores the
author and returns any single blanket strategy (`raw`, `reveal`, `reanchor`).
Every single-answer candidate fails at least one protected session, so no
hard-coded constant or blanket rule can pass the suite.

## Quill runtime evidence

The reading surface is genuinely Quill-driven, not a wrapper or a mention:

- `repo/src/editor.js` imports `Quill from 'quill'`, constructs
  `new Quill(...)`, loads the document with `Quill.import('delta')`, and inserts
  the pasted block via `quill.updateContents(delta, 'api')`.
- `repo/src/pasteFlow.js` settles the scroll on Quill's editor root
  (`quill.root`, the `.ql-editor` scroll container).
- `repo/build.mjs` fails the build if `quill` is not installed or is not pulled
  into the app bundle graph; it also ships Quill's own `quill.snow.css`.
- `repo/verifiers/browser_check.py` rebuilds from source, then asserts the
  served bundle contains Quill and the live DOM is a Quill editor before judging.
- The `_gates/run_gates.py` `framework_dependency` gate independently checks the
  pin, the installed package, and the import footprint in the runtime bundle.
