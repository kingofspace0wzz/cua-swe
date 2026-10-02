# Public release notes

This public repository starts from a fresh Git root. It contains a selected snapshot of the canonical benchmark, environments, evaluator dependency closure, release tests, and publication documentation.

## Contents and preservation

- 105 canonical tasks: Web 36, Game 29, Mobile 20, DevOps 20.
- Executable task source, environments, verifiers, and controls are preserved byte for byte.
- The frozen Web harness, Game runner, Mobile evaluator, and DevOps runner are included with their supporting code.
- A task-name table is materialized and a Game source-path compatibility link is retained so evaluator imports and task paths resolve in this repository.
- README figures are crops of Figures 1 and 2 from the rendered current preprint, including the original captions. [Figure provenance](assets/figure-provenance.json) records the source PDF digest, pages, and crop bounds.
- The leaderboard is generated from the September 24, 2026 paper snapshot. A newer public release date does not imply newer model evaluations.

## Validation performed

The public snapshot passed source/input validation for all 105 tasks, including Web public-input integrity, result-to-input bindings, and Mobile frozen-file checks. Its offline regression suite reported **165 passed, 27 skipped, and 29 subtests passed** in a dedicated Python 3.11 environment. Skipped tests require additional native runtime capabilities. The leaderboard generator was checked against the source counts.

No paid model calls or full benchmark campaigns were executed during export. Source validation does not certify installed browser/CLI identities, live provider access, or end-to-end execution on a new host. Follow the [runtime requirements](evaluation.md#host-setup) before running the benchmark.

## Public provider interface

The public entry point `scripts/run_evaluation.py` accepts model IDs through Responses, Chat Completions, Anthropic Messages, and Bedrock Converse. It selects the same released manifests and records a separate provider-extension identity. Mobile also records its installed browser tree. The paper's original configurations remain available through the canonical dispatcher.

See the [README](../README.md#run-and-evaluate) for executable commands, [provider guide](providers.md) for endpoint configuration, and [agent guide](agents.md) for custom loops and CLIs.

## Provider update validation

The configurable-provider update passed **94 regression tests**, the 105-task release integrity check, and leaderboard consistency checks. HTTP fixtures exercised all four API formats, including tool results, screenshot payloads, authentication, and conversation continuation.

Native smoke evaluations completed on one released task in each domain using local mock model endpoints. Web, Game, and DevOps exercised code-only tool execution, audit, and verification; Mobile additionally exercised graphical observation, screenshot delivery, reference/negative controls, and evidence validation. Each unchanged submission was scored as a valid failed repair. These are integration checks; the leaderboard retains the published model evaluations.

## License status

Upstream license and attribution files are preserved. Original CUA-SWE material does not yet have a selected repository-wide license. Consult [third-party notices](../THIRD_PARTY_NOTICES.md) for the bundled components.

## Release checks

CI runs a pinned Gitleaks credential scan, the 105-task release integrity check, the leaderboard consistency check, and the offline regression tests. The Gitleaks allowlist contains ten exact reviewed non-secret values: seven content hashes, two model labels, and one browser storage key. Run the same checks locally:

```bash
python -m pip install -e '.[dev,evaluation]'
python scripts/check_release.py
python scripts/build_leaderboard.py --check
python -m pytest -q tests/test_canonical_evaluation_pipeline.py tests/test_web_frozen_runner.py tests/test_mobile_release.py tests/test_public_providers.py
```
