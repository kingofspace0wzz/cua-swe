from __future__ import annotations

import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from cua_swe_bench.commands import run_command
from cua_swe_bench.mobilegym_runtime import MobileGymRuntime
from cua_swe_bench.runner import BenchmarkRunner
from cua_swe_bench.schema import TaskBundle


GateStatus = Literal["pass", "fail", "skip"]
CONSTRUCTION_EVIDENCE_GATES = [
    "no_op_agent_fails",
    "gold_patch_applies",
    "gold_patch_passes",
    "negative_patch_applies",
    "negative_patch_fails",
    "verifier_is_discriminative",
]
DEFAULT_ARTIFACTS_ROOT = Path("artifacts")
DEFAULT_MOBILEGYM_RUNS_ROOT = DEFAULT_ARTIFACTS_ROOT / "mobilegym-runs"
DEFAULT_MOBILEGYM_CANARY_RUNS_ROOT = DEFAULT_ARTIFACTS_ROOT / "mobilegym-canary-runs"
DEFAULT_MOBILEGYM_CANARY_OUTPUT_ROOT = DEFAULT_ARTIFACTS_ROOT / "mobilegym-canary-outputs"
DEFAULT_MOBILEGYM_WORKFLOW_ROOT = DEFAULT_ARTIFACTS_ROOT / "workflow-runs"


class WorkflowGateResult(BaseModel):
    name: str
    status: GateStatus
    required: bool = True
    message: str = ""
    artifact_path: str | None = None


class WorkflowTaskStatus(BaseModel):
    task_id: str
    task_file: str
    ready: bool
    gates: list[WorkflowGateResult] = Field(default_factory=list)


class WorkflowManifest(BaseModel):
    run_id: str
    created_at: str
    workflow: str
    tasks_root: str | None = None
    preflight_gates: list[WorkflowGateResult] = Field(default_factory=list)
    task_statuses: list[WorkflowTaskStatus] = Field(default_factory=list)


class WorkflowRunPaths(BaseModel):
    run_id: str
    run_dir: str
    manifest_path: str
    events_path: str
    summary_path: str
    construction_report_path: str | None = None


def default_noop_agent_command() -> str:
    code = 'print("no changes")'
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_now() -> str:
    return _utc_now().isoformat(timespec="seconds")


def _safe_run_id(workflow: str) -> str:
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{workflow}"


def _gate(name: str, status: GateStatus, message: str = "", required: bool = True, artifact_path: str | None = None) -> WorkflowGateResult:
    return WorkflowGateResult(
        name=name,
        status=status,
        required=required,
        message=message,
        artifact_path=artifact_path,
    )


def _ready(gates: list[WorkflowGateResult]) -> bool:
    return all(gate.status == "pass" for gate in gates if gate.required)


def _gold_patch_candidates(task_file: Path) -> list[Path]:
    return [task_file.parent / "gold.patch", task_file.parent / "gold.diff"]


def _negative_patch_candidates(task_file: Path) -> list[Path]:
    candidates = [task_file.parent / "negative.patch", task_file.parent / "negative.diff"]
    negatives_dir = task_file.parent / "negatives"
    if negatives_dir.exists():
        candidates.extend(sorted(negatives_dir.glob("*.patch")))
        candidates.extend(sorted(negatives_dir.glob("*.diff")))
    return candidates


def _existing_paths(candidates: list[Path]) -> list[Path]:
    return [candidate for candidate in candidates if candidate.exists()]


def _patch_agent_command(patch_path: Path) -> str:
    return f"git apply --whitespace=nowarn {shlex.quote(str(patch_path.resolve()))}"


