# Canonical Mobile evaluation

The canonical entrypoint dispatches the frozen synthetic Mobile tasks to the
protected evaluator ported from the completed campaign. It preserves the
source-only coding namespace, separate untrusted build namespace, trusted
native runtime, deterministic controls, clean final grading, screenshot
custody checks, and real native CLI execution.

## Protocol

- One attempt per selected task/model/condition; 60 model responses and 2,700
  seconds of active agent time; at most 16,384 output tokens per response.
- High reasoning for Responses routes; adaptive/high for Messages routes.
  Sampling parameters remain omitted. One transport attempt, with a request
  timeout no greater than 600 seconds or the remaining active budget.
- GPT-6 uses `gpt-6-astra` through the Responses API.
- The eight active API models support code-only and CUA. Codex uses the real
  0.155.1 CLI with GPT 5.6 Sol in CUA only. API Opus 5 and Claude Code Opus 5
  remain user-deferred (60 cells); their adapters are retained for lineage.
- Controls run before each attempt. Grading runs from a clean workspace after
  extracting permitted edits. Screenshot evidence is required for CUA success.
- Run up to four isolated evaluator processes. Audit after the batch. A
  provider/infrastructure fault holds further dispatch; in-flight attempts
  finish. No automatic retry, replacement, or conversion of exclusions to
  behavioral failures. Keep the original attempt and its diagnostics.
- Automated custody auditing is distinct from human failure attribution.
  A verifier failure alone is not proof of a genuine capability failure.

## Check or plan without model calls

```bash
python scripts/run_canonical_evaluation.py check
python scripts/run_mobile_evaluation.py --check
python scripts/run_mobile_evaluation.py --plan \
  --model api-gpt6-astra --condition cua --scope full \
  --output-root "$MOBILE_OUTPUT_ROOT/new-campaign"
```

## Operator environment

Execution requires Linux, user namespaces, Node, Git, fonts, the pinned
bubblewrap binary, and the evaluated Playwright browser tree. Use a dedicated
Python environment matching [requirements.lock](requirements.lock). The
browser tree must match the SHA-256 commitment in every task specification;
an unverified current browser download is insufficient. Bubblewrap must match
the evaluated binary commitment checked by `settings.validate_runtime`.

Supply deployment locations and provider routes in a **private JSON file**,
referenced with `--runtime-config`. Never commit this file or runtime logs.
Required keys are `output_root`, `python`, `venv`, `browsers`, `bwrap`,
`browser_bwrap`, and `providers`. Paths must be absolute and normalized. Python
must reside inside `venv`. Optional keys are `apparmor_profile` and
`cli_toolchain`. The latter contains `dependencies/` and the exact
`source-manifest.json` for native CLI runs.

The `providers` map uses route identifiers: `gpt56-sol`, `gpt56-luna`,
`gpt56-terra`, `gpt6-astra`, `grok46`, `claude-opus48`, `claude-sonnet5`,
`claude-fable5`, and `codex-sol`. Each value is
`{"base_url": "https://...", "api_key_env": "NAME"}`; the wire protocol is fixed
by the route (OpenAI Responses for GPT, Grok, and Codex routes; Anthropic
Messages for Claude routes), and requests go to `<base_url>/responses` or
`<base_url>/messages` through the shared provider layer
(`scripts/provider_client.py`). The key is read from the named variable in the
evaluator's host environment (`NONE` for an unauthenticated local endpoint).
Keys and this configuration stay in the host evaluator process and its
host-only CLI transport worker; they never enter the agent or build namespace.

```json
{
  "providers": {
    "gpt6-astra": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
    "claude-opus48": {"base_url": "https://api.anthropic.com/v1", "api_key_env": "ANTHROPIC_API_KEY"}
  }
}
```

For Codex, preserve the exact installation described by
[cli-source-manifest.json](cli-source-manifest.json) and the pinned
[model-catalog.json](model-catalog.json). Verification checks every package
file and confines dependency symlinks. A different CLI version is a new
protocol revision, not a transparent replacement.

## Execute

An explicit `run` command authorizes model calls. Choose a new campaign
subdirectory inside the configured `output_root`:

```bash
python scripts/run_canonical_evaluation.py run \
  --domain mobile --scope full --model api-gpt6-astra --condition cua \
  --runtime-config "$MOBILE_RUNTIME_CONFIG" \
  --output-root "$MOBILE_OUTPUT_ROOT/new-campaign" --max-workers 4
```

The launcher claims each cell once, resolves the frozen inputs, records the
pre-dispatch task/protocol/harness identities, and writes original attempts,
post-batch custody reviews, and a summary. Existing campaign directories are
rejected. A new campaign does not silently replace any published result.

## Port and verification

The task inputs are byte-preserved. Package imports and trusted deployment
settings were made portable, and model requests use the shared provider layer
with operator-configured routes. The canonical scheduler
replaces campaign-specific queue wrappers, and CLI files are checked against
exact public file pins. The relocated evaluator has its own
[runtime manifest](runtime-manifest.json) rather than the original harness digest. Source lineage retains the original
module hashes and enumerates these changes.

The frozen regression suite covers namespace separation, protected file
custody, negative controls, candidate error attribution, deadlines, provider
receipts, image binding, and route selection. Native integration tests require
the Linux environment above. Release tests also verify all input bytes and
apply every relocated control without model calls:

```bash
python -m pytest -q tests/test_mobile_release.py tests/test_mobile_frozen*.py
```
