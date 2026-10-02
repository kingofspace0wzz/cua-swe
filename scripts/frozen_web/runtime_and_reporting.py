"""Web-only runtime admission and separate legacy/native reporting.

The 41-file BASE and all raw trial/native outputs remain unchanged.
The CUA disposition below is copied from the evaluated canonical helper
(SHA 56af4077d1040056a6c4675bf0c10cc193862a98004e8a72bfabfc597c10aaf0,
lines 98–133); reported_success is the evaluated corrected Web predicate
(SHA bdd52a6ca2a752cf573512d82166f1e82b58c61090fde3f0d2445fb122e38905,
lines 198–203).
"""
from __future__ import annotations

from functools import wraps
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any


class RuntimePinError(RuntimeError):
    """Host setup failure before any agent/native execution, not task failure."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cli_runtime(trial, harness, pins: dict) -> dict | None:
    """Resolve exactly the PATH-selected CLI used by the frozen helper."""
    runtime = trial.model.runtime
    if trial.condition != "cua" or runtime not in {"codex", "claude"}:
        return None
    selected = shutil.which(runtime)
    if not selected:
        raise RuntimePinError(f"{runtime}: selected CLI is unavailable; no trial ran")
    entry = Path(selected).resolve()
    if runtime == "codex":
        try:
            native = harness._codex_native_binary(entry)
        except (OSError, RuntimeError) as exc:
            raise RuntimePinError(
                "codex: cannot resolve the unique native binary; no trial ran"
            ) from exc
        candidates = [
            ("launcher", entry, pins["codex"]["launcher_sha256"]),
            ("native", native, pins["codex"]["native_sha256"]),
        ]
    else:
        candidates = [("native", entry, pins["claude"]["native_sha256"])]
    files = []
    for role, path, expected in candidates:
        try:
            actual = _file_sha256(path)
        except OSError as exc:
            raise RuntimePinError(
                f"{runtime}: selected {role} is unreadable; no trial ran"
            ) from exc
        if actual != expected:
            raise RuntimePinError(
                f"{runtime}: selected {role} digest differs from the evaluated pin; no trial ran"
            )
        files.append({"role": role, "path": str(path),
                      "sha256": actual, "expected_sha256": expected})
    return {
        "model": trial.model.key, "runtime": runtime, "files": files,
        "validation": "point_in_time_file_hashes_before_trial",
        "client_executed_by_validation": False,
    }


def cua_evidence_disposition(result: dict[str, Any]) -> str:
    evidence = ((result.get("protocol") or {}).get("cua_evidence") or {})
    screenshots = evidence.get("screenshot_attachments")
    matched_views = evidence.get("matched_image_view_calls")
    visual_observation = bool(
        evidence.get("capability_assigned") is True
        and evidence.get("observation_mode") == "visual"
        and int(evidence.get("observations") or 0) > 0
        and int(evidence.get("host_audited_observations") or 0) > 0
        and evidence.get("visual_grounded") is True
        and isinstance(screenshots, list)
        and bool(screenshots)
        and isinstance(matched_views, list)
        and bool(matched_views)
    )
    recorded_evidence = bool(
        evidence.get("capability_assigned") is True
        and evidence.get("capability_used") is True
        and evidence.get("evidenced") is True
        and evidence.get("raw_gui_evidenced") is True
        and evidence.get("visual_grounded") is True
        and evidence.get("observation_mode") == "visual"
        and isinstance(screenshots, list)
        and bool(screenshots)
    )
    if recorded_evidence or visual_observation:
        return "valid"
    if (
        int(evidence.get("observations") or 0) == 0
        and int(evidence.get("host_audited_observations") or 0) == 0
        and (not isinstance(screenshots, list) or not screenshots)
        and (not isinstance(matched_views, list) or not matched_views)
        and evidence.get("visual_grounded") is not True
    ):
        return "nonuse"
    return "inconsistent"


def reported_success(row: dict) -> bool:
    if row.get("infrastructure_error"):
        return False
    if not row.get("verifier_success") or not (row.get("protocol") or {}).get("compliant"):
        return False
    return row["trial"]["condition"] != "cua" or cua_evidence_disposition(row) == "valid"


def build_report(run_root: Path, trials, results: list[dict]) -> dict:
    rows = []
    for result in results:
        trial = result["trial"]
        condition = trial["condition"]
        native = result.get("verifier_success")
        native = native if isinstance(native, bool) else None
        infra = result.get("infrastructure_error")
        protocol = (result.get("protocol") or {}).get("compliant")
        known = (
            isinstance(infra, bool)
            and (infra or isinstance(native, bool) and isinstance(protocol, bool))
        )
        trial_path = run_root / "trials" / trial["key"] / "trial.json"
        rows.append({
            "key": trial["key"],
            "task_id": trial["task_id"],
            "model": result["model"]["key"],
            "condition": condition,
            "status": result.get("status"),
            "native_success": native,
            "legacy_reported_success": reported_success(result) if known else None,
            "infrastructure_error": infra,
            "scorable": result.get("scorable"),
            "protocol_compliant": protocol,
            "cua_evidence_disposition": (
                cua_evidence_disposition(result) if condition == "cua" else "not_applicable"
            ),
            "trial": {
                "path": str(trial_path),
                "sha256": _file_sha256(trial_path) if trial_path.is_file() else None,
            },
        })
    summary = run_root / "summary.json"
    return {
        "schema_version": 1,
        "scope": "Web-only reporting projection; raw trial/native outputs unchanged",
        "reported_predicate": "no infrastructure error AND native verifier pass AND protocol.compliant AND (code-only OR valid original CUA evidence)",
        "budget_attestation": "diagnostic; not an additional reported-success gate",
        "planned_rows": len(trials),
        "recorded_rows": len(rows),
        "native_passes": sum(row["native_success"] is True for row in rows),
        "legacy_reported_passes": sum(row["legacy_reported_success"] is True for row in rows),
        "native_unknown": sum(row["native_success"] is None for row in rows),
        "legacy_reported_unknown": sum(row["legacy_reported_success"] is None for row in rows),
        "infrastructure_rows": sum(row["infrastructure_error"] is True for row in rows),
        "raw_summary": {
            "path": str(summary),
            "sha256": _file_sha256(summary) if summary.is_file() else None,
        },
        "rows": rows,
    }


def install(harness, pins: dict) -> None:
    """Attach preflight and reporting to new runs without editing BASE behavior."""
    if getattr(harness, "_web_portable_reporting_installed", False):
        raise RuntimeError("Web runtime/reporting support is already installed")
    original_trial = harness.run_trial
    original_summary = harness.write_summary
    original_parse = getattr(harness, "parse_args", None)

    if original_parse is not None:
        @wraps(original_parse)
        def parse_args():
            args = original_parse()
            # The BASE manifest records client versions. Admit the selected CLI
            # before that code can execute it; metadata/replay-only modes skip it.
            metadata_only = any(getattr(args, name, False) for name in (
                "dry_run", "staging_check", "protocol_replay_root", "merge_shard",
            ))
            if not metadata_only and not getattr(args, "code_only_only", False):
                for model in harness.selected_models(args):
                    validate_cli_runtime(
                        SimpleNamespace(condition="cua", model=model), harness, pins
                    )
            return args
        harness.parse_args = parse_args

    @wraps(original_trial)
    def run_trial(trial, run_root, python_bin, max_agent_tokens=200_000):
        safe_key = hashlib.sha256(trial.key.encode()).hexdigest()
        try:
            runtime = validate_cli_runtime(trial, harness, pins)
        except RuntimePinError as exc:
            harness._write_json(Path(run_root) / "runtime-pin-failures" / f"{safe_key}.json", {
                "schema_version": 1, "trial_key": trial.key,
                "model": trial.model.key, "phase": "runtime_preflight",
                "error": str(exc), "agent_started": False,
                "native_success": None, "legacy_reported_success": None,
            })
            raise
        if runtime is not None:
            harness._write_json(Path(run_root) / "runtime-pins" / f"{safe_key}.json", {
                "schema_version": 1, "trial_key": trial.key, **runtime,
            })
        return original_trial(trial, run_root, python_bin, max_agent_tokens)

    @wraps(original_summary)
    def write_summary(run_root, trials, results, *, reported_run_root=None):
        value = original_summary(
            run_root, trials, results, reported_run_root=reported_run_root
        )
        harness._write_json(
            Path(run_root) / "canonical-web-results.json",
            build_report(Path(run_root), trials, results),
        )
        return value

    harness.run_trial = run_trial
    harness.write_summary = write_summary
    harness._web_portable_reporting_installed = True
