# Gauge update replay (frontier-hard r5 successor)

The opening console starts one real UDP capture fed by two attributed site
relay endpoints per deployment profile, each on its own producer socket. Every
relay opens the session epoch, and follows its internal rollover points, with
one atomic announce batch: the relay's own `<relay>.sync` register line first,
then the authoritative current reading of every gauge that relay tracks
(negative readings keep their minus sign; nonnegative announce readings are
unsigned). Between announces, live-forwarded lines follow the deployment's
provisioned relay generation. In profile A (the agent-facing runtime) the
pass-through generation forwards signed relative updates:
`workers.north.headroom` opens at 40, receives +6, +6, +0, an unsigned rebase
to 18, and the next `north-bay.sync`-led announce restates 18; after +3 x4 and
-4 the closing announce restates 26, and `workers.south.headroom` (12, -3)
is restated at 9. In profile B the folding generation publishes sign-formatted
absolute readings: `workers.east.headroom` (125, +136, +147, +147) is restated
at 52 after an unsigned 52 reading, matching the last reading rather than any
accumulation. Profile C repeats the pass-through generation with decimal
thermal margins. No producer label, README sentence, inventory, mode table or
public payload states which generation a deployment runs; the console shows
only neutral relay names (north-bay, south-bay, east-bay, west-bay,
room-riser, rack-riser) in the Source columns.

Select the first gauge and open Update history: intact signed datagrams
correspond to parsed tokens, but the broken worker stores each parsed number
as a replacement, so in profile A the +6 update shows before 40 and stored 6,
+0 stores 0, and each announce restatement visibly snaps the gauge back to the
accumulated level (18, then 26). The unsigned capacity/reference streams and
the relay sync registers stay correct in the broken console as unaffected
controls. The three deterministic decision states are the empty session, the
seeded opening epoch1 capture, and the replayed epoch3 capture after reset;
idle, page reload and worker restart preserve state without reseeding.

Gold reconciles the deployment's active generation per epoch from the announce
evidence, holding signed live lines (never announce lines) until the first
announce restatement that resolves a divergence between the accumulated-sum
and last-reading interpretations, then applies everything exactly once, in
receipt order, within the published one-second bound; announce restatements
are always applied as authoritative absolute readings. Ingress normalization
(`alternates/ingress-normalize.patch`) and a worker-inline reconciler without
the separate relay module (`alternates/worker-inline-reconciler.patch`) are
verified equivalent alternates. Protected negatives cover the exact successful
predecessor GPT-6 and Fable 5 code-only patches plus the canonical
`negative.patch` (all three hardcode lexical sign-delta handling, which
corrupts every folding-deployment signed reading in profile B and misapplies
the signed-negative announce restatements in profiles A and C), sign-subset
and numeric-sign guesses, add-everything, dedup/global-state/clamp/
reset-per-datagram corruption, signed-update deletion, a display-only running
total forgery, treating any unsigned line as reconciliation evidence
(misbinds on the ordinary rebase), an inverted announce binding, and a partial
repair that only applies the bound mode to announce-tracked identities and
corrupts the late `depot.dock`/`depot.pier`/`intake` streams.

The protected writer uses the frozen A/B/C plans in batched and whole-line
split forms; announce batches are never split. Its native socket receipt
witness is outside candidate control. A lost candidate update, parse
exception, dropped attribution or silent drop after native receipt is a
candidate failure. There is no resend or hidden retry. Missing native receipt
or byte/order mismatch at the independent socket is infrastructure-invalid.

Verify every receipt, identity, relay attribution, multiplicity and state
transition across two graded epochs per profile/form combination (opening
epoch1 and replayed epoch3); include signed zeros, unsigned rebase between
announces, repeated lines within a batch and across datagrams, first signed
value with implicit zero on a late identity, announce-restatement authority
(including signed-negative restatements), healthy unsigned traffic, sync
registers, idle, no-input, reset/replay, page reload and process restart,
plus the no-public-convention-field predicate and announce/attribution/epoch
visibility predicates. Full native state and behavior are required; matching
a displayed number is insufficient. All author calls are externally bounded
to120s and agent budgets remain1800/115/210/26.

Construction and observed model validity are separate. Refer to lane reports
for actual certification and parent-only gate results.
