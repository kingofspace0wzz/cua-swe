from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from cua_swe_bench.llm.provider import ModelProvider, ModelProviderConfig, ModelTextResult
from cua_swe_bench.schema import TaskBundle


PROMPT_TEMPLATE_ID = "cua-swe-evaluator-v0"


class EvaluatorAnnotationResult(BaseModel):
    ok: bool
    task_id: str
    model_id: str | None
    provider: str | None
    base_url: str | None
    api_key_env: str | None
    prompt_template_id: str
    invoked: bool
    prompt_path: str
    raw_response_path: str | None = None
    annotation_json_path: str | None = None
    summary_path: str
    provider_result: ModelTextResult | None = None
    message: str = ""


class EvaluatorAnnotator:
    def __init__(self, output_root: Path | str = Path("evaluator_runs")) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def annotate_task(
        self,
        task_file: Path | str,
        invoke: bool = True,
        model_role: str = "evaluator",
        model_id: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
        max_tokens: int = 1400,
        temperature: float | None = None,
    ) -> EvaluatorAnnotationResult:
        task_path = Path(task_file)
        task = self._load_task(task_path)
        prompt = self._build_prompt(task_path=task_path, task=task)
        config = ModelProviderConfig.from_env(model_role=model_role).with_overrides(
            model_id=model_id,
            provider=provider,
            base_url=base_url,
            api_key_env=api_key_env,
        ).model_copy(update={"max_tokens": max_tokens, "temperature": temperature})

        run_dir = self._task_run_dir(task.id)
        prompt_path = run_dir / "prompt.txt"
        raw_path = run_dir / "annotation_raw.txt"
        annotation_path = run_dir / "annotation.json"
        summary_path = run_dir / "summary.md"
        prompt_path.write_text(prompt, encoding="utf-8")

        if not invoke:
            result = EvaluatorAnnotationResult(
                ok=True,
                task_id=task.id,
                model_id=config.model_id,
                provider=config.protocol,
                base_url=config.base_url,
                api_key_env=config.api_key_env,
                prompt_template_id=PROMPT_TEMPLATE_ID,
                invoked=False,
                prompt_path=str(prompt_path),
                summary_path=str(summary_path),
                message="prompt recorded without invoking evaluator",
            )
            summary_path.write_text(self._render_summary(result, annotation=None), encoding="utf-8")
            return result

        provider_result = ModelProvider(config).converse_text(prompt)
        raw_path.write_text(provider_result.output_text, encoding="utf-8")
        parsed = self._parse_json_object(provider_result.output_text)
        if parsed is not None:
            annotation_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

        result = EvaluatorAnnotationResult(
            ok=provider_result.ok,
            task_id=task.id,
            model_id=config.model_id,
            provider=provider_result.provider,
            base_url=provider_result.base_url,
            api_key_env=provider_result.api_key_env,
            prompt_template_id=PROMPT_TEMPLATE_ID,
            invoked=True,
            prompt_path=str(prompt_path),
            raw_response_path=str(raw_path),
            annotation_json_path=str(annotation_path) if parsed is not None else None,
            summary_path=str(summary_path),
            provider_result=provider_result,
            message=provider_result.message,
        )
        summary_path.write_text(self._render_summary(result, annotation=parsed), encoding="utf-8")
        return result

    def _load_task(self, task_file: Path) -> TaskBundle:
        data = yaml.safe_load(task_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"task file must contain a mapping: {task_file}")
        return TaskBundle.model_validate(data)

    def _task_run_dir(self, task_id: str) -> Path:
        safe_task_id = task_id.replace("/", "_")
        base = datetime.now(timezone.utc).strftime(f"%Y%m%dT%H%M%SZ-evaluator-{safe_task_id}")
        candidate = self.output_root / base
        suffix = 2
        while candidate.exists():
            candidate = self.output_root / f"{base}-{suffix}"
            suffix += 1
        candidate.mkdir(parents=True)
        return candidate

    def _build_prompt(self, task_path: Path, task: TaskBundle) -> str:
        task_dir = task_path.parent
        context = {
            "task_yaml": task_path.read_text(encoding="utf-8"),
            "replay": self._read_optional(task_dir / "replay.md"),
            "gold_patch": self._read_optional(task_dir / "gold.patch") or self._read_optional(task_dir / "gold.diff"),
            "negative_patch": self._read_optional(task_dir / "negative.patch") or self._first_negative_patch(task_dir),
            "verifiers": self._read_verifiers(task_dir),
        }
        return "\n".join(
            [
                "You are an advisory evaluator for CUA-SWE benchmark construction.",
                "The deterministic verifier and certification workflow decide pass/fail. Your role is to annotate benchmark quality only.",
                "Return only a JSON object with these keys:",
                "ambiguity_risk: low|medium|high",
                "verifier_adequacy: low|medium|high",
                "cua_relevance: low|medium|high",
                "implementation_leakage_risk: low|medium|high",
                "side_effect_risk: low|medium|high",
                "recommended_action: accept|revise|reject",
                "rationale: short string",
                "notes: array of short strings",
                "",
                f"Task id: {task.id}",
                f"Track: {task.track}",
                f"Type: {task.type}",
                f"Difficulty: {task.difficulty}",
                "",
                "## task.yaml",
                self._truncate(context["task_yaml"]),
                "",
                "## replay.md",
                self._truncate(context["replay"]),
                "",
                "## verifier files",
                self._truncate(context["verifiers"]),
                "",
                "## gold patch",
                self._truncate(context["gold_patch"]),
                "",
                "## negative patch",
                self._truncate(context["negative_patch"]),
            ]
        )

    def _read_optional(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _first_negative_patch(self, task_dir: Path) -> str:
        negatives = task_dir / "negatives"
        if not negatives.exists():
            return ""
        for path in sorted([*negatives.glob("*.patch"), *negatives.glob("*.diff")]):
            return path.read_text(encoding="utf-8")
        return ""

    def _read_verifiers(self, task_dir: Path) -> str:
        verifier_dir = task_dir / "repo" / "verifiers"
        if not verifier_dir.exists():
            return ""
        chunks = []
        for path in sorted(verifier_dir.iterdir()):
            if path.is_file() and path.suffix in {".py", ".js", ".jsx", ".ts", ".tsx"}:
                chunks.append(f"### {path.relative_to(task_dir)}\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(chunks)

    def _truncate(self, text: str, max_chars: int = 12000) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[truncated]"

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _render_summary(self, result: EvaluatorAnnotationResult, annotation: dict[str, Any] | None) -> str:
        lines = [
            "# Evaluator Annotation",
            "",
            f"- Task: `{result.task_id}`",
            f"- Prompt template: `{result.prompt_template_id}`",
            f"- Model id: `{result.model_id}`",
            f"- Invoked: `{result.invoked}`",
            f"- OK: `{result.ok}`",
            f"- Message: {result.message}",
            f"- Prompt: `{result.prompt_path}`",
        ]
        if result.raw_response_path:
            lines.append(f"- Raw response: `{result.raw_response_path}`")
        if result.annotation_json_path:
            lines.append(f"- Parsed JSON: `{result.annotation_json_path}`")
        if annotation:
            lines.extend(["", "## Annotation", ""])
            for key in [
                "recommended_action",
                "ambiguity_risk",
                "verifier_adequacy",
                "cua_relevance",
                "implementation_leakage_risk",
                "side_effect_risk",
                "rationale",
            ]:
                if key in annotation:
                    lines.append(f"- `{key}`: {annotation[key]}")
        lines.append("")
        return "\n".join(lines)
