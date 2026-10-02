"""Focused source/portability checks; no models, browsers or native verifiers."""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts/run_web_clean_ablation.py"
CAPSULE = ROOT / "scripts/frozen_web"
spec = importlib.util.spec_from_file_location("web_frozen_entry_test", ENTRY)
assert spec is not None and spec.loader is not None
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
support_spec = importlib.util.spec_from_file_location(
    "web_runtime_reporting_test", CAPSULE / "runtime_and_reporting.py"
)
assert support_spec is not None and support_spec.loader is not None
support = importlib.util.module_from_spec(support_spec)
support_spec.loader.exec_module(support)


def test_full_source_closure():
    pins = entry.validate_frozen_sources()
    paths = [r["path"] for r in pins["harness_files"]]
    assert len(paths) == len(set(paths)) == 41
    assert "src/cua_swe_bench/provider_layer.py" in paths
    assert all((CAPSULE / path).is_file() for path in paths)


@pytest.mark.parametrize("relative", [
    "scripts/render_web_agent_prompt.py",
    "src/cua_swe_bench/adapters/web.py",
    "retention_entrypoint.py",
    "runtime-pins.json",
    "runtime_and_reporting.py",
])
def test_changed_dependency_refused_before_import(tmp_path, relative):
    copied = tmp_path / "frozen_web"
    shutil.copytree(CAPSULE, copied)
    with (copied / relative).open("ab") as output:
        output.write(b"\n# changed\n")
    with pytest.raises(RuntimeError, match="source digest mismatch"):
        entry.validate_frozen_sources(copied)


def test_uninventoried_python_dependency_refused(tmp_path):
    copied = tmp_path / "frozen_web"
    shutil.copytree(CAPSULE, copied)
    (copied / "src/cua_swe_bench/unexpected.py").write_text("pass\n")
    with pytest.raises(RuntimeError, match="package inventory mismatch"):
        entry.validate_frozen_sources(copied)


def test_portable_paths_mask_checkout_and_import_private_package():
    # Loading definitions only: no harness main, sandbox, task or provider runs.
    code = """
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
capsule=root/'scripts/frozen_web'
sys.path[:0]=[str(capsule/'scripts'),str(capsule/'src')]
import run_clean_ablation as h
import cua_swe_bench.schema as schema
import run_model_matrix as matrix
print(json.dumps({
    'root':str(h.REPO_ROOT),
    'frozen':str(h.FROZEN_ROOT),
    'schema':str(Path(schema.__file__).resolve()),
    'digest':h._evaluation_harness_digest(),
    'profile':h._sandbox_profile(),
    'models':{m.key:[m.runtime,m.model_id] for m in matrix.MODELS},
    'historical_names':len(matrix.TASK_NAMES),
}))
"""
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code, str(ROOT)],
        check=True, text=True, capture_output=True,
    )
    result = json.loads(proc.stdout)
    pins = entry.validate_frozen_sources()
    assert result["root"] == str(ROOT)
    assert result["frozen"] == str(CAPSULE)
    assert result["schema"] == str(CAPSULE / "src/cua_swe_bench/schema.py")
    assert result["digest"] == pins["portable_harness_sha256"]
    assert f'(subpath "{ROOT}")' in result["profile"]
    assert result["historical_names"] == 42
    assert result["models"]["api-gpt6-astra"] == ["responses", "gpt-6-astra"]
    assert result["models"]["claude-code-opus5"] == ["claude", "claude-opus-5"]


def test_retention_and_help_bootstrap_without_runtime_execution():
    proc = subprocess.run(
        [sys.executable, "-I", str(ENTRY), "--help"],
        check=True, text=True, capture_output=True,
    )
    assert "--task-file" in proc.stdout
    assert "--max-agent-tokens" in proc.stdout


