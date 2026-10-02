from __future__ import annotations

from pathlib import Path
import time

import yaml

from cua_swe_bench.commands import RunningCommand, run_command, start_command
from cua_swe_bench.recorder import ResultRecorder
from cua_swe_bench.results import RunResult, VerifierReport, VerifierResult
from cua_swe_bench.schema import TaskBundle
from cua_swe_bench.verifiers import VerifierRunner
from cua_swe_bench.workspace import Workspace, WorkspaceManager


class BenchmarkRunner:
    def __init__(self, runs_root: Path | str, output_root: Path | str, launch_startup_wait_sec: float = 0.5) -> None:
        self.workspace_manager = WorkspaceManager(runs_root)
        self.recorder = ResultRecorder(output_root)
        self.launch_startup_wait_sec = launch_startup_wait_sec

    def run_task_file(self, task_file: Path | str, agent_command: str) -> RunResult:
        data = yaml.safe_load(Path(task_file).read_text(encoding="utf-8"))
        task = TaskBundle.model_validate(data)
        return self.run_task(task, agent_command)

    def run_task(self, task: TaskBundle, agent_command: str) -> RunResult:
        workspace = self.workspace_manager.prepare(task.id, task.repo_snapshot)
        launch_processes: list[RunningCommand] = []

        try:
            for command in task.setup.install:
                install_result = run_command(command, cwd=workspace.path, timeout_sec=task.budgets.wall_time_sec)
                if not install_result.ok:
                    return self._record_failure(
                        task=task,
                        workspace=workspace,
                        group="setup",
                        command=command,
                        actual_exit_code=install_result.exit_code,
                        stdout=install_result.stdout,
                        stderr=install_result.stderr,
                    )

            for command in task.setup.reset:
                reset_result = run_command(command, cwd=workspace.path, timeout_sec=task.budgets.wall_time_sec)
                if not reset_result.ok:
                    return self._record_failure(
                        task=task,
                        workspace=workspace,
                        group="setup",
                        command=command,
                        actual_exit_code=reset_result.exit_code,
                        stdout=reset_result.stdout,
                        stderr=reset_result.stderr,
                    )

            for command in task.setup.launch:
                launch_processes.append(start_command(command, cwd=workspace.path))
            launch_failure = self._check_launch_processes(launch_processes)
            if launch_failure is not None:
                command, exit_code, stdout, stderr = launch_failure
                return self._record_failure(
                    task=task,
                    workspace=workspace,
                    group="setup",
                    command=command,
                    actual_exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                )

            agent_result = run_command(agent_command, cwd=workspace.path, timeout_sec=task.budgets.wall_time_sec)
            if not agent_result.ok:
                return self._record_failure(
                    task=task,
                    workspace=workspace,
                    group="agent",
                    command=agent_command,
                    actual_exit_code=agent_result.exit_code,
                    stdout=agent_result.stdout,
                    stderr=agent_result.stderr,
                )

            report = VerifierRunner(timeout_sec=task.budgets.wall_time_sec).run(task.verifiers, cwd=workspace.path)
            return self.recorder.record(
                task_id=task.id,
                workspace_path=workspace.path,
                patch=workspace.diff(),
                report=report,
            )
        finally:
            for process in reversed(launch_processes):
                process.stop()

    def _check_launch_processes(self, launch_processes: list[RunningCommand]) -> tuple[str, int, str, str] | None:
        if not launch_processes:
            return None
        if self.launch_startup_wait_sec > 0:
            time.sleep(self.launch_startup_wait_sec)
        for process in launch_processes:
            result = process.result_if_exited()
            if result is not None:
                stderr = result.stderr
                message = "setup.launch exited before agent/verifier execution"
                stderr = f"{stderr}\n{message}" if stderr else message
                return result.command, result.exit_code, result.stdout, stderr
        return None

    def _record_failure(
        self,
        task: TaskBundle,
        workspace: Workspace,
        group: str,
        command: str,
        actual_exit_code: int,
        stdout: str,
        stderr: str,
    ) -> RunResult:
        actual = "\n".join(
            [
                f"command: {command}",
                f"cwd: {workspace.path}",
                f"exit code: {actual_exit_code}",
                f"stdout: {stdout}",
                f"stderr: {stderr}",
            ]
        )
        report = VerifierReport(
            results=[
                VerifierResult(
                    name=f"{group}: {command}",
                    group=group,
                    command=command,
                    passed=False,
                    expected="exit code 0",
                    actual=actual,
                    expected_exit_code=0,
                    actual_exit_code=actual_exit_code,
                    stdout=stdout,
                    stderr=stderr,
                )
            ]
        )
        return self.recorder.record(
            task_id=task.id,
            workspace_path=workspace.path,
            patch=workspace.diff(),
            report=report,
        )
