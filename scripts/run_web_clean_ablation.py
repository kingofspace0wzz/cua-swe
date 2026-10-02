#!/usr/bin/env python3
"""Run the portable, source-pinned Web evaluator in a fresh Python process.

Canonical task/model selection belongs to run_canonical_evaluation.py. This
entrypoint verifies the private dependency closure before importing it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

FROZEN_ROOT = Path(__file__).resolve().parent / "frozen_web"
SOURCE_PINS_SHA256 = "9cb72f97a45cb75bd7add5503470e7796118f9913068ef50ab0c75341ce8a4cd"


def validate_frozen_sources(root: Path = FROZEN_ROOT) -> dict:
    """Validate bytes without importing the evaluator or accessing a provider."""
    manifest = root / "source-pins.json"
    raw = manifest.read_bytes()
    if manifest.is_symlink() or hashlib.sha256(raw).hexdigest() != SOURCE_PINS_SHA256:
        raise RuntimeError("frozen Web source-pins digest mismatch")
    pins = json.loads(raw)
    digest = hashlib.sha256()
    expected_package_files = set()
    for group in ("harness_files", "support_files"):
        for record in pins[group]:
            relative = record["path"]
            path = root / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise RuntimeError("invalid frozen Web source path")
            if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
                raise RuntimeError(f"frozen Web source must not be a symlink: {relative}")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise RuntimeError(f"frozen Web source digest mismatch: {relative}")
            if group == "harness_files":
                digest.update(relative.encode())
                digest.update(b"\0")
                digest.update(data)
                digest.update(b"\0")
                if relative.startswith("src/cua_swe_bench/"):
                    expected_package_files.add(relative)
    actual_package_files = {
        p.relative_to(root).as_posix()
        for p in (root / "src/cua_swe_bench").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    if actual_package_files != expected_package_files:
        raise RuntimeError("frozen Web package inventory mismatch")
    if digest.hexdigest() != pins["portable_harness_sha256"]:
        raise RuntimeError("frozen Web composite harness digest mismatch")
    return pins


def main() -> int:
    validate_frozen_sources()
    conflicting = {
        name for name in sys.modules
        if name == "cua_swe_bench" or name.startswith("cua_swe_bench.")
        or name in {"run_clean_ablation", "run_model_matrix",
                    "render_web_agent_prompt"}
    }
    if conflicting:
        raise RuntimeError("the frozen Web evaluator requires a fresh Python process")
    sys.path[:0] = [
        str(FROZEN_ROOT / "scripts"),
        str(FROZEN_ROOT / "src"),
    ]
    spec = importlib.util.spec_from_file_location(
        "_web_frozen_retention", FROZEN_ROOT / "retention_entrypoint.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the frozen Web retention entrypoint")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    harness = importlib.import_module("run_clean_ablation")
    module.install(harness)
    support_spec = importlib.util.spec_from_file_location(
        "_web_frozen_runtime_reporting", FROZEN_ROOT / "runtime_and_reporting.py"
    )
    if support_spec is None or support_spec.loader is None:
        raise RuntimeError("cannot load Web runtime/reporting support")
    support = importlib.util.module_from_spec(support_spec)
    sys.modules[support_spec.name] = support
    support_spec.loader.exec_module(support)
    runtime_pins = json.loads((FROZEN_ROOT / "runtime-pins.json").read_text())
    support.install(harness, runtime_pins)
    return harness.main()


if __name__ == "__main__":
    raise SystemExit(main())
