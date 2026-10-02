#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Iterator, Mapping

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cua_swe_bench.commands import CommandResult, run_command  # noqa: E402
from cua_swe_bench.recorder import ResultRecorder  # noqa: E402
from cua_swe_bench.results import VerifierReport, VerifierResult  # noqa: E402
from cua_swe_bench.schema import TaskBundle  # noqa: E402
from cua_swe_bench.workspace import Workspace, WorkspaceManager  # noqa: E402


CANONICAL_MANIFEST = REPO_ROOT / "dataset/manifest.yaml"


def _canonical_task_names() -> list[str]:
    payload = yaml.safe_load(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if payload.get("task_count") != 42 or len(tasks) != 42:
        raise RuntimeError("canonical dataset manifest must contain exactly 42 tasks")
    return [row["task_id"].removeprefix("web.") for row in tasks]


TASK_NAMES = _canonical_task_names()


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    runtime: str
    model_id: str


MODELS = [
    ModelSpec("gpt56-luna", "GPT 5.6 Luna", "codex", "gpt-5.6-luna"),
    ModelSpec("gpt54", "GPT 5.4", "codex", "gpt-5.4"),
    ModelSpec("qwen3vl235b", "Qwen3 VL 235B A22B", "qwen", "qwen3-vl-235b-a22b-instruct"),
    ModelSpec("opus48", "Claude Opus 4.8", "anthropic", "claude-opus-4-8"),
    ModelSpec("sonnet5", "Claude Sonnet 5.0", "anthropic", "claude-sonnet-5"),
    ModelSpec("haiku45", "Claude Haiku 4.5", "anthropic", "claude-haiku-4-5"),
    ModelSpec("fable5", "Claude Fable 5", "anthropic", "claude-fable-5"),
    ModelSpec("grok43", "Grok 4.3", "codex", "grok-4.3"),
    ModelSpec("kimi25", "Kimi K2.5", "kimi", "kimi-k2.5"),
    ModelSpec("api-gpt56-sol", "GPT 5.6 Sol (API)", "responses", "gpt-5.6-sol"),
    ModelSpec("api-gpt56-luna", "GPT 5.6 Luna (API)", "responses", "gpt-5.6-luna"),
    ModelSpec("api-gpt56-terra", "GPT 5.6 Terra (API)", "responses", "gpt-5.6-terra"),
    ModelSpec("api-gpt6-astra", "GPT-6 Astra (API)", "responses", "gpt-6-astra"),
    ModelSpec("api-opus5", "Claude Opus 5 (API)", "anthropic", "claude-opus-5"),
    ModelSpec("api-opus48", "Claude Opus 4.8 (API)", "anthropic", "claude-opus-4-8"),
    ModelSpec("api-sonnet5", "Claude Sonnet 5 (API)", "anthropic", "claude-sonnet-5"),
    ModelSpec("api-fable5", "Claude Fable 5 (API)", "anthropic", "claude-fable-5"),
    ModelSpec("api-grok46", "Grok 4.6 (API)", "responses", "grok-4.6"),
    ModelSpec("codex-gpt56-sol", "GPT 5.6 Sol (Codex CUA)", "codex", "gpt-5.6-sol"),
]


# Every model call goes through the shared provider gateway (scripts/provider_relay.py).
# The controller keeps provider credentials. Each trial's agent receives a lease: a
# token valid for one wire protocol and one model, revoked when the agent finishes.
# The lease token travels only in the agent process environment, never in argv.
RUNTIME_PROTOCOLS = {
    "codex": "responses",
    "claude": "anthropic",
    "responses": "responses",
    "anthropic": "anthropic",
    "kimi": "chat-completions",
    "qwen": "chat-completions",
}
PROVIDER_ROUTE_ENV_NAMES = (
    "CUA_SWE_PROVIDER_ROUTES",
    "CUA_SWE_CODEX_BASE_URL",
    "CUA_SWE_CODEX_API_KEY_ENV",
    "CUA_SWE_CLAUDE_BASE_URL",
)
PROVIDER_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CUA_SWE_PROVIDER_TOKEN",
)
GATEWAY_TOKEN_ENV = "CUA_SWE_GATEWAY_TOKEN"
CLI_RUNTIMES = frozenset({"codex", "claude"})
# Lease-delivered variables: present only in the agent's environment, scrubbed elsewhere.
PROVIDER_LEASE_ENV_NAMES = (
    *PROVIDER_ROUTE_ENV_NAMES,
    GATEWAY_TOKEN_ENV,
    "CUA_SWE_PROVIDER_CONFIG",
)
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_GATEWAY_LOCK = threading.Lock()
_GATEWAY: Any = None


