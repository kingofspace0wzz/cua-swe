# Replay: Fleet Analytics Console linked-zoom

## Provenance

- Upstream: apache/echarts issue
  [#20071](https://github.com/apache/echarts/issues/20071), revision
  `30076aedcd7b7f65d8dd8e8d9ece46ce778133a3`, Apache-2.0.
- Implementation: behavior-derived clean-room fixture. ECharts' linked
  dataZoom broadcasts a toolbox rubber-band from one chart to sibling charts;
  #20071 is that the broadcast window must map correctly onto linked charts
  whose axis domains differ. The full ECharts render/option runtime is heavy,
  so the domain-mapping behaviour is reproduced in a clean-room canvas fleet
  console with the same driving-chart-to-linked-chart broadcast model and
  independent per-chart domains.

## Surface

A "Fleet Analytics Console": a large primary chart above a row of three
smaller linked panels. Each panel plots a metric across its own independent
reading range, and each panel header prints the visible-window read-out
(`lo – hi`) of the slice it is currently framed to. A toolbox above the charts
has a **Window zoom** button (arm it, then rubber-band a horizontal span on the
primary chart) and a **Reset** button.

## Harness-owned contract

`env/service.mjs` serves the active dashboard manifest over
`/api/workspace/manifest` (the static host forwards `/api/workspace/*` to it and
relays the opaque `x-workspace-link` header). Each served workspace
(`CONTRACT_VARIANT` = `alpha`, `beta`, `gamma`) gives its charts **different
domains** and a **different scripted rubber-band fraction**, and samples each
series **non-uniformly in x** so that "same fraction of the domain" and "same
sample index" no longer coincide. The manifest hands the console only the raw
per-chart series, each chart's domain, and the scripted gesture fraction — never
the resolved linked window, the mapping policy, or a per-chart target range.

## Broken behaviour

The broadcast reuses the primary chart's own framed data window verbatim on
every linked panel (`resolveLinkedWindow` → `rawWindow`). Because the linked
panels have different reading ranges, that raw window lands them on the wrong
stretch (and is clamped to their extent), so the panels no longer line up on
the moment framed on the primary chart.

## Expected (gold) behaviour

Each linked panel frames the stretch of **its own** range that corresponds to
the framed fraction of the primary chart's range. On every workspace the linked
read-outs then match `[domain_lo + f_lo·span, domain_lo + f_hi·span]` for that
panel's own domain and the served fraction `[f_lo, f_hi]`.

## Screenshot-only discovery

1. Read the active workspace title and note the four charts and their header
   read-outs (all showing their full range at load).
2. Arm **Window zoom** and rubber-band a span on the primary chart.
3. Read each linked panel's header read-out. Broken: the linked read-outs jump
   to numbers that do not lie within, or do not proportionally match, their own
   range — they copy the primary chart's numbers. Correct: each linked read-out
   shows the proportional slice of its own range.
4. The correct behaviour is only visible by interacting: source alone offers a
   raw-window copy, a raw-sample-index copy, and a per-domain map, and does not
   say which lands every panel on the corresponding stretch.

## Two source-plausible repairs distinguished by protected payloads

- **Map by domain fraction (gold):** normalize the framed fraction onto each
  panel's own domain. Matches the corresponding slice on all workspaces.
- **Copy the selected sample-index span (negative):** read each panel at the
  master's selected sample indices. Looks like a fix, but because sampling is
  non-uniform per chart, the sample at index *i* does not sit at fraction *i/n*
  of the domain, so the framed stretch is off on charts with different sampling
  — fails on all three workspaces.

## Verifier

`repo/verifiers/browser_check.py` starts each protected workspace on an
ephemeral port, forwards `/api/workspace/*`, loads the console, runs the scripted
rubber-band through the same code path a manual selection uses, reads each linked
panel's live rendered window from the DOM, and requires every linked panel to
frame the slice of its own domain that corresponds to the served fraction —
recomputed live, nothing hard-coded — on all three workspaces.

## Local reproduction

```
cd repo && npm run build
# start a workspace feed, then the static host pointed at it, or just:
python3 verifiers/browser_check.py   # runs all three protected workspaces
```

- Broken baseline: verifier fails (raw window copied onto mismatched domains).
- `git apply gold.patch`: verifier passes on all three workspaces.
- `git apply negative.patch`: verifier fails (sample-index copy mis-frames).
- `git apply _probes/hardcoded.patch`: pins a `[40%,70%]` slice; passes only the
  workspace whose fraction is `[0.4,0.7]` and fails the other two.
```
