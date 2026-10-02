from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Iterable, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
import yaml


GateName = Literal[
    "source",
    "diagnostic_design",
    "broken_reproduction",
    "evaluation_design",
    "local_certification",
    "luna_comparison",
    "batch",
]
ReviewDecision = Literal[
    "approve",
    "revise",
    "drop",
    "accept_for_batch",
    "revise_and_rerun",
    "blocked",
    "reject",
]
ReviewCheckStatus = Literal["pass", "fail", "na"]


LUNA_MODEL_KEY = "gpt56-luna"
LUNA_MODEL_ID = "gpt-5.6-luna"
DEFAULT_ATTEMPTS_PER_CONDITION = 3
DEFAULT_BROWSER_ADVANTAGE_PP = 30.0
DEFAULT_MIN_BROWSER_SUCCESS_RATE = 2 / 3
DEFAULT_MAX_BROWSER_SUCCESS_RATE = 2 / 3
DEFAULT_MAX_CODE_ONLY_SUCCESS_RATE = 1 / 3
APPROVAL_DECISIONS = {"approve", "accept_for_batch"}
CONSTRUCTION_GATE_ORDER: tuple[GateName, ...] = (
    "source",
    "diagnostic_design",
    "broken_reproduction",
    "evaluation_design",
    "local_certification",
    "luna_comparison",
)
REVIEW_ATTESTATION = (
    "I did not construct or modify the reviewed task, and this decision applies only to the recorded inputs."
)
TASK_ID_PATTERN = r"^web\.[a-z0-9-]+\.[0-9]{3}$"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_project_path(path: Path | str, project_root: Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def _project_relative_key(path: Path | str, project_root: Path) -> str:
    resolved = _resolve_project_path(path, project_root)
    try:
        relative = resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"path is outside project root: {path}") from exc
    return relative.as_posix()


