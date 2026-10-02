# devops.rate-before-aggregation.harder-1.frontier-hard-r1.001

Controlled frontier-hardening round of devops.rate-before-aggregation.harder-1.001; same
independence group and the same reset-aware rate-before-aggregation failure family.

Run the application with env/service.mjs as described in runtime-contract.yaml. At
1280x720 compare all three scenario buttons across all three counter panels. In restart
scenarios the baseline has rectangular blocks aligned with target-restart markers and
inflated totals; the control burst is legitimate. Scroll to target evidence, then open
Query definitions.

Every deployed recording rule is already written in the recommended textual form (a
per-series rate inside a service sum), so the expressions alone no longer identify the
broken ordering. What differs is each rule's upstream input, described by the runtime
lineage notes on every definition card and confirmed by chart consequences:

- The bound Traffic window rule consumes service_stream_total, a single per-service
  counter merged upstream by the ingress gateway cost rollup. Independent target resets
  are folded into one counter before the rate window, so the effective evaluation is
  still aggregate-before-rate: rectangular blocks at reset markers and inflated totals.
- Traffic detail consumes panel_counter_total, the raw per-target application scrape at
  the live 15s cadence. This is the only input that preserves independent reset
  identities at full freshness and resolution; binding it yields the reset-aware
  per-target rate before the service sum.
- Traffic capacity consumes target_stream_total from a cross-zone relay mirror whose
  samples trail the live scrape by one collection interval; if bound, the whole curve
  (including the control burst) lags the burst marker by one 15s tick.
- Traffic archive consumes archive_stream_total from the archive compactor, which keeps
  the last sample of each 30s block; if bound, the curve staircases and flattens the
  burst crest in every scenario.

Gold changes the durable pipeline binding to traffic-detail and makes compilePanelPlan
forward that binding. An equivalent accepted repair pins traffic-detail in both the
policy and the compiler (alternates/pinned-detail-binding.patch). Preserve all points,
target reset evidence, markers, summaries, and the 60-second range. Reload and service
reset must preserve the corrected behavior. Hidden certification rotates targets,
panels, and reset/burst schedules; it uses the same deployment contract.

The only difficulty axis changed from the parent is preserve_upstream_transformations:
the deployed rule expressions keep their realistic upstream transformations (gateway
rollup, relay mirror, archive compaction), and the correct ordering is diagnosable only
from those transformations' runtime consequences and lineage notes, not from a
textually distinctive source binding or step order. The predecessor code-only patches
that parsed the step text for a rate-before-sum shape now re-select the broken rollup
input and are retained as exact protected negatives. No raw model output or trajectory
informed this successor. Future evaluation uses ports 51300/51400 and requires a fresh
host token. No evaluation is part of construction.
