from __future__ import annotations

import argparse
from pathlib import Path
import hashlib
import json
import shutil
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_canonical_evaluation as canonical  # noqa: E402


def _args(
    tmp_path: Path,
    *,
    domain: str,
    scope: str = "full",
    condition: str = "code-only",
    model: str = "api-gpt6-astra",
) -> argparse.Namespace:
    return argparse.Namespace(
        domain=domain,
        scope=scope,
        condition=condition,
        model=model,
        output_root=tmp_path / "run",
        execution_host="test-host",
        shard_id=None,
        max_workers=1,
        python=Path(sys.executable),
    )


def test_catalog_matches_all_canonical_domain_manifests() -> None:
    result = canonical.validate_catalog()
    assert result["valid"], result["errors"]
    assert {
        name: row["task_count"] for name, row in result["domains"].items()
    } == {"web": 36, "game": 29, "mobile": 20, "devops": 20}
    assert result["domains"]["web"]["model_overrides"]["claude-code-opus5"]["status"] == "active"


@pytest.mark.parametrize(
    ("domain", "expected"),
    (("web", 36), ("game", 29), ("devops", 20)),
)
def test_full_plan_selects_only_manifest_tasks(
    tmp_path: Path, domain: str, expected: int
) -> None:
    command = canonical.build_command(_args(tmp_path, domain=domain))
    assert command.count("--task-file") == expected
    assert "--code-only-only" in command


def test_gate_uses_first_ten_manifest_tasks(tmp_path: Path) -> None:
    command = canonical.build_command(_args(tmp_path, domain="web", scope="gate"))
    assert command.count("--task-file") == 10


def test_cua_plan_requires_visual_mode(tmp_path: Path) -> None:
    command = canonical.build_command(
        _args(
            tmp_path,
            domain="game",
            condition="cua",
            model="codex-gpt56-sol",
        )
    )
    assert "--cua-only" in command
    assert "--visual-cua" in command


def test_game_uses_frozen_september_six_runner(tmp_path: Path) -> None:
    command = canonical.build_command(
        _args(tmp_path, domain="game", condition="code-only")
    )
    runner = Path(command[1])
    assert runner.name == "run_game_clean_ablation.py"
    catalog = canonical._load(canonical.CATALOG_PATH)
    expected = catalog["domains"]["game"]["protected_runner_sha256"]
    assert hashlib.sha256(runner.read_bytes()).hexdigest() == expected


def test_mobile_uses_the_protected_native_pipeline(tmp_path: Path) -> None:
    command = canonical.build_command(_args(tmp_path, domain="mobile"))
    assert Path(command[1]).name == "run_mobile_evaluation.py"
    assert "--task-file" not in command
    assert command[command.index("--condition") + 1] == "code-only"
    for model in ("api-opus5", "claude-code-opus5"):
        with pytest.raises(ValueError, match="user_deferred"):
            canonical.build_command(_args(tmp_path, domain="mobile", model=model, condition="cua"))


def test_web_claude_code_uses_its_own_protected_runner(tmp_path: Path) -> None:
    command = canonical.build_command(
        _args(tmp_path, domain="web", condition="cua", model="claude-code-opus5")
    )
    assert Path(command[1]).name == "run_web_clean_ablation.py"
    assert command[command.index("--model") + 1] == "claude-code-opus5"
    assert "--evaluation-matrix" in command
    assert "--cua-only" in command
    assert "--visual-cua" in command
    assert command.count("--task-file") == 36


@pytest.mark.parametrize("domain", ["game", "devops"])
def test_claude_code_remains_blocked_outside_web(tmp_path: Path, domain: str) -> None:
    with pytest.raises(ValueError, match="blocked_main_integration"):
        canonical.build_command(
            _args(
                tmp_path,
                domain=domain,
                condition="cua",
                model="claude-code-opus5",
            )
        )


def test_web_cli_has_no_code_only_substitution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not support code-only"):
        canonical.build_command(
            _args(tmp_path, domain="web", model="claude-code-opus5")
        )


@pytest.mark.parametrize("domain", ["game", "devops"])
def test_web_matrix_flag_does_not_change_other_domains(tmp_path: Path, domain: str) -> None:
    command = canonical.build_command(_args(tmp_path, domain=domain))
    assert "--evaluation-matrix" not in command
    assert "--max-turns" not in command
    assert "--prompt-revision" not in command


def test_saved_web36_matrix_preserves_both_outcomes() -> None:
    catalog = canonical._load(canonical.CATALOG_PATH)
    web = catalog["domains"]["web"]
    manifest = canonical._load(canonical.REPO_ROOT / web["manifest"])
    assert canonical._validate_evaluation_summary(catalog, web, manifest["tasks"]) == []
    summary = canonical._load(canonical.REPO_ROOT / web["evaluation_summary"]["path"])
    rows = summary["rows"]
    assert len(rows) == 720
    assert sum(row["reported_success"] for row in rows) == 219
    assert sum(row["native_success"] for row in rows) == 255
    assert sum(row["native_success"] and not row["reported_success"] for row in rows) == 36
    assert len({(row["model"], row["condition"]) for row in rows}) == 20


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "input"])
def test_web_summary_rejects_incomplete_or_misbound_rows(
    tmp_path: Path, mutation: str
) -> None:
    catalog = canonical._load(canonical.CATALOG_PATH)
    web = dict(catalog["domains"]["web"])
    manifest = canonical._load(canonical.REPO_ROOT / web["manifest"])
    summary = canonical._load(canonical.REPO_ROOT / web["evaluation_summary"]["path"])
    if mutation == "missing":
        summary["rows"].pop()
    elif mutation == "duplicate":
        summary["rows"][-1] = summary["rows"][0]
    else:
        summary["rows"][0]["evaluated_task_input_sha256"] = "0" * 64
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    web["evaluation_summary"] = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    assert canonical._validate_evaluation_summary(catalog, web, manifest["tasks"])


