from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print

from cua_swe_bench.baseline import BaselineDryRunner
from cua_swe_bench.diversity import audit_source
from cua_swe_bench.evaluator import EvaluatorAnnotator
from cua_swe_bench.llm.provider import ModelProvider, ModelProviderConfig
from cua_swe_bench.mobilegym_runtime import MOBILEGYM_PYTHON_ENV, MobileGymOutcome, MobileGymRuntime
from cua_swe_bench.registry import TaskRegistry
from cua_swe_bench.runner import BenchmarkRunner
from cua_swe_bench.workflow import (
    DEFAULT_MOBILEGYM_RUNS_ROOT,
    DEFAULT_MOBILEGYM_WORKFLOW_ROOT,
    WorkflowExecutor,
    WorkflowStore,
)

app = typer.Typer(help="CUA-SWE benchmark runner")
workflow_app = typer.Typer(help="Benchmark construction workflow automation")
baseline_app = typer.Typer(help="Baseline agent reproducibility helpers")
evaluator_app = typer.Typer(help="LLM evaluator annotation helpers")
mobilegym_app = typer.Typer(help="MobileGym upstream runtime helpers")
dataset_app = typer.Typer(help="Dataset inventory and diversity controls")
app.add_typer(workflow_app, name="workflow")
app.add_typer(baseline_app, name="baseline")
app.add_typer(evaluator_app, name="evaluator")
app.add_typer(mobilegym_app, name="mobilegym")
app.add_typer(dataset_app, name="dataset")


@app.command()
def list_tasks(tasks_root: Path = Path("dataset/web/tasks")) -> None:
    registry = TaskRegistry(tasks_root)
    for task in registry.list_tasks():
        print(f"{task.id}\t{task.track}\t{task.type}\t{task.difficulty}")


@dataset_app.command("audit-diversity")
def dataset_audit_diversity(
    source: Path = typer.Argument(..., help="Canonical manifest or candidate inventory YAML."),
    policy: Path = typer.Option(
        Path("dataset/pipeline/v2/diversity-policy.yaml"),
        "--policy",
        help="Diversity policy YAML.",
    ),
    phase: str = typer.Option("proposal", "--phase", help="Audit phase: proposal or freeze."),
    output: Optional[Path] = typer.Option(None, "--output", help="Optional JSON report path."),
    enforce: bool = typer.Option(True, "--enforce/--no-enforce", help="Exit non-zero when a gate fails."),
) -> None:
    if phase not in {"proposal", "freeze"}:
        raise typer.BadParameter("phase must be proposal or freeze", param_hint="--phase")
    audit = audit_source(source=source, policy_path=policy, phase=phase)  # type: ignore[arg-type]
    rendered = audit.model_dump_json(indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if enforce and not audit.ready:
        raise typer.Exit(1)


@app.command()
def run(task_file: Path, agent_command: str, runs_root: Path = Path("runs"), output_root: Path = Path("outputs")) -> None:
    runner = BenchmarkRunner(runs_root=runs_root, output_root=output_root)
    result = runner.run_task_file(task_file=task_file, agent_command=agent_command)
    print(result.model_dump_json(indent=2))


@workflow_app.command("validate")
def workflow_validate(tasks_root: Path = Path("dataset/web/tasks"), workflow_root: Path = Path("workflow_runs")) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).validate(tasks_root=tasks_root)
    print(paths.model_dump_json(indent=2))


@workflow_app.command("preflight")
def workflow_preflight(
    tasks_root: Path = Path("dataset/web/tasks"),
    workflow_root: Path = Path("workflow_runs"),
    mobilegym_repo: Path = Path("../baselines/repos/mobilegym"),
    require_provider: bool = typer.Option(False, "--require-provider", help="Require model provider config/client readiness."),
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).preflight(
        tasks_root=tasks_root,
        mobilegym_repo=mobilegym_repo,
        require_provider=require_provider,
    )
    print(paths.model_dump_json(indent=2))


@workflow_app.command("run-noop")
def workflow_run_noop(
    task_file: Path,
    runs_root: Path = Path("runs"),
    output_root: Path = Path("outputs"),
    workflow_root: Path = Path("workflow_runs"),
    agent_command: Optional[str] = None,
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).run_noop(
        task_file=task_file,
        runs_root=runs_root,
        output_root=output_root,
        agent_command=agent_command,
    )
    print(paths.model_dump_json(indent=2))


@workflow_app.command("run-gold")
def workflow_run_gold(
    task_file: Path,
    runs_root: Path = Path("runs"),
    output_root: Path = Path("outputs"),
    workflow_root: Path = Path("workflow_runs"),
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).run_gold(
        task_file=task_file,
        runs_root=runs_root,
        output_root=output_root,
    )
    print(paths.model_dump_json(indent=2))


