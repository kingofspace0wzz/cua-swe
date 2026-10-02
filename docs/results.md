# Scores and provenance

The public leaderboard comes from the manuscript's canonical September 24, 2026 result snapshot, copied into [paper-results.json](../results/paper-results.json). Its `sha256` commits to the manuscript's source report. [build_leaderboard.py](../scripts/build_leaderboard.py) derives the README table, full result tables, and CSV from the integer success counts and domain denominators. It does not estimate missing results or round percentages before computing counts.

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
