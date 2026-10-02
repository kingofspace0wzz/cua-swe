# Replay: v3.jupyterlab-shiftclick-cellselect.001

Behavior-derived clean-room reproduction of jupyterlab/jupyterlab#19243
("Fix Shift-click cell selection after editor text selection"), pinned to the
broken base `c92f5efa1285d4e091f8a73a6a661439ca347670`.

## Layout

- `repo/` — agent-visible product. A minimal notebook surface whose mousedown
  selection handler (`src/notebook.mjs`) mirrors JupyterLab's
  `Notebook._evtMouseDown` at the broken revision, including the coarse guard
  that blocks cell range selection whenever any text is selected.
- `env/service.mjs` — evaluator-owned scene feed. Delivers the five protected
  notebook documents (cell kinds and output DOM, including a shadow-DOM widget
  output). Not visible to the agent.
- `runtime-contract.yaml` — protected staging policy and the decisive edge.
- `gold.patch` — the region-aware repair mirroring PR#19243.
- `negative.patch` — a realistic partial repair that treats only the output
  area as a browser-owned text region and forgets rendered markdown inputs.
- `_probes/source_analogue.patch` — the strongest source-only generalization
  ("anything outside a code editor is a browser text selection").
- `repo/verifiers/browser_check.py` — deterministic behavioral verifier over
  five protected payloads.

## Run

```bash
cd repo
npm install --offline
node build.mjs
# app + scene feed are launched by the verifier for gate replay:
python3 verifiers/browser_check.py    # exit 0 == PASS
```

To run the product manually:

```bash
node env/../env/service.mjs --host 127.0.0.1 --port 4270 &
CUA_SWE_EXTERNAL_SERVICE_ORIGIN=http://127.0.0.1:4270 \
  node repo/server.mjs --host 127.0.0.1 --port 4173
# open http://127.0.0.1:4173/?doc=A  (also B, C, D, E)
```

## Gates

```bash
bash _gates/run_gates.sh    # 10 pass / 0 fail
```

## Protected payloads

| Payload | Selection anchor | Shift-click target | Expected |
| --- | --- | --- | --- |
| A | code editor | other cell prompt | extend cell range |
| B | output area | same output | browser text selection (no cell range) |
| C | rendered markdown | same rendered markdown | browser text selection |
| D | shadow-DOM output | same shadow output | browser text selection |
| E | output area | DIFFERENT cell prompt | extend cell range |

Broken build fails A and E (any selection blocks the cell range). The negative
repair fails C (rendered markdown not treated as a text region). The source-only
analogue fails E (a Shift-click on a prompt while output text is selected must
still extend the cell range; the anchor-only rule leaves it to the browser).
Only the gold region-aware repair passes all five.

## Behavioral evidence

`_probes/broken_shot/payloadA_after_shiftclick.png` and
`_probes/gold_shot/payloadA_after_shiftclick.png` show the visible difference:
after selecting editor text and Shift-clicking a later cell's prompt, the broken
build highlights only the clicked cell, while the gold build highlights the full
range of cells.
