from __future__ import annotations

from pathlib import Path

from cua_swe_bench.commands import run_command
from cua_swe_bench.results import VerifierReport, VerifierResult
from cua_swe_bench.schema import VerifierSpec


class VerifierRunner:
    def __init__(self, timeout_sec: int = 120) -> None:
        self.timeout_sec = timeout_sec

    def run(self, spec: VerifierSpec, cwd: Path) -> VerifierReport:
        results: list[VerifierResult] = []
        for group, command in spec.ordered_commands():
            command_result = run_command(command, cwd=cwd, timeout_sec=self.timeout_sec)
            results.append(
                VerifierResult(
                    name=f"{group}: {command}",
                    group=group,
                    command=command,
                    passed=command_result.ok,
                    actual_exit_code=command_result.exit_code,
                    stdout=command_result.stdout,
                    stderr=command_result.stderr,
                )
            )
        return VerifierReport(results=results)
