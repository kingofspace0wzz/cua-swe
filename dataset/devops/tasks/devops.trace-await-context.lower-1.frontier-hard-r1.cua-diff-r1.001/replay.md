# Replay: devops.trace-await-context.lower-1.frontier-hard-r1.cua-diff-r1.001

Evaluator-owned. The agent-visible workspace contains the Continuum trace
console source and symptom-level instruction only. Protected schedules,
suspension points, trace/span identities, hidden profiles, verifier, patches,
and this replay are excluded.

## Controlled successor

This differential-frontier revision of
`devops.trace-await-context.lower-1.frontier-hard-r1.001` changes one axis:
`increase_concurrent_lifetime_disambiguation`. The parent was a certified
lower anchor: both GPT-6 Astra and Claude Fable 5 failed code-only and both
passed grounded screenshot CUA with byte-equivalent repairs that bind
`catalog.awaitContinuations` into the compatibility policy and make the
runtime-profile compiler consume it.

The successor preserves the async-context propagation failure and the source
topology (the agent-visible repo is byte-identical to the parent) while the
evaluator-owned runtime adds a second, concurrency-scoped compatibility
dimension:

- every protected profile now declares a manager-specific
  `delayedContinuationBinding` next to its `awaitContinuations` style
  (zone managers restore `creation-zone` bindings; the continuation-store
  manager restores `resume-snapshot` bindings);
- the overlapping scenarios stagger the two operation lifetimes so the
  earlier operation's post-await work partly completes before and partly
  after the newer operation starts (delayed completions);
- when the compiled runtime intercepts continuations correctly but leaves
  the continuation binding undeclared (or fixes a wrong value), delayed
  completions resume under whichever operation is *ambient* — the most
  recently started one — producing locally plausible but conflicting
  observations: zero orphans and a compatible-looking sequential state, yet
  cross-parented spans, foreign trace IDs, `crossed` transitions, and
  under-attached instrumentation coverage in the overlapping scenario.

A repair that only binds the continuation style — including both exact
predecessor lower-anchor CUA patches — now makes the first (sequential)
scenario look fully healthy on every surface and still fails: in all three
grading variants the overlapping scenario cross-parents every delayed
completion of the earlier operation under the newer operation's root. The
await-context mechanism, source architecture, symptom-level instruction
style, repair topology (compatibility policy plus runtime-profile compiler),
ancestry oracle, reset/unaffected controls, budgets, and negative families
are unchanged. Both predecessor CUA patches are retained byte-exactly as
protected negatives. No raw model trajectory informed this successor.

## Broken behavior

The capability catalog selects a zone-based context manager for the agent
session. The compatibility policy nevertheless declares native async
semantics, and the runtime-profile compiler hard-codes the same choice while
declaring no continuation binding. Pre-await spans remain under the operation
root, while hand-written and automatically instrumented spans created after
suspension become unrelated roots in both scenarios — the same first-screen
symptom as the parent.

The protected compatibility card is scenario-aware:

- while continuations are not intercepted it reports `incompatible` and the
  parent's manager-specific `awaitContinuations` recommendation;
- once interception is repaired but the binding is undeclared, the
  sequential scenario honestly reports `compatible` with a caveat that no
  overlapping lifetimes were contested — the decoy state;
- the overlapping scenario then reports `incompatible`, states that delayed
  completions adopt the ambient operation, shows the configured binding as
  `undeclared`, and directs the operator to declare the `continuation_scope`
  compiled for the runtime from the catalog's `delayedContinuationBinding`
  instead of leaving it undeclared or fixing one value, naming the manager's
  own binding. This declaration text exists only in the evaluator-owned
  engine and is observable only on the rendered card in that state.

Correlating four deterministic states is required: the broken sequential
start state, the overlapping broken state, the post-interception-repair
sequential decoy state, and the post-repair overlapping state whose delayed
completions conflict. Reload deterministically resets to the sequential
scenario; pre-await spans and the newer operation's spans are unaffected
controls that stay attached in every post-interception state.

## Gold behavior

`gold.patch` changes two production files:

1. `src/config/contextCompatibilityPolicy.js` declares both catalog
   declarations (`asyncSemantics: catalog.awaitContinuations` and
   `continuationScope: catalog.delayedContinuationBinding`).
2. `src/config/compileRuntimeProfile.js` consumes both policy fields.

Both changes are necessary. Binding only the continuation style reproduces
the predecessor patches and fails the overlapping scenarios; binding only the
scope leaves native semantics active on zone profiles. Equivalent
comprehensive repairs are accepted by the protected runtime, including
explicit propagation across every boundary (`explicit-all`), which is
compatible with every manager and binding. Fixed continuation targets, fixed
binding constants (`creation-zone` fails the store-manager variant), manual
parenting, and one-instrumentation repairs remain insufficient.

## Protected variants and verifier

The evaluator-owned engine holds visible and hidden operation names,
schedules, suspension boundaries, nested automatic instrumentation,
deterministic trace and span IDs, overlapping lifetimes with delayed
completions, semantic ancestry, and the manager-specific continuation and
binding compatibility matrix. The host proxies normal catalog, configure,
snapshot, and advance operations but not `/audit` or `/reset`.

For all three profiles — `visible` (zone), `hidden` (zone, renamed), and
`hidden-store` (continuation-store requiring native continuations and
resume-snapshot bindings) — the verifier drives the sequential and
overlapping scenarios through the browser. It requires exactly one root per
operation, every non-root span to descend transitively from its own root,
every protected automatic span to remain present, distinct traces for
overlapping operations, no cross-parentage, complete UI inventories, an
honest compatibility card in every state, deterministic scenario advance,
deterministic reload-reset back to the sequential topology, and no protected
audit exposure.

Manual hand-span parenting, one-auto-span repair, manual-plus-one-auto
repair, global-root reuse, visible-profile constants, renderer forgery, span
deletion, scenario suppression, fixed promise-chain or lowered targets, the
exact predecessor code-only patch, both exact predecessor lower-anchor CUA
patches, style-only repairs, scope-only repairs, fixed binding constants,
ambient binding constants, and interception-plus-manual-parenting hybrids
all fail the protected contract.