def _provider_layer_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (
            parent / "scripts" / "provider_relay.py"
        ).is_file():
            return parent / "scripts"
    raise RuntimeError("scripts/provider_relay.py was not found above the evaluation runner")


def _load_provider_module(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _provider_layer_dir() / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the shared provider layer: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def provider_gateway() -> Any:
    """Start one controller-side gateway per runner process; it stops at exit."""
    global _GATEWAY
    with _GATEWAY_LOCK:
        if _GATEWAY is None:
            _load_provider_module("provider_client")
            relay = _load_provider_module("provider_relay")
            stack = contextlib.ExitStack()
            _GATEWAY = stack.enter_context(relay.gateway())
            atexit.register(stack.close)
        return _GATEWAY


def provider_secret_env_names(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Every API-key variable the controller may hold; scrubbed from agent commands."""
    env = os.environ if environ is None else environ
    names = list(PROVIDER_SECRET_ENV_NAMES)
    try:
        routes = json.loads(env.get("CUA_SWE_PROVIDER_ROUTES") or "{}")
    except ValueError:
        routes = {}
    if isinstance(routes, dict):
        names.extend(
            str(route.get("api_key_env") or "")
            for route in routes.values()
            if isinstance(route, dict)
        )
    names.append(str(env.get("CUA_SWE_CODEX_API_KEY_ENV") or ""))
    names.extend(name for name in env if name.upper().endswith("_API_KEY"))
    return tuple(
        dict.fromkeys(
            name
            for name in names
            if name not in {"NONE", GATEWAY_TOKEN_ENV} and _ENV_NAME.fullmatch(name)
        )
    )


def _require_provider_route(runtime: str) -> str:
    """Return the runtime's wire protocol; fail when the controller cannot authenticate it."""
    protocol = RUNTIME_PROTOCOLS.get(runtime)
    if protocol is None:
        raise ValueError(f"unsupported agent runtime: {runtime}")
    if not provider_gateway().serves(protocol):
        raise RuntimeError(
            f"provider configuration error: no authenticated {protocol} route for the "
            f"{runtime} runtime; set the routed API key on the controller "
            "(see CUA_SWE_PROVIDER_ROUTES)"
        )
    return protocol


@contextlib.contextmanager
def _provider_lease(runtime: str, model_id: str) -> Iterator[dict[str, str]]:
    """Yield the agent environment for a lease that is revoked when the block exits."""
    protocol = _require_provider_route(runtime)
    with provider_gateway().lease(protocol, model_id) as lease:
        yield dict(lease.environment(cli=runtime in CLI_RUNTIMES))


def agent_process_environment(
    lease_environment: Mapping[str, str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Controller environment for the agent process, with only this lease's routing."""
    env = dict(os.environ if environ is None else environ)
    for name in PROVIDER_LEASE_ENV_NAMES:
        env.pop(name, None)
    env.update(lease_environment)
    return env


def run_agent_command(
    command: str,
    *,
    cwd: Path,
    timeout_sec: int,
    lease_environment: Mapping[str, str],
) -> CommandResult:
    """run_command for the agent: the lease reaches it through the process environment."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            env=agent_process_environment(lease_environment),
        )
    except subprocess.TimeoutExpired as exc:
        def text(output: Any) -> str:
            if output is None:
                return ""
            return output.decode(errors="replace") if isinstance(output, bytes) else output

        stderr = text(exc.stderr)
        message = f"Command timed out after {timeout_sec} seconds"
        return CommandResult(
            command=command,
            exit_code=124,
            stdout=text(exc.stdout),
            stderr=f"{stderr}\n{message}" if stderr else message,
        )
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@dataclass(frozen=True)
class Trial:
    ordinal: int
    task_name: str
    model: ModelSpec
    attempt: int
    port: int

    @property
    def task_id(self) -> str:
        return f"web.{self.task_name}"

    @property
    def key(self) -> str:
        return f"{self.model.key}/{self.task_id}/attempt-{self.attempt}"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_task(task_name: str) -> TaskBundle:
    path = REPO_ROOT / "dataset" / "tasks" / "web" / task_name / "task.yaml"
    return TaskBundle.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _commit_harness_baseline(workspace: Workspace, port: int) -> dict[Path, bytes]:
    package_path = workspace.path / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.setdefault("scripts", {})
    for name, command in list(scripts.items()):
        if isinstance(command, str):
            scripts[name] = command.replace("4173", str(port))
    if "dev" not in scripts:
        scripts["dev"] = f"vite --host 127.0.0.1 --port {port}"
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    protected: dict[Path, bytes] = {}
    verifier_root = workspace.path / "verifiers"
    for verifier_path in verifier_root.rglob("*.py"):
        text = verifier_path.read_text(encoding="utf-8").replace("4173", str(port))
        verifier_path.write_text(text, encoding="utf-8")
        protected[verifier_path] = verifier_path.read_bytes()

    for command in (
        "git add package.json verifiers",
        "git -c user.name=cua-swe -c user.email=cua-swe@example.invalid commit -m 'parallel rollout port baseline'",
    ):
        result = run_command(command, cwd=workspace.path, timeout_sec=30)
        if not result.ok:
            raise RuntimeError(f"harness baseline command failed: {command}\n{result.stderr}")
    return protected


def _restore_verifiers(protected: dict[Path, bytes]) -> None:
    for path, content in protected.items():
        path.write_bytes(content)


def _cleanup_trial_processes(trial_dir: Path) -> None:
    marker = f"{trial_dir.resolve()}/"
    output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, command = line.split(None, 1)
        pid = int(pid_text)
        if marker not in command or pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _run_verifiers(
    task: TaskBundle,
    workspace: Path,
    python_bin: Path,
    environment: Mapping[str, str] | None = None,
) -> VerifierReport:
    results: list[VerifierResult] = []
    for group, command in task.verifiers.ordered_commands():
        values = {
            "CUA_SWE_PYTHON": str(python_bin),
            "CUA_SWE_MOBILEGYM_PYTHON": str(python_bin),
            **dict(environment or {}),
        }
        wrapped = shlex.join(
            ["env", *(f"{key}={value}" for key, value in values.items()), "sh", "-c", command]
        )
        command_result = run_command(wrapped, cwd=workspace, timeout_sec=task.budgets.wall_time_sec)
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


def _agent_command(
    trial: Trial,
    task: TaskBundle,
    rollout_dir: Path,
    python_bin: Path,
    condition: str,
) -> str:
    values = {
        "CUA_SWE_AGENT_ROLLOUT_DIR": str(rollout_dir),
        "CUA_SWE_TASK_ID": task.id,
        "CUA_SWE_TASK_INSTRUCTION": task.instruction,
        "CUA_SWE_AGENT_RUNTIME": trial.model.runtime,
        "CUA_SWE_WEB_PORT": str(trial.port),
        "CUA_SWE_WEB_URL": f"http://127.0.0.1:{trial.port}",
        "CUA_SWE_WEB_CUA_PYTHON": str(python_bin),
        "CUA_SWE_AGENT_PYTHON": str(python_bin),
        "CUA_SWE_PYTHON": str(python_bin),
        "CUA_SWE_CODEX_MODEL": trial.model.model_id,
        "CUA_SWE_CODEX_REASONING_EFFORT": "medium",
        "CUA_SWE_ANTHROPIC_MODEL": trial.model.model_id,
        "CUA_SWE_KIMI_MODEL": trial.model.model_id,
    }
    # Provider keys are scrubbed; the lease arrives through the process environment.
    command = ["env"]
    for name in provider_secret_env_names():
        command.extend(["-u", name])
    command.extend(f"{key}={value}" for key, value in values.items())
    script_name = "run_web_cua_agent.sh" if condition == "cua" else "run_code_only_agent.sh"
    command.extend(["bash", str(REPO_ROOT / "scripts" / script_name)])
    return shlex.join(command)


def _command_dict(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.ok,
    }


def run_trial(trial: Trial, run_root: Path, python_bin: Path, condition: str) -> dict[str, Any]:
    started = time.monotonic()
    trial_dir = run_root / "trials" / trial.model.key / trial.task_id / f"attempt-{trial.attempt}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = trial_dir / "trial.json"
    base_metadata = {
        "trial": {
            "ordinal": trial.ordinal,
            "key": trial.key,
            "task_id": trial.task_id,
            "attempt": trial.attempt,
            "port": trial.port,
        },
        "model": asdict(trial.model),
        "condition": condition,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(metadata_path, {**base_metadata, "status": "preparing"})

    try:
        task = _load_task(trial.task_name)
        workspace = WorkspaceManager(trial_dir / "run").prepare(task.id, task.repo_snapshot)
        protected = _commit_harness_baseline(workspace, trial.port)

        install_results = [
            run_command(command, cwd=workspace.path, timeout_sec=task.budgets.wall_time_sec)
            for command in task.setup.install
        ]
        reset_results = [
            run_command(command, cwd=workspace.path, timeout_sec=task.budgets.wall_time_sec)
            for command in task.setup.reset
        ]
        setup_results = install_results + reset_results
        if any(not result.ok for result in setup_results):
            result = {
                **base_metadata,
                "status": "setup_error",
                "benchmark_success": False,
                "setup": [_command_dict(item) for item in setup_results],
                "duration_sec": time.monotonic() - started,
            }
            _write_json(metadata_path, result)
            return result

        rollout_dir = trial_dir / "rollout"
        rollout_dir.mkdir(parents=True, exist_ok=True)
        agent_command = _agent_command(trial, task, rollout_dir, python_bin, condition)
        _write_json(metadata_path, {**base_metadata, "status": "running_agent"})
        with _provider_lease(trial.model.runtime, trial.model.model_id) as lease_environment:
            agent_result = run_agent_command(
                agent_command,
                cwd=workspace.path,
                timeout_sec=task.budgets.wall_time_sec,
                lease_environment=lease_environment,
            )

        _restore_verifiers(protected)
        report = _run_verifiers(task, workspace.path, python_bin)
        recorder_result = ResultRecorder(trial_dir / "result").record(
            task_id=task.id,
            workspace_path=workspace.path,
            patch=workspace.diff(),
            report=report,
        )
        benchmark_success = bool(agent_result.ok and report.success)
        status = "completed" if agent_result.ok else "agent_error"
        result = {
            **base_metadata,
            "status": status,
            "benchmark_success": benchmark_success,
            "verifier_success": report.success,
            "progress": report.progress,
            "agent": _command_dict(agent_result),
            "setup": [_command_dict(item) for item in setup_results],
            "run_result": recorder_result.model_dump(),
            "duration_sec": time.monotonic() - started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _cleanup_trial_processes(trial_dir)
        _write_json(metadata_path, result)
        return result
    except Exception as exc:
        result = {
            **base_metadata,
            "status": "harness_error",
            "benchmark_success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "duration_sec": time.monotonic() - started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _cleanup_trial_processes(trial_dir)
        _write_json(metadata_path, result)
        return result


def _rate(successes: int, trials: int) -> str:
    return (
        f"{successes}/{trials} ({(100 * successes / trials):.1f}%)"
        if trials
        else "0/0 (N/A)"
    )


def write_summary(
    run_root: Path,
    trials: list[Trial],
    results: list[dict[str, Any]],
    condition: str,
) -> None:
    by_key = {
        (result["model"]["key"], result["trial"]["task_id"], result["trial"]["attempt"]): result
        for result in results
    }
    rows: list[dict[str, Any]] = []
    for model in MODELS:
        selected = [trial for trial in trials if trial.model.key == model.key]
        model_results = [
            by_key[(trial.model.key, trial.task_id, trial.attempt)]
            for trial in selected
            if (trial.model.key, trial.task_id, trial.attempt) in by_key
        ]
        rows.append(
            {
                "model": asdict(model),
                "successes": sum(bool(item.get("benchmark_success")) for item in model_results),
                "trials": len(selected),
                "completed_results": len(model_results),
                "status_counts": {
                    status: sum(item.get("status") == status for item in model_results)
                    for status in sorted({str(item.get("status")) for item in model_results})
                },
            }
        )
    summary = {
        "run_root": str(run_root),
        "trial_count": len(trials),
        "result_count": len(results),
        "condition": condition,
        "models": rows,
        "results": results,
    }
    _write_json(run_root / "summary.json", summary)

    lines = [
        f"# {'Computer-Use' if condition == 'cua' else 'Code-Only'} Model Matrix",
        "",
        f"Trials: {len(results)}/{len(trials)} recorded.",
        "",
        "## Overall by model",
        "",
        "| Model | Success rate | Runtime/setup errors |",
        "| --- | ---: | ---: |",
    ]
    for row in rows:
        errors = sum(
            count
            for status, count in row["status_counts"].items()
            if status != "completed"
        )
        lines.append(
            f"| {row['model']['label']} | {_rate(row['successes'], row['trials'])} | {errors} |"
        )
    lines.extend(
        [
            "",
            "## By model and task",
            "",
            "| Model | Task | Success rate |",
            "| --- | --- | ---: |",
        ]
    )
    for model in MODELS:
        for task_name in TASK_NAMES:
            task_id = f"web.{task_name}"
            selected = [
                item
                for item in results
                if item["model"]["key"] == model.key and item["trial"]["task_id"] == task_id
            ]
            lines.append(
                f"| {model.label} | {task_id} | "
                f"{_rate(sum(bool(item.get('benchmark_success')) for item in selected), len(selected))} |"
            )
    (run_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_trials(args: argparse.Namespace) -> list[Trial]:
    models = [model for model in MODELS if not args.model or model.key in args.model]
    tasks = [task for task in TASK_NAMES if not args.task or task in args.task]
    trials: list[Trial] = []
    ordinal = 0
    for attempt in range(1, args.attempts + 1):
        for task_name in tasks:
            for model in models:
                trials.append(
                    Trial(
                        ordinal=ordinal,
                        task_name=task_name,
                        model=model,
                        attempt=attempt,
                        port=args.base_port + ordinal,
                    )
                )
                ordinal += 1
    return trials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the CUA or code-only model evaluation matrix"
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--base-port", type=int, default=43100)
    parser.add_argument("--condition", choices=("cua", "code-only"), default="cua")
    parser.add_argument("--model", action="append", choices=[model.key for model in MODELS])
    parser.add_argument("--task", action="append", choices=TASK_NAMES)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trials = build_trials(args)
    if args.dry_run:
        print(json.dumps([{"key": trial.key, "port": trial.port} for trial in trials], indent=2))
        return 0
    artifact_group = "model-matrix" if args.condition == "cua" else "code-only-matrix"
    run_root = (args.output_root or (
        REPO_ROOT / "artifacts" / artifact_group / _utc_stamp()
    )).expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    _write_json(
        run_root / "manifest.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "condition": args.condition,
            "computer_use_allowed": args.condition == "cua",
            "visual_feedback_allowed": args.condition == "cua",
            "tasks": [f"web.{name}" for name in TASK_NAMES],
            "models": [asdict(model) for model in MODELS],
            "attempts": args.attempts,
            "max_workers": args.max_workers,
            "trials": [{"key": trial.key, "port": trial.port} for trial in trials],
        },
    )
    print(f"RUN_ROOT={run_root}", flush=True)
    print(f"TRIALS={len(trials)} MAX_WORKERS={args.max_workers}", flush=True)

    results: list[dict[str, Any]] = []
    output_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_trial = {
            executor.submit(run_trial, trial, run_root, args.python, args.condition): trial
            for trial in trials
        }
        for future in as_completed(future_to_trial):
            trial = future_to_trial[future]
            result = future.result()
            results.append(result)
            with output_lock:
                print(
                    f"[{len(results):02d}/{len(trials):02d}] {trial.key} "
                    f"status={result['status']} success={result.get('benchmark_success', False)} "
                    f"duration={result.get('duration_sec', 0):.1f}s",
                    flush=True,
                )
                write_summary(run_root, trials, results, args.condition)

    write_summary(run_root, trials, results, args.condition)
    failures = sum(not bool(result.get("benchmark_success")) for result in results)
    print(f"COMPLETE successes={len(results) - failures} failures={failures}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
