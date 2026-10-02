# Owner20 tail-decision cua-diff r2 reproduction

The page opens on Live incident with the missing checkout trace selected. Its
ERROR dependency arrives at +2450 ms; the decision log cached a drop at
+250 ms. Select payments: the ERROR child arrived early and was sampled,
distinguishing late decisions from absent error policies. Select worker: an
ordinary trace whose last span arrives at +2620 ms, the slowest delivery in
the window (also visible on the arrival/decision timeline). The Receiver
delivery ledger in the lower grid lists every recorded window and the replay
staging buffer with raw per-trace span receipts, under an identity line
reading "Receiver firmware 2419 · delivery profile DP-C41 · envelopes:
runbook RB-217". Early arrivals retains both error traces; Interleaved
traffic loses its late checkout child (+2530 ms) again. Replay unseen trace
receives the refunds ERROR dependency at +2620 ms under the same production
configuration. All of this is reachable in six clicks after opening.

No machine-readable surface publishes an envelope, margin, band bound, or
derived wait. The Receiver service levels article shows the current collector
decision wait (250 ms), the probability baseline (5%), and the served
identity string "delivery profile DP-C41 on firmware 2419 — decision envelope
and margin per receiver operations runbook RB-217". The full-width Receiver
operations runbook panel below the lower grid renders the runbook RB-217 PNG
(served by the protected receiver, proxied as /api/runbook): the current
FIRMWARE 2419 table maps every supported profile code to its delivery
envelope and decision margin — DP-A19 1450/120 ms, DP-C41 2840/120 ms,
DP-H77 3970/150 ms, DP-K58 3370/90 ms, DP-M63 5150/200 ms — with the rule
"hold every tail decision open for at least the active profile's delivery
envelope, and close it no later than the decision margin after the envelope;
measured from first span receipt; applies to every incident window, probe,
and replay". A clearly marked "FIRMWARE 2381 (SUPERSEDED 2026-03-02 — DO NOT
USE)" table beneath it lists different values (DP-C41 2680/140, DP-H77
3560/140, DP-K58 3080/140) and must be rejected. The mapping exists only in
those pixels: not in repository source, HTML, bundled assets, client-visible
JSON, accessibility metadata, or any API field.

The three graded delivery profiles report pairwise-distinct opaque codes with
pairwise-disjoint accepted decision bands — DP-C41 [2840 ms, 2960 ms], DP-H77
[3970 ms, 4120 ms], DP-K58 [3370 ms, 3460 ms] — and every band floor sits
above that profile's recorded ledger maximum plus the parent-era 180 ms
margin (2620/3390/2960 ms + 180 ms). Consequently every fixed wait fails at
least two profiles; raw-ledger maxima, ledger + 180 ms (the parent gold),
ledger + 50 ms and ledger + 0 ms (both exact successful predecessor code-only
patches), ledger + arbitrary padding (e.g. +300 ms), single-profile
constants, and the superseded 2381 table all fail at least one profile's
band. Any repair that reads the receiver's reported profile code at the
existing single configure call and selects a durable wait inside the current
runbook band for every supported code is accepted; no exact literal, source
shape, or policy name is required.

The protected receiver still refuses decision traffic until a collector plan
is deployed and records the deploy history; the verifier rejects sessions
whose deployed plans differ, so per-window or post-observation retuning fails
the durable-configuration check. Gold transcribes the current runbook table
into the plan compiler, keys it by `catalog.receiver.firmware.profileCode`,
and threads `catalog.receiver` through the existing single configure call. It
intentionally changes decision timestamps and preserves incoming spans and
timestamps, retention eligibility, ordinary sampling, and replay input. It
does not change policies, receiver telemetry, the protected runtime, or the
runbook panel. Reload restores the opening state. Repeated replay is
idempotent. Reset restores the pristine opening. Baseline construction
failure is expected and is not a model outcome.
