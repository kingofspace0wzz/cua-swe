from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
import yaml


AuditPhase = Literal["proposal", "freeze"]
GateStatus = Literal["pass", "fail", "not_evaluable"]
REAL_SOURCE_TYPES = {"real_repo", "adapted_real_repo", "behavior_derived_clean_room"}


class ProvenanceMetadata(BaseModel):
    source_type: Literal[
        "real_repo",
        "adapted_real_repo",
        "behavior_derived_clean_room",
        "synthetic",
    ]
    source_repo: str
    source_issue_or_pr: str | None = None
    source_revision: str | None = None
    license: str | None = None


class DiversityMetadata(BaseModel):
    product_domain: str
    framework: str
    ui_surface: str
    discovery_pattern: str
    bug_mechanism: str
    contract_channel: str
    patch_topology: str
    parent_template: str
    independence_group: str
    controlled_variant: bool = False


class CandidateRecord(BaseModel):
    candidate_id: str
    status: str
    task_file: str | None = None
    provenance: ProvenanceMetadata
    diversity: DiversityMetadata
    capability_necessity_hypothesis: str = Field(min_length=1)
    runtime_evidence: str = Field(min_length=1)
    materialization_verified: bool = False


class CandidateInventory(BaseModel):
    schema_version: int
    inventory_id: str
    status: str
    candidates: list[CandidateRecord]

    @model_validator(mode="after")
    def unique_candidates(self) -> "CandidateInventory":
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique")
        return self


class PhasePolicy(BaseModel):
    min_candidates: int = Field(ge=1)
    max_share_by_axis: dict[str, float] = Field(default_factory=dict)
    min_unique_by_axis: dict[str, int] = Field(default_factory=dict)
    min_real_source_share: float = Field(ge=0, le=1)
    max_tasks_per_source_repo: int = Field(ge=1)
    require_materialized_tasks: bool = False


class DiversityPolicy(BaseModel):
    schema_version: int
    policy_id: str
    proposal: PhasePolicy
    freeze: PhasePolicy


class AuditGate(BaseModel):
    name: str
    status: GateStatus
    observed: Any
    required: Any
    message: str


class DiversityAudit(BaseModel):
    schema_version: int = 1
    source_id: str
    phase: AuditPhase
    candidate_count: int
    independent_unit_count: int
    controlled_variant_count: int
    distributions: dict[str, dict[str, int]]
    gates: list[AuditGate]
    ready: bool
    caveats: list[str] = Field(default_factory=list)


def load_policy(path: Path | str) -> DiversityPolicy:
    return DiversityPolicy.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_candidate_inventory(path: Path | str) -> CandidateInventory:
    return CandidateInventory.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _normalized_source_fingerprint(text: str) -> str:
    text = re.sub(r"//[^\n]*|/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(
        r"`(?:\\.|[^`])*`|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'",
        " STRING ",
        text,
        flags=re.S,
    )
    text = re.sub(r"\b\d+(?:\.\d+)?\b", " NUMBER ", text)
    text = re.sub(r"[A-Za-z_$][A-Za-z0-9_$-]*", " IDENTIFIER ", text)
    text = re.sub(r"\s+", "", text)
    return sha256(text.encode("utf-8")).hexdigest()[:16]