@workflow_app.command("run-negative")
def workflow_run_negative(
    task_file: Path,
    runs_root: Path = Path("runs"),
    output_root: Path = Path("outputs"),
    workflow_root: Path = Path("workflow_runs"),
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).run_negative(
        task_file=task_file,
        runs_root=runs_root,
        output_root=output_root,
    )
    print(paths.model_dump_json(indent=2))


@workflow_app.command("certify-task")
def workflow_certify_task(
    task_file: Path,
    runs_root: Path = Path("runs"),
    output_root: Path = Path("outputs"),
    workflow_root: Path = Path("workflow_runs"),
    agent_command: Optional[str] = None,
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).certify_task(
        task_file=task_file,
        runs_root=runs_root,
        output_root=output_root,
        agent_command=agent_command,
    )
    print(paths.model_dump_json(indent=2))


@workflow_app.command("status")
def workflow_status(workflow_root: Path = Path("workflow_runs"), run_id: Optional[str] = None) -> None:
    manifest = WorkflowStore(workflow_root).read_manifest(run_id=run_id)
    print(f"{manifest.run_id}\t{manifest.workflow}\t{manifest.created_at}")
    for gate in manifest.preflight_gates:
        if gate.required and gate.status != "pass":
            print(f"preflight:{gate.name}\t{gate.status}\t{gate.message}")
    for status in manifest.task_statuses:
        blockers = [
            gate.name
            for gate in status.gates
            if gate.required and gate.status != "pass"
        ]
        blocker_text = ",".join(blockers) if blockers else "none"
        ready_text = "ready" if status.ready else "not-ready"
        print(f"{status.task_id}\t{ready_text}\t{blocker_text}")


@workflow_app.command("report")
def workflow_report(workflow_root: Path = Path("workflow_runs"), run_id: Optional[str] = None) -> None:
    report_path = WorkflowStore(workflow_root).write_construction_report(run_id=run_id)
    print(str(report_path))


@workflow_app.command("mobilegym-predata")
def workflow_mobilegym_predata(
    env_url: str,
    mobilegym_root: Path = Path("../baselines/repos/mobilegym"),
    task_id: str = "notes.CreateNoteWithReminder",
    suite: str = "notes",
    mobilegym_runs_root: Path = DEFAULT_MOBILEGYM_RUNS_ROOT,
    workflow_root: Path = DEFAULT_MOBILEGYM_WORKFLOW_ROOT,
    python_executable: Optional[str] = typer.Option(
        None,
        "--python",
        help=f"Python executable used for MobileGym. Defaults to {MOBILEGYM_PYTHON_ENV} or python3.",
    ),
    min_task_count: int = typer.Option(15, "--min-task-count"),
    headless: bool = typer.Option(True, "--headless/--headed"),
    replay_max_steps: int = typer.Option(40, "--replay-max-steps"),
    runtime_timeout_sec: int = typer.Option(60, "--runtime-timeout-sec"),
    noop_timeout_sec: int = typer.Option(180, "--noop-timeout-sec"),
    replay_timeout_sec: int = typer.Option(300, "--replay-timeout-sec"),
    canary_task_file: Optional[Path] = typer.Option(
        None,
        "--canary-task-file",
        help="Optional CUA-SWE task.yaml to certify after MobileGym runtime/replay gates pass.",
    ),
    canary_runs_root: Optional[Path] = typer.Option(
        None,
        "--canary-runs-root",
        help="Runs root for optional canary certification. Defaults under artifacts/mobilegym-canary-runs.",
    ),
    canary_output_root: Optional[Path] = typer.Option(
        None,
        "--canary-output-root",
        help="Output root for optional canary certification. Defaults under artifacts/mobilegym-canary-outputs.",
    ),
) -> None:
    paths = WorkflowExecutor(workflow_root=workflow_root).mobilegym_predata(
        mobilegym_root=mobilegym_root,
        env_url=env_url,
        task_id=task_id,
        suite=suite,
        mobilegym_runs_root=mobilegym_runs_root,
        python_executable=python_executable,
        min_task_count=min_task_count,
        headless=headless,
        replay_max_steps=replay_max_steps,
        runtime_timeout_sec=runtime_timeout_sec,
        noop_timeout_sec=noop_timeout_sec,
        replay_timeout_sec=replay_timeout_sec,
        canary_task_file=canary_task_file,
        canary_runs_root=canary_runs_root,
        canary_output_root=canary_output_root,
    )
    print(paths.model_dump_json(indent=2))


