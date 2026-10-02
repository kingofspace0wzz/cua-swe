# Evaluated Web-36 release

This release contains the revised 33-task evaluation and the three admitted
Canvas additions: `web.fabric-nested-selection-05.001`,
`web.fabric-nested-selection-06.001`, and
`web.fabric-nested-selection-44.001`.

The [manifest](manifest.yaml) is the versioned copy of the canonical
[`dataset/web/manifest.yaml`](../../manifest.yaml). Its denominator is 36
tasks per model and condition. Web results remain separate from Game,
Mobile, and DevOps results.

The [evaluation summary](evaluation-summary.json) retains the 720 selected
outcomes: nine API models in code-only and CUA conditions, plus two CLI
agents in CUA. It records native verifier success and reported success
separately, along with the source artifact hashes. Publishing this release
does not rerun or rescore those attempts.

The [task lineage](../../evaluation/web36-task-lineage.json) binds the
portable bundles to the evaluated inputs. Paths are relocated for repository
use. Those relocations produce new canonical bundle digests; the original evaluated
digests remain recorded separately. Instructions, broken source snapshots,
runtime contracts, and verifiers must match their evaluated bytes.

Use [`scripts/run_evaluation.py`](../../../../scripts/run_evaluation.py) for subsequent runs; the
[README](../../../../README.md#run-and-evaluate) gives the commands.