def _detect_framework(package: dict[str, Any]) -> str:
    package_name = str(package.get("name") or "").lower()
    dependencies = {
        **(package.get("dependencies") or {}),
        **(package.get("devDependencies") or {}),
    }
    if package_name in {"ol", "openlayers"} or "ol" in dependencies:
        return "openlayers_map"
    # Large editor and visualization repositories often expose framework
    # adapters only in workspaces, so their root package looks like generic
    # JavaScript.  Preserve the actual reusable UI architecture instead of
    # collapsing every monorepo into ``other_web``.
    for marker, label in (
        ("@storybook/", "storybook_manager"),
        ("@xyflow/", "xyflow_canvas"),
        ("@codemirror/", "codemirror_editor"),
        ("@tiptap/", "tiptap_editor"),
        ("@fullcalendar/", "fullcalendar_scheduler"),
        ("@react-spectrum/", "react_spectrum"),
        ("@dnd-kit/", "dndkit_interaction"),
        ("@ag-grid-community/", "ag_grid"),
        ("ag-grid-", "ag_grid"),
        ("@monaco-editor/", "monaco_editor"),
        ("monaco-editor", "monaco_editor"),
        ("echarts", "echarts_visualization"),
        ("excalidraw", "excalidraw_canvas"),
        ("openlayers", "openlayers_map"),
        ("react-konva", "konva_canvas"),
        ("@tanstack/virtual", "tanstack_virtual"),
        ("react-window", "react_window_virtualizer"),
        ("slate", "slate_editor"),
        ("quill", "quill_editor"),
        ("recharts", "recharts_visualization"),
        ("handsontable", "handsontable_grid"),
        ("maplibre", "maplibre_webgl"),
    ):
        if marker in package_name or any(marker in dependency for dependency in dependencies):
            return label
    for dependency, label in (
        ("next", "nextjs"),
        ("react", "react"),
        ("vue", "vue"),
        ("svelte", "svelte"),
        ("@angular/core", "angular"),
    ):
        if dependency in dependencies:
            return label
    return "vanilla_js" if not dependencies else "other_web"


def _detect_surface(app_source: str) -> tuple[str, str]:
    lowered = app_source.lower()
    if "json.stringify" in lowered and "<pre" in lowered:
        return "diagnostic_json_card", "expand_raw_json_panel"
    if "<canvas" in lowered or "getcontext(" in lowered:
        return "canvas", "direct_manipulation"
    if "<table" in lowered:
        return "data_table", "table_interaction"
    if "role=\"dialog\"" in lowered or "<dialog" in lowered:
        return "modal", "modal_interaction"
    if "<form" in lowered:
        return "form", "form_interaction"
    return "single_page_content", "page_observation"


def _patch_topology(task_root: Path) -> str:
    patch_path = task_root / "gold.patch"
    if not patch_path.is_file():
        return "missing_gold_patch"
    patch = patch_path.read_text(encoding="utf-8", errors="replace")
    files = re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.M)
    hunks = len(re.findall(r"^@@", patch, flags=re.M))
    if len(files) == 1 and hunks == 1:
        return f"single_file_single_hunk:{files[0]}"
    if len(files) == 1:
        return f"single_file_multi_hunk:{files[0]}"
    return f"multi_file:{len(files)}"


def _family_index(project_root: Path, profile: dict[str, Any]) -> dict[str, str]:
    relative = profile.get("family_index")
    if not relative:
        return {}
    payload = yaml.safe_load((project_root / relative).read_text(encoding="utf-8"))
    return {
        row["task_id"]: row.get("family", "numeric_representation")
        for row in payload.get("examples", [])
    }


def inventory_from_manifest(path: Path | str) -> CandidateInventory:
    manifest_path = Path(path).resolve()
    project_root = manifest_path.parent.parent
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    profile = payload.get("collection_profile") or {}
    family_by_task = _family_index(project_root, profile)
    variant_parents = profile.get("controlled_variant_parents") or {}
    candidates: list[CandidateRecord] = []

    for row in payload.get("tasks", []):
        task_file = project_root / row["task_file"]
        task_root = task_file.parent
        task = yaml.safe_load(task_file.read_text(encoding="utf-8"))
        repo_root = project_root / task["repo_snapshot"]["path"]
        app_source = (repo_root / "src" / "app.js").read_text(encoding="utf-8", errors="replace")
        package = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
        surface, discovery = _detect_surface(app_source)
        controlled = row.get("cohort") == "frontier_calibration_stage_two"
        family = row.get("family") or family_by_task.get(row["task_id"], "unclassified")
        parent = variant_parents.get(row.get("family", ""), row["task_id"])
        repo_ref = task["repo_snapshot"].get("ref", "synthetic")
        candidates.append(
            CandidateRecord(
                candidate_id=row["task_id"],
                status="frozen_development_task",
                task_file=row["task_file"],
                provenance=ProvenanceMetadata(
                    source_type=profile.get("source_type", "synthetic"),
                    source_repo=profile.get("source_repo", f"synthetic:{repo_ref}"),
                    source_revision=repo_ref,
                ),
                diversity=DiversityMetadata(
                    product_domain=row["task_id"].split(".", 1)[1].rsplit("-contract", 1)[0],
                    framework=_detect_framework(package),
                    ui_surface=surface,
                    discovery_pattern=discovery,
                    bug_mechanism=family,
                    contract_channel="runtime_external_service",
                    patch_topology=_patch_topology(task_root),
                    parent_template=_normalized_source_fingerprint(app_source),
                    independence_group=parent if controlled else row["task_id"],
                    controlled_variant=controlled,
                ),
                capability_necessity_hypothesis=(
                    "The correct external contract is unavailable in source and observable only through the runtime UI."
                ),
                runtime_evidence="Expandable product diagnostics expose the live external contract.",
                materialization_verified=True,
            )
        )
    return CandidateInventory(
        schema_version=1,
        inventory_id=payload.get("collection_id", manifest_path.stem),
        status=payload.get("status", "unknown"),
        candidates=candidates,
    )


