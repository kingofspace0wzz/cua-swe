# CUA-SWE benchmark data

[registry.json](registry.json) is the release allowlist: 36 Web, 29 Game, 20 Mobile, and 20 DevOps tasks. Domain manifests define their order and evaluation membership.

Each domain keeps task source, protected environments, and tests together. `manifest.yaml` is the 42-name compatibility table required when importing the retained baseline model registry; its entries do not select the public benchmark. `collections/game-cua/tasks/game` is a compatibility link to the canonical Game task directory.

Use the [evaluation guide](../docs/evaluation.md) and [agent integration guide](../docs/agents.md). Do not expose the complete dataset checkout to an evaluated agent.
