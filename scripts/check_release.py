#!/usr/bin/env python3
"""Check public release completeness and frozen inputs without model requests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml
from run_canonical_evaluation import validate_catalog
from run_web_clean_ablation import validate_frozen_sources
from build_leaderboard import load_scores


def main():
    result = validate_catalog()
    errors = list(result["errors"])
    inventory = json.loads((ROOT / "dataset/release-files.json").read_text())
    if inventory["file_count"] != len(inventory["files"]):
        errors.append("release input inventory count differs")
    for record in inventory["files"]:
        path = ROOT / record["path"]
        try:
            if record["kind"] == "symlink":
                data = path.readlink().as_posix().encode()
            else:
                if path.is_symlink():
                    raise ValueError("file replaced by symlink")
                data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                errors.append(f"release input changed: {record['path']}")
        except (OSError, ValueError):
            errors.append(f"release input missing or wrong type: {record['path']}")
    try:
        validate_frozen_sources()
        load_scores()
    except (ValueError, RuntimeError, KeyError, OSError) as exc:
        errors.append(str(exc))
    catalog = yaml.safe_load((ROOT / "dataset/evaluation/pipelines.yaml").read_text())
    count = 0
    for domain, spec in catalog["domains"].items():
        if domain == "mobile":
            count += spec["task_count"]  # Input and runtime hashes checked by validate_catalog.
            continue
        manifest = yaml.safe_load((ROOT / spec["manifest"]).read_text())
        for row in manifest["tasks"]:
            task_path = ROOT / row["task_file"]
            task = yaml.safe_load(task_path.read_text())
            snapshot = (ROOT / task["repo_snapshot"]["path"]).resolve()
            if snapshot != (task_path.parent / "repo").resolve() or not snapshot.is_dir():
                errors.append(f"missing or misdirected source snapshot: {row['task_id']}")
            count += 1
    import run_game_clean_ablation as game
    import run_clean_ablation as devops
    for module in (game, devops):
        for condition in ("code-only", "cua"):
            for runtime in ("responses", "anthropic", "codex"):
                for name in module._expected_tool_names(condition, runtime):
                    if not (ROOT / "scripts" / name).is_file():
                        errors.append(f"missing isolated tool: {name}")
    if count != 105:
        errors.append(f"expected 105 task inputs, found {count}")
    print(json.dumps({"valid": not errors, "task_count": count, "domains": result["domains"],
                      "errors": errors, "model_calls": 0,
                      "scope": "Source and input validation; runtime/provider readiness requires separate checks."}, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
