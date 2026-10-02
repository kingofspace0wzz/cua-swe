# Replay: devops.trace-clock-skew.lower-3.frontier-hard-r1.cua-upper-r6.001

Evaluator-owned. The agent-visible workspace contains the Spanline query
console and symptom-level instruction only. Raw capture sets, the
clock-authority registry, opaque filing-code provenance, the raster
calibration-board sheets, expected per-authority corrections, hidden
controls, protected adjustment audit, verifier, patches, and this replay are
excluded.

## Lineage and the single changed axis

Parent `devops.trace-clock-skew.lower-3.frontier-hard-r1.cua-upper-r5.001`
reached strict confirmation with GPT-6 CUA 0/3, but Claude Fable 5 passed one
clean screenshot-CUA round by reading the **machine-readable** catalog
metadata: its patch keyed on `capture.window === "before-reset"`,
`capture.status === "current"`, `capture.recordedBy`, and
`catalog.resetEvent.owner` — semantic fields any code path could consume
without interpreting a single pixel. The parent is therefore not a valid
upper anchor.

This successor changes exactly one axis:
`move_reference_pairing_authority_to_operator_calibration_pixels`. Every
semantic pairing and reset-authority field is removed from every
machine-readable channel:

- `resetEvent` (with its `owner`) becomes an opaque `transition` notice
  (`at`, `label`, `bulletin`) with **no crew or authority field**;
- `capture.window` / `capture.status` / `capture.recordedBy` /
  `capture.supersededBy` become opaque filing codes: a register token
  (`R-207` archive / `R-311` post-transition recheck), a disposition token
  (`D-41` / `D-17` / `D-63`), and a recording-crew token (`crew-04`,
  `crew-07`, `crew-08`, `crew-12`, `crew-26`);
- titles, advisories, and identifiers are re-coded to carry only those
  codes (`checkout-r131`, `invoice-r204`, …) plus neutral facts; a
  protected-verifier scan asserts the payload channel contains no semantic
  vocabulary (`superseded`, `standing`, `current`, `before/after`, `owner`,
  `reference`, …);
- the **complete mapping** — which register is the pre-transition archive
  and the sanctioned pairing rule (sheet 1), which crew code holds reset
  authority and which crews never provide timing references (sheet 2), and
  which disposition is standing versus withdrawn versus sensor recheck
  (sheet 3) — is published only on the evaluator-owned raster **operator
  calibration board**, three deterministic PNG sheets paged inside a normal
  console panel, corroborated by the regenerated raster decision guide;
- to keep the mapping necessary rather than statistically inferable, each
  broken workload now has a **fourth** replay candidate: a standing
  (`D-41`) audit-desk record with a wrong magnitude, and the hidden feed
  workload's withdrawn record is filed by an audit desk. The constructor
  invariant matrix (18 machine-only selectors: recency, order,
  catalog position, disposition-only, crew multiplicity, withdrawn-sibling
  crew, crew extremes, delta magnitude, sensor agreement, violation
  cleanliness, crew exclusion, …) shows no rule that ignores the board
  selects the reference in all four workloads across both profiles.

Everything else is held constant: the trace-clock-skew failure family, the
Spanline source substrate (the only agent-visible additions are the generic
calibration-board panel, view, styles, and proxy allowlist entry — the
repaired files `adjustmentPolicy.js`, `query.js`, `compileAdjusters.js` and
every other source file are byte-identical to the parent, so every protected
predecessor patch applies cleanly), the dedupe/sort upstream
transformations, the maintenance replay semantics and correction magnitudes
(rack +600, rack-b +400 visible; pod −500, pod-y −320 hidden), root-span
invariance, matched-span adjustment limits (`maxAdjustmentMs`), symptom-only
instruction style, deterministic exact-geometry oracle, reset and unaffected
controls, custody policy, screenshot-only observation channel, and all agent
budgets.

## Broken behavior

