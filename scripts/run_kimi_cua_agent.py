#!/usr/bin/env python3
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
        "function": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "view_image",
            "description": (
                "Visually inspect a screenshot produced by the CUA-SWE adapter. "
                "Pass the exact screenshot path returned by observe or act."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish after implementing and validating the task.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
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


class ChatClient:
    def __init__(self, model: str, code_only: bool = False) -> None:
        self.model = model
        self.code_only = code_only
        self.tools = [
            tool for tool in TOOLS if not code_only or tool["function"]["name"] != "view_image"
        ]
        self.transport = ProviderTransport.for_agent("chat-completions", model)
        self.endpoint = self.transport.endpoint

    def create(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": self.tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(10):
            try:
                response = requests.post(
                    self.endpoint,
                    data=body,
                    headers=self.transport.headers(),
                    timeout=300,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"retryable provider HTTP {response.status_code}: {_trim(response.text, 2000)}")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt == 9:
                    break
                time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"provider request failed after retries: {last_error}")


class KimiAgent:
    def __init__(
        self,
        client: ChatClient,
        workspace: Path,
        rollout_dir: Path,
        prompt: str,
        max_turns: int,
    ) -> None:
        self.client = client
        self.workspace = workspace.resolve()
        self.rollout_dir = rollout_dir.resolve()
        self.max_turns = max_turns
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        self.trajectory_path = self.rollout_dir / "kimi-agent-trajectory.jsonl"
        self.final_path = self.rollout_dir / "kimi_last_message.txt"
        self.rollout_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data: Any) -> None:
        record = {"timestamp": _now(), "event": event, **data}
        with self.trajectory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def run(self) -> int:
        self.log("start", model=self.client.model, workspace=str(self.workspace))
        for turn in range(1, self.max_turns + 1):
            response = self.client.create(self._messages_for_request())
            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError(f"Kimi response did not contain choices: {_trim(json.dumps(response), 4000)}")
            message = choices[0].get("message") or {}
            assistant = {
                key: message[key]
                for key in ("role", "content", "tool_calls")
                if key in message and message[key] is not None
            }
            assistant.setdefault("role", "assistant")
            self.messages.append(assistant)
            self.log(
                "assistant",
                turn=turn,
                requested_model=self.client.model,
                returned_model=response.get("model"),
                content=_trim(str(message.get("content") or ""), 8000),
                tool_calls=message.get("tool_calls") or [],
                finish_reason=choices[0].get("finish_reason"),
                usage=response.get("usage"),
            )

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final = str(message.get("content") or "")
                self.final_path.write_text(final + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=final, explicit=False)
                return 0

            attached_images: list[tuple[str, str]] = []
            for call in tool_calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                call_id = str(call.get("id") or f"call-{turn}-{len(self.messages)}")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                    result, image_data = self._execute_tool(name, arguments)
                except Exception as exc:
                    result = f"{type(exc).__name__}: {exc}"
                    image_data = None
                self.messages.append({"role": "tool", "tool_call_id": call_id, "content": _trim(result)})
                self.log("tool", turn=turn, name=name, arguments=arguments, result=_trim(result, 8000))
                if image_data is not None:
                    attached_images.append(image_data)
                if name == "finish" and not result.startswith(("ValueError:", "RuntimeError:")):
                    summary = str(arguments.get("summary") or result)
                    self.final_path.write_text(summary + "\n", encoding="utf-8")
                    self.log("finish", turn=turn, summary=summary, explicit=True)
                    return 0

            for path, data_url in attached_images:
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"CUA screenshot from {path}:"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                )

        self.log("max_turns", max_turns=self.max_turns)
        return 3

    def _messages_for_request(self) -> list[dict[str, Any]]:
        image_indexes = [
            index
            for index, message in enumerate(self.messages)
            if isinstance(message.get("content"), list)
            and any(part.get("type") == "image_url" for part in message["content"])
        ]
        keep = set(image_indexes[-4:])
        compacted: list[dict[str, Any]] = []
        for index, message in enumerate(self.messages):
            if index not in keep and index in image_indexes:
                compacted.append({"role": "user", "content": "[Older CUA screenshot omitted from context.]"})
            else:
                compacted.append(message)
        return compacted

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, tuple[str, str] | None]:
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
                output = "\n".join(
                    [
                        f"exit_code: {completed.returncode}",
                        f"stdout:\n{completed.stdout}",
                        f"stderr:\n{completed.stderr}",
                    ]
                )
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(
                    [
                        "exit_code: 124",
                        f"stdout:\n{exc.stdout or ''}",
                        f"stderr:\n{exc.stderr or ''}",
                        f"command timed out after {timeout} seconds",
                    ]
                )
            return _trim(output), None

        if name == "view_image":
            if self.client.code_only:
                raise ValueError("view_image is unavailable in the code-only condition")
            raw_path = Path(str(arguments.get("path") or "")).expanduser()
            path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
            path = path.resolve()
            allowed = any(path.is_relative_to(root) for root in (self.workspace, self.rollout_dir))
            if not allowed:
                raise ValueError("image path must be inside the workspace or rollout directory")
            if not path.is_file():
                raise ValueError(f"image does not exist: {path}")
            if path.stat().st_size > 3_000_000:
                raise ValueError("image exceeds Kimi's 3 MB image payload limit")
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"Attached screenshot {path}", (str(path), f"data:{mime_type};base64,{encoded}")

        if name == "finish":
            return str(arguments.get("summary") or "Finished."), None

        raise ValueError(f"unknown tool: {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Kimi K2.5 as a CUA-SWE coding agent")
    parser.add_argument("--model", default="kimi-k2.5")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rollout-dir", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--code-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent = KimiAgent(
        client=ChatClient(args.model, code_only=args.code_only),
        workspace=args.workspace,
        rollout_dir=args.rollout_dir,
        prompt=args.prompt,
        max_turns=args.max_turns,
    )
    return agent.run()


if __name__ == "__main__":
    raise SystemExit(main())
