#!/usr/bin/env python3
"""Minimal stdio MCP bridge that returns protected CUA screenshots as image content."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import Any


PROTOCOL_VERSION = "2025-06-18"
ACTION_FIELDS = (
    "x",
    "y",
    "end_x",
    "end_y",
    "delta_x",
    "delta_y",
    "steps",
    "text",
    "width",
    "height",
    "duration_ms",
)
ACTION_KINDS = (
    "click",
    "type",
    "press",
    "key_hold",
    "scroll",
    "drag",
    "drag_start",
    "drag_move",
    "drag_end",
    "back",
    "forward",
    "resize",
    "wait",
)
ACTION_FIELDS_BY_KIND = {
    "click": {"x", "y"},
    "type": {"text"},
    "press": {"text"},
    "key_hold": {"text", "duration_ms"},
    "scroll": {"x", "y", "delta_x", "delta_y"},
    "drag": {"x", "y", "end_x", "end_y", "steps"},
    "drag_start": {"x", "y"},
    "drag_move": {"x", "y", "steps"},
    "drag_end": {"x", "y", "steps"},
    "back": set(),
    "forward": set(),
    "resize": {"width", "height"},
    "wait": {"duration_ms"},
}


class VisualCuaMcp:
    def __init__(self) -> None:
        self.launcher = Path(os.environ["CUA_SWE_WEB_CUA_LAUNCHER"])
        self.session = Path(os.environ["CUA_SWE_WEB_CUA_SESSION"])
        self.rollout = Path(os.environ["CUA_SWE_AGENT_ROLLOUT_DIR"])
        self.artifacts = self.rollout / "cua-adapter"
        self.url = os.environ["CUA_SWE_WEB_URL"]
        self.viewport = os.environ["CUA_SWE_WEB_VIEWPORT"]
        self.trajectory = self.rollout / "visual-mcp-trajectory.jsonl"
        self.started = False

    def log(self, name: str, arguments: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "tool",
            "name": name,
            "arguments": arguments,
        }
        with self.trajectory.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def command(self, *arguments: str) -> dict[str, Any]:
        completed = subprocess.run(
            [str(self.launcher), *arguments],
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return json.loads(completed.stdout)

    def start(self) -> dict[str, Any]:
        if not self.started:
            self.command(
                "start",
                "--url",
                self.url,
                "--artifacts-dir",
                str(self.artifacts),
                "--session-file",
                str(self.session),
                "--viewport",
                self.viewport,
                "--observation-mode",
                "visual",
            )
            self.started = True
        return self.command("observe", "--session-file", str(self.session))

    def observe(self) -> dict[str, Any]:
        if not self.started:
            return self.start()
        return self.command("observe", "--session-file", str(self.session))

    def act(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.started:
            self.start()
        kind = str(arguments["kind"])
        if kind not in ACTION_FIELDS_BY_KIND:
            raise ValueError(f"unknown action kind: {kind}")
        argv = [
            "act",
            "--session-file",
            str(self.session),
            "--kind",
            kind,
        ]
        # The MCP schema must describe every action variant in one object. Some
        # clients consequently send irrelevant optional fields (notably
        # ``steps`` on scroll/wait). Normalize those fields at this boundary so
        # a schema-valid tool call cannot be rejected by GuiAction downstream.
        for field in ACTION_FIELDS_BY_KIND[kind]:
            if field in arguments and arguments[field] is not None:
                argv.extend(["--" + field.replace("_", "-"), str(arguments[field])])
        return self.command(*argv)

    def stop(self) -> None:
        if not self.started:
            return
        try:
            self.command("stop", "--session-file", str(self.session))
        except Exception:
            pass
        self.started = False

    def image_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        observation = payload.get("observation") or {}
        allowed = {"screenshot_path", "observation_mode"}
        if set(observation) != allowed or observation.get("observation_mode") != "visual":
            raise RuntimeError("protected adapter returned a non-visual observation")
        path = Path(str(observation["screenshot_path"])).resolve()
        if not path.is_file() or not path.is_relative_to(self.rollout.resolve()):
            raise RuntimeError("protected screenshot is outside the rollout directory")
        data = path.read_bytes()
        if len(data) > 5_000_000:
            raise RuntimeError("protected screenshot exceeds the MCP image limit")
        self.log("view_image", {"path": str(path), "delivery": "mcp_image_content"})
        return {
            "content": [
                {"type": "text", "text": "Protected screenshot attached."},
                {
                    "type": "image",
                    "data": base64.b64encode(data).decode("ascii"),
                    "mimeType": mimetypes.guess_type(path.name)[0] or "image/png",
                },
            ],
            "isError": False,
        }

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "start",
                "description": "Start the protected browser and return its screenshot pixels.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "observe",
                "description": "Capture and return the current protected browser screenshot pixels.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "act",
                "description": (
                    "Perform one coordinate browser action and return the new screenshot pixels. "
                    "Use press with text such as Shift+Enter or Alt+R for a keyboard key/chord. "
                    "Use key_hold with one or two '+'-separated keys and duration_ms for gameplay. "
                    "Action fields are kind-specific: scroll uses x, y, delta_x, delta_y; "
                    "steps applies only to drag, drag_move, and drag_end."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(ACTION_KINDS)},
                        **{
                            field: ({"type": "string"} if field == "text" else {"type": "integer"})
                            for field in ACTION_FIELDS
                        },
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            },
        ]

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        identifier = request.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cua-swe-visual", "version": "1.0.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.tools()}
        elif method == "tools/call":
            params = request.get("params") or {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if name == "start":
                result = self.image_result(self.start())
            elif name == "observe":
                result = self.image_result(self.observe())
            elif name == "act":
                result = self.image_result(self.act(arguments))
            else:
                raise ValueError(f"unknown tool: {name}")
        else:
            raise ValueError(f"unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": identifier, "result": result}


def main() -> int:
    server = VisualCuaMcp()

    def stop(_signum: int, _frame: Any) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    for line in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            response = server.dispatch(request)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"},
            }
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    # The host-owned broker is the sole lifecycle authority. It closes every
    # private browser session after the audited agent process has exited.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
