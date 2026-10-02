# Replay

Open the console at its assigned URL. The initial series remains above the shown
threshold through 3:00, longer than the 120-second hold, yet the alert timeline
stays pending with a fresh active-since time and fingerprint at each evaluation.
The delivery journal at the bottom shows the receiver route key staying constant
while the alert key changes every tick, with status divergent; firing, delivered,
and unrouted all stay 0. Open Labels & detail: one expanded reading changes with
the plotted sample between evaluations while service, instance, severity, team,
and the routed selector label stay constant. Correlating the two surfaces —
identity churn on the timeline/labels side and the stable route key plus the
receiver match selector on the delivery side — supports identity misplacement in
the rule adapter rather than insufficient time, a threshold miss, a restart, or
a receiver outage.

Repair the adapter so the compiled alert identity carries exactly the labels the
receiver route consumes, while every other enrichment stays descriptive detail.
Gold binds the catalog route into rule compilation: enrichments named by the
receiver match selector remain labels, everything else becomes annotations. The
same samples then fire after the full hold, the journal reports aligned with the
alert key equal to the route key, and delivery counts every firing alert. Short
burst remains healthy after recovery. Independent targets keep their own pending
clocks. Advance, Replay capture, Reset, and browser reload remain deterministic.

Protected profiles rotate receiver route names, selector keys (including
multi-key and label-derived selector values), enrichment names and order, value
scales, hold/interval, and target names. Keeping only the visible selector key,
keeping constant-template enrichments as labels, moving every enrichment to
annotations, dropping non-routed detail, or repainting the journal all fail at
least one profile. Baseline failure, gold replay, and construction probes are
not model results.
