from __future__ import annotations

import shlex
from pathlib import Path

from cua_swe_bench.adapters.base import GuiAction, GuiObservation
from cua_swe_bench.commands import CommandResult, run_command


class MobileGymAdapter:
    def __init__(self, mobilegym_root: Path, env_url: str, task_id: str, runs_dir: Path) -> None:
        self.mobilegym_root = Path(mobilegym_root)
        self.env_url = env_url
        self.task_id = task_id
        self.runs_dir = Path(runs_dir)

    def build_run_command(self, agent: str) -> str:
        return (
            "python -m bench_env.run "
            f"--task-id {shlex.quote(self.task_id)} "
            f"--env-url {shlex.quote(self.env_url)} "
            f"--agent {shlex.quote(agent)} "
            f"--runs-dir {shlex.quote(str(self.runs_dir))}"
        )

    def run_benchmark(self, agent: str, timeout_sec: int = 600) -> CommandResult:
        return run_command(self.build_run_command(agent), cwd=self.mobilegym_root, timeout_sec=timeout_sec)

    def start(self, _workspace: Path) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def observe(self) -> GuiObservation:
        return GuiObservation(
            url=self.env_url,
            text="MobileGym observation is produced by bench_env.run",
            metadata={"adapter": "mobilegym"},
        )

    def act(self, action: GuiAction) -> GuiObservation:
        raise RuntimeError("MobileGym actions are delegated to bench_env.run for the vertical slice")

    def stop(self) -> None:
        return None
