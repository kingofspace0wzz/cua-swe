#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import requests

from provider_client import ProviderTransport


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(value: str, limit: int = 24_000) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return value[:half] + "\n...[output truncated]...\n" + value[-half:]


def _parse_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Qwen occasionally appends one unmatched closing brace to otherwise
        # valid client-side tool arguments. Accept only that narrow defect.
        if text.endswith("}") and text.count("}") == text.count("{") + 1:
            parsed = json.loads(text[:-1])
        else:
            raise
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must decode to an object")
    return parsed


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "toolSpec": {
            "name": name,
            "description": description,
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                }
            },
        }
    }


TOOLS = [
    _tool(
        "shell",
        "Run a shell command in the task workspace to inspect, edit, build, or test source code.",
        {
            "command": {"type": "string"},
            "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 180},
        },
        ["command"],
    ),
    _tool(
        "visual_cua_start",
        "Start the protected screenshot-only browser session and receive its screenshot pixels.",
        {},
        [],
    ),
    _tool(
        "visual_cua_observe",
        "Receive current screenshot pixels from the protected browser session.",
        {},
        [],
    ),
    _tool(
        "visual_cua_act",
        "Perform one coordinate browser action and receive the resulting screenshot pixels.",
        {
            "kind": {
                "type": "string",
                "enum": [
                    "click",
                    "type",
                    "scroll",
                    "drag",
                    "drag_start",
                    "drag_move",
                    "drag_end",
                    "resize",
                    "back",
                    "forward",
                    "wait",
                ],
            },
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text": {"type": "string"},
            "delta_y": {"type": "integer"},
            "end_x": {"type": "integer"},
            "end_y": {"type": "integer"},
            "steps": {"type": "integer", "minimum": 1, "maximum": 100},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        ["kind"],
    ),
    _tool(
        "finish",
        "Finish after implementing and validating the task.",
        {"summary": {"type": "string"}},
        ["summary"],
    ),
]


class QwenChatClient:
    def __init__(self, model: str) -> None:
        self.model = model
        self.transport = ProviderTransport.for_agent("chat-completions", model)
        self.endpoint = self.transport.endpoint

    def create(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": spec["toolSpec"]["name"],
                    "description": spec["toolSpec"]["description"],
                    "parameters": spec["toolSpec"]["inputSchema"]["json"],
                },
            }
            for spec in TOOLS
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
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
                    raise RuntimeError(
                        f"retryable provider HTTP {response.status_code}: {_trim(response.text, 2000)}"
                    )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt == 9:
                    break
                time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"provider Chat Completions request failed: {last_error}")


