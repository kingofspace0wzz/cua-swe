# Gauge update replay (frontier-hard r4 successor)

The opening console starts one real UDP capture fed by four provisioned fleet
endpoints, each on its own producer socket. Every session epoch opens with the
four endpoints' channel self-checks before any ordinary traffic: each endpoint
sends two identically signed pulses on its own check register followed by one
unsigned settle line carrying the endpoint's own resulting register value. The
left-rail provisioning bulletin, served with the runtime session, describes
that check. In the opening epoch `cabinet-agents` (+2/+2 settle 4 in profile A)
and `gatehouse-counters` (+3/+3 settle 6) settle to the accumulated register
(delta-capable relays), while `yard-station` (+1.5/+1.5 settle 1.5) and
`basin-level` (+0.5/+0.5 settle 0.5) settle to the last reading (snapshot
publishers). Select the first gauge and open Update history: intact signed
datagrams from `cabinet-agents` correspond to parsed tokens, but the broken
worker stores each numeric delta as a replacement, so the relay calibration
shows stored 2 where the settle line then jumps the register to 4, and the +6
headroom update stores 6 instead of 46. The older unsigned relay stream and
both snapshot-style endpoints' repeated identical signed readings visibly stay
correct in the broken console.

New in this revision, the fleet inventory no longer describes update
semantics: the four cards expose only endpoint labels, UDP endpoints and
neutral lane/firmware channel designations (lane G2, S9, C4, L6), and no card
wording, endpoint name, README sentence or public payload states which
channels are additive. The active convention is demonstrated only behaviorally
by the epoch-opening channel checks. A deterministic collector rollout still
activates at session epoch3 (the session epoch increments on every
seed/reset/replay and is shown in the console footer): `gatehouse-counters`
moves from lane G2 to lane C4 and its unchanged +3/+3 check now settles at 3
(absolute re-reports, repeated within a batch and across shifts, including a
plus-signed re-report equal to its unsigned baseline inside one batch), while
`yard-station` moves onto lane G2 and its unchanged +1.5/+1.5 check now
settles at 3 (signed deltas repeated identically across datagrams, an unsigned
rebase, a first delta from implicit zero and a signed zero). `cabinet-agents`
and `basin-level` keep their channels, checks and plans across the rollout as
unaffected endpoint controls.

Gold binds each endpoint's active convention per epoch from its channel check
- holding that endpoint's signed lines until the unsigned settle discloses
whether the pulses accumulated - and only then applies and commits the
calibration and ordinary traffic exactly once, in receipt order, under the
bound mode; per-endpoint ingress normalization and per-endpoint event
reduction using the same calibration evidence are verified equivalent
alternates. Protected negatives cover uniform lexical sign-delta handling (the
r0 predecessor patches and the canonical negative), the exact successful
frontier-hard-r1 Fable patch (a runtime metadata keyword classifier), the
exact successful frontier-hard-r2 Fable patch (an inventory prose classifier
with a source-to-mode cache), the exact successful frontier-hard-r3 Fable
patch (a broad lexical inventory classifier with an all-delta fallback that
now misreads every snapshot-provisioned endpoint because the inventory
wording is neutral), the r2 parent gold as `static-fleet-provisioning`,
endpoint-name keyword classification, an epoch-parity activation guess, a
stale channel-text lookup with a first-seen source-to-mode cache
(`cached-first-epoch-provisioning`), and every inherited parent negative; each
corrupts at least one endpoint's stream in at least one graded epoch.

The protected writer uses the frozen A/B/C plans in batched and whole-line
split forms, selecting the epoch-active wave plan per session; each wave opens
with the four calibration groups. Its native socket receipt witness is outside
candidate control. A lost candidate update, parse exception, dropped
attribution or silent drop after native receipt is a candidate failure. There
is no resend or hidden retry. Missing native receipt or byte/order mismatch at
the independent socket is infrastructure-invalid.

Verify every receipt, identity, producer attribution, multiplicity and state
transition across three graded epochs per profile/form combination (opening
epoch1, post-rollout epoch3, repeated post-rollout epoch4); include signed
zeros, absolute rebase, repeated lines, repeated identical signed readings on
the currently-absolute channels, repeated identical signed deltas on the
currently-additive channels, plus-signed re-reports, healthy absolute traffic,
idle, no-input, reset/replay, page reload and process restart, plus the
channel-check calibration predicates (the check opens every graded epoch,
settles to the endpoint's own register and precedes ordinary traffic in the
sink), the per-endpoint mode-consistency predicate over all four endpoints in
every graded epoch, the neutral-inventory predicate, the bulletin visibility
predicate, the epoch-active inventory visibility predicate (retired
designations absent) and the deterministic post-rollout replay predicate. Full
native state and behavior are required; matching a displayed number is
insufficient. All author calls are externally bounded to120s and agent budgets
remain1800/115/210/26.

Construction and observed model validity are separate. Refer to the
construction run report for actual certification results.
