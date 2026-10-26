# Scores and provenance

The public leaderboard combines the original September 24, 2026 paper snapshot in [paper-results.json](../results/paper-results.json) with the October 22 [Opus 5.5 snapshot](../results/opus55-20261022/evaluation-results.json). Each source retains its own report hash. [build_leaderboard.py](../scripts/build_leaderboard.py) validates the integer counts, domain denominators, and Opus 5.5 report hash and macro means, then derives the README table, full result tables, and CSV. Missing results are not estimated.

## October 2026 update

Claude Opus 5.5 achieves 13.3% code-only and 48.6% hybrid CUA success, a 35.3-point gain using equal weights for the four unrounded domain fractions. Its 210 completed evaluations cover the same 105-task inventory in both conditions. The † marker identifies this additional evaluation throughout the tables.

The new evaluation uses the released configurable-provider evaluator with provider-default sampling and reasoning, distinct from the original paper's fixed configurations. Runtime repairs and corrected protocol audits are documented in the [source report](../results/opus55-20261022/evaluation-report.md). Only aggregate pass@1 results are supplied; no Opus 5.5 task-level, efficiency, or repeated-attempt results are inferred. The original paper snapshot and its reviewed repeated-attempt cohort remain unchanged.

## Interpreting the table

- **Pass@1:** the selected first attempt for the paper's single-attempt result.
- **Code-only:** coding without application or computer-use access.
- **Hybrid CUA:** coding with screenshot-based computer use.
- **Pass@3:** at least one success in the reviewed three-attempt set. The supplied single-attempt dispatcher does not recreate that reviewed cohort automatically.
- **Deferred / not evaluated:** no measured score, rather than zero success.

The task denominators are Web 36, Game 29, DevOps 20, and Mobile 20. Keep these separate. API systems call each model through its API; Codex and Claude Code are distinct CLI systems. This leaderboard is a versioned research result, not a claim that provider access or the same executable remains available today.

## Domain scoring

**Web:** the original reported score requires the deterministic verifier, the original protocol-compliance predicate, appropriate CUA evidence, and no infrastructure error. The release stores 720 selected rows, with 219 originally reported successes and 255 native verifier passes. The 36 native passes excluded by the original reporting rules must not silently become reported successes. Budget attestations that were diagnostic in the original protocol do not become new scoring exclusions.

**Game:** keep the original pass@1 results separate from the reviewed repeated-attempt cohort. Eight of its 87 first attempts were replaced after runtime review: seven for GPT-6 and one for Fable. Thus GPT-6's first attempt in the repeated set is 17/29, while its original pass@1 is 11/29. The complete tables show both explicitly.

**DevOps:** preserve reviewed attempt eligibility and infrastructure classifications. Refusals or agent behavior must not be relabeled as infrastructure merely because a task failed.

**Mobile:** the paper's table uses reviewed eligible attempts; the packaged campaign summary also preserves raw executed, excluded, deferred, and behavioral outcomes. These are different views and should not be collapsed into one raw success fraction. New canonical runs use one attempt per cell and hold dispatch on infrastructure faults; they do not automatically repeat the paper's review/replacement process.

## What is included

- Paper aggregate scores with success counts and denominators, including repeated-attempt results.
- Web selected per-task results and task-input lineage under `dataset/web/releases/` and `dataset/web/evaluation/`.
- Mobile reviewed campaign records and frozen input lineage under `dataset/mobile/releases/`.
- The exact task manifests and pinned evaluator sources needed to identify evaluation conditions.

Aggregate paper results remain identifiable as paper results rather than being presented as newly rerun scores.
