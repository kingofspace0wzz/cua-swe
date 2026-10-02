# Replay: devops.slo-availability-rollup.harder-1.frontier-hard-r1.001

Controlled frontier-hardening round of devops.slo-availability-rollup.harder-1.001; same
independence group and the same SLO availability-rollup failure family.

Open **Reporting agreement** under pooled event totals. The agreement lists each serving region
with an equal reporting share, states that the shares are independent of request volume, and states
that budget utilization uses the same shares. These facts are supplied by the protected runtime.
Collapse the agreement and inspect the region breakdown lower in the console. Compare high-volume
dilution, low-volume inverse bias and mixed regions in both rolling windows: regional request
volume differs by orders of magnitude while reporting shares stay equal, and neither raw request
pooling nor equal slice averaging reproduces the agreed portfolio values.

Open **Rollup reference**. Unlike the parent round, the reference is now a neutral parameter menu:
six supported policies (event pooling, volume-weighted regional weighting, slice-total weighting,
grouped parity, delivery weighting, equal slice mean) documented only by their own arithmetic. No
entry restates the agreement, no entry is marked authoritative, and the first entries are decoys.
Two entries are region-scoped: a volume-weighted regional policy and the grouped-parity policy.
Only correlating the agreement's equal, volume-independent shares (against the unequal regional
volumes visible in the breakdowns) with the reference's parameter vocabulary identifies the
authoritative durable plan: availability and budget must use the weighted-slices mode with the
regional-parity weight.

The expected headline availability is the mean of per-region good/total ratios. Each region pools
every slice in that window before it receives one share. Verdict compares this availability with
the active objective. Budget consumed is the mean of per-region bad/(regional total * (1-objective))
percentages; remaining is 100 minus consumed. Raw pooled good, bad, total and allowed counts stay
unmodified as event audit information; they are not the denominator of this portfolio report.

Repair the durable definition and the plan compiler. The protected engine already supports the
required policy; do not change event payloads, engine arithmetic, objectives, fixtures, verifiers
or build entrypoints. Check selected slices, the region and endpoint breakdowns, all verdict
filters, four probes and replay. Replay adds a region in the visible profile and must update
reporting shares. Reset must restore the opening ledger. Hidden identity and objective variants
must pass without special cases. Equivalent plan-field-preserving compilation is accepted
(alternates/preserve-plan-fields.patch).

The only difficulty axis changed from the parent is require_cross_surface_correlation: the parent's
rollup reference listed the authoritative policy first with a description that restated the
agreement, so a runtime heuristic over that single surface reconstructed the contract. This round
keeps the parent's events, oracle, gold semantics, source tree, instruction and controls, but the
reference no longer identifies the answer alone and the protected engine honestly implements the
volume-weighted regional decoy. The parent's successful Claude Fable 5 code-only patch is retained
byte-exact as negatives/predecessor-fable5-successful-code-only.patch; its pooled-hint heuristic now
deterministically compiles the event-pooled plan and fails the ledger comparison in every scenario.
