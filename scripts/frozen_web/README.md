# Frozen Web evaluator

This source copy preserves the evaluator used for the selected 720 Web36
rows. Invoke it through `scripts/run_web_clean_ablation.py`; canonical task and
model selection remains in `scripts/run_canonical_evaluation.py`.

The per-file hashes and the 41-file BASE harness digest are in
`source-pins.json`; the launcher validates them before every run.

The runner separates `FROZEN_ROOT` (this directory's scripts and Python package)
from `REPO_ROOT` (the containing checkout's tasks, source-access policy and
repository mask), and the model matrix uses the current Python interpreter.

Every model call goes through the repository provider layer. The runner starts
the authenticated gateway in `scripts/provider_relay.py` on the controller; it
holds the API credentials and forwards each request to the endpoint configured
for its wire protocol. Each trial gets a lease token valid only for its protocol
and model, passed in the agent's environment and revoked when the trial ends.
Agents, including the Codex and Claude Code CLIs, receive only a loopback
gateway URL and that lease, never an API key. Configure upstream endpoints and key
variables with `CUA_SWE_PROVIDER_ROUTES` (see
[docs/providers.md](../../docs/providers.md)); without it, Responses traffic goes
to the OpenAI API and Messages traffic to the Claude API. The runner copies
`scripts/provider_client.py` from the checkout into each isolated tool packet, and
the package adds `provider_layer.py` to locate that shared layer.
The separately pinned retention extension uses a relative BASE path and updated
expected hashes for that portable runner.

`dataset/manifest.yaml` is the exact 42-name table imported by the
frozen model matrix. It is not the canonical task selector. Formal Web36 calls
must pass the canonical dispatcher's explicit `--task-file` list. Retained model
routes outside the canonical catalog are not additional admitted conditions.

The launcher validates all source pins before importing this package in
a fresh Python process. Generic, Game and DevOps runners keep their own imports.
This is a source freeze, not a self-contained runtime image: Python packages,
Node, browser, sandbox/tracing tools and CLI binaries still require a compatible
host. Do not substitute installed client versions for the evaluated CLI pins or
claim provider availability from source validation.

Before the startup version probes and again before each actual CLI CUA trial,
the outer Web support module validates the
PATH-resolved client against `runtime-pins.json`: both Codex's launcher and its
unique native binary, or Claude's resolved native binary. It does not execute
clients, contact providers or read credentials. A mismatch records a runtime
preflight failure with unknown native/reported outcomes and stops before trial
execution; an initial refusal can precede output-root creation. Dispatcher
plan/check and entrypoint help/dry-run do not perform this probe.
These hashes are a point-in-time check, not an immutable executable lease or
validation of Node, libraries, browsers, OS or provider availability.

New runs also emit `canonical-web-results.json` beside the unmodified native
summary. Each row separates `native_success` from `legacy_reported_success`.
The latter uses the evaluated protocol-compliance and CUA-evidence predicate,
without adding diagnostic budget checks. Missing outcomes remain unknown.
This projection and the runtime guard are separately pinned support code;
neither changes the 41-file BASE digest or the saved scores.
