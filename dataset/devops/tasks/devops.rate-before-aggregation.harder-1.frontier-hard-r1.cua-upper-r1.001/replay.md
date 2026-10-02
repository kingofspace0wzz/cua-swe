# devops.rate-before-aggregation.harder-1.frontier-hard-r1.cua-upper-r1.001

Controlled upper-frontier successor of
devops.rate-before-aggregation.harder-1.frontier-hard-r1.001; same independence group
and the same reset-aware rate-before-aggregation failure family. The only changed axis
is require_counter_lineage_across_paired_windows.

Run the application with env/service.mjs as described in runtime-contract.yaml. At
1280x720 the console now pairs two deterministic observation windows per profile,
separated by a recorded collector publication transition (visible profile: Window A ·
pre-rollout and Window B · post-rollout around a 420s rollout; hidden profile: Cycle 1
· pilot publication and Cycle 2 · post-rollback around a 435s rollback, under
different window identities).

Normal operator replay (~20 GUI actions, well within budget):

1. First screen (earlier window, Burst control, Requests): the burst is a clean ramp;
   no artifact. Compare all three panels.
2. Rolling restart and Restart in burst in the earlier window: rectangular blocks
   aligned with the target-restart markers and inflated totals on every panel; the
   target evidence table shows exactly one target resetting and recovering per
   scenario.
3. Switch to the paired later window and repeat: the same artifact reappears around
   the later window's own reset markers; Burst control remains clean in both windows
   (unaffected control).
4. Read the collection lineage record: each window documents which metric carries the
   raw per-target application scrape, and the transition marker documents the
   publication re-registration between the paired windows.
5. Open Query definitions: every deployed rule is textually a per-series rate inside a
   service sum, so expressions alone identify nothing. The per-window lineage notes on
   each card are decisive:
   - Traffic window consumes one merged per-service counter in both windows
     (aggregate-before-rate everywhere; the bound baseline).
   - Traffic detail carries the raw per-target scrape in the earlier visible window
     only; after the rollout the same metric name is republished by the ingress
     gateway as one merged counter.
   - Traffic stream is the gateway staging rollup in the earlier visible window and
     carries the migrated raw per-target scrape in the later one.
   - Traffic capacity trails the live scrape by one interval; Traffic archive keeps
     one sample per 30s block; both are wrong in every window.
6. Return to the earlier window: the paired state reproduces exactly (reset control).

Divergence structure: any single static binding is locally healthy in exactly one
window of each profile and collapses in the other after (or before) the recorded
counter-reset transition; the hidden profile migrates in the opposite direction, so a
mapping copied from the visible profile fails there. Gold binds one deployed
per-target scrape rule per collection window from the catalog's window lineage
declaration (catalog.windows[].perTargetScrape) and makes compilePanelPlan forward a
string-or-per-window binding; main.js passes the catalog into the policy. An
equivalent accepted repair builds the same per-window binding with a loop
(alternates/window-lineage-reduce-binding.patch). Preserve all windows, points,
target reset evidence, markers, summaries, and the 60-second range. Reload and
service reset must preserve the corrected behavior. Hidden certification rotates
targets, panels, reset/burst schedules, migration direction, and window identities;
it uses the same deployment contract.

The exact successful parent lower-anchor CUA patches (static traffic-detail binding)
apply cleanly, render a fully healthy earlier window, and fail only in the paired
later visible window and the earlier hidden cycle — the intended trap. No raw model
output or trajectory informed this successor. Future evaluation uses ports
51300/51400 and requires a fresh host token. No evaluation is part of construction.