The query chain only deduplicates and sorts spans; it performs no clock
correction. The console opens with the checkout capture (rack authority
`tempo-rack-a` = `app-a`+`db-a` leads its gateway) beside the orders capture
(`db-b`'s cache lookup pokes out of `app-b`'s list span — the ambiguous
boundary). All replays render normally except for small residual violations
on withdrawn partial-step records. The shared-clock flagged pair shows the
same `side-c` violation in both records with an explicit runtime advisory
naming `crew-07`.

## Deterministic states and decision-changing observations

1. Launch: opposite-sign archived cards, host chain, raster playbook,
   calibration board on sheet 1, and the checkout capture in every panel.
2. Board states: sheets 1→2→3 page deterministically (wrap and step-back
   verified) and the board stays readable across archive, replay, control,
   and reselection states.
3. Selector states: each of fourteen visible captures re-evaluates through
   the live pipeline; reselecting a capture resubmits deterministically
   identical geometry (reset/repeated-action control).
4. Replay candidates, the aligned pair, and the flagged pair are unaffected
   zero-shift controls.
5. Hidden profile: renamed hosts, authorities, services, identifiers,
   opposite signs, different magnitudes, rotated ambiguity topology,
   reordered candidate timestamps, and reassigned decoy crews behave
   identically under gold.

Decision-changing observations:

- Host notes group `app-a`/`db-a` (and hidden `worker-x`/`sql-x`) under one
  authority: correction unit is the authority group.
- Selecting two replays of one workload shows their reported times disagree
  while services, operations, hosts, durations, and roots match: signature
  matching cannot select the reference, and the reference delta still
  exceeds the visible boundary overhang, so boundary fitting stays wrong.
- Titles and advisories carry only filing codes; the calibration board's
  three sheets are the only place those codes are defined, so the pairing
  decision requires reading the raster pixels: sheet 1 fixes the register
  pairing, sheet 2 fixes the reset-authority crew, sheet 3 fixes the
  standing/withdrawn/sensor dispositions. All three are needed: two
  standing replays compete in every lane (crew-12 vs an audit desk), the
  withdrawn record is the newest hidden invoice record, and the sensor
  recheck is filed by the same crew code the unaffected flagged control
  names.
- Comparing the board-designated replay with the broken capture per
  authority gives the exact owner and magnitude; the ambiguous capture's
  violating leaf is byte-identical while its parent authority moves.
- The aligned pair is byte-identical and the flagged violation persists
  across the transition: persistent boundaries are instrumentation, and
  zero-delta authorities must not move.

## Gold behavior

`gold.patch` changes four production files:

1. `src/config/adjustmentPolicy.js` enables calibration-reference shifting.
2. `src/controllers/query.js` resolves the evaluated capture's
   board-designated replay from the opaque catalog filing codes and loads it
   as the reference.
3. `src/trace/calibrationReference.js` (new) selects the unique
   post-transition replay of the workload filed with the standing
   disposition by the reset-authority crew (both learned from the raster
   board), matches spans across the pair by service, operation, and host,
   derives one coherent replay delta per time authority, verifies duration
   equality, and translates every span of each nonzero-delta authority by
   its bounded delta.
4. `src/trace/compileAdjusters.js` registers that adjuster between
   deduplication and sorting.

The filing-code constants in gold are exactly the mapping the board
publishes in pixels; they appear nowhere in the agent workspace or in any
machine-readable payload. Equivalent runtime-derived repairs that compose
the same board mapping are accepted (per-matched-span substitution from the
board-designated replay produces identical geometry).

## Protected verifier

