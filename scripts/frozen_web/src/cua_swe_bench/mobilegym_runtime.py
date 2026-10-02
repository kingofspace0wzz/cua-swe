from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from cua_swe_bench.commands import run_command
from cua_swe_bench.config import config_value, dotenv_values


MOBILEGYM_PYTHON_ENV = "CUA_SWE_MOBILEGYM_PYTHON"
MobileGymOutcome = Literal["success", "failed", "error", "not_success", "any"]


def default_mobilegym_python(start: Path | None = None) -> str:
    starts = [start] if start is not None else [Path.cwd(), Path(__file__).resolve()]
    for candidate in starts:
        value = config_value(MOBILEGYM_PYTHON_ENV, dotenv_values(start=candidate))
        if value:
            return value
    return "python3"


class MobileGymRuntimeCheck(BaseModel):
    ok: bool
    mobilegym_root: str
    python_executable: str
    env_url: str | None = None
    list_online: bool = False
    required_python: str = ">=3.11"
    python_version: str | None = None
    repo_present: bool = False
    bench_env_present: bool = False
    run_module_present: bool = False
    package_json_present: bool = False
    list_command: str | None = None
    list_exit_code: int | None = None
    task_count: int | None = None
    task_ids: list[str] = Field(default_factory=list)
    message: str
    stderr: str = ""


class MobileGymTaskRunCheck(BaseModel):
    ok: bool
    task_id: str
    expected_outcome: MobileGymOutcome
    observed_outcome: str | None = None
    mobilegym_root: str
    python_executable: str
    env_url: str
    runs_dir: str
    command: str
    exit_code: int | None = None
    run_dir: str | None = None
    summary_path: str | None = None
    results_path: str | None = None
    success_count: int | None = None
    failed_count: int | None = None
    error_count: int | None = None
    judge: dict[str, Any] | None = None
    message: str
    stdout: str = ""
    stderr: str = ""


