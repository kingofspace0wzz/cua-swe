# Replay: devops.trace-await-context.lower-1.frontier-hard-r1.001

Evaluator-owned. The agent-visible workspace contains the Continuum trace
console source and symptom-level instruction only. Protected schedules,
suspension points, trace/span identities, hidden profiles, verifier, patches,
and this replay are excluded.

## Controlled successor

This frontier-hard revision of `devops.trace-await-context.lower-1.001`
changes one axis: `add_hidden_runtime_variants`. The parent was solved
code-only by GPT-6 Astra, which guessed the conventional `"lowered"`
compile target and hard-coded it into the compatibility policy while making
the runtime-profile compiler consume the policy. The successor adds
evaluator-owned runtime compatibility variants that distinguish the required
async-context behavior:

- every protected profile now declares a manager-specific continuation style
  (`awaitContinuations`) in its capability catalog;
- the two zone-manager profiles (visible and hidden) still require lowered
  (or promise-chain) continuations;
- a new store-based hidden profile uses a `continuation-store` manager that
  intercepts native await continuations directly and loses context when
  async work is lowered to scheduler callbacks, so it requires `native`
  continuations.

A fixed compile target can no longer satisfy every variant. The await-context
mechanism, source architecture, symptom-level instruction, repair topology
(compatibility policy plus runtime-profile compiler), ancestry oracle,
reset/unaffected controls, and negative families are unchanged. The exact
predecessor code-only patch is retained as the protected negative
`negatives/gpt6-code-only.patch`. No raw model trajectory informed
this successor.

## Broken behavior

The capability catalog selects a zone-based context manager for the agent
session. The compatibility policy nevertheless declares native async
semantics, and the runtime-profile compiler hard-codes the same choice
instead of consuming the declaration. Pre-await spans remain under the
operation root, while hand-written and automatically instrumented spans
created after suspension become unrelated roots.

The first scenario makes the suspension boundary visible without concurrency.
Changing only displayed indentation or manually parenting named application
spans cannot repair protected automatic HTTP, timer, storage, rpc, cache,
queue, lock, bus, and scheduler spans. The second scenario overlaps two
operations, rejecting a single mutable global root that would cross-parent
one operation under another.

The protected compatibility card reports the configured manager, compiled
async semantics, suspension outcome, and — decisively — that continuation
support is manager-specific and must follow the `awaitContinuations` style
declared by the runtime catalog instead of a fixed target. This declaration
text exists only in the evaluator-owned engine and is observable only on the
rendered card.

The runtime contract names the decisive screenshot paths:

- `compatibility.recommendation` states the manager-specific catalog
  declaration that the compiled semantics must consume;
- `scenario.label` distinguishes the sequential and overlapping runs;
- `span.trace-id`, `span.parent-id`, and `span.operation` expose raw lineage;
- `transition.status` identifies the suspension boundaries that lose context;
- `instrumentation.kind` exposes multiple protected automatic span families;
- `summary.trace-count`, `summary.orphan-count`, and `waterfall.depth` expose
  topology across sequential and overlapping scenarios.

## Gold behavior

`gold.patch` changes two production files:

1. `src/config/contextCompatibilityPolicy.js` declares the catalog's
   manager-specific continuation style (`catalog.awaitContinuations`) instead
   of a hard-coded target.
2. `src/config/compileRuntimeProfile.js` consumes that declaration.

Both changes are necessary. Binding the declaration while retaining the
hard-coded compiler leaves native semantics active on zone profiles. A
compiler that consumes the still-broken declaration faithfully reproduces the
context loss.

Equivalent comprehensive repairs are accepted by the protected runtime,
including explicit propagation across every boundary (`explicit-all`), which
is compatible with every manager. Fixed compile targets (`lowered` or
`promise-chain`), partial manual parenting, and one-instrumentation fixes
remain insufficient.

## Protected variants and verifier

The evaluator-owned engine holds visible and hidden operation names,
schedules, suspension boundaries, nested automatic instrumentation,
deterministic trace and span IDs, concurrency, semantic ancestry, and the
manager-specific continuation compatibility matrix. The host proxies normal
catalog, configure, snapshot, and advance operations but not `/audit` or
`/reset`.

For all three profiles — `visible` (zone), `hidden` (zone, renamed), and
`hidden-store` (continuation-store requiring native continuations) — the
verifier drives the sequential and overlapping scenarios through the browser.
It requires exactly one root per operation, every non-root span to descend
transitively from its own root, every protected automatic span to remain
present, distinct traces for overlapping operations, no cross-parentage,
complete UI inventories, deterministic scenario advance, and no protected
audit exposure.

Manual hand-span parenting, one-auto-span repair, manual-plus-one-auto
repair, global-root reuse, visible-profile constants, renderer forgery, span
deletion, scenario suppression, the exact predecessor hard-coded-lowered
patch, and fixed promise-chain or lowered targets all fail the protected
contract.
