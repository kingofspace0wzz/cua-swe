# Protected environment inputs

`service.py` is an evaluator-owned loopback lifecycle service. It exposes only
the literal `/health` readiness endpoint and contains no gameplay data,
benchmark answers, verifier thresholds, or repair behavior.

The public game uses only the fixed seed and level declared in `task.yaml`.
Protected replay assertions live in the evaluator-owned browser verifier and
candidate contracts, not in this service or the agent-visible source.
