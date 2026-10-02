# devops.scrape-response-phase-deadline.owner29-r1.frontier-hard-r2.cua-diff-r3.001

One-axis successor of
`devops.scrape-response-phase-deadline.owner29-r1.frontier-hard-r2.cua-diff-r2.001`.
The scrape transport bug, native HTTP collector, receiver ingestion, target
controls, reset/replay workflow and deterministic behavioral oracle are
preserved; the agent-visible broken transport source (`src/scrape.mjs`,
`src/budgets.mjs`, `src/collector.mjs`, `src/metrics.mjs`) is byte-identical to
the parent. The changed axis is deadline authority:
`epoch_scoped_cross_surface_deadline_authority`.

In the parent, one static receiver runbook PNG published the approved
whole-response cap per rollout profile, collection tier and receiver class,
and all four successful predecessor screenshot-CUA repairs (one Fable 5,
three GPT-6) transcribed exactly that single three-dimensional matrix. In
this successor the single matrix no longer exists. Two normal operator
surfaces replace it:

1. the **policy activation board** maps each rollout profile AND activation
   epoch to its active opaque policy revision, including plausible superseded
   revisions ("do not apply") and a rollback row (VT-58 E-241 reactivates the
   older PRV-5203);
2. the **deadline authority matrix** maps policy revision, collection tier
   and receiver class to freshness, abort and the approved whole-response
   cap, including rows for the superseded decoy revisions.

Runtime targets and `/begin` descriptors expose only opaque profile, epoch,
tier and receiver-class identifiers; policy revision tokens exist only in
pixels. The console shows the live activation epoch beside the profile code,
and every explicit reset advances the rollout to its next scheduled
activation epoch, so the same profile is governed by a different revision
after replay. Hidden grading profiles rename every token: profile codes
(VT-58, JN-84), epoch codes, revision tokens, tier tokens (express/freight,
rapid/batch) and receiver-class tokens (relay/trunk, orbit/depot).

Operator replay:

1. Read the activation board row matching the displayed rollout profile and
   the live activation epoch; note the superseded revisions and that the
   next scheduled epoch activates a different revision.
2. Read the deadline authority matrix rows for that active revision; note
   that sibling receiver classes inside one tier carry different envelopes,
   and that the same tier/class cell changes between revisions.
3. Run scrape checks and open the affected target; correlate its tier AND
   receiver class (target table or detail facts) with the active revision's
   matrix row; confirm the 250 ms connection cap closes supported responses
   before payload preparation/body completion.
4. Repair the connection-to-response transition and select the approved
   whole-response cap by active policy revision (profile + epoch), tier and
   receiver class.
5. Reset and replay; the activation epoch advances, a different revision
   governs the same profile, and supported targets must ingest exact
   complete samples inside the newly active envelopes while stalls and
   trickles close inside the newly active abort envelopes. The
   completed-attempt ledger keeps prior rows with their original epoch
   provenance.

The protected verifier exercises all three profiles and, in every profile,
both activation epochs (reset advances the schedule deterministically).
Within every profile at least one tier/class cell has disjoint feasible cap
intervals across the two epochs, so no epoch-agnostic profile/tier/class
matrix — including the exact parent gold and all four exact successful
predecessor CUA patches — satisfies both episodes; no flat, per-tier-only,
per-class-only, start-epoch-only, latest-revision-only or
superseded-revision cap assignment survives either. No-op fails, gold passes
twice, the canonical negative fails twice, every inherited realistic
negative fails, and all four exact successful predecessor CUA patches apply
cleanly and fail: their stale single-matrix caps close the supported
bulk/freight/batch-class exporters before body completion in both epochs and
overshoot the small streamline/relay abort envelopes. The certification
matrix is recorded in the construction run directory for this candidate.
