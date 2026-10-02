# Integrating your agent

CUA-SWE supplies source workspaces, application environments, screenshot/action tools, independent verifiers, and result records. Choose an integration according to what you want to change:

| Integration | Entry point |
| --- | --- |
| Your model on a supported API, using the baseline agent loop | [`run_evaluation.py`](../scripts/run_evaluation.py), with `--provider`, `--model`, and optional `--base-url` |
| A new wire protocol | [`ProviderClient`](../scripts/provider_client.py) and its [transport contract](providers.md#extending-the-transport) |
| Your own agent loop or CLI | Domain adapter interfaces below |

## Web, Game, and DevOps

[`public_taskbundle.py`](../scripts/public_taskbundle.py) is a complete provider extension. It selects an arbitrary model ID, builds the isolated tool packet, records the extension's source hashes, and delegates workspace setup, browser access, patch extraction, and verification to the domain runner.

The API agent executable receives this interface:

```text
python agent_adapter.py \
  --model MODEL_ID \
  --workspace SOURCE_WORKSPACE \
  --rollout-dir ARTIFACT_DIRECTORY \
  --prompt TASK_PROMPT [--code-only]
```

[`run_provider_agent.py`](../scripts/run_provider_agent.py) implements it using the baseline Responses-style agent loop. `agent_adapter.py` above names the interface your implementation provides.

To integrate a custom loop:

1. Add your adapter and its supporting files to the extension's tool packet. The packet is mounted with the agent's permitted source workspace.
2. Launch it through the existing audited wrapper, using the supplied workspace, prompt, model configuration, and artifact directory.
3. Connect source operations to the provided shell and computer-use operations to the protected launcher described in the prompt.
4. Record model turns, tool calls/results, token usage, image delivery, termination, and final source changes in the supported transcript format. Add an audit parser if your agent emits a different format.
5. Exercise the task's controls and one-task run, then evaluate the manifest gate and full collection.

| Runtime value | Meaning |
| --- | --- |
| Working directory / `--workspace` | Editable source workspace |
| `CUA_SWE_TASK_ID` / `CUA_SWE_TASK_INSTRUCTION` | Selected task identity and instruction |
| `CUA_SWE_BUILD_COMMAND` | Public application build command |
| `CUA_SWE_AGENT_ROLLOUT_DIR` | Agent artifact directory |
| `CUA_SWE_WEB_CUA_LAUNCHER` | Protected screenshot/action tool, in CUA mode |
| `CUA_SWE_WEB_URL` / `CUA_SWE_WEB_VIEWPORT` | Application address and viewport |

The baseline loop exposes `shell`, `view_image`, and `finish`. `shell` invokes the computer-use launcher; `view_image` sends its screenshot pixels to the model. The [provider adapter tests](../tests/test_public_providers.py) exercise image delivery and tool-call continuation across all four APIs.

The domain runners own application startup, operational state, source extraction, and final verification. Their main extension points are `_expected_tool_names`, `_copy_isolated_tools`, `_agent_command`, and the transcript audit helpers in the corresponding runner:

- Web: [`scripts/frozen_web/scripts/run_clean_ablation.py`](../scripts/frozen_web/scripts/run_clean_ablation.py).
- Game: [`scripts/run_game_clean_ablation.py`](../scripts/run_game_clean_ablation.py).
- DevOps: [`scripts/run_clean_ablation.py`](../scripts/run_clean_ablation.py).

## Mobile

[`public_mobile.py`](../scripts/public_mobile.py) integrates configurable providers with Mobile's native application runtime, source sandbox, controls, and grader.

A provider client factory receives `(protocol, tools, root)` and returns a client implementing `create(items, previous_response_id=...)`. [`ProviderClient`](../scripts/provider_client.py) is the ready-to-use implementation for Responses, Chat Completions, Messages, and Converse.

A custom loop implements the equivalent of:

```text
Agent(task, baseline, sandbox, runtime, condition, artifact_root, client_factory)
```

Use `sandbox` for source/build operations and `runtime` for graphical interaction. The baseline [`Agent`](../src/cua_swe_bench/mobile_evaluation/agent.py) provides the state/receipt schema consumed by [`run_attempt`](../src/cua_swe_bench/mobile_evaluation/runner.py) and the evidence auditor. The browser tool supports screenshots, reload, click, long press, drag, typing, key presses, and scroll.

The evaluator runs baseline and reference controls, prepares the source workspace, invokes the loop, extracts its patch, and grades the patch in a clean runtime. Preserve this lifecycle in a custom integration and record its own protocol and source identity.

## Reporting new results

Include the task release, model/agent version, provider interface, evaluator extension hash, runtime identity, condition, budget, success count, denominator, and exclusions. For Web, retain native verifier success and reported success. For Mobile, retain the per-attempt classification and image-delivery evidence.

The benchmark's model/API integration works directly from the README commands. A custom agent loop or CLI uses the adapter contract above so its tools, trace format, and evaluation lifecycle are defined together.
