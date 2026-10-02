from __future__ import annotations

from pydantic import BaseModel, Field, computed_field, model_validator


class VerifierResult(BaseModel):
    name: str
    group: str
    command: str
    passed: bool
    expected: str = ""
    actual: str = ""
    expected_exit_code: int = 0
    actual_exit_code: int
    stdout: str
    stderr: str
    evidence_path: str | None = None

    @model_validator(mode="after")
    def populate_compatibility_fields(self) -> "VerifierResult":
        if not self.expected:
            self.expected = f"exit code {self.expected_exit_code}"
        if not self.actual:
            output = "\n".join(part for part in [self.stdout, self.stderr] if part).strip()
            self.actual = f"exit code {self.actual_exit_code}\n{output}".strip()
        return self


class VerifierReport(BaseModel):
    results: list[VerifierResult] = Field(default_factory=list)

    @computed_field
    @property
    def success(self) -> bool:
        return bool(self.results) and all(result.passed for result in self.results)

    @computed_field
    @property
    def progress(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for result in self.results if result.passed)
        return passed / len(self.results)


class RunResult(BaseModel):
    task_id: str
    success: bool
    progress: float
    patch_path: str | None
    verifier_report_path: str
    workspace_path: str
