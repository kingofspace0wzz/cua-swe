# Replay: devops.slo-availability-rollup.harder-1.frontier-hard-r1.cua-upper-r1.001

Controlled upper-frontier successor of devops.slo-availability-rollup.harder-1.frontier-hard-r1.001;
same independence group and the same SLO availability-rollup failure family. The only changed
difficulty axis is require_epoch_and_window_authority_intersection.

Open the console. The summary, totals, slices, breakdowns, Reporting agreement, and Rollup
reference behave exactly as in the parent: the agreement lists each serving region with an equal,
volume-independent reporting share and ties budget utilization to the same shares, while neither
raw request pooling nor equal slice averaging reproduces the agreed portfolio values in the
dilution, inverse, and mixed-regions scenarios across both rolling windows.

New in this revision, the durable definition is a **window-scoped rollup deployment schedule**
(`src/config/sloDefinition.js`) with four revisions next to the superseded legacy default. Each
revision declares rollups per aggregation scope; the runtime **Rollup deployments** ledger dates
them against a report date of 2025-09-30 and shows per-scope coverage with compiled rollup chips:

- `rev-2411` — Published 2024-11-08, standing and review scopes (event-pooled era);
- `rev-2503` — Published 2025-03-22, standing and review scopes (equal-slice-mean era);
- `rev-2507` — Published 2025-07-18, **standing scope only**;
- `rev-2509` — Submitted 2025-09-14 · review pending, both scopes (delivery-weighted draft).

The scope columns name the windows ("Standing · 30-day rolling", "Review · 7-day rolling"), and in
the broken state every covered chip collapses to the equal slice mean while `rev-2509`'s chip keeps
its delivery weight — the compiler coercion is visible at runtime. No record is marked
authoritative for any window.

Three **Rollup views** render beside the ledger: an archived baseline (`rev-2411`, computed over
the active window's opening ledger and frozen across replay), a **prior publication for this
window** whose epoch tag changes with the active window (`rev-2503` in the 30-day window,
`rev-2411` in the 7-day window, both live), and a submitted revision preview (`rev-2509`, live).

The authoritative (epoch, window) pairs are identifiable only by intersection: the archived and
submitted tags remove `rev-2411` and `rev-2509` from headline candidacy; the 30-day prior tag
removes `rev-2503` there, leaving the standing-scope publication `rev-2507` as the 30-day
authority; the 7-day prior tag names `rev-2411`, and the coverage column shows `rev-2507` never
covered the review scope, leaving `rev-2503` as the 7-day authority. "Review pending" on the
newest submission is a deliberate misreading of the review window; the deployment ledger alone
also supports reading `rev-2503` (the latest dual-scope publication) as governing both windows.
The correct target policy is unchanged from the parent and remains runtime-only: correlating the
agreement's equal, volume-independent regional shares (against the unequal regional volumes in the
breakdowns) with the Rollup reference's neutral parameter vocabulary identifies the
weighted-slices mode with the regional-parity weight.

The expected headline availability in both windows is the mean of per-region good/total ratios;
budget consumed is the mean of per-region bad/(regional total * (1-objective)) percentages;
verdict compares the availability with the active objective; raw pooled good, bad, total and
allowed counts stay unmodified as event audit information. Repair the plan compiler passthrough
and exactly the two authoritative window entries: `rev-2507`'s standing entry and `rev-2503`'s
review entry. Do not change event payloads, engine arithmetic, objectives, fixtures, verifiers,
build entrypoints, the legacy default's role, or the declared policies of the non-authoritative
entries: the archived baseline must keep matching an independent event-pooled oracle over the
opening ledger, the 30-day prior view an independent equal-slice-mean oracle, the 7-day prior view
an independent event-pooled oracle, and the submitted preview an independent delivery-weighted
oracle over the live ledger. Check selected slices, the region and endpoint breakdowns, all
verdict filters, four probes, replay (which rebalances the reporting shares and recomputes only
the live views), window returns, and reset. Hidden identity and objective variants must pass
without special cases. Equivalent plan-field-preserving compilation is accepted
(alternates/preserve-plan-fields.patch).

Normal operator replay (well within budget, ~18 GUI actions): open the agreement and breakdowns in
dilution/inverse states (~6 actions), expand the reference (~1), read the deployments ledger and
views (~1), switch windows and compare the prior tags in both windows (~2), replay in the
mixed-regions 7-day state and compare the frozen archive against the live views (~3), run a probe
and a filter (~3), then edit the two authoritative entries plus the compiler and re-verify (~2
navigations).

Both successful parent lower-anchor CUA patches are retained byte-exact as
negatives/gpt6-successful-lower-anchor-cua.patch and
negatives/fable5-successful-lower-anchor-cua.patch; each still repairs only the superseded legacy
default plus the compiler, leaves both authoritative window entries compiling to the equal slice
mean, and deterministically fails the protected ledger comparison in every scenario. The parent's
canonical negative and accepted alternate are retained byte-exactly as
negatives/legacy-availability-only.patch and negatives/legacy-plan-fields-parity.patch and fail
for the same reason. Newest-submitted, full-coverage, single-window (standing-only canonical
negative.patch and review-window-only), schedule-shotgun, mean-sweep, scope-extension,
schedule-config-only, window-id-keyed, and deployment-view display-forgery attacks are protected
negatives as well.
