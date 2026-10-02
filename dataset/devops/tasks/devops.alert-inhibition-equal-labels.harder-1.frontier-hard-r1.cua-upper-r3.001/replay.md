# Replay: devops.alert-inhibition-equal-labels.harder-1.frontier-hard-r1.cua-upper-r3.001

Evaluator-owned. The agent-visible workspace contains Sentinel source and a
symptom-level instruction only. Raw alerts, hidden profiles, the
scope-dimension registry values, the stamping-epoch policy, advisories,
routes, timeline phases, expected queues, verifier, patches, and this replay
are excluded.

## Broken behavior

The deployed rule compares alerts on two equality dimensions but does not
require any of them to be present. The protected engine follows Alertmanager
semantics: absent and empty values compare alike. A source without a
concrete value on the authoritative dimension therefore suppresses unrelated
services that also lack it, while legitimate suppressions — including pairs
that legitimately omit the other, absence-tolerant dimension — continue to
work.

The authoritative equality-label contract is evaluator-owned runtime state.
Unlike the parent, the registry no longer carries per-dimension rollout or
re-stamp status fields at all. Every registry dimension carries only an
opaque migration **epoch code** (visible profile: `cluster` under `M126`,
`environment` under `M112`; hidden renamed profile: `tenant` under `M131`,
`zone` under `M108`), a stale scope-taxonomy role, and a neutral note that
defers to the scope stamping runbook. The decisive mapping — which epochs
are **sealed** (a missing label is an eligibility violation, so the rule
must require it on both alerts) and which are still **stamping** (a missing
label is expected and matches as recorded) — is published only as the
raster pixels of the ops-docs runbook page rendered by the evaluator-owned
service (`/runbook`, proxied at `/api/runbook`, displayed in the console's
"Stamping runbook" panel):

```
EPOCH  STATE     MISSING LABEL
M108   STAMPING  EXPECTED
M112   SEALED    VIOLATION
M117   SEALED    VIOLATION
M121   STAMPING  EXPECTED
M126   STAMPING  EXPECTED
M131   SEALED    VIOLATION
```

The mapping is absent from repository source, comments, HTML, bundled
assets, client-visible JSON, accessibility metadata, and every other
machine-readable API field. Reading it requires the normal operator step of
looking at the rendered runbook page. The required dimension set is then
confirmed by the same cross-state behavioral evidence as the parent:

- **state 1 (initial batch)** matches every unrelated suppression by
  absence on both dimensions, so requiring either or both is locally
  consistent;
- **state 2 (arriving alerts)** wrongly holds an unscoped service that
  shares a **concrete** value on the stamping-epoch dimension with an
  unscoped source (killing any repair that requires that dimension) while
  a pair that omits the stamping-epoch dimension but shares a concrete
  sealed-epoch value must stay suppressed (killing require-all and every
  repair that requires the stamping-epoch dimension);
- **state 3 (partial resolution)** shows resolved sources releasing their
  legitimate targets while absence-matched suppression persists, rejecting
  stale-state and resolution-handling hypotheses;
- **state 4 (replay)** deterministically restores the initial batch, and
  the archive notification route delivers every active alert in every
  state, separating engine eligibility from delivery-layer tampering.

The hidden profile renames every alert and dimension, swaps the registry
order and the equality order, inverts the stale role decoy, and draws its
epochs from runbook rows the visible profile never exercises: its
authoritative dimension is sealed under `M131` and its absence-tolerant
dimension is still stamping under `M108`. Epoch codes give no usable
ordering signal (sealed: M112, M117, M131; stamping: M108, M121, M126), so
hard-coded labels, positional guesses, role predicates, guard-everything
sets, rollout/re-stamp field derivations (the fields no longer exist),
visible-epoch special cases, default-require and default-tolerate partial
tables, and numeric epoch cutoffs each fail at least one profile. Only the
complete published runbook table selects the correct guard set in both
profiles.

## Gold and equivalent behavior

The gold transcribes the published runbook table into the scope policy as a
per-epoch stamping map, derives `presenceDimensions` from registry entries
whose epoch is sealed, and makes the rule compiler consume it on both
sides. Both production files are necessary. Behaviorally equivalent
source-only or target-only presence guards are accepted;
`alternates/target-only-presence.patch` is retained as proof.

## Protected verification

Fresh visible and hidden engines each run all four timeline states. The
verifier requires exact protected queue, edge, and route signatures per
state, every alert present exactly once, only present-guard alerts
suppressed, complete queue/graph/comparison/route surfaces, complete
registry (including epoch codes), advisory, and runbook surfaces that agree
with the runtime catalog and the ops-docs render (the console must display
the authentic `/api/runbook` pixels, byte-identical to the service render),
deterministic advance through every state, exact replay equality between
the reset state and the initial state, an archive route that always equals
the active-alert count, and no host audit exposure. The exact predecessor
CUA patches (Fable 5's rollout/re-stamp field derivation, which now
compiles a require-everything guard set; GPT-6's hard-coded environment
label), the byte-identical parent gold (its rollout/re-stamp intersection
now compiles an empty guard set), the grandparent rollout-complete gold,
the re-stamp-only and never-re-stamped predicate variants, the stale
scope-role decoy, positional guesses, visible-name and visible-epoch
special cases, default-require and numeric-cutoff partial runbook tables,
partition-dimension deletion, rule deletion, missing-equality override,
renderer and runbook forgery, row deletion, and incident suppression
attacks all fail.
