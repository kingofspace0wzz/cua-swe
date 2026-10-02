from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel

from cua_swe_bench.llm.provider import WIRE_PROTOCOLS, ModelCheckResult, ModelProvider, ModelProviderConfig
from cua_swe_bench.schema import TaskBundle


class BaselineDryRunResult(BaseModel):
    ok: bool
    provider: str | None
    task_id: str
    model_id: str | None
    base_url: str | None
    api_key_env: str | None
    prompt_template_id: str
    agent_mode: str
    allowed_tools: dict[str, bool]
    provider_check: ModelCheckResult | None = None
    artifact_path: str | None = None
    message: str = ""


class BaselineDryRunner:
    def __init__(self, workflow_root: Path | str = Path("workflow_runs")) -> None:
        self.workflow_root = Path(workflow_root)
        self.workflow_root.mkdir(parents=True, exist_ok=True)

    def dry_run(
        self,
        task_file: Path | str,
        provider: str | None = None,
        model_role: str = "construction",
        model_id: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
        prompt_template_id: str = "cua-swe-v0",
        agent_mode: str = "coding-active-cua",
    ) -> BaselineDryRunResult:
        task = self._load_task(task_file)
        if provider is not None and provider not in WIRE_PROTOCOLS:
            result = BaselineDryRunResult(
                ok=False,
                provider=provider,
                task_id=task.id,
                model_id=model_id,
                base_url=base_url,
                api_key_env=api_key_env,
                prompt_template_id=prompt_template_id,
                agent_mode=agent_mode,
                allowed_tools=task.allowed_tools.model_dump(),
                message=f"unsupported provider: {provider}",
            )
            return self._record(result)

        config = ModelProviderConfig.from_env(model_role=model_role).with_overrides(
            model_id=model_id,
            provider=provider,
            base_url=base_url,
            api_key_env=api_key_env,
        )
        check = ModelProvider(config).smoke_check(invoke=False)
        result = BaselineDryRunResult(
            ok=check.ok,
            provider=check.provider,
            task_id=task.id,
            model_id=config.model_id,
            base_url=check.base_url,
            api_key_env=check.api_key_env,
            prompt_template_id=prompt_template_id,
            agent_mode=agent_mode,
            allowed_tools=task.allowed_tools.model_dump(),
            provider_check=check,
            message="baseline dry-run recorded" if check.ok else check.message,
        )
        return self._record(result)

    def _load_task(self, task_file: Path | str) -> TaskBundle:
        data = yaml.safe_load(Path(task_file).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"task file must contain a mapping: {task_file}")
        return TaskBundle.model_validate(data)

    def _record(self, result: BaselineDryRunResult) -> BaselineDryRunResult:
        run_dir = self.workflow_root / self._unique_run_id()
        run_dir.mkdir(parents=True)
        artifact_path = run_dir / "baseline_dry_run.json"
        summary_path = run_dir / "summary.md"
        result = result.model_copy(update={"artifact_path": str(artifact_path)})
        artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        summary_path.write_text(self._render_summary(result), encoding="utf-8")
        return result

    def _unique_run_id(self) -> str:
        base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-baseline-dry-run")
        candidate = base
        suffix = 2
        while (self.workflow_root / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _render_summary(self, result: BaselineDryRunResult) -> str:
        lines = [
            "# Baseline Dry Run",
            "",
            f"- Provider: `{result.provider}`",
            f"- Task: `{result.task_id}`",
            f"- Agent mode: `{result.agent_mode}`",
            f"- Prompt template: `{result.prompt_template_id}`",
            f"- Model id: `{result.model_id}`",
            f"- Base URL: `{result.base_url}`",
            f"- API key variable: `{result.api_key_env}`",
            f"- OK: `{result.ok}`",
            f"- Message: {result.message}",
            "",
            "## Allowed Tools",
            "",
        ]
        for name, enabled in result.allowed_tools.items():
            lines.append(f"- `{name}`: `{enabled}`")
        lines.append("")
        return "\n".join(lines)