def _distribution(records: list[CandidateRecord], axis: str) -> Counter[str]:
    if axis == "source_repo":
        return Counter(record.provenance.source_repo for record in records)
    return Counter(str(getattr(record.diversity, axis)) for record in records)


def _independent_representatives(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Return one statistical unit per ancestry group.

    Prefer the non-variant parent when an inventory contains both a parent and
    controlled difficulty variants.  Variants remain visible in the audit, but
    cannot make a collection look more diverse than its independent sources.
    """
    by_group: dict[str, CandidateRecord] = {}
    for record in records:
        group = record.diversity.independence_group
        current = by_group.get(group)
        if current is None or (
            current.diversity.controlled_variant
            and not record.diversity.controlled_variant
        ):
            by_group[group] = record
    return list(by_group.values())


def audit_inventory(
    inventory: CandidateInventory,
    policy: DiversityPolicy,
    phase: AuditPhase,
) -> DiversityAudit:
    phase_policy = getattr(policy, phase)
    records = inventory.candidates
    quota_records = _independent_representatives(records)
    gates: list[AuditGate] = []
    axes = set(phase_policy.max_share_by_axis) | set(phase_policy.min_unique_by_axis) | {"source_repo"}
    distributions = {axis: dict(_distribution(quota_records, axis)) for axis in sorted(axes)}
    count = len(records)
    quota_count = len(quota_records)

    gates.append(
        AuditGate(
            name="minimum_candidate_count",
            status="pass" if quota_count >= phase_policy.min_candidates else "fail",
            observed=quota_count,
            required=f">={phase_policy.min_candidates}",
            message=f"inventory contains {quota_count} independent candidates ({count} task bundles)",
        )
    )

    for axis, maximum in sorted(phase_policy.max_share_by_axis.items()):
        values = _distribution(quota_records, axis)
        largest_label, largest_count = values.most_common(1)[0] if values else ("none", 0)
        observed = largest_count / quota_count if quota_count else 0.0
        gates.append(
            AuditGate(
                name=f"max_share:{axis}",
                status="pass" if observed <= maximum + 1e-12 else "fail",
                observed={"label": largest_label, "count": largest_count, "share": round(observed, 4)},
                required=f"<={maximum}",
                message=f"largest {axis} cluster is {largest_label}",
            )
        )

    for axis, minimum in sorted(phase_policy.min_unique_by_axis.items()):
        observed = len(_distribution(quota_records, axis))
        gates.append(
            AuditGate(
                name=f"min_unique:{axis}",
                status="pass" if observed >= minimum else "fail",
                observed=observed,
                required=f">={minimum}",
                message=f"inventory has {observed} unique {axis} values",
            )
        )

    real_count = sum(record.provenance.source_type in REAL_SOURCE_TYPES for record in quota_records)
    real_share = real_count / quota_count if quota_count else 0.0
    gates.append(
        AuditGate(
            name="minimum_real_source_share",
            status="pass" if real_share >= phase_policy.min_real_source_share else "fail",
            observed={"count": real_count, "share": round(real_share, 4)},
            required=f">={phase_policy.min_real_source_share}",
            message="real-source candidates include direct, adapted, and clean-room behavior-derived sources",
        )
    )

    largest_repo_count = max(_distribution(quota_records, "source_repo").values(), default=0)
    gates.append(
        AuditGate(
            name="maximum_tasks_per_source_repo",
            status="pass" if largest_repo_count <= phase_policy.max_tasks_per_source_repo else "fail",
            observed=largest_repo_count,
            required=f"<={phase_policy.max_tasks_per_source_repo}",
            message="maximum candidate count contributed by one source repository",
        )
    )

    materialized = sum(record.materialization_verified for record in records)
    if phase_policy.require_materialized_tasks:
        materialized_status: GateStatus = "pass" if materialized == count else "fail"
    else:
        materialized_status = "pass"
    gates.append(
        AuditGate(
            name="materialized_task_bundles",
            status=materialized_status,
            observed=materialized,
            required=f"{count}" if phase_policy.require_materialized_tasks else "not required in proposal phase",
            message="freeze admission requires every candidate to have a task bundle",
        )
    )

    controlled_count = sum(record.diversity.controlled_variant for record in records)
    ready = all(gate.status == "pass" for gate in gates)
    caveats = []
    if controlled_count:
        caveats.append(
            "Controlled variants share statistical ancestry and must not be reported as independent tasks."
        )
    if phase == "proposal":
        caveats.append(
            "Proposal readiness validates declared diversity only; source fingerprints become enforceable after materialization."
        )
    return DiversityAudit(
        source_id=inventory.inventory_id,
        phase=phase,
        candidate_count=count,
        independent_unit_count=quota_count,
        controlled_variant_count=controlled_count,
        distributions=distributions,
        gates=gates,
        ready=ready,
        caveats=caveats,
    )


def audit_source(
    source: Path | str,
    policy_path: Path | str,
    phase: AuditPhase,
) -> DiversityAudit:
    source_path = Path(source)
    payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if "tasks" in payload:
        inventory = inventory_from_manifest(source_path)
    else:
        inventory = _hydrate_materialized_inventory(
            CandidateInventory.model_validate(payload), source_path.resolve()
        )
    return audit_inventory(inventory, load_policy(policy_path), phase)


def _resolve_path(relative: str, source_path: Path) -> Path | None:
    requested = Path(relative)
    if requested.is_absolute():
        return requested if requested.exists() else None
    for root in (Path.cwd(), *source_path.parents):
        candidate = root / requested
        if candidate.exists():
            return candidate.resolve()
    return None


def _patched_source(task_root: Path, repo_root: Path) -> str:
    patch_path = task_root / "gold.patch"
    if not patch_path.is_file():
        return ""
    patch = patch_path.read_text(encoding="utf-8", errors="replace")
    files = re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.M)
    parts = []
    for relative in files:
        path = repo_root / relative
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _hydrate_materialized_inventory(
    inventory: CandidateInventory,
    source_path: Path,
) -> CandidateInventory:
    """Verify task paths and replace declared structural fields with evidence."""
    hydrated = []
    for record in inventory.candidates:
        task_file = _resolve_path(record.task_file, source_path) if record.task_file else None
        if task_file is None or not task_file.is_file():
            hydrated.append(record.model_copy(update={"materialization_verified": False}))
            continue
        task = yaml.safe_load(task_file.read_text(encoding="utf-8"))
        repo_root = _resolve_path(task["repo_snapshot"]["path"], task_file)
        if repo_root is None or not repo_root.is_dir():
            hydrated.append(record.model_copy(update={"materialization_verified": False}))
            continue
        source = _patched_source(task_file.parent, repo_root)
        if not source:
            hydrated.append(record.model_copy(update={"materialization_verified": False}))
            continue
        package_path = repo_root / "package.json"
        framework = record.diversity.framework
        if package_path.is_file():
            framework = _detect_framework(json.loads(package_path.read_text(encoding="utf-8")))
        diversity = record.diversity.model_copy(
            update={
                "framework": framework,
                "patch_topology": _patch_topology(task_file.parent),
                "parent_template": _normalized_source_fingerprint(source),
            }
        )
        hydrated.append(
            record.model_copy(
                update={"diversity": diversity, "materialization_verified": True}
            )
        )
    return inventory.model_copy(update={"candidates": hydrated})
