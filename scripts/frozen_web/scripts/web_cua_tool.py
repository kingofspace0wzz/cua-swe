#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import secrets
import subprocess
import sys
import threading
import time
from typing import Any
from urllib import error, request

TOOLS_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOLS_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pydantic import ValidationError


from cua_swe_bench.adapters.base import CLICK_MODIFIERS, GuiAction, GuiObservation  # noqa: E402
from cua_swe_bench.adapters.web import (  # noqa: E402
    MAX_VIEWPORT_HEIGHT,
    MAX_VIEWPORT_WIDTH,
    WebFrontendAdapter,
)


MAX_REQUEST_BODY_BYTES = 16_384
OBSERVATION_MODES = ("structured", "visual")


class RequestBodyTooLarge(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_viewport(value: str | None) -> dict[str, int] | None:
    if not value:
        return None
    normalized = value.lower().replace("×", "x")
    try:
        width_text, height_text = normalized.split("x", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("viewport must be formatted as WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("viewport width and height must be positive")
    if width > MAX_VIEWPORT_WIDTH or height > MAX_VIEWPORT_HEIGHT:
        raise argparse.ArgumentTypeError(
            f"viewport must not exceed {MAX_VIEWPORT_WIDTH}x{MAX_VIEWPORT_HEIGHT}"
        )
    return {"width": width, "height": height}


def _observation_dict(observation: GuiObservation) -> dict[str, Any]:
    return observation.model_dump()


def _public_observation_dict(
    observation: GuiObservation,
    observation_mode: str,
) -> dict[str, Any]:
    if observation_mode == "structured":
        return _observation_dict(observation)
    if observation_mode == "visual":
        return {
            "screenshot_path": str(observation.screenshot_path),
            "observation_mode": "visual",
        }
    raise ValueError(f"unsupported observation mode: {observation_mode}")


def _post(
    session_file: Path,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    session = _read_json(session_file)
    url = f"http://{session['host']}:{session['port']}{endpoint}"
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "content-type": "application/json",
            "x-cua-token": str(session["auth_token"]),
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        try:
            response_payload = json.loads(response_text)
        except json.JSONDecodeError:
            detail = response_text.strip() or exc.reason
        else:
            detail = response_payload.get("error") or response_text
        raise RuntimeError(f"CUA service returned HTTP {exc.code}: {detail}") from exc


def _get(session_file: Path, endpoint: str) -> dict[str, Any]:
    session = _read_json(session_file)
    url = f"http://{session['host']}:{session['port']}{endpoint}"
    req = request.Request(
        url,
        headers={"x-cua-token": str(session["auth_token"])},
        method="GET",
    )
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class CuaServer:
    def __init__(
        self,
        adapter: WebFrontendAdapter,
        artifacts_dir: Path,
        observation_mode: str = "structured",
    ) -> None:
        self.adapter = adapter
        self.artifacts_dir = artifacts_dir
        self.observation_mode = observation_mode
        self.trajectory_path = artifacts_dir / "trajectory.jsonl"

    def log_event(
        self,
        event: str,
        observation: GuiObservation | None = None,
        action: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": _now(),
            "event": event,
        }
        if action is not None:
            record["action"] = action
        if observation is not None:
            record["observation"] = _observation_dict(observation)
        with self.trajectory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _make_handler(state: CuaServer, auth_token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CUASWEWebTool/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_payload(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0") or "0")
            if length > MAX_REQUEST_BODY_BYTES:
                raise RequestBodyTooLarge(
                    f"request body must not exceed {MAX_REQUEST_BODY_BYTES} bytes"
                )
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _write(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle_error(self, status: int, exc: Exception) -> None:
            self._write(status, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        def _authorized(self) -> bool:
            supplied = self.headers.get("x-cua-token", "")
            if not secrets.compare_digest(supplied, auth_token):
                self._write(403, {"ok": False, "error": "forbidden"})
                return False
            return True

        def do_GET(self) -> None:
            if not self._authorized():
                return
            if self.path != "/health":
                self._write(404, {"ok": False, "error": "not found"})
                return
            self._write(200, {"ok": True})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            try:
                if self.path == "/observe":
                    observation = state.adapter.observe()
                    state.log_event("observe", observation=observation)
                    self._write(
                        200,
                        {
                            "ok": True,
                            "observation": _public_observation_dict(
                                observation,
                                state.observation_mode,
                            ),
                        },
                    )
                    return

                if self.path == "/act":
                    payload = self._read_payload()
                    action = GuiAction.model_validate(payload)
                    observation = state.adapter.act(action)
                    state.log_event("act", action=action.model_dump(), observation=observation)
                    self._write(
                        200,
                        {
                            "ok": True,
                            "action": action.model_dump(),
                            "observation": _public_observation_dict(
                                observation,
                                state.observation_mode,
                            ),
                        },
                    )
                    return

                if self.path == "/stop":
                    self._write(200, {"ok": True})

                    def stop_server() -> None:
                        self.server.shutdown()

                    threading.Thread(target=stop_server, daemon=True).start()
                    return

                self._write(404, {"ok": False, "error": "not found"})
            except Exception as exc:
                cancel_active_drag = getattr(state.adapter, "cancel_active_drag", None)
                cancelled = bool(cancel_active_drag()) if callable(cancel_active_drag) else False
                if cancelled:
                    state.log_event(
                        "drag_cancel",
                        action={"request_path": self.path, "reason": f"{type(exc).__name__}: {exc}"},
                    )
                if isinstance(exc, RequestBodyTooLarge):
                    status = 413
                elif isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError)):
                    status = 400
                else:
                    status = 500
                self._handle_error(status, exc)

    return Handler


def _session_file(args: argparse.Namespace) -> Path:
    if args.session_file:
        return Path(args.session_file).resolve()
    return Path(args.artifacts_dir).resolve() / "session.json"


def cmd_start(args: argparse.Namespace) -> int:
    artifacts_dir = Path(args.artifacts_dir).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    session_file = _session_file(args)
    if session_file.exists():
        session_file.unlink()

    stdout_path = artifacts_dir / "server_stdout.txt"
    stderr_path = artifacts_dir / "server_stderr.txt"
    command = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "serve",
        "--url",
        args.url,
        "--artifacts-dir",
        str(artifacts_dir),
        "--session-file",
        str(session_file),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--observation-mode",
        args.observation_mode,
    ]
    if args.viewport:
        command.extend(["--viewport", args.viewport])
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )

    deadline = time.time() + args.timeout
    last_error = "session file was not created"
    while time.time() < deadline:
        if process.poll() is not None:
            last_error = f"server exited with code {process.returncode}"
            break
        if session_file.exists():
            try:
                health = _get(session_file, "/health")
                if health.get("ok") is True:
                    session = _read_json(session_file)
                    public_session = {
                        key: value
                        for key, value in session.items()
                        if key not in {"auth_token", "pid", "host", "port"}
                    }
                    public_session["server_stdout"] = str(stdout_path)
                    public_session["server_stderr"] = str(stderr_path)
                    print(json.dumps(public_session, indent=2, sort_keys=True))
                    return 0
            except (OSError, error.URLError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        time.sleep(0.2)

    if process.poll() is None:
        process.terminate()
    print(f"failed to start CUA web tool: {last_error}", file=sys.stderr)
    if stderr_path.exists():
        print(stderr_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    artifacts_dir = Path(args.artifacts_dir).resolve()
    session_file = Path(args.session_file).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    adapter = WebFrontendAdapter(
        start_url=args.url,
        artifacts_dir=artifacts_dir,
        viewport=_parse_viewport(args.viewport),
    )
    auth_token = secrets.token_urlsafe(48)
    server = HTTPServer(
        (args.host, args.port),
        _make_handler(
            CuaServer(adapter, artifacts_dir, args.observation_mode),
            auth_token,
        ),
    )
    host, port = server.server_address

    try:
        adapter.start(Path.cwd())
        _write_json(
            session_file,
            {
                "pid": os.getpid(),
                "auth_token": auth_token,
                "host": host,
                "port": port,
                "url": args.url,
                "viewport": _parse_viewport(args.viewport) or {"width": 1280, "height": 720},
                "artifacts_dir": str(artifacts_dir),
                "trajectory_path": str(artifacts_dir / "trajectory.jsonl"),
                "observation_mode": args.observation_mode,
            },
        )
        server.serve_forever(poll_interval=0.2)
        return 0
    finally:
        adapter.stop()
        server.server_close()


def cmd_observe(args: argparse.Namespace) -> int:
    result = _post(Path(args.session_file).resolve(), "/observe")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


def cmd_act(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"kind": args.kind}
    for field in [
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
    ]:
        value = getattr(args, field)
        if value is not None:
            payload[field] = value
    modifiers = getattr(args, "modifiers", None)
    if modifiers is not None:
        payload["modifiers"] = modifiers
    result = _post(Path(args.session_file).resolve(), "/act", payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


def cmd_stop(args: argparse.Namespace) -> int:
    session_file = Path(args.session_file).resolve()
    session: dict[str, Any] | None = None
    if session_file.exists():
        session = _read_json(session_file)
    try:
        result = _post(session_file, "/stop", timeout=2)
        print(json.dumps(result, indent=2, sort_keys=True))
    except Exception as exc:
        print(f"stop request failed: {exc}", file=sys.stderr)
        if session and "pid" in session:
            try:
                os.kill(int(session["pid"]), signal.SIGTERM)
            except OSError:
                pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CUA-SWE web adapter CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start a persistent web adapter session")
    start.add_argument("--url", required=True)
    start.add_argument("--artifacts-dir", required=True)
    start.add_argument("--session-file")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=0)
    start.add_argument("--timeout", type=float, default=20.0)
    start.add_argument("--viewport", help="Browser viewport as WIDTHxHEIGHT, for example 390x760")
    start.add_argument(
        "--observation-mode",
        choices=OBSERVATION_MODES,
        default="structured",
    )
    start.set_defaults(func=cmd_start)

    serve = subparsers.add_parser("serve", help=argparse.SUPPRESS)
    serve.add_argument("--url", required=True)
    serve.add_argument("--artifacts-dir", required=True)
    serve.add_argument("--session-file", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--viewport")
    serve.add_argument(
        "--observation-mode",
        choices=OBSERVATION_MODES,
        default="structured",
    )
    serve.set_defaults(func=cmd_serve)

    observe = subparsers.add_parser("observe", help="capture a GUI observation")
    observe.add_argument("--session-file", required=True)
    observe.set_defaults(func=cmd_observe)

    act = subparsers.add_parser("act", help="send a GUI action and observe the result")
    act.add_argument("--session-file", required=True)
    act.add_argument(
        "--kind",
        choices=[
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
        ],
        required=True,
    )
    act.add_argument("--x", type=int)
    act.add_argument("--y", type=int)
    act.add_argument("--end-x", type=int)
    act.add_argument("--end-y", type=int)
    act.add_argument("--delta-x", type=int)
    act.add_argument("--delta-y", type=int)
    act.add_argument("--steps", type=int)
    act.add_argument("--text")
    act.add_argument("--width", type=int)
    act.add_argument("--height", type=int)
    act.add_argument("--duration-ms", type=int)
    act.add_argument(
        "--modifiers",
        nargs="+",
        choices=CLICK_MODIFIERS,
        help="Click only: hold these unique modifier keys for one coordinate click, then release",
    )
    act.set_defaults(func=cmd_act)

    stop = subparsers.add_parser("stop", help="stop a persistent web adapter session")
    stop.add_argument("--session-file", required=True)
    stop.set_defaults(func=cmd_stop)

    return parser


def main() -> int:
    if not sys.flags.isolated:
        raise SystemExit("web_cua_tool.py must run with Python isolated mode (-I)")
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
