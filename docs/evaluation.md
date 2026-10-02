# Running CUA-SWE evaluations

Use [`scripts/run_evaluation.py`](../scripts/run_evaluation.py) to evaluate a model through Responses, Chat Completions, Anthropic Messages, or Bedrock. The [README](../README.md#quick-start) gives installation and provider commands. This guide explains host setup, task selection, domain behavior, and outputs.

## Host setup

| Component | Configuration |
| --- | --- |
| OS | Linux with user namespaces and bubblewrap |
| Python | Python 3.11+ in a virtual environment; use the same executable for installation and evaluation |
| TaskBundle tools | Git, npm, `strace` with `--always-show-pid` and `--decode-pids=pidns`, GNU `timeout`, and a C compiler |
| Browser | Playwright Chromium and its OS dependencies. Web UI verifiers launch Chrome at `/usr/bin/google-chrome`; without it they use the newest Chromium in the Playwright browser cache. Set `CUA_SWE_VERIFIER_CHROME_PATH` to choose another Chrome inside that cache |
| Web / DevOps | Node version required by the selected application's package; modern tasks use Node 22.22.2+ |
| Game | Node 18 and Java 17 on the system task path (`/usr/bin:/bin:/usr/local/bin`) |
| TaskBundle bootstrap | `@openai/codex@0.146.0`, installed with nested dependencies as shown in the README |
| Mobile | Generated runtime JSON describing Python, Chromium, bubblewrap, and output locations |

On a host that needs multiple Node versions, keep Node 18 on Game's system task path and select Node 22.22.2+ in the interactive shell for Web/DevOps. Agent tools are installed separately under `$VIRTUAL_ENV/agent-tools`.

Check sandbox availability:

```bash
bwrap --ro-bind / / --unshare-user --unshare-pid --proc /proc /bin/true
strace --always-show-pid --decode-pids=pidns -e trace=execve /bin/true
node --version
java -version
python scripts/check_release.py
```

Application dependencies are installed using each task's declared setup commands. Allow network access during setup. Source/build commands and provider requests use the evaluator's corresponding execution boundaries.

## Task selection

Each invocation selects exactly one domain manifest. `--scope gate` selects its first 10 tasks; `--scope full` selects all tasks. Repeat `--task-id` to choose an explicit subset; this takes precedence over scope.

```bash
python scripts/run_evaluation.py plan --domain game --scope full "${API[@]}"
python scripts/run_evaluation.py run --domain game "${API[@]}" \
  --task-id gameqa.2048-seeded-restart-parity.002 --condition code-only \
  --output-root "$PWD/artifacts/game-single"
```

`API` is the Bash array configured in the [README](../README.md#choose-your-api-provider). Each run gets a new output directory. The default concurrency is one task. Web and Game accept `--max-workers N`; Mobile and DevOps use one worker.

## Web

Web runs 36 application tasks through its retained protected evaluator. It prepares source, serves the application, provides the browser tool, extracts changes, and runs independent verifiers. `cua` adds screenshot-based interaction; `code-only` provides source and terminal access.

`runner/canonical-web-results.json` contains `native_success` and `legacy_reported_success`. The former is the verifier outcome; the latter additionally applies Web's protocol and CUA-evidence requirements. The raw trial and summary files retain the underlying evidence.

## Game

Game runs 29 tasks across 12 games. Task runtimes resolve system Node 18 and Java 17. The evaluator retains the game's startup contract, seeded behavior, screenshot/action interface, and deterministic gameplay verifiers.

Each command schedules one attempt per selected task. The paper's repeated-attempt Game results are published separately in [results](../results/README.md).

## DevOps

DevOps runs 20 tasks using the shared TaskBundle evaluator. The evaluator starts the task's application and operational services, supplies the editable source, and grades the final configuration and behavior against fresh service state.

## Mobile

Mobile runs 20 browser-based mobile application tasks with a dedicated native runtime. Configure it once per local Python/browser installation:

```bash
python scripts/configure_mobile_runtime.py \
  --output mobile-runtime-config.local.json \
  --output-root "$PWD/artifacts/mobile"
```

Use `--browsers /absolute/browser/directory` or `--bwrap /absolute/path/to/bwrap` when those runtimes are installed elsewhere. Choose evaluation output directories under the configured `output_root`.

```bash
python scripts/run_evaluation.py run --domain mobile "${API[@]}" \
  --task-id mobile.synthetic.external-wallchart-schedule.005 \
  --condition cua --runtime-config mobile-runtime-config.local.json \
  --output-root "$PWD/artifacts/mobile/single"
```

Before the agent runs, the evaluator captures baseline state and verifies broken, gold, alternative, and partial controls. It then prepares a source sandbox, exposes screenshot/coordinate actions, extracts the agent's source changes, and grades them in a clean application instance. Failed repairs receive a pristine replay.

The public Mobile protocol records the installed browser tree and binds the relocated task and controls to that runtime. The task source and verifier remain the released versions. Each attempt records 60-response / 2,700-active-second budgets, provider usage, image delivery, runtime identity, and grading evidence.

## Reading results

All domains write `evaluation.json` with task selection and provider/extension metadata. `completion.json` records process exit status. A successful process exit means the evaluator completed; task success comes from its result records.

| Domain | Main results | Per-task evidence |
| --- | --- | --- |
| Web | `runner/summary.json`, `runner/canonical-web-results.json` | `runner/trials/` |
| Game / DevOps | `runner/summary.json` | `runner/trials/` |
| Mobile | `summary.json` | `attempts/TASK_ID/attempt.json` |

TaskBundle rows include verifier results, protocol compliance, CUA evidence, and infrastructure status. Mobile rows contain classification, evidence validity, and software correctness. An excluded/infrastructure result has no model success score. Report success counts, scored denominators, and exclusions for each domain and condition.

The public extension identity distinguishes configurable-provider runs from the paper's recorded baseline configurations. Report that identity, the endpoint/model version, installed runtime, and condition with new results.

## Paper configurations

[`scripts/run_canonical_evaluation.py`](../scripts/run_canonical_evaluation.py) retains the paper's model catalog and configuration commitments:

```bash
python scripts/run_canonical_evaluation.py show
python scripts/run_canonical_evaluation.py plan \
  --domain web --scope full --model api-gpt6-astra --condition cua \
  --execution-host local --output-root "$PWD/artifacts/paper-web-plan"
```

The configuration, runtime, and model registrations for that route are in [`dataset/evaluation/pipelines.yaml`](../dataset/evaluation/pipelines.yaml). The public provider entry point accepts additional model IDs and API interfaces directly.
