# Opus 5.5 evaluation report

Benchmark: CUA-SWE. Snapshot: October 22, 2026.
Model: Opus 5.5.
Cohort: 105 tasks in each of two conditions, for 210 completed evaluations.

| Domain | Tasks per condition | Code-only successes | Hybrid CUA successes |
| --- | ---: | ---: | ---: |
| Web | 36 | 10 | 17 |
| Game | 29 | 3 | 5 |
| DevOps | 20 | 1 | 15 |
| Mobile | 20 | 2 | 11 |

## Scoring and cohort

Pass@1 is the number of tasks with both a correct patch and a valid trajectory, divided by the full domain task inventory. Model-caused rule violations remain task failures. Infrastructure-invalid attempts are replaced before selection; valid model failures are not retried to obtain better scores.
Code-only permits coding without application or computer-use access. Hybrid CUA combines coding with screenshot-based computer use. One accepted attempt is selected per task and condition.
The four-domain mean gives equal weight to the unrounded domain fractions.

- Code-only mean: 13.3%.
- Hybrid CUA mean: 48.6%.

## Methodology and comparability

This is a new evaluation using the released configurable-provider evaluator with provider-default sampling and reasoning. It is distinct from the paper's fixed model configurations and reviewed repeated-attempt cohorts. Temporary upstream failures may be retried within a request.
Runtime repairs and corrected protocol audits were applied. The audit corrections address repository-boundary matching, supported browser action options, relative references to the supplied launcher, and unassigned adapter identities. Original selected model attempts, patches and protected verifier outputs were retained.
Only aggregate pass@1 results are reported here. Raw trajectories, infrastructure records and execution identifiers are excluded from this package.