class TaskReadinessChecker:
    def __init__(self, tasks_root: Path | str = Path("dataset/tasks"), project_root: Path | str | None = None) -> None:
        self.tasks_root = Path(tasks_root)
        self.project_root = Path.cwd() if project_root is None else Path(project_root)

    def validate_tasks(self) -> list[WorkflowTaskStatus]:
        return [self.validate_task_file(path) for path in sorted(self.tasks_root.glob("**/task.yaml"))]

    def validate_task_file(
        self,
        task_file: Path | str,
        extra_gates: list[WorkflowGateResult] | None = None,
    ) -> WorkflowTaskStatus:
        path = Path(task_file)
        extra_by_name = {gate.name: gate for gate in extra_gates or []}
        task_id = path.parent.name
        gates: list[WorkflowGateResult] = []

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("task file must contain a mapping")
            task = TaskBundle.model_validate(data)
        except Exception as exc:
            gates.append(_gate("schema_valid", "fail", str(exc)))
            gates.extend(extra_by_name.values())
            return WorkflowTaskStatus(task_id=task_id, task_file=str(path), ready=False, gates=gates)

        task_id = task.id
        gates.append(_gate("schema_valid", "pass"))
        gates.append(self._repo_snapshot_gate(task_file=path, task=task))
        gates.append(self._verifier_gate(task))
        gates.append(self._replay_gate(path))
        gates.append(self._lifecycle_gate(task))
        gates.append(self._mobilegym_runtime_spec_gate(task))
        gates.append(self._gold_patch_gate(path))
        gates.append(self._negative_case_gate(path))
        for gate_name in CONSTRUCTION_EVIDENCE_GATES:
            if gate_name in extra_by_name:
                gates.append(extra_by_name[gate_name])
            else:
                gates.append(
                    _gate(
                        gate_name,
                        "skip",
                        f"run `cua-swe workflow certify-task {path}` to execute this gate",
                    )
                )
        return WorkflowTaskStatus(task_id=task_id, task_file=str(path), ready=_ready(gates), gates=gates)

    def _repo_snapshot_gate(self, task_file: Path, task: TaskBundle) -> WorkflowGateResult:
        if task.repo_snapshot.source not in {"local", "mobilegym_overlay"}:
            return _gate(
                "repo_snapshot_present",
                "fail",
                f"runner currently supports local and mobilegym_overlay snapshots only, got {task.repo_snapshot.source}",
            )
        if task.repo_snapshot.path is None:
            return _gate("repo_snapshot_present", "fail", f"{task.repo_snapshot.source} snapshot path is missing")

        snapshot_path = self._resolve_repo_snapshot_path(task_file, task.repo_snapshot.path)
        if snapshot_path.exists():
            if task.repo_snapshot.source == "mobilegym_overlay" and task.repo_snapshot.overlay_patch:
                patch_path = self._resolve_repo_snapshot_path(task_file, task.repo_snapshot.overlay_patch)
                if not patch_path.exists():
                    return _gate("repo_snapshot_present", "fail", f"missing overlay patch: {patch_path}")
                return _gate("repo_snapshot_present", "pass", f"{snapshot_path}; overlay={patch_path}")
            return _gate("repo_snapshot_present", "pass", str(snapshot_path))
        return _gate("repo_snapshot_present", "fail", f"missing repo snapshot: {snapshot_path}")

    def _resolve_repo_snapshot_path(self, task_file: Path, snapshot_path: str) -> Path:
        path = Path(snapshot_path)
        if path.is_absolute():
            return path
        candidates = [
            self.project_root / path,
            self.tasks_root.parent / path,
            task_file.parent / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _verifier_gate(self, task: TaskBundle) -> WorkflowGateResult:
        if task.verifiers.ordered_commands():
            return _gate("verifier_present", "pass")
        return _gate("verifier_present", "fail", "task has no verifier commands")

    def _replay_gate(self, task_file: Path) -> WorkflowGateResult:
        replay = task_file.parent / "replay.md"
        if replay.exists():
            return _gate("replay_doc_present", "pass", str(replay))
        return _gate("replay_doc_present", "fail", f"missing replay note: {replay}")

    def _lifecycle_gate(self, task: TaskBundle) -> WorkflowGateResult:
        return _gate("lifecycle_supported_by_runner", "pass", "runner supports setup.reset and setup.launch")

    def _mobilegym_runtime_spec_gate(self, task: TaskBundle) -> WorkflowGateResult:
        if task.track != "mobilegym":
            return _gate(
                "mobilegym_runtime_spec_present",
                "skip",
                "not a MobileGym task",
                required=False,
            )
        if task.mobilegym_runtime is None:
            return _gate(
                "mobilegym_runtime_spec_present",
                "fail",
                "MobileGym benchmark tasks must declare mobilegym_runtime with an upstream_task_id",
            )
        return _gate(
            "mobilegym_runtime_spec_present",
            "pass",
            task.mobilegym_runtime.upstream_task_id,
        )

    def _gold_patch_gate(self, task_file: Path) -> WorkflowGateResult:
        for candidate in _gold_patch_candidates(task_file):
            if candidate.exists():
                return _gate("gold_patch_present", "pass", str(candidate))
        return _gate("gold_patch_present", "fail", "missing gold.patch or gold.diff")

    def _negative_case_gate(self, task_file: Path) -> WorkflowGateResult:
        candidates = _negative_patch_candidates(task_file) + [task_file.parent / "negatives"]
        for candidate in candidates:
            if candidate.exists():
                return _gate("negative_case_present", "pass", str(candidate))
        return _gate("negative_case_present", "fail", "missing negative patch, diff, or negatives/ directory")


class PreflightChecker:
    def __init__(
        self,
        project_root: Path | str,
        tasks_root: Path | str = Path("dataset/tasks"),
        mobilegym_repo: Path | str = Path("../baselines/repos/mobilegym"),
        workflow_root: Path | str = Path("workflow_runs"),
        require_provider: bool = False,
    ) -> None:
        self.project_root = Path(project_root)
        self.tasks_root = Path(tasks_root)
        self.mobilegym_repo = Path(mobilegym_repo)
        self.workflow_root = Path(workflow_root)
        self.require_provider = require_provider

    def run(self) -> list[WorkflowGateResult]:
        tasks = self._load_tasks_for_preflight()
        has_web_task = any(task.track == "web_frontend" for task in tasks)
        has_mobile_task = any(task.track == "mobilegym" for task in tasks)
        gates = [
            self._package_import_gate(),
            self._command_gate("pytest_available", f"{shlex.quote(sys.executable)} -m pytest --version"),
            self._command_gate("git_available", "git --version"),
            self._command_gate("node_available", "node --version") if has_web_task else _gate("node_available", "skip", "no web tasks found", required=False),
            self._command_gate("npm_available", "npm --version") if has_web_task else _gate("npm_available", "skip", "no web tasks found", required=False),
            self._mobilegym_gate(has_mobile_task),
            self._mobilegym_runtime_gate(has_mobile_task),
            self._provider_gate(),
            self._generated_artifacts_gate(),
        ]
        return gates

    def _load_tasks_for_preflight(self) -> list[TaskBundle]:
        tasks: list[TaskBundle] = []
        for path in sorted(self.tasks_root.glob("**/task.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    tasks.append(TaskBundle.model_validate(data))
            except Exception:
                continue
        return tasks

    def _package_import_gate(self) -> WorkflowGateResult:
        try:
            import cua_swe_bench
        except Exception as exc:
            return _gate("package_import", "fail", f"{type(exc).__name__}: {exc}")
        version = getattr(cua_swe_bench, "__version__", "unknown")
        return _gate("package_import", "pass", f"cua_swe_bench {version}")

    def _command_gate(self, name: str, command: str) -> WorkflowGateResult:
        result = run_command(command, cwd=self.project_root, timeout_sec=30)
        if result.ok:
            message = result.stdout.strip() or result.stderr.strip()
            return _gate(name, "pass", message)
        return _gate(name, "fail", result.stderr.strip() or result.stdout.strip() or f"exit code {result.exit_code}")

    def _mobilegym_gate(self, has_mobile_task: bool) -> WorkflowGateResult:
        if not has_mobile_task:
            return _gate("mobilegym_repo_present", "skip", "no MobileGym tasks found", required=False)
        path = self.mobilegym_repo if self.mobilegym_repo.is_absolute() else self.project_root / self.mobilegym_repo
        if path.exists():
            return _gate("mobilegym_repo_present", "pass", str(path))
        return _gate("mobilegym_repo_present", "fail", f"missing MobileGym repo: {path}")

    def _mobilegym_runtime_gate(self, has_mobile_task: bool) -> WorkflowGateResult:
        if not has_mobile_task:
            return _gate("mobilegym_runtime_ready", "skip", "no MobileGym tasks found", required=False)
        path = self.mobilegym_repo if self.mobilegym_repo.is_absolute() else self.project_root / self.mobilegym_repo
        result = MobileGymRuntime(mobilegym_root=path, python_executable=sys.executable).check(
            suite="notes",
            include_task_ids=False,
            timeout_sec=30,
        )
        status: GateStatus = "pass" if result.ok else "fail"
        return _gate("mobilegym_runtime_ready", status, result.message)

    def _provider_gate(self) -> WorkflowGateResult:
        if not self.require_provider:
            return _gate("provider_config_present", "skip", "model provider check not required", required=False)
        from cua_swe_bench.llm.provider import ModelProvider

        result = ModelProvider.from_env().smoke_check(invoke=False)
        status: GateStatus = "pass" if result.ok else "fail"
        return _gate("provider_config_present", status, result.message)

    def _generated_artifacts_gate(self) -> WorkflowGateResult:
        allowed = (self.workflow_root if self.workflow_root.is_absolute() else self.project_root / self.workflow_root).resolve()
        blocked = []
        for name in ["runs", "outputs", "workflow_runs", "node_modules"]:
            candidate = self.project_root / name
            if not candidate.exists():
                continue
            if candidate.resolve() == allowed:
                continue
            blocked.append(str(candidate))
        if not blocked:
            return _gate("repo_local_artifacts_absent", "pass")
        return _gate("repo_local_artifacts_absent", "fail", "remove generated artifacts: " + ", ".join(blocked))


class WorkflowStore:
    def __init__(self, workflow_root: Path | str = Path("workflow_runs")) -> None:
        self.workflow_root = Path(workflow_root)
        self.workflow_root.mkdir(parents=True, exist_ok=True)

    def write_run(
        self,
        workflow: str,
        task_statuses: list[WorkflowTaskStatus],
        tasks_root: Path | str | None = None,
        preflight_gates: list[WorkflowGateResult] | None = None,
        events: list[dict[str, Any]] | None = None,
        construction_report: bool = False,
        artifacts: dict[str, Any] | None = None,
    ) -> WorkflowRunPaths:
        run_id = self._unique_run_id(workflow)
        run_dir = self.workflow_root / run_id
        run_dir.mkdir(parents=True)

        manifest = WorkflowManifest(
            run_id=run_id,
            created_at=_isoformat_now(),
            workflow=workflow,
            tasks_root=None if tasks_root is None else str(tasks_root),
            preflight_gates=preflight_gates or [],
            task_statuses=task_statuses,
        )
        manifest_path = run_dir / "manifest.json"
        events_path = run_dir / "events.jsonl"
        summary_path = run_dir / "summary.md"
        construction_report_path = run_dir / "construction_report.md" if construction_report else None

        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        self._write_events(
            events_path,
            workflow=workflow,
            task_statuses=task_statuses,
            preflight_gates=preflight_gates or [],
            events=events or [],
        )
        summary_path.write_text(self._render_summary(manifest), encoding="utf-8")
        if construction_report_path is not None:
            construction_report_path.write_text(self._render_construction_report(manifest), encoding="utf-8")
        for relative_path, payload in (artifacts or {}).items():
            artifact_path = run_dir / relative_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, str):
                artifact_path.write_text(payload, encoding="utf-8")
            else:
                artifact_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )

        return WorkflowRunPaths(
            run_id=run_id,
            run_dir=str(run_dir),
            manifest_path=str(manifest_path),
            events_path=str(events_path),
            summary_path=str(summary_path),
            construction_report_path=None if construction_report_path is None else str(construction_report_path),
        )

    def latest_manifest_path(self) -> Path | None:
        manifests = sorted(self.workflow_root.glob("*/manifest.json"))
        if not manifests:
            return None
        return manifests[-1]

    def read_manifest(self, run_id: str | None = None) -> WorkflowManifest:
        path = self.workflow_root / run_id / "manifest.json" if run_id else self.latest_manifest_path()
        if path is None:
            raise FileNotFoundError(f"no workflow manifests under {self.workflow_root}")
        return WorkflowManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def write_construction_report(self, run_id: str | None = None) -> Path:
        manifest_path = self.workflow_root / run_id / "manifest.json" if run_id else self.latest_manifest_path()
        if manifest_path is None:
            raise FileNotFoundError(f"no workflow manifests under {self.workflow_root}")
        manifest = WorkflowManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        report_path = manifest_path.parent / "construction_report.md"
        report_path.write_text(self._render_construction_report(manifest), encoding="utf-8")
        return report_path

    def _unique_run_id(self, workflow: str) -> str:
        base = _safe_run_id(workflow)
        candidate = base
        suffix = 2
        while (self.workflow_root / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _write_events(
        self,
        events_path: Path,
        workflow: str,
        task_statuses: list[WorkflowTaskStatus],
        preflight_gates: list[WorkflowGateResult],
        events: list[dict[str, Any]],
    ) -> None:
        rows: list[dict[str, Any]] = [
            {"time": _isoformat_now(), "event": "workflow_started", "workflow": workflow}
        ]
        if preflight_gates:
            rows.append(
                {
                    "time": _isoformat_now(),
                    "event": "preflight_status",
                    "gates": [gate.model_dump() for gate in preflight_gates],
                }
            )
        for status in task_statuses:
            rows.append(
                {
                    "time": _isoformat_now(),
                    "event": "task_status",
                    "task_id": status.task_id,
                    "ready": status.ready,
                    "gates": [gate.model_dump() for gate in status.gates],
                }
            )
        rows.extend(events)
        rows.append({"time": _isoformat_now(), "event": "workflow_finished", "workflow": workflow})
        events_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _render_summary(self, manifest: WorkflowManifest) -> str:
        lines = [
            f"# Workflow Run {manifest.run_id}",
            "",
            f"- Workflow: `{manifest.workflow}`",
            f"- Created: `{manifest.created_at}`",
        ]
        if manifest.tasks_root:
            lines.append(f"- Tasks root: `{manifest.tasks_root}`")
        if manifest.preflight_gates:
            failing = [
                gate.name
                for gate in manifest.preflight_gates
                if gate.required and gate.status != "pass"
            ]
            lines.append(f"- Preflight: `{'pass' if not failing else 'fail'}`")
            lines.extend(["", "| Preflight Gate | Status | Message |", "| --- | --- | --- |"])
            for gate in manifest.preflight_gates:
                lines.append(f"| `{gate.name}` | {gate.status} | {gate.message} |")
        lines.extend(["", "| Task | Ready | Required gates not passing |", "| --- | --- | --- |"])
        for status in manifest.task_statuses:
            blockers = [
                gate.name
                for gate in status.gates
                if gate.required and gate.status != "pass"
            ]
            blocker_text = ", ".join(blockers) if blockers else "none"
            ready_text = "yes" if status.ready else "no"
            lines.append(f"| `{status.task_id}` | {ready_text} | {blocker_text} |")
        lines.append("")
        return "\n".join(lines)

    def _render_construction_report(self, manifest: WorkflowManifest) -> str:
        lines = [
            f"# Construction Report {manifest.run_id}",
            "",
            f"- Workflow: `{manifest.workflow}`",
            f"- Created: `{manifest.created_at}`",
        ]
        if manifest.tasks_root:
            lines.append(f"- Tasks root: `{manifest.tasks_root}`")
        if manifest.preflight_gates:
            lines.extend(["", "## Preflight", "", "| Gate | Status | Message |", "| --- | --- | --- |"])
            for gate in manifest.preflight_gates:
                lines.append(f"| `{gate.name}` | {gate.status} | {gate.message} |")
        lines.extend(["", "## Task Readiness", "", "| Task | Ready | Next Action |", "| --- | --- | --- |"])
        for status in manifest.task_statuses:
            blockers = [gate for gate in status.gates if gate.required and gate.status != "pass"]
            if not blockers:
                next_action = "ready for benchmark data construction"
            else:
                first = blockers[0]
                next_action = f"fix `{first.name}`: {first.message or first.status}"
            ready_text = "yes" if status.ready else "no"
            lines.append(f"| `{status.task_id}` | {ready_text} | {next_action} |")
        lines.append("")
        return "\n".join(lines)


class WorkflowExecutor:
    def __init__(
        self,
        workflow_root: Path | str = Path("workflow_runs"),
        project_root: Path | str | None = None,
    ) -> None:
        self.project_root = Path.cwd() if project_root is None else Path(project_root)
        self.store = WorkflowStore(workflow_root)

    def validate(self, tasks_root: Path | str = Path("dataset/tasks")) -> WorkflowRunPaths:
        checker = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root)
        statuses = checker.validate_tasks()
        return self.store.write_run("validate", task_statuses=statuses, tasks_root=tasks_root)

    def preflight(
        self,
        tasks_root: Path | str = Path("dataset/tasks"),
        mobilegym_repo: Path | str = Path("../baselines/repos/mobilegym"),
        require_provider: bool = False,
    ) -> WorkflowRunPaths:
        checker = PreflightChecker(
            project_root=self.project_root,
            tasks_root=tasks_root,
            mobilegym_repo=mobilegym_repo,
            workflow_root=self.store.workflow_root,
            require_provider=require_provider,
        )
        gates = checker.run()
        task_statuses = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root).validate_tasks()
        return self.store.write_run(
            "preflight",
            task_statuses=task_statuses,
            tasks_root=tasks_root,
            preflight_gates=gates,
            construction_report=True,
        )

    def run_noop(
        self,
        task_file: Path | str,
        runs_root: Path | str = Path("runs"),
        output_root: Path | str = Path("outputs"),
        agent_command: str | None = None,
    ) -> WorkflowRunPaths:
        task_path = Path(task_file)
        gate, events = self._evaluate_noop(
            task_file=task_path,
            runs_root=runs_root,
            output_root=output_root,
            agent_command=agent_command,
        )
        tasks_root = self._infer_tasks_root(task_path)
        checker = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root)
        status = checker.validate_task_file(task_path, extra_gates=[gate])
        return self.store.write_run("run-noop", task_statuses=[status], tasks_root=checker.tasks_root, events=events)

    def run_gold(
        self,
        task_file: Path | str,
        runs_root: Path | str = Path("runs"),
        output_root: Path | str = Path("outputs"),
    ) -> WorkflowRunPaths:
        task_path = Path(task_file)
        gates, events = self._evaluate_gold(task_path, runs_root=runs_root, output_root=output_root)
        tasks_root = self._infer_tasks_root(task_path)
        status = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root).validate_task_file(
            task_path,
            extra_gates=gates,
        )
        return self.store.write_run("run-gold", task_statuses=[status], tasks_root=tasks_root, events=events)

    def run_negative(
        self,
        task_file: Path | str,
        runs_root: Path | str = Path("runs"),
        output_root: Path | str = Path("outputs"),
    ) -> WorkflowRunPaths:
        task_path = Path(task_file)
        gates, events = self._evaluate_negative(task_path, runs_root=runs_root, output_root=output_root)
        tasks_root = self._infer_tasks_root(task_path)
        status = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root).validate_task_file(
            task_path,
            extra_gates=gates,
        )
        return self.store.write_run("run-negative", task_statuses=[status], tasks_root=tasks_root, events=events)

    def certify_task(
        self,
        task_file: Path | str,
        runs_root: Path | str = Path("runs"),
        output_root: Path | str = Path("outputs"),
        agent_command: str | None = None,
    ) -> WorkflowRunPaths:
        task_path = Path(task_file)
        status, events = self._certify_task_status(
            task_file=task_path,
            runs_root=runs_root,
            output_root=output_root,
            agent_command=agent_command,
        )
        tasks_root = self._infer_tasks_root(task_path)
        return self.store.write_run(
            "certify-task",
            task_statuses=[status],
            tasks_root=tasks_root,
            events=events,
            construction_report=True,
        )

    def _certify_task_status(
        self,
        task_file: Path,
        runs_root: Path | str,
        output_root: Path | str,
        agent_command: str | None = None,
    ) -> tuple[WorkflowTaskStatus, list[dict[str, Any]]]:
        noop_gate, noop_events = self._evaluate_noop(
            task_file=task_file,
            runs_root=Path(runs_root) / "noop",
            output_root=Path(output_root) / "noop",
            agent_command=agent_command,
        )
        gold_gates, gold_events = self._evaluate_gold(
            task_file,
            runs_root=Path(runs_root) / "gold",
            output_root=Path(output_root) / "gold",
        )
        negative_gates, negative_events = self._evaluate_negative(
            task_file,
            runs_root=Path(runs_root) / "negative",
            output_root=Path(output_root) / "negative",
        )
        extra_gates = [noop_gate] + gold_gates + negative_gates
        gate_by_name = {gate.name: gate for gate in extra_gates}
        discriminative = (
            gate_by_name.get("no_op_agent_fails", _gate("missing", "fail")).status == "pass"
            and gate_by_name.get("gold_patch_passes", _gate("missing", "fail")).status == "pass"
            and gate_by_name.get("negative_patch_fails", _gate("missing", "fail")).status == "pass"
        )
        extra_gates.append(
            _gate(
                "verifier_is_discriminative",
                "pass" if discriminative else "fail",
                "no-op fails, gold passes, and negative fails" if discriminative else "expected no-op fail, gold pass, and negative fail",
            )
        )
        tasks_root = self._infer_tasks_root(task_file)
        status = TaskReadinessChecker(tasks_root=tasks_root, project_root=self.project_root).validate_task_file(
            task_file,
            extra_gates=extra_gates,
        )
        return status, noop_events + gold_events + negative_events

    def mobilegym_predata(
        self,
        *,
        mobilegym_root: Path | str = Path("../baselines/repos/mobilegym"),
        env_url: str,
        task_id: str = "notes.CreateNoteWithReminder",
        suite: str = "notes",
        mobilegym_runs_root: Path | str = DEFAULT_MOBILEGYM_RUNS_ROOT,
        python_executable: str | None = None,
        min_task_count: int = 15,
        headless: bool = True,
        replay_max_steps: int = 40,
        runtime_timeout_sec: int = 60,
        noop_timeout_sec: int = 180,
        replay_timeout_sec: int = 300,
        canary_task_file: Path | str | None = None,
        canary_runs_root: Path | str | None = None,
        canary_output_root: Path | str | None = None,
    ) -> WorkflowRunPaths:
        runtime = MobileGymRuntime(
            mobilegym_root=mobilegym_root,
            python_executable=python_executable,
        )
        runs_root = self._resolve_project_path(mobilegym_runs_root)
        events: list[dict[str, Any]] = []
        artifacts: dict[str, Any] = {}
        gates: list[WorkflowGateResult] = []
        task_statuses: list[WorkflowTaskStatus] = []

        runtime_result = runtime.check(
            suite=suite,
            env_url=env_url,
            list_online=True,
            include_task_ids=True,
            timeout_sec=runtime_timeout_sec,
        )
        artifacts["mobilegym-runtime.json"] = runtime_result.model_dump()
        events.append(self._run_event("mobilegym_runtime_check", runtime_result.model_dump()))
        task_count = runtime_result.task_count or 0
        runtime_ok = runtime_result.ok and task_count >= min_task_count and task_id in runtime_result.task_ids
        runtime_message = runtime_result.message
        if runtime_result.ok:
            runtime_message = (
                f"{runtime_result.message}; task_count={task_count}; "
                f"required_task_present={task_id in runtime_result.task_ids}"
            )
        gates.append(
            _gate(
                "mobilegym_online_runtime_ready",
                "pass" if runtime_ok else "fail",
                runtime_message,
                artifact_path="mobilegym-runtime.json",
            )
        )

        noop_result = None
        if runtime_ok:
            noop_result = runtime.run_task(
                task_id=task_id,
                env_url=env_url,
                runs_dir=runs_root / "noop",
                agent="human",
                expected_outcome="failed",
                headless=headless,
                max_steps=1,
                quiet=True,
                stdin_text="\n",
                timeout_sec=noop_timeout_sec,
            )
            artifacts["mobilegym-noop.json"] = noop_result.model_dump()
            events.append(self._run_event("mobilegym_noop_check", noop_result.model_dump()))
            gates.append(
                _gate(
                    "mobilegym_noop_fails",
                    "pass" if noop_result.ok and noop_result.observed_outcome == "failed" else "fail",
                    noop_result.message,
                    artifact_path="mobilegym-noop.json",
                )
            )
        else:
            gates.append(
                _gate(
                    "mobilegym_noop_fails",
                    "skip",
                    "blocked because online runtime gate did not pass",
                )
            )

        replay_result = None
        if runtime_ok:
            replay_result = runtime.replay_task(
                task_id=task_id,
                env_url=env_url,
                runs_dir=runs_root / "replay",
                expected_outcome="success",
                headless=headless,
                max_steps=replay_max_steps,
                timeout_sec=replay_timeout_sec,
            )
            artifacts["mobilegym-replay.json"] = replay_result.model_dump()
            events.append(self._run_event("mobilegym_replay_check", replay_result.model_dump()))
            gates.append(
                _gate(
                    "mobilegym_deterministic_replay_passes",
                    "pass" if replay_result.ok and replay_result.observed_outcome == "success" else "fail",
                    replay_result.message,
                    artifact_path="mobilegym-replay.json",
                )
            )
            gates.append(self._mobilegym_replay_artifact_gate(task_id, replay_result))
        else:
            gates.append(
                _gate(
                    "mobilegym_deterministic_replay_passes",
                    "skip",
                    "blocked because online runtime gate did not pass",
                )
            )
            gates.append(
                _gate(
                    "mobilegym_replay_artifacts_present",
                    "skip",
                    "blocked because online runtime gate did not pass",
                )
            )

        canary_required = canary_task_file is not None
        executable_gates_ok = all(gate.status == "pass" for gate in gates if gate.required)
        if canary_task_file is None:
            gates.append(
                _gate(
                    "mobilegym_overlay_canary_certification",
                    "skip",
                    "pass --canary-task-file to certify one bug/gold/negative overlay through the replay",
                    required=False,
                )
            )
        elif not executable_gates_ok:
            gates.append(
                _gate(
                    "mobilegym_overlay_canary_certification",
                    "skip",
                    "blocked because earlier MobileGym pre-data gates did not pass",
                    required=True,
                )
            )
        else:
            canary_path = Path(canary_task_file)
            canary_status, canary_events = self._certify_task_status(
                task_file=canary_path,
                runs_root=self._resolve_project_path(canary_runs_root)
                if canary_runs_root is not None
                else self._resolve_project_path(DEFAULT_MOBILEGYM_CANARY_RUNS_ROOT),
                output_root=self._resolve_project_path(canary_output_root)
                if canary_output_root is not None
                else self._resolve_project_path(DEFAULT_MOBILEGYM_CANARY_OUTPUT_ROOT),
            )
            task_statuses.append(canary_status)
            events.extend(canary_events)
            blockers = [
                gate.name
                for gate in canary_status.gates
                if gate.required and gate.status != "pass"
            ]
            artifacts["canary-certification.json"] = {
                "task_status": canary_status.model_dump(),
                "events": canary_events,
            }
            gates.append(
                _gate(
                    "mobilegym_overlay_canary_certification",
                    "pass" if canary_status.ready else "fail",
                    "canary ready" if canary_status.ready else "required gates not passing: " + ", ".join(blockers),
                    required=canary_required,
                    artifact_path="canary-certification.json",
                )
            )

        return self.store.write_run(
            "mobilegym-predata",
            task_statuses=task_statuses,
            preflight_gates=gates,
            events=events,
            construction_report=True,
            artifacts=artifacts,
        )

    def _resolve_project_path(self, path: Path | str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate

    def _infer_tasks_root(self, task_file: Path) -> Path:
        for parent in task_file.parents:
            if parent.name == "tasks":
                return parent
        return task_file.parents[1] if len(task_file.parents) > 1 else Path("dataset/tasks")

    def _mobilegym_replay_artifact_gate(
        self,
        task_id: str,
        replay_result: Any,
    ) -> WorkflowGateResult:
        if not replay_result or not replay_result.run_dir:
            return _gate(
                "mobilegym_replay_artifacts_present",
                "fail",
                "replay produced no run_dir",
                artifact_path="mobilegym-replay.json",
            )
        run_dir = Path(replay_result.run_dir)
        summary_path = Path(replay_result.summary_path) if replay_result.summary_path else run_dir / "summary.json"
        results_path = Path(replay_result.results_path) if replay_result.results_path else run_dir / "results.jsonl"
        trajectory_dir = run_dir / "trajectory" / task_id.replace(".", "_")
        screenshots = [
            path
            for path in trajectory_dir.glob("step_*.jpg")
            if "_annot" not in path.stem
        ] if trajectory_dir.exists() else []
        ok = (
            summary_path.exists()
            and results_path.exists()
            and trajectory_dir.exists()
            and len(screenshots) >= 1
        )
        message = (
            f"summary={summary_path.exists()} results={results_path.exists()} "
            f"trajectory={trajectory_dir.exists()} screenshots={len(screenshots)}"
        )
        return _gate(
            "mobilegym_replay_artifacts_present",
            "pass" if ok else "fail",
            message,
            artifact_path=str(run_dir),
        )

    def _evaluate_noop(
        self,
        task_file: Path,
        runs_root: Path | str,
        output_root: Path | str,
        agent_command: str | None = None,
    ) -> tuple[WorkflowGateResult, list[dict[str, Any]]]:
        command = agent_command or default_noop_agent_command()
        events: list[dict[str, Any]] = []
        try:
            result = BenchmarkRunner(runs_root=runs_root, output_root=output_root).run_task_file(
                task_file=task_file,
                agent_command=command,
            )
            passed = not result.success
            gate = _gate(
                "no_op_agent_fails",
                "pass" if passed else "fail",
                f"no-op success={result.success} progress={result.progress}",
                artifact_path=result.verifier_report_path,
            )
            events.append(self._run_event("noop_result", result.model_dump()))
            return gate, events
        except Exception as exc:
            gate = _gate("no_op_agent_fails", "fail", f"{type(exc).__name__}: {exc}")
            events.append(self._error_event("noop_error", task_file, exc))
            return gate, events

    def _evaluate_gold(
        self,
        task_file: Path,
        runs_root: Path | str,
        output_root: Path | str,
    ) -> tuple[list[WorkflowGateResult], list[dict[str, Any]]]:
        patch_paths = _existing_paths(_gold_patch_candidates(task_file))
        if not patch_paths:
            return [
                _gate("gold_patch_applies", "fail", "missing gold.patch or gold.diff"),
                _gate("gold_patch_passes", "fail", "missing gold.patch or gold.diff"),
            ], []
        patch_path = patch_paths[0]
        return self._evaluate_patch(
            stage="gold",
            task_file=task_file,
            patch_paths=[patch_path],
            runs_root=runs_root,
            output_root=output_root,
            applies_gate_name="gold_patch_applies",
            outcome_gate_name="gold_patch_passes",
            expect_success=True,
        )

    def _evaluate_negative(
        self,
        task_file: Path,
        runs_root: Path | str,
        output_root: Path | str,
    ) -> tuple[list[WorkflowGateResult], list[dict[str, Any]]]:
        patch_paths = _existing_paths(_negative_patch_candidates(task_file))
        if not patch_paths:
            return [
                _gate("negative_patch_applies", "fail", "missing negative patch, diff, or negatives/*.patch"),
                _gate("negative_patch_fails", "fail", "missing negative patch, diff, or negatives/*.patch"),
            ], []
        return self._evaluate_patch(
            stage="negative",
            task_file=task_file,
            patch_paths=patch_paths,
            runs_root=runs_root,
            output_root=output_root,
            applies_gate_name="negative_patch_applies",
            outcome_gate_name="negative_patch_fails",
            expect_success=False,
        )

    def _evaluate_patch(
        self,
        stage: str,
        task_file: Path,
        patch_paths: list[Path],
        runs_root: Path | str,
        output_root: Path | str,
        applies_gate_name: str,
        outcome_gate_name: str,
        expect_success: bool,
    ) -> tuple[list[WorkflowGateResult], list[dict[str, Any]]]:
        events: list[dict[str, Any]] = []
        applies_results: list[bool] = []
        outcome_results: list[bool] = []
        artifact_paths: list[str] = []

        for index, patch_path in enumerate(patch_paths):
            run_suffix = str(index + 1) if len(patch_paths) > 1 else "single"
            try:
                result = BenchmarkRunner(
                    runs_root=Path(runs_root) / run_suffix,
                    output_root=Path(output_root) / run_suffix,
                ).run_task_file(task_file=task_file, agent_command=_patch_agent_command(patch_path))
                agent_failed = self._report_has_group(result.verifier_report_path, "agent")
                applies = not agent_failed
                outcome_ok = applies and (result.success if expect_success else not result.success)
                applies_results.append(applies)
                outcome_results.append(outcome_ok)
                artifact_paths.append(result.verifier_report_path)
                event_payload = result.model_dump()
                event_payload["patch_path_input"] = str(patch_path)
                event_payload["patch_applied"] = applies
                events.append(self._run_event(f"{stage}_patch_result", event_payload))
            except Exception as exc:
                applies_results.append(False)
                outcome_results.append(False)
                events.append(self._error_event(f"{stage}_patch_error", task_file, exc, patch_path=patch_path))

        applies_pass = all(applies_results)
        outcome_pass = all(outcome_results)
        applies_message = f"{sum(applies_results)}/{len(patch_paths)} patches applied"
        if expect_success:
            outcome_message = f"{sum(outcome_results)}/{len(patch_paths)} gold patches passed verifiers"
        else:
            outcome_message = f"{sum(outcome_results)}/{len(patch_paths)} negative patches failed verifiers"
        artifact_path = artifact_paths[0] if artifact_paths else None
        return [
            _gate(applies_gate_name, "pass" if applies_pass else "fail", applies_message, artifact_path=artifact_path),
            _gate(outcome_gate_name, "pass" if outcome_pass else "fail", outcome_message, artifact_path=artifact_path),
        ], events

    def _report_has_group(self, verifier_report_path: str, group: str) -> bool:
        try:
            data = json.loads(Path(verifier_report_path).read_text(encoding="utf-8"))
        except Exception:
            return False
        results = data.get("results")
        if not isinstance(results, list):
            return False
        return any(isinstance(result, dict) and result.get("group") == group for result in results)

    def _run_event(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"time": _isoformat_now(), "event": event}
        row.update(payload)
        return row

    def _error_event(self, event: str, task_file: Path, exc: Exception, patch_path: Path | None = None) -> dict[str, Any]:
        row = {
            "time": _isoformat_now(),
            "event": event,
            "task_file": str(task_file),
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        if patch_path is not None:
            row["patch_path_input"] = str(patch_path)
        return row