def test_paper_prompt_and_tool_files_not_rewritten():
    # Digests of the agent prompt and CUA tool files used for the paper's Web runs.
    paper_digests = {
        "render_web_agent_prompt.py": "1a681c376d2c636489f11e83084116d0a65b7e34e1718c2eefe4dc1042ad668e",
        "web_cua_tool.py": "9af3db1b67d0b182040ef82e5ab473d6b7a09a3dcbbf5b5150265dff2bc3e522",
        "web_cua_mcp.py": "8c774cca017a43ce5e23b2b7e3255a0e6daa0665c21064bfb180ca0c4bfe6638",
        "web_cua_broker.py": "9097331f217ddf386f736a9d6ddb33b890abde6ad846ab421547f90326ac38c7",
    }
    pins = entry.validate_frozen_sources()
    records = {item["path"]: item for item in pins["harness_files"]}
    for name, digest in paper_digests.items():
        assert records["scripts/" + name]["sha256"] == digest
    for path in CAPSULE.rglob("*.py"):
        ast.parse(path.read_bytes(), filename=str(path))


def _row(*, condition="cua", native=True, compliant=True, infra=False):
    return {
        "trial": {"key": f"{condition}/model/task/attempt-1",
                  "task_id": "task", "condition": condition},
        "model": {"key": "model"},
        "status": "complete", "verifier_success": native,
        "infrastructure_error": infra, "scorable": not infra,
        "protocol": {
            "compliant": compliant, "budget_attestation": {"compliant": False},
            "cua_evidence": {
                "capability_assigned": True, "capability_used": True,
                "evidenced": True, "raw_gui_evidenced": True,
                "visual_grounded": True, "observation_mode": "visual",
                "screenshot_attachments": ["saved.png"],
            },
        },
    }


def test_native_and_legacy_reported_are_distinct_and_budget_is_diagnostic(tmp_path):
    good = _row()
    excluded = _row(compliant=False)
    failed = _row(native=False)
    rows = [good, excluded, failed]
    original = copy.deepcopy(rows)
    report = support.build_report(tmp_path, [None] * 4, rows)
    assert report["native_passes"] == 2
    assert report["legacy_reported_passes"] == 1
    assert report["planned_rows"] == 4 and report["recorded_rows"] == 3
    assert report["rows"][1]["native_success"] is True
    assert report["rows"][1]["legacy_reported_success"] is False
    assert rows == original


def test_legacy_visual_observation_branch_and_nonuse():
    row = _row()
    evidence = row["protocol"]["cua_evidence"]
    # The evaluated fallback accepts observed/viewed screenshots even without
    # the stronger capability_used/evidenced flags.
    evidence.update(capability_used=False, evidenced=False, raw_gui_evidenced=False,
                    observations=1, host_audited_observations=1,
                    matched_image_view_calls=["saved.png"])
    assert support.cua_evidence_disposition(row) == "valid"
    assert support.reported_success(row) is True
    row["protocol"]["cua_evidence"] = {}
    assert support.cua_evidence_disposition(row) == "nonuse"
    assert support.reported_success(row) is False
    row["trial"]["condition"] = "code-only"
    assert support.reported_success(row) is True


def test_missing_outcomes_not_converted_to_failures(tmp_path):
    pending = _row(native=None)
    pending["infrastructure_error"] = None
    report = support.build_report(tmp_path, [None], [pending])
    row = report["rows"][0]
    assert row["native_success"] is None
    assert row["legacy_reported_success"] is None
    assert report["native_unknown"] == report["legacy_reported_unknown"] == 1
    infra = support.build_report(tmp_path, [None], [_row(native=None, infra=True)])
    assert infra["rows"][0]["native_success"] is None
    assert infra["rows"][0]["legacy_reported_success"] is False
    assert infra["infrastructure_rows"] == 1


def _trial(runtime="codex", condition="cua"):
    return SimpleNamespace(
        key=f"{condition}/{runtime}/task/attempt-1", condition=condition,
        model=SimpleNamespace(key=f"{runtime}-model", runtime=runtime),
    )


