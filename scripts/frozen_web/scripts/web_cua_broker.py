#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
from typing import Any


MAX_REQUEST_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_ACTIVE_SESSIONS = 2
MAX_REQUEST_SECONDS = 5.0
ALLOWED_VERBS = {"start", "observe", "act", "stop"}
TOOL_HELP = """Protected coordinate browser tool
Usage:
  --help
  start --url <task-url> --artifacts-dir <rollout-dir> --session-file <session>
        --viewport <width>x<height> --observation-mode visual|structured
  observe --session-file <session>
  act --session-file <session> --kind <action> [action fields]
  stop --session-file <session>

Action fields:
  click: x, y; optional --modifiers Shift Control Alt Meta (choose one to four)
  type, press: --text <text-or-key/chord>
  key_hold: --text <key/chord>, --duration-ms <1..2000>
  scroll: --x, --y, --delta-x, --delta-y
  drag: --x, --y, --end-x, --end-y; optional --steps
  drag_start: --x, --y
  drag_move, drag_end: --x, --y; optional --steps
  resize: --width, --height
  wait: optional --duration-ms <1..2000>
  back, forward: no action fields

Coordinates use --x <number> --y <number>. For click, --modifiers takes
distinct, case-sensitive key names as separate tokens, for example
--modifiers Shift or --modifiers Shift Control. The keys are held during
that coordinate click and released afterward, including on click errors.
Omit --modifiers for an ordinary click. It is not supported on other actions.
All commands retain the task URL, workspace and rollout path restrictions.
Only the exact top-level --help request displays this documentation.
"""


@dataclass(frozen=True)
class BrokerSession:
    public_artifacts: str
    private_root: Path
    private_session: Path
    private_artifacts: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recv_line(connection: socket.socket) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + MAX_REQUEST_SECONDS
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("CUA broker request timed out")
        connection.settimeout(min(1.0, remaining))
        try:
            chunk = connection.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("request exceeded the broker size limit")
        if data.endswith(b"\n"):
            break
    return bytes(data)


def _within(value: str, root: Path) -> bool:
    candidate = Path(os.path.normpath(value))
    return candidate.is_absolute() and candidate.is_relative_to(root)


def _validate_resize_options(parsed: dict[str, str]) -> None:
    if parsed.get("--kind") != "resize":
        return
    expected = {"--session-file", "--kind", "--width", "--height"}
    if set(parsed) != expected:
        raise ValueError("CUA resize requires only width and height")
    try:
        width = int(parsed["--width"])
        height = int(parsed["--height"])
    except ValueError as exc:
        raise ValueError("CUA resize dimensions must be integers") from exc
    if width <= 0 or height <= 0 or width > 3_840 or height > 2_160:
        raise ValueError("CUA resize dimensions must be within 1x1 and 3840x2160")


def _validate_request(argv: list[str], args: argparse.Namespace) -> str:
    if argv == ["--help"]:
        return "help"
    if not argv or argv[0] not in ALLOWED_VERBS:
        raise ValueError("unsupported CUA broker verb")
    verb = argv[0]
    parsed: dict[str, str] = {}
    index = 1
    while index < len(argv):
        option = argv[index]
        if not option.startswith("--") or option in parsed:
            raise ValueError("invalid or duplicate CUA broker option")
        index += 1
        if option == "--modifiers":
            modifiers: list[str] = []
            while index < len(argv) and not argv[index].startswith("--"):
                modifiers.append(argv[index])
                index += 1
            if (
                not 1 <= len(modifiers) <= 4
                or len(set(modifiers)) != len(modifiers)
                or any(key not in {"Shift", "Control", "Alt", "Meta"} for key in modifiers)
            ):
                raise ValueError("CUA click modifiers must be distinct Shift, Control, Alt or Meta")
            parsed[option] = " ".join(modifiers)
        else:
            if index >= len(argv):
                raise ValueError("CUA broker options must be name/value pairs")
            parsed[option] = argv[index]
            index += 1
    allowed = {
        "start": {"--url", "--artifacts-dir", "--session-file", "--host", "--port", "--timeout", "--viewport", "--observation-mode"},
        "observe": {"--session-file"},
        "act": {
            "--session-file",
            "--kind",
            "--x",
            "--y",
            "--end-x",
            "--end-y",
            "--delta-x",
            "--delta-y",
            "--steps",
            "--text",
            "--width",
            "--height",
            "--duration-ms",
            "--modifiers",
        },
        "stop": {"--session-file"},
    }[verb]
    if not set(parsed).issubset(allowed):
        raise ValueError("CUA broker request contains an unsupported option")
    if "--modifiers" in parsed and parsed.get("--kind") != "click":
        raise ValueError("CUA modifiers are only supported for click")
    if verb == "act":
        _validate_resize_options(parsed)
    session = parsed.get("--session-file")
    if not session or not _within(session, args.rollout_root):
        raise ValueError("CUA broker session path escaped the rollout root")
    if verb == "start":
        if parsed.get("--url") != args.expected_url:
            raise ValueError("CUA broker URL differs from the task URL")
        artifacts = parsed.get("--artifacts-dir")
        if not artifacts or not _within(artifacts, args.rollout_root):
            raise ValueError("CUA broker artifact path escaped the rollout root")
        if parsed.get("--host", "127.0.0.1") != "127.0.0.1":
            raise ValueError("CUA broker host must remain loopback-only")
    return verb


