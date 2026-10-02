# Replay: devops.trace-clock-skew.lower-3.frontier-hard-r1.001

Evaluator-owned. The agent-visible workspace contains the Spanline query
console and symptom-level instruction only. Raw trace profiles, the
clock-authority registry, expected per-authority corrections, hidden controls,
protected adjustment audit, verifier, patches, and this replay are excluded.

## Lineage and the single changed axis

Parent `devops.trace-clock-skew.lower-3.001` was solved code-only by both
GPT-6 Astra and Claude Fable 5. Both attacks inferred the complete repair from
source alone: the `crossHostMode: "observe"` policy literal, the catalog
`maxAdjustmentMs`, and the host-chain heading that narrated per-host coherent
shifting. Their patches implement bounded per-host translation derived purely
from parent/child geometry.

This successor changes exactly one axis: `externalize_decisive_truth`. The
authoritative clock-domain and correction truth now lives in evaluator-owned
runtime state. Hosts belong to time authorities (machines that share one
clock source). The correction unit is the authority group, not the host:

- every span from every host under one skewed authority receives one
  coherent shift, even a host whose own boundary geometry looks aligned or
  suggests a smaller shift;
- a violating cross-host boundary whose two hosts share one authority is an
  instrumentation defect and must stay reported as-is, exactly like the
  retained same-host control.

The authority registry is served only by the protected trace service and is
observable through normal operator surfaces: per-host operator notes in the
Host comparison panel, instrumentation advisories in the Warnings panel, and
the protected first-viewport raster playbook. The agent-visible source renders
`hostNotes` and `advisories` generically and never names the authority
concept; the per-host coherence narration was removed from the host-chain
heading because it is no longer true. Everything else is held constant: the
trace-clock-skew failure family, the Spanline substrate, the dedupe/sort
upstream transformations, the symptom-only instruction style, the deterministic
exact-geometry oracle, and the reset plus unaffected controls.

## Broken behavior

The query chain only deduplicates and sorts spans; it performs no clock
correction. In one visible trace the checkout rack (hosts `app-a` and `db-a`,
one shared authority) leads its gateway by 600ms, so its charge span starts
before the root. In another, the orders rack (`app-b` and `db-b`) trails its
gateway by 300ms, so its span ends after the root while its `db-b` span
happens to look contained. A shared-clock control trace shows a `side-c`
proxy-handshake span outside its `edge-c` parent with an explicit runtime
advisory that the two hosts share one time authority. Aligned cross-host and
same-host malformed controls are retained from the parent.

## Deterministic states and decision-changing observations

1. Launch state: opposite-sign leading and trailing comparison cards, host
   chain, raster playbook, and the checkout trace in every panel.
2. Selector states: each of four visible traces re-evaluates through the live
   pipeline and re-renders every surface; reselecting a trace resubmits
   deterministically identical geometry (reset control).
3. Hidden profile: renamed hosts, authorities, services, depths, signs, and
   magnitudes behave identically under gold.

Decision-changing observations:

- Host comparison notes (runtime values) group `app-a`/`db-a`, `app-b`/`db-b`,
  `edge-c`/`side-c` under one authority each. This flips the repair unit from
  per-host to per-authority-group: `db-a` must move 600 (not the 100 its own
  boundary suggests) and `db-b` must move -300 (although it looks contained).
- The shared-clock advisory plus the unmoved `side-c` expectation flips the
  correction predicate from "different host" to "different time authority".
- The raster playbook sequences parent-first evaluation against displayed
  parent geometry, whole-group translation, duration preservation, and
  control protection; the notes carry membership and the playbook carries
  policy, so no single surface exposes the complete contract.

## Gold behavior

`gold.patch` changes three production files:

1. `src/config/adjustmentPolicy.js` enables bounded authority shifting.
2. `src/trace/authorityAlignment.js` adds a new implementation that walks
   spans in parent order, skips boundaries whose two ends report through one
   time authority, infers a bounded correction from the displayed parent
   geometry of each violating cross-authority boundary, applies one shift to
   every span in that authority group, and preserves start/end durations.
3. `src/trace/compileAdjusters.js` registers that implementation between
   deduplication and sorting.

No complete helper exists in the broken source. The algorithm must be
implemented and must consume the runtime authority identity carried by the
protected trace payload (or equivalent runtime-derived grouping). It moves
neither aligned cross-host data, nor shared-authority instrumentation data,
nor same-host data, and respects the profile's maximum adjustment.

## Protected verifier

The service returns ordinary raw traces and records adjusted spans submitted
by the application. It independently computes expected geometry from the
protected authority registry. For every trace in visible and hidden profiles,
the verifier requires:

- exact submitted geometry;
- unchanged span inventory, parentage, services, operations, hosts, and
  durations;
- unchanged root geometry;
- one coherent expected shift for every time authority;
- byte-stable control traces (all-zero expected shifts stay reported as-is);
- rendered host notes that name each host's runtime authority and rendered
  runtime advisories (screenshots agree with scored behavior);
- every trace selected through the browser;
- the protected raster playbook loaded in the first viewport;
- protected audit inaccessible from the application host.

## Documented negative semantics

- `negative.patch` (duration clamp): clamping to the parent changes measured
  durations; fails duration and exact-geometry checks.
- `negatives/gpt6-successful-code-only.patch` (exact predecessor
  bytes, sha256 a4217d53...): bounded per-host feasible-interval shifts; gives
  `db-a` 100 instead of the authority shift 600, leaves `db-b` at 0 instead of
  -300, and moves the shared-authority `side-c`/`mesh-z` instrumentation spans.
- `negatives/fable5-successful-code-only.patch` (exact predecessor bytes,
  sha256 e3e34d1a...): per-host BFS minimal-skew translation; same authority
  co-movement and instrumentation-control failures.
- `negatives/host-coherent-shift.patch` (the parent task's gold): per-host
  parent-ordered whole-host shifting; correct unit in the parent, wrong unit
  here for the same documented reasons.
- `negatives/subtree-shift.patch`: translates whole descendant subtrees; drags
  the independent `mq-a`/`log-x` children with the corrected group and moves
  instrumentation spans.
- `negatives/offending-span-only.patch`: moves only the violating span and
  leaves same-authority peers and descendants behind.
- `negatives/global-shift.patch`: one constant trace-wide shift breaks
  opposite-sign traces and every control.
- `negatives/renderer-forgery.patch`: display-only clamping leaves submitted
  geometry wrong.
- `negatives/trace-deletion.patch`: filters skewed traces from the catalog;
  fails submission and selector coverage.
- `negatives/visible-host-special-case.patch`: hardcoded visible host
  constants; corrupts the aligned `app-a` control and fails renamed hidden
  hosts.
