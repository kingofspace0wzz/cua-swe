# Owner20 tail-decision frontier-hard r2 reproduction

The page opens on Live incident with the missing checkout trace selected. Its
ERROR dependency arrives at +3300ms; the decision log cached a drop at +250ms.
Select payments: the ERROR child arrived early and was sampled, distinguishing
late decisions from absent error policies. Early arrivals retains both error
traces; Interleaved traffic loses the late child again. Replay unseen trace
selects a newly received late error under the same production configuration.
All of this is reachable in four clicks after opening, with both key diagnosis
observations visible without scrolling.

The Receiver service levels article shows the receiver policy panel, a raster
rendering published by the protected receiver and proxied at
`/api/service-levels`. It lists three collector policy profiles with
activation epochs: SL-EDGE-2024.11 (superseded), SL-INCIDENT-2026.09
(ACTIVE - envelope <= 3300 ms, decision SLO <= 3600 ms, measured from first
receipt), and SL-DRAFT-2027.01 (scheduled, not yet active). The active profile
governs every window, probe, and replay: the collector must hold each tail
decision open for the full delivery envelope and close it within the SLO, so
the semantically accepted decision-wait band is [3300 ms, 3600 ms]. Any
correct wait inside that band is accepted; no exact configuration literal,
source shape, or policy name is required. The decisive values exist only as
panel pixels: snapshot and audit JSON publish no envelope, SLO, or policy
field, and in the hidden variants every observable delivery lag (scenarios,
replay, probes) stays below 3000 ms, so no runtime statistic, JSON field, or
adaptive alignment reproduces the band. The superseded (1900 ms) and scheduled
(5200 ms) rows are decision-changing distractors that fail behaviorally.

Gold records the active profile's service levels and derives the shared
decision wait from them (deployed wait 3300 ms). It intentionally changes
decision timestamps and preserves incoming spans and timestamps, retention
eligibility, ordinary sampling, and replay input. It does not change policies,
receiver telemetry, compiler, renderer, or protected runtime. The exact
successful Fable r1 patch (wait 2000 ms plus a runtime alignment that reads
`diagnostics.deliveryEnvelopeMs`/`decisionBudgetMs`) applies cleanly and
fails: those fields no longer exist, the alignment no-ops, and the 2000 ms
wait decides before the late dependency arrives and below the published
envelope in every profile. Lag-adaptive repairs pass the visible profile but
fail the hidden profiles' published band. Reload restores the opening state.
Repeated replay is idempotent. Reset restores the pristine opening and the
canonical panel. Baseline construction failure is expected and is not a model
outcome.