class MobileGymRuntime:
    def __init__(
        self,
        mobilegym_root: Path | str = Path("../baselines/repos/mobilegym"),
        python_executable: str | None = None,
        min_python: tuple[int, int] = (3, 11),
    ) -> None:
        self.mobilegym_root = Path(mobilegym_root)
        self.python_executable = python_executable or default_mobilegym_python()
        self.min_python = min_python

    def check(
        self,
        suite: str | None = None,
        env_url: str | None = None,
        list_online: bool = False,
        include_task_ids: bool = False,
        timeout_sec: int = 30,
    ) -> MobileGymRuntimeCheck:
        root = self.mobilegym_root
        if not root.exists():
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                message=f"missing MobileGym repo: {root}",
            )

        bench_env_present = (root / "bench_env").is_dir()
        run_module_present = (root / "bench_env" / "run.py").exists()
        package_json_present = (root / "package.json").exists()

        if not bench_env_present or not run_module_present:
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                repo_present=True,
                bench_env_present=bench_env_present,
                run_module_present=run_module_present,
                package_json_present=package_json_present,
                message="MobileGym repo is missing bench_env/run.py",
            )

        version_result = run_command(
            self._python_version_command(),
            cwd=root,
            timeout_sec=timeout_sec,
        )
        python_version = version_result.stdout.strip()
        if not version_result.ok:
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                repo_present=True,
                bench_env_present=bench_env_present,
                run_module_present=run_module_present,
                package_json_present=package_json_present,
                list_exit_code=version_result.exit_code,
                message="could not execute configured Python interpreter",
                stderr=version_result.stderr,
            )

        parsed = self._parse_python_version(python_version)
        if parsed < self.min_python:
            required = ".".join(str(part) for part in self.min_python)
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                python_version=python_version,
                repo_present=True,
                bench_env_present=bench_env_present,
                run_module_present=run_module_present,
                package_json_present=package_json_present,
                message=f"MobileGym runtime requires Python >= {required}; got {python_version}",
            )

        try:
            command = self.build_list_command(
                suite=suite,
                env_url=env_url,
                list_online=list_online,
            )
        except ValueError as exc:
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                python_version=python_version,
                repo_present=True,
                bench_env_present=bench_env_present,
                run_module_present=run_module_present,
                package_json_present=package_json_present,
                message=str(exc),
            )

        list_result = run_command(command, cwd=root, timeout_sec=timeout_sec)
        task_ids = self._extract_task_ids(list_result.stdout)
        if not list_result.ok:
            return MobileGymRuntimeCheck(
                ok=False,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                list_online=list_online,
                python_version=python_version,
                repo_present=True,
                bench_env_present=bench_env_present,
                run_module_present=run_module_present,
                package_json_present=package_json_present,
                list_command=command,
                list_exit_code=list_result.exit_code,
                task_count=len(task_ids) if task_ids else None,
                task_ids=task_ids if include_task_ids else [],
                message="MobileGym bench_env.run --list failed",
                stderr=list_result.stderr or list_result.stdout,
            )

        return MobileGymRuntimeCheck(
            ok=True,
            mobilegym_root=str(root),
            python_executable=self.python_executable,
            env_url=env_url,
            list_online=list_online,
            python_version=python_version,
            repo_present=True,
            bench_env_present=bench_env_present,
            run_module_present=run_module_present,
            package_json_present=package_json_present,
            list_command=command,
            list_exit_code=list_result.exit_code,
            task_count=len(task_ids),
            task_ids=task_ids if include_task_ids else [],
            message=(
                "MobileGym runtime and online simulator listing work"
                if list_online
                else "MobileGym runtime is importable and task listing works"
            ),
        )

    def build_list_command(
        self,
        suite: str | None = None,
        env_url: str | None = None,
        list_online: bool = False,
        headless: bool = True,
    ) -> str:
        if list_online and not env_url:
            raise ValueError("MobileGym online listing requires --env-url")
        parts = [shlex.quote(self.python_executable), "-m", "bench_env.run", "--list"]
        if suite:
            parts.extend(["--suite", shlex.quote(suite)])
        if list_online:
            parts.extend(["--list-online", "--env-url", shlex.quote(env_url or "")])
            if headless:
                parts.append("--headless")
        return " ".join(parts)

    def build_run_command(
        self,
        task_id: str,
        env_url: str,
        agent: str,
        runs_dir: Path | str,
        *,
        headless: bool = True,
        max_steps: int | None = None,
        quiet: bool = False,
    ) -> str:
        parts = [
            shlex.quote(self.python_executable),
            "-m",
            "bench_env.run",
            "--task-id",
            shlex.quote(task_id),
            "--env-url",
            shlex.quote(env_url),
            "--agent",
            shlex.quote(agent),
            "--runs-dir",
            shlex.quote(str(runs_dir)),
        ]
        if headless:
            parts.append("--headless")
        if max_steps is not None:
            parts.extend(["--max-steps", str(max_steps)])
        if quiet:
            parts.append("--quiet")
        return " ".join(parts)

    def build_replay_command(
        self,
        task_id: str,
        env_url: str,
        runs_dir: Path | str,
        result_json: Path | str,
        *,
        replay_name: str = "notes-create-note-with-reminder-v0",
        headless: bool = True,
        max_steps: int | None = None,
    ) -> list[str]:
        parts = [
            self.python_executable,
            "-m",
            "cua_swe_bench.mobilegym_replay_worker",
            "--task-id",
            task_id,
            "--env-url",
            env_url,
            "--runs-dir",
            str(runs_dir),
            "--result-json",
            str(result_json),
            "--replay-name",
            replay_name,
        ]
        if headless:
            parts.append("--headless")
        else:
            parts.append("--headed")
        if max_steps is not None:
            parts.extend(["--max-steps", str(max_steps)])
        return parts

    def run_task(
        self,
        task_id: str,
        env_url: str,
        runs_dir: Path | str,
        *,
        agent: str = "human",
        expected_outcome: MobileGymOutcome = "success",
        headless: bool = True,
        max_steps: int | None = None,
        quiet: bool = True,
        stdin_text: str | None = None,
        timeout_sec: int = 300,
    ) -> MobileGymTaskRunCheck:
        root = self.mobilegym_root
        command = self.build_run_command(
            task_id=task_id,
            env_url=env_url,
            agent=agent,
            runs_dir=runs_dir,
            headless=headless,
            max_steps=max_steps,
            quiet=quiet,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                shell=True,
                text=True,
                input=stdin_text,
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._output_to_text(exc.stdout)
            stderr = self._output_to_text(exc.stderr)
            timeout_message = f"Command timed out after {timeout_sec} seconds"
            stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
            return MobileGymTaskRunCheck(
                ok=False,
                task_id=task_id,
                expected_outcome=expected_outcome,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                runs_dir=str(runs_dir),
                command=command,
                exit_code=124,
                message="MobileGym task run timed out",
                stdout=stdout,
                stderr=stderr,
            )

        base = self._task_run_base_result(
            task_id=task_id,
            expected_outcome=expected_outcome,
            env_url=env_url,
            runs_dir=runs_dir,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if completed.returncode != 0:
            return base.model_copy(
                update={
                    "ok": False,
                    "message": "MobileGym bench_env.run exited non-zero",
                }
            )

        try:
            run_dir = self._latest_run_dir(Path(runs_dir))
            summary_path = run_dir / "summary.json"
            results_path = run_dir / "results.jsonl"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            task_result = self._read_task_result(results_path, task_id)
        except Exception as exc:
            return base.model_copy(
                update={
                    "ok": False,
                    "message": f"could not read MobileGym run artifacts: {exc}",
                }
            )

        observed = self._observed_outcome(summary, task_result, task_id)
        ok = self._matches_expected(observed, expected_outcome)
        return base.model_copy(
            update={
                "ok": ok,
                "observed_outcome": observed,
                "run_dir": str(run_dir),
                "summary_path": str(summary_path),
                "results_path": str(results_path),
                "success_count": int(summary.get("success", 0) or 0),
                "failed_count": int(summary.get("failed", 0) or 0),
                "error_count": int(summary.get("error", 0) or 0),
                "judge": task_result.get("judge") if task_result else None,
                "message": (
                    f"MobileGym outcome matched expected {expected_outcome}"
                    if ok
                    else f"MobileGym outcome {observed} did not match expected {expected_outcome}"
                ),
            }
        )

    def replay_task(
        self,
        task_id: str,
        env_url: str,
        runs_dir: Path | str,
        *,
        expected_outcome: MobileGymOutcome = "success",
        replay_name: str = "notes-create-note-with-reminder-v0",
        headless: bool = True,
        max_steps: int | None = None,
        timeout_sec: int = 300,
    ) -> MobileGymTaskRunCheck:
        root = self.mobilegym_root
        result_json = Path(runs_dir) / "cua_swe_replay_result.json"
        result_json.parent.mkdir(parents=True, exist_ok=True)
        command_parts = self.build_replay_command(
            task_id=task_id,
            env_url=env_url,
            runs_dir=runs_dir,
            result_json=result_json,
            replay_name=replay_name,
            headless=headless,
            max_steps=max_steps,
        )
        command = " ".join(shlex.quote(part) for part in command_parts)
        env = os.environ.copy()
        src_root = Path(__file__).resolve().parents[1]
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(src_root)
            if not existing_pythonpath
            else f"{src_root}{os.pathsep}{existing_pythonpath}"
        )
        try:
            completed = subprocess.run(
                command_parts,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._output_to_text(exc.stdout)
            stderr = self._output_to_text(exc.stderr)
            timeout_message = f"Command timed out after {timeout_sec} seconds"
            stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
            return MobileGymTaskRunCheck(
                ok=False,
                task_id=task_id,
                expected_outcome=expected_outcome,
                mobilegym_root=str(root),
                python_executable=self.python_executable,
                env_url=env_url,
                runs_dir=str(runs_dir),
                command=command,
                exit_code=124,
                message="MobileGym replay timed out",
                stdout=stdout,
                stderr=stderr,
            )

        base = self._task_run_base_result(
            task_id=task_id,
            expected_outcome=expected_outcome,
            env_url=env_url,
            runs_dir=runs_dir,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        try:
            run_dir = self._latest_run_dir(Path(runs_dir))
            summary_path = run_dir / "summary.json"
            results_path = run_dir / "results.jsonl"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            task_result = self._read_task_result(results_path, task_id)
        except Exception as exc:
            worker_payload = None
            if result_json.exists():
                try:
                    worker_payload = json.loads(result_json.read_text(encoding="utf-8"))
                except Exception:
                    worker_payload = None
            message = f"could not read MobileGym replay artifacts: {exc}"
            if worker_payload and worker_payload.get("message"):
                message = f"{message}; worker: {worker_payload['message']}"
            return base.model_copy(update={"ok": False, "message": message})

        observed = self._observed_outcome(summary, task_result, task_id)
        ok = self._matches_expected(observed, expected_outcome)
        return base.model_copy(
            update={
                "ok": ok,
                "observed_outcome": observed,
                "run_dir": str(run_dir),
                "summary_path": str(summary_path),
                "results_path": str(results_path),
                "success_count": int(summary.get("success", 0) or 0),
                "failed_count": int(summary.get("failed", 0) or 0),
                "error_count": int(summary.get("error", 0) or 0),
                "judge": task_result.get("judge") if task_result else None,
                "message": (
                    f"MobileGym replay outcome matched expected {expected_outcome}"
                    if ok
                    else f"MobileGym replay outcome {observed} did not match expected {expected_outcome}"
                ),
            }
        )

    def _python_version_command(self) -> str:
        code = (
            "import sys; "
            "print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        )
        return f"{shlex.quote(self.python_executable)} -c {shlex.quote(code)}"

    def _parse_python_version(self, version: str) -> tuple[int, int]:
        match = re.search(r"(\d+)\.(\d+)", version)
        if not match:
            return (0, 0)
        return (int(match.group(1)), int(match.group(2)))

    def _extract_task_ids(self, output: str) -> list[str]:
        task_ids: list[str] = []
        for line in output.splitlines():
            match = re.search(r"\b([a-zA-Z0-9_]+\.[A-Za-z][A-Za-z0-9_]*)\b", line)
            if match and match.group(1) not in task_ids:
                task_ids.append(match.group(1))
        return task_ids

    def _task_run_base_result(
        self,
        *,
        task_id: str,
        expected_outcome: MobileGymOutcome,
        env_url: str,
        runs_dir: Path | str,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> MobileGymTaskRunCheck:
        return MobileGymTaskRunCheck(
            ok=False,
            task_id=task_id,
            expected_outcome=expected_outcome,
            mobilegym_root=str(self.mobilegym_root),
            python_executable=self.python_executable,
            env_url=env_url,
            runs_dir=str(runs_dir),
            command=command,
            exit_code=exit_code,
            message="MobileGym task run has not been evaluated",
            stdout=stdout,
            stderr=stderr,
        )

    def _latest_run_dir(self, runs_dir: Path) -> Path:
        candidates = [path for path in runs_dir.iterdir() if (path / "summary.json").exists()]
        if not candidates:
            raise FileNotFoundError(f"no MobileGym summary.json found under {runs_dir}")
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _read_task_result(self, results_path: Path, task_id: str) -> dict[str, Any]:
        if not results_path.exists():
            return {}
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            result = json.loads(line)
            if result.get("id") == task_id:
                return result
        return {}

    def _observed_outcome(
        self,
        summary: dict[str, Any],
        task_result: dict[str, Any],
        task_id: str,
    ) -> str:
        if task_result.get("is_error"):
            return "error"
        if task_result.get("is_success"):
            return "success"
        if task_result:
            return "failed"

        if task_id in summary.get("error_tasks", []):
            return "error"
        if task_id in summary.get("success_tasks", []):
            return "success"
        if task_id in summary.get("failed_tasks", []):
            return "failed"
        return "unknown"

    def _matches_expected(self, observed: str, expected: MobileGymOutcome) -> bool:
        if expected == "any":
            return observed in {"success", "failed", "error"}
        if expected == "not_success":
            return observed in {"failed", "error"}
        return observed == expected

    def _output_to_text(self, output: str | bytes | None) -> str:
        if output is None:
            return ""
        if isinstance(output, bytes):
            return output.decode(errors="replace")
        return output
