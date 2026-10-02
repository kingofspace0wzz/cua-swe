# Replay: devops.alert-inhibition-equal-labels.harder-1.frontier-hard-r1.001

Evaluator-owned. The agent-visible workspace contains Sentinel source and a
symptom-level instruction only. Raw alerts, hidden profiles, the
scope-dimension registry values, advisories, arrivals, expected queues,
verifier, patches, and this replay are excluded.

## Broken behavior

The deployed rule compares alerts on two equality dimensions but does not
require any of them to be present. The protected engine follows Alertmanager
semantics: absent and empty values compare alike. A source without a concrete
placement value therefore suppresses unrelated services that also lack that
placement, while legitimate suppressions — including pre-rollout pairs where
both alerts legitimately omit the partition label — continue to work.

The authoritative equality-label contract is evaluator-owned runtime state
and is split across normal operator surfaces:

- the scope-dimension registry classifies each equality dimension
  (`placement` versus `partition`) and its note states that only alerts with
  a concrete placement participate in suppression;
- the incident advisory and the per-dimension label comparisons state that
  pre-rollout alerts omit the partition label and that matching by absence
  between two such alerts is expected and must keep working;
- the queues, edges, and arriving batch show which suppressions are
  unrelated, which are legitimate, and that the boundary generalizes to
  unseen alerts.

No agent-visible source file states which dimensions require presence. The
visible profile guards `cluster` (registry order places the placement
dimension first); the hidden profile renames every alert and dimension,
guards `tenant`, and places the partition dimension first, so positional,
name-based, and guard-everything repairs all fail at least one profile.

The arriving batch adds an unseen unscoped service alert that must fire and
an unseen pre-rollout legacy pair that must stay suppressed. Excluding only
the initially visible services remains partial. Disabling the rule, guarding
every equality dimension, or dropping the partition dimension are all wrong
because intended suppression — including partition separation and legacy
absence-matching — must survive.

The decisive screenshot paths are:

- `incident.label` distinguishes initial and arriving batches;
- `summary.firing-count`, `summary.suppressed-count`, and
  `summary.unscoped-count` expose queue changes;
- `advisory.text` states the pre-rollout absence-matching expectation;
- `dimension.name`, `dimension.role`, and `dimension.note` expose the
  registry classification that gates eligibility;
- `alert.scope-state` and `alert.inhibited-by` expose held-alert ownership;
- `edge.source` and `edge.target` expose protected suppression causality;
- `comparison.dimension`, `comparison.role`, and `comparison.state`
  distinguish concrete equality, recorded partition equality, expected
  absence-matching, and absent/empty placement equality;
- `rule.required-source-labels` and `rule.required-target-labels` expose the
  deployed eligibility guards.

## Gold and equivalent behavior

The gold derives the presence-guard set in the scope policy from the runtime
registry entries whose role is `placement` and makes the rule compiler
consume it on both sides. Both production files are necessary. Behaviorally
equivalent source-only or target-only presence guards are accepted;
`alternates/target-only-presence.patch` is retained as proof.

## Protected verification

Fresh visible and hidden engines each run an initial incident and an arriving
batch. The verifier requires exact protected queue and edge signatures, every
alert present exactly once, only present-placement alerts suppressed,
complete queue/graph/comparison surfaces, complete registry and advisory
surfaces that agree with the runtime catalog, deterministic advance, and no
host audit exposure. The recycled predecessor code-only patch
(guard-every-equality-dimension), positional first-dimension guessing,
visible-name and visible-scope special cases, partition-dimension deletion,
rule deletion, missing-equality override, renderer forgery, row deletion, and
incident suppression attacks all fail.