The service returns ordinary raw captures and records adjusted spans
submitted by the application; it independently computes expected geometry
from the protected authority registry. For every capture in visible and
hidden profiles the verifier requires exact submitted geometry; unchanged
inventory, parentage, services, operations, hosts, durations, and roots; one
coherent expected shift per authority; byte-stable zero-shift controls
(every replay candidate, aligned pair, flagged pair); the ambiguous card's
non-owner span unmoved; at least four overlapping replay candidates per
broken workload spanning three crews with withdrawn and sensor-recheck
filings and two competing standing replays, with exactly one standing
reset-authority replay whose deltas equal the protected correction while
every other candidate disagrees; a machine-channel semantic-leak scan over
catalog, capture metadata, titles, identifiers, and advisories; an opaque
transition notice with no crew field; three deterministic board sheets with
deterministic paging that stay readable across archive, replay, control,
and reselection states; rendered titles carrying register, disposition, and
crew codes and advisories naming crew codes; corrected boundary and
translated-span counts; the flagged violation persisting across the
transition with its crew code recurring on a candidate of every broken
workload; a deterministic reselection resubmission; the raster playbook in
the first viewport; and no protected audit exposure on the application host
(672 checks per full run).

## Documented negative semantics

- `negative.patch` (canonical, inherited duration clamp): resizing to the
  parent changes host-measured durations; fails duration and geometry
  checks.
- `negatives/fable5-successful-parent-cua.patch` (REQUIRED exact parent
  confirmation CUA bytes, sha256 53a3b4d5…): keys on the removed semantic
  metadata (`capture.window`, `capture.status`, `capture.recordedBy`,
  `resetEvent.owner`); it selects no reference in either profile and
  submits uncorrected geometry (22 checks fail — same signature as no-op).
- `negatives/parent-gold-semantic-metadata.patch` (exact parent gold bytes,
  sha256 21355c5e…): the same semantic-metadata selector topology; selects
  no reference and fails identically.
- `negatives/register-first-recapture.patch` (single-window pairing): first
  same-workload recheck-register record; picks the withdrawn partial step.
- `negatives/standing-disposition-first.patch`: disposition-only selection;
  picks the audit desk's standing record in the orders lane.
- `negatives/authority-crew-earliest.patch`: crew-only selection; picks the
  withdrawn crew-12 record.
- `negatives/register-latest-recapture.patch`: recency selection; picks the
  audit or withdrawn record depending on lane.
- `negatives/flagged-crew-exclusion-latest.patch`: excludes the flagged
  control's crew and takes the newest remaining record; picks audit-desk
  decoys.
- `negatives/hardcoded-visible-reference-ids.patch`: literal visible-profile
  id map; the hidden profile has different identifiers and stays broken.
- `negatives/origin-normalize-shift.patch`: translates whole traces
  (including roots) to a zero origin; fails root-geometry and control
  byte-stability checks.
- Inherited parent negatives, all byte-identical and re-certified against
  the successor: the grandparent GPT-6 confirmation CUA patch
  (`gpt6-successful-parent-cua.patch`, title-regex and
  signature-match pairing — the title vocabulary no longer exists),
  `parent-gold-supersession-blind.patch`, `latest-recapture.patch`,
  `current-first-recapture.patch`, `resync-id-pattern.patch`,
  `owner-earliest-recapture.patch` (all key on removed fields or renamed
  identifiers and select no reference),
  `gpt6-successful-lower-anchor-cua.patch` and
  `fable5-successful-lower-anchor-cua.patch` (boundary-fit owner and
  magnitude), `parent-gold-boundary-fit.patch`, `root-boundary-only.patch`,
  `reversed-reference-shift.patch`, `gpt6-successful-code-only.patch`
  / `predecessor-gpt6-successful-code-only.patch`,
  `fable5-successful-code-only.patch` /
  `predecessor-fable5-successful-code-only.patch`,
  `host-coherent-shift.patch`, `subtree-shift.patch`,
  `offending-span-only.patch`, `global-shift.patch`,
  `renderer-forgery.patch` (display-only; submitted geometry unchanged),
  `trace-deletion.patch` (selector and submission coverage fail),
  `visible-host-special-case.patch` (hard-coded host constants).