@app.command("provider-check")
def provider_check(
    model_id: Optional[str] = None,
    model_role: str = "default",
    provider: Optional[str] = typer.Option(None, "--provider", help="Wire protocol: responses, chat-completions, anthropic, or bedrock."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="API base URL; defaults to the routed or public endpoint."),
    api_key_env: Optional[str] = typer.Option(None, "--api-key-env", help="Environment variable holding the API key, or NONE."),
    invoke: bool = typer.Option(False, "--invoke", help="Call the configured model."),
) -> None:
    config = ModelProviderConfig.from_env(model_role=model_role).with_overrides(
        model_id=model_id,
        provider=provider,
        base_url=base_url,
        api_key_env=api_key_env,
    )
    result = ModelProvider(config).smoke_check(invoke=invoke)
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)


@baseline_app.command("dry-run")
def baseline_dry_run(
    task_file: Path,
    model_role: str = "construction",
    model_id: Optional[str] = None,
    provider: Optional[str] = typer.Option(None, "--provider", help="Wire protocol: responses, chat-completions, anthropic, or bedrock."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="API base URL; defaults to the routed or public endpoint."),
    api_key_env: Optional[str] = typer.Option(None, "--api-key-env", help="Environment variable holding the API key, or NONE."),
    prompt_template_id: str = "cua-swe-v0",
    agent_mode: str = "coding-active-cua",
    workflow_root: Path = Path("workflow_runs"),
) -> None:
    result = BaselineDryRunner(workflow_root=workflow_root).dry_run(
        task_file=task_file,
        provider=provider,
        model_role=model_role,
        model_id=model_id,
        base_url=base_url,
        api_key_env=api_key_env,
        prompt_template_id=prompt_template_id,
        agent_mode=agent_mode,
    )
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)


@evaluator_app.command("annotate-task")
def evaluator_annotate_task(
    task_file: Path,
    output_root: Path = Path("evaluator_runs"),
    model_role: str = "evaluator",
    model_id: Optional[str] = None,
    provider: Optional[str] = typer.Option(None, "--provider", help="Wire protocol: responses, chat-completions, anthropic, or bedrock."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="API base URL; defaults to the routed or public endpoint."),
    api_key_env: Optional[str] = typer.Option(None, "--api-key-env", help="Environment variable holding the API key, or NONE."),
    max_tokens: int = 1400,
    temperature: Optional[float] = None,
    invoke: bool = typer.Option(True, "--invoke/--no-invoke", help="Call the configured evaluator model."),
) -> None:
    result = EvaluatorAnnotator(output_root=output_root).annotate_task(
        task_file=task_file,
        invoke=invoke,
        model_role=model_role,
        model_id=model_id,
        provider=provider,
        base_url=base_url,
        api_key_env=api_key_env,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)


@evaluator_app.command("annotate-all")
def evaluator_annotate_all(
    tasks_root: Path = Path("dataset/web/tasks"),
    output_root: Path = Path("evaluator_runs"),
    model_role: str = "evaluator",
    model_id: Optional[str] = None,
    provider: Optional[str] = typer.Option(None, "--provider", help="Wire protocol: responses, chat-completions, anthropic, or bedrock."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="API base URL; defaults to the routed or public endpoint."),
    api_key_env: Optional[str] = typer.Option(None, "--api-key-env", help="Environment variable holding the API key, or NONE."),
    max_tokens: int = 1400,
    temperature: Optional[float] = None,
    invoke: bool = typer.Option(True, "--invoke/--no-invoke", help="Call the configured evaluator model."),
) -> None:
    annotator = EvaluatorAnnotator(output_root=output_root)
    ok = True
    for task_file in sorted(tasks_root.glob("**/task.yaml")):
        result = annotator.annotate_task(
            task_file=task_file,
            invoke=invoke,
            model_role=model_role,
            model_id=model_id,
            provider=provider,
            base_url=base_url,
            api_key_env=api_key_env,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        print(result.model_dump_json(indent=2))
        ok = ok and result.ok
    if not ok:
        raise typer.Exit(1)


@mobilegym_app.command("check-runtime")
def mobilegym_check_runtime(
    mobilegym_root: Path = Path("../baselines/repos/mobilegym"),
    python_executable: Optional[str] = typer.Option(
        None,
        "--python",
        help=f"Python executable used to run bench_env.run. Defaults to {MOBILEGYM_PYTHON_ENV} or python3.",
    ),
    suite: Optional[str] = typer.Option(None, "--suite", help="Optional MobileGym suite to list, such as notes."),
    env_url: Optional[str] = typer.Option(None, "--env-url", help="Simulator URL for online task listing."),
    list_online: bool = typer.Option(False, "--online/--static", help="Use MobileGym --list-online through the simulator."),
    include_task_ids: bool = typer.Option(False, "--include-task-ids", help="Include parsed task ids in output."),
    timeout_sec: int = typer.Option(30, "--timeout-sec", help="Runtime check timeout."),
) -> None:
    result = MobileGymRuntime(
        mobilegym_root=mobilegym_root,
        python_executable=python_executable,
    ).check(
        suite=suite,
        env_url=env_url,
        list_online=list_online,
        include_task_ids=include_task_ids,
        timeout_sec=timeout_sec,
    )
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)