class QwenCUAAgent:
    def __init__(
        self,
        client: QwenChatClient,
        workspace: Path,
        rollout_dir: Path,
        prompt: str,
        max_turns: int,
    ) -> None:
        self.client = client
        self.workspace = workspace.resolve()
        self.rollout_dir = rollout_dir.resolve()
        self.max_turns = max_turns
        self.launcher = Path(os.environ["CUA_SWE_WEB_CUA_LAUNCHER"]).resolve()
        self.session_file = Path(os.environ["CUA_SWE_WEB_CUA_SESSION"]).resolve()
        self.web_url = os.environ["CUA_SWE_WEB_URL"]
        self.viewport = os.environ["CUA_SWE_WEB_VIEWPORT"]
        try:
            viewport_width, viewport_height = self.viewport.lower().split("x", 1)
            self.viewport_width = int(viewport_width)
            self.viewport_height = int(viewport_height)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "CUA_SWE_WEB_VIEWPORT must have the form WIDTHxHEIGHT"
            ) from exc
        if self.viewport_width <= 0 or self.viewport_height <= 0:
            raise ValueError("CUA_SWE_WEB_VIEWPORT dimensions must be positive")
        self.adapter_dir = self.rollout_dir / "cua-adapter"
        self.visual_started = False
        tool_note = (
            "\n\nFor this native tool-calling runtime, the protected visual_cua MCP operations "
            "named in the policy are exposed as visual_cua_start, visual_cua_observe, "
            "and visual_cua_act. Their successful results contain screenshot pixels only."
        )
        self.messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt + tool_note}
        ]
        self.trajectory_path = self.rollout_dir / "qwen-agent-trajectory.jsonl"
        self.final_path = self.rollout_dir / "qwen_last_message.txt"
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
            message = choices[0].get("message") if choices else None
            if not isinstance(message, dict):
                raise RuntimeError(f"Qwen response lacked an assistant message: {_trim(str(response))}")
            self.log(
                "assistant",
                turn=turn,
                requested_model=self.client.model,
                returned_model=response.get("model"),
                content=message.get("content"),
                tool_calls=message.get("tool_calls") or [],
                stop_reason=choices[0].get("finish_reason"),
                usage=response.get("usage"),
            )
            # Keep the raw provider response in the trajectory above, but only send
            # canonical JSON tool arguments back to the provider. Qwen occasionally emits
            # one unmatched trailing brace; replaying that malformed JSON can make
            # an otherwise valid next request fail with HTTP 400.
            history_message = deepcopy(message)
            tool_uses = history_message.get("tool_calls") or []
            for tool_use in tool_uses:
                function = tool_use.get("function") or {}
                try:
                    parsed_arguments = _parse_tool_arguments(function.get("arguments"))
                except (json.JSONDecodeError, ValueError):
                    parsed_arguments = {}
                function["arguments"] = json.dumps(
                    parsed_arguments, separators=(",", ":"), sort_keys=True
                )
            self.messages.append(history_message)
            if not tool_uses:
                final = str(history_message.get("content") or "").strip()
                self.final_path.write_text(final + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=final, explicit=False)
                return 0

            attached_screenshots: list[Path] = []
            for tool_use in tool_uses:
                function = tool_use.get("function") or {}
                name = str(function.get("name") or "")
                call_id = str(tool_use.get("id") or "")
                try:
                    arguments = _parse_tool_arguments(function.get("arguments"))
                except (json.JSONDecodeError, ValueError):
                    arguments = {}
                try:
                    content, screenshot = self._execute_tool(name, arguments)
                    status = "success"
                except Exception as exc:
                    content = f"{type(exc).__name__}: {exc}"
                    screenshot = None
                    status = "error"
                self.log(
                    "tool",
                    turn=turn,
                    name=name,
                    arguments=arguments,
                    status=status,
                    error=content if status == "error" else None,
                )
                if screenshot is not None:
                    # Match screenshot consumption to the host-owned broker artifact
                    # without exposing its path or any metadata to the model.
                    self.log(
                        "tool",
                        turn=turn,
                        name="view_image",
                        arguments={"path": str(screenshot), "delivery": "converse_image_content"},
                        status="success",
                    )
                    attached_screenshots.append(screenshot)
                    content = "Screenshot pixels are attached in the next user message."
                self.messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": content}
                )
                if name == "finish" and status == "success":
                    summary = str(arguments.get("summary") or "Finished.")
                    self.final_path.write_text(summary + "\n", encoding="utf-8")
                    self.log("finish", turn=turn, summary=summary, explicit=True)
                    return 0
            for screenshot in attached_screenshots:
                encoded = base64.b64encode(screenshot.read_bytes()).decode("ascii")
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded}"},
                            }
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
            if index in image_indexes and index not in keep:
                compacted.append(
                    {"role": "user", "content": "[Older CUA screenshot omitted from context.]"}
                )
            else:
                compacted.append(message)
        return compacted

    def _launcher(self, verb: str, arguments: dict[str, Any]) -> Path:
        arguments = dict(arguments)
        x_pair = arguments.get("x")
        if isinstance(x_pair, (list, tuple)) and len(x_pair) == 2 and "y" not in arguments:
            arguments["x"], arguments["y"] = x_pair
        end_pair = arguments.get("end_x")
        if (
            isinstance(end_pair, (list, tuple))
            and len(end_pair) == 2
            and "end_y" not in arguments
        ):
            arguments["end_x"], arguments["end_y"] = end_pair
        if verb == "act":
            # Qwen3-VL emits coordinates in its documented 0..1000 image space.
            # The protected browser launcher expects viewport pixels.
            for key in ("x", "end_x"):
                if key in arguments and arguments[key] is not None:
                    arguments[key] = self._normalized_coordinate(
                        arguments[key], self.viewport_width
                    )
            for key in ("y", "end_y"):
                if key in arguments and arguments[key] is not None:
                    arguments[key] = self._normalized_coordinate(
                        arguments[key], self.viewport_height
                    )
            if arguments.get("delta_y") is not None:
                delta_y = int(arguments["delta_y"])
                scaled_delta = round(delta_y * self.viewport_height / 1000)
                if delta_y and not scaled_delta:
                    scaled_delta = 1 if delta_y > 0 else -1
                arguments["delta_y"] = scaled_delta
        if verb == "start" and self.visual_started:
            verb = "observe"
        command = [str(self.launcher), verb]
        if verb == "start":
            command.extend(
                [
                    "--url",
                    self.web_url,
                    "--artifacts-dir",
                    str(self.adapter_dir),
                    "--session-file",
                    str(self.session_file),
                    "--viewport",
                    self.viewport,
                    "--observation-mode",
                    "visual",
                ]
            )
        else:
            command.extend(["--session-file", str(self.session_file)])
        if verb == "act":
            command.extend(["--kind", str(arguments.get("kind") or "")])
            option_names = {
                "x": "--x",
                "y": "--y",
                "text": "--text",
                "delta_y": "--delta-y",
                "end_x": "--end-x",
                "end_y": "--end-y",
                "steps": "--steps",
                "width": "--width",
                "height": "--height",
            }
            allowed_fields = {
                "click": {"x", "y"},
                "type": {"text"},
                "scroll": {"x", "y", "delta_y"},
                "drag": {"x", "y", "end_x", "end_y", "steps"},
                "drag_start": {"x", "y"},
                "drag_move": {"x", "y", "steps"},
                "drag_end": {"x", "y", "steps"},
                "resize": {"width", "height"},
                "back": set(),
                "forward": set(),
                "wait": set(),
            }.get(str(arguments.get("kind") or ""), set())
            for key in allowed_fields:
                option = option_names[key]
                if key in arguments and arguments[key] is not None:
                    command.extend([option, str(arguments[key])])
        completed = subprocess.run(
            command,
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"protected visual_cua {verb} failed with exit {completed.returncode}")
        if verb == "start":
            self.visual_started = True
            completed = subprocess.run(
                [
                    str(self.launcher),
                    "observe",
                    "--session-file",
                    str(self.session_file),
                ],
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"protected visual_cua observe failed with exit {completed.returncode}"
                )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("protected visual_cua returned invalid JSON") from exc
        observation = payload.get("observation") if isinstance(payload, dict) else None
        if not isinstance(observation, dict):
            observation = payload
        path = Path(str(observation.get("screenshot_path") or "")).resolve()
        if not path.is_file() or not path.is_relative_to(self.rollout_dir):
            raise RuntimeError("protected visual_cua did not return a valid rollout screenshot")
        return path

    @staticmethod
    def _normalized_coordinate(value: Any, dimension: int) -> int:
        coordinate = round(int(value) * dimension / 1000)
        return min(max(coordinate, 0), dimension - 1)

    def _execute_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[str, Path | None]:
        if name == "shell":
            command = str(arguments.get("command") or "")
            if not command:
                raise ValueError("shell command must not be empty")
            timeout = min(max(int(arguments.get("timeout_sec", 120)), 1), 180)
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
            return _trim(output), None
        if name == "visual_cua_start":
            screenshot = self._launcher("start", arguments)
        elif name == "visual_cua_observe":
            screenshot = self._launcher("observe", arguments)
        elif name == "visual_cua_act":
            screenshot = self._launcher("act", arguments)
        elif name == "finish":
            return "Finished.", None
        else:
            raise ValueError(f"unknown tool: {name}")
        return "Screenshot pixels attached.", screenshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Qwen3 VL as a screenshot-only CUA-SWE agent")
    parser.add_argument("--model", default="qwen3-vl-235b-a22b-instruct")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rollout-dir", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-turns", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent = QwenCUAAgent(
        client=QwenChatClient(args.model),
        workspace=args.workspace,
        rollout_dir=args.rollout_dir,
        prompt=args.prompt,
        max_turns=args.max_turns,
    )
    return agent.run()


if __name__ == "__main__":
    raise SystemExit(main())