def test_cli_hashes_both_selected_codex_files_without_execution(tmp_path, monkeypatch):
    launcher, native = tmp_path / "codex.js", tmp_path / "codex"
    launcher.write_bytes(b"fake launcher")
    native.write_bytes(b"fake native")
    link = tmp_path / "selected-codex"
    link.symlink_to(launcher)
    monkeypatch.setattr(support.shutil, "which", lambda name: str(link))
    pins = {"codex": {"launcher_sha256": support._file_sha256(launcher),
                      "native_sha256": support._file_sha256(native)}}
    harness = SimpleNamespace(_codex_native_binary=lambda path: native)
    result = support.validate_cli_runtime(_trial(), harness, pins)
    assert [r["path"] for r in result["files"]] == [str(launcher), str(native)]
    native.write_bytes(b"changed native")
    with pytest.raises(support.RuntimePinError, match="native digest differs"):
        support.validate_cli_runtime(_trial(), harness, pins)


def test_claude_selected_file_and_api_no_probe(tmp_path, monkeypatch):
    native = tmp_path / "claude"
    native.write_bytes(b"fake claude")
    monkeypatch.setattr(support.shutil, "which", lambda name: str(native))
    pins = {"claude": {"native_sha256": support._file_sha256(native)}}
    assert support.validate_cli_runtime(_trial("claude"), None, pins)["runtime"] == "claude"
    monkeypatch.setattr(support.shutil, "which", lambda name: pytest.fail("unexpected CLI probe"))
    assert support.validate_cli_runtime(_trial("responses"), None, {}) is None
    assert support.validate_cli_runtime(_trial("codex", "code-only"), None, {}) is None


def test_runtime_failure_stops_before_trial_and_records_no_outcome(tmp_path, monkeypatch):
    records = {}
    harness = SimpleNamespace(
        run_trial=lambda *args: pytest.fail("trial must not start"),
        write_summary=lambda *args, **kwargs: None,
        _write_json=lambda path, value: records.update({str(path): value}),
    )
    monkeypatch.setattr(support.shutil, "which", lambda name: None)
    support.install(harness, {})
    with pytest.raises(support.RuntimePinError, match="unavailable"):
        harness.run_trial(_trial("claude"), tmp_path, Path(sys.executable))
    record = next(iter(records.values()))
    assert record["phase"] == "runtime_preflight"
    assert record["agent_started"] is False
    assert record["native_success"] is record["legacy_reported_success"] is None


def test_summary_hook_preserves_raw_results_and_keyword_contract(tmp_path):
    written = {}
    sentinel = object()
    root_argument = tmp_path / "display"
    def original(run_root, trials, results, *, reported_run_root=None):
        assert reported_run_root == root_argument
        written["raw"] = copy.deepcopy(results)
        return sentinel
    harness = SimpleNamespace(
        run_trial=lambda *args: None, write_summary=original,
        _write_json=lambda path, value: written.update({Path(path).name: value}),
    )
    support.install(harness, {})
    rows = [_row(compliant=False)]
    assert harness.write_summary(tmp_path, [None], rows,
                                 reported_run_root=root_argument) is sentinel
    assert written["raw"] == rows
    projection = written["canonical-web-results.json"]["rows"][0]
    assert projection["native_success"] is True
    assert projection["legacy_reported_success"] is False


def test_cli_preflight_precedes_manifest_version_execution(monkeypatch):
    args = SimpleNamespace(code_only_only=False, dry_run=False)
    harness = SimpleNamespace(
        run_trial=lambda *args: None, write_summary=lambda *args, **kwargs: None,
        parse_args=lambda: args,
        selected_models=lambda args: [_trial("claude").model],
    )
    monkeypatch.setattr(support.shutil, "which", lambda name: None)
    support.install(harness, {})
    with pytest.raises(support.RuntimePinError, match="unavailable"):
        harness.parse_args()


@pytest.mark.parametrize("mode", [
    "dry_run", "staging_check", "protocol_replay_root", "merge_shard",
])
def test_metadata_only_modes_do_not_probe_cli(mode, monkeypatch):
    args = SimpleNamespace(code_only_only=False, **{mode: True})
    harness = SimpleNamespace(
        run_trial=lambda *args: None, write_summary=lambda *args, **kwargs: None,
        parse_args=lambda: args,
        selected_models=lambda args: pytest.fail("metadata mode must not probe"),
    )
    monkeypatch.setattr(support.shutil, "which", lambda name: pytest.fail("CLI probe"))
    support.install(harness, {})
    assert harness.parse_args() is args
