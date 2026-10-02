#!/usr/bin/env python3
"""Manifest-driven entry point for every formal CUA-SWE evaluation."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "dataset/evaluation/pipelines.yaml"
REGISTRY_PATH = REPO_ROOT / "dataset/registry.json"
WEB_TASK_DIGEST_EXCLUDES = frozenset({
    ".git", ".next", ".pytest_cache", "__pycache__", "dist",
    "node_modules", "verifier-artifacts",
})


def _load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def _task_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("tasks")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("manifest tasks must be a list of objects")
    return rows


def _model_for_domain(
    catalog: dict[str, Any], domain: dict[str, Any], key: str
) -> dict[str, Any]:
    model = (catalog.get("models") or {}).get(key)
    if not isinstance(model, dict):
        raise ValueError(f"unknown model: {key}")
    # A Web host adapter does not enable that adapter for other domains.
    override = (domain.get("model_overrides") or {}).get(key, {})
    return {**model, **override}


def _validate_evaluation_summary(
    catalog: dict[str, Any],
    spec: dict[str, Any],
    task_rows: list[dict[str, Any]],
) -> list[str]:
    """Bind the promoted inventory to saved results without rescoring them."""
    reference = spec.get("evaluation_summary")
    if not reference:
        return []
    path = REPO_ROOT / str(reference["path"])
    if not path.is_file():
        return [f"missing evaluation summary: {path}"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
        return ["evaluation summary digest mismatch"]
    summary = _load(path)
    inputs = {
        str(row["task_id"]): row.get("evaluated_task_input_sha256")
        for row in task_rows
    }
    cells = {
        (key, condition)
        for key in catalog["models"]
        for model in [_model_for_domain(catalog, spec, key)]
        if model.get("status") in {None, "active"}
        for condition in model.get("conditions", [])
    }
    expected = {
        (task_id, model, condition)
        for task_id in inputs
        for model, condition in cells
    }
    rows = summary.get("rows") or []
    actual = [
        (row.get("task_id"), row.get("model"), row.get("condition"))
        for row in rows
    ]
    errors = []
    if len(actual) != len(set(actual)) or set(actual) != expected:
        errors.append("evaluation summary does not cover the exact task/model/condition matrix")
    if summary.get("task_count") != len(inputs) or summary.get("attempt_count") != len(rows):
        errors.append("evaluation summary counts disagree with its rows")
    if any(
        row.get("evaluated_task_input_sha256") != inputs.get(row.get("task_id"))
        for row in rows
    ):
        errors.append("evaluation summary task-input lineage differs from the manifest")
    return errors


def _validate_model_registry(catalog: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Check the actual frozen route table without importing a model runner."""
    reference = spec.get("model_registry")
    if not reference:
        return []
    path = REPO_ROOT / str(reference["path"])
    if not path.is_file():
        return [f"missing model registry: {path}"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference["sha256"]:
        return ["model registry digest mismatch"]
    tree = ast.parse(data)
    routes: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == "MODELS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.List):
            return ["model registry must contain the frozen literal MODELS table"]
        for entry in node.value.elts:
            if (
                not isinstance(entry, ast.Call)
                or not isinstance(entry.func, ast.Name)
                or entry.func.id != "ModelSpec"
                or len(entry.args) != 4
            ):
                return ["unsupported entry in frozen model registry"]
            key, _label, runtime, model_id = [
                ast.literal_eval(value) for value in entry.args
            ]
            routes[key] = {"runtime": runtime, "model_id": model_id}
    errors = []
    for key in catalog["models"]:
        model = _model_for_domain(catalog, spec, key)
        if model.get("status") not in {None, "active"}:
            continue
        expected = {field: model.get(field) for field in ("runtime", "model_id")}
        if routes.get(key) != expected:
            errors.append(f"model route differs from frozen runner: {key}")
    return errors


def _task_digests(root: Path, original_yaml: bytes) -> tuple[str, str]:
    """Evaluated tree algorithm, with a second digest restoring only task.yaml."""
    canonical, evaluated = hashlib.sha256(), hashlib.sha256()
    entries = sorted(
        (path for path in root.rglob("*")
         if (path.is_file() or path.is_symlink())
         and not any(part in WEB_TASK_DIGEST_EXCLUDES
                     for part in path.relative_to(root).parts)),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in entries:
        relative = path.relative_to(root).as_posix()
        kind = b"symlink\0" if path.is_symlink() else b"file\0"
        prefix = relative.encode() + b"\0" + kind
        canonical.update(prefix)
        evaluated.update(prefix)
        if path.is_symlink():
            data = os.readlink(path).encode()
            canonical.update(data)
            evaluated.update(data)
        else:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    canonical.update(chunk)
                    if relative != "task.yaml":
                        evaluated.update(chunk)
            if relative == "task.yaml":
                evaluated.update(original_yaml)
        canonical.update(b"\0")
        evaluated.update(b"\0")
    return canonical.hexdigest(), evaluated.hexdigest()


def _validate_task_lineage(
    spec: dict[str, Any], task_rows: list[dict[str, Any]]
) -> list[str]:
    reference = spec.get("task_lineage")
    if not reference:
        return []
    path = REPO_ROOT / str(reference["path"])
    if not path.is_file():
        return [f"missing task lineage: {path}"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
        return ["task lineage digest mismatch"]
    lineage = _load(path)
    if set(lineage.get("task_digest_excludes") or []) != WEB_TASK_DIGEST_EXCLUDES:
        return ["task lineage uses different evaluated digest exclusions"]
    records = lineage.get("tasks") or []
    by_id = {record["task_id"]: record for record in records}
    if len(by_id) != len(records) or set(by_id) != {row["task_id"] for row in task_rows}:
        return ["task lineage does not cover the exact manifest"]
    errors = []
    for row in task_rows:
        task_id = row["task_id"]
        record = by_id[task_id]
        task_file = REPO_ROOT / row["task_file"]
        original_path = REPO_ROOT / record["original_task_yaml"]
        if not task_file.is_file() or not original_path.is_file():
            errors.append(f"missing canonical/original task YAML: {task_id}")
            continue
        original = original_path.read_bytes()
        if (
            task_file.is_symlink()
            or hashlib.sha256(original).hexdigest() != record.get("public_original_task_yaml_sha256", record["evaluated_task_yaml_sha256"])
            or hashlib.sha256(task_file.read_bytes()).hexdigest()
            != record["canonical_task_yaml_sha256"]
            or row["task_file"] != record["task_file"]
        ):
            errors.append(f"task YAML binding mismatch: {task_id}")
            continue
        canonical_yaml, evaluated_yaml = _load(task_file), _load(original_path)
        snapshot_path = canonical_yaml["repo_snapshot"]["path"]
        canonical_yaml["repo_snapshot"]["path"] = evaluated_yaml["repo_snapshot"]["path"]
        if (
            canonical_yaml != evaluated_yaml
            or canonical_yaml.get("id") != task_id
            or (REPO_ROOT / snapshot_path).resolve() != (task_file.parent / "repo").resolve()
        ):
            errors.append(f"task relocation changes more than its snapshot path: {task_id}")
            continue
        canonical, evaluated = _task_digests(task_file.parent, original)
        if canonical != row.get("task_digest") or canonical != record["canonical_task_digest"]:
            errors.append(f"canonical task digest mismatch: {task_id}")
        if (
            evaluated != record.get("public_original_yaml_restored_digest", record["original_yaml_restored_digest"])
            or row.get("evaluated_task_input_sha256") != record["evaluated_task_input_sha256"]
            or record["evaluated_task_input_sha256"] != record["original_yaml_restored_digest"]
            or record["evaluated_task_input_sha256"] != record["recorded_evaluation_component_pins"]["task_input_sha256"]
            or record["evaluated_task_yaml_sha256"] != record["recorded_evaluation_component_pins"]["task_file_sha256"]
        ):
            errors.append(f"published task digest or historical input binding mismatch: {task_id}")
    return errors


def validate_catalog() -> dict[str, Any]:
    catalog = _load(CATALOG_PATH)
    registry = _load(REGISTRY_PATH)
    registry_domains = {
        str(row["domain"]): row for row in registry.get("domains", [])
    }
    errors: list[str] = []
    domains: dict[str, Any] = {}
    for name, spec in (catalog.get("domains") or {}).items():
        manifest_path = REPO_ROOT / str(spec["manifest"])
        if not manifest_path.is_file():
            errors.append(f"{name}: missing manifest {manifest_path}")
            continue
        manifest = _load(manifest_path)
        rows = _task_rows(manifest)
        expected = int(spec["task_count"])
        if manifest.get("task_count") != expected or len(rows) != expected:
            errors.append(f"{name}: expected {expected} manifest tasks")
        registry_row = registry_domains.get(name)
        task_ids = [str(row.get("task_id") or "") for row in rows]
        if registry_row is None:
            errors.append(f"{name}: absent from dataset/registry.json")
        elif task_ids != list(registry_row.get("task_ids") or []):
            errors.append(f"{name}: manifest IDs differ from the global registry")
        missing: list[str] = []
        if spec.get("bundle_format") == "task_yaml":
            for row in rows:
                task_file = REPO_ROOT / str(row.get("task_file") or "")
                if not task_file.is_file():
                    missing.append(str(task_file))
        if missing:
            errors.append(f"{name}: missing {len(missing)} task files")
        if name == "mobile":
            sys.path.insert(0, str(REPO_ROOT / "src"))
            from cua_swe_bench.mobile_evaluation.release import validate_release
            try:
                validate_release(REPO_ROOT)
            except (ValueError, KeyError, OSError) as exc:
                errors.append(f"mobile: {exc}")
        else:
            errors.extend(
                f"{name}: {error}"
                for error in _validate_evaluation_summary(catalog, spec, rows)
            )
            errors.extend(
                f"{name}: {error}"
                for error in _validate_model_registry(catalog, spec)
            )
            errors.extend(
                f"{name}: {error}"
                for error in _validate_task_lineage(spec, rows)
            )
        domains[name] = {
            "status": spec.get("status"),
            "task_count": len(rows),
            "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        }
        if spec.get("model_overrides"):
            domains[name]["model_overrides"] = spec["model_overrides"]
    runner_paths: set[Path] = set()
    default_runner = catalog.get("protected_runner")
    if default_runner:
        runner_paths.add(REPO_ROOT / str(default_runner))
    for name, spec in (catalog.get("domains") or {}).items():
        runner_value = spec.get("protected_runner", default_runner)
        runner = REPO_ROOT / str(runner_value or "")
        runner_paths.add(runner)
        if not runner.is_file():
            errors.append(f"{name}: missing protected runner {runner}")
            continue
        expected_sha256 = spec.get("protected_runner_sha256")
        if expected_sha256:
            actual_sha256 = hashlib.sha256(runner.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                errors.append(
                    f"{name}: protected runner digest mismatch: "
                    f"expected {expected_sha256}, got {actual_sha256}"
                )
    for runner in runner_paths:
        if not runner.is_file():
            errors.append(f"missing protected runner: {runner}")
    return {
        "schema_version": 1,
        "valid": not errors,
        "errors": errors,
        "domains": domains,
        "models": catalog.get("models") or {},
    }


def build_command(args: argparse.Namespace) -> list[str]:
    catalog = _load(CATALOG_PATH)
    domain = (catalog.get("domains") or {}).get(args.domain)
    if not isinstance(domain, dict):
        raise ValueError(f"unknown domain: {args.domain}")
    if domain.get("status") != "active":
        raise ValueError(
            f"{args.domain} evaluation is {domain.get('status')}: "
            f"{domain.get('reason', 'no canonical runner')}"
        )
    model = _model_for_domain(catalog, domain, args.model)
    if model.get("status") not in {None, "active"}:
        raise ValueError(
            f"{args.model} is {model.get('status')}: {model.get('reason')}"
        )
    if args.condition not in (model.get("conditions") or []):
        raise ValueError(f"{args.model} does not support {args.condition}")
    if args.domain == "mobile":
        command = [str(args.python.expanduser().absolute()),
                   str(REPO_ROOT / domain["protected_runner"]),
                   "--model", args.model, "--condition", args.condition,
                   "--scope", args.scope, "--output-root", str(args.output_root.expanduser().absolute()),
                   "--max-workers", str(args.max_workers)]
        if getattr(args, "runtime_config", None):
            command.extend(("--runtime-config", str(args.runtime_config.expanduser().absolute())))
        if getattr(args, "command", None) == "plan":
            command.append("--plan")
        return command
    if not args.execution_host:
        raise ValueError("--execution-host is required for this domain")
    manifest = _load(REPO_ROOT / str(domain["manifest"]))
    rows = _task_rows(manifest)
    if args.scope == "gate":
        rows = rows[: int(catalog["gate_task_count"])]
    task_files = [REPO_ROOT / str(row["task_file"]) for row in rows]
    runner = domain.get("protected_runner", catalog.get("protected_runner"))
    command = [
        str(args.python.expanduser().absolute()),
        str(REPO_ROOT / str(runner)),
        "--attempts", "1",
        "--max-workers", str(args.max_workers),
        "--model", args.model,
        "--run-attempt", "1",
        "--shard-id", args.shard_id or f"{args.domain}-{args.scope}-{args.condition}-{args.model}",
        "--execution-host", args.execution_host,
        "--output-root", str(args.output_root.expanduser().absolute()),
        "--python", str(args.python.expanduser().absolute()),
    ]
    command.extend(domain.get("runner_args") or [])
    command.append("--code-only-only" if args.condition == "code-only" else "--cua-only")
    if args.condition == "cua":
        command.append("--visual-cua")
    for task_file in task_files:
        command.extend(("--task-file", str(task_file)))
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check, plan, or run the canonical per-domain evaluation pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    subparsers.add_parser("show")
    for name in ("plan", "run"):
        child = subparsers.add_parser(name)
        child.add_argument("--domain", required=True, choices=("web", "game", "mobile", "devops"))
        child.add_argument("--scope", choices=("gate", "full"), default="gate")
        child.add_argument("--condition", choices=("code-only", "cua"), required=True)
        child.add_argument("--model", required=True)
        child.add_argument("--output-root", type=Path, required=True)
        child.add_argument("--execution-host")
        child.add_argument("--runtime-config", type=Path, help="Private Mobile host configuration")
        child.add_argument("--shard-id")
        child.add_argument("--max-workers", type=int, default=1)
        child.add_argument("--python", type=Path, default=Path(sys.executable))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = validate_catalog()
    if args.command in {"check", "show"}:
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0 if validation["valid"] else 2
    if not validation["valid"]:
        raise SystemExit("\n".join(validation["errors"]))
    try:
        command = build_command(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"command": command}, indent=2), flush=True)
    if args.command == "plan":
        return 0
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
