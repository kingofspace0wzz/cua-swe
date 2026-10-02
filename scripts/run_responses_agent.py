#!/usr/bin/env python3
"""Run an OpenAI-compatible coding agent through the Responses API."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import mimetypes
from pathlib import Path
import subprocess
import time
from typing import Any

import requests

from provider_client import ProviderTransport


TOOLS = [
    {
        "type": "function",
        "name": "shell",
        "description": (
            "Run a shell command in the task workspace. Use the CUA-SWE adapter "
            "CLI described in the prompt for every browser observation/action."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 180},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "view_image",
        "description": "Visually inspect a screenshot produced by the CUA-SWE adapter.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "finish",
        "description": "Finish after implementing and validating the task.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(value: str, limit: int = 24_000) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return value[:half] + "\n...[output truncated]...\n" + value[-half:]


class ResponsesClient:
    def __init__(
        self,
        model: str,
        *,
        code_only: bool = False,
        request_timeout_seconds: int = 600,
        request_attempts: int = 10,
        max_output_tokens: int = 16_384,
    ) -> None:
        self.model = model
        self.code_only = code_only
        self.request_timeout_seconds = request_timeout_seconds
        self.request_attempts = request_attempts
        self.max_output_tokens = max_output_tokens
        self.tools = [
            tool for tool in TOOLS if not code_only or tool["name"] != "view_image"
        ]
        self.transport = ProviderTransport.for_agent("responses", model)
        self.endpoint = self.transport.endpoint

    def create(
        self,
        input_items: list[dict[str, Any]],
        *,
        previous_response_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "tools": self.tools,
            "tool_choice": "auto",
            "max_output_tokens": self.max_output_tokens,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        body = json.dumps(payload, separators=(",", ":")).encode()
        last_error: Exception | None = None
        for attempt in range(self.request_attempts):
            try:
                response = requests.post(
                    self.endpoint,
                    data=body,
                    headers=self.transport.headers(),
                    timeout=self.request_timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise RuntimeError(
                        f"retryable provider HTTP {response.status_code}: "
                        f"{_trim(response.text, 2000)}"
                    )
                response.raise_for_status()
                decoded = response.json()
                if not isinstance(decoded, dict):
                    raise RuntimeError("provider response is not a JSON object")
                return decoded
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.request_attempts:
                    time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"provider request failed after retries: {last_error}")


class ResponsesAgent:
    def __init__(
        self,
        client: ResponsesClient,
        workspace: Path,
        rollout_dir: Path,
        prompt: str,
        max_turns: int,
    ) -> None:
        self.client = client
        self.workspace = workspace.resolve()
        self.rollout_dir = rollout_dir.resolve()
        self.prompt = prompt
        self.max_turns = max_turns
        self.trajectory_path = self.rollout_dir / "responses-agent-trajectory.jsonl"
        self.final_path = self.rollout_dir / "responses_last_message.txt"
        self.rollout_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data: Any) -> None:
        record = {"timestamp": _now(), "event": event, **data}
        with self.trajectory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def run(self) -> int:
        self.log("start", requested_model=self.client.model, workspace=str(self.workspace))
        previous_response_id: str | None = None
        input_items: list[dict[str, Any]] = [
            {"role": "user", "content": [{"type": "input_text", "text": self.prompt}]}
        ]
        for turn in range(1, self.max_turns + 1):
            response = self.client.create(
                input_items, previous_response_id=previous_response_id
            )
            response_id = str(response.get("id") or "")
            if not response_id:
                raise RuntimeError("Responses API reply is missing an id")
            previous_response_id = response_id
            output = response.get("output") or []
            if not isinstance(output, list):
                raise RuntimeError("Responses API output is not a list")
            calls = [item for item in output if item.get("type") == "function_call"]
            text = self._output_text(response, output)
            self.log(
                "assistant",
                turn=turn,
                response_id=response_id,
                requested_model=self.client.model,
                returned_model=response.get("model"),
                status=response.get("status"),
                incomplete_details=response.get("incomplete_details"),
                usage=response.get("usage"),
                content=_trim(text, 8000),
                tool_calls=calls,
            )
            if not calls:
                if response.get("status") == "incomplete":
                    input_items = [{
                        "role": "user",
                        "content": [{
                            "type": "input_text",
                            "text": "Continue working. Use tools as needed and finish the task.",
                        }],
                    }]
                    continue
                self.final_path.write_text(text + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=text, explicit=False)
                return 0

            next_input: list[dict[str, Any]] = []
            finish_summary: str | None = None
            for index, call in enumerate(calls):
                name = str(call.get("name") or "")
                call_id = str(call.get("call_id") or call.get("id") or "")
                if not call_id:
                    raise RuntimeError("Responses function call is missing call_id")
                try:
                    arguments = json.loads(str(call.get("arguments") or "{}"))
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must decode to an object")
                    result, image = self._execute_tool(name, arguments)
                    is_error = False
                except Exception as exc:
                    arguments = {}
                    result = f"{type(exc).__name__}: {exc}"
                    image = None
                    is_error = True
                next_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _trim(result),
                })
                self.log(
                    "tool",
                    turn=turn,
                    index=index,
                    name=name,
                    arguments=arguments,
                    result=_trim(result, 8000),
                    is_error=is_error,
                )
                if image is not None:
                    path, data_url = image
                    next_input.append({
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": f"CUA screenshot from {path}:"},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    })
                if name == "finish" and not is_error:
                    finish_summary = str(arguments.get("summary") or result)
            if finish_summary is not None:
                self.final_path.write_text(finish_summary + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=finish_summary, explicit=True)
                return 0
            input_items = next_input
        self.log("max_turns", max_turns=self.max_turns)
        return 3

    @staticmethod
    def _output_text(response: dict[str, Any], output: list[dict[str, Any]]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct.strip()
        chunks: list[str] = []
        for item in output:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") in {"output_text", "text"}:
                    chunks.append(str(part.get("text") or ""))
        return "\n".join(chunks).strip()

    def _execute_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[str, tuple[str, str] | None]:
        if name == "shell":
            command = str(arguments.get("command") or "")
            if not command:
                raise ValueError("shell command must not be empty")
            timeout = min(max(int(arguments.get("timeout_sec", 120)), 1), 180)
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.workspace,
                    shell=True,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
                output = (
                    f"exit_code: {completed.returncode}\n"
                    f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                )
            except subprocess.TimeoutExpired as exc:
                output = (
                    f"exit_code: 124\nstdout:\n{exc.stdout or ''}\n"
                    f"stderr:\n{exc.stderr or ''}\n"
                    f"command timed out after {timeout} seconds"
                )
            return _trim(output), None
        if name == "view_image":
            if self.client.code_only:
                raise ValueError("view_image is unavailable in code-only")
            raw_path = Path(str(arguments.get("path") or "")).expanduser()
            path = (raw_path if raw_path.is_absolute() else self.workspace / raw_path).resolve()
            if not any(path.is_relative_to(root) for root in (self.workspace, self.rollout_dir)):
                raise ValueError("image path must be inside workspace or rollout")
            if not path.is_file() or path.stat().st_size > 5_000_000:
                raise ValueError(f"invalid image: {path}")
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode()
            return f"Attached screenshot {path}", (str(path), f"data:{mime};base64,{encoded}")
        if name == "finish":
            return str(arguments.get("summary") or "Finished."), None
        raise ValueError(f"unknown tool: {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rollout-dir", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--request-timeout-seconds", type=int, default=600)
    parser.add_argument("--request-attempts", type=int, default=10)
    parser.add_argument("--max-output-tokens", type=int, default=16_384)
    parser.add_argument("--code-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return ResponsesAgent(
        ResponsesClient(
            args.model,
            code_only=args.code_only,
            request_timeout_seconds=args.request_timeout_seconds,
            request_attempts=args.request_attempts,
            max_output_tokens=args.max_output_tokens,
        ),
        args.workspace,
        args.rollout_dir,
        args.prompt,
        args.max_turns,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
