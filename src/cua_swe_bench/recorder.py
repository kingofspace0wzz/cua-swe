from __future__ import annotations

import json
from pathlib import Path

from cua_swe_bench.results import RunResult, VerifierReport


class RecorderError(ValueError):
    pass


class ResultRecorder:
    def __init__(self, output_root: Path | str) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def record(self, task_id: str, workspace_path: Path | str, patch: str, report: VerifierReport) -> RunResult:
        self._validate_task_id(task_id)
        workspace = Path(workspace_path)
        run_dir = self.output_root / task_id
        run_dir.mkdir(parents=True, exist_ok=True)

        patch_path = run_dir / "patch.diff"
        report_path = run_dir / "verifier_report.json"
        result_path = run_dir / "run_result.json"

        patch_path.write_text(patch, encoding="utf-8")
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        result = RunResult(
            task_id=task_id,
            success=report.success,
            progress=report.progress,
            patch_path=str(patch_path),
            verifier_report_path=str(report_path),
            workspace_path=str(workspace),
        )
        result_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")
        return result

    def _validate_task_id(self, task_id: str) -> None:
        path = Path(task_id)
        if task_id in {"", ".", ".."} or path.is_absolute() or "/" in task_id or "\\" in task_id:
            raise RecorderError(f"unsafe task id: {task_id!r}")