@mobilegym_app.command("build-run-command")
def mobilegym_build_run_command(
    task_id: str,
    env_url: str,
    runs_dir: Path,
    agent: str = "human",
    mobilegym_root: Path = Path("../baselines/repos/mobilegym"),
    python_executable: Optional[str] = typer.Option(
        None,
        "--python",
        help=f"Python executable used to run bench_env.run. Defaults to {MOBILEGYM_PYTHON_ENV} or python3.",
    ),
    headless: bool = typer.Option(True, "--headless/--headed"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
) -> None:
    command = MobileGymRuntime(
        mobilegym_root=mobilegym_root,
        python_executable=python_executable,
    ).build_run_command(
        task_id=task_id,
        env_url=env_url,
        agent=agent,
        runs_dir=runs_dir,
        headless=headless,
        max_steps=max_steps,
    )
    print(command)


@mobilegym_app.command("run-task")
def mobilegym_run_task(
    task_id: str,
    env_url: str,
    runs_dir: Path = DEFAULT_MOBILEGYM_RUNS_ROOT / "manual",
    agent: str = "human",
    mobilegym_root: Path = Path("../baselines/repos/mobilegym"),
    python_executable: Optional[str] = typer.Option(
        None,
        "--python",
        help=f"Python executable used to run bench_env.run. Defaults to {MOBILEGYM_PYTHON_ENV} or python3.",
    ),
    expected_outcome: MobileGymOutcome = typer.Option(
        "success",
        "--expect",
        help="Expected MobileGym outcome: success, failed, error, not_success, or any.",
    ),
    headless: bool = typer.Option(True, "--headless/--headed"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
    quiet: bool = typer.Option(True, "--quiet/--verbose"),
    human_complete: bool = typer.Option(False, "--human-complete", help="Feed Enter to the human agent."),
    human_input: Optional[str] = typer.Option(None, "--human-input", help="Text fed to the human agent stdin."),
    timeout_sec: int = typer.Option(300, "--timeout-sec"),
) -> None:
    stdin_text = None
    if human_input is not None:
        stdin_text = f"{human_input}\n"
    elif human_complete:
        stdin_text = "\n"

    result = MobileGymRuntime(
        mobilegym_root=mobilegym_root,
        python_executable=python_executable,
    ).run_task(
        task_id=task_id,
        env_url=env_url,
        runs_dir=runs_dir,
        agent=agent,
        expected_outcome=expected_outcome,
        headless=headless,
        max_steps=max_steps,
        quiet=quiet,
        stdin_text=stdin_text,
        timeout_sec=timeout_sec,
    )
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)


@mobilegym_app.command("replay-task")
def mobilegym_replay_task(
    task_id: str,
    env_url: str,
    runs_dir: Path = DEFAULT_MOBILEGYM_RUNS_ROOT / "replay",
    mobilegym_root: Path = Path("../baselines/repos/mobilegym"),
    python_executable: Optional[str] = typer.Option(
        None,
        "--python",
        help=f"Python executable used to run the replay worker. Defaults to {MOBILEGYM_PYTHON_ENV} or python3.",
    ),
    expected_outcome: MobileGymOutcome = typer.Option(
        "success",
        "--expect",
        help="Expected MobileGym outcome: success, failed, error, not_success, or any.",
    ),
    replay_name: str = typer.Option("notes-create-note-with-reminder-v0", "--replay-name"),
    headless: bool = typer.Option(True, "--headless/--headed"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
    timeout_sec: int = typer.Option(300, "--timeout-sec"),
) -> None:
    result = MobileGymRuntime(
        mobilegym_root=mobilegym_root,
        python_executable=python_executable,
    ).replay_task(
        task_id=task_id,
        env_url=env_url,
        runs_dir=runs_dir,
        expected_outcome=expected_outcome,
        replay_name=replay_name,
        headless=headless,
        max_steps=max_steps,
        timeout_sec=timeout_sec,
    )
    print(result.model_dump_json(indent=2))
    if not result.ok:
        raise typer.Exit(1)