def test_web_summary_digest_mismatch_fails_closed() -> None:
    catalog = canonical._load(canonical.CATALOG_PATH)
    web = dict(catalog["domains"]["web"])
    web["evaluation_summary"] = {**web["evaluation_summary"], "sha256": "0" * 64}
    manifest = canonical._load(canonical.REPO_ROOT / web["manifest"])
    assert canonical._validate_evaluation_summary(catalog, web, manifest["tasks"]) == [
        "evaluation summary digest mismatch"
    ]


@pytest.mark.parametrize("field,value", [
    ("runtime", "codex"),
    ("model_id", "gpt-5.6-sol"),
])
def test_web_catalog_cannot_relabel_the_actual_frozen_route(field: str, value: str) -> None:
    catalog = canonical._load(canonical.CATALOG_PATH)
    catalog["models"]["api-gpt6-astra"][field] = value
    assert canonical._validate_model_registry(catalog, catalog["domains"]["web"]) == [
        "model route differs from frozen runner: api-gpt6-astra"
    ]


@pytest.mark.parametrize("changed_file", ["repo/src/app.mjs", "env/service.mjs"])
def test_web_lineage_detects_source_and_protected_asset_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_file: str
) -> None:
    catalog = canonical._load(canonical.CATALOG_PATH)
    web = dict(catalog["domains"]["web"])
    manifest = canonical._load(canonical.REPO_ROOT / web["manifest"])
    task = next(row for row in manifest["tasks"]
                if row["task_id"] == "web.fabric-nested-selection-05.001")
    lineage = canonical._load(canonical.REPO_ROOT / web["task_lineage"]["path"])
    record = next(row for row in lineage["tasks"] if row["task_id"] == task["task_id"])
    task_root = Path(task["task_file"]).parent
    shutil.copytree(canonical.REPO_ROOT / task_root, tmp_path / task_root)
    original = Path(record["original_task_yaml"])
    (tmp_path / original).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(canonical.REPO_ROOT / original, tmp_path / original)
    lineage["tasks"] = [record]
    lineage_path = tmp_path / "lineage.json"
    lineage_path.write_text(json.dumps(lineage), encoding="utf-8")
    web["task_lineage"] = {
        "path": str(lineage_path),
        "sha256": hashlib.sha256(lineage_path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(canonical, "REPO_ROOT", tmp_path)
    assert canonical._validate_task_lineage(web, [task]) == []
    path = tmp_path / task_root / changed_file
    path.write_bytes(path.read_bytes() + b"\n// changed after admission\n")
    assert canonical._validate_task_lineage(web, [task]) == [
        f"canonical task digest mismatch: {task['task_id']}",
        f"published task digest or historical input binding mismatch: {task['task_id']}",
    ]


def test_gpt6_route_is_the_responses_api() -> None:
    models = canonical._load(canonical.CATALOG_PATH)["models"]
    assert models["api-gpt6-astra"] == {
        "label": "GPT-6 Astra (API)",
        "model_id": "gpt-6-astra",
        "runtime": "responses",
        "conditions": ["code-only", "cua"],
    }


@pytest.mark.parametrize("changed_binding", ["archive", "historical_input", "historical_yaml"])
def test_web_public_redaction_preserves_measurement_bindings(tmp_path, monkeypatch, changed_binding):
    catalog = canonical._load(canonical.CATALOG_PATH)
    web = dict(catalog["domains"]["web"])
    manifest = canonical._load(canonical.REPO_ROOT / web["manifest"])
    task = next(row for row in manifest["tasks"] if row["task_id"] == "web.fabric-nested-selection-05.001")
    lineage = canonical._load(canonical.REPO_ROOT / web["task_lineage"]["path"])
    record = next(row for row in lineage["tasks"] if row["task_id"] == task["task_id"])
    task_root = Path(task["task_file"]).parent
    shutil.copytree(canonical.REPO_ROOT / task_root, tmp_path / task_root)
    original = Path(record["original_task_yaml"])
    (tmp_path / original).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(canonical.REPO_ROOT / original, tmp_path / original)
    assert record["public_original_task_yaml_sha256"] != record["evaluated_task_yaml_sha256"]
    assert record["public_original_yaml_restored_digest"] != record["evaluated_task_input_sha256"]
    if changed_binding == "archive":
        with (tmp_path / original).open('ab') as f:
            f.write(b'\n# modified archive\n')
    elif changed_binding == "historical_input":
        task["evaluated_task_input_sha256"] = '0' * 64
    else:
        record["evaluated_task_yaml_sha256"] = '0' * 64
    lineage["tasks"] = [record]
    lineage_path = tmp_path / 'lineage.json'
    lineage_path.write_text(json.dumps(lineage))
    web["task_lineage"] = {"path": str(lineage_path), "sha256": hashlib.sha256(lineage_path.read_bytes()).hexdigest()}
    monkeypatch.setattr(canonical, 'REPO_ROOT', tmp_path)
    assert canonical._validate_task_lineage(web, [task])
