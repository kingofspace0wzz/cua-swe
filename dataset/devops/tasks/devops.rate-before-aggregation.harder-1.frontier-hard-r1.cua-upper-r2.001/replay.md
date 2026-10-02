# devops.rate-before-aggregation.harder-1.frontier-hard-r1.cua-upper-r2.001

Controlled upper-frontier successor of
devops.rate-before-aggregation.harder-1.frontier-hard-r1.001; same independence group
and the same reset-aware rate-before-aggregation failure family. The only changed axis
is couple_reset_lineage_with_late_arrival.

Run the application with env/service.mjs as described in runtime-contract.yaml. At
1280x720 the console pairs two deterministic observation windows per profile (visible:
Window A · steady collection and Window B · post-failover around a 480s ingest
collector failover; hidden: Epoch 1 · scheduled publication and Epoch 2 · reconnect
drain around a 540s failover recovery, under different window identities).

Normal operator replay (~22 GUI actions, well within budget):

1. First screen (Window A, Burst control, Requests): the burst is a clean ramp; no
   artifact. Compare all three panels.
2. Rolling restart and Restart in burst in Window A: rectangular blocks aligned with
   the target-restart markers and inflated totals on every panel; the target evidence
   table shows the scheduled target resetting and recovering, and every publication
   "on schedule".
3. Switch to Window B and repeat: the same rectangle artifact appears around the later
   window's own reset markers; Burst control remains clean in both windows (unaffected
   control). In the restart scenarios the restarting target's Publication cell reads
   "N samples queued · drained <time>s", and a "collector drain" marker sits at the
   drain time between the restart marker and the burst.
4. Read the collection record: Window A documents on-schedule publication with
   identical live-feed and ledger orderings; Window B documents the 480s failover and
   that drained publications commit to the live feed in arrival order while the
   collection ledger re-orders them by original scrape timestamp.
5. Open Query definitions: every deployed rule is textually a per-series rate inside a
   service sum, so expressions alone identify nothing. The ingestion lineage notes are
   decisive only when coupled with the record and the drain evidence:
   - Traffic window (bound baseline) consumes one merged per-service counter from the
     ingress gateway rollup: aggregate-before-rate in every window.
   - Traffic detail consumes the raw per-target scrape via the live collector feed,
     which commits samples in arrival order: indistinguishable from correct in Window
     A and in every burst control, but after the failover it commits the restarting
     target's delayed samples late, so the reset-aware window misplaces the restart
     correction (a stale plateau then a jump around the drain marker).
   - Traffic ledger consumes the same per-target samples re-committed by the
     write-ahead collection ledger in original scrape-timestamp order: preserves true
     reset lineage in both windows at the same 15s cadence (complete for these closed
     windows).
   - Traffic capacity trails the live scrape by one interval; Traffic archive keeps
     one sample per 30s block; both are wrong in every window.
6. Return to Window A: the paired state reproduces exactly (reset control), and
   /configure and /reset restore deterministic state.

Divergence structure (measured in the engine matrix): the broken rollup binding fails
the 12 restart states per profile; binding the arrival-order live feed matches the
protected expectation in all 9 first-window states and both later-window burst
controls and diverges only in the 6 later-window restart states, after the late sample
and the reset transition; binding the ledger matches all 18 states. Gold rebinds the
durable policy to traffic-ledger and makes compilePanelPlan forward the binding (2
files). Accepted equivalents: pinning traffic-ledger in policy and compiler
(alternates/pinned-ledger-binding.patch) and a catalog-driven per-window map that
keeps the live feed in the clean first window and the ledger afterwards
(alternates/first-window-feed-map.patch) — the candidate repairs agree in the first
window by construction. Preserve all windows, points, target reset and publication
evidence, markers, records, summaries, and the 60-second range. Reload and service
reset must preserve the corrected behavior. Hidden certification rotates targets,
panels, windows, reset schedules, and late-drain schedules; it uses the same
deployment contract.

The exact successful parent lower-anchor CUA patches (static traffic-detail binding)
apply cleanly, render a fully healthy first window and control burst everywhere, and
fail only in the paired later window's restart states after the recorded drain — the
intended trap. A hard-coded per-window map keyed to the visible window identities
passes the visible profile and is rejected by the hidden profile's window identities
(negatives/visible-window-map.patch). No raw model output or trajectory informed this
successor. Future evaluation uses ports 51300/51400 and requires a fresh host token.
No evaluation is part of construction.
