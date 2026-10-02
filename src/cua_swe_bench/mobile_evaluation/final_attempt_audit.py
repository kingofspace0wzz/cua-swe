"""Whole-attempt audit for fresh Mobile evaluation, separate from admission."""
from pathlib import Path
import json

from cua_swe_bench.mobile_evaluation import admission
from cua_swe_bench.mobile_evaluation.core import Task, digest, evidence, tree, verify_ref
from cua_swe_bench.mobile_evaluation.grading import interpret
from cua_swe_bench.mobile_evaluation.workspace import prepare, apply
from .cli_evidence import audit_cli_agent, require


def read(path):
    return json.loads(Path(path).read_text())


def contained(reference, root):
    require(verify_ref(reference), "missing or changed primary evidence")
    path = Path(reference["path"])
    require(path.resolve().is_relative_to(Path(root).resolve()), "borrowed attempt evidence")
    return path


def audit_attempt(attempt_path, audit_root, expected_task, expected_protocol, expected_harness, *,
                  synthetic_test=False):
    attempt_path, audit_root = Path(attempt_path), Path(audit_root)
    root = attempt_path.parent
    require(not audit_root.resolve().is_relative_to(root.resolve()),
            "audit outputs must not alter the original attempt inventory")
    require(not audit_root.exists(), "audit output already exists")
    a = read(attempt_path)
    require(a["synthetic"] is synthetic_test, "synthetic fixture cannot become a model result")
    require(a["phase"] == "evaluation" and a["slot"] == 1 and a["condition"] in {"code-only", "cua"},
            "not a fresh single-slot evaluation attempt")
    require(verify_ref(expected_task), "selected task changed")
    task = Task.load(expected_task["path"])
    task.validate_inputs()
    require(read(root / "task.json") == task.c, "attempt did not use its selected frozen task")
    protocol = read(root / "protocol.json")
    require(protocol == a["protocol"] == expected_protocol, "unapproved evaluation protocol")
    require(digest(read(root / "harness.json")) == expected_harness,
            "unapproved evaluation harness")
    identity = {
        **task.identity, "protocol_digest": digest(protocol), "harness_digest": expected_harness,
        "controls_digest": digest(task.c.get("controls", {})),
    }
    require(a["identity"] == identity, "attempt identity differs")
    require(len({r["path"] for r in a["artifacts"]}) == len(a["artifacts"]), "duplicate evidence entry")
    for reference in a["artifacts"]:
        contained(reference, root)
    actual_inventory = [
        evidence(p) for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink() and p != attempt_path
        and not any(part in ("workspace", "source", "git-metadata") for part in p.relative_to(root).parts)
    ]
    require(actual_inventory == a["artifacts"], "attempt inventory is incomplete or changed")
    agent_path = root / "agent/agent.json"
    require((a["agent"] == read(agent_path)) if agent_path.exists() else a["agent"] == {},
            "agent summary differs from primary record")
    cl = a["classification"]
    audit_root.mkdir(parents=True)
    summary = {
        "attempt": evidence(attempt_path), "task": expected_task, "identity": identity,
        "synthetic_test": synthetic_test, "original_artifacts_verified": len(a["artifacts"]),
        "classification": cl["classification"], "scorable": cl["scorable"],
        "genuine_failure_attribution_performed": False,
    }
    if not cl["scorable"]:
        summary.update(
            passed=True, performance_credit=False, requires_invalid_attempt_review=True,
            software_correct=None, counted_success=False,
            scope="Primary custody only; invalid attempts earn no failure or success credit.")
        (audit_root / "review.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
    require(cl["execution_valid"] and not cl["faults"] and not a["agent"]["faults"],
            "faulted attempt cannot be scored")
    required_health = {"instruction", "source", "baseline", "grader_controls",
                       "shell_before", "shell_after", "runtime_before"}
    require(all(a["health"].get(key) is True for key in required_health), "execution health incomplete")
    agent = a["agent"]
    require(agent["termination"] in {"submitted", "time_cap", "response_cap"}
            and 1 <= agent["responses"] <= protocol["responses"]
            and set(agent["returned_models"]) == {protocol["model"]},
            "invalid model/response/termination accounting")
    require(read(root / "agent/prompt.json")["instruction_sha256"] == task.c["instruction"]["sha256"],
            "instruction delivery differs")
    if protocol.get("evidence_format") == "native-cli-stream-receipts-v1":
        require(a["condition"] == "cua", "native CLI is not an approved code-only row")
        transport = audit_cli_agent(
            root / "agent", root / "runtime", protocol,
            test_limits=(protocol["responses"], protocol["active_seconds"], protocol["max_output_tokens"])
            if synthetic_test else None)
    else:
        from .final_api_evidence import audit_api_agent
        require(admission.validate_evidence(a), "API attempt evidence failed its native audit")
        transport = audit_api_agent(root / "agent", protocol, a["condition"])
    (audit_root / "transport.json").write_text(json.dumps(transport, indent=2) + "\n")
    baseline = prepare(task, audit_root / "source")
    require(baseline == read(root / "baseline.json"), "solver baseline differs from task")
    patch = read(root / "patch.json")
    require(patch["task_digest"] == task.id and patch["baseline_digest"] == digest(baseline),
            "patch is not bound to the frozen task baseline")
    apply(task, baseline, patch, audit_root / "source")
    submitted_source = tree(audit_root / "source")
    grade = read(root / "grading/grade.json")
    require(grade == a["grade"], "grade summary differs")
    first = contained(grade["result"], root)
    verdict = interpret(read(first), task.c["expected_assertions"])
    require(verdict["correct"] is grade["correct"] is cl["software_correct"],
            "raw task assertion outcome differs")
    require(tree(first.parent.parent / "source") == submitted_source,
            "first grading workspace does not contain the submitted patch")
    if task.c["backend"].get("native"):
        require(tree(first.parent / "source") == submitted_source,
                "native verifier did not receive the submitted source")
    raw_replay_identical = None
    if not verdict["correct"]:
        replay = contained(grade["replay"]["result"], root)
        repeated = interpret(read(replay), task.c["expected_assertions"])
        require(verdict == repeated and not grade["replay"]["correct"], "failure replay differs")
        require(tree(replay.parent.parent / "source") == submitted_source,
                "replay grading workspace does not contain the submitted patch")
        if task.c["backend"].get("native"):
            require(tree(replay.parent / "source") == submitted_source,
                    "native replay did not receive the submitted source")
        raw_replay_identical = first.read_bytes() == replay.read_bytes()
        require(raw_replay_identical, "raw first/replay results differ; manual review required")
    controls = read(root / "controls/controls.json")
    require(controls["passed"] and controls["task_digest"] == task.id,
            "control result does not certify this task")
    require(read(contained(controls["baseline_manifest"], root)) == baseline,
            "control baseline differs from solver baseline")
    expected_controls = {"broken": False, **{name: row["correct"] for name, row in task.c["controls"].items()}}
    require(set(controls["outcomes"]) == set(expected_controls), "control matrix incomplete")
    for name, expected in expected_controls.items():
        result = controls["outcomes"][name]
        raw = contained(result["result"], root)
        check = interpret(read(raw), task.c["expected_assertions"])
        require(check["correct"] is expected is result["correct"], "control outcome differs")
        if not expected:
            repeated = contained(result["replay"]["result"], root)
            require(raw.read_bytes() == repeated.read_bytes(), "raw control replay differs")
    used = bool(agent["images_delivered"])
    require(cl["cua_used"] is used and cl["success_without_cua"] is (verdict["correct"] and not used),
            "visual-use classification differs")
    if a["condition"] == "code-only":
        require(not used and not agent.get("images_created"), "code-only received visual inputs")
    expected_class = "valid_success" if verdict["correct"] else "valid_model_failure"
    require(cl["classification"] == expected_class, "classification does not match raw grading")
    counted = verdict["correct"] and (a["condition"] == "code-only" or used)
    summary.update(
        passed=True, software_correct=verdict["correct"], counted_success=counted,
        visual_evidence_used=used, rule_exclusion="cua_nonuse" if verdict["correct"] and not counted else None,
        patch=evidence(root / "patch.json"), transport_audit=evidence(audit_root / "transport.json"),
        control_outcomes_verified=len(expected_controls), raw_failure_replay_identical=raw_replay_identical,
        submitted_patch_matches_clean_grading_source=True,
        candidate_error_requires_manual_review="candidate_error" in verdict,
        performance_credit=not synthetic_test,
        scope="Execution, protocol, evidence custody, source binding, complete controls and raw assertion outcomes. Genuine capability attribution beyond these checks is not inferred for candidate errors.")
    (audit_root / "review.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