def _validate_repo_relative_reference(raw_path: str, *, label: str) -> PurePosixPath:
    if re.match(r"^[A-Za-z]:[\\/]", raw_path):
        raise ValueError(f"{label} must be project-root-relative: {raw_path}")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or not path.parts:
        raise ValueError(f"{label} must be project-root-relative: {raw_path}")
    if path.as_posix() != raw_path or any(part in {".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a normalized project-root-relative path: {raw_path}")
    if path.parts[0] == "artifacts":
        raise ValueError(f"{label} cannot reference ignored artifacts: {raw_path}")
    return path


class ReviewCheck(BaseModel):
    name: str = Field(min_length=1)
    status: ReviewCheckStatus
    evidence: str = Field(min_length=1)


class GateReview(BaseModel):
    schema_version: Literal[1]
    task_id: str = Field(pattern=TASK_ID_PATTERN)
    iteration: int = Field(ge=1)
    gate: GateName
    review_number: int = Field(ge=1)
    constructor_agent_id: str = Field(min_length=1)
    reviewer_agent_id: str = Field(min_length=1)
    reviewer_model: str | None = None
    reviewed_at: datetime
    decision: ReviewDecision
    input_sha256: dict[str, str] = Field(min_length=1)
    checks: list[ReviewCheck] = Field(min_length=1)
    blocking_findings: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    notes: str = ""
    attestation: Literal[
        "I did not construct or modify the reviewed task, and this decision applies only to the recorded inputs."
    ]

    @field_validator("input_sha256")
    @classmethod
    def validate_input_entries(cls, value: dict[str, str]) -> dict[str, str]:
        for raw_path, digest in value.items():
            _validate_repo_relative_reference(raw_path, label="review input")
            if not SHA256_PATTERN.fullmatch(digest):
                raise ValueError(f"review input hash must be lowercase SHA-256: {raw_path}")
        return value

    @model_validator(mode="after")
    def validate_independence_and_decision(self) -> "GateReview":
        if self.constructor_agent_id == self.reviewer_agent_id:
            raise ValueError("constructor and reviewer agent IDs must differ")
        if self.decision in APPROVAL_DECISIONS:
            failed = [check.name for check in self.checks if check.status != "pass"]
            if failed:
                raise ValueError("approval requires every check to pass: " + ", ".join(failed))
            if self.blocking_findings or self.required_revisions:
                raise ValueError("approval cannot contain blocking findings or required revisions")
        return self

    def validate_input_hashes(self, project_root: Path) -> list[str]:
        errors: list[str] = []
        root = project_root.resolve()
        for raw_path, expected in self.input_sha256.items():
            path = (root / Path(*PurePosixPath(raw_path).parts)).resolve()
            if not path.is_relative_to(root):
                errors.append(f"review input is outside project root: {raw_path}")
            elif path.relative_to(root).parts[0] == "artifacts":
                errors.append(f"review input cannot reference ignored artifacts: {raw_path}")
            elif not path.is_file():
                errors.append(f"review input is missing: {raw_path}")
            elif sha256_file(path) != expected:
                errors.append(f"review input changed after review: {raw_path}")
        return errors


class ConstructionTaskEntry(BaseModel):
    id: str = Field(pattern=TASK_ID_PATTERN)
    proposal: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    initial_state: str = Field(min_length=1)
    replaces_candidate: str | None = Field(default=None, pattern=TASK_ID_PATTERN)


class ConstructionReserveEntry(BaseModel):
    id: str = Field(pattern=TASK_ID_PATTERN)
    proposal: str = Field(min_length=1)
    disposition: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ConstructionBatchManifest(BaseModel):
    schema_version: Literal[1]
    batch_id: str = Field(min_length=1)
    workflow: str = Field(min_length=1)
    target_task_count: int = Field(ge=1)
    status: str = Field(min_length=1)
    tasks: list[ConstructionTaskEntry] = Field(min_length=1)
    reserves: list[ConstructionReserveEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_roster(self) -> "ConstructionBatchManifest":
        task_ids = [task.id for task in self.tasks]
        duplicate_tasks = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
        if duplicate_tasks:
            raise ValueError("construction roster contains duplicate task IDs: " + ", ".join(duplicate_tasks))
        if len(task_ids) != self.target_task_count:
            raise ValueError(
                f"construction roster target_task_count is {self.target_task_count}, "
                f"but contains {len(task_ids)} tasks"
            )

        reserve_ids = [reserve.id for reserve in self.reserves]
        duplicate_reserves = sorted(
            {reserve_id for reserve_id in reserve_ids if reserve_ids.count(reserve_id) > 1}
        )
        if duplicate_reserves:
            raise ValueError(
                "construction roster contains duplicate reserve IDs: " + ", ".join(duplicate_reserves)
            )
        overlap = sorted(set(task_ids) & set(reserve_ids))
        if overlap:
            raise ValueError("active and reserve task IDs overlap: " + ", ".join(overlap))
        for task in self.tasks:
            if task.replaces_candidate and task.replaces_candidate not in reserve_ids:
                raise ValueError(
                    f"replacement {task.id} references non-reserve candidate {task.replaces_candidate}"
                )
        return self


class TaskWorkflowStatus(BaseModel):
    task_id: str
    iteration: int
    state: Literal[
        "awaiting_review",
        "revise",
        "dropped",
        "blocked",
        "invalid_review",
        "batch_ready",
    ]
    gate: GateName | None = None
    review_file: str | None = None
    decision: ReviewDecision | None = None
    error: str | None = None


def task_workflow_status(
    task_id: str,
    iteration: int,
    *,
    reviews_root: Path | str,
    project_root: Path | str = Path.cwd(),
    required_review_inputs: Iterable[Path | str] = (),
) -> TaskWorkflowStatus:
    project = Path(project_root).resolve()
    root = _resolve_project_path(reviews_root, project) / task_id / f"iteration-{iteration:02d}"
    for gate in CONSTRUCTION_GATE_ORDER:
        candidates = list(root.glob(f"{gate}.review-*.json")) if root.is_dir() else []
        numbered: list[tuple[int, Path]] = []
        for candidate in candidates:
            match = re.fullmatch(rf"{re.escape(gate)}\.review-([0-9]+)\.json", candidate.name)
            if match:
                numbered.append((int(match.group(1)), candidate))
        if not numbered:
            return TaskWorkflowStatus(
                task_id=task_id,
                iteration=iteration,
                state="awaiting_review",
                gate=gate,
            )
        duplicate_numbers = sorted(
            {number for number, _ in numbered if sum(item[0] == number for item in numbered) > 1}
        )
        if duplicate_numbers:
            duplicate_files = sorted(
                str(path) for number, path in numbered if number in duplicate_numbers
            )
            return TaskWorkflowStatus(
                task_id=task_id,
                iteration=iteration,
                state="invalid_review",
                gate=gate,
                review_file=duplicate_files[-1],
                error=(
                    "duplicate review filename numbers: "
                    + ", ".join(str(number) for number in duplicate_numbers)
                    + " ("
                    + ", ".join(duplicate_files)
                    + ")"
                ),
            )
        filename_review_number, review_file = max(numbered)
        try:
            review = load_gate_review(
                review_file,
                project_root=project,
                required_input_paths=required_review_inputs,
            )
            if review.task_id != task_id or review.iteration != iteration or review.gate != gate:
                raise ValueError("review identity does not match its workflow position")
            if review.review_number != filename_review_number:
                raise ValueError(
                    f"review number {review.review_number} does not match filename number "
                    f"{filename_review_number}"
                )
        except (OSError, ValueError) as exc:
            return TaskWorkflowStatus(
                task_id=task_id,
                iteration=iteration,
                state="invalid_review",
                gate=gate,
                review_file=str(review_file),
                error=str(exc),
            )
        if review.decision in APPROVAL_DECISIONS:
            continue
        if review.decision in {"revise", "revise_and_rerun"}:
            state = "revise"
        elif review.decision in {"drop", "reject"}:
            state = "dropped"
        else:
            state = "blocked"
        return TaskWorkflowStatus(
            task_id=task_id,
            iteration=iteration,
            state=state,
            gate=gate,
            review_file=str(review_file),
            decision=review.decision,
        )
    return TaskWorkflowStatus(task_id=task_id, iteration=iteration, state="batch_ready")


def workflow_status(
    workflow_file: Path | str,
    *,
    reviews_root: Path | str,
    project_root: Path | str = Path.cwd(),
) -> list[TaskWorkflowStatus]:
    project = Path(project_root).resolve()
    workflow_path = _resolve_project_path(workflow_file, project)
    _project_relative_key(workflow_path, project)
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("task_manifest"):
        raise ValueError("workflow file must declare a mutable task_manifest")

    manifest_reference = str(data["task_manifest"])
    manifest_relative = _validate_repo_relative_reference(
        manifest_reference,
        label="workflow task_manifest",
    )
    project_candidate = (project / Path(*manifest_relative.parts)).resolve()
    workflow_candidate = (workflow_path.parent / Path(*manifest_relative.parts)).resolve()
    manifest_path = project_candidate if project_candidate.is_file() else workflow_candidate
    _project_relative_key(manifest_path, project)

    manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = ConstructionBatchManifest.model_validate(manifest_data)
    workflow_reference = _validate_repo_relative_reference(
        manifest.workflow,
        label="construction roster workflow",
    )
    referenced_workflow = (project / Path(*workflow_reference.parts)).resolve()
    if referenced_workflow != workflow_path:
        raise ValueError(
            f"construction roster workflow {manifest.workflow} does not reference {workflow_path}"
        )

    for entry in [*manifest.tasks, *manifest.reserves]:
        proposal_reference = _validate_repo_relative_reference(
            entry.proposal,
            label=f"proposal for {entry.id}",
        )
        proposal_path = (project / Path(*proposal_reference.parts)).resolve()
        if not proposal_path.is_file():
            raise ValueError(f"proposal for {entry.id} is missing: {entry.proposal}")
        expected_name = f"proposed.{entry.id}.md"
        if proposal_path.name != expected_name:
            raise ValueError(
                f"proposal for {entry.id} must be named {expected_name}: {entry.proposal}"
            )

    return [
        task_workflow_status(
            task.id,
            task.iteration,
            reviews_root=reviews_root,
            project_root=project,
            required_review_inputs=(workflow_path,),
        )
        for task in manifest.tasks
    ]


class LunaTaskAssessment(BaseModel):
    task_id: str
    infrastructure_failures: int = 0
    browser_verifier_passes: int
    browser_successes_without_browser: int
    browser_passes: int
    browser_trials: int
    browser_success_rate: float
    code_only_passes: int
    code_only_trials: int
    code_only_success_rate: float
    browser_advantage_pp: float
    decision: Literal["advance", "revise", "reject", "incomplete"]
    failed_requirements: list[str] = Field(default_factory=list)
    hard_rejection_reasons: list[str] = Field(default_factory=list)


class LunaComparisonAssessment(BaseModel):
    model_id: str = LUNA_MODEL_ID
    attempts_per_condition: int
    browser_advantage_must_exceed_pp: float
    minimum_browser_success_rate: float
    maximum_browser_success_rate: float
    maximum_code_only_success_rate: float
    tasks: list[LunaTaskAssessment]

    @property
    def all_advance(self) -> bool:
        return bool(self.tasks) and all(task.decision == "advance" for task in self.tasks)


def load_gate_review(
    path: Path | str,
    project_root: Path | str = Path.cwd(),
    *,
    required_input_paths: Iterable[Path | str] = (),
) -> GateReview:
    project = Path(project_root).resolve()
    review_path = _resolve_project_path(path, project)
    review = GateReview.model_validate_json(review_path.read_text(encoding="utf-8"))
    errors = review.validate_input_hashes(project)
    for required_path in required_input_paths:
        required_key = _project_relative_key(required_path, project)
        if required_key not in review.input_sha256:
            errors.append(f"review input is required but not hashed: {required_key}")
    if errors:
        raise ValueError("; ".join(errors))
    return review


def _condition_name(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"cua", "browser", "browser_use"}:
        return "browser_use"
    if normalized == "code_only":
        return "code_only"
    raise ValueError(f"unsupported evaluation condition: {value}")


def assess_luna_comparison(
    summary: dict,
    *,
    attempts_per_condition: int = DEFAULT_ATTEMPTS_PER_CONDITION,
    browser_advantage_pp: float = DEFAULT_BROWSER_ADVANTAGE_PP,
    minimum_browser_success_rate: float = DEFAULT_MIN_BROWSER_SUCCESS_RATE,
    maximum_browser_success_rate: float = DEFAULT_MAX_BROWSER_SUCCESS_RATE,
    maximum_code_only_success_rate: float = DEFAULT_MAX_CODE_ONLY_SUCCESS_RATE,
) -> LunaComparisonAssessment:
    if minimum_browser_success_rate > maximum_browser_success_rate:
        raise ValueError("minimum browser success rate cannot exceed maximum")
    results = summary.get("results")
    if not isinstance(results, list):
        raise ValueError("comparison summary must contain a results list")

    grouped: dict[str, dict[str, list[dict]]] = {}
    for result in results:
        model = result.get("model", {})
        if model.get("key") != LUNA_MODEL_KEY or model.get("model_id") != LUNA_MODEL_ID:
            raise ValueError("comparison contains a model other than GPT 5.6 Luna")
        trial = result.get("trial", {})
        task_id = trial.get("task_id")
        condition = _condition_name(str(trial.get("condition", "")))
        if not task_id:
            raise ValueError("comparison result is missing trial.task_id")
        grouped.setdefault(str(task_id), {"browser_use": [], "code_only": []})[condition].append(result)

    assessments: list[LunaTaskAssessment] = []
    for task_id in sorted(grouped):
        by_condition = grouped[task_id]
        infra = [
            result
            for condition_results in by_condition.values()
            for result in condition_results
            if result.get("infrastructure_error") is True
        ]
        browser = [r for r in by_condition["browser_use"] if r.get("infrastructure_error") is not True]
        code_only = [r for r in by_condition["code_only"] if r.get("infrastructure_error") is not True]
        failed: list[str] = []
        if len(browser) != attempts_per_condition:
            failed.append(f"expected {attempts_per_condition} valid browser-use trials, found {len(browser)}")
        if len(code_only) != attempts_per_condition:
            failed.append(f"expected {attempts_per_condition} valid code-only trials, found {len(code_only)}")

        expected_attempts = list(range(1, attempts_per_condition + 1))
        for label, condition_results in (("browser-use", browser), ("code-only", code_only)):
            attempts = [result.get("trial", {}).get("attempt") for result in condition_results]
            if sorted(attempt for attempt in attempts if isinstance(attempt, int)) != expected_attempts:
                failed.append(
                    f"{label} valid trials must contain each attempt exactly once: "
                    f"expected {expected_attempts}, found {attempts}"
                )
            if any(not isinstance(result.get("verifier_success"), bool) for result in condition_results):
                failed.append(f"{label} valid trials must record boolean verifier_success")

        browser_usage: list[bool] = []
        for result in browser:
            capability_used = (
                ((result.get("protocol") or {}).get("cua_evidence") or {}).get("capability_used")
            )
            if not isinstance(capability_used, bool):
                failed.append("browser-use valid trials must record boolean browser capability usage")
                browser_usage.append(False)
            else:
                browser_usage.append(capability_used)

        browser_verifier_passes = sum(bool(result.get("verifier_success")) for result in browser)
        browser_successes_without_browser = sum(
            bool(result.get("verifier_success")) and not used
            for result, used in zip(browser, browser_usage)
        )
        browser_passes = sum(
            bool(result.get("verifier_success")) and used
            for result, used in zip(browser, browser_usage)
        )
        code_passes = sum(bool(result.get("verifier_success")) for result in code_only)
        browser_rate = browser_passes / len(browser) if browser else 0.0
        code_rate = code_passes / len(code_only) if code_only else 0.0
        advantage = 100.0 * (browser_rate - code_rate)

        hard_rejections: list[str] = []
        if browser_successes_without_browser:
            hard_rejections.append(
                "browser-capable agent passed without audited browser use; task is not CUA-necessary"
            )
        structurally_complete = not failed
        if structurally_complete:
            if browser_successes_without_browser:
                failed.append(
                    "successful browser-use trials must actually exercise the browser capability"
                )
            if browser_rate < minimum_browser_success_rate:
                failed.append("browser-use success is below the minimum")
            if browser_rate > maximum_browser_success_rate:
                failed.append("browser-use success is above the maximum; task is too easy")
            if code_rate > maximum_code_only_success_rate:
                failed.append("code-only success is above the maximum")
            if advantage <= browser_advantage_pp:
                failed.append("browser-use advantage does not exceed the required percentage points")

        decision: Literal["advance", "revise", "reject", "incomplete"]
        if hard_rejections:
            decision = "reject"
        elif not structurally_complete:
            decision = "incomplete"
        elif failed:
            decision = "revise"
        else:
            decision = "advance"
        assessments.append(
            LunaTaskAssessment(
                task_id=task_id,
                infrastructure_failures=len(infra),
                browser_verifier_passes=browser_verifier_passes,
                browser_successes_without_browser=browser_successes_without_browser,
                browser_passes=browser_passes,
                browser_trials=len(browser),
                browser_success_rate=browser_rate,
                code_only_passes=code_passes,
                code_only_trials=len(code_only),
                code_only_success_rate=code_rate,
                browser_advantage_pp=advantage,
                decision=decision,
                failed_requirements=failed,
                hard_rejection_reasons=hard_rejections,
            )
        )

    if not assessments:
        raise ValueError("comparison contains no GPT 5.6 Luna task results")
    return LunaComparisonAssessment(
        attempts_per_condition=attempts_per_condition,
        browser_advantage_must_exceed_pp=browser_advantage_pp,
        minimum_browser_success_rate=minimum_browser_success_rate,
        maximum_browser_success_rate=maximum_browser_success_rate,
        maximum_code_only_success_rate=maximum_code_only_success_rate,
        tasks=assessments,
    )


def load_and_assess_luna_comparison(path: Path | str, **kwargs: float | int) -> LunaComparisonAssessment:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    return assess_luna_comparison(summary, **kwargs)