def _append_audit(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _replace_option(argv: list[str], option: str, value: str) -> list[str]:
    rewritten = list(argv)
    index = rewritten.index(option)
    rewritten[index + 1] = value
    return rewritten


def _peer_pid(connection: socket.socket, claimed_pid: Any) -> int:
    if hasattr(socket, "SO_PEERCRED"):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        pid, _uid, _gid = struct.unpack("3i", credentials)
        return pid
    # macOS is used only for local unit tests; protected evaluation is Linux
    # and always uses kernel-authenticated SO_PEERCRED.
    if isinstance(claimed_pid, int) and claimed_pid > 0:
        return claimed_pid
    raise ValueError("peer PID provenance is unavailable")


def _response(
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    files: list[dict[str, str]] | None = None,
) -> bytes:
    payload = {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "files": files or [],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"


def _translated_output(stdout: str, session: BrokerSession) -> tuple[str, list[dict[str, str]]]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.replace(str(session.private_artifacts), session.public_artifacts), []

    attachments: dict[str, dict[str, str]] = {}

    def translate(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {name: translate(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [translate(item, key) for item in value]
        if not isinstance(value, str):
            return value
        candidate = Path(os.path.normpath(value))
        if not candidate.is_absolute() or not candidate.is_relative_to(session.private_artifacts):
            return value.replace(str(session.private_artifacts), session.public_artifacts)
        relative = candidate.relative_to(session.private_artifacts)
        public_path = str(Path(session.public_artifacts) / relative)
        if key == "screenshot_path":
            metadata = candidate.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("broker screenshot is not a regular file")
            data = candidate.read_bytes()
            attachments[public_path] = {
                "path": public_path,
                "data_base64": base64.b64encode(data).decode("ascii"),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        return public_path

    translated = translate(payload)
    return json.dumps(translated, indent=2, sort_keys=True) + "\n", list(attachments.values())


def _terminate_session(session_file: Path, *, grace_seconds: float = 1.0) -> None:
    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def serve(args: argparse.Namespace) -> int:
    socket_path = Path(args.socket)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    audit_path = Path(args.audit_log)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch(exist_ok=True)
    os.chmod(audit_path, 0o600)
    environment = {
        "HOME": args.home,
        "XDG_CACHE_HOME": args.cache_home,
        "PLAYWRIGHT_BROWSERS_PATH": args.playwright_browsers,
        "PATH": "/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "LANG": "C.UTF-8",
        "TMPDIR": "/tmp",
    }
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(16)
    stopping = False
    state_root = Path(args.state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    if not stat.S_ISDIR(state_root.lstat().st_mode):
        raise RuntimeError("CUA broker state root is not a directory")
    os.chmod(state_root, 0o700)
    sessions: dict[str, BrokerSession] = {}
    active_process: subprocess.Popen[str] | None = None
    active_connection: socket.socket | None = None

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping, active_process, active_connection
        stopping = True
        if active_process is not None and active_process.poll() is None:
            try:
                os.killpg(active_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if active_connection is not None:
            try:
                active_connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            active_connection.close()
        server.close()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    sequence = 0
    try:
        while not stopping:
            try:
                connection, _ = server.accept()
            except OSError:
                if stopping:
                    break
                raise
            active_connection = connection
            with connection:
                sequence += 1
                peer_pid = -1
                started = _now()
                argv: list[str] = []
                verb = "invalid"
                files: list[dict[str, str]] = []
                try:
                    request = json.loads(_recv_line(connection).decode("utf-8"))
                    peer_pid = _peer_pid(connection, request.get("pid"))
                    if request.get("shutdown") is True and hmac.compare_digest(
                        str(request.get("admin_token") or ""),
                        args.admin_token,
                    ):
                        stopping = True
                        connection.sendall(_response(0, "broker shutdown accepted\n"))
                        active_connection = None
                        continue
                    if not hmac.compare_digest(
                        str(request.get("token") or ""),
                        args.token,
                    ):
                        raise ValueError("invalid CUA broker capability")
                    argv = request.get("argv")
                    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
                        raise ValueError("invalid CUA broker argv")
                    verb = _validate_request(argv, args)
                    cwd = str(request.get("cwd") or "")
                    if not _within(cwd, args.workspace):
                        raise ValueError("CUA broker cwd escaped the task workspace")
                    if verb == "help":
                        stdout, stderr, exit_code = TOOL_HELP, "", 0
                    else:
                        public_session = argv[argv.index("--session-file") + 1]
                        if verb == "start":
                            if public_session in sessions:
                                raise ValueError("CUA broker session is already active")
                            if len(sessions) >= MAX_ACTIVE_SESSIONS:
                                raise ValueError(
                                    f"CUA broker permits at most {MAX_ACTIVE_SESSIONS} active browser sessions"
                                )
                            session_root = state_root / (
                                hashlib.sha256(public_session.encode()).hexdigest()
                                + f"-{sequence:06d}"
                            )
                            session_root.mkdir(mode=0o700, exist_ok=False)
                            session = BrokerSession(
                                public_artifacts=argv[argv.index("--artifacts-dir") + 1],
                                private_root=session_root,
                                private_session=session_root / "session.json",
                                private_artifacts=session_root / "artifacts",
                            )
                        else:
                            session = sessions.get(public_session)
                            if session is None:
                                raise ValueError("CUA broker session was not started by this broker")
                        tool_argv = _replace_option(
                            argv,
                            "--session-file",
                            str(session.private_session),
                        )
                        if verb == "start":
                            tool_argv = _replace_option(
                                tool_argv,
                                "--artifacts-dir",
                                str(session.private_artifacts),
                            )
                        active_process = subprocess.Popen(
                            [args.python, "-I", args.tool, *tool_argv],
                            cwd=args.workspace,
                            env=environment,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            start_new_session=True,
                        )
                        try:
                            completed_stdout, completed_stderr = active_process.communicate(
                                timeout=args.command_timeout
                            )
                        except subprocess.TimeoutExpired:
                            os.killpg(active_process.pid, signal.SIGKILL)
                            completed_stdout, completed_stderr = active_process.communicate(timeout=5)
                            raise TimeoutError("CUA broker tool command timed out")
                        exit_code = active_process.returncode
                        active_process = None
                        stdout = completed_stdout[:MAX_OUTPUT_BYTES]
                        stderr = completed_stderr[:MAX_OUTPUT_BYTES]
                        stdout, files = _translated_output(stdout, session)
                        stdout = stdout.replace(str(session.private_session), public_session)
                        stderr = stderr.replace(str(session.private_root), "<broker-state>")
                        if exit_code == 0 and verb == "start":
                            sessions[public_session] = session
                        elif exit_code == 0 and verb == "stop":
                            sessions.pop(public_session, None)
                except Exception as exc:
                    if active_process is not None and active_process.poll() is None:
                        try:
                            os.killpg(active_process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        active_process.wait(timeout=5)
                    active_process = None
                    stdout = ""
                    stderr = f"CUA broker rejected request: {type(exc).__name__}: {exc}\n"
                    exit_code = 126
                record = {
                    "sequence": sequence,
                    "started_at": started,
                    "finished_at": _now(),
                    "peer_pid": peer_pid,
                    "verb": verb,
                    "argv": argv,
                    "exit_code": exit_code,
                    "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                    "files": [
                        {"path": item["path"], "sha256": item["sha256"]}
                        for item in files
                    ],
                }
                _append_audit(Path(args.audit_log), record)
                try:
                    connection.sendall(_response(exit_code, stdout, stderr, files))
                except OSError:
                    pass
            active_connection = None
    finally:
        private_sessions = {
            *(session.private_session for session in sessions.values()),
            *state_root.glob("*/session.json"),
        }
        for private_session in private_sessions:
            try:
                subprocess.run(
                    [
                        args.python,
                        "-I",
                        args.tool,
                        "stop",
                        "--session-file",
                        str(private_session),
                    ],
                    cwd=args.workspace,
                    env=environment,
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                pass
            _terminate_session(private_session)
        server.close()
        socket_path.unlink(missing_ok=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Host-owned CUA broker")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--admin-token", required=True)
    parser.add_argument("--audit-log", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--expected-url", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--cache-home", required=True)
    parser.add_argument("--playwright-browsers", required=True)
    parser.add_argument("--command-timeout", type=float, default=90.0)
    return parser


if __name__ == "__main__":
    raise SystemExit(serve(build_parser().parse_args()))
