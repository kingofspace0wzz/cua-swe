#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cua_swe_bench.commands import (  # noqa: E402
    CommandResult,
    RunningCommand,
    run_command,
    start_command,
)
from cua_swe_bench.recorder import ResultRecorder  # noqa: E402
from cua_swe_bench.results import RunResult, VerifierReport, VerifierResult  # noqa: E402
from cua_swe_bench.schema import TaskBundle  # noqa: E402
from cua_swe_bench.web_frontend_workflow import (  # noqa: E402
    LUNA_MODEL_ID,
    assess_luna_comparison,
)
from cua_swe_bench.workspace import Workspace  # noqa: E402
from run_model_matrix import (  # noqa: E402
    MODELS,
    TASK_NAMES,
    PROVIDER_LEASE_ENV_NAMES,
    ModelSpec,
    _command_dict,
    _provider_lease,
    _rate,
    _require_provider_route,
    provider_secret_env_names,
    run_agent_command,
)


CONDITIONS = ("cua", "code-only")
ADAPTER_SYSTEM_EXECUTABLES = (Path("/usr/bin/nvidia-modprobe"),)
DYNAMIC_LOADER_NAMES = {"ld.so", "ld64.so.1"}
TASK_RUNTIME_PATH = "/usr/bin:/bin:/usr/local/bin"
SOURCE_GIT_TIMEOUT_SEC = 180
SENSITIVE_ENV_NAMES = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GIT_ASKPASS",
    "SSH_AUTH_SOCK",
    "NETRC",
    "NPM_TOKEN",
    "NODE_AUTH_TOKEN",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "NODE_OPTIONS",
    "BROWSER",
    "CHROME_BIN",
    "CHROME_PATH",
    "PUPPETEER_EXECUTABLE_PATH",
    "PLAYWRIGHT_NODEJS_PATH",
    "ELECTRON_RUN_AS_NODE",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "KIMI_API_KEY",
    "PLAYWRIGHT_BROWSERS_PATH",
)
# Credential-shaped variables are matched by name, so no individual service needs listing.
CREDENTIAL_ENV_NAME = re.compile(
    r"[A-Za-z0-9_]*_(?:TOKEN|SECRET|SECRET_KEY|ACCESS_KEY|ACCESS_KEY_ID|PASSWORD|CREDENTIALS|CREDENTIALS_FILE)",
    re.IGNORECASE,
)


def sensitive_env_names() -> tuple[str, ...]:
    """Fixed sensitive names plus credential-shaped names in the controller environment."""
    lease = set(PROVIDER_LEASE_ENV_NAMES)
    found = sorted(
        name for name in os.environ if name not in lease and CREDENTIAL_ENV_NAME.fullmatch(name)
    )
    return (*SENSITIVE_ENV_NAMES, *found)


ISOLATED_TOOL_FILES = (
    "render_web_agent_prompt.py",
    "run_web_cua_agent.sh",
    "run_code_only_agent.sh",
    "run_anthropic_cua_agent.py",
    "run_responses_agent.py",
    "provider_client.py",
    "run_kimi_cua_agent.py",
    "run_qwen_cua_agent.py",
    "run_storybook_resize_capability.py",
    "web_cua_broker.py",
    "web_cua_client.py",
    "web_cua_launcher.S",
    "web_cua_mcp.py",
    "web_cua_tool.py",
)
SOURCE_EXCLUDES = {
    ".git",
    "node_modules",
    "dist",
    ".next",
    "verifiers",
    "verifier-artifacts",
    "gold.patch",
    "negative.patch",
    "replay.md",
    "task.yaml",
}
PROTECTED_MATERIAL_NAMES = {
    "verifiers",
    "verifier-artifacts",
    "gold.patch",
    "negative.patch",
    "replay.md",
    "task.yaml",
}

BROWSER_EXECUTABLE_NAMES = {
    "chrome",
    "chrome-headless-shell",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "playwright",
    "puppeteer",
    "selenium",
}
BROWSER_INVOCATION = re.compile(
    r"(?i)(?:web_cua_tool|playwright|puppeteer|selenium|chromium|google-chrome"
    r"|browser[_ -]devtools)"
)
LOOPBACK_URL = re.compile(
    r"(?i)(?:https?://(?:127\.0\.0\.1|localhost|\[?::1\]?)(?::|/)|\$CUA_SWE_WEB_URL)"
)
SHELL_CODEX_NESTED = re.compile(
    r"(?is)(?:^|(?:&&|\|\||[;|\n])\s*)"
    r"(?:exec\s+)?(?:command\s+)?(?:env\s+)?"
    r"(?:[\"']?[^\s;&|\n]+/)?codex(?:\.js)?[\"']?\s+"
    r"(?:(?!(?:&&|\|\||[;|\n])).)*?\bexec\b"
)
SHELL_CLAUDE_NESTED = re.compile(
    r"(?is)(?:^|(?:&&|\|\||[;|\n])\s*)"
    r"(?:exec\s+)?(?:command\s+)?(?:env\s+)?"
    r"(?:[\"']?[^\s;&|\n]+/)?claude[\"']?\s+"
    r"(?:(?!(?:&&|\|\||[;|\n])).)*?(?:--print|-p)(?:\s|$)"
)
EXTERNAL_NETWORK_COMMAND = re.compile(
    r"(?i)(?:"
    r"\b(?:curl|wget)\b[^\n]*https?://(?!(?:127\.0\.0\.1|localhost|\[?::1\]?)(?::|/))|"
    r"\bgit\s+(?:clone|fetch|pull|ls-remote|submodule\s+update)\b|"
    r"\b(?:gh|ssh|scp|sftp)\b|"
    r"\bcodex\b[^\n]*\s--search\b|"
    r"\b(?:npm|pnpm|yarn)\s+(?:install|add|update|upgrade)\b|"
    r"\b(?:pip|pip3|uv\s+pip|python\d*(?:\.\d+)?\s+-m\s+pip)\s+"
    r"(?:install|download)\b"
    r")"
)
HIDDEN_PATH_NAME = re.compile(
    r"(?i)(?:verifiers?/|gold\.patch|negative\.patch|replay\.md|task\.yaml"
    r"|/tasks/web/)"
)
BLOCKED_REPO_ATTEMPT = re.compile(
    rf"(?i)(?:{re.escape(str(REPO_ROOT.resolve()))}|/tasks/web/)"
)
PROVIDER_INFRASTRUCTURE_ERROR = re.compile(
    r"(?i)(?:"
    r"invalid[_ ]api[_ ]key|incorrect api key|authentication_error|"
    r"unexpected status 401 unauthorized|"
    r"unexpected status 429|too many requests|throttl(?:ed|ing)|rate_limit_error|"
    r"retryable provider http 5(?:00|02|03|04)|"
    r"service[_ ]?unavailable|overloaded_error|model[_ ]?timeout|"
    r"failed to connect to (?:https?://)?api\.(?:openai|anthropic)\.com"
    r")"
)
TASK_DIGEST_EXCLUDES = {
    ".git",
    "node_modules",
    "dist",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "verifier-artifacts",
}
PRE_AGENT_SOURCE_EXCLUDES = frozenset(
    {
        *TASK_DIGEST_EXCLUDES,
        ".cache",
        ".nx",
        ".turbo",
        ".vite",
        "coverage",
    }
)
HARNESS_FILES = (
    "scripts/run_game_clean_ablation.py",
    "scripts/run_model_matrix.py",
    *(f"scripts/{name}" for name in ISOLATED_TOOL_FILES),
)


@dataclass(frozen=True)
class TaskInput:
    task_file: Path
    task_id: str
    task_name: str
    digest: str


@dataclass(frozen=True)
class CleanTrial:
    ordinal: int
    task_file: Path
    task_id: str
    task_name: str
    task_digest: str
    model: ModelSpec
    attempt: int
    condition: str
    port: int
    observation_mode: str = "structured"

    @property
    def key(self) -> str:
        return f"{self.condition}/{self.model.key}/{self.task_id}/attempt-{self.attempt}"


@dataclass(frozen=True)
class ProtectedRuntimeContract:
    source_path: Path
    service_command: str
    service_health_path: str
    application_command: str


@dataclass
class ProtectedServiceHandle:
    process: RunningCommand
    staged_root: Path
    port: int
    health_url: str


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved)


def _reject_symlink_tree(root: Path, context: str) -> None:
    candidate = Path(root.anchor) if root.is_absolute() else Path.cwd()
    parts = root.parts[1:] if root.is_absolute() else root.parts
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"{context} contains a symlink path component: {candidate}")
    if root.exists():
        symlinks = [path for path in root.rglob("*") if path.is_symlink()]
        if symlinks:
            raise ValueError(f"{context} contains symlinks: {symlinks[:5]}")


def _load_task_file(path: Path) -> TaskBundle:
    return TaskBundle.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _load_protected_runtime_contract(task_file: Path) -> ProtectedRuntimeContract | None:
    path = task_file.resolve().parent / "runtime-contract.yaml"
    if not path.is_file():
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("visibility") != "evaluator_owned":
        raise ValueError("runtime contract must be evaluator_owned")
    service = payload.get("service")
    application = payload.get("application")
    if not isinstance(service, dict) or not isinstance(application, dict):
        raise ValueError("runtime contract requires service and application mappings")
    service_command = str(service.get("command") or "").strip()
    application_command = str(application.get("command") or "").strip()
    health_path = str(service.get("health_path") or "").strip()
    if "{service_port}" not in service_command:
        raise ValueError("protected service command must contain {service_port}")
    if "{service_port}" not in application_command or "{app_port}" not in application_command:
        raise ValueError("protected application command must contain {service_port} and {app_port}")
    if not health_path.startswith("/") or "{" in health_path or "}" in health_path:
        raise ValueError("protected service health_path must be a literal absolute path")
    return ProtectedRuntimeContract(
        source_path=path,
        service_command=service_command,
        service_health_path=health_path,
        application_command=application_command,
    )


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _declared_web_viewport(task: TaskBundle) -> str:
    value = task.environment.viewport_or_device
    matches = re.findall(r"(?<![0-9])([1-9][0-9]{0,3})x([1-9][0-9]{0,3})(?![0-9])", value)
    if len(matches) != 1:
        raise ValueError(f"web task has no unambiguous declared viewport: {value!r}")
    width, height = (int(part) for part in matches[0])
    if width > 3840 or height > 2160:
        raise ValueError(f"web task viewport exceeds adapter bounds: {value!r}")
    return f"{width}x{height}"


def _declared_web_start_url(task: TaskBundle, port: int) -> str:
    value = _replace_runtime_port(str(task.environment.start_url), port)
    expected_origin = f"http://127.0.0.1:{port}"
    if value != expected_origin and not value.startswith(f"{expected_origin}/"):
        raise ValueError(
            "web task start_url must use the isolated loopback origin: "
            f"{task.environment.start_url!r}"
        )
    return value


def _task_input_digest(task_file: Path) -> str:
    task_root = task_file.resolve().parent
    return _tree_digest(task_root, excludes=TASK_DIGEST_EXCLUDES)


def _task_input(task_file: Path) -> TaskInput:
    resolved = task_file.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"task file does not exist: {resolved}")
    task = _load_task_file(resolved)
    if task.track != "web_frontend":
        raise ValueError(f"clean browser comparison requires a web task: {task.id}")
    return TaskInput(
        task_file=resolved,
        task_id=task.id,
        task_name=task.id.removeprefix("web."),
        digest=_task_input_digest(resolved),
    )


@lru_cache(maxsize=1)
def _evaluation_harness_digest() -> str:
    digest = hashlib.sha256()
    files = [REPO_ROOT / relative for relative in HARNESS_FILES]
    files.extend(
        path
        for path in (REPO_ROOT / "src" / "cua_swe_bench").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    for path in sorted(files, key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _version_record(command: str, *args: str) -> dict[str, Any]:
    executable = shutil.which(command)
    if not executable:
        return {"available": False, "path": None, "version": None}
    result = subprocess.run(
        [executable, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return {
        "available": result.returncode == 0,
        "path": str(Path(executable).resolve()),
        "version": output[0] if output else None,
    }


@lru_cache(maxsize=8)
def _runtime_provenance(python_bin_text: str) -> dict[str, Any]:
    python_bin = str(Path(python_bin_text).expanduser().absolute())
    python_result = subprocess.run(
        [python_bin, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    playwright_result = subprocess.run(
        [
            python_bin,
            "-c",
            "import importlib.metadata as m; print(m.version('playwright'))",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    chrome = next(
        (
            _version_record(name, "--version")
            for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
            if shutil.which(name)
        ),
        {"available": False, "path": None, "version": None},
    )
    playwright_root = Path(
        os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH",
            str(Path.home() / ".cache" / "ms-playwright"),
        )
    ).expanduser()
    playwright_executables = sorted(
        path
        for path in playwright_root.glob(
            "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
        if path.is_file()
    )
    playwright_browser_version = None
    if playwright_executables:
        browser_result = subprocess.run(
            [str(playwright_executables[-1]), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        playwright_browser_version = (
            browser_result.stdout or browser_result.stderr
        ).strip()
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "available": python_result.returncode == 0,
            "path": python_bin,
            "version": (python_result.stdout or python_result.stderr).strip(),
        },
        "node": _version_record("node", "--version"),
        "npm": _version_record("npm", "--version"),
        "codex": _version_record("codex", "--version"),
        "claude": _version_record("claude", "--version"),
        "chrome": chrome,
        "playwright_python": {
            "available": playwright_result.returncode == 0,
            "version": playwright_result.stdout.strip() or None,
        },
        "playwright_browser": {
            "available": bool(playwright_executables),
            "path": str(playwright_executables[-1])
            if playwright_executables
            else None,
            "version": playwright_browser_version,
        },
        "bubblewrap": _version_record("bwrap", "--version"),
        "strace": _version_record("strace", "--version"),
    }


def _run_or_raise(command: str, cwd: Path, context: str, timeout_sec: int = 120) -> CommandResult:
    result = run_command(command, cwd=cwd, timeout_sec=timeout_sec)
    if not result.ok:
        raise RuntimeError(
            f"{context}\ncommand: {command}\nexit: {result.exit_code}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _snapshot_source(task: Any) -> Path:
    raw = Path(task.repo_snapshot.path)
    source = raw if raw.is_absolute() else REPO_ROOT / raw
    source = source.resolve()
    if not source.is_dir():
        raise RuntimeError(f"missing local snapshot: {source}")
    return source


def _relative_tree_entries(
    root: Path,
    excludes: set[str] | frozenset[str],
    *,
    root_only_excludes: bool = False,
) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if (path.is_file() or path.is_symlink())
            and not (
                path.relative_to(root).parts[0] in excludes
                if root_only_excludes
                else any(part in excludes for part in path.relative_to(root).parts)
            )
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _tree_digest(
    root: Path,
    *,
    excludes: set[str] | frozenset[str],
    root_only_excludes: bool = False,
) -> str:
    """Hash file bytes and symlink identity without following directory links."""
    digest = hashlib.sha256()
    for path in _relative_tree_entries(
        root,
        excludes,
        root_only_excludes=root_only_excludes,
    ):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            digest.update(b"file\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_source_symlinks(source: Path) -> dict[str, str]:
    root = source.resolve()
    records: dict[str, str] = {}
    for path in _relative_tree_entries(
        source,
        SOURCE_EXCLUDES,
        root_only_excludes=True,
    ):
        if not path.is_symlink():
            continue
        relative = path.relative_to(source).as_posix()
        raw_target = os.readlink(path)
        if Path(raw_target).is_absolute():
            raise RuntimeError(
                f"source snapshot symlink must be relative: {relative} -> {raw_target}"
            )
        resolved_target = (path.parent / raw_target).resolve(strict=False)
        if not resolved_target.is_relative_to(root):
            raise RuntimeError(
                f"source snapshot symlink escapes source root: {relative} -> {raw_target}"
            )
        if not resolved_target.exists():
            raise RuntimeError(
                f"source snapshot symlink is broken: {relative} -> {raw_target}"
            )
        target_relative = resolved_target.relative_to(root)
        if target_relative.parts[0] in SOURCE_EXCLUDES:
            raise RuntimeError(
                "source snapshot symlink resolves into excluded material: "
                f"{relative} -> {raw_target}"
            )
        records[relative] = raw_target
    return records


def _copy_source_only(source: Path, target: Path) -> None:
    source_symlinks = _safe_source_symlinks(source)

    source_root = source.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        if Path(directory).resolve() != source_root:
            return set()
        return {name for name in names if name in SOURCE_EXCLUDES}

    shutil.copytree(source, target, ignore=ignore, symlinks=True)
    copied_symlinks = _safe_source_symlinks(target)
    if copied_symlinks != source_symlinks:
        raise RuntimeError(
            "source-only copy changed symlink identity: "
            f"source={source_symlinks} copied={copied_symlinks}"
        )
    leaked = [
        path
        for path in target.rglob("*")
        if path.relative_to(target).parts[0] in SOURCE_EXCLUDES
    ]
    if leaked:
        raise RuntimeError(f"sensitive paths leaked into isolated source: {leaked[:5]}")

    source_digest = _tree_digest(
        source,
        excludes=SOURCE_EXCLUDES,
        root_only_excludes=True,
    )
    copied_digest = _tree_digest(target, excludes=frozenset())
    if copied_digest != source_digest:
        raise RuntimeError(
            "source-only copy does not match the frozen source boundary: "
            f"source={source_digest} copied={copied_digest}"
        )


PORT_FLAG = re.compile(r"(?P<prefix>--port(?:\s+|=))\d+")
LOOPBACK_PORT = re.compile(r"(?P<prefix>https?://(?:127\.0\.0\.1|localhost):)\d+")


def _replace_runtime_port(value: str, port: int) -> str:
    value = PORT_FLAG.sub(lambda match: f"{match.group('prefix')}{port}", value)
    return LOOPBACK_PORT.sub(lambda match: f"{match.group('prefix')}{port}", value)


def _rewrite_package_port(workspace: Path, port: int) -> None:
    package_path = workspace / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.setdefault("scripts", {})
    for name, command in list(scripts.items()):
        if isinstance(command, str):
            scripts[name] = _replace_runtime_port(command, port)
    if "dev" not in scripts:
        scripts["dev"] = f"vite --host 127.0.0.1 --port {port}"
    elif isinstance(scripts["dev"], str) and not PORT_FLAG.search(scripts["dev"]):
        scripts["dev"] = f"{scripts['dev']} --port {port}"
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")


ROOT_PACKAGE_LAUNCH = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(?:exec\s+)?"
    r"(?:npm(?:\s+run)?|pnpm|yarn)\b"
)


def _prepare_runtime_port(task: TaskBundle, workspace: Path, port: int) -> None:
    """Rewrite a root package script when setup.launch invokes it indirectly.

    Replacing a port in ``npm run dev`` itself is impossible: the fixed port
    lives in package.json.  These rewrites happen before the isolated source
    baseline is committed, so they are harness configuration rather than an
    agent patch.
    """
    package_path = workspace / "package.json"
    if not package_path.is_file():
        return
    if not task.setup.launch or any(
        ROOT_PACKAGE_LAUNCH.search(command) for command in task.setup.launch
    ):
        _rewrite_package_port(workspace, port)


def _public_build_command(task: TaskBundle) -> str:
    setup = getattr(task, "setup", None)
    for command in reversed(getattr(setup, "install", ())):
        lowered = command.lower()
        if re.search(r"(?:\bnx\b.*\bbuild\b|\bbuild\b.*\bnx\b)", lowered):
            return command
    return "npm run build"


def _public_launch_commands(task: TaskBundle, workspace: Path, port: int) -> tuple[str, ...]:
    if task.setup.launch:
        return tuple(_replace_runtime_port(command, port) for command in task.setup.launch)
    package_path = workspace / "package.json"
    if not package_path.is_file():
        raise RuntimeError("web CUA task has no setup.launch or root package.json")
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.get("scripts") or {}
    if not isinstance(scripts, dict) or not isinstance(scripts.get("dev"), str):
        raise RuntimeError("web CUA task has no setup.launch or root dev script")
    return ("npm run dev",)


def _initialize_source_git(workspace: Path) -> Workspace:
    for command in (
        "git init",
        "git add .",
        "git -c user.name=cua-swe -c user.email=cua-swe@example.invalid "
        "commit -m 'isolated source baseline'",
    ):
        _run_or_raise(
            command,
            workspace,
            "isolated Git setup failed",
            timeout_sec=SOURCE_GIT_TIMEOUT_SEC,
        )
    tracked = run_command(
        "git ls-files",
        cwd=workspace,
        timeout_sec=SOURCE_GIT_TIMEOUT_SEC,
    )
    if not tracked.ok:
        raise RuntimeError(f"could not audit isolated Git history: {tracked.stderr}")
    forbidden = [line for line in tracked.stdout.splitlines() if HIDDEN_PATH_NAME.search(line)]
    if forbidden:
        raise RuntimeError(f"hidden material entered isolated Git history: {forbidden}")
    return Workspace(task_id="isolated", path=workspace)


# Native agents import the shared provider layer (provider_client.py) from their directory.
NATIVE_AGENT_RUNTIMES = frozenset({"responses", "anthropic", "kimi", "qwen"})


def _expected_tool_names(condition: str, runtime: str) -> list[str]:
    if runtime not in {
        "codex",
        "claude",
        "responses",
        "anthropic",
        "kimi",
        "qwen",
    }:
        raise ValueError(f"unsupported isolated agent runtime: {runtime}")
    wrapper = "run_web_cua_agent.sh" if condition == "cua" else "run_code_only_agent.sh"
    names = ["render_web_agent_prompt.py", wrapper]
    if condition == "cua":
        names.extend(
            (
                "web_cua_broker.py",
                "web_cua_client.py",
                "web_cua_launcher.S",
                "web_cua_mcp.py",
                "web_cua_tool.py",
            )
        )
    if runtime == "responses":
        names.append("run_responses_agent.py")
    elif runtime == "anthropic":
        names.append("run_anthropic_cua_agent.py")
    elif runtime == "kimi":
        names.append("run_kimi_cua_agent.py")
    elif runtime == "qwen":
        names.append("run_qwen_cua_agent.py")
    if runtime in NATIVE_AGENT_RUNTIMES:
        # Native agents import the shared provider layer from their own directory.
        names.append("provider_client.py")
    return names


def _copy_isolated_tools(
    isolated_root: Path,
    condition: str,
    runtime: str = "codex",
) -> Path:
    scripts_dir = isolated_root / "tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    names = _expected_tool_names(condition, runtime)
    for name in names:
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts_dir / name)
    if condition == "cua":
        isolated_src = isolated_root / "tools" / "src"
        shutil.copytree(
            REPO_ROOT / "src" / "cua_swe_bench",
            isolated_src / "cua_swe_bench",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    return scripts_dir


@lru_cache(maxsize=8)
def _expected_tool_packet_digest(condition: str, runtime: str = "codex") -> str:
    temporary_root = Path(tempfile.mkdtemp(prefix="cua-swe-tool-packet-digest-"))
    try:
        _copy_isolated_tools(temporary_root, condition, runtime)
        return _tool_source_digest(temporary_root / "tools")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def _sandbox_profile() -> str:
    repo = str(REPO_ROOT.resolve()).replace('"', '\\"')
    return "".join(
        [
            "(version 1)",
            "(allow default)",
            f'(deny file-read* (subpath "{repo}"))',
            f'(deny file-write* (subpath "{repo}"))',
        ]
    )


def _ancestor_named(path: Path, name: str, parent_name: str | None = None) -> Path | None:
    for candidate in (path, *path.parents):
        if candidate.name == name and (
            parent_name is None or candidate.parent.name == parent_name
        ):
            return candidate
    return None


def _venv_root(python_bin: Path | None) -> Path | None:
    if python_bin is None:
        return None
    candidate = python_bin.expanduser().absolute()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "pyvenv.cfg").is_file():
            return parent
    return None


def _resolver_runtime_mounts(
    resolv_conf: Path = Path("/etc/resolv.conf"),
) -> list[Path]:
    candidates = [Path("/run/systemd/resolve/resolv.conf")]
    if resolv_conf.is_symlink():
        try:
            resolved = resolv_conf.resolve(strict=True)
        except OSError:
            resolved = None
        if resolved is not None and not resolved.is_relative_to(Path("/etc")):
            candidates.append(resolved)
    return list(dict.fromkeys(path for path in candidates if path.is_file()))


def _bubblewrap_runtime_mounts(
    python_bin: Path | None,
    *,
    allow_browser_runtime: bool = True,
) -> list[Path]:
    paths: list[Path] = []
    codex_command = shutil.which("codex")
    if codex_command:
        local_bin = Path(codex_command).expanduser().absolute().parent
        if local_bin.is_dir():
            paths.append(local_bin)
    node_path = shutil.which("node")
    if node_path:
        resolved_node = Path(node_path).resolve()
        node_root = next(
            (
                candidate
                for candidate in (resolved_node.parent, *resolved_node.parents)
                if candidate.name.startswith("node-v")
            ),
            None,
        )
        if node_root is not None:
            paths.append(node_root)
    if codex_command:
        codex_root = _ancestor_named(
            Path(codex_command).resolve(), "codex", "@openai"
        )
        if codex_root is not None:
            paths.append(codex_root)
    claude_command = shutil.which("claude")
    if claude_command:
        claude_entry = Path(claude_command).expanduser().absolute()
        if claude_entry.parent.is_dir():
            paths.append(claude_entry.parent)
        claude_resolved = claude_entry.resolve()
        if claude_resolved.parent.is_dir():
            paths.append(claude_resolved.parent)
    venv_root = _venv_root(python_bin)
    if venv_root is not None:
        paths.append(venv_root)
    if allow_browser_runtime:
        chrome_root = Path("/opt/google/chrome")
        if chrome_root.is_dir():
            paths.append(chrome_root)
        playwright_browsers = Path(
            os.environ.get(
                "PLAYWRIGHT_BROWSERS_PATH",
                str(Path.home() / ".cache" / "ms-playwright"),
            )
        ).expanduser()
        if playwright_browsers.is_dir():
            paths.append(playwright_browsers)
    paths.extend(_resolver_runtime_mounts())
    return list(dict.fromkeys(path for path in paths if path.exists()))


def _bubblewrap_parent_dirs(paths: list[Path]) -> list[Path]:
    directories: set[Path] = set()
    for path in paths:
        for parent in reversed(path.parents):
            if parent == Path("/"):
                continue
            if parent.parts and parent.parts[1] in {"usr", "etc", "proc", "dev", "tmp"}:
                continue
            directories.add(parent)
    return sorted(directories, key=lambda item: (len(item.parts), str(item)))


def _sandbox_command(
    profile: str,
    isolated_root: Path,
    workspace: Path,
    python_bin: Path | None = None,
    *,
    allow_browser_runtime: bool = True,
    read_only_paths: tuple[Path, ...] = (),
    pinned_writable_paths: tuple[Path, ...] = (),
    external_read_only_mounts: tuple[tuple[Path, Path], ...] = (),
    external_writable_mounts: tuple[tuple[Path, Path], ...] = (),
    workspace_read_only_mounts: tuple[tuple[Path, Path], ...] = (),
    workspace_writable_mounts: tuple[tuple[Path, Path], ...] = (),
    unshare_network: bool = False,
) -> tuple[list[str], str]:
    sandbox_exec = shutil.which("sandbox-exec")
    if sandbox_exec:
        if (
            read_only_paths
            or pinned_writable_paths
            or external_read_only_mounts
            or external_writable_mounts
            or workspace_read_only_mounts
            or workspace_writable_mounts
            or unshare_network
        ):
            raise RuntimeError("protected verifier containment requires bubblewrap")
        return [sandbox_exec, "-p", profile], "sandbox-exec"

    bubblewrap = shutil.which("bwrap")
    if bubblewrap:
        root = isolated_root.resolve()
        work = workspace.resolve()
        if not work.is_relative_to(root):
            raise RuntimeError("isolated workspace must be inside the isolated root")
        runtime_mounts = _bubblewrap_runtime_mounts(
            python_bin,
            allow_browser_runtime=allow_browser_runtime,
        )
        parent_dirs = _bubblewrap_parent_dirs([*runtime_mounts, root])
        command = [
            bubblewrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-pid",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/etc",
            "/etc",
        ]
        if unshare_network:
            command.append("--unshare-net")
        command.extend(
            [
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--symlink",
                "usr/sbin",
                "/sbin",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
            ]
        )
        for directory in parent_dirs:
            command.extend(["--dir", str(directory)])
        for path in runtime_mounts:
            command.extend(["--ro-bind", str(path), str(path)])
        command.extend(
            [
                "--dir",
                str(root),
                "--bind",
                str(root),
                str(root),
                "--bind",
                str(work),
                str(work),
            ]
        )
        rollout = root / "rollout"
        if rollout.is_dir() and not rollout.is_symlink():
            command.extend(["--bind", str(rollout), str(rollout)])
        for path in pinned_writable_paths:
            pinned = path.absolute()
            if not pinned.is_relative_to(root) or not pinned.is_dir() or pinned.is_symlink():
                raise RuntimeError(f"invalid pinned sandbox path: {pinned}")
            command.extend(["--bind", str(pinned), str(pinned)])
        for path in read_only_paths:
            protected = path.absolute()
            if (
                not protected.is_relative_to(root)
                or not protected.is_dir()
                or protected.is_symlink()
            ):
                raise RuntimeError(f"invalid read-only sandbox path: {protected}")
            command.extend(["--ro-bind", str(protected), str(protected)])
        external_mounts = (
            *((source, target, True) for source, target in external_read_only_mounts),
            *((source, target, False) for source, target in external_writable_mounts),
        )
        workspace_mounts = (
            *((source, target, True) for source, target in workspace_read_only_mounts),
            *((source, target, False) for source, target in workspace_writable_mounts),
        )
        for source, target, read_only in workspace_mounts:
            host_source = source.expanduser().absolute()
            namespace_target = target.absolute()
            if (
                not host_source.is_dir()
                or host_source.is_symlink()
                or not namespace_target.is_relative_to(work)
                or namespace_target == work
            ):
                raise RuntimeError(
                    f"invalid external workspace mount: {host_source} -> {namespace_target}"
                )
            command.extend(
                [
                    "--dir",
                    str(namespace_target),
                    "--ro-bind" if read_only else "--bind",
                    str(host_source),
                    str(namespace_target),
                ]
            )
        created_mount_dirs: set[Path] = set()
        if external_mounts:
            command.extend(["--dir", "/run"])
        for source, target, read_only in external_mounts:
            host_source = source.expanduser().absolute()
            namespace_target = target.absolute()
            if (
                not host_source.is_dir()
                or host_source.is_symlink()
                or not namespace_target.is_relative_to(Path("/run/cua-swe-evaluator"))
            ):
                raise RuntimeError(
                    f"invalid external evaluator mount: {host_source} -> {namespace_target}"
                )
            for directory in reversed(namespace_target.parents):
                if directory in {Path("/"), Path("/run")}:
                    continue
                if directory not in created_mount_dirs:
                    command.extend(["--dir", str(directory)])
                    created_mount_dirs.add(directory)
            if namespace_target not in created_mount_dirs:
                command.extend(["--dir", str(namespace_target)])
                created_mount_dirs.add(namespace_target)
            command.extend(
                [
                    "--ro-bind" if read_only else "--bind",
                    str(host_source),
                    str(namespace_target),
                ]
            )
        command.extend(
            [
                "--ro-bind",
                str(root / "tools"),
                str(root / "tools"),
                "--chdir",
                str(work),
            ]
        )
        return (
            command,
            "bubblewrap",
        )

    raise RuntimeError(
        "no supported evaluation sandbox found; install sandbox-exec on macOS "
        "or bubblewrap (bwrap) on Linux"
    )


def _directory_identity(path: Path) -> dict[str, int]:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"protected root is not a directory: {path}")
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }


def _assert_directory_identity(path: Path, expected: dict[str, int]) -> None:
    actual = _directory_identity(path)
    if actual != expected:
        raise RuntimeError(f"protected root identity changed during agent execution: {path}")


def _verify_sandbox(
    profile: str,
    isolated_root: Path,
    workspace: Path,
    task_file: Path,
    source: Path,
    python_bin: Path,
    *,
    allow_browser_runtime: bool,
) -> dict[str, Any]:
    sandbox, backend = _sandbox_command(
        profile,
        isolated_root,
        workspace,
        python_bin,
        allow_browser_runtime=allow_browser_runtime,
    )
    candidates = [task_file, task_file.parent / "gold.patch"]
    verifier_root = source / "verifiers"
    if verifier_root.is_dir():
        candidates.extend(sorted(path for path in verifier_root.rglob("*") if path.is_file())[:1])
    protected_targets = [path for path in candidates if path.is_file()]
    probes: list[dict[str, Any]] = []
    for target in protected_targets:
        command = shlex.join([*sandbox, "/bin/cat", str(target)])
        result = run_command(command, cwd=workspace, timeout_sec=15)
        probes.append(
            {
                "target_kind": _repo_relative(target),
                "blocked": not result.ok,
                "exit_code": result.exit_code,
                "stderr": result.stderr,
            }
        )
    local_probe = workspace / ".isolation-write-probe"
    command = shlex.join(
        [
            *sandbox,
            "/bin/sh",
            "-c",
            f"printf ok > {shlex.quote(str(local_probe))} && cat {shlex.quote(str(local_probe))}",
        ]
    )
    local = run_command(command, cwd=workspace, timeout_sec=15)
    local_probe.unlink(missing_ok=True)
    tool_target = next(
        path
        for path in (isolated_root / "tools" / "scripts").iterdir()
        if path.is_file()
    )
    tool_write = run_command(
        shlex.join(
            [
                *sandbox,
                "/bin/sh",
                "-c",
                f"printf tamper >> {shlex.quote(str(tool_target))}",
            ]
        ),
        cwd=workspace,
        timeout_sec=15,
    )
    host_path_probes: list[dict[str, Any]] = []
    browser_runtime_probes: list[dict[str, Any]] = []
    if backend == "bubblewrap":
        host_targets = [
            REPO_ROOT,
            Path.home() / ".ssh",
            Path.home() / ".claude",
            Path.home() / ".codex",
        ]
        for target in host_targets:
            if not target.exists():
                continue
            result = run_command(
                shlex.join(
                    [
                        *sandbox,
                        "/bin/sh",
                        "-c",
                        f"test ! -e {shlex.quote(str(target))}",
                    ]
                ),
                cwd=workspace,
                timeout_sec=15,
            )
            host_path_probes.append(
                {
                    "target_kind": str(target),
                    "blocked": result.ok,
                    "exit_code": result.exit_code,
                    "stderr": result.stderr,
                }
            )
        if not allow_browser_runtime:
            for target in (
                Path("/opt/google/chrome"),
                Path(
                    os.environ.get(
                        "PLAYWRIGHT_BROWSERS_PATH",
                        str(Path.home() / ".cache" / "ms-playwright"),
                    )
                ).expanduser(),
            ):
                result = run_command(
                    shlex.join([*sandbox, "/bin/sh", "-c", f"test ! -e {shlex.quote(str(target))}"]),
                    cwd=workspace,
                    timeout_sec=15,
                )
                browser_runtime_probes.append(
                    {
                        "target_kind": str(target),
                        "blocked": result.ok,
                        "exit_code": result.exit_code,
                        "stderr": result.stderr,
                    }
                )
    if (
        not all(item["blocked"] for item in probes)
        or not local.ok
        or local.stdout.strip() != "ok"
        or tool_write.ok
        or any(not probe["blocked"] for probe in host_path_probes)
        or any(not probe["blocked"] for probe in browser_runtime_probes)
    ):
        raise RuntimeError(
            "sandbox isolation preflight failed: "
            f"probes={probes}, local={_command_dict(local)}, "
            f"tool_write={_command_dict(tool_write)}, "
            f"host_paths={host_path_probes}, browser_runtime={browser_runtime_probes}"
        )
    return {
        "backend": backend,
        "repo_probes": probes,
        "workspace_read_write_allowed": True,
        "tools_write_blocked": True,
        "filesystem_policy": (
            "allowlisted_root" if backend == "bubblewrap" else "repo_denied"
        ),
        "host_path_probes": host_path_probes,
        "browser_runtime_probes": browser_runtime_probes,
        "runtime_read_only_mounts": [
            str(path)
            for path in _bubblewrap_runtime_mounts(
                python_bin,
                allow_browser_runtime=allow_browser_runtime,
            )
        ]
        if backend == "bubblewrap"
        else [],
        "tool_write_probe": {
            "target": str(tool_target.relative_to(isolated_root)),
            "exit_code": tool_write.exit_code,
            "stderr": tool_write.stderr,
        },
    }


def _run_setup_commands(
    commands: tuple[str, ...],
    *,
    task: TaskBundle,
    profile: str,
    isolated_root: Path,
    workspace: Path,
    python_bin: Path,
    timeout_sec: int,
) -> list[CommandResult]:
    sandbox, _backend = _sandbox_command(
        profile,
        isolated_root,
        workspace,
        python_bin,
        allow_browser_runtime=False,
    )
    environment = ["env"]
    for name in (*sensitive_env_names(), *provider_secret_env_names(), *PROVIDER_LEASE_ENV_NAMES):
        environment.extend(["-u", name])
    environment.extend(
        [
            f"HOME={isolated_root / 'home'}",
            f"XDG_CACHE_HOME={isolated_root / 'home' / '.cache'}",
            f"npm_config_cache={isolated_root / 'home' / '.npm'}",
            f"PATH={_task_runtime_path(task)}",
            "DO_NOT_TRACK=1",
            "NEXT_TELEMETRY_DISABLED=1",
            "TURBO_TELEMETRY_DISABLED=1",
            "NG_CLI_ANALYTICS=false",
            "CI=1",
        ]
    )
    return [
        run_command(
            shlex.join([*sandbox, *environment, "/bin/sh", "-lc", command]),
            cwd=workspace,
            timeout_sec=timeout_sec,
        )
        for command in commands
    ]


def _task_runtime_path(task: Any) -> str:
    """Use the host's mounted modern Node for Web tasks, Node 18 for Games."""
    if str(getattr(task, "id", "")).startswith("gameqa."):
        return TASK_RUNTIME_PATH
    node = shutil.which("node")
    if not node:
        return TASK_RUNTIME_PATH
    node_parent = str(Path(node).expanduser().absolute().parent)
    return ":".join(dict.fromkeys((node_parent, *TASK_RUNTIME_PATH.split(":"))))


def _isolated_lifecycle_environment(
    isolated_root: Path,
    task: TaskBundle,
) -> list[str]:
    environment = ["env"]
    for name in (*sensitive_env_names(), *provider_secret_env_names(), *PROVIDER_LEASE_ENV_NAMES):
        environment.extend(["-u", name])
    environment.extend(
        [
            f"HOME={isolated_root / 'home'}",
            f"XDG_CACHE_HOME={isolated_root / 'home' / '.cache'}",
            f"npm_config_cache={isolated_root / 'home' / '.npm'}",
            f"PATH={_task_runtime_path(task)}",
            "DO_NOT_TRACK=1",
            "NEXT_TELEMETRY_DISABLED=1",
            "TURBO_TELEMETRY_DISABLED=1",
            "NG_CLI_ANALYTICS=false",
            "CI=1",
            "NO_UPDATE_NOTIFIER=1",
            "npm_config_offline=true",
            "npm_config_update_notifier=false",
        ]
    )
    return environment


def _http_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1):
            return True
    except HTTPError:
        return True
    except (OSError, URLError):
        return False


def _start_protected_service(
    *,
    task_file: Path,
    contract: ProtectedRuntimeContract,
    timeout_sec: int = 30,
) -> tuple[ProtectedServiceHandle, dict[str, Any]]:
    protected_root = Path(tempfile.mkdtemp(prefix="cua-swe-protected-service-"))
    staged_task = protected_root / "task"
    shutil.copytree(
        task_file.resolve().parent,
        staged_task,
        ignore=shutil.ignore_patterns(
            ".git",
            "node_modules",
            "dist",
            ".next",
            "__pycache__",
            ".pytest_cache",
            "verifier-artifacts",
        ),
    )
    materialized_entrypoint = _materialize_protected_service_entrypoint(
        staged_task,
        contract.service_command,
    )
    service_port = _reserve_loopback_port()
    command = contract.service_command.format(service_port=service_port)
    process = start_command(command, cwd=staged_task)
    health_url = f"http://127.0.0.1:{service_port}{contract.service_health_path}"
    deadline = time.monotonic() + timeout_sec
    try:
        while time.monotonic() < deadline:
            result = process.result_if_exited()
            if result is not None:
                raise RuntimeError(
                    "protected service exited before readiness: "
                    f"{result.command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
            if _http_ready(health_url):
                handle = ProtectedServiceHandle(
                    process=process,
                    staged_root=protected_root,
                    port=service_port,
                    health_url=health_url,
                )
                return handle, {
                    "source_sha256": _tree_digest(staged_task, excludes=TASK_DIGEST_EXCLUDES),
                    "source_outside_agent_sandbox": True,
                    "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                    "health_url": health_url,
                    "port": service_port,
                    "pid": process.process.pid,
                    "ready": True,
                    "materialized_entrypoint": materialized_entrypoint,
                }
            time.sleep(0.25)
        raise RuntimeError(f"protected service was not ready at {health_url}")
    except Exception:
        process.stop()
        shutil.rmtree(protected_root, ignore_errors=True)
        raise


def _materialize_protected_service_entrypoint(
    staged_task: Path,
    service_command: str,
) -> dict[str, str] | None:
    argv = shlex.split(service_command)
    if len(argv) < 2 or Path(argv[0]).name != "node":
        return None
    relative_entrypoint = Path(argv[1])
    if relative_entrypoint.is_absolute() or ".." in relative_entrypoint.parts:
        raise RuntimeError("protected service entrypoint must stay within the staged task")
    entrypoint = staged_task / relative_entrypoint
    if entrypoint.is_file():
        return None
    contract_module = staged_task / "repo" / "verifiers" / "contract_service.mjs"
    contract_payloads = (
        staged_task / "repo" / "verifiers" / "contract_payloads.json"
    )
    if (
        relative_entrypoint != Path("env/service.mjs")
        or not contract_module.is_file()
        or not contract_payloads.is_file()
    ):
        return None
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    entrypoint.write_text(
        """import {createContractServer} from '../repo/verifiers/contract_service.mjs';

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ?
      process.argv[index + 1] : fallback;
}

const host = option('--host', '127.0.0.1');
const port = Number(option('--port', '0'));
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error(`invalid --port: ${port}`);
}
const server = createContractServer();
server.listen(port, host);
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
""",
        encoding="utf-8",
    )
    return {
        "target": relative_entrypoint.as_posix(),
        "source": "repo/verifiers/contract_service.mjs",
        "reason": "runtime contract omitted evaluator-owned service entrypoint",
    }


def _stop_protected_service(handle: ProtectedServiceHandle | None) -> dict[str, Any] | None:
    if handle is None:
        return None
    result = handle.process.stop()
    health_closed = not _http_ready(handle.health_url)
    evidence = {
        "result": _command_dict(result),
        "health_url": handle.health_url,
        "port_closed": health_closed,
    }
    shutil.rmtree(handle.staged_root, ignore_errors=True)
    if not health_closed:
        raise RuntimeError(f"protected service remained reachable at {handle.health_url}")
    return evidence


def _start_public_app(
    *,
    task: TaskBundle,
    profile: str,
    isolated_root: Path,
    workspace: Path,
    python_bin: Path,
    port: int,
    runtime_contract: ProtectedRuntimeContract | None = None,
    protected_service_port: int | None = None,
    timeout_sec: int = 120,
) -> tuple[list[RunningCommand], dict[str, Any]]:
    if runtime_contract is not None:
        if protected_service_port is None:
            raise RuntimeError("external-contract application requires a protected service port")
        commands = (
            runtime_contract.application_command.format(
                app_port=port,
                service_port=protected_service_port,
            ),
        )
    else:
        commands = _public_launch_commands(task, workspace, port)
    sandbox, backend = _sandbox_command(
        profile,
        isolated_root,
        workspace,
        python_bin,
        allow_browser_runtime=False,
    )
    environment = _isolated_lifecycle_environment(isolated_root, task)
    processes: list[RunningCommand] = []
    url = f"http://127.0.0.1:{port}"
    if _http_ready(url):
        raise RuntimeError(f"public CUA application port is already occupied: {url}")
    try:
        for command in commands:
            processes.append(
                start_command(
                    shlex.join(
                        [*sandbox, *environment, "/bin/sh", "-lc", command]
                    ),
                    cwd=workspace,
                )
            )
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            for process in processes:
                result = process.result_if_exited()
                if result is not None:
                    raise RuntimeError(
                        "setup.launch exited before the CUA agent: "
                        f"{result.command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                    )
            if _http_ready(url):
                return processes, {
                    "backend": backend,
                    "commands": list(commands),
                    "external_contract": runtime_contract is not None,
                    "protected_service_port": protected_service_port,
                    "url": url,
                    "ready": True,
                    "pids": [process.process.pid for process in processes],
                }
            time.sleep(0.5)
        raise RuntimeError(f"public CUA application was not ready at {url}")
    except Exception:
        for process in reversed(processes):
            process.stop()
        raise


def _stop_public_app(
    processes: list[RunningCommand],
    *,
    port: int,
    timeout_sec: int = 10,
) -> dict[str, Any]:
    results = [process.stop() for process in reversed(processes)]
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline and _http_ready(url):
        time.sleep(0.25)
    port_closed = not _http_ready(url)
    evidence = {
        "results": [_command_dict(result) for result in results],
        "url": url,
        "port_closed": port_closed,
    }
    if not port_closed:
        raise RuntimeError(f"public CUA application did not release port {port}")
    return evidence


def _start_fresh_evaluation_runtime(
    *,
    task_file: Path,
    task: TaskBundle,
    profile: str,
    isolated_root: Path,
    workspace: Path,
    python_bin: Path,
    port: int,
    runtime_contract: ProtectedRuntimeContract | None,
) -> tuple[
    ProtectedServiceHandle | None,
    dict[str, Any] | None,
    list[RunningCommand],
    dict[str, Any],
]:
    protected_service: ProtectedServiceHandle | None = None
    protected_service_start: dict[str, Any] | None = None
    if runtime_contract is not None:
        protected_service, protected_service_start = _start_protected_service(
            task_file=task_file,
            contract=runtime_contract,
        )
    try:
        application_processes, application_start = _start_public_app(
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace,
            python_bin=python_bin,
            port=port,
            runtime_contract=runtime_contract,
            protected_service_port=(
                protected_service.port if protected_service is not None else None
            ),
        )
    except Exception:
        _stop_protected_service(protected_service)
        raise
    return (
        protected_service,
        protected_service_start,
        application_processes,
        application_start,
    )


def _run_argv_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    display_command: str,
) -> CommandResult:
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
        exit_code = process.returncode
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        timeout_message = f"Command timed out after {timeout_sec} seconds"
        stderr = "\n".join(
            part
            for part in (
                str(exc.stderr or stderr or ""),
                timeout_message,
            )
            if part
        )
        stdout = str(exc.stdout or stdout or "")
        exit_code = 124
    return CommandResult(
        command=display_command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )


def _transient_node_esm_loader_failure(result: CommandResult) -> bool:
    """Identify the intermittent Node loader crash seen in contained builds."""
    if result.ok:
        return False
    combined = "\n".join((result.stdout or "", result.stderr or ""))
    return (
        "/node_modules/esm/esm.js:1" in combined
        and "const __global__ = this;(function (require, module, __shared__)" in combined
        and len(combined) >= 65_536
    )


def _replace_with_empty_directory(path: Path) -> None:
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)
    path.mkdir(parents=True)


def _trusted_verifier_path(python_bin: Path) -> str:
    directories: list[str] = [str(python_bin.expanduser().absolute().parent)]
    for executable in (shutil.which("node"), shutil.which("npm")):
        if executable:
            directories.append(str(Path(executable).expanduser().absolute().parent))
    directories.extend(("/usr/bin", "/bin", "/usr/local/bin"))
    return ":".join(dict.fromkeys(directories))


def _run_verifiers_contained(
    task: TaskBundle,
    workspace: Path,
    python_bin: Path,
    *,
    profile: str,
    isolated_root: Path,
    verifier_root: Path,
    artifact_root: Path,
    task_environment_root: Path | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[VerifierReport, dict[str, Any]]:
    rollout_root = isolated_root / "rollout"
    verifier_home = verifier_root.parent / "home"
    namespace_root = Path("/run/cua-swe-evaluator")
    namespace_verifier_root = namespace_root / "verifiers"
    namespace_artifact_root = namespace_root / "verifier-artifacts"
    namespace_home = namespace_root / "home"
    workspace_verifier_root = workspace / "verifiers"
    workspace_artifact_root = workspace / "verifier-artifacts"
    # Preserve the task bundle's original ``repo/`` + sibling ``env/``
    # layout.  Verifiers legitimately resolve protected contracts through
    # paths such as ``WORKSPACE.parent / 'env'`` or ``../../env``.  Mounting
    # the environment under ``workspace/env`` silently breaks those paths and
    # makes every behavioral verifier fail before reaching its assertions.
    workspace_environment_root = workspace.parent / "env"
    if verifier_root.is_relative_to(workspace):
        raise RuntimeError("protected verifier root must be external to the agent workspace")
    if artifact_root.is_relative_to(workspace):
        raise RuntimeError("verifier artifact root must be external to the agent workspace")
    if not verifier_root.is_dir() or verifier_root.is_symlink():
        raise RuntimeError("protected verifier root is not a regular directory")
    _reject_symlink_tree(verifier_root, "protected verifier root")
    _replace_with_empty_directory(artifact_root)
    _replace_with_empty_directory(verifier_home)
    task_environment_digest: str | None = None
    if task_environment_root is not None:
        if workspace_environment_root.exists() or workspace_environment_root.is_symlink():
            raise RuntimeError("post-agent task environment target already exists")
        shutil.copytree(task_environment_root, workspace_environment_root)
        _reject_symlink_tree(workspace_environment_root, "post-agent task environment")
        task_environment_digest = _directory_digest(workspace_environment_root)
    verifier_digest = _directory_digest(verifier_root)
    protected_identities = {
        "workspace": _directory_identity(workspace),
        "rollout": _directory_identity(rollout_root),
        "verifiers": _directory_identity(verifier_root),
        "verifier_artifacts": _directory_identity(artifact_root),
    }
    sandbox, backend = _sandbox_command(
        profile,
        isolated_root,
        workspace,
        python_bin,
        allow_browser_runtime=True,
        read_only_paths=(
            rollout_root,
            *((workspace_environment_root,) if task_environment_root is not None else ()),
        ),
        external_read_only_mounts=(
            (verifier_root, namespace_verifier_root),
        ),
        external_writable_mounts=(
            (artifact_root, namespace_artifact_root),
            (verifier_home, namespace_home),
        ),
        workspace_read_only_mounts=(
            (verifier_root, workspace_verifier_root),
        ),
        workspace_writable_mounts=(
            (artifact_root, workspace_artifact_root),
        ),
        # The trusted browser verifier must share the host loopback namespace
        # with the separately launched application.  An isolated network
        # namespace makes 127.0.0.1 refer to the verifier sandbox itself and
        # deterministically turns every UI check into connection-refused.
        unshare_network=False,
    )
    if backend != "bubblewrap":
        raise RuntimeError("protected verifier execution did not use bubblewrap")
    browser_root = Path(
        os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH",
            str(Path.home() / ".cache" / "ms-playwright"),
        )
    ).expanduser()
    if not browser_root.is_dir():
        raise RuntimeError("Playwright browser root is unavailable to contained verifiers")
    values = {
        "HOME": str(namespace_home),
        "XDG_CACHE_HOME": str(namespace_home / ".cache"),
        "npm_config_cache": str(namespace_home / ".npm"),
        "PATH": _trusted_verifier_path(python_bin),
        "LANG": "C.UTF-8",
        "TMPDIR": "/tmp",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PLAYWRIGHT_BROWSERS_PATH": str(browser_root),
        "CUA_SWE_PYTHON": str(python_bin),
        "CUA_SWE_MOBILEGYM_PYTHON": str(python_bin),
        "CUA_SWE_WORKSPACE": str(workspace),
        "CUA_SWE_VERIFIER_ROOT": str(workspace_verifier_root),
        "CUA_SWE_VERIFIER_ARTIFACTS": str(workspace_artifact_root),
        "CI": "1",
        **dict(environment or {}),
    }
    results: list[VerifierResult] = []
    loopback_readiness: list[dict[str, Any]] = []
    loopback_url = values.get("CUA_SWE_WEB_URL")
    for group, command in task.verifiers.ordered_commands():
        if loopback_url:
            ready = _http_ready(loopback_url)
            loopback_readiness.append(
                {"group": group, "phase": "before", "ready": ready}
            )
            if group != "build" and not ready:
                raise RuntimeError(
                    f"public evaluation application is unavailable before {group}: "
                    f"{loopback_url}"
                )
        argv = [
            *sandbox,
            "/usr/bin/env",
            "-i",
            *(f"{key}={value}" for key, value in values.items()),
            "/bin/sh",
            "-c",
            command,
        ]
        command_result = _run_argv_command(
            argv,
            cwd=workspace,
            timeout_sec=task.budgets.wall_time_sec,
            display_command=command,
        )
        transient_retries = 0
        while (
            group == "build"
            and transient_retries < 2
            and _transient_node_esm_loader_failure(command_result)
        ):
            transient_retries += 1
            time.sleep(1)
            command_result = _run_argv_command(
                argv,
                cwd=workspace,
                timeout_sec=task.budgets.wall_time_sec,
                display_command=command,
            )
        if transient_retries and command_result.ok:
            command_result = CommandResult(
                command=command_result.command,
                exit_code=command_result.exit_code,
                stdout=(
                    f"{command_result.stdout}\n"
                    f"[evaluator recovered after {transient_retries} transient "
                    "Node esm loader failure(s)]"
                ).strip(),
                stderr=command_result.stderr,
            )
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
        if loopback_url:
            loopback_readiness.append(
                {
                    "group": group,
                    "phase": "after",
                    "ready": _http_ready(loopback_url),
                }
            )
    for label, path in (
        ("workspace", workspace),
        ("rollout", rollout_root),
        ("verifiers", verifier_root),
        ("verifier_artifacts", artifact_root),
    ):
        _assert_directory_identity(path, protected_identities[label])
    if _directory_digest(verifier_root) != verifier_digest:
        raise RuntimeError("read-only verifier contents changed during evaluation")
    if (
        task_environment_digest is not None
        and _directory_digest(workspace_environment_root) != task_environment_digest
    ):
        raise RuntimeError("read-only task environment changed during evaluation")
    return VerifierReport(results=results), {
        "backend": backend,
        "network_namespace": "host_shared_for_loopback_application",
        "environment_policy": "empty_then_allowlisted",
        "verifier_root_read_only": True,
        "rollout_root_read_only": True,
        "artifact_root_pinned": True,
        "browser_runtime_read_only": True,
        "verifier_external_to_agent_workspace": True,
        "artifacts_external_to_agent_workspace": True,
        "evaluator_mount_namespace": str(namespace_root),
        "application_started_before_evaluator_materialization": True,
        "loopback_readiness": loopback_readiness,
        "verifier_digest_before": verifier_digest,
        "verifier_digest_after": _directory_digest(verifier_root),
        "task_environment_read_only": task_environment_root is not None,
        "task_environment_digest_before": task_environment_digest,
        "task_environment_digest_after": (
            _directory_digest(workspace_environment_root)
            if task_environment_digest is not None
            else None
        ),
        "pre_verifier_root_identities": protected_identities,
        "post_verifier_root_identities": {
            "workspace": _directory_identity(workspace),
            "rollout": _directory_identity(rollout_root),
            "verifiers": _directory_identity(verifier_root),
            "verifier_artifacts": _directory_identity(artifact_root),
        },
    }


def _extract_agent_patch_contained(
    workspace: Path,
    python_bin: Path,
    *,
    profile: str,
    isolated_root: Path,
    timeout_sec: int,
) -> tuple[str, dict[str, Any]]:
    rollout_root = isolated_root / "rollout"
    protected_identities = {
        "workspace": _directory_identity(workspace),
        "rollout": _directory_identity(rollout_root),
    }
    sandbox, backend = _sandbox_command(
        profile,
        isolated_root,
        workspace,
        python_bin,
        allow_browser_runtime=False,
        read_only_paths=(workspace, rollout_root),
        unshare_network=True,
    )
    if backend != "bubblewrap":
        raise RuntimeError("protected patch extraction did not use bubblewrap")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required for protected patch extraction")
    environment = [
        "/usr/bin/env",
        "-i",
        "HOME=/tmp",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_OPTIONAL_LOCKS=0",
    ]
    git_prefix = [
        git,
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "diff.external=",
    ]

    def invoke(arguments: list[str], display: str) -> CommandResult:
        return _run_argv_command(
            [*sandbox, *environment, *git_prefix, *arguments],
            cwd=workspace,
            timeout_sec=timeout_sec,
            display_command=display,
        )

    tracked = invoke(
        ["diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index"],
        "protected git diff",
    )
    if not tracked.ok:
        raise RuntimeError(f"protected tracked diff failed: {tracked.stderr}")
    untracked = invoke(
        ["ls-files", "-z", "--others", "--exclude-standard"],
        "protected git ls-files",
    )
    if not untracked.ok:
        raise RuntimeError(f"protected untracked listing failed: {untracked.stderr}")
    parts = [tracked.stdout]
    for raw_path in untracked.stdout.split("\0"):
        if not raw_path:
            continue
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("protected untracked listing returned an unsafe path")
        diff = invoke(
            [
                "diff",
                "--no-index",
                "--no-ext-diff",
                "--no-textconv",
                "--binary",
                "--full-index",
                "--",
                "/dev/null",
                raw_path,
            ],
            f"protected untracked diff: {raw_path}",
        )
        if diff.exit_code not in {0, 1}:
            raise RuntimeError(f"protected untracked diff failed: {diff.stderr}")
        if diff.exit_code == 1:
            parts.append(diff.stdout)
    for label, path in (("workspace", workspace), ("rollout", rollout_root)):
        _assert_directory_identity(path, protected_identities[label])
    return "\n".join(part for part in parts if part), {
        "backend": backend,
        "network_namespace": "isolated",
        "environment_policy": "empty_then_allowlisted",
        "workspace_read_only": True,
        "rollout_root_read_only": True,
        "git_external_diff_disabled": True,
        "git_textconv_disabled": True,
        "git_fsmonitor_disabled": True,
        "pre_patch_root_identities": protected_identities,
        "post_patch_root_identities": {
            "workspace": _directory_identity(workspace),
            "rollout": _directory_identity(rollout_root),
        },
    }


def _codex_native_binary(codex_entry: Path) -> Path:
    package_root = _ancestor_named(codex_entry, "codex", "@openai")
    if package_root is None:
        raise RuntimeError(f"Codex entry is outside the expected read-only package: {codex_entry}")
    candidates = sorted(
        path.resolve()
        for path in package_root.glob("node_modules/@openai/codex-*/vendor/*/bin/codex")
        if path.is_file()
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one architecture-native Codex binary, found "
            f"{[str(path) for path in candidates]}"
        )
    return candidates[0]


def _audit_file_record(path: Path) -> dict[str, str]:
    invoked = path.expanduser().absolute()
    resolved = invoked.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"audit policy executable is missing: {invoked}")
    return {
        "path": str(invoked),
        "resolved_path": str(resolved),
        "sha256": _sha256_file(resolved),
    }


def _adapter_runtime_executables(python_bin: Path) -> list[Path]:
    candidates: set[Path] = set()
    venv_root = _venv_root(python_bin)
    if venv_root is not None:
        for library_root in ("lib", "lib64"):
            candidates.update(
                path
                for path in venv_root.glob(
                    f"{library_root}/python*/site-packages/playwright/driver/node"
                )
                if path.is_file()
            )
    for root in (
        Path(
            os.environ.get(
                "PLAYWRIGHT_BROWSERS_PATH",
                str(Path.home() / ".cache" / "ms-playwright"),
            )
        ).expanduser(),
        Path("/opt/google/chrome"),
    ):
        if not root.is_dir():
            continue
        candidates.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.name
            in {
                "chrome",
                "chrome-headless-shell",
                "chrome_crashpad_handler",
                "google-chrome",
            }
        )
    candidates.update(path for path in ADAPTER_SYSTEM_EXECUTABLES if path.is_file())
    return sorted((path.absolute() for path in candidates), key=str)


def _dynamic_loader_paths() -> list[Path]:
    candidates: set[Path] = set()
    for root in (Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64")):
        if not root.is_dir():
            continue
        for pattern in ("ld-linux*.so*", "ld-musl*.so*", "ld.so", "ld64.so.1"):
            candidates.update(path for path in root.glob(pattern) if path.is_file())
    return sorted((path.absolute() for path in candidates), key=str)


def _launcher_macro(name: str, value: str) -> str:
    if any(character in value for character in ('"', "\\", "\n", "\r")):
        raise RuntimeError(f"unsafe character in CUA launcher value {name}")
    return f'-D{name}="{value}"'


def _compile_cua_launcher(
    isolated_root: Path,
    scripts_dir: Path,
    python_bin: Path,
    broker_socket: Path,
    broker_token: str,
) -> Path:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("protected CUA launcher currently requires x86_64 Linux")
    compiler = shutil.which("cc")
    if not compiler:
        raise RuntimeError("a C compiler is required to build the protected CUA launcher")
    output = isolated_root / "tools" / "bin" / "web_cua_launcher"
    output.parent.mkdir(parents=True)
    command = [
        compiler,
        "-nostdlib",
        "-static",
        "-no-pie",
        "-Wl,--build-id=none",
        "-x",
        "assembler-with-cpp",
        _launcher_macro("ADAPTER_PYTHON", str(python_bin.expanduser().absolute())),
        _launcher_macro("ADAPTER_CLIENT", str((scripts_dir / "web_cua_client.py").absolute())),
        _launcher_macro("ADAPTER_HOME", f"HOME={isolated_root / 'home'}"),
        _launcher_macro("ADAPTER_CACHE", f"XDG_CACHE_HOME={isolated_root / 'home' / '.cache'}"),
        _launcher_macro("BROKER_SOCKET", str(broker_socket.absolute())),
        _launcher_macro("BROKER_TOKEN", broker_token),
        str(scripts_dir / "web_cua_launcher.S"),
        "-o",
        str(output),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"failed to compile protected CUA launcher: {result.stderr}")
    output.chmod(0o755)
    return output


@dataclass(frozen=True)
class CuaBrokerHandle:
    process: subprocess.Popen[bytes]
    socket_path: Path
    admin_token: str
    network_audit_path: Path


def _start_cua_broker(
    *,
    isolated_root: Path,
    workspace: Path,
    rollout_dir: Path,
    scripts_dir: Path,
    python_bin: Path,
    broker_socket: Path,
    broker_token: str,
    audit_path: Path,
    state_root: Path,
    network_audit_path: Path,
    expected_url: str,
) -> CuaBrokerHandle:
    playwright_browsers = Path(
        os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH",
            str(Path.home() / ".cache" / "ms-playwright"),
        )
    ).expanduser()
    if not playwright_browsers.is_dir():
        raise RuntimeError("Playwright browser root is unavailable to the host CUA broker")
    broker_socket.parent.mkdir(parents=True, exist_ok=True)
    strace = shutil.which("strace")
    if not strace:
        raise RuntimeError("host-owned broker network auditing requires strace")
    admin_token = secrets.token_hex(32)
    broker_command = [
        str(python_bin),
        "-I",
        str(scripts_dir / "web_cua_broker.py"),
        "--socket",
        str(broker_socket),
        "--token",
        broker_token,
        "--admin-token",
        admin_token,
        "--audit-log",
        str(audit_path),
        "--state-root",
        str(state_root),
        "--python",
        str(python_bin),
        "--tool",
        str(scripts_dir / "web_cua_tool.py"),
        "--workspace",
        str(workspace),
        "--rollout-root",
        str(rollout_dir),
        "--expected-url",
        expected_url,
        "--home",
        str(isolated_root / "home"),
        "--cache-home",
        str(isolated_root / "home" / ".cache"),
        "--playwright-browsers",
        str(playwright_browsers),
    ]
    command = [
        strace,
        "-f",
        "-qq",
        "-v",
        "--always-show-pid",
        "--decode-pids=pidns",
        "--kill-on-exit",
        "-s",
        "512",
        "-e",
        "trace=execve,execveat,connect,sendto,sendmsg,sendmmsg,clone,clone3,fork,vfork,exit,exit_group",
        "-o",
        str(network_audit_path),
        *broker_command,
    ]
    stdout = (audit_path.parent / "cua-broker-stdout.txt").open("wb")
    stderr = (audit_path.parent / "cua-broker-stderr.txt").open("wb")
    try:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    finally:
        stdout.close()
        stderr.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if broker_socket.is_socket():
            return CuaBrokerHandle(
                process=process,
                socket_path=broker_socket,
                admin_token=admin_token,
                network_audit_path=network_audit_path,
            )
        if process.poll() is not None:
            details = (audit_path.parent / "cua-broker-stderr.txt").read_text(
                encoding="utf-8", errors="replace"
            )
            raise RuntimeError(f"host CUA broker exited during startup: {details}")
        time.sleep(0.05)
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("host CUA broker did not create its socket")


def _traced_process_ids(path: Path) -> set[int]:
    if not path.is_file():
        return set()
    return {
        int(pid)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if (pid := _strace_pid(line)).isdigit()
    }


def _stop_cua_broker(handle: CuaBrokerHandle | None) -> dict[str, Any] | None:
    if handle is None:
        return None
    process = handle.process
    if process.poll() is None and handle.socket_path.is_socket():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(str(handle.socket_path))
                connection.sendall(
                    json.dumps(
                        {
                            "shutdown": True,
                            "admin_token": handle.admin_token,
                            "pid": os.getpid(),
                        },
                        separators=(",", ":"),
                    ).encode()
                    + b"\n"
                )
                connection.recv(4096)
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    traced_pids = _traced_process_ids(handle.network_audit_path)
    live_pids: list[int] = []
    if platform.system() == "Linux":
        for pid in sorted(traced_pids):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            try:
                state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
            except (OSError, IndexError):
                state = "?"
            if state == "Z":
                continue
            live_pids.append(pid)
        for pid in live_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    with handle.network_audit_path.open("a", encoding="utf-8") as audit:
        audit.write("# CUA_SWE_BROKER_AUDIT_COMPLETE\n")
        audit.flush()
        os.fsync(audit.fileno())
    if live_pids:
        raise RuntimeError(
            "host CUA broker left traced descendants after shutdown: "
            + ", ".join(str(pid) for pid in live_pids)
        )
    return {
        "strace_kill_on_exit": True,
        "network_audit_complete": True,
        "traced_pid_count": len(traced_pids),
        "live_descendants_after_stop": [],
    }


def _write_audit_policy(
    policy_path: Path,
    *,
    trial: CleanTrial,
    isolated_root: Path,
    scripts_dir: Path,
    rollout_dir: Path,
    python_bin: Path,
    codex_entry: Path,
    adapter_launcher: Path | None,
    broker_socket: Path | None,
    broker_token: str | None,
    broker_audit_path: Path | None,
    broker_state_root: Path | None,
    broker_network_audit_path: Path | None,
    expected_app_url: str,
    expected_viewport: str | None,
) -> dict[str, Any]:
    native = _codex_native_binary(codex_entry)
    model_runtime = trial.model.runtime
    native_model_entries = {
        "responses": scripts_dir / "run_responses_agent.py",
        "anthropic": scripts_dir / "run_anthropic_cua_agent.py",
        "kimi": scripts_dir / "run_kimi_cua_agent.py",
        "qwen": scripts_dir / "run_qwen_cua_agent.py",
    }
    if model_runtime == "claude":
        claude_command = shutil.which("claude")
        if not claude_command:
            raise RuntimeError("Claude Code is not available on the evaluation host")
        model_entry = Path(claude_command).resolve()
        model_executable = model_entry
        model_bootstrap_kind = "direct"
    else:
        model_entry = native_model_entries.get(model_runtime, codex_entry)
        model_executable = (
            python_bin if model_runtime in native_model_entries else codex_entry
        )
        model_bootstrap_kind = (
            "python-script" if model_runtime in native_model_entries else "codex"
        )
    if trial.condition == "cua" and adapter_launcher is None:
        raise RuntimeError("CUA runtime has no immutable environment-sanitizing launcher")
    if trial.condition == "cua" and (
        broker_socket is None
        or broker_token is None
        or broker_audit_path is None
        or broker_state_root is None
        or broker_network_audit_path is None
    ):
        raise RuntimeError("CUA runtime has no host-owned broker provenance")
    if trial.condition == "cua" and _normalized_viewport(expected_viewport) is None:
        raise RuntimeError("CUA runtime has no valid task-declared viewport")
    dynamic_loaders = _dynamic_loader_paths()
    if platform.system() == "Linux" and not dynamic_loaders:
        raise RuntimeError("host audit could not identify a system dynamic loader")
    policy: dict[str, Any] = {
        "version": (
            6
            if model_runtime in {*native_model_entries, "claude"}
            else 4
        ),
        "execution_host": socket.gethostname(),
        "condition": trial.condition,
        "observation_mode": trial.observation_mode,
        "task_id": trial.task_id,
        "port": trial.port,
        "rollout_root": str(rollout_dir.resolve()),
        "workspace_root": str((isolated_root / "workspace").resolve()),
        "tool_packet_sha256": _tool_source_digest(isolated_root / "tools"),
        "codex_entry": _audit_file_record(codex_entry),
        "codex_native": _audit_file_record(native),
        "required_codex_argv": ["--strict-config", "--disable", "plugins"],
        "model_runtime": model_runtime,
        "model_bootstrap_kind": model_bootstrap_kind,
        "model_entry": _audit_file_record(model_entry),
        "model_executable": _audit_file_record(model_executable),
        "adapter_python": _audit_file_record(python_bin),
        "adapter_launcher": (
            _audit_file_record(adapter_launcher)
            if trial.condition == "cua" and adapter_launcher is not None
            else None
        ),
        "adapter_tool": (
            _audit_file_record(scripts_dir / "web_cua_client.py")
            if trial.condition == "cua"
            else None
        ),
        "adapter_descendant_executables": [],
        "broker_socket": str(broker_socket) if broker_socket is not None else None,
        "broker_token": broker_token,
        "broker_token_sha256": (
            hashlib.sha256(broker_token.encode()).hexdigest()
            if broker_token is not None
            else None
        ),
        "broker_audit_path": (
            str(broker_audit_path.resolve()) if broker_audit_path is not None else None
        ),
        "broker_state_root": (
            str(broker_state_root.resolve()) if broker_state_root is not None else None
        ),
        "broker_network_audit_path": (
            str(broker_network_audit_path.resolve())
            if broker_network_audit_path is not None
            else None
        ),
        "broker_tool": (
            _audit_file_record(scripts_dir / "web_cua_tool.py")
            if trial.condition == "cua"
            else None
        ),
        "broker_entry": (
            _audit_file_record(scripts_dir / "web_cua_broker.py")
            if trial.condition == "cua"
            else None
        ),
        "dynamic_loaders": [_audit_file_record(path) for path in dynamic_loaders],
        "expected_app_url": expected_app_url,
        "expected_viewport": expected_viewport if trial.condition == "cua" else None,
        "trace_contract": {
            "process": [
                "chdir",
                "clone",
                "clone3",
                "execve",
                "execveat",
                "exit",
                "exit_group",
                "fchdir",
                "fork",
                "vfork",
            ],
            "network": ["connect", "sendmsg", "sendmmsg", "sendto"],
            "complete_sentinel": "# CUA_SWE_AUDIT_COMPLETE",
        },
    }
    _write_json(policy_path, policy)
    return policy


def _agent_command(
    trial: CleanTrial,
    task: Any,
    isolated_root: Path,
    scripts_dir: Path,
    rollout_dir: Path,
    python_bin: Path,
    profile: str,
    host_audit_path: Path,
) -> str:
    codex_command = shutil.which("codex")
    if not codex_command:
        raise RuntimeError("Codex CLI is not available on the evaluation host")
    values = {
        "CUA_SWE_AGENT_ROLLOUT_DIR": str(rollout_dir),
        "CUA_SWE_TASK_ID": task.id,
        "CUA_SWE_TASK_INSTRUCTION": task.instruction,
        "CUA_SWE_BUILD_COMMAND": _public_build_command(task),
        "CUA_SWE_AGENT_RUNTIME": trial.model.runtime,
        "CUA_SWE_AGENT_PYTHON": str(python_bin),
        "CUA_SWE_PYTHON": str(python_bin),
        "CUA_SWE_CODEX_MODEL": trial.model.model_id,
        "CUA_SWE_CODEX_REASONING_EFFORT": "medium",
        "CODEX_HOME": str(isolated_root / "codex-home"),
        "HOME": str(isolated_root / "home"),
        "XDG_CACHE_HOME": str(isolated_root / "home" / ".cache"),
        "npm_config_cache": str(isolated_root / "home" / ".npm"),
        "PATH": _task_runtime_path(task),
        "DO_NOT_TRACK": "1",
        "NEXT_TELEMETRY_DISABLED": "1",
        "TURBO_TELEMETRY_DISABLED": "1",
        "NG_CLI_ANALYTICS": "false",
        "CI": "1",
        "NO_UPDATE_NOTIFIER": "1",
        "npm_config_offline": "true",
        "npm_config_update_notifier": "false",
        "CUA_SWE_CODEX_BIN": str(Path(codex_command).resolve()),
        "CUA_SWE_CODEX_NODE": str(Path(shutil.which("node") or "node").resolve()),
        "CUA_SWE_ANTHROPIC_AGENT": str(scripts_dir / "run_anthropic_cua_agent.py"),
        "CUA_SWE_ANTHROPIC_MODEL": trial.model.model_id,
        "CUA_SWE_RESPONSES_AGENT": str(scripts_dir / "run_responses_agent.py"),
        "CUA_SWE_RESPONSES_MODEL": trial.model.model_id,
        "CUA_SWE_KIMI_AGENT": str(scripts_dir / "run_kimi_cua_agent.py"),
        "CUA_SWE_KIMI_MODEL": trial.model.model_id,
        "CUA_SWE_QWEN_AGENT": str(scripts_dir / "run_qwen_cua_agent.py"),
        "CUA_SWE_QWEN_MODEL": trial.model.model_id,
    }
    if trial.model.runtime == "claude":
        claude_command = shutil.which("claude")
        if not claude_command:
            raise RuntimeError("Claude Code is not available on the evaluation host")
        values.update(
            {
                "CUA_SWE_CLAUDE_BIN": str(Path(claude_command).resolve()),
                "CUA_SWE_CLAUDE_MODEL": trial.model.model_id,
            }
        )
    if trial.condition == "cua":
        values.update(
            {
                "PYTHONNOUSERSITE": "1",
                "CUA_SWE_WEB_PORT": str(trial.port),
                "CUA_SWE_WEB_URL": _declared_web_start_url(task, trial.port),
                "CUA_SWE_WEB_CUA_TOOL": str(scripts_dir / "web_cua_tool.py"),
                "CUA_SWE_WEB_CUA_PYTHON": str(python_bin),
                "CUA_SWE_WEB_CUA_LAUNCHER": str(
                    isolated_root / "tools" / "bin" / "web_cua_launcher"
                ),
                "CUA_SWE_WEB_VIEWPORT": _declared_web_viewport(task),
                "CUA_SWE_WEB_OBSERVATION_MODE": trial.observation_mode,
            }
        )
    sandbox, _backend = _sandbox_command(
        profile,
        isolated_root,
        isolated_root / "workspace",
        python_bin,
        allow_browser_runtime=False,
    )
    strace = shutil.which("strace")
    if not strace:
        raise RuntimeError("host-owned exec auditing requires strace on evaluation hosts")
    timeout_command = shutil.which("timeout")
    if not timeout_command:
        raise RuntimeError("protected evaluation requires GNU timeout on evaluation hosts")
    wall_time_sec = int(task.budgets.wall_time_sec)
    command = [
        strace,
        "-f",
        "-qq",
        "--always-show-pid",
        "--decode-pids=pidns",
        "-s",
        "4096",
        "-e",
        "trace=execve,execveat,connect,sendto,sendmsg,sendmmsg,chdir,fchdir,clone,clone3,fork,vfork,exit,exit_group",
        "-o",
        str(host_audit_path),
        timeout_command,
        "--signal=TERM",
        "--kill-after=10s",
        f"{wall_time_sec}s",
        *sandbox,
        "env",
    ]
    for name in (
        *sensitive_env_names(),
        *provider_secret_env_names(),
        "CUA_SWE_TASK_CONTEXT",
        "CUA_SWE_TASK_VALIDATION_FLOW",
        "CUA_SWE_CODEX_PROFILE",
    ):
        command.extend(["-u", name])
    # Model calls go through the controller's gateway. The trial's lease (token and
    # routes) is not on this command line: run_agent_command passes it as process
    # environment, which strace records only as a variable count.
    command.extend(f"{key}={value}" for key, value in values.items())
    script = "run_web_cua_agent.sh" if trial.condition == "cua" else "run_code_only_agent.sh"
    command.extend(["bash", str(scripts_dir / script)])
    # Codex 0.146 reads additional prompt text from any inherited non-TTY
    # stdin.  Evaluation shards are commonly launched by an orchestrator whose
    # stdin pipe stays open for the lifetime of the shard, which would leave the
    # agent blocked waiting for EOF before its first model turn.  The protected
    # agent protocol is non-interactive, so close stdin explicitly at the shell
    # boundary.
    return f"{shlex.join(command)} </dev/null"


def _replace_declared_app_port(value: str, declared_url: str, port: int) -> str:
    parsed = urlsplit(declared_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port is None:
        raise ValueError(f"task start_url has no loopback port: {declared_url!r}")
    declared_port = parsed.port
    value = re.sub(
        rf"(?P<prefix>https?://(?:127\.0\.0\.1|localhost):){declared_port}(?![0-9])",
        lambda match: f"{match.group('prefix')}{port}",
        value,
    )
    return re.sub(
        rf"(?P<prefix>--port(?:=|\s+)){declared_port}(?![0-9])",
        lambda match: f"{match.group('prefix')}{port}",
        value,
    )


def _copy_evaluation_verifiers(
    source: Path,
    verifier_target: Path,
    port: int,
    declared_url: str,
    *,
    task_environment_available: bool = False,
) -> None:
    verifier_source = source / "verifiers"
    if not verifier_source.is_dir():
        raise RuntimeError(f"snapshot verifier directory is missing: {verifier_source}")
    if verifier_target.exists():
        raise RuntimeError("protected verifier staging target already exists")
    shutil.copytree(verifier_source, verifier_target)
    for verifier in verifier_target.rglob("*"):
        if not verifier.is_file():
            continue
        try:
            contents = verifier.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rewritten = _replace_declared_app_port(contents, declared_url, port)
        if rewritten != contents:
            verifier.write_text(rewritten, encoding="utf-8")


def _run_protected_post_agent_verifier(
    *,
    task: TaskBundle,
    source: Path,
    workspace: Path,
    port: int,
    python_bin: Path,
    profile: Path,
    isolated_root: Path,
    protected_root: Path,
) -> tuple[VerifierReport, dict[str, Any]]:
    """Run the single condition-independent evaluator after agent termination."""
    verifier_root = protected_root / "verifiers"
    artifact_root = protected_root / "verifier-artifacts"
    task_environment_root = source.parent / "env"
    if not protected_root.is_dir() or any(protected_root.iterdir()):
        raise RuntimeError("protected evaluation root must be a fresh external directory")
    if protected_root.is_relative_to(isolated_root):
        raise RuntimeError("protected evaluation root must be outside the agent sandbox")
    _copy_evaluation_verifiers(
        source,
        verifier_root,
        port,
        str(task.environment.start_url),
        task_environment_available=task_environment_root.is_dir(),
    )
    return _run_verifiers_contained(
        task,
        workspace,
        python_bin,
        profile=profile,
        isolated_root=isolated_root,
        verifier_root=verifier_root,
        artifact_root=artifact_root,
        task_environment_root=(
            task_environment_root if task_environment_root.is_dir() else None
        ),
        environment={
            "CUA_SWE_WEB_PORT": str(port),
            "CUA_SWE_WEB_URL": _declared_web_start_url(task, port),
        },
    )


def _cleanup_processes(marker_root: Path) -> None:
    marker = f"{marker_root.resolve()}/"
    try:
        output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    except subprocess.SubprocessError:
        return
    killed: list[int] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_text, command = line.split(None, 1)
            pid = int(pid_text)
        except ValueError:
            continue
        if marker not in command or pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            pass
    if not killed:
        return
    time.sleep(0.5)
    for pid in killed:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@dataclass(frozen=True)
class HostExecEvent:
    index: int
    pid: str
    executable: str
    argv: tuple[str, ...]
    raw: str
    succeeded: bool


@dataclass(frozen=True)
class HostTraceAttribution:
    lines: tuple[str, ...]
    exec_events: tuple[HostExecEvent, ...]
    exec_cwds: dict[int, str]
    parents: dict[str, str]
    spawned_at: dict[str, int]
    thread_children: frozenset[str]
    model_trust_from: dict[str, int]
    agent_trust_from: dict[str, int]
    adapter_trust_from: dict[str, int]
    model_pids: frozenset[str]
    adapter_pids: frozenset[str]
    adapter_requests: tuple[tuple[str, str, int, tuple[str, ...]], ...]
    adapter_invocations: tuple[tuple[str, str], ...]
    invalid_adapter_invocations: tuple[str, ...]
    audit_errors: tuple[str, ...]
    policy: dict[str, Any]


def _strace_pid(line: str) -> str:
    match = re.match(r"\s*(?:\[pid\s+)?(\d+)\]?\s+", line)
    return match.group(1) if match else "unknown"


def _strace_body(line: str) -> str:
    match = re.match(r"\s*(?:\[pid\s+)?\d+\]?\s+", line)
    return line[match.end() :] if match else ""


def _strace_argv(arguments: str) -> tuple[str, ...]:
    values: list[str] = []
    for token in re.findall(r'"((?:\\.|[^"\\])*)"', arguments):
        try:
            values.append(json.loads(f'"{token}"'))
        except json.JSONDecodeError:
            values.append(token)
    return tuple(values)


def _strace_quoted_value(value: str) -> str:
    try:
        return str(json.loads(f'"{value}"'))
    except json.JSONDecodeError:
        return value


def _host_exec_event(index: int, line: str) -> HostExecEvent | None:
    match = re.search(r'execve\("([^"]+)", \[(.*)\],', line)
    if not match:
        match = re.search(
            r'execveat\([^,]+,\s*"([^"]+)",\s*\[(.*)\],', line
        )
    if not match:
        return None
    return HostExecEvent(
        index=index,
        pid=_strace_pid(line),
        executable=match.group(1),
        argv=_strace_argv(match.group(2)),
        raw=line,
        succeeded=re.search(r"\)\s+=\s+0(?:\s|$)", line) is not None,
    )


def _host_exec_events(
    lines: tuple[str, ...],
    audit_errors: list[str],
) -> tuple[HostExecEvent, ...]:
    events: list[HostExecEvent] = []
    pending: dict[tuple[str, str], tuple[int, str]] = {}
    for index, line in enumerate(lines):
        pid = _strace_pid(line)
        unfinished = re.search(r"\b(execve|execveat)\(.*<unfinished \.\.\.>", line)
        if unfinished:
            key = (pid, unfinished.group(1))
            if key in pending:
                audit_errors.append(f"overlapping unfinished {key[1]} events for PID {pid}")
            pending[key] = (index, line.replace(" <unfinished ...>", ""))
            continue
        resumed = re.search(r"<\.\.\. (execve|execveat) resumed>(.*)$", line)
        if resumed:
            key = (pid, resumed.group(1))
            original = pending.pop(key, None)
            if original is None:
                audit_errors.append(f"host audit has unmatched resumed {key[1]} for PID {pid}")
                continue
            original_index, prefix = original
            combined = prefix + resumed.group(2)
            event = _host_exec_event(original_index, combined)
            if event is None:
                audit_errors.append(f"host audit could not reconstruct {key[1]} for PID {pid}")
            else:
                events.append(event)
            continue
        event = _host_exec_event(index, line)
        if event is not None:
            events.append(event)
    if pending:
        audit_errors.append("host audit ends with unfinished executable lifecycle events")
    return tuple(sorted(events, key=lambda event: event.index))


def _load_audit_policy(path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, ["missing host-owned audit policy"]
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"invalid host-owned audit policy: {type(exc).__name__}"]
    policy_version = policy.get("version")
    if policy_version not in {1, 2, 3, 4, 5, 6}:
        errors.append("unsupported audit policy version")
    if policy_version in {2, 3, 4} and policy.get("required_codex_argv") != [
        "--strict-config",
        "--disable",
        "plugins",
    ]:
        errors.append("audit policy lacks the required Codex plugin-disable arguments")
    if policy.get("condition") not in CONDITIONS:
        errors.append("audit policy has invalid condition")
    def validate_file_record(record: Any, label: str) -> None:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            errors.append(f"audit policy lacks {label} path")
            return
        invoked = Path(record["path"])
        if not invoked.is_absolute():
            errors.append(f"audit policy {label} path is not absolute")
        if re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256") or "")) is None:
            errors.append(f"audit policy lacks {label} digest")
            return
        # Remote shards are revalidated after transfer, where the execution-host runtime
        # paths need not exist.  On the execution host every recorded file does
        # exist, so bind the policy to both its resolved path and its contents.
        if invoked.exists():
            if not invoked.is_file():
                errors.append(f"audit policy {label} is not a regular file")
                return
            resolved = invoked.resolve()
            recorded_resolved = record.get("resolved_path")
            if recorded_resolved is not None and recorded_resolved != str(resolved):
                errors.append(f"audit policy {label} resolved path changed")
            if _sha256_file(resolved) != record.get("sha256"):
                errors.append(f"audit policy {label} digest mismatch")

    for label in ("codex_entry", "codex_native", "adapter_python"):
        record = policy.get(label)
        validate_file_record(record, label)
    if policy_version in {5, 6}:
        allowed_runtimes = (
            {"anthropic", "kimi", "qwen"}
            if policy_version == 5
            else {"responses", "anthropic", "kimi", "qwen", "claude"}
        )
        if policy.get("model_runtime") not in allowed_runtimes:
            errors.append("audit policy has invalid native model runtime")
        if policy_version == 6 and policy.get("model_bootstrap_kind") not in {
            "python-script",
            "direct",
        }:
            errors.append("audit policy has invalid model bootstrap kind")
        for label in ("model_entry", "model_executable"):
            validate_file_record(policy.get(label), label)
    if policy.get("condition") == "cua":
        launcher = policy.get("adapter_launcher")
        validate_file_record(launcher, "adapter_launcher")
        record = policy.get("adapter_tool")
        validate_file_record(record, "adapter_tool")
        descendants = policy.get("adapter_descendant_executables")
        if policy_version not in {4, 5, 6} and (not isinstance(descendants, list) or not descendants):
            errors.append("CUA audit policy lacks adapter descendant executable allowlist")
        elif isinstance(descendants, list):
            for index, descendant in enumerate(descendants):
                validate_file_record(descendant, f"adapter_descendant_executables[{index}]")
        if policy_version in {4, 5, 6}:
            for label in ("broker_tool", "broker_entry"):
                validate_file_record(policy.get(label), label)
            for label in (
                "broker_socket",
                "broker_audit_path",
                "broker_state_root",
                "broker_network_audit_path",
                "broker_token",
            ):
                if not isinstance(policy.get(label), str) or not policy[label]:
                    errors.append(f"audit policy lacks {label}")
            token = str(policy.get("broker_token") or "")
            if hashlib.sha256(token.encode()).hexdigest() != policy.get(
                "broker_token_sha256"
            ):
                errors.append("audit policy broker token digest mismatch")
            if _normalized_viewport(str(policy.get("expected_viewport") or "")) is None:
                errors.append("audit policy lacks a valid expected_viewport")
    dynamic_loaders = policy.get("dynamic_loaders")
    if policy_version in {3, 4, 5, 6} and (
        not isinstance(dynamic_loaders, list) or not dynamic_loaders
    ):
        errors.append("audit policy lacks dynamic-loader provenance")
    elif isinstance(dynamic_loaders, list):
        for index, loader in enumerate(dynamic_loaders):
            validate_file_record(loader, f"dynamic_loaders[{index}]")
    for label in ("rollout_root", "expected_app_url", "task_id"):
        if not isinstance(policy.get(label), str) or not policy[label]:
            errors.append(f"audit policy lacks {label}")
    if policy_version in {3, 4, 5, 6}:
        workspace_root = policy.get("workspace_root")
        if not isinstance(workspace_root, str) or not Path(workspace_root).is_absolute():
            errors.append("audit policy lacks absolute workspace_root")
    if not isinstance(policy.get("port"), int):
        errors.append("audit policy lacks port")
    rollout_root = Path(str(policy.get("rollout_root") or ""))
    isolated_tools = rollout_root.parent / "tools"
    expected_tool_digest = policy.get("tool_packet_sha256")
    if re.fullmatch(r"[0-9a-f]{64}", str(expected_tool_digest or "")) is None:
        errors.append("audit policy lacks tool packet digest")
    elif isolated_tools.is_dir() and _tool_source_digest(isolated_tools) != expected_tool_digest:
        errors.append("audit policy tool packet digest mismatch")
    return policy, errors


def _argv_option(argv: tuple[str, ...], name: str) -> str | None:
    try:
        index = argv.index(name)
    except ValueError:
        return None
    return argv[index + 1] if index + 1 < len(argv) else None


def _normalized_viewport(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.fullmatch(r"([1-9][0-9]{0,3})x([1-9][0-9]{0,3})", value)
    if match is None:
        return None
    width, height = (int(part) for part in match.groups())
    return value if width <= 3840 and height <= 2160 else None


def _path_within(value: str | None, root: Path) -> bool:
    if not value:
        return False
    candidate = Path(os.path.normpath(value))
    return candidate.is_absolute() and candidate.is_relative_to(root)


def _validated_adapter_arguments(
    argv: tuple[str, ...],
    verb_index: int,
    policy: dict[str, Any],
) -> str | None:
    if len(argv) <= verb_index:
        return None
    verb = argv[verb_index]
    allowed_options = {
        "start": {"--url", "--artifacts-dir", "--session-file", "--host", "--port", "--timeout", "--viewport", "--observation-mode"},
        "serve": {"--url", "--artifacts-dir", "--session-file", "--host", "--port", "--viewport", "--observation-mode"},
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
        },
        "stop": {"--session-file"},
    }
    if verb not in allowed_options:
        return None
    parsed: dict[str, str] = {}
    index = verb_index + 1
    while index < len(argv):
        option = argv[index]
        if option not in allowed_options[verb] or option in parsed or index + 1 >= len(argv):
            return None
        parsed[option] = argv[index + 1]
        index += 2
    rollout_root = Path(str(policy.get("rollout_root") or "/invalid"))
    session_file = parsed.get("--session-file")
    if not _path_within(session_file, rollout_root):
        return None
    if verb in {"start", "serve"}:
        if parsed.get("--url") != policy.get("expected_app_url"):
            return None
        if not _path_within(parsed.get("--artifacts-dir"), rollout_root):
            return None
        viewport = parsed.get("--viewport")
        if policy.get("version") in {4, 5, 6} and _normalized_viewport(viewport) is None:
            return None
        if viewport is not None and _normalized_viewport(viewport) is None:
            return None
        if parsed.get("--observation-mode", "structured") != policy.get(
            "observation_mode", "structured"
        ):
            return None
    if parsed.get("--host", "127.0.0.1") != "127.0.0.1":
        return None
    if verb == "act" and parsed.get("--kind") == "resize":
        if set(parsed) != {
            "--session-file",
            "--kind",
            "--width",
            "--height",
        }:
            return None
        try:
            width = int(parsed["--width"])
            height = int(parsed["--height"])
        except ValueError:
            return None
        if width <= 0 or height <= 0 or width > 3840 or height > 2160:
            return None
    if verb == "act" and "--duration-ms" in parsed:
        try:
            duration_ms = int(parsed["--duration-ms"])
        except ValueError:
            return None
        if duration_ms < 1 or duration_ms > 2000:
            return None
    return verb


def _validated_public_adapter_invocation(
    event: HostExecEvent,
    policy: dict[str, Any],
) -> str | None:
    launcher = str((policy.get("adapter_launcher") or {}).get("path") or "")
    if (
        not launcher
        or event.executable != launcher
        or not event.argv
        or event.argv[0] != launcher
    ):
        return None
    if event.argv == (launcher, "--help"):
        return "help"
    verb = _validated_adapter_arguments(event.argv, 1, policy)
    return verb if verb in {"start", "observe", "act", "stop"} else None


def _validated_internal_serve(
    event: HostExecEvent,
    policy: dict[str, Any],
) -> bool:
    python_path = str((policy.get("adapter_python") or {}).get("path") or "")
    tool_path = str((policy.get("adapter_tool") or {}).get("path") or "")
    return (
        event.executable == python_path
        and event.argv[:3] == (python_path, "-I", tool_path)
        and _validated_adapter_arguments(event.argv, 3, policy) == "serve"
    )


def _serve_matches_start(serve: HostExecEvent, start: HostExecEvent) -> bool:
    def normalized_path(event: HostExecEvent, option: str) -> str | None:
        value = _argv_option(event.argv, option)
        return os.path.normpath(value) if value else None

    return (
        _argv_option(serve.argv, "--url") == _argv_option(start.argv, "--url")
        and normalized_path(serve, "--artifacts-dir")
        == normalized_path(start, "--artifacts-dir")
        and normalized_path(serve, "--session-file")
        == normalized_path(start, "--session-file")
        and _argv_option(serve.argv, "--host")
        == (_argv_option(start.argv, "--host") or "127.0.0.1")
        and _argv_option(serve.argv, "--port")
        == (_argv_option(start.argv, "--port") or "0")
        and _argv_option(serve.argv, "--viewport")
        == _argv_option(start.argv, "--viewport")
        and _argv_option(serve.argv, "--observation-mode")
        == _argv_option(start.argv, "--observation-mode")
    )


def _propagate_trust(
    roots: dict[str, int],
    parents: dict[str, str],
    spawned_at: dict[str, int],
    *,
    allowed_children: set[str] | None = None,
) -> dict[str, int]:
    trusted = dict(roots)
    changed = True
    while changed:
        changed = False
        for child, parent in parents.items():
            if allowed_children is not None and child not in allowed_children:
                continue
            transition = spawned_at.get(child)
            if (
                parent in trusted
                and transition is not None
                and transition >= trusted[parent]
                and child not in trusted
            ):
                trusted[child] = transition
                changed = True
    return trusted


def _is_descendant(pid: str, ancestor: str, parents: dict[str, str]) -> bool:
    seen: set[str] = set()
    current = pid
    while current in parents and current not in seen:
        seen.add(current)
        current = parents[current]
        if current == ancestor:
            return True
    return False


@lru_cache(maxsize=64)
def _host_trace_attribution(host_audit_path: Path) -> HostTraceAttribution:
    if not host_audit_path.is_file():
        return HostTraceAttribution(
            lines=(),
            exec_events=(),
            exec_cwds={},
            parents={},
            spawned_at={},
            thread_children=frozenset(),
            model_trust_from={},
            agent_trust_from={},
            adapter_trust_from={},
            model_pids=frozenset(),
            adapter_pids=frozenset(),
            adapter_requests=(),
            adapter_invocations=(),
            invalid_adapter_invocations=(),
            audit_errors=("missing host audit",),
            policy={},
        )
    lines = tuple(
        host_audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
    )
    policy, audit_errors = _load_audit_policy(
        host_audit_path.with_name("audit-policy.json")
    )
    if not any(line.startswith("# CUA_SWE_AUDIT_COMPLETE") for line in lines):
        audit_errors.append("host audit lacks completion sentinel")
    exec_events = _host_exec_events(lines, audit_errors)

    parents: dict[str, str] = {}
    spawned_at: dict[str, int] = {}
    thread_children: set[str] = set()
    pending: dict[tuple[str, str], tuple[int, str]] = {}
    pending_exits: dict[tuple[str, str], tuple[int, int]] = {}
    exited_at: dict[str, int] = {}
    exit_events: dict[str, list[tuple[int, int, bool]]] = {}
    for index, line in enumerate(lines):
        parent = _strace_pid(line)
        if parent == "unknown":
            continue
        body = _strace_body(line)
        unfinished_exit = re.match(
            r"(?P<syscall>exit|exit_group)\((?P<code>-?\d+)\s+"
            r"<unfinished \.\.\.>",
            body,
        )
        if unfinished_exit:
            syscall = unfinished_exit.group("syscall")
            pending_exits[(parent, syscall)] = (
                index,
                int(unfinished_exit.group("code")),
            )
            continue
        resumed_exit = re.match(
            r"<\.\.\. (?P<syscall>exit|exit_group) resumed>\)\s+=\s+\?",
            body,
        )
        if resumed_exit:
            syscall = resumed_exit.group("syscall")
            pending_exit = pending_exits.pop((parent, syscall), None)
            if pending_exit is None:
                audit_errors.append(
                    f"host audit has unmatched resumed {syscall} for PID {parent}"
                )
            else:
                _, exit_code = pending_exit
                exit_events.setdefault(parent, []).append(
                    (index, exit_code, syscall == "exit_group")
                )
                exited_at[parent] = index
            continue
        exit_match = re.match(r"(exit|exit_group)\((-?\d+)\)", body)
        if exit_match:
            exit_events.setdefault(parent, []).append(
                (index, int(exit_match.group(2)), exit_match.group(1) == "exit_group")
            )
            exited_at[parent] = index
            continue
        summary_exit = re.match(r"\+\+\+ exited with (-?\d+) \+\+\+", body)
        if summary_exit:
            exit_events.setdefault(parent, []).append(
                (index, int(summary_exit.group(1)), True)
            )
            exited_at[parent] = index
            continue
        summary_signal = re.match(
            r"\+\+\+ killed by (SIG[A-Z0-9]+)(?: \(core dumped\))? \+\+\+",
            body,
        )
        if summary_signal:
            signal_number = int(getattr(signal, summary_signal.group(1), signal.SIGKILL))
            exit_events.setdefault(parent, []).append(
                (index, 128 + signal_number, True)
            )
            exited_at[parent] = index
            continue
        if parent in exited_at and "+++ exited" not in line:
            audit_errors.append(f"PID {parent} produced events after exit")
        unfinished = re.match(
            r"(clone3?|fork|vfork)\(.*<unfinished \.\.\.>", body
        )
        if unfinished:
            pending[(parent, unfinished.group(1))] = (index, line)
            continue
        resumed = re.match(
            r"<\.\.\. (?P<syscall>clone3?|fork|vfork) resumed>.*\)\s+=\s+"
            r"(?P<child>\d+)(?:\s+/\*\s+(?P<host_child>\d+)\s+in strace's PID NS\s+\*/)?",
            body,
        )
        if resumed:
            syscall = resumed.group("syscall")
            child = resumed.group("host_child") or resumed.group("child")
            pending_call = pending.pop((parent, syscall), None)
            if pending_call is None:
                audit_errors.append(
                    f"host audit has unmatched resumed {syscall} for PID {parent}"
                )
                spawn_index = index
                call_text = line
            else:
                spawn_index, unfinished_line = pending_call
                call_text = unfinished_line + line
        else:
            completed = re.match(
                r"(?P<syscall>clone3?|fork|vfork)\(.*\)\s+=\s+"
                r"(?P<child>\d+)(?:\s+/\*\s+(?P<host_child>\d+)\s+in strace's PID NS\s+\*/)?",
                body,
            )
            if not completed:
                continue
            child = completed.group("host_child") or completed.group("child")
            spawn_index = index
            call_text = line
        if child in parents and parents[child] != parent:
            audit_errors.append(f"ambiguous or reused child PID {child}")
        parents.setdefault(child, parent)
        spawned_at.setdefault(child, spawn_index)
        if "CLONE_THREAD" in call_text:
            thread_children.add(child)

    # The harness appends its completion sentinel only after strace exits.
    # At that point an unfinished clone/fork has returned no child PID and
    # cannot affect ancestry. An unfinished exit already records its exit code;
    # strace may omit the cosmetic resumed line when cleanup terminates the
    # final thread.
    for (pid, syscall), (index, exit_code) in pending_exits.items():
        exit_events.setdefault(pid, []).append(
            (index, exit_code, syscall == "exit_group")
        )
        exited_at[pid] = index

    workspace_root = str(policy.get("workspace_root") or "")
    if not Path(workspace_root).is_absolute():
        # Version 1/2 policies predate cwd provenance. They remain readable for
        # old synthetic tests, but fresh version-3 shards always bind this root.
        workspace_root = str(Path.cwd().resolve())
    children_at: dict[int, list[str]] = {}
    for child, spawn_index in spawned_at.items():
        children_at.setdefault(spawn_index, []).append(child)
    exec_indices = {event.index for event in exec_events}
    cwd_by_pid: dict[str, str] = {}
    exec_cwds: dict[int, str] = {}
    for index, line in enumerate(lines):
        pid = _strace_pid(line)
        if pid == "unknown":
            continue
        if pid not in cwd_by_pid:
            parent = parents.get(pid)
            cwd_by_pid[pid] = cwd_by_pid.get(parent or "", workspace_root)
        if index in exec_indices:
            exec_cwds[index] = cwd_by_pid[pid]
        chdir_match = re.search(
            r'\bchdir\("((?:\\.|[^"\\])*)"\)\s+=\s+0(?:\s|$)',
            line,
        )
        if chdir_match:
            target = _strace_quoted_value(chdir_match.group(1))
            cwd_by_pid[pid] = os.path.normpath(
                target
                if Path(target).is_absolute()
                else os.path.join(cwd_by_pid[pid], target)
            )
        if policy.get("version") not in {4, 5, 6} and re.search(
            r"\bfchdir\([^)]*\)\s+=\s+0(?:\s|$)", line
        ):
            audit_errors.append(
                "host audit cannot resolve a successful fchdir working-directory change"
            )
        for child in children_at.get(index, []):
            cwd_by_pid[child] = cwd_by_pid[pid]

    for index, line in enumerate(lines):
        if "execveat(" not in line:
            continue
        event = next((item for item in exec_events if item.index == index), None)
        if event is None or (event.succeeded and not Path(event.executable).is_absolute()):
            audit_errors.append("host audit contains an unresolved execveat event")
            break

    model_roots: dict[str, int] = {}
    if policy.get("version") in {5, 6}:
        model_runtime = str(policy.get("model_runtime") or "")
        model_entry = str((policy.get("model_entry") or {}).get("path") or "")
        model_executable = str(
            (policy.get("model_executable") or {}).get("path") or ""
        )
        bootstrap_kind = str(policy.get("model_bootstrap_kind") or "python-script")
        if bootstrap_kind == "direct":
            native_bootstraps = [
                event
                for event in exec_events
                if event.succeeded
                and (
                    (
                        event.executable == model_entry
                        and bool(event.argv)
                        and event.argv[0] == model_entry
                    )
                    or (
                        Path(event.executable).name == "node"
                        and len(event.argv) > 1
                        and event.argv[1] == model_entry
                    )
                )
            ]
        else:
            native_bootstraps = [
                event
                for event in exec_events
                if event.succeeded
                and event.executable == model_executable
                and len(event.argv) > 1
                and event.argv[0] == model_executable
                and event.argv[1] == model_entry
            ]
        if len(native_bootstraps) == 1:
            bootstrap = native_bootstraps[0]
            model_roots[bootstrap.pid] = bootstrap.index
        elif not native_bootstraps:
            audit_errors.append(
                f"host audit lacks the canonical {model_runtime} adapter bootstrap"
            )
        else:
            audit_errors.append(
                f"host audit has ambiguous canonical {model_runtime} adapter bootstraps"
            )
    else:
        codex_entry = str((policy.get("codex_entry") or {}).get("path") or "")
        codex_native = str((policy.get("codex_native") or {}).get("path") or "")
        bootstrap: HostExecEvent | None = None
        if codex_entry:
            for event in exec_events:
                exact_entry = (
                    event.executable == codex_entry
                    and bool(event.argv)
                    and event.argv[0] == codex_entry
                )
                node_entry = (
                    Path(event.executable).name == "node"
                    and len(event.argv) > 1
                    and event.argv[1] == codex_entry
                )
                if event.succeeded and (exact_entry or node_entry):
                    bootstrap = event
                    break

        native_transition: HostExecEvent | None = None
        if bootstrap is not None:
            model_roots[bootstrap.pid] = bootstrap.index
            if codex_native:
                bootstrap_arguments = (
                    bootstrap.argv[2:]
                    if (
                        Path(bootstrap.executable).name == "node"
                        and len(bootstrap.argv) > 1
                        and bootstrap.argv[1] == codex_entry
                    )
                    else bootstrap.argv[1:]
                )
                native_candidates: list[HostExecEvent] = []
                for event in exec_events:
                    if (
                        event.index < bootstrap.index
                        or not event.succeeded
                        or event.executable != codex_native
                        or not event.argv
                        or event.argv[0] != codex_native
                        or event.argv[1:] != bootstrap_arguments
                    ):
                        continue
                    same_pid = event.pid == bootstrap.pid
                    direct_child = (
                        parents.get(event.pid) == bootstrap.pid
                        and event.pid not in thread_children
                        and spawned_at.get(event.pid, -1) >= bootstrap.index
                    )
                    if not (same_pid or direct_child):
                        continue
                    lower_bound = bootstrap.index if same_pid else spawned_at[event.pid]
                    intervening = [
                        prior
                        for prior in exec_events
                        if prior.pid == event.pid
                        and prior.succeeded
                        and lower_bound < prior.index < event.index
                        and not (
                            same_pid
                            and Path(prior.executable).name == "node"
                            and len(prior.argv) > 1
                            and prior.argv[1] == codex_entry
                        )
                    ]
                    if not intervening:
                        native_candidates.append(event)
                if len(native_candidates) == 1:
                    native_transition = native_candidates[0]
                    model_roots[native_transition.pid] = native_transition.index
                elif len(native_candidates) > 1:
                    audit_errors.append(
                        "host audit has ambiguous canonical native Codex transitions"
                    )
        if bootstrap is None:
            audit_errors.append("host audit lacks the canonical Codex bootstrap")
        elif policy.get("version") in {2, 3, 4}:
            required_codex_argv = tuple(policy.get("required_codex_argv") or ())
            has_required_argv = any(
                bootstrap.argv[index : index + len(required_codex_argv)]
                == required_codex_argv
                for index in range(
                    len(bootstrap.argv) - len(required_codex_argv) + 1
                )
            )
            if not required_codex_argv or not has_required_argv:
                audit_errors.append(
                    "canonical Codex bootstrap does not disable plugins"
                )
        if codex_native and native_transition is None:
            audit_errors.append("host audit lacks the canonical native Codex transition")

    model_trust_from = _propagate_trust(
        model_roots,
        parents,
        spawned_at,
        allowed_children=thread_children,
    )
    all_model_descendants = _propagate_trust(model_roots, parents, spawned_at)
    agent_trust_from = {
        pid: transition
        for pid, transition in all_model_descendants.items()
        if pid not in model_roots
    }

    def is_agent_event(event: HostExecEvent) -> bool:
        model_from = model_trust_from.get(event.pid)
        if model_from is not None and event.index >= model_from:
            return False
        agent_from = agent_trust_from.get(event.pid)
        return agent_from is not None and event.index >= agent_from

    def exit_code_after(pid: str, index: int) -> int | None:
        group_exits = [
            (event_index, code)
            for event_index, code, is_group in exit_events.get(pid, [])
            if is_group and event_index > index
        ]
        if group_exits:
            return min(group_exits)[1]
        ordinary = [
            (event_index, code)
            for event_index, code, _is_group in exit_events.get(pid, [])
            if event_index > index
        ]
        return min(ordinary)[1] if ordinary else None

    adapter_roots: dict[str, int] = {}
    adapter_requests: list[tuple[str, str, int, tuple[str, ...]]] = []
    adapter_invocations: list[tuple[str, str]] = []
    invalid_adapter_invocations: list[str] = []
    public_invocations: list[tuple[HostExecEvent, HostExecEvent, str]] = []
    adapter_tool = str((policy.get("adapter_tool") or {}).get("path") or "")
    adapter_python = str((policy.get("adapter_python") or {}).get("path") or "")
    adapter_launcher = str((policy.get("adapter_launcher") or {}).get("path") or "")
    recognized_tool_exec_indices: set[int] = set()
    if policy.get("condition") == "cua" and adapter_tool and adapter_python and adapter_launcher:
        for event in exec_events:
            if event.executable != adapter_launcher:
                continue
            verb = _validated_public_adapter_invocation(event, policy)
            if verb is None or not event.succeeded:
                invalid_adapter_invocations.append(event.raw)
                continue
            if policy.get("version") in {4, 5, 6}:
                expected_python_argv = (
                    adapter_python,
                    "-I",
                    adapter_tool,
                    "--socket",
                    str(policy.get("broker_socket") or ""),
                    "--token",
                    str(policy.get("broker_token") or ""),
                    "--",
                    *event.argv[1:],
                )
            else:
                expected_python_argv = (
                    adapter_python,
                    "-I",
                    adapter_tool,
                    *event.argv[1:],
                )
            next_exec = next(
                (
                    candidate
                    for candidate in exec_events
                    if candidate.pid == event.pid and candidate.index > event.index
                ),
                None,
            )
            if (
                next_exec is None
                or not next_exec.succeeded
                or next_exec.executable != adapter_python
                or next_exec.argv != expected_python_argv
            ):
                invalid_adapter_invocations.append(event.raw)
                continue
            python_event = next_exec
            recognized_tool_exec_indices.add(python_event.index)
            if not is_agent_event(event):
                # The benchmark-owned CUA wrapper runs exact, source-digest-bound
                # stop calls from its EXIT trap after the model has terminated.
                # They cannot provide visual feedback and are not agent actions.
                if verb != "stop":
                    invalid_adapter_invocations.append(event.raw)
                continue
            intervening = [
                candidate
                for candidate in exec_events
                if candidate.pid == event.pid
                and candidate.succeeded
                and event.index < candidate.index < python_event.index
            ]
            if intervening:
                invalid_adapter_invocations.append(event.raw)
                continue
            adapter_roots[event.pid] = event.index
            public_invocations.append((event, python_event, verb))

    adapter_trust_from = _propagate_trust(adapter_roots, parents, spawned_at)
    start_serves: dict[int, HostExecEvent] = {}
    for start_event, _python_event, verb in public_invocations:
        if policy.get("version") in {4, 5, 6}:
            continue
        if verb != "start":
            continue
        serve_events = [
            event
            for event in exec_events
            if parents.get(event.pid) == start_event.pid
            and spawned_at.get(event.pid, -1) >= start_event.index
            and event.index >= spawned_at.get(event.pid, event.index)
            and event.succeeded
            and _validated_internal_serve(event, policy)
            and _serve_matches_start(event, start_event)
        ]
        if len(serve_events) == 1:
            start_serves[start_event.index] = serve_events[0]
            recognized_tool_exec_indices.add(serve_events[0].index)
        elif len(serve_events) > 1:
            invalid_adapter_invocations.extend(event.raw for event in serve_events[1:])

    for event in exec_events:
        if (
            adapter_tool
            and adapter_tool in event.argv
            and event.index not in recognized_tool_exec_indices
        ):
            invalid_adapter_invocations.append(event.raw)

    allowed_adapter_executables = {
        adapter_launcher,
        adapter_python,
        *(
            str(record.get("path") or "")
            for record in policy.get("adapter_descendant_executables") or []
            if isinstance(record, dict)
        ),
    }

    def inherited_executable(pid: str, before_index: int, seen: set[str] | None = None) -> str | None:
        lineage = set(seen or ())
        if pid in lineage:
            return None
        lineage.add(pid)
        prior = [
            event
            for event in exec_events
            if event.pid == pid and event.succeeded and event.index < before_index
        ]
        for event in reversed(prior):
            if event.executable != "/proc/self/exe":
                return event.executable
        parent = parents.get(pid)
        transition = spawned_at.get(pid)
        if parent is None or transition is None or transition >= before_index:
            return None
        return inherited_executable(parent, transition, lineage)

    for event in exec_events:
        adapter_from = adapter_trust_from.get(event.pid)
        proc_self_alias = (
            event.executable == "/proc/self/exe"
            and inherited_executable(event.pid, event.index)
            in allowed_adapter_executables
        )
        if (
            event.succeeded
            and adapter_from is not None
            and event.index >= adapter_from
            and event.executable not in allowed_adapter_executables
            and not proc_self_alias
        ):
            audit_errors.append(
                f"unrecognized executable in trusted CUA subtree: {event.executable}"
            )

    successful_starts: dict[str, HostExecEvent] = {}
    driver_paths = {
        path
        for path in allowed_adapter_executables
        if path and Path(path).name == "node" and "playwright" in Path(path).parts
    }
    browser_paths = {
        path
        for path in allowed_adapter_executables
        if path
        and Path(path).name
        in {"chrome", "google-chrome", "chrome-headless-shell"}
    }
    for public_event, python_event, verb in public_invocations:
        invocation_exit = exit_code_after(public_event.pid, python_event.index)
        if invocation_exit is None:
            audit_errors.append("CUA client invocation lacks an exit status")
            continue
        adapter_requests.append(
            (public_event.pid, verb, invocation_exit, public_event.argv[1:])
        )
        if verb == "help":
            if invocation_exit != 126:
                audit_errors.append("CUA launcher help probe was not safely rejected")
            continue
        if invocation_exit != 0:
            # A well-formed, provenance-matched CUA request remains authorized
            # when the adapter reports a recoverable operation failure. Only
            # successful calls contribute positive browser-use evidence.
            continue
        if verb == "start":
            if policy.get("version") in {4, 5, 6}:
                session = _argv_option(public_event.argv, "--session-file")
                if session:
                    successful_starts[os.path.normpath(session)] = public_event
                    adapter_invocations.append((public_event.pid, "start"))
                continue
            serve = start_serves.get(public_event.index)
            if serve is None:
                continue
            serve_trust = _propagate_trust(
                {serve.pid: serve.index}, parents, spawned_at
            )
            serve_execs = {
                event.executable
                for event in exec_events
                if event.succeeded
                and event.pid in serve_trust
                and event.index >= serve_trust[event.pid]
            }
            if not (serve_execs & driver_paths and serve_execs & browser_paths):
                continue
            session = _argv_option(public_event.argv, "--session-file")
            if session:
                successful_starts[os.path.normpath(session)] = public_event
                adapter_invocations.append((public_event.pid, "start"))
        elif verb in {"observe", "act"}:
            session = _argv_option(public_event.argv, "--session-file")
            if session and os.path.normpath(session) in successful_starts:
                adapter_invocations.append((public_event.pid, verb))
        elif verb == "stop":
            adapter_invocations.append((public_event.pid, verb))

    known_pids = {
        *(event.pid for event in exec_events),
        *parents.keys(),
        *parents.values(),
    }
    for line in lines:
        if not any(
            syscall in line
            for syscall in ("connect(", "sendto(", "sendmsg(", "sendmmsg(")
        ):
            continue
        pid = _strace_pid(line)
        if pid == "unknown" or pid not in known_pids:
            audit_errors.append(f"network event has unknown process provenance: {pid}")
            break
    return HostTraceAttribution(
        lines=lines,
        exec_events=exec_events,
        exec_cwds=exec_cwds,
        parents=parents,
        spawned_at=spawned_at,
        thread_children=frozenset(thread_children),
        model_trust_from=model_trust_from,
        agent_trust_from=agent_trust_from,
        adapter_trust_from=adapter_trust_from,
        model_pids=frozenset(model_trust_from),
        adapter_pids=frozenset(adapter_trust_from),
        adapter_requests=tuple(adapter_requests),
        adapter_invocations=tuple(adapter_invocations),
        invalid_adapter_invocations=tuple(dict.fromkeys(invalid_adapter_invocations)),
        audit_errors=tuple(dict.fromkeys(audit_errors)),
        policy=policy,
    )


def _tool_commands(rollout_dir: Path, host_audit_path: Path) -> list[str]:
    commands: list[str] = []
    for trajectory in rollout_dir.glob("*trajectory.jsonl"):
        for line in trajectory.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != "tool":
                continue
            name = str(event.get("name") or "")
            arguments = event.get("arguments") or {}
            if name == "shell":
                commands.append(str(arguments.get("command") or ""))
            elif name == "view_image":
                commands.append(f"VIEW_IMAGE {arguments}")
    stdout_path = rollout_dir / "agent_stdout.txt"
    if stdout_path.is_file():
        for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if not isinstance(item, dict):
                item = event if isinstance(event, dict) else {}
            item_type = str(item.get("type") or event.get("type") or "")
            if item_type in {"command_execution", "shell", "shell_command"}:
                command = item.get("command") or item.get("cmd")
                if command:
                    commands.append(str(command))
            if item_type in {"image_view", "view_image"}:
                commands.append(f"VIEW_IMAGE {item}")
    stderr_path = rollout_dir / "agent_stderr.txt"
    if stderr_path.exists():
        for line in stderr_path.read_text(encoding="utf-8", errors="replace").splitlines():
            shell_match = re.search(r"/(?:usr/)?bin/(?:ba|z|)sh -lc (.+?)(?: in /|$)", line)
            if shell_match:
                commands.append(shell_match.group(1))
            elif line.strip().startswith("view_image"):
                commands.append(f"VIEW_IMAGE {line}")
    trace = _host_trace_attribution(host_audit_path)
    for event in trace.exec_events:
        model_from = trace.model_trust_from.get(event.pid)
        if model_from is not None and event.index >= model_from:
            continue
        adapter_from = trace.adapter_trust_from.get(event.pid)
        if adapter_from is not None and event.index >= adapter_from:
            continue
        agent_from = trace.agent_trust_from.get(event.pid)
        if agent_from is None or event.index < agent_from:
            continue
        commands.append(event.raw)
    return commands


TEST_RUN_COMMAND = re.compile(
    r"(?i)(?:^|\s|&&|;|\|)"
    r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:build|test|check|lint|typecheck|verify)\b|"
    r"(?:^|\s|&&|;|\|)(?:pytest|vitest|jest|playwright\s+test|cargo\s+test|go\s+test)\b"
)


def _agent_usage_counts(rollout_dir: Path) -> dict[str, int]:
    """Read provider-neutral counts from the durable structured rollout."""
    stdout_path = rollout_dir / "agent_stdout.txt"
    completed_items: set[str] = set()
    fallback_steps = 0
    reported_steps = 0
    usage: dict[str, int] = {}
    stdout_lines = (
        stdout_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if stdout_path.is_file()
        else []
    )
    for line in stdout_lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict):
            item_id = str(item.get("id") or "")
            if item_id:
                completed_items.add(item_id)
            else:
                fallback_steps += 1
        elif event.get("event") == "assistant" or event.get("type") == "assistant":
            fallback_steps += 1
        raw_usage = event.get("usage")
        if event.get("type") == "turn.completed" and isinstance(raw_usage, dict):
            usage = {
                key: int(raw_usage.get(key) or 0)
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                )
            }
        elif event.get("type") == "result" and isinstance(raw_usage, dict):
            cache_creation = int(raw_usage.get("cache_creation_input_tokens") or 0)
            cache_read = int(raw_usage.get("cache_read_input_tokens") or 0)
            uncached_input = int(raw_usage.get("input_tokens") or 0)
            usage = {
                "input_tokens": uncached_input + cache_creation + cache_read,
                "cached_input_tokens": cache_read,
                "output_tokens": int(raw_usage.get("output_tokens") or 0),
            }
            reported_steps = max(reported_steps, int(event.get("num_turns") or 0))
    if not completed_items and fallback_steps == 0:
        trajectory_usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
        }
        trajectory_steps = 0
        for trajectory in rollout_dir.glob("*agent-trajectory.jsonl"):
            for line in trajectory.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("event") != "assistant":
                    continue
                trajectory_steps += 1
                raw_usage = event.get("usage")
                if not isinstance(raw_usage, dict):
                    continue
                input_tokens = int(raw_usage.get("input_tokens") or 0)
                output_tokens = int(raw_usage.get("output_tokens") or 0)
                input_details = raw_usage.get("input_tokens_details")
                cached_tokens = int(
                    raw_usage.get("cache_read_input_tokens")
                    or (
                        input_details.get("cached_tokens")
                        if isinstance(input_details, dict)
                        else 0
                    )
                    or 0
                )
                trajectory_usage["input_tokens"] += input_tokens
                trajectory_usage["cached_input_tokens"] += min(
                    input_tokens, cached_tokens
                )
                trajectory_usage["output_tokens"] += output_tokens
        if trajectory_steps:
            fallback_steps = trajectory_steps
            usage = trajectory_usage
    input_tokens = usage.get("input_tokens", 0)
    cached_input_tokens = min(input_tokens, usage.get("cached_input_tokens", 0))
    output_tokens = usage.get("output_tokens", 0)
    return {
        "model_steps": len(completed_items) + max(fallback_steps, reported_steps),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "noncached_tokens": input_tokens - cached_input_tokens + output_tokens,
    }


def _budget_attestation(
    task: TaskBundle,
    rollout_dir: Path,
    host_audit_path: Path,
    *,
    agent_duration_sec: float,
    max_agent_tokens: int,
    cua_evidence: dict[str, Any],
) -> dict[str, Any]:
    usage = _agent_usage_counts(rollout_dir)
    test_runs = sum(
        1
        for command in _tool_commands(rollout_dir, host_audit_path)
        if TEST_RUN_COMMAND.search(command.splitlines()[0] if command else "")
    )
    observed = {
        "wall_time_sec": agent_duration_sec,
        "model_steps": usage["model_steps"],
        "gui_actions": int(cua_evidence.get("host_audited_actions", 0)),
        "test_runs": test_runs,
        "noncached_tokens": usage["noncached_tokens"],
        "token_usage": usage,
    }
    limits = {
        "wall_time_sec": task.budgets.wall_time_sec,
        "model_steps": task.budgets.max_steps,
        "gui_actions": task.budgets.max_gui_actions,
        "test_runs": task.budgets.max_test_runs,
        "noncached_tokens": max_agent_tokens,
    }
    exceeded = [
        name
        for name in ("wall_time_sec", "model_steps", "gui_actions", "test_runs", "noncached_tokens")
        if observed[name] > limits[name]
    ]
    return {
        "limits": limits,
        "observed": observed,
        "exceeded": exceeded,
        # Resource overruns are operational diagnostics, not treatment
        # contamination.  The wall clock is already enforced by the process
        # timeout; post-run step/action/test/token counts must not turn a
        # capability outcome into a protocol error.
        "compliant": True,
        "diagnostic_only": True,
        "enforcement": "hard_wall_timeout_with_post_run_budget_diagnostics",
    }


def _agent_exec_events(trace: HostTraceAttribution) -> list[HostExecEvent]:
    events: list[HostExecEvent] = []
    for event in trace.exec_events:
        model_from = trace.model_trust_from.get(event.pid)
        if model_from is not None and event.index >= model_from:
            continue
        adapter_from = trace.adapter_trust_from.get(event.pid)
        if adapter_from is not None and event.index >= adapter_from:
            continue
        agent_from = trace.agent_trust_from.get(event.pid)
        if agent_from is not None and event.index >= agent_from:
            events.append(event)
    return events


def _shell_command_payload(event: HostExecEvent) -> str | None:
    if Path(event.executable).name not in {"bash", "dash", "sh", "zsh"}:
        return None
    for index, argument in enumerate(event.argv[1:], start=1):
        if argument.startswith("-") and "c" in argument[1:] and index + 1 < len(event.argv):
            return event.argv[index + 1]
    return None


def _env_command_argv(event: HostExecEvent) -> tuple[str, ...] | None:
    if Path(event.executable).name != "env":
        return None
    index = 1
    while index < len(event.argv):
        argument = event.argv[index]
        if argument in {"-u", "--unset"}:
            index += 2
            continue
        if argument.startswith("-") or ("=" in argument and not argument.startswith("=")):
            index += 1
            continue
        return event.argv[index:]
    return None


def _argv_invokes_nested_model(
    executable: str,
    argv: tuple[str, ...],
    policy: dict[str, Any],
) -> bool:
    if not argv:
        return False
    codex_paths = {
        str((policy.get("codex_entry") or {}).get("path") or ""),
        str((policy.get("codex_native") or {}).get("path") or ""),
    }
    codex_paths.discard("")
    name = Path(executable).name.lower()
    arguments = argv[1:]
    if executable in codex_paths or name in {"codex", "codex.js"}:
        return "exec" in arguments
    if name in {"node", "nodejs"} and len(argv) > 1:
        entry = argv[1]
        if entry in codex_paths or Path(entry).name.lower() == "codex.js":
            return "exec" in argv[2:]
    if name == "claude":
        return "--print" in arguments or "-p" in arguments
    return False


def _event_invokes_nested_model(
    event: HostExecEvent,
    policy: dict[str, Any],
) -> bool:
    if _argv_invokes_nested_model(event.executable, event.argv, policy):
        return True
    env_argv = _env_command_argv(event)
    if env_argv and _argv_invokes_nested_model(env_argv[0], env_argv, policy):
        return True
    payload = _shell_command_payload(event)
    return bool(
        payload
        and (
            SHELL_CODEX_NESTED.search(payload)
            or SHELL_CLAUDE_NESTED.search(payload)
        )
    )


def _nested_model_invocations(
    events: list[HostExecEvent],
    policy: dict[str, Any],
) -> list[str]:
    return [
        event.raw
        for event in events
        if event.succeeded and _event_invokes_nested_model(event, policy)
    ]


def _invocation_tool(event: HostExecEvent) -> tuple[str, tuple[str, ...]]:
    """Return the command tool and its arguments without treating search text as code."""
    executable = Path(event.executable).name.lower()
    argv = event.argv or (event.executable,)
    first = Path(argv[0]).name.lower()
    if executable in {"node", "nodejs"} and len(argv) > 1:
        script = Path(argv[1]).name.lower()
        if script in {"npm", "npm-cli.js", "npx", "npx-cli.js"}:
            return ("npx" if script.startswith("npx") else "npm", argv[2:])
        if script in {"pnpm", "pnpm.cjs", "yarn", "yarn.js"}:
            return (script.split(".", 1)[0], argv[2:])
        if script in {"vite", "vite.js", "next", "next.js"}:
            return (script.split(".", 1)[0], argv[2:])
        return (executable, argv[1:])
    return (first or executable, argv[1:])


def _is_dynamic_loader_name(value: str) -> bool:
    name = Path(value).name.lower()
    return (
        name.startswith("ld-linux")
        or name.startswith("ld-musl")
        or name in DYNAMIC_LOADER_NAMES
    )


def _dynamic_loader_target(event: HostExecEvent, *, is_loader: bool) -> str | None:
    if not is_loader:
        return None
    arguments = list(event.argv[1:])
    index = 0
    options_with_value = {
        "--argv0",
        "--audit",
        "--glibc-hwcaps-mask",
        "--glibc-hwcaps-prepend",
        "--inhibit-rpath",
        "--library-path",
        "--preload",
    }
    while index < len(arguments):
        argument = arguments[index]
        if argument in options_with_value:
            index += 2
            continue
        if argument.startswith("-"):
            index += 1
            continue
        return argument
    return None


def _python_or_node_execution_target(
    tool: str,
    arguments: tuple[str, ...],
) -> str | None:
    if tool in {"node", "nodejs"}:
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument in {"-e", "--eval", "-p", "--print"}:
                return None
            if argument in {"-r", "--require", "--import"}:
                index += 2
                continue
            if argument.startswith("-"):
                index += 1
                continue
            return argument
        return None
    if tool in {"python", "python3"} or tool.startswith("python3."):
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument in {"-c", "-"}:
                return None
            if argument == "-m":
                return arguments[index + 1] if index + 1 < len(arguments) else None
            if argument in {"-W", "-X"}:
                index += 2
                continue
            if argument.startswith("-"):
                index += 1
                continue
            return argument
    return None


def _protected_browser_digests(policy: dict[str, Any]) -> frozenset[str]:
    if policy.get("version") in {4, 5, 6}:
        # Browser executables exist only in the host broker's namespace. The
        # agent-side audit relies on broker request provenance, not mutable
        # workspace pathname hashing.
        return frozenset()
    adapter_entries = (policy.get("adapter_launcher"), policy.get("adapter_tool"))
    records: list[Any] = list(policy.get("adapter_descendant_executables") or [])
    records.extend(adapter_entries)
    digests: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        path = str(record.get("path") or "")
        name = Path(path).name.lower()
        is_browser = name in BROWSER_EXECUTABLE_NAMES
        is_adapter_entry = any(record is entry for entry in adapter_entries)
        digest = str(record.get("sha256") or "")
        if (is_browser or is_adapter_entry) and re.fullmatch(r"[0-9a-f]{64}", digest):
            digests.add(digest)
    return frozenset(digests)


def _protected_loader_digests(policy: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        str(record.get("sha256"))
        for record in policy.get("dynamic_loaders") or []
        if isinstance(record, dict)
        and re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256") or ""))
    )


def _resolve_traced_path(value: str, cwd: str) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    return os.path.normpath(str(candidate))


def _digest_for_path(
    value: str,
    digest_cache: dict[str, str | None],
) -> str | None:
    normalized = os.path.normpath(value)
    if normalized not in digest_cache:
        candidate = Path(normalized)
        try:
            digest_cache[normalized] = (
                _sha256_file(candidate.resolve()) if candidate.is_file() else None
            )
        except OSError:
            digest_cache[normalized] = None
    return digest_cache[normalized]


def _matches_protected_digest(
    value: str,
    protected_digests: frozenset[str],
    digest_cache: dict[str, str | None],
) -> bool:
    return bool(protected_digests) and _digest_for_path(value, digest_cache) in protected_digests


def _browser_or_image_exec(
    event: HostExecEvent,
    *,
    cwd: str = "/",
    protected_digests: frozenset[str] = frozenset(),
    loader_digests: frozenset[str] = frozenset(),
    digest_cache: dict[str, str | None] | None = None,
) -> bool:
    tool, arguments = _invocation_tool(event)
    executable_name = Path(event.executable).name.lower()
    cache = digest_cache if digest_cache is not None else {}
    executable_path = _resolve_traced_path(event.executable, cwd)
    is_loader = _is_dynamic_loader_name(event.executable) or _matches_protected_digest(
        executable_path,
        loader_digests,
        cache,
    )
    loader_target = _dynamic_loader_target(event, is_loader=is_loader)
    loader_target_path = (
        _resolve_traced_path(loader_target, cwd) if loader_target else None
    )
    target_name = Path(loader_target).name.lower() if loader_target else ""
    if (
        tool in BROWSER_EXECUTABLE_NAMES
        or executable_name in BROWSER_EXECUTABLE_NAMES
        or target_name in BROWSER_EXECUTABLE_NAMES
    ):
        return True
    if "browser-devtools" in tool or "browser_devtools" in tool:
        return True
    execution_target = _python_or_node_execution_target(tool, arguments)
    if execution_target and BROWSER_INVOCATION.search(execution_target):
        return True
    if tool == "npx" and arguments and BROWSER_INVOCATION.search(arguments[0]):
        return True
    if tool in {"npm", "pnpm", "yarn"} and arguments:
        command_index = 1 if arguments[0].lower() in {"exec", "dlx"} else -1
        if command_index >= 0 and len(arguments) > command_index:
            if BROWSER_INVOCATION.search(arguments[command_index]):
                return True
    execution_target_path = (
        _resolve_traced_path(execution_target, cwd) if execution_target else None
    )
    if _matches_protected_digest(executable_path, protected_digests, cache):
        return True
    if execution_target_path and _matches_protected_digest(
        execution_target_path,
        protected_digests,
        cache,
    ):
        return True
    if loader_target_path and _matches_protected_digest(
        loader_target_path,
        protected_digests,
        cache,
    ):
        return True
    # A successful executable that disappears before protected post-run audit
    # cannot be proven distinct from a copied browser/loader. Fail closed for
    # CUA trials; stable virtual proc aliases are attributed by ancestry above.
    if protected_digests and event.succeeded:
        stable_virtual = event.executable.startswith(("/proc/", "/dev/fd/"))
        if not stable_virtual and _digest_for_path(executable_path, cache) is None:
            return True
        if loader_target_path and _digest_for_path(loader_target_path, cache) is None:
            return True
    if is_loader and loader_target is None and protected_digests:
        # A protected/renamed loader invocation with no auditable target is not
        # a permitted direct browser path.
        return True
    return False


def _server_or_preview_exec(event: HostExecEvent) -> bool:
    tool, arguments = _invocation_tool(event)
    lowered = tuple(argument.lower() for argument in arguments)
    if tool in {"npm", "pnpm", "yarn"}:
        if not lowered:
            return False
        verb_index = 1 if lowered[0] == "run" else 0
        return len(lowered) > verb_index and lowered[verb_index] in {
            "dev",
            "preview",
            "start",
        }
    if tool == "next":
        return bool(lowered) and lowered[0] in {"dev", "start"}
    if tool == "vite":
        return not lowered or lowered[0] in {"dev", "preview"} or "--host" in lowered
    return False


def _local_http_exec(event: HostExecEvent) -> bool:
    tool, arguments = _invocation_tool(event)
    return tool in {"curl", "wget"} and any(
        LOOPBACK_URL.search(argument) for argument in arguments
    )


def _external_network_exec(event: HostExecEvent) -> bool:
    """Classify the executed program, never prose embedded in shell heredocs."""
    tool, arguments = _invocation_tool(event)
    lowered = tuple(argument.lower() for argument in arguments)
    if tool in {"curl", "wget"}:
        return any(
            re.search(r"https?://", argument, re.IGNORECASE)
            and not LOOPBACK_URL.search(argument)
            for argument in arguments
        )
    if tool == "git":
        return bool(lowered) and (
            lowered[0] in {"clone", "fetch", "pull", "ls-remote"}
            or lowered[:2] == ("submodule", "update")
        )
    if tool in {"gh", "ssh", "scp", "sftp"}:
        return True
    if tool in {"codex", "codex.js"}:
        return "--search" in lowered
    if tool in {"npm", "pnpm", "yarn"}:
        return bool(lowered) and lowered[0] in {
            "install",
            "add",
            "update",
            "upgrade",
        }
    if tool in {"pip", "pip3"}:
        return bool(lowered) and lowered[0] in {"install", "download"}
    if tool.startswith("python") and lowered[:2] == ("-m", "pip"):
        return len(lowered) > 2 and lowered[2] in {"install", "download"}
    if tool == "uv" and lowered[:2] == ("pip", "install"):
        return True
    return False


def _network_audit(host_audit_path: Path) -> dict[str, Any]:
    if not host_audit_path.is_file():
        return {
            "loopback_connections": 0,
            "model_transport_connections": 0,
            "unauthorized_external_connections": ["missing host audit"],
        }
    trace = _host_trace_attribution(host_audit_path)
    loopback = 0
    model_transport = 0
    unauthorized: list[str] = []
    for index, line in enumerate(trace.lines):
        if (
            not any(
                syscall in line
                for syscall in ("connect(", "sendto(", "sendmsg(", "sendmmsg(")
            )
            or "sa_family=AF_INET" not in line
        ):
            continue
        result_match = re.search(r"\)\s+=\s+(-?\d+)(?:\s+([A-Z]+))?", line)
        if result_match is None:
            continue
        result = int(result_match.group(1))
        error_name = result_match.group(2)
        if result < 0 and error_name != "EINPROGRESS":
            continue
        address_match = re.search(r'inet_addr\("([^"]+)"\)', line)
        if not address_match:
            address_match = re.search(
                r'inet_pton\(AF_INET6,\s*"([^"]+)"', line
            )
        address = address_match.group(1) if address_match else "unparsed"
        port_match = re.search(r"sin6?_port=htons\((\d+)\)", line)
        # getaddrinfo performs UDP "connect" calls to port 0 only to select a
        # route/source address. They do not transmit application traffic.
        if port_match and int(port_match.group(1)) == 0:
            continue
        is_loopback = (
            address.startswith("127.")
            or address == "::1"
            or address.lower().startswith("::ffff:127.")
        )
        if is_loopback:
            loopback += 1
        else:
            model_from = trace.model_trust_from.get(_strace_pid(line))
            if model_from is not None and index >= model_from:
                model_transport += 1
            else:
                unauthorized.append(line)
    return {
        "loopback_connections": loopback,
        "model_transport_connections": model_transport,
        "unauthorized_external_connections": unauthorized,
    }


def _broker_audit_file(trace: HostTraceAttribution, host_audit_path: Path) -> Path:
    recorded = str(trace.policy.get("broker_audit_path") or "")
    audit_path = Path(recorded) if recorded else Path("/__missing_broker_audit__")
    if not audit_path.is_file():
        audit_path = host_audit_path.with_name(audit_path.name)
    return audit_path


def _successful_broker_records(
    trace: HostTraceAttribution,
    host_audit_path: Path,
) -> list[dict[str, Any]]:
    if trace.policy.get("condition") != "cua" or trace.policy.get("version") not in {4, 5, 6}:
        return []
    audit_path = _broker_audit_file(trace, host_audit_path)
    if not audit_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in audit_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("exit_code") != 0:
            continue
        argv = record.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            continue
        verb = _validated_adapter_arguments(tuple(argv), 0, trace.policy)
        if verb in {"start", "observe", "act", "stop"} and record.get("verb") == verb:
            records.append(record)
    return records


def _cua_evidence(
    rollout_dir: Path,
    host_audit_path: Path,
    observation_mode: str = "structured",
) -> dict[str, Any]:
    trace = _host_trace_attribution(host_audit_path)
    recorded_state_root = str(trace.policy.get("broker_state_root") or "")
    if recorded_state_root:
        state_root = Path(recorded_state_root)
        if not state_root.is_dir():
            state_root = host_audit_path.parent / state_root.name
        trajectories = list(state_root.glob("*/artifacts/trajectory.jsonl"))
    else:
        trajectories = list(rollout_dir.glob("cua-*/trajectory.jsonl"))
    observations = 0
    actions = 0
    for trajectory in trajectories:
        for line in trajectory.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "observe":
                observations += 1
            elif event.get("event") == "act":
                actions += 1
    if trace.policy.get("version") in {4, 5, 6}:
        successful_broker_records = _successful_broker_records(trace, host_audit_path)
        verbs = [str(record["verb"]) for record in successful_broker_records]
    else:
        successful_broker_records = []
        verbs = [verb for _pid, verb in trace.adapter_invocations]
    host_observations = verbs.count("observe")
    host_actions = verbs.count("act")
    host_starts = verbs.count("start")
    screenshot_paths = sorted(
        {
            str(item.get("path"))
            for record in successful_broker_records
            for item in (record.get("files") or [])
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and str(item.get("path")).lower().endswith(".png")
        }
    )
    image_view_calls = [
        command
        for command in _tool_commands(rollout_dir, host_audit_path)
        if command.startswith("VIEW_IMAGE ")
    ]
    matched_image_view_calls = [
        command
        for command in image_view_calls
        if any(path in command or Path(path).name in command for path in screenshot_paths)
    ]
    visual_grounded = bool(screenshot_paths and matched_image_view_calls)
    if observation_mode == "visual":
        raw_evidenced = bool(
            trajectories
            and observations > 0
            and host_observations > 0
        )
    else:
        raw_evidenced = bool(
            trajectories
            and observations > 0
            and actions > 0
            and host_starts > 0
            and host_observations > 0
            and host_actions > 0
        )
    return {
        "trajectory_count": len(trajectories),
        "observations": observations,
        "actions": actions,
        "host_audited_starts": host_starts,
        "host_audited_observations": host_observations,
        "host_audited_actions": host_actions,
        "successful_broker_requests": len(successful_broker_records),
        "observation_mode": observation_mode,
        "screenshot_attachments": screenshot_paths,
        "image_view_calls": image_view_calls,
        "matched_image_view_calls": matched_image_view_calls,
        "raw_gui_evidenced": raw_evidenced,
        "visual_grounded": visual_grounded,
        "evidenced": bool(
            raw_evidenced
            and (observation_mode != "visual" or visual_grounded)
        ),
    }


def _broker_audit_findings(
    trace: HostTraceAttribution,
    host_audit_path: Path,
) -> tuple[list[str], list[str]]:
    if trace.policy.get("condition") != "cua" or trace.policy.get("version") not in {4, 5, 6}:
        return [], []
    audit_path = _broker_audit_file(trace, host_audit_path)
    if not audit_path.is_file():
        return ["missing host-owned CUA broker audit"], []
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    violations: list[str] = []
    for expected_sequence, line in enumerate(
        audit_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            errors.append("CUA broker audit contains invalid JSON")
            continue
        if not isinstance(record, dict) or record.get("sequence") != expected_sequence:
            errors.append("CUA broker audit sequence is not contiguous")
            continue
        argv = record.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            errors.append("CUA broker audit contains invalid argv")
            continue
        verb = _validated_adapter_arguments(tuple(argv), 0, trace.policy)
        if (
            argv == ["--help"]
            and record.get("verb") == "invalid"
            and record.get("exit_code") == 126
        ):
            verb = "help"
        if verb not in {"start", "observe", "act", "stop", "help"} or (
            verb != "help" and record.get("verb") != verb
        ):
            violations.append(json.dumps(record, sort_keys=True))
            continue
        if not isinstance(record.get("peer_pid"), int) or not isinstance(
            record.get("exit_code"), int
        ):
            errors.append("CUA broker audit lacks process or exit provenance")
            continue
        records.append(record)
    trace_requests = Counter(trace.adapter_requests)
    broker_requests = Counter(
        (
            str(record["peer_pid"]),
            (
                "help"
                if record["argv"] == ["--help"]
                and record["verb"] == "invalid"
                and record["exit_code"] == 126
                else str(record["verb"])
            ),
            int(record["exit_code"]),
            tuple(record["argv"]),
        )
        for record in records
        if record["verb"] in {"start", "observe", "act", "stop"}
        or (
            record["argv"] == ["--help"]
            and record["verb"] == "invalid"
            and record["exit_code"] == 126
        )
    )
    trace_requests = _normalize_timeout_adapter_requests(
        trace_requests,
        broker_requests,
    )
    if trace_requests != broker_requests:
        unmatched = broker_requests - trace_requests
        missing = trace_requests - broker_requests
        violations.append(
            "host trace and CUA broker request provenance differ: "
            f"unmatched={dict(unmatched)}, missing={dict(missing)}"
        )
    return list(dict.fromkeys(errors)), list(dict.fromkeys(violations))


def _normalize_timeout_adapter_requests(
    trace_requests: Counter[tuple[str, str, int, tuple[str, ...]]],
    broker_requests: Counter[tuple[str, str, int, tuple[str, ...]]],
) -> Counter[tuple[str, str, int, tuple[str, ...]]]:
    normalized = trace_requests.copy()
    timeout_exit_codes = {
        120,  # Python reports a broken stdout pipe after the broker completed.
        128 + int(signal.SIGTERM),
        128 + int(signal.SIGKILL),
    }
    for broker_request, broker_count in broker_requests.items():
        peer_pid, verb, broker_exit, argv = broker_request
        if broker_exit != 0:
            continue
        remaining = broker_count - normalized[broker_request]
        if remaining <= 0:
            continue
        candidates = [
            request
            for request, count in normalized.items()
            if count > 0
            and request[0] == peer_pid
            and request[1] == verb
            and request[2] in timeout_exit_codes
            and request[3] == argv
        ]
        for candidate in candidates:
            shifted = min(remaining, normalized[candidate])
            normalized[candidate] -= shifted
            if normalized[candidate] == 0:
                del normalized[candidate]
            normalized[broker_request] += shifted
            remaining -= shifted
            if remaining == 0:
                break
    return normalized


def _broker_network_findings(
    trace: HostTraceAttribution,
    host_audit_path: Path,
) -> tuple[list[str], list[str], dict[str, Any]]:
    empty = {
        "audited_connections": 0,
        "allowed_loopback_connections": 0,
        "allowed_loopback_ports": [],
        "unauthorized_connections": [],
    }
    if trace.policy.get("condition") != "cua" or trace.policy.get("version") not in {4, 5, 6}:
        return [], [], empty
    recorded = str(trace.policy.get("broker_network_audit_path") or "")
    audit_path = Path(recorded) if recorded else Path("/__missing_broker_network_audit__")
    if not audit_path.is_file():
        audit_path = host_audit_path.with_name(audit_path.name)
    if not audit_path.is_file():
        return ["missing host-owned broker network audit"], [], empty
    lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
    errors: list[str] = []
    if not lines or lines[-1] != "# CUA_SWE_BROKER_AUDIT_COMPLETE":
        errors.append("broker network audit lacks completion sentinel")
    if not any("execve(" in line for line in lines):
        errors.append("broker network audit lacks broker process provenance")
    allowed_ports = {int(trace.policy.get("port") or -1)}
    state_root_recorded = str(trace.policy.get("broker_state_root") or "")
    state_root = (
        Path(state_root_recorded)
        if state_root_recorded
        else Path("/__missing_broker_state__")
    )
    if not state_root.is_dir():
        state_root = host_audit_path.parent / state_root.name
    if state_root.is_dir():
        for session_file in state_root.glob("*/session.json"):
            try:
                session = json.loads(session_file.read_text(encoding="utf-8"))
                allowed_ports.add(int(session["port"]))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                errors.append("broker state contains an invalid private session")
    completed_network_lines: list[str] = []
    pending_network_calls: dict[tuple[str, str], str] = {}
    for line in lines:
        unfinished = re.search(
            r"\b(connect|sendto|sendmsg|sendmmsg)\(.*<unfinished \.\.\.>", line
        )
        if unfinished:
            key = (_strace_pid(line), unfinished.group(1))
            if key in pending_network_calls:
                errors.append("broker network audit has overlapping unfinished network calls")
            pending_network_calls[key] = line
            continue
        resumed = re.search(
            r"<\.\.\. (connect|sendto|sendmsg|sendmmsg) resumed>(.*)", line
        )
        if resumed:
            key = (_strace_pid(line), resumed.group(1))
            original = pending_network_calls.pop(key, None)
            if original is None:
                errors.append("broker network audit has an unmatched resumed network call")
                continue
            completed_network_lines.append(
                original.split("<unfinished ...>", 1)[0] + resumed.group(2)
            )
            continue
        completed_network_lines.append(line)
    if any("sa_family=AF_INET" in line for line in pending_network_calls.values()):
        errors.append("broker network audit ends with an unfinished internet network call")

    audited = 0
    allowed_loopback = 0
    violations: list[str] = []
    for line in completed_network_lines:
        if (
            not any(
                syscall in line
                for syscall in ("connect(", "sendto(", "sendmsg(", "sendmmsg(")
            )
            or "sa_family=AF_INET" not in line
        ):
            continue
        result_match = re.search(r"\)\s+=\s+(-?\d+)(?:\s+([A-Z]+))?", line)
        if result_match is None:
            errors.append("broker network audit contains an unparsed network result")
            continue
        result = int(result_match.group(1))
        error_name = result_match.group(2)
        if result < 0 and error_name != "EINPROGRESS":
            continue
        family_matches = list(
            re.finditer(r"sa_family=(AF_INET6|AF_INET)(?=[,}])", line)
        )
        if not family_matches:
            errors.append("broker network audit contains an unparsed network destination")
            violations.append(line)
            continue
        if "sendmmsg(" in line and "..." in line:
            errors.append("broker network audit contains an abbreviated sendmmsg payload")
            violations.append(line)
            continue
        for index, family_match in enumerate(family_matches):
            end = (
                family_matches[index + 1].start()
                if index + 1 < len(family_matches)
                else len(line)
            )
            destination = line[family_match.start() : end]
            family = family_match.group(1)
            address_match = (
                re.search(r'inet_pton\(AF_INET6,\s*"([^"]+)"', destination)
                if family == "AF_INET6"
                else re.search(r'inet_addr\("([^"]+)"\)', destination)
            )
            port_match = re.search(r"sin6?_port=htons\((\d+)\)", destination)
            audited += 1
            if not address_match or not port_match:
                errors.append("broker network audit contains an unparsed network destination")
                violations.append(line)
                continue
            address = address_match.group(1)
            port = int(port_match.group(1))
            loopback = (
                address.startswith("127.")
                or address == "::1"
                or address.lower().startswith("::ffff:127.")
            )
            if loopback and port in allowed_ports:
                allowed_loopback += 1
            else:
                violations.append(line)
    summary = {
        "audited_connections": audited,
        "allowed_loopback_connections": allowed_loopback,
        "allowed_loopback_ports": sorted(port for port in allowed_ports if port >= 0),
        "unauthorized_connections": list(dict.fromkeys(violations)),
    }
    return list(dict.fromkeys(errors)), list(dict.fromkeys(violations)), summary


def _audit_protocol(
    trial: CleanTrial,
    rollout_dir: Path,
    host_audit_path: Path,
) -> dict[str, Any]:
    trace = _host_trace_attribution(host_audit_path)
    audit_errors = list(trace.audit_errors)
    broker_audit_errors, broker_violations = _broker_audit_findings(
        trace,
        host_audit_path,
    )
    audit_errors.extend(broker_audit_errors)
    # A fail-closed broker rejection is an ordinary recoverable tool error, not
    # treatment contamination. Agents sometimes guess a session-file path
    # before using the broker-issued path. When the broker rejects that request
    # with exit 126, creates no files, and the matching launcher/client exec is
    # fully audited, retain it as a warning while preserving all successful
    # browser-use evidence. Other malformed or unmatched requests remain hard
    # protocol violations.
    recoverable_broker_rejections: list[dict[str, Any]] = []
    recoverable_provenance_violations: list[str] = []
    recoverable_provenance_pids: set[int] = set()
    strict_broker_violations: list[str] = []
    for item in broker_violations:
        try:
            record = json.loads(item)
        except (json.JSONDecodeError, TypeError):
            rejected_matches = re.findall(
                r"\('([0-9]+)',\s*'[^']+',\s*126,\s*\(",
                str(item),
            )
            all_statuses = re.findall(
                r"\('[0-9]+',\s*'[^']+',\s*(-?[0-9]+),\s*\(",
                str(item),
            )
            if (
                trial.condition == "cua"
                and str(item).startswith(
                    "host trace and CUA broker request provenance differ:"
                )
                and rejected_matches
                and all(status == "126" for status in all_statuses)
            ):
                recoverable_provenance_violations.append(str(item))
                recoverable_provenance_pids.update(
                    int(pid) for pid in rejected_matches
                )
                continue
            strict_broker_violations.append(item)
            continue
        if (
            trial.condition == "cua"
            and isinstance(record, dict)
            and record.get("verb") == "invalid"
            and record.get("exit_code") == 126
            and record.get("files") == []
            and isinstance(record.get("argv"), list)
        ):
            recoverable_broker_rejections.append(record)
        else:
            strict_broker_violations.append(item)
    broker_violations = strict_broker_violations
    recoverable_peer_pids = {
        int(record["peer_pid"])
        for record in recoverable_broker_rejections
        if isinstance(record.get("peer_pid"), int)
    }
    recoverable_session_paths = {
        path
        for record in recoverable_broker_rejections
        if (path := _argv_option(tuple(record["argv"]), "--session-file"))
    }
    diagnostic_adapter_invocations: list[str] = []
    strict_invalid_adapter_invocations: list[str] = []
    for line in trace.invalid_adapter_invocations:
        pid_match = re.match(r"\s*(\d+)\s", line)
        peer_rejected = bool(
            pid_match
            and int(pid_match.group(1))
            in (recoverable_peer_pids | recoverable_provenance_pids)
        )
        session_rejected = any(path in line for path in recoverable_session_paths)
        read_only_adapter_inspection = bool(
            re.search(r'execve\("/usr/bin/(?:grep|sed)"', line)
            and "web_cua_client.py" in line
        )
        no_verb_launcher_probe = bool(
            "web_cua_launcher" in line
            and re.search(r'web_cua_launcher\", \[\"[^\"]*web_cua_launcher\"\]', line)
        )
        if trial.condition == "cua" and (
            peer_rejected
            or (
                session_rejected
                and ("web_cua_launcher" in line or "web_cua_client.py" in line)
            )
            or read_only_adapter_inspection
            or no_verb_launcher_probe
        ):
            diagnostic_adapter_invocations.append(line)
        else:
            strict_invalid_adapter_invocations.append(line)
    protocol_diagnostics: dict[str, list[Any]] = {}
    if diagnostic_adapter_invocations:
        protocol_diagnostics["rejected_or_read_only_adapter_invocation"] = list(
            diagnostic_adapter_invocations
        )
    if recoverable_broker_rejections:
        protocol_diagnostics["rejected_broker_request"] = list(
            recoverable_broker_rejections
        )
    if recoverable_provenance_violations:
        protocol_diagnostics["rejected_broker_provenance"] = list(
            recoverable_provenance_violations
        )
    broker_network_errors, broker_network_violations, broker_network = (
        _broker_network_findings(trace, host_audit_path)
    )
    audit_errors.extend(broker_network_errors)
    for label, actual, expected in (
        ("condition", trace.policy.get("condition"), trial.condition),
        ("task_id", trace.policy.get("task_id"), trial.task_id),
        ("port", trace.policy.get("port"), trial.port),
        (
            "observation_mode",
            trace.policy.get("observation_mode", "structured"),
            trial.observation_mode,
        ),
    ):
        if actual != expected:
            audit_errors.append(
                f"audit policy {label} mismatch: expected {expected!r}, found {actual!r}"
            )
    expected_viewport = trace.policy.get("expected_viewport")
    declared_viewport_starts = 0
    successful_viewport_starts = 0
    if trial.condition == "cua" and expected_viewport:
        if trace.policy.get("version") in {4, 5, 6}:
            successful_records = _successful_broker_records(trace, host_audit_path)
            successful_viewport_starts = sum(
                1 for record in successful_records if record.get("verb") == "start"
            )
            declared_viewport_starts = sum(
                1
                for record in successful_records
                if record.get("verb") == "start"
                and _argv_option(tuple(record["argv"]), "--viewport") == expected_viewport
            )
        else:
            successful_viewport_starts = sum(
                1
                for event in trace.exec_events
                if _validated_public_adapter_invocation(event, trace.policy) == "start"
            )
            declared_viewport_starts = sum(
                1
                for event in trace.exec_events
                if _validated_public_adapter_invocation(event, trace.policy) == "start"
                and _argv_option(event.argv, "--viewport") == expected_viewport
            )
        if successful_viewport_starts and not declared_viewport_starts:
            audit_errors.append(
                f"CUA trace started a viewport other than the task declaration {expected_viewport}"
            )
    audit_valid = not audit_errors
    commands = _tool_commands(rollout_dir, host_audit_path)
    # Notes are commonly written with a heredoc and may truthfully mention that
    # hidden files were unavailable. Audit the executable portion, not heredoc
    # prose, so those notes are not mistaken for access attempts.
    controls = [
        command.splitlines()[0] if "<<" in command.splitlines()[0] else command
        for command in commands
        if command.splitlines()
    ]
    # The isolated source has no hidden files at all. Record only attempts to
    # escape to the benchmark repository; ordinary defensive exclusions such
    # as `rg -g '!verifiers/**'` are evidence of compliance, not violations.
    hidden_attempts = [command for command in controls if BLOCKED_REPO_ATTEMPT.search(command)]
    network = _network_audit(host_audit_path)
    agent_exec_events = _agent_exec_events(trace)
    external_network_commands = [
        event.raw
        for event in agent_exec_events
        if event.succeeded and _external_network_exec(event)
    ]
    network_compliant = not external_network_commands and not network[
        "unauthorized_external_connections"
    ]
    protected_browser_digests = _protected_browser_digests(trace.policy)
    protected_loader_digests = _protected_loader_digests(trace.policy)
    executable_digest_cache: dict[str, str | None] = {}

    def invokes_browser(event: HostExecEvent) -> bool:
        return _browser_or_image_exec(
            event,
            cwd=trace.exec_cwds.get(
                event.index,
                str(trace.policy.get("workspace_root") or "/"),
            ),
            protected_digests=protected_browser_digests,
            loader_digests=protected_loader_digests,
            digest_cache=executable_digest_cache,
        )

    if trial.condition == "code-only":
        forbidden: dict[str, list[str]] = {}
        server_events = [
            event.raw for event in agent_exec_events if _server_or_preview_exec(event)
        ]
        if server_events:
            forbidden["server_or_preview"] = server_events
        local_http_events = [
            event.raw for event in agent_exec_events if _local_http_exec(event)
        ]
        if local_http_events:
            forbidden["local_http"] = local_http_events
        browser_events = [
            event.raw for event in agent_exec_events if invokes_browser(event)
        ]
        image_tool_calls = [command for command in controls if command.startswith("VIEW_IMAGE ")]
        if browser_events or image_tool_calls:
            forbidden["browser_or_image"] = browser_events + image_tool_calls
        nested_model = _nested_model_invocations(agent_exec_events, trace.policy)
        if nested_model:
            forbidden["nested_model_invocation"] = nested_model
        if strict_invalid_adapter_invocations:
            forbidden["untrusted_adapter_invocation"] = list(
                strict_invalid_adapter_invocations
            )
        if broker_violations:
            forbidden["untrusted_broker_request"] = broker_violations
        if broker_network_violations:
            forbidden["browser_network_escape"] = broker_network_violations
        evidence = {
            "evidenced": False,
            "trajectory_count": 0,
            "observations": 0,
            "actions": 0,
            "host_audited_starts": 0,
            "host_audited_observations": 0,
            "host_audited_actions": 0,
        }
        compliant = audit_valid and not forbidden and not hidden_attempts and network_compliant
    else:
        direct_browser = [
            event.raw for event in agent_exec_events if invokes_browser(event)
        ]
        nested_model = _nested_model_invocations(agent_exec_events, trace.policy)
        forbidden = {}
        local_http_events = [
            event.raw for event in agent_exec_events if _local_http_exec(event)
        ]
        if local_http_events:
            forbidden["direct_local_http"] = local_http_events
        if direct_browser:
            forbidden["direct_browser_automation"] = direct_browser
        if nested_model:
            forbidden["nested_model_invocation"] = nested_model
        if strict_invalid_adapter_invocations:
            forbidden["untrusted_adapter_invocation"] = list(
                strict_invalid_adapter_invocations
            )
        if broker_violations:
            forbidden["untrusted_broker_request"] = broker_violations
        if broker_network_violations:
            forbidden["browser_network_escape"] = broker_network_violations
        evidence = _cua_evidence(
            rollout_dir,
            host_audit_path,
            trial.observation_mode,
        )
        evidence["expected_viewport"] = expected_viewport
        evidence["declared_viewport_starts"] = declared_viewport_starts
        evidence["capability_assigned"] = True
        evidence["capability_used"] = bool(evidence["evidenced"])
        compliant = (
            audit_valid
            and not forbidden
            and not hidden_attempts
            and network_compliant
        )
    return {
        "compliant": compliant,
        "protocol_clean": compliant and not protocol_diagnostics,
        "forbidden_actions": forbidden,
        "protocol_diagnostics": protocol_diagnostics,
        "hidden_material_attempts": hidden_attempts,
        "external_network_commands": external_network_commands,
        "network_audit": network,
        "broker_network_audit": broker_network,
        "recoverable_broker_rejections": recoverable_broker_rejections,
        "cua_evidence": evidence,
        "treatment_assignment": {
            "browser_capability_assigned": trial.condition == "cua",
            "browser_capability_used": bool(evidence.get("evidenced")),
            "analysis_policy": "intent_to_treat",
        },
        "audited_command_count": len(commands),
        "audit_integrity": {
            "valid": audit_valid,
            "errors": list(dict.fromkeys(audit_errors)),
            "model_processes": len(trace.model_pids),
            "adapter_processes": len(trace.adapter_pids),
        },
    }


def _copy_run_artifacts(
    isolated_root: Path,
    trial_dir: Path,
    protected_evaluation_root: Path | None = None,
) -> None:
    rollout = isolated_root / "rollout"
    if rollout.is_symlink():
        raise RuntimeError("refusing to copy a symlinked rollout root")
    if rollout.is_dir():
        shutil.copytree(
            rollout,
            trial_dir / "rollout",
            dirs_exist_ok=True,
            symlinks=True,
        )
    verifier_artifacts = (
        protected_evaluation_root / "verifier-artifacts"
        if protected_evaluation_root is not None
        else isolated_root / "protected-evaluation" / "verifier-artifacts"
    )
    if verifier_artifacts.is_symlink():
        raise RuntimeError("refusing to copy a symlinked verifier-artifacts root")
    if verifier_artifacts.is_dir():
        shutil.copytree(
            verifier_artifacts,
            trial_dir / "verifier-artifacts",
            dirs_exist_ok=True,
            symlinks=True,
        )


def _provider_infrastructure_failure(
    agent_result: CommandResult,
    rollout_dir: Path,
) -> dict[str, str] | None:
    """Return a sanitized provider failure when the agent never completed normally."""
    if agent_result.ok:
        return None
    # Agent stdout is structured model/tool output and may legitimately contain
    # local-app HTTP or connection failures. Only provider/CLI error channels
    # can justify removing a trial from the success-rate denominator.
    sources = [agent_result.stderr]
    for name in ("agent_stderr.txt",):
        path = rollout_dir / name
        if path.is_file():
            sources.append(path.read_text(encoding="utf-8", errors="replace"))
    combined = "\n".join(sources)
    match = PROVIDER_INFRASTRUCTURE_ERROR.search(combined)
    if not match:
        return None
    normalized = match.group(0).lower()
    if "expired" in normalized or "401" in normalized:
        category = "provider_authentication"
    elif "429" in normalized or "request" in normalized or "throttl" in normalized:
        category = "provider_capacity"
    else:
        category = "provider_transport"
    return {
        "category": category,
        "message": "model provider failed before a scorable agent completion",
    }


def _post_verifier_result_fields(
    *,
    agent_ok: bool,
    verifier_success: bool,
    treatment_compliant: bool,
    causal_grounded: bool = True,
) -> dict[str, Any]:
    """Separate code correctness, CUA grounding, and evaluation integrity."""
    return {
        "status": (
            "protocol_error"
            if not treatment_compliant
            else "completed"
            if agent_ok
            else "agent_error"
        ),
        "scorable": treatment_compliant,
        "benchmark_success": verifier_success,
        "causal_success": (
            verifier_success and causal_grounded if treatment_compliant else None
        ),
        "infrastructure_error": False,
        "verifier_success": verifier_success,
    }


def run_trial(
    trial: CleanTrial,
    run_root: Path,
    python_bin: Path,
    max_agent_tokens: int = 200_000,
) -> dict[str, Any]:
    started = time.monotonic()
    trial_dir = (
        run_root
        / "trials"
        / trial.condition
        / trial.model.key
        / trial.task_id
        / f"attempt-{trial.attempt}"
    )
    trial_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = trial_dir / "trial.json"
    base = {
        "trial": {
            "ordinal": trial.ordinal,
            "key": trial.key,
            "task_id": trial.task_id,
            "attempt": trial.attempt,
            "condition": trial.condition,
            "observation_mode": trial.observation_mode,
            "port": trial.port,
            "task_file": _repo_relative(trial.task_file),
            "task_digest": trial.task_digest,
        },
        "model": asdict(trial.model),
        "isolation": "source-only-external-workspace+platform-sandbox-denied-benchmark-repo",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(metadata_path, {**base, "status": "preparing"})
    isolated_root = Path(tempfile.mkdtemp(prefix="cua-swe-eval-"))
    broker_socket = isolated_root / "broker" / "cua.sock"
    broker_token = secrets.token_hex(32)
    broker_process: CuaBrokerHandle | None = None
    public_app_processes: list[RunningCommand] = []
    evaluation_app_processes: list[RunningCommand] = []
    protected_evaluation_root: Path | None = None
    protected_service: ProtectedServiceHandle | None = None
    workspace_path = isolated_root / "workspace"
    try:
        # Fail before staging when the controller cannot authenticate this runtime.
        _require_provider_route(trial.model.runtime)
        task = _load_task_file(trial.task_file)
        runtime_contract = _load_protected_runtime_contract(trial.task_file)
        if task.id != trial.task_id:
            raise RuntimeError(
                f"task identity changed after scheduling: expected {trial.task_id}, found {task.id}"
            )
        current_digest = _task_input_digest(trial.task_file)
        if current_digest != trial.task_digest:
            raise RuntimeError(
                f"task input changed after scheduling: {trial.task_id}"
            )
        source = _snapshot_source(task)
        _copy_source_only(source, workspace_path)
        source_only_digest = _tree_digest(
            source,
            excludes=SOURCE_EXCLUDES,
            root_only_excludes=True,
        )
        copied_source_digest = _tree_digest(workspace_path, excludes=frozenset())
        base["input_custody"] = {
            "task_file_sha256": _sha256_file(trial.task_file),
            "task_input_sha256": trial.task_digest,
            "instruction_sha256": hashlib.sha256(task.instruction.encode("utf-8")).hexdigest(),
            "source_only_sha256": source_only_digest,
            "copied_source_only_sha256": copied_source_digest,
            "source_symlinks": _safe_source_symlinks(source),
            "verifier_sha256": _directory_digest(source / "verifiers"),
            "harness_sha256": _evaluation_harness_digest(),
            "runtime_contract_sha256": (
                _sha256_file(runtime_contract.source_path)
                if runtime_contract is not None
                else None
            ),
        }
        if copied_source_digest != source_only_digest:
            raise RuntimeError("source-only custody digest changed during staging")
        _prepare_runtime_port(task, workspace_path, trial.port)
        workspace = _initialize_source_git(workspace_path)
        scripts_dir = _copy_isolated_tools(
            isolated_root,
            trial.condition,
            trial.model.runtime,
        )
        adapter_launcher = (
            _compile_cua_launcher(
                isolated_root,
                scripts_dir,
                python_bin,
                broker_socket,
                broker_token,
            )
            if trial.condition == "cua"
            else None
        )
        (isolated_root / "home" / ".cache").mkdir(parents=True)
        (isolated_root / "home" / ".npm").mkdir(parents=True)
        profile = _sandbox_profile()
        pre_setup_attestation = _verify_sandbox(
            profile,
            isolated_root,
            workspace_path,
            trial.task_file,
            source,
            python_bin,
            allow_browser_runtime=False,
        )
        setup_results = _run_setup_commands(
            (*task.setup.install, *task.setup.reset),
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace_path,
            python_bin=python_bin,
            timeout_sec=task.budgets.wall_time_sec,
        )
        if any(not result.ok for result in setup_results):
            _write_json(
                trial_dir / "isolation_attestation.json",
                {"pre_setup": pre_setup_attestation, "post_setup": None},
            )
            result = {
                **base,
                "status": "setup_error",
                "scorable": False,
                "benchmark_success": False,
                "causal_success": False,
                "infrastructure_error": True,
                "setup": [_command_dict(item) for item in setup_results],
                "duration_sec": time.monotonic() - started,
            }
            _write_json(metadata_path, result)
            return result

        post_setup_attestation = _verify_sandbox(
            profile,
            isolated_root,
            workspace_path,
            trial.task_file,
            source,
            python_bin,
            allow_browser_runtime=False,
        )
        leaked_after_setup = [
            path
            for path in workspace_path.rglob("*")
            if any(
                part in PROTECTED_MATERIAL_NAMES
                for part in path.relative_to(workspace_path).parts
            )
        ]
        if leaked_after_setup:
            raise RuntimeError(
                "setup introduced protected or excluded paths: "
                + ", ".join(str(path.relative_to(workspace_path)) for path in leaked_after_setup[:5])
            )
        isolation_attestation = {
            **post_setup_attestation,
            "pre_setup": pre_setup_attestation,
            "post_setup": post_setup_attestation,
            "workspace_outside_benchmark_repo": not workspace_path.is_relative_to(REPO_ROOT),
            "verifier_present_during_agent": (workspace_path / "verifiers").exists(),
            "fresh_git_history": True,
            "source_excludes": sorted(SOURCE_EXCLUDES),
            "condition_tools": sorted(path.name for path in scripts_dir.iterdir()),
            "condition_python_package_present": (
                isolated_root / "tools" / "src" / "cua_swe_bench"
            ).exists(),
            "condition_tool_packet_sha256": _tool_source_digest(
                isolated_root / "tools"
            ),
        }
        post_common_setup_source_digest = _tree_digest(
            workspace_path,
            excludes=PRE_AGENT_SOURCE_EXCLUDES,
        )
        isolation_attestation["post_common_setup_source_sha256"] = (
            post_common_setup_source_digest
        )
        if trial.condition == "cua":
            if runtime_contract is not None:
                protected_service, protected_service_start = _start_protected_service(
                    task_file=trial.task_file,
                    contract=runtime_contract,
                )
                isolation_attestation["protected_service_start"] = protected_service_start
            else:
                isolation_attestation["protected_service_start"] = None
            public_app_processes, public_app_start = _start_public_app(
                task=task,
                profile=profile,
                isolated_root=isolated_root,
                workspace=workspace_path,
                python_bin=python_bin,
                port=trial.port,
                runtime_contract=runtime_contract,
                protected_service_port=(
                    protected_service.port if protected_service is not None else None
                ),
            )
            isolation_attestation["public_app_start"] = public_app_start
        else:
            isolation_attestation["public_app_start"] = None
        pre_agent_source_digest = _tree_digest(
            workspace_path,
            excludes=PRE_AGENT_SOURCE_EXCLUDES,
        )
        isolation_attestation["pre_agent_source_sha256"] = pre_agent_source_digest
        isolation_attestation["pre_agent_source_excludes"] = sorted(
            PRE_AGENT_SOURCE_EXCLUDES
        )
        isolation_attestation["public_app_start_preserved_source"] = (
            pre_agent_source_digest == post_common_setup_source_digest
        )
        if pre_agent_source_digest != post_common_setup_source_digest:
            raise RuntimeError(
                "condition runtime launch changed the pre-agent source boundary"
            )
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)

        rollout_dir = isolated_root / "rollout"
        rollout_dir.mkdir()
        protected_root_identities = {
            "workspace": _directory_identity(workspace_path),
            "rollout": _directory_identity(rollout_dir),
        }
        isolation_attestation["pre_agent_root_identities"] = protected_root_identities
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)
        (isolated_root / "codex-home").mkdir()
        host_audit_path = trial_dir / "host-execve.log"
        audit_policy_path = trial_dir / "audit-policy.json"
        broker_audit_path = trial_dir / "cua-broker-audit.jsonl"
        broker_state_root = trial_dir / "cua-broker-state"
        broker_network_audit_path = trial_dir / "cua-broker-network.log"
        codex_command = shutil.which("codex")
        if not codex_command:
            raise RuntimeError("Codex CLI is required for protected Luna evaluation")
        _write_audit_policy(
            audit_policy_path,
            trial=trial,
            isolated_root=isolated_root,
            scripts_dir=scripts_dir,
            rollout_dir=rollout_dir,
            python_bin=python_bin,
            codex_entry=Path(codex_command).resolve(),
            adapter_launcher=adapter_launcher,
            broker_socket=broker_socket if trial.condition == "cua" else None,
            broker_token=broker_token if trial.condition == "cua" else None,
            broker_audit_path=broker_audit_path if trial.condition == "cua" else None,
            broker_state_root=broker_state_root if trial.condition == "cua" else None,
            broker_network_audit_path=(
                broker_network_audit_path if trial.condition == "cua" else None
            ),
            expected_app_url=_declared_web_start_url(task, trial.port),
            expected_viewport=(
                _declared_web_viewport(task) if trial.condition == "cua" else None
            ),
        )
        if trial.condition == "cua":
            broker_process = _start_cua_broker(
                isolated_root=isolated_root,
                workspace=workspace_path,
                rollout_dir=rollout_dir,
                scripts_dir=scripts_dir,
                python_bin=python_bin,
                broker_socket=broker_socket,
                broker_token=broker_token,
                audit_path=broker_audit_path,
                state_root=broker_state_root,
                network_audit_path=broker_network_audit_path,
                expected_url=_declared_web_start_url(task, trial.port),
            )
        agent_command = _agent_command(
            trial,
            task,
            isolated_root,
            scripts_dir,
            rollout_dir,
            python_bin,
            profile,
            host_audit_path,
        )
        _write_json(metadata_path, {**base, "status": "running_agent"})
        agent_started = time.monotonic()
        # The lease is valid only while the agent runs and is revoked on any exit.
        with _provider_lease(trial.model.runtime, trial.model.model_id) as lease_environment:
            agent_result = run_agent_command(
                agent_command,
                cwd=workspace_path,
                timeout_sec=task.budgets.wall_time_sec + 30,
                lease_environment=lease_environment,
            )
        agent_duration_sec = time.monotonic() - agent_started
        isolation_attestation["agent_finished_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        for label, path in (("workspace", workspace_path), ("rollout", rollout_dir)):
            _assert_directory_identity(path, protected_root_identities[label])
        isolation_attestation["post_agent_root_identities"] = {
            "workspace": _directory_identity(workspace_path),
            "rollout": _directory_identity(rollout_dir),
        }
        isolation_attestation["protected_root_identities_unchanged"] = True
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)
        broker_cleanup = _stop_cua_broker(broker_process)
        broker_process = None
        isolation_attestation["broker_cleanup"] = broker_cleanup
        _cleanup_processes(isolated_root)
        if public_app_processes:
            isolation_attestation["public_app_cleanup"] = _stop_public_app(
                public_app_processes,
                port=trial.port,
            )
            public_app_processes = []
        else:
            isolation_attestation["public_app_cleanup"] = None
        isolation_attestation["public_app_cleanup_finished_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)
        with host_audit_path.open("a", encoding="utf-8") as audit_handle:
            audit_handle.write(
                f"# CUA_SWE_AUDIT_COMPLETE agent_exit={agent_result.exit_code}\n"
            )

        agent_patch, patch_containment = _extract_agent_patch_contained(
            workspace_path,
            python_bin,
            profile=profile,
            isolated_root=isolated_root,
            timeout_sec=30,
        )
        isolation_attestation["patch_containment"] = patch_containment
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)
        protocol = _audit_protocol(trial, rollout_dir, host_audit_path)
        protocol["budget_attestation"] = _budget_attestation(
            task,
            rollout_dir,
            host_audit_path,
            agent_duration_sec=agent_duration_sec,
            max_agent_tokens=max_agent_tokens,
            cua_evidence=protocol["cua_evidence"],
        )
        protocol["compliant"] = bool(
            protocol["compliant"]
            and protocol["budget_attestation"]["compliant"]
        )
        if not protocol["audit_integrity"]["valid"]:
            _copy_run_artifacts(isolated_root, trial_dir)
            result = {
                **base,
                "status": "infrastructure_error",
                "scorable": False,
                "benchmark_success": False,
                "causal_success": False,
                "infrastructure_error": True,
                "infrastructure_failure": {
                    "category": "host_audit_integrity",
                    "message": "; ".join(protocol["audit_integrity"]["errors"][:5]),
                },
                "protocol": protocol,
                "agent": _command_dict(agent_result),
                "setup": [_command_dict(item) for item in setup_results],
                "patch": agent_patch,
                "duration_sec": time.monotonic() - started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(metadata_path, result)
            return result
        infrastructure_failure = _provider_infrastructure_failure(agent_result, rollout_dir)
        if infrastructure_failure:
            _copy_run_artifacts(isolated_root, trial_dir)
            result = {
                **base,
                "status": "infrastructure_error",
                "scorable": False,
                "benchmark_success": False,
                "causal_success": False,
                "infrastructure_error": True,
                "infrastructure_failure": infrastructure_failure,
                "protocol": protocol,
                "agent": _command_dict(agent_result),
                "setup": [_command_dict(item) for item in setup_results],
                "patch": agent_patch,
                "duration_sec": time.monotonic() - started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(metadata_path, result)
            return result
        pre_evaluation_app_source_digest = _tree_digest(
            workspace_path,
            excludes=PRE_AGENT_SOURCE_EXCLUDES,
        )
        if protected_service is not None:
            isolation_attestation["pre_evaluation_protected_service_cleanup"] = (
                _stop_protected_service(protected_service)
            )
            protected_service = None
        (
            protected_service,
            evaluation_protected_service_start,
            evaluation_app_processes,
            evaluation_app_start,
        ) = _start_fresh_evaluation_runtime(
            task_file=trial.task_file,
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace_path,
            python_bin=python_bin,
            port=trial.port,
            runtime_contract=runtime_contract,
        )
        isolation_attestation["evaluation_protected_service_start"] = (
            evaluation_protected_service_start
        )
        isolation_attestation["evaluation_app_start"] = evaluation_app_start
        isolation_attestation["evaluation_app_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        post_evaluation_app_source_digest = _tree_digest(
            workspace_path,
            excludes=PRE_AGENT_SOURCE_EXCLUDES,
        )
        isolation_attestation["evaluation_app_source_sha256_before_start"] = (
            pre_evaluation_app_source_digest
        )
        isolation_attestation["evaluation_app_source_sha256_after_start"] = (
            post_evaluation_app_source_digest
        )
        isolation_attestation["evaluation_app_start_preserved_source"] = (
            pre_evaluation_app_source_digest == post_evaluation_app_source_digest
        )
        if pre_evaluation_app_source_digest != post_evaluation_app_source_digest:
            raise RuntimeError("evaluation application launch changed the repaired source")
        protected_evaluation_root = Path(
            tempfile.mkdtemp(prefix="cua-swe-protected-evaluation-")
        )
        # Treatment-compliance auditing never substitutes for task evaluation.
        # Both conditions receive the same pristine post-run verifier after the
        # agent exits, even when the trajectory later proves unusable for the
        # matched causal comparison. Noncompliant treatments are retained with
        # their real verifier outcome but marked unscorable for review/rerun.
        isolation_attestation["verifier_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        report, verifier_containment = _run_protected_post_agent_verifier(
            task=task,
            source=source,
            workspace=workspace_path,
            port=trial.port,
            python_bin=python_bin,
            profile=profile,
            isolated_root=isolated_root,
            protected_root=protected_evaluation_root,
        )
        isolation_attestation["verifier_finished_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        isolation_attestation["verifier_containment"] = verifier_containment
        isolation_attestation["evaluation_app_cleanup"] = _stop_public_app(
            evaluation_app_processes,
            port=trial.port,
        )
        evaluation_app_processes = []
        isolation_attestation["protected_service_cleanup"] = _stop_protected_service(
            protected_service
        )
        protected_service = None
        isolation_attestation["evaluation_app_cleanup_finished_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        _write_json(trial_dir / "isolation_attestation.json", isolation_attestation)
        _copy_run_artifacts(
            isolated_root,
            trial_dir,
            protected_evaluation_root,
        )
        recorder_result = ResultRecorder(trial_dir / "result").record(
            task_id=task.id,
            workspace_path=trial_dir / "isolated-workspace-removed",
            patch=agent_patch,
            report=report,
        )
        verifier_success = bool(report.success)
        treatment_compliant = bool(protocol["compliant"])
        causal_grounded = (
            trial.condition != "cua"
            or bool((protocol.get("cua_evidence") or {}).get("evidenced"))
        )
        result = {
            **base,
            **_post_verifier_result_fields(
                agent_ok=agent_result.ok,
                verifier_success=verifier_success,
                treatment_compliant=treatment_compliant,
                causal_grounded=causal_grounded,
            ),
            "protocol": protocol,
            "progress": report.progress,
            "agent": _command_dict(agent_result),
            "setup": [_command_dict(item) for item in setup_results],
            "run_result": recorder_result.model_dump(),
            "duration_sec": time.monotonic() - started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(metadata_path, result)
        return result
    except Exception as exc:
        artifact_copy_error: str | None = None
        try:
            _copy_run_artifacts(
                isolated_root,
                trial_dir,
                protected_evaluation_root,
            )
        except Exception as copy_exc:
            artifact_copy_error = f"{type(copy_exc).__name__}: {copy_exc}"
        result = {
            **base,
            "status": "harness_error",
            "scorable": False,
            "benchmark_success": False,
            "causal_success": False,
            "infrastructure_error": True,
            "error": f"{type(exc).__name__}: {exc}",
            "artifact_copy_error": artifact_copy_error,
            "duration_sec": time.monotonic() - started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(metadata_path, result)
        return result
    finally:
        _stop_cua_broker(broker_process)
        _cleanup_processes(isolated_root)
        for process in reversed(evaluation_app_processes):
            process.stop()
        for process in reversed(public_app_processes):
            process.stop()
        _stop_protected_service(protected_service)
        if protected_evaluation_root is not None:
            shutil.rmtree(protected_evaluation_root, ignore_errors=True)
        shutil.rmtree(isolated_root, ignore_errors=True)


def run_staging_demonstration(
    *,
    task_file: Path,
    output_root: Path,
    python_bin: Path,
    port: int,
    responsive_capability: bool = False,
    responsive_baseline: bool = False,
) -> dict[str, Any]:
    """Exercise protected retained-app staging with a dummy, non-model agent."""
    if responsive_capability and responsive_baseline:
        raise ValueError("responsive gold and baseline staging are mutually exclusive")
    responsive_replay = responsive_capability or responsive_baseline
    resolved_task_file = task_file.expanduser().resolve()
    if output_root.exists():
        raise ValueError(f"staging output already exists: {output_root}")
    output_root.mkdir(parents=True)
    isolated_root = Path(tempfile.mkdtemp(prefix="cua-swe-staging-"))
    workspace = isolated_root / "workspace"
    broker_socket = isolated_root / "broker" / "cua.sock"
    broker_token = secrets.token_hex(32)
    broker_process: CuaBrokerHandle | None = None
    public_app_processes: list[RunningCommand] = []
    protected_service: ProtectedServiceHandle | None = None
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": (
            "non_evaluative_storybook_resize_capability_staging"
            if responsive_capability
            else (
                "non_evaluative_storybook_resize_baseline_staging"
                if responsive_baseline
                else "non_evaluative_protected_staging_demonstration"
            )
        ),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "task_file": _repo_relative(resolved_task_file),
        "port": port,
        "model_invoked": False,
        "scored_evaluation": False,
    }
    try:
        task = _load_task_file(resolved_task_file)
        runtime_contract = _load_protected_runtime_contract(resolved_task_file)
        source = _snapshot_source(task)
        _copy_source_only(source, workspace)
        source_only_digest = _tree_digest(
            source,
            excludes=SOURCE_EXCLUDES,
            root_only_excludes=True,
        )
        copied_source_digest = _tree_digest(workspace, excludes=frozenset())
        evidence["input_custody"] = {
            "task_file_sha256": _sha256_file(resolved_task_file),
            "task_input_sha256": _task_input_digest(resolved_task_file),
            "instruction_sha256": hashlib.sha256(task.instruction.encode("utf-8")).hexdigest(),
            "source_only_sha256": source_only_digest,
            "copied_source_only_sha256": copied_source_digest,
            "source_symlinks": _safe_source_symlinks(source),
            "verifier_sha256": _directory_digest(source / "verifiers"),
            "harness_sha256": _evaluation_harness_digest(),
            "runtime_contract_sha256": (
                _sha256_file(runtime_contract.source_path)
                if runtime_contract is not None
                else None
            ),
        }
        if source_only_digest != copied_source_digest:
            raise RuntimeError("staging source-only custody digest mismatch")
        _prepare_runtime_port(task, workspace, port)
        _initialize_source_git(workspace)
        if responsive_capability:
            gold_patch = resolved_task_file.parent / "gold.patch"
            if not gold_patch.is_file():
                raise RuntimeError("responsive capability staging requires gold.patch")
            gold_apply = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(gold_patch)],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            evidence["gold_patch"] = {
                "sha256": _sha256_file(gold_patch),
                "applied": gold_apply.returncode == 0,
                "stderr": gold_apply.stderr,
            }
            if gold_apply.returncode != 0:
                raise RuntimeError("responsive capability staging gold patch did not apply")
        scripts_dir = _copy_isolated_tools(isolated_root, "cua", "codex")
        if responsive_replay:
            shutil.copy2(
                REPO_ROOT / "scripts" / "run_storybook_resize_capability.py",
                scripts_dir / "run_storybook_resize_capability.py",
            )
        adapter_launcher = (
            _compile_cua_launcher(
                isolated_root,
                scripts_dir,
                python_bin,
                broker_socket,
                broker_token,
            )
            if responsive_replay
            else None
        )
        (isolated_root / "home" / ".cache").mkdir(parents=True)
        (isolated_root / "home" / ".npm").mkdir(parents=True)
        (isolated_root / "rollout").mkdir()
        profile = _sandbox_profile()
        evidence["pre_setup_sandbox"] = _verify_sandbox(
            profile,
            isolated_root,
            workspace,
            resolved_task_file,
            source,
            python_bin,
            allow_browser_runtime=False,
        )
        setup_results = _run_setup_commands(
            (*task.setup.install, *task.setup.reset),
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace,
            python_bin=python_bin,
            timeout_sec=task.budgets.wall_time_sec,
        )
        evidence["setup"] = [_command_dict(result) for result in setup_results]
        if any(not result.ok for result in setup_results):
            raise RuntimeError("staging setup command failed")
        evidence["post_setup_sandbox"] = _verify_sandbox(
            profile,
            isolated_root,
            workspace,
            resolved_task_file,
            source,
            python_bin,
            allow_browser_runtime=False,
        )
        protected_before_agent = [
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*")
            if any(
                part in PROTECTED_MATERIAL_NAMES
                for part in path.relative_to(workspace).parts
            )
        ]
        evidence["protected_paths_before_agent"] = protected_before_agent
        if protected_before_agent:
            raise RuntimeError(
                "protected material entered the staged agent workspace: "
                + ", ".join(protected_before_agent[:5])
            )
        if runtime_contract is not None:
            protected_service, protected_service_start = _start_protected_service(
                task_file=resolved_task_file,
                contract=runtime_contract,
            )
            evidence["protected_service_start"] = protected_service_start
        else:
            evidence["protected_service_start"] = None
        public_app_processes, public_app_start = _start_public_app(
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace,
            python_bin=python_bin,
            port=port,
            runtime_contract=runtime_contract,
            protected_service_port=(
                protected_service.port if protected_service is not None else None
            ),
        )
        evidence["public_app_start"] = public_app_start
        sandbox, backend = _sandbox_command(
            profile,
            isolated_root,
            workspace,
            python_bin,
            allow_browser_runtime=False,
        )
        dummy_command = (
            "test ! -e verifiers && test ! -e task.yaml && "
            "test ! -e gold.patch && test ! -e negative.patch && "
            "test ! -e replay.md"
        )
        dummy_started_at = datetime.now(timezone.utc).isoformat()
        dummy_result = run_command(
            shlex.join([*sandbox, "/bin/sh", "-lc", dummy_command]),
            cwd=workspace,
            timeout_sec=30,
        )
        dummy_finished_at = datetime.now(timezone.utc).isoformat()
        evidence["dummy_agent"] = {
            "backend": backend,
            "command": dummy_command,
            "started_at": dummy_started_at,
            "finished_at": dummy_finished_at,
            "result": _command_dict(dummy_result),
        }
        if not dummy_result.ok:
            raise RuntimeError("dummy protected agent probe failed")
        if responsive_replay:
            broker_audit_path = output_root / "cua-broker-audit.jsonl"
            broker_state_root = output_root / "cua-broker-state"
            broker_network_audit_path = output_root / "cua-broker-network.log"
            broker_process = _start_cua_broker(
                isolated_root=isolated_root,
                workspace=workspace,
                rollout_dir=isolated_root / "rollout",
                scripts_dir=scripts_dir,
                python_bin=python_bin,
                broker_socket=broker_socket,
                broker_token=broker_token,
                audit_path=broker_audit_path,
                state_root=broker_state_root,
                network_audit_path=broker_network_audit_path,
                expected_url=_declared_web_start_url(task, port),
            )
            replay_kind = "capability" if responsive_capability else "baseline"
            replay_rollout = isolated_root / "rollout" / f"storybook-resize-{replay_kind}"
            replay_command = shlex.join(
                [
                    *sandbox,
                    str(python_bin),
                    "-I",
                    str(scripts_dir / "run_storybook_resize_capability.py"),
                    "--launcher",
                    str(adapter_launcher),
                    "--url",
                    _declared_web_start_url(task, port),
                    "--rollout",
                    str(replay_rollout),
                    "--expected-outcome",
                    "repaired" if responsive_capability else "broken-baseline",
                ]
            )
            replay_result = run_command(
                replay_command,
                cwd=workspace,
                timeout_sec=600,
            )
            try:
                replay_evidence = json.loads(replay_result.stdout)
            except json.JSONDecodeError:
                replay_evidence = {
                    "status": "fail",
                    "error": "responsive replay driver returned non-JSON output",
                }
            evidence[f"responsive_{replay_kind}"] = {
                "backend": backend,
                "command": replay_command,
                "result": _command_dict(replay_result),
                "evidence": replay_evidence,
            }
            if not replay_result.ok or replay_evidence.get("status") != "pass":
                raise RuntimeError(f"same-page responsive {replay_kind} staging failed")
            evidence["broker_cleanup"] = _stop_cua_broker(broker_process)
            broker_process = None
            rollout_source = replay_rollout
            shutil.copytree(rollout_source, output_root / "rollout")
            evidence["responsive_artifacts"] = {
                "broker_audit_sha256": _sha256_file(broker_audit_path),
                "broker_network_audit_sha256": _sha256_file(broker_network_audit_path),
                "broker_state_sha256": _tree_digest(
                    broker_state_root,
                    excludes=frozenset(),
                ),
                "rollout_sha256": _tree_digest(
                    output_root / "rollout",
                    excludes=frozenset(),
                ),
            }
        _cleanup_processes(isolated_root)
        evidence["public_app_cleanup"] = _stop_public_app(
            public_app_processes,
            port=port,
        )
        public_app_processes = []
        if protected_service is not None:
            evidence["pre_evaluation_protected_service_cleanup"] = (
                _stop_protected_service(protected_service)
            )
            protected_service = None
        (
            protected_service,
            evaluation_protected_service_start,
            public_app_processes,
            evaluation_app_start,
        ) = _start_fresh_evaluation_runtime(
            task_file=resolved_task_file,
            task=task,
            profile=profile,
            isolated_root=isolated_root,
            workspace=workspace,
            python_bin=python_bin,
            port=port,
            runtime_contract=runtime_contract,
        )
        evidence["evaluation_protected_service_start"] = (
            evaluation_protected_service_start
        )
        evidence["evaluation_app_start"] = evaluation_app_start
        verifier_started_at = datetime.now(timezone.utc).isoformat()
        protected_evaluation_root = Path(
            tempfile.mkdtemp(prefix="cua-swe-protected-staging-evaluation-")
        )
        report, containment = _run_protected_post_agent_verifier(
            task=task,
            source=source,
            workspace=workspace,
            port=port,
            python_bin=python_bin,
            profile=profile,
            isolated_root=isolated_root,
            protected_root=protected_evaluation_root,
        )
        verifier_finished_at = datetime.now(timezone.utc).isoformat()
        evidence["post_agent_verifier"] = {
            "started_at": verifier_started_at,
            "finished_at": verifier_finished_at,
            "report": report.model_dump(),
            "containment": containment,
        }
        evidence["evaluation_app_cleanup"] = _stop_public_app(
            public_app_processes,
            port=port,
        )
        public_app_processes = []
        evidence["protected_service_cleanup"] = _stop_protected_service(
            protected_service
        )
        protected_service = None
        groups = {result.group: result for result in report.results}
        behavioral_results = [
            result for result in report.results if result.group != "build"
        ]
        expected_result = (
            report.success
            if responsive_capability
            else (
                groups.get("build") is not None
                and groups["build"].passed
                and behavioral_results
                and any(not result.passed for result in behavioral_results)
                and not report.success
            )
        )
        evidence[
            "expected_gold_result" if responsive_capability else "expected_noop_result"
        ] = expected_result
        if not expected_result:
            expectation = "gold pass" if responsive_capability else "certified no-op outcome"
            raise RuntimeError(f"protected staging verifier did not reproduce {expectation}")
        evidence["status"] = "pass"
    except Exception as exc:
        evidence["status"] = "fail"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _stop_cua_broker(broker_process)
        _cleanup_processes(isolated_root)
        for process in reversed(public_app_processes):
            process.stop()
        _stop_protected_service(protected_service)
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output_root / "staging-demonstration.json", evidence)
        shutil.rmtree(isolated_root, ignore_errors=True)
    return evidence


def replay_protocol_evidence(
    *,
    input_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Re-audit sealed trials without changing their signed classifications."""
    source_root = input_root.expanduser().resolve()
    destination = output_root.expanduser().absolute()
    if not source_root.is_dir():
        raise ValueError(f"protocol replay input does not exist: {source_root}")
    if destination.exists():
        raise ValueError(f"protocol replay output already exists: {destination}")
    if destination.resolve().is_relative_to(source_root):
        raise ValueError("protocol replay output cannot be inside the sealed input root")
    manifest_path = source_root / "manifest.json"
    summary_path = source_root / "summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        raise ValueError("protocol replay input lacks manifest.json or summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = summary.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("protocol replay input has no signed trial results")
    records: list[dict[str, Any]] = []
    for result in results:
        trial_dir = source_root / _trial_relative_dir(result)
        trial_path = trial_dir / "trial.json"
        host_audit_path = trial_dir / "host-execve.log"
        rollout_dir = trial_dir / "rollout"
        if not trial_path.is_file() or not host_audit_path.is_file() or not rollout_dir.is_dir():
            raise ValueError(f"protocol replay input is incomplete: {trial_dir}")
        signed = json.loads(trial_path.read_text(encoding="utf-8"))
        if signed != result:
            raise ValueError(f"signed trial and summary disagree: {trial_dir}")
        recorded_protocol = signed.get("protocol")
        if not isinstance(recorded_protocol, dict):
            raise ValueError(f"signed trial lacks protocol evidence: {trial_dir}")
        replayed_protocol = _audit_protocol(
            _audit_trial_from_result(signed),
            rollout_dir,
            host_audit_path,
        )
        recorded_forbidden = recorded_protocol.get("forbidden_actions") or {}
        replayed_forbidden = replayed_protocol.get("forbidden_actions") or {}
        records.append(
            {
                "trial_key": signed["trial"]["key"],
                "signed_status": signed.get("status"),
                "signed_scorable": signed.get("scorable"),
                "signed_verifier_success": signed.get("verifier_success"),
                "signed_trial_sha256": _sha256_file(trial_path),
                "host_audit_sha256": _sha256_file(host_audit_path),
                "rollout_sha256": _tree_digest(rollout_dir, excludes=frozenset()),
                "recorded_protocol_sha256": hashlib.sha256(
                    json.dumps(
                        recorded_protocol,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "replayed_protocol_sha256": hashlib.sha256(
                    json.dumps(
                        replayed_protocol,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "recorded_compliant": recorded_protocol.get("compliant"),
                "replayed_compliant": replayed_protocol.get("compliant"),
                "recorded_forbidden_counts": {
                    key: len(value) for key, value in recorded_forbidden.items()
                },
                "replayed_forbidden_counts": {
                    key: len(value) for key, value in replayed_forbidden.items()
                },
                "replayed_audit_integrity": replayed_protocol.get("audit_integrity"),
                "replayed_cua_evidence": replayed_protocol.get("cua_evidence"),
                "replayed_protocol": replayed_protocol,
            }
        )
    expected_conditions = {"cua", "code-only"}
    replay_conditions = {
        str(record["trial_key"]).split("/", 1)[0] for record in records
    }
    passed = (
        replay_conditions == expected_conditions
        and all(record["signed_status"] == "protocol_error" for record in records)
        and all(record["signed_scorable"] is False for record in records)
        and all(record["recorded_compliant"] is False for record in records)
        and all(
            record["recorded_forbidden_counts"] == {"nested_model_invocation": 1}
            for record in records
        )
        and all(record["replayed_compliant"] is True for record in records)
        and all(record["replayed_forbidden_counts"] == {} for record in records)
        and all(
            (record["replayed_audit_integrity"] or {}).get("valid") is True
            for record in records
        )
    )
    evidence = {
        "schema_version": 1,
        "kind": "non_evaluative_protocol_regression_replay",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(source_root),
        "manifest_sha256": _sha256_file(manifest_path),
        "summary_sha256": _sha256_file(summary_path),
        "evaluation_harness_sha256": _evaluation_harness_digest(),
        "model_invoked": False,
        "scored_evaluation": False,
        "signed_inputs_modified": False,
        "records": records,
        "status": "pass" if passed else "fail",
    }
    destination.mkdir(parents=True)
    _write_json(destination / "protocol-replay.json", evidence)
    return evidence


def selected_task_inputs(args: argparse.Namespace) -> list[TaskInput]:
    if args.task_file:
        if args.task:
            raise ValueError("--task-file and legacy --task cannot be combined")
        inputs = [_task_input(path) for path in args.task_file]
    else:
        names = [name for name in TASK_NAMES if not args.task or name in args.task]
        inputs = [
            _task_input(REPO_ROOT / "dataset" / "tasks" / "web" / name / "task.yaml")
            for name in names
        ]
    duplicates = sorted(
        task_id
        for task_id in {item.task_id for item in inputs}
        if sum(item.task_id == task_id for item in inputs) > 1
    )
    if duplicates:
        raise ValueError("duplicate task IDs: " + ", ".join(duplicates))
    if not inputs:
        raise ValueError("no tasks selected")
    return inputs


def selected_models(args: argparse.Namespace) -> list[ModelSpec]:
    development_pair = bool(getattr(args, "development_pair", False))
    visual_cua = bool(getattr(args, "visual_cua", False))
    evaluation_matrix = bool(getattr(args, "evaluation_matrix", False))
    single_frontier = visual_cua or bool(getattr(args, "code_only_only", False))
    if single_frontier:
        if not args.model or (
            not evaluation_matrix and len(set(args.model)) != 1
        ):
            mode = "--visual-cua" if visual_cua else "--code-only-only"
            requirement = (
                "one or more --model values with --evaluation-matrix"
                if evaluation_matrix
                else "exactly one --model"
            )
            raise ValueError(f"{mode} requires {requirement}")
        return [model for model in MODELS if model.key in set(args.model)]
    if args.luna_workflow or development_pair:
        if args.model and set(args.model) != {"gpt56-luna"}:
            mode = (
                "--visual-cua"
                if visual_cua
                else "--development-pair"
                if development_pair
                else "--luna-workflow"
            )
            raise ValueError(f"{mode} cannot be combined with another model")
        return [model for model in MODELS if model.key == "gpt56-luna"]
    if args.model and "gpt56-luna" in args.model:
        raise ValueError("GPT 5.6 Luna requires --luna-workflow")
    models = [
        model
        for model in MODELS
        if model.key != "gpt56-luna" and (not args.model or model.key in args.model)
    ]
    if not models:
        raise ValueError("no models selected")
    return models


def _active_conditions(args: argparse.Namespace) -> tuple[str, ...]:
    if bool(getattr(args, "code_only_only", False)):
        return ("code-only",)
    return ("cua",) if bool(getattr(args, "cua_only", False)) else CONDITIONS


def _all_trials(args: argparse.Namespace) -> list[CleanTrial]:
    models = selected_models(args)
    tasks = selected_task_inputs(args)
    trials: list[CleanTrial] = []
    ordinal = 0
    pair_ordinal = 0
    for attempt in range(1, args.attempts + 1):
        for task_index, task in enumerate(tasks):
            active_conditions = _active_conditions(args)
            first = "cua" if (attempt + task_index) % 2 else "code-only"
            conditions = (
                active_conditions
                if len(active_conditions) == 1
                else (first, "code-only" if first == "cua" else "cua")
            )
            for model in models:
                pair_port = args.base_port + pair_ordinal
                pair_ordinal += 1
                for condition in conditions:
                    trials.append(
                        CleanTrial(
                            ordinal=ordinal,
                            task_file=task.task_file,
                            task_id=task.task_id,
                            task_name=task.task_name,
                            task_digest=task.digest,
                            model=model,
                            attempt=attempt,
                            condition=condition,
                            port=pair_port,
                            observation_mode=(
                                "visual"
                                if bool(getattr(args, "visual_cua", False))
                                else "structured"
                            ),
                        )
                    )
                    ordinal += 1
    return trials


def build_trials(args: argparse.Namespace) -> list[CleanTrial]:
    trials = _all_trials(args)
    expected_conditions = set(_active_conditions(args))
    attempts = list(getattr(args, "run_attempt", None) or [])
    retry_keys = list(getattr(args, "retry_key", None) or [])
    if attempts and retry_keys:
        raise ValueError("--run-attempt and --retry-key cannot be combined")
    if not attempts and not retry_keys:
        return trials
    if attempts:
        if len(attempts) != len(set(attempts)):
            raise ValueError("duplicate --run-attempt values are not allowed")
        if any(attempt < 1 or attempt > args.attempts for attempt in attempts):
            raise ValueError("--run-attempt must be between 1 and --attempts")
        selected = [trial for trial in trials if trial.attempt in set(attempts)]
        selected_pairs = {(trial.task_id, trial.model.key, trial.attempt) for trial in selected}
        for task_id, model_key, attempt in selected_pairs:
            conditions = {
                trial.condition
                for trial in selected
                if (trial.task_id, trial.model.key, trial.attempt)
                == (task_id, model_key, attempt)
            }
            if conditions != expected_conditions:
                raise ValueError("attempt shards must include every selected condition")
        return selected
    if len(retry_keys) != len(set(retry_keys)):
        raise ValueError("duplicate --retry-key values are not allowed")
    canonical_keys = {trial.key for trial in trials}
    unknown = sorted(set(retry_keys).difference(canonical_keys))
    if unknown:
        raise ValueError("unknown --retry-key values: " + ", ".join(unknown))
    selected = [trial for trial in trials if trial.key in set(retry_keys)]
    groups: dict[tuple[str, str, int], set[str]] = {}
    for trial in selected:
        group = (trial.task_id, trial.model.key, trial.attempt)
        groups.setdefault(group, set()).add(trial.condition)
    if not groups or any(conditions != expected_conditions for conditions in groups.values()):
        raise ValueError("retries must include every selected condition")
    return selected


def _trial_manifest_record(trial: CleanTrial) -> dict[str, Any]:
    return {
        "key": trial.key,
        "ordinal": trial.ordinal,
        "port": trial.port,
        "task_id": trial.task_id,
        "task_digest": trial.task_digest,
        "model_key": trial.model.key,
        "model_id": trial.model.model_id,
        "condition": trial.condition,
        "attempt": trial.attempt,
        "observation_mode": trial.observation_mode,
    }


def _canonical_task_custody(task_file: Path, task_digest: str) -> dict[str, Any]:
    task = _load_task_file(task_file)
    source = _snapshot_source(task)
    return {
        "task_file": _repo_relative(task_file),
        "task_digest": task_digest,
        "task_file_sha256": _sha256_file(task_file),
        "instruction_sha256": hashlib.sha256(task.instruction.encode("utf-8")).hexdigest(),
        "source_only_sha256": _tree_digest(
            source,
            excludes=SOURCE_EXCLUDES,
            root_only_excludes=True,
        ),
        "source_symlinks": _safe_source_symlinks(source),
        "verifier_sha256": _directory_digest(source / "verifiers"),
    }


def _manifest_payload(args: argparse.Namespace, trials: list[CleanTrial]) -> dict[str, Any]:
    canonical_trials = _all_trials(args)
    harness_digest = _evaluation_harness_digest()
    runtime = _runtime_provenance(str(getattr(args, "python", sys.executable)))
    selection_mode = (
        "paired_attempt_shard"
        if getattr(args, "run_attempt", None)
        else "pair_retry"
        if getattr(args, "retry_key", None)
        else "full"
    )
    task_inputs: dict[str, dict[str, Any]] = {}
    for trial in canonical_trials:
        prior = task_inputs.get(trial.task_id)
        if prior is None:
            task_inputs[trial.task_id] = _canonical_task_custody(
                trial.task_file, trial.task_digest
            )
        elif (
            prior["task_file"] != _repo_relative(trial.task_file)
            or prior["task_digest"] != trial.task_digest
        ):
            raise ValueError(f"task identity is inconsistent across trials: {trial.task_id}")
    models = {trial.model.key: asdict(trial.model) for trial in canonical_trials}
    active_conditions = _active_conditions(args)
    locked_inputs = {
        "iteration": args.iteration,
        "attempts": args.attempts,
        "run_mode": (
            "visual_cua_frontier"
            if bool(getattr(args, "visual_cua", False))
            else "code_only_frontier"
            if bool(getattr(args, "code_only_only", False))
            else "development_pair"
            if getattr(args, "development_pair", False)
            else "confirmatory_luna"
            if args.luna_workflow
            else "cua_only"
            if bool(getattr(args, "cua_only", False))
            else "comparison"
        ),
        "conditions": list(active_conditions),
        "tasks": task_inputs,
        "models": models,
        "evaluation_harness_digest": harness_digest,
        "execution_policy": {
            "shard_unit": (
                "cua_attempt"
                if active_conditions == ("cua",)
                else "code_only_attempt"
                if active_conditions == ("code-only",)
                else "paired_attempt"
            ),
            "per_host_max_workers": int(args.max_workers),
            "fail_fast_on_infrastructure_failure": True,
            "infrastructure_retry": (
                "new_cua-attempt_shard_on_same_physical_host"
                if len(active_conditions) == 1
                else "new_complete-pair_shard_on_same_physical_host"
            ),
            "max_agent_noncached_tokens": int(
                getattr(args, "max_agent_tokens", 200_000)
            ),
        },
        "trials": [_trial_manifest_record(trial) for trial in canonical_trials],
    }
    signature = hashlib.sha256(
        json.dumps(locked_inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "experiment": (
            "visual_cua_frontier_evaluation"
            if bool(getattr(args, "visual_cua", False))
            else "code_only_frontier_evaluation"
            if bool(getattr(args, "code_only_only", False))
            else "cua_only_evaluation"
            if len(active_conditions) == 1
            else "browser_vs_code_only_evaluation"
        ),
        "iteration": args.iteration,
        "evaluation_signature": signature,
        "evaluation_harness_digest": harness_digest,
        "runtime_provenance": runtime,
        "actual_hostname": socket.gethostname(),
        "execution_policy": locked_inputs["execution_policy"],
        "isolation": {
            "agent_workspace": "external temporary source-only copy",
            "git_history": "fresh; source files only",
            "benchmark_repo": "file reads and writes denied by the platform sandbox",
            "supported_sandboxes": ["sandbox-exec", "bubblewrap"],
            "evaluation_artifacts_excluded": sorted(SOURCE_EXCLUDES),
            "evaluation_timing": "verifier runs only after the agent process exits",
        },
        "tasks": task_inputs,
        "conditions": list(active_conditions),
        "models": models,
        "attempts": args.attempts,
        "run_mode": locked_inputs["run_mode"],
        "max_workers": args.max_workers,
        "trials": locked_inputs["trials"],
        "shard_id": getattr(args, "shard_id", None),
        "execution_host": getattr(args, "execution_host", None),
        "selection_mode": selection_mode,
        "selected_trial_keys": [trial.key for trial in trials],
    }


def _complete_result_set(manifest: dict[str, Any], results: list[dict[str, Any]]) -> bool:
    expected = [str(item["key"]) for item in manifest["trials"]]
    actual = [str(item["trial"]["key"]) for item in results]
    return (
        len(actual) == len(set(actual))
        and set(actual) == set(expected)
        and all(
            result.get("scorable") is True
            and result.get("infrastructure_error") is False
            and ((result.get("protocol") or {}).get("audit_integrity") or {}).get("valid") is True
            and result.get("status") in {"completed", "agent_error"}
            and isinstance(result.get("verifier_success"), bool)
            and (result.get("protocol") or {}).get("compliant") is True
            and result.get("benchmark_success") is result.get("verifier_success")
            and result.get("causal_success")
            is (
                result.get("verifier_success")
                and (
                    result.get("trial", {}).get("condition") != "cua"
                    or bool(
                        ((result.get("protocol") or {}).get("cua_evidence") or {}).get(
                            "evidenced"
                        )
                    )
                )
            )
            for result in results
        )
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _tool_source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.relative_to(root).parts[0] != "bin"
            and "__pycache__" not in path.relative_to(root).parts
            and path.suffix != ".pyc"
        ),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _trial_relative_dir(result: dict[str, Any]) -> Path:
    return (
        Path("trials")
        / str(result["trial"]["condition"])
        / str(result["model"]["key"])
        / str(result["trial"]["task_id"])
        / f"attempt-{int(result['trial']['attempt'])}"
    )


def _validate_result_identity(
    root: Path,
    result: dict[str, Any],
    expected_trial: dict[str, Any],
    expected_model: dict[str, Any],
    expected_task: dict[str, Any],
    expected_harness_digest: str,
) -> Path:
    key = str(result["trial"]["key"])
    for field in (
        "key",
        "ordinal",
        "port",
        "task_id",
        "task_digest",
        "condition",
        "attempt",
    ):
        if result.get("trial", {}).get(field) != expected_trial.get(field):
            raise ValueError(f"result {key} disagrees with canonical trial field {field}")
    if result.get("model") != expected_model:
        raise ValueError(f"result {key} disagrees with the canonical model configuration")
    _validate_input_custody(
        key,
        result,
        expected_task=expected_task,
        expected_harness_digest=expected_harness_digest,
    )
    if type(result.get("infrastructure_error")) is not bool:
        raise ValueError(f"result {key} lacks explicit boolean infrastructure classification")
    if type(result.get("scorable")) is not bool:
        raise ValueError(f"result {key} lacks explicit boolean scoring classification")
    if result["infrastructure_error"] is True and result["scorable"] is True:
        raise ValueError(f"infrastructure failure cannot be scorable: {key}")
    trial_dir = root / _trial_relative_dir(result)
    trial_path = trial_dir / "trial.json"
    if not trial_path.is_file():
        raise ValueError(f"missing durable trial.json: {key}")
    recorded = json.loads(trial_path.read_text(encoding="utf-8"))
    if recorded != result:
        raise ValueError(f"summary result disagrees with durable trial.json: {key}")
    return trial_dir


def _audit_trial_from_result(result: dict[str, Any]) -> CleanTrial:
    trial = result["trial"]
    return CleanTrial(
        ordinal=int(trial["ordinal"]),
        task_file=Path(str(trial.get("task_file") or ".")),
        task_id=str(trial["task_id"]),
        task_name=str(trial["task_id"]),
        task_digest=str(trial["task_digest"]),
        model=ModelSpec(**result["model"]),
        attempt=int(trial["attempt"]),
        condition=str(trial["condition"]),
        port=int(trial["port"]),
        observation_mode=str(trial.get("observation_mode") or "structured"),
    )


def _validate_probe_attestation(key: str, phase: str, data: dict[str, Any]) -> None:
    probes = data.get("repo_probes") or []
    target_kinds = [str(probe.get("target_kind") or "") for probe in probes]
    normalized = [target.lower().replace("\\", "/") for target in target_kinds]
    required_targets = (
        any(target.endswith("/task.yaml") or target == "task.yaml" for target in normalized),
        any(target.endswith("/gold.patch") or target == "gold.patch" for target in normalized),
        any("/verifiers/" in f"/{target}" for target in normalized),
    )
    if (
        data.get("backend") != "bubblewrap"
        or data.get("workspace_read_write_allowed") is not True
        or data.get("tools_write_blocked") is not True
        or len(probes) < 3
        or len(set(target_kinds)) != len(target_kinds)
        or not all(required_targets)
        or not all(
            probe.get("blocked") is True
            and isinstance(probe.get("exit_code"), int)
            and probe["exit_code"] != 0
            for probe in probes
        )
    ):
        raise ValueError(f"{phase} isolation evidence is incomplete: {key}")
    tool_probe = data.get("tool_write_probe") or {}
    if (
        not str(tool_probe.get("target") or "").startswith("tools/scripts/")
        or not isinstance(tool_probe.get("exit_code"), int)
        or tool_probe["exit_code"] == 0
    ):
        raise ValueError(f"{phase} read-only tool evidence is incomplete: {key}")
    host_probes = data.get("host_path_probes") or []
    host_targets = [str(probe.get("target_kind") or "") for probe in host_probes]
    if (
        data.get("filesystem_policy") != "allowlisted_root"
        or len(host_probes) < 3
        or not all(probe.get("blocked") is True for probe in host_probes)
        or not any(target.endswith("/.ssh") for target in host_targets)
        or not any(target.endswith("/.codex") for target in host_targets)
        or not any(
            "cua-swe-workers" in target or target.endswith("/author1-20260809")
            for target in host_targets
        )
    ):
        raise ValueError(f"{phase} host-filesystem isolation is incomplete: {key}")
    runtime_mounts = [str(path) for path in data.get("runtime_read_only_mounts") or []]
    browser_probes = data.get("browser_runtime_probes") or []
    if (
        not runtime_mounts
        or any(path in {"/", str(Path.home())} for path in runtime_mounts)
        or any("cua-swe-workers" in path for path in runtime_mounts)
        or any(
            "google/chrome" in path or "ms-playwright" in path
            for path in runtime_mounts
        )
        or len(browser_probes) != 2
        or not all(probe.get("blocked") is True for probe in browser_probes)
    ):
        raise ValueError(f"{phase} runtime allowlist is unsafe: {key}")


def _validate_raw_protocol_evidence(
    trial_dir: Path,
    result: dict[str, Any],
) -> None:
    key = str(result["trial"]["key"])
    host_audit = trial_dir / "host-execve.log"
    rollout = trial_dir / "rollout"
    if (
        not host_audit.is_file()
        or host_audit.stat().st_size == 0
        or "execve(" not in host_audit.read_text(encoding="utf-8", errors="replace")
    ):
        raise ValueError(f"missing host-owned exec audit: {key}")
    for name in ("agent_stdout.txt", "agent_stderr.txt"):
        if not (rollout / name).is_file():
            raise ValueError(f"missing durable agent rollout artifact {name}: {key}")
    recomputed = _audit_protocol(
        _audit_trial_from_result(result),
        rollout,
        host_audit,
    )
    recorded = dict(result.get("protocol") or {})
    budget = recorded.pop("budget_attestation", None)
    recorded_compliant = recorded.pop("compliant", None)
    recomputed_compliant = bool(recomputed.pop("compliant", False))
    expected_compliant = bool(
        recomputed_compliant
        and isinstance(budget, dict)
        and budget.get("compliant") is True
    )
    if recorded != recomputed or recorded_compliant is not expected_compliant:
        raise ValueError(f"recorded protocol summary disagrees with raw artifacts: {key}")
    observed = budget.get("observed") if isinstance(budget, dict) else None
    usage = _agent_usage_counts(rollout)
    recomputed_test_runs = sum(
        1
        for command in _tool_commands(rollout, host_audit)
        if TEST_RUN_COMMAND.search(command.splitlines()[0] if command else "")
    )
    if (
        not isinstance(observed, dict)
        or observed.get("token_usage") != usage
        or observed.get("model_steps") != usage["model_steps"]
        or observed.get("noncached_tokens") != usage["noncached_tokens"]
        or observed.get("gui_actions")
        != int((recomputed.get("cua_evidence") or {}).get("host_audited_actions", 0))
        or observed.get("test_runs") != recomputed_test_runs
    ):
        raise ValueError(f"budget summary disagrees with raw rollout evidence: {key}")
    if result["trial"]["condition"] == "cua" and result.get("scorable") is True:
        screenshots = [
            path
            for path in rollout.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        if not screenshots or not any(path.stat().st_size > 0 for path in screenshots):
            raise ValueError(f"browser-use result lacks durable screenshot evidence: {key}")


def _validate_verifier_artifacts(trial_dir: Path, result: dict[str, Any]) -> None:
    key = str(result["trial"]["key"])
    task_id = str(result["trial"]["task_id"])
    result_root = trial_dir / "result" / task_id
    patch_path = result_root / "patch.diff"
    report_path = result_root / "verifier_report.json"
    run_result_path = result_root / "run_result.json"
    if not all(path.is_file() for path in (patch_path, report_path, run_result_path)):
        raise ValueError(f"completed trial lacks durable verifier artifacts: {key}")
    try:
        report = VerifierReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        durable_run_result = RunResult.model_validate_json(
            run_result_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ValueError(f"invalid durable verifier artifacts: {key}: {exc}") from exc
    if (
        report.success is not result["verifier_success"]
        or durable_run_result.success is not report.success
        or durable_run_result.task_id != task_id
        or durable_run_result.progress != report.progress
        or result.get("progress") != report.progress
        or durable_run_result.model_dump() != result.get("run_result")
    ):
        raise ValueError(f"verifier summary disagrees with durable artifacts: {key}")


def _validate_verifier_containment(key: str, attestation: dict[str, Any]) -> None:
    verifier_containment = attestation.get("verifier_containment")
    if not isinstance(verifier_containment, dict):
        raise ValueError(f"verifier containment evidence is missing: {key}")
    pre_verifier_roots = verifier_containment.get("pre_verifier_root_identities")
    if (
        verifier_containment.get("backend") != "bubblewrap"
        or verifier_containment.get("network_namespace")
        != "host_shared_for_loopback_application"
        or verifier_containment.get("environment_policy")
        != "empty_then_allowlisted"
        or verifier_containment.get("verifier_root_read_only") is not True
        or verifier_containment.get("rollout_root_read_only") is not True
        or verifier_containment.get("artifact_root_pinned") is not True
        or verifier_containment.get("browser_runtime_read_only") is not True
        or verifier_containment.get("verifier_external_to_agent_workspace") is not True
        or verifier_containment.get("artifacts_external_to_agent_workspace") is not True
        or verifier_containment.get("evaluator_mount_namespace")
        != "/run/cua-swe-evaluator"
        or verifier_containment.get(
            "application_started_before_evaluator_materialization"
        )
        is not True
        or not isinstance(pre_verifier_roots, dict)
        or pre_verifier_roots
        != verifier_containment.get("post_verifier_root_identities")
        or set(pre_verifier_roots)
        != {"workspace", "rollout", "verifiers", "verifier_artifacts"}
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(verifier_containment.get("verifier_digest_before") or ""),
        )
        is None
        or verifier_containment.get("verifier_digest_before")
        != verifier_containment.get("verifier_digest_after")
    ):
        raise ValueError(f"verifier containment evidence is incomplete: {key}")


def _validate_budget_attestation(
    key: str,
    protocol: dict[str, Any],
    *,
    expect_compliant: bool,
) -> None:
    budget = protocol.get("budget_attestation")
    limits = budget.get("limits") if isinstance(budget, dict) else None
    observed = budget.get("observed") if isinstance(budget, dict) else None
    names = {
        "wall_time_sec",
        "model_steps",
        "gui_actions",
        "test_runs",
        "noncached_tokens",
    }
    if (
        not isinstance(budget, dict)
        or budget.get("compliant") is not expect_compliant
        or budget.get("enforcement")
        not in {
            "hard_wall_timeout_and_post_run_protocol_rejection",
            "hard_wall_timeout_with_post_run_budget_diagnostics",
        }
        or not isinstance(limits, dict)
        or not isinstance(observed, dict)
        or not names.issubset(limits)
        or not names.issubset(observed)
        or any(not isinstance(limits[name], (int, float)) for name in names)
        or any(not isinstance(observed[name], (int, float)) for name in names)
        or not isinstance(budget.get("exceeded"), list)
    ):
        raise ValueError(f"budget attestation is incomplete: {key}")
    actual_exceeded = sorted(
        name for name in names if observed[name] > limits[name]
    )
    if sorted(budget["exceeded"]) != actual_exceeded:
        raise ValueError(f"budget exceedance evidence disagrees with limits: {key}")


def _validate_input_custody(
    key: str,
    result: dict[str, Any],
    *,
    expected_task: dict[str, Any],
    expected_harness_digest: str,
) -> None:
    custody = result.get("input_custody")
    required_hashes = (
        "task_file_sha256",
        "task_input_sha256",
        "instruction_sha256",
        "source_only_sha256",
        "copied_source_only_sha256",
        "verifier_sha256",
        "harness_sha256",
    )
    if (
        not isinstance(custody, dict)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(custody.get(field) or ""))
            is None
            for field in required_hashes
        )
    ):
        raise ValueError(f"input custody evidence is incomplete: {key}")
    symlinks = custody.get("source_symlinks")
    if not isinstance(symlinks, dict) or any(
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or not isinstance(target, str)
        or not target
        or Path(target).is_absolute()
        for relative, target in symlinks.items()
    ):
        raise ValueError(f"source symlink custody evidence is invalid: {key}")
    expected = {
        "task_file_sha256": expected_task.get("task_file_sha256"),
        "task_input_sha256": expected_task.get("task_digest"),
        "instruction_sha256": expected_task.get("instruction_sha256"),
        "source_only_sha256": expected_task.get("source_only_sha256"),
        "copied_source_only_sha256": expected_task.get("source_only_sha256"),
        "source_symlinks": expected_task.get("source_symlinks"),
        "verifier_sha256": expected_task.get("verifier_sha256"),
        "harness_sha256": expected_harness_digest,
    }
    if custody != expected:
        raise ValueError(f"input custody evidence disagrees with canonical inputs: {key}")


def _parse_attested_time(key: str, name: str, attestation: dict[str, Any]) -> datetime:
    raw = attestation.get(name)
    if not isinstance(raw, str):
        raise ValueError(f"lifecycle timestamp {name} is missing: {key}")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"lifecycle timestamp {name} is invalid: {key}") from exc
    if value.tzinfo is None:
        raise ValueError(f"lifecycle timestamp {name} lacks timezone: {key}")
    return value


def _validate_public_app_lifecycle(
    key: str,
    result: dict[str, Any],
    attestation: dict[str, Any],
) -> None:
    condition = str(result["trial"]["condition"])
    expected_url = f"http://127.0.0.1:{int(result['trial']['port'])}"
    start = attestation.get("public_app_start")
    cleanup = attestation.get("public_app_cleanup")
    evaluation_start = attestation.get("evaluation_app_start")
    evaluation_cleanup = attestation.get("evaluation_app_cleanup")
    if condition == "cua":
        if (
            not isinstance(start, dict)
            or start.get("backend") != "bubblewrap"
            or start.get("ready") is not True
            or start.get("url") != expected_url
            or not isinstance(start.get("commands"), list)
            or not start["commands"]
            or not all(isinstance(command, str) and command for command in start["commands"])
            or not isinstance(start.get("pids"), list)
            or len(start["pids"]) != len(start["commands"])
            or not all(isinstance(pid, int) and pid > 0 for pid in start["pids"])
            or not isinstance(cleanup, dict)
            or cleanup.get("url") != expected_url
            or cleanup.get("port_closed") is not True
            or not isinstance(cleanup.get("results"), list)
            or len(cleanup["results"]) != len(start["commands"])
            or not all(
                isinstance(item, dict) and isinstance(item.get("exit_code"), int)
                for item in cleanup["results"]
            )
        ):
            raise ValueError(f"CUA public application lifecycle evidence is incomplete: {key}")
    elif condition == "code-only":
        if start is not None or cleanup is not None:
            raise ValueError(f"code-only trial launched a public application: {key}")
    else:
        raise ValueError(f"unknown trial condition: {condition}")
    if (
        not isinstance(evaluation_start, dict)
        or evaluation_start.get("backend") != "bubblewrap"
        or evaluation_start.get("ready") is not True
        or evaluation_start.get("url") != expected_url
        or not isinstance(evaluation_start.get("commands"), list)
        or not evaluation_start["commands"]
        or not isinstance(evaluation_cleanup, dict)
        or evaluation_cleanup.get("url") != expected_url
        or evaluation_cleanup.get("port_closed") is not True
        or attestation.get("evaluation_app_start_preserved_source") is not True
        or attestation.get("evaluation_app_source_sha256_before_start")
        != attestation.get("evaluation_app_source_sha256_after_start")
    ):
        raise ValueError(f"external evaluation application lifecycle is incomplete: {key}")
    agent_finished = _parse_attested_time(key, "agent_finished_at", attestation)
    cleanup_finished = _parse_attested_time(
        key, "public_app_cleanup_finished_at", attestation
    )
    verifier_started = _parse_attested_time(key, "verifier_started_at", attestation)
    verifier_finished = _parse_attested_time(key, "verifier_finished_at", attestation)
    evaluation_started = _parse_attested_time(
        key, "evaluation_app_started_at", attestation
    )
    evaluation_cleanup_finished = _parse_attested_time(
        key, "evaluation_app_cleanup_finished_at", attestation
    )
    if not (
        agent_finished
        <= cleanup_finished
        <= evaluation_started
        <= verifier_started
        <= verifier_finished
        <= evaluation_cleanup_finished
    ):
        raise ValueError(f"public application and verifier lifecycle order is invalid: {key}")


def _validate_unscorable_treatment_result(root: Path, result: dict[str, Any]) -> None:
    """Validate a real verifier outcome excluded only for treatment contamination."""
    key = str(result["trial"]["key"])
    if (
        result.get("scorable") is not False
        or result.get("infrastructure_error") is not False
        or result.get("status") != "protocol_error"
    ):
        raise ValueError(f"invalid unscorable treatment result: {key}")
    protocol = result.get("protocol") or {}
    if (
        (protocol.get("audit_integrity") or {}).get("valid") is not True
        or protocol.get("compliant") is not False
    ):
        raise ValueError(f"unscorable treatment lacks valid noncompliance evidence: {key}")
    budget = protocol.get("budget_attestation") or {}
    if not isinstance(budget.get("compliant"), bool):
        raise ValueError(f"unscorable treatment lacks budget evidence: {key}")
    _validate_budget_attestation(
        key,
        protocol,
        expect_compliant=bool(budget["compliant"]),
    )
    if (
        not isinstance(result.get("verifier_success"), bool)
        or result.get("benchmark_success") is not result["verifier_success"]
        or result.get("causal_success") is not None
    ):
        raise ValueError(f"unscorable treatment altered the verifier outcome: {key}")
    agent = result.get("agent") or {}
    if not isinstance(agent.get("exit_code"), int):
        raise ValueError(f"unscorable treatment lacks agent exit status: {key}")
    trial_dir = root / _trial_relative_dir(result)
    _validate_raw_protocol_evidence(trial_dir, result)
    _validate_verifier_artifacts(trial_dir, result)
    attestation_path = trial_dir / "isolation_attestation.json"
    if not attestation_path.is_file():
        raise ValueError(f"missing isolation attestation: {key}")
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    if attestation.get("verifier_present_during_agent") is not False:
        raise ValueError(f"verifier was present during agent execution: {key}")
    _validate_public_app_lifecycle(key, result, attestation)
    _validate_verifier_containment(key, attestation)


def _validate_scorable_result(root: Path, result: dict[str, Any]) -> None:
    key = str(result["trial"]["key"])
    trial_dir = root / _trial_relative_dir(result)
    if result.get("scorable") is not True or result.get("infrastructure_error") is not False:
        raise ValueError(f"result is not scorable: {key}")
    if result.get("status") not in {"completed", "agent_error"}:
        raise ValueError(f"scorable result has invalid status: {key}")
    if not isinstance(result.get("verifier_success"), bool):
        raise ValueError(f"scorable result lacks boolean verifier_success: {key}")
    protocol = result.get("protocol") or {}
    if (protocol.get("audit_integrity") or {}).get("valid") is not True:
        raise ValueError(f"scorable result lacks valid host-audit integrity: {key}")
    condition = result["trial"]["condition"]
    if protocol.get("compliant") is not True:
        raise ValueError(f"scorable result is not treatment-compliant: {key}")
    _validate_budget_attestation(key, protocol, expect_compliant=True)
    assignment = protocol.get("treatment_assignment") or {}
    if (
        assignment.get("analysis_policy") != "intent_to_treat"
        or assignment.get("browser_capability_assigned")
        is not (condition == "cua")
        or not isinstance(assignment.get("browser_capability_used"), bool)
    ):
        raise ValueError(f"treatment assignment evidence is incomplete: {key}")
    cua = protocol.get("cua_evidence") or {}
    if condition == "cua":
        if (
            cua.get("capability_assigned") is not True
            or cua.get("capability_used")
            is not assignment["browser_capability_used"]
        ):
            raise ValueError(f"browser capability assignment is not attested: {key}")
    elif condition == "code-only":
        if protocol.get("forbidden_actions") or protocol.get("hidden_material_attempts"):
            raise ValueError(f"code-only result contains forbidden actions: {key}")
    else:
        raise ValueError(f"unknown trial condition: {condition}")
    expected_causal_success = bool(result["verifier_success"]) and (
        condition != "cua" or bool(cua.get("evidenced"))
    )
    if (
        result.get("benchmark_success") is not result["verifier_success"]
        or result.get("causal_success") is not expected_causal_success
    ):
        raise ValueError(f"task success is not the protected verifier result: {key}")
    agent = result.get("agent") or {}
    if not isinstance(agent.get("exit_code"), int):
        raise ValueError(f"scorable result lacks agent exit status: {key}")
    if result["status"] == "completed" and agent["exit_code"] != 0:
        raise ValueError(f"completed result records a nonzero agent exit: {key}")
    if result["status"] == "agent_error" and agent["exit_code"] == 0:
        raise ValueError(f"agent_error result records a successful agent exit: {key}")
    _validate_raw_protocol_evidence(trial_dir, result)
    _validate_verifier_artifacts(trial_dir, result)
    attestation_path = trial_dir / "isolation_attestation.json"
    if not attestation_path.is_file():
        raise ValueError(f"missing isolation attestation: {key}")
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    if attestation.get("backend") != "bubblewrap":
        raise ValueError(f"protected run did not use bubblewrap: {key}")
    if attestation.get("verifier_present_during_agent") is not False:
        raise ValueError(f"verifier was present during agent execution: {key}")
    _validate_public_app_lifecycle(key, result, attestation)
    _validate_probe_attestation(key, "post_setup_top_level", attestation)
    for phase in ("pre_setup", "post_setup"):
        phase_attestation = attestation.get(phase) or {}
        _validate_probe_attestation(key, phase, phase_attestation)
    if attestation.get("workspace_outside_benchmark_repo") is not True:
        raise ValueError(f"agent workspace was not external: {key}")
    if attestation.get("fresh_git_history") is not True:
        raise ValueError(f"fresh source-only Git history is not attested: {key}")
    pre_agent_source = str(attestation.get("pre_agent_source_sha256") or "")
    post_common_setup_source = str(
        attestation.get("post_common_setup_source_sha256") or ""
    )
    if (
        re.fullmatch(r"[0-9a-f]{64}", pre_agent_source) is None
        or pre_agent_source != post_common_setup_source
        or attestation.get("public_app_start_preserved_source") is not True
        or set(attestation.get("pre_agent_source_excludes") or [])
        != set(PRE_AGENT_SOURCE_EXCLUDES)
    ):
        raise ValueError(f"pre-agent source custody evidence is incomplete: {key}")
    pre_agent_roots = attestation.get("pre_agent_root_identities")
    post_agent_roots = attestation.get("post_agent_root_identities")
    if (
        attestation.get("protected_root_identities_unchanged") is not True
        or not isinstance(pre_agent_roots, dict)
        or pre_agent_roots != post_agent_roots
        or set(pre_agent_roots) != {"workspace", "rollout"}
    ):
        raise ValueError(f"protected root identity evidence is incomplete: {key}")
    patch_containment = attestation.get("patch_containment")
    pre_patch_roots = (
        patch_containment.get("pre_patch_root_identities")
        if isinstance(patch_containment, dict)
        else None
    )
    if (
        not isinstance(patch_containment, dict)
        or patch_containment.get("backend") != "bubblewrap"
        or patch_containment.get("network_namespace") != "isolated"
        or patch_containment.get("environment_policy") != "empty_then_allowlisted"
        or patch_containment.get("workspace_read_only") is not True
        or patch_containment.get("rollout_root_read_only") is not True
        or patch_containment.get("git_external_diff_disabled") is not True
        or patch_containment.get("git_textconv_disabled") is not True
        or patch_containment.get("git_fsmonitor_disabled") is not True
        or not isinstance(pre_patch_roots, dict)
        or pre_patch_roots != patch_containment.get("post_patch_root_identities")
        or set(pre_patch_roots) != {"workspace", "rollout"}
    ):
        raise ValueError(f"patch containment evidence is incomplete: {key}")
    _validate_verifier_containment(key, attestation)
    if not PROTECTED_MATERIAL_NAMES.issubset(set(attestation.get("source_excludes") or [])):
        raise ValueError(f"protected source exclusions are incomplete: {key}")
    tools = set(attestation.get("condition_tools") or [])
    expected_tools = set(
        _expected_tool_names(condition, str(result["model"]["runtime"]))
    )
    if tools != expected_tools:
        raise ValueError(f"condition tool packet has unexpected capabilities: {key}")
    package_present = attestation.get("condition_python_package_present")
    if package_present is not (condition == "cua"):
        raise ValueError(f"condition-specific Python package isolation failed: {key}")
    broker_cleanup = attestation.get("broker_cleanup")
    if condition == "cua":
        if (
            not isinstance(broker_cleanup, dict)
            or broker_cleanup.get("strace_kill_on_exit") is not True
            or broker_cleanup.get("network_audit_complete") is not True
            or not isinstance(broker_cleanup.get("traced_pid_count"), int)
            or broker_cleanup["traced_pid_count"] <= 0
            or broker_cleanup.get("live_descendants_after_stop") != []
        ):
            raise ValueError(f"broker descendant cleanup evidence is incomplete: {key}")
    elif broker_cleanup is not None:
        raise ValueError(f"code-only trial unexpectedly launched a CUA broker: {key}")
    if attestation.get("condition_tool_packet_sha256") != _expected_tool_packet_digest(
        condition,
        str(result["model"]["runtime"]),
    ):
        raise ValueError(f"condition tool packet digest does not match the harness: {key}")


def merge_shards(args: argparse.Namespace) -> Path:
    if not args.output_root:
        raise ValueError("--merge-shard requires --output-root")
    if not args.luna_workflow:
        raise ValueError("--merge-shard requires --luna-workflow")
    if (
        args.resume
        or args.dry_run
        or args.run_attempt
        or args.retry_key
        or args.shard_id
        or args.execution_host
    ):
        raise ValueError(
            "--merge-shard cannot be combined with execution or resume options"
        )
    canonical_trials = _all_trials(args)
    expected_manifest = _manifest_payload(args, canonical_trials)
    expected_signature = expected_manifest["evaluation_signature"]
    expected_keys = {trial.key for trial in canonical_trials}
    canonical_by_key = {item["key"]: item for item in expected_manifest["trials"]}
    results_by_key: dict[str, list[dict[str, Any]]] = {}
    roots: list[Path] = []
    shard_records: list[dict[str, Any]] = []
    seen_shard_ids: set[str] = set()
    runtime_reference: dict[str, Any] | None = None
    origin_host_by_key: dict[str, str] = {}
    origin_evidence_by_key: dict[str, dict[str, Any]] = {}
    paired_shard_by_key: dict[str, str] = {}
    retry_selections: list[tuple[str, str, set[str]]] = []
    for raw_root in args.merge_shard:
        unresolved_root = raw_root.expanduser().absolute()
        _reject_symlink_tree(unresolved_root, "merge shard")
        root = unresolved_root.resolve()
        manifest_path = root / "manifest.json"
        summary_path = root / "summary.json"
        if not manifest_path.is_file() or not summary_path.is_file():
            raise ValueError(f"incomplete shard root: {root}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("evaluation_signature") != expected_signature:
            raise ValueError(f"shard evaluation signature does not match: {root}")
        if manifest.get("evaluation_harness_digest") != expected_manifest["evaluation_harness_digest"]:
            raise ValueError(f"shard harness digest does not match: {root}")
        shard_id = str(manifest.get("shard_id") or "")
        execution_host = str(manifest.get("execution_host") or "")
        actual_hostname = str(manifest.get("actual_hostname") or "")
        selection_mode = str(manifest.get("selection_mode") or "")
        runtime = manifest.get("runtime_provenance")
        if (
            not shard_id
            or not execution_host
            or not actual_hostname
            or shard_id in seen_shard_ids
        ):
            raise ValueError(f"shard identity is missing or duplicated: {root}")
        if not isinstance(runtime, dict):
            raise ValueError(f"shard runtime provenance is missing: {root}")
        if runtime_reference is None:
            runtime_reference = runtime
        elif runtime != runtime_reference:
            raise ValueError(f"shard runtime provenance does not match: {root}")
        seen_shard_ids.add(shard_id)
        planned_order = list(manifest.get("selected_trial_keys") or [])
        selected_keys = set(planned_order)
        if not selected_keys or not selected_keys.issubset(expected_keys):
            raise ValueError(f"shard has invalid selected trial keys: {root}")
        expected_order = [trial.key for trial in canonical_trials if trial.key in selected_keys]
        if planned_order != expected_order:
            raise ValueError(f"shard trial selection is not in canonical order: {root}")
        if selection_mode == "paired_attempt_shard":
            groups: dict[tuple[str, str, int], set[str]] = {}
            for key in selected_keys:
                prior_shard = paired_shard_by_key.setdefault(key, shard_id)
                if prior_shard != shard_id:
                    raise ValueError(
                        f"canonical trial was allocated to multiple paired shards: {key}"
                    )
                item = canonical_by_key[key]
                group = (str(item["task_id"]), str(item["model_key"]), int(item["attempt"]))
                groups.setdefault(group, set()).add(str(item["condition"]))
                prior_host = origin_host_by_key.setdefault(key, actual_hostname)
                if prior_host != actual_hostname:
                    raise ValueError(f"canonical trial was allocated to multiple hosts: {key}")
            if not groups or any(conditions != set(CONDITIONS) for conditions in groups.values()):
                raise ValueError(f"attempt shard does not contain complete condition pairs: {root}")
        elif selection_mode == "pair_retry":
            retry_groups: dict[tuple[str, str, int], set[str]] = {}
            for key in selected_keys:
                item = canonical_by_key[key]
                group = (str(item["task_id"]), str(item["model_key"]), int(item["attempt"]))
                retry_groups.setdefault(group, set()).add(str(item["condition"]))
            if not retry_groups or any(
                conditions != set(CONDITIONS)
                for conditions in retry_groups.values()
            ):
                raise ValueError(f"retry shard does not contain complete condition pairs: {root}")
            retry_selections.append((shard_id, actual_hostname, selected_keys))
        else:
            raise ValueError(f"unsupported shard selection mode {selection_mode!r}: {root}")
        shard_results = json.loads(summary_path.read_text(encoding="utf-8")).get(
            "results", []
        )
        result_keys = {str(result["trial"]["key"]) for result in shard_results}
        if len(result_keys) != len(shard_results) or not result_keys.issubset(selected_keys):
            raise ValueError(f"shard results are not a valid fail-fast prefix: {root}")
        if list(result["trial"]["key"] for result in shard_results) != planned_order[: len(shard_results)]:
            raise ValueError(f"shard results are not in deterministic fail-fast order: {root}")
        for result in shard_results:
            key = str(result["trial"]["key"])
            trial_dir = _validate_result_identity(
                root,
                result,
                canonical_by_key[key],
                expected_manifest["models"][canonical_by_key[key]["model_key"]],
                expected_manifest["tasks"][canonical_by_key[key]["task_id"]],
                expected_manifest["evaluation_harness_digest"],
            )
            results_by_key.setdefault(key, []).append(
                {
                    "root": root,
                    "shard_id": shard_id,
                    "actual_hostname": actual_hostname,
                    "selection_mode": selection_mode,
                    "result": result,
                    "trial_dir": trial_dir,
                    "artifact_digest": _directory_digest(trial_dir),
                }
            )
        if selection_mode == "paired_attempt_shard":
            recorded_by_key = {
                str(result["trial"]["key"]): result for result in shard_results
            }
            infrastructure_positions = [
                index
                for index, key in enumerate(planned_order)
                if recorded_by_key.get(key, {}).get("infrastructure_error") is True
            ]
            if infrastructure_positions and infrastructure_positions != [
                len(shard_results) - 1
            ]:
                raise ValueError(
                    f"paired shard did not stop immediately after infrastructure failure: {root}"
                )
            for index, key in enumerate(planned_order):
                origin_evidence_by_key[key] = {
                    "actual_hostname": actual_hostname,
                    "recorded_result": recorded_by_key.get(key),
                    "preceded_by_fail_fast_infrastructure": any(
                        position < index for position in infrastructure_positions
                    ),
                }
        shard_records.append(
            {
                "shard_id": shard_id,
                "execution_host": execution_host,
                "actual_hostname": actual_hostname,
                "selection_mode": selection_mode,
                "root": str(root),
                "manifest_sha256": _sha256_file(manifest_path),
                "summary_sha256": _sha256_file(summary_path),
                "selected_trial_keys": planned_order,
                "recorded_trial_keys": [str(result["trial"]["key"]) for result in shard_results],
            }
        )
        roots.append(root)
    retry_shard_by_key: dict[str, str] = {}
    for retry_shard, retry_host, retry_keys in retry_selections:
        pair_has_retryable_antecedent = False
        for key in retry_keys:
            origin_host = origin_host_by_key.get(key)
            if not origin_host:
                raise ValueError(f"retry has no paired-attempt antecedent: {key}")
            if origin_host != retry_host:
                raise ValueError(f"retry changed the physical host for paired trial: {key}")
            evidence = origin_evidence_by_key.get(key) or {}
            antecedent = evidence.get("recorded_result")
            retryable = (
                isinstance(antecedent, dict)
                and antecedent.get("scorable") is False
            ) or (
                antecedent is None
                and evidence.get("preceded_by_fail_fast_infrastructure") is True
            )
            pair_has_retryable_antecedent = pair_has_retryable_antecedent or retryable
            if key in retry_shard_by_key:
                raise ValueError(f"multiple retry shards target the same pair member: {key}")
            retry_shard_by_key[key] = retry_shard
        if not pair_has_retryable_antecedent:
            raise ValueError("pair retry has no retryable antecedent")
    missing = sorted(expected_keys.difference(results_by_key))
    extra = sorted(set(results_by_key).difference(expected_keys))
    if missing or extra:
        raise ValueError(f"merged shards are incomplete: missing={missing}, extra={extra}")

    chosen: dict[str, dict[str, Any]] = {}
    unscorable_attempts: list[dict[str, Any]] = []
    superseded_pair_attempts: list[dict[str, Any]] = []
    for key, records in results_by_key.items():
        if any(
            type(record["result"].get("infrastructure_error")) is not bool
            or type(record["result"].get("scorable")) is not bool
            for record in records
        ):
            raise ValueError(f"result has no explicit scoring classification: {key}")
        all_scorable = [
            record
            for record in records
            if record["result"]["scorable"] is True
            and record["result"]["infrastructure_error"] is False
        ]
        retry_shard = retry_shard_by_key.get(key)
        scorable = (
            [record for record in all_scorable if record["shard_id"] == retry_shard]
            if retry_shard
            else all_scorable
        )
        if retry_shard:
            superseded_pair_attempts.extend(
                record
                for record in records
                if record["shard_id"] != retry_shard
                and record["result"].get("scorable") is True
            )
        unscorable = [
            record for record in records if record["result"]["scorable"] is False
        ]
        for record in unscorable:
            result = record["result"]
            if result["infrastructure_error"] is False:
                _validate_unscorable_treatment_result(record["root"], result)
        if len(scorable) != 1:
            raise ValueError(
                f"expected exactly one scorable result for {key}, found {len(scorable)}"
            )
        _validate_scorable_result(scorable[0]["root"], scorable[0]["result"])
        origin_host = origin_host_by_key.get(key)
        if origin_host != scorable[0]["actual_hostname"]:
            raise ValueError(f"scorable retry changed the physical host: {key}")
        chosen[key] = scorable[0]
        unscorable_attempts.extend(unscorable)

    paired_chosen: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for record in chosen.values():
        result = record["result"]
        pair = (
            str(result["trial"]["task_id"]),
            str(result["model"]["key"]),
            int(result["trial"]["attempt"]),
        )
        paired_chosen.setdefault(pair, []).append(record)
    for pair, records in paired_chosen.items():
        if len(records) != 2 or {
            str(record["result"]["trial"]["condition"]) for record in records
        } != set(CONDITIONS):
            raise ValueError(f"chosen results do not form a complete matched pair: {pair}")
        if len({record["actual_hostname"] for record in records}) != 1:
            raise ValueError(f"matched conditions ran on different physical hosts: {pair}")
        if len({int(record["result"]["trial"]["port"]) for record in records}) != 1:
            raise ValueError(f"matched conditions used different runtime ports: {pair}")
        source_digests = set()
        for record in records:
            attestation = json.loads(
                (record["trial_dir"] / "isolation_attestation.json").read_text(
                    encoding="utf-8"
                )
            )
            source_digests.add(str(attestation.get("pre_agent_source_sha256") or ""))
        if len(source_digests) != 1 or re.fullmatch(
            r"[0-9a-f]{64}", next(iter(source_digests), "")
        ) is None:
            raise ValueError(f"matched conditions did not share an exact source digest: {pair}")

    run_root = args.output_root.expanduser().resolve()
    if run_root.exists():
        raise ValueError(f"merge output already exists: {run_root}")
    run_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{run_root.name}.merge-", dir=run_root.parent))
    unscorable_records: list[dict[str, Any]] = []
    merged_manifest = {
        **expected_manifest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "shard_id": "merged",
        "execution_host": None,
        "actual_hostname": None,
        "runtime_provenance": runtime_reference,
        "selection_mode": "merged",
        "max_workers": None,
        "selected_trial_keys": sorted(expected_keys),
        "merged_from": [str(root) for root in roots],
    }
    try:
        for key, record in chosen.items():
            result = record["result"]
            relative = _trial_relative_dir(result)
            shutil.copytree(record["trial_dir"], stage / relative)
        for index, record in enumerate(unscorable_attempts, start=1):
            result = record["result"]
            relative = _trial_relative_dir(result)
            reason = (
                "infrastructure_failure"
                if result.get("infrastructure_error") is True
                else "treatment_noncompliance"
            )
            destination = (
                Path(
                    "infrastructure-runs"
                    if reason == "infrastructure_failure"
                    else "treatment-noncompliant-runs"
                )
                / f"{index:02d}-{record['shard_id']}"
                / relative
            )
            shutil.copytree(record["trial_dir"], stage / destination)
            unscorable_records.append(
                {
                    "trial_key": result["trial"]["key"],
                    "shard_id": record["shard_id"],
                    "status": result.get("status"),
                    "reason": reason,
                    "failure": result.get("infrastructure_failure"),
                    "verifier_success": result.get("verifier_success"),
                    "artifact_path": str(destination),
                    "artifact_digest": record["artifact_digest"],
                }
            )
        superseded_records: list[dict[str, Any]] = []
        for index, record in enumerate(superseded_pair_attempts, start=1):
            result = record["result"]
            relative = _trial_relative_dir(result)
            destination = (
                Path("superseded-pair-runs")
                / f"{index:02d}-{record['shard_id']}"
                / relative
            )
            shutil.copytree(record["trial_dir"], stage / destination)
            superseded_records.append(
                {
                    "trial_key": result["trial"]["key"],
                    "shard_id": record["shard_id"],
                    "status": result.get("status"),
                    "verifier_success": result.get("verifier_success"),
                    "artifact_path": str(destination),
                    "artifact_digest": record["artifact_digest"],
                    "reason": "complete_pair_retry_superseded_antecedent",
                }
            )
        _write_json(stage / "manifest.json", merged_manifest)
        _write_json(
            stage / "merge-manifest.json",
            {
                "evaluation_signature": expected_signature,
                "evaluation_harness_digest": expected_manifest["evaluation_harness_digest"],
                "runtime_provenance": runtime_reference,
                "shards": shard_records,
                "canonical_trial_keys": [trial.key for trial in canonical_trials],
                "canonical_artifact_digests": {
                    key: record["artifact_digest"] for key, record in sorted(chosen.items())
                },
                "unscorable_attempts": unscorable_records,
                "superseded_pair_attempts": superseded_records,
                "infrastructure_attempts": [
                    record
                    for record in unscorable_records
                    if record["reason"] == "infrastructure_failure"
                ],
            },
        )
        results = [chosen[trial.key]["result"] for trial in canonical_trials]
        if not _complete_result_set(merged_manifest, results):
            raise ValueError("strict merged result set is incomplete or unscorable")
        write_summary(stage, canonical_trials, results, reported_run_root=run_root)
        write_luna_assessment(stage, merged_manifest, results)
        stage.rename(run_root)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return run_root


def write_summary(
    run_root: Path,
    trials: list[CleanTrial],
    results: list[dict[str, Any]],
    *,
    reported_run_root: Path | None = None,
) -> None:
    summary = {
        "run_root": str(reported_run_root or run_root),
        "trial_count": len(trials),
        "result_count": len(results),
        "experiment": "browser_vs_code_only_evaluation",
        "results": results,
    }
    _write_json(run_root / "summary.json", summary)
    lines = [
        "# Browser-use vs. code-only results",
        "",
        f"Trials completed: {len(results)}/{len(trials)}.",
        "",
        "Success means the evaluation verifier passed after the agent finished. "
        "Evaluation artifacts were not part of either agent workspace.",
        "Provider/harness failures and treatment-noncompliant trajectories are "
        "excluded from success-rate denominators and must be reviewed or rerun. "
        "Their real post-run verifier outcomes remain recorded.",
        "",
        "## Overall",
        "",
        "| Condition | Passed | Total | Success rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for condition in CONDITIONS:
        selected = [
            result
            for result in results
            if result["trial"]["condition"] == condition
            and result.get("scorable") is True
        ]
        passed = sum(bool(item.get("verifier_success")) for item in selected)
        label = "Browser use" if condition == "cua" else "Code only"
        rate = f"{100.0 * passed / len(selected):.1f}%" if selected else "N/A"
        lines.append(f"| {label} | {passed} | {len(selected)} | {rate} |")
    lines.extend(
        [
            "",
            "## By model",
            "",
            "| Model | Browser use | Code only |",
            "| --- | ---: | ---: |",
        ]
    )
    models = {trial.model.key: trial.model for trial in trials}
    for model in models.values():
        values = []
        for condition in CONDITIONS:
            selected = [
                result
                for result in results
                if result["trial"]["condition"] == condition
                and result["model"]["key"] == model.key
                and result.get("scorable") is True
            ]
            values.append(_rate(sum(bool(item.get("verifier_success")) for item in selected), len(selected)))
        lines.append(f"| {model.label} | {values[0]} | {values[1]} |")
    lines.extend(
        [
            "",
            "## By task",
            "",
            "| Task | Browser use | Code only |",
            "| --- | ---: | ---: |",
        ]
    )
    task_ids = list(dict.fromkeys(trial.task_id for trial in trials))
    for task_id in task_ids:
        values = []
        for condition in CONDITIONS:
            selected = [
                result
                for result in results
                if result["trial"]["condition"] == condition
                and result["trial"]["task_id"] == task_id
                and result.get("scorable") is True
            ]
            values.append(_rate(sum(bool(item.get("verifier_success")) for item in selected), len(selected)))
        lines.append(f"| {task_id} | {values[0]} | {values[1]} |")
    (run_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_luna_assessment(
    run_root: Path,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
) -> bool:
    assessment = assess_luna_comparison({"results": results})
    payload = assessment.model_dump()
    payload.update(
        {
            "iteration": manifest["iteration"],
            "evaluation_signature": manifest["evaluation_signature"],
            "success_definition": "verifier_pass",
        }
    )
    _write_json(run_root / "luna-assessment.json", payload)
    for task in assessment.tasks:
        decision = task.model_dump()
        decision.update(
            {
                "schema_version": 1,
                "gate": "luna_comparison",
                "iteration": manifest["iteration"],
                "model_id": LUNA_MODEL_ID,
                "task_digest": manifest["tasks"][task.task_id]["task_digest"],
                "evaluation_signature": manifest["evaluation_signature"],
                "success_definition": "verifier_pass",
                "generated_by": "deterministic_threshold_assessor",
            }
        )
        _write_json(
            run_root
            / "decisions"
            / task.task_id
            / f"iteration-{manifest['iteration']:02d}"
            / "luna-threshold.json",
            decision,
        )
    return assessment.all_advance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the browser-use vs. code-only evaluation")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--base-port", type=int, default=45100)
    parser.add_argument(
        "--max-agent-tokens",
        type=int,
        default=200_000,
        help="shared per-trial non-cached input plus output token budget",
    )
    parser.add_argument("--model", action="append", choices=[model.key for model in MODELS])
    parser.add_argument(
        "--luna-workflow",
        action="store_true",
        help="lock the run to GPT 5.6 Luna and the three-attempt construction gate",
    )
    parser.add_argument(
        "--development-pair",
        action="store_true",
        help="run one matched GPT 5.6 Luna pair for adaptive construction feedback",
    )
    parser.add_argument(
        "--cua-only",
        action="store_true",
        help="run only the audited computer-use condition; do not schedule code-only trials",
    )
    parser.add_argument(
        "--code-only-only",
        action="store_true",
        help="run only the code-only condition; do not schedule computer-use trials",
    )
    parser.add_argument(
        "--visual-cua",
        action="store_true",
        help="expose screenshot paths only and lock the run to one GPT 5.6 CUA attempt per task",
    )
    parser.add_argument(
        "--evaluation-matrix",
        action="store_true",
        help=(
            "allow multiple explicitly selected models and parallel workers in "
            "a protected one-attempt code-only or screenshot-CUA shard"
        ),
    )
    parser.add_argument("--task", action="append", choices=TASK_NAMES)
    parser.add_argument(
        "--task-file",
        action="append",
        type=Path,
        help="task.yaml path; repeat for each regenerated task",
    )
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument(
        "--run-attempt",
        action="append",
        type=int,
        help="execute every selected condition for this canonical attempt; repeat as needed",
    )
    parser.add_argument(
        "--retry-key",
        action="append",
        metavar="CANONICAL-TRIAL-KEY",
        help="select both canonical keys for a complete matched-pair retry shard",
    )
    parser.add_argument(
        "--shard-id",
        help="durable shard label; required for attempt/retry execution",
    )
    parser.add_argument(
        "--execution-host",
        help="evaluation host label; required for attempt/retry execution",
    )
    parser.add_argument(
        "--merge-shard",
        action="append",
        type=Path,
        help="completed shard root to validate and merge; repeat for every shard",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--staging-check",
        action="store_true",
        help="run one non-model protected retained-app staging demonstration",
    )
    parser.add_argument(
        "--responsive-capability-check",
        action="store_true",
        help="with --staging-check, apply gold and replay retained-page responsive CUA actions",
    )
    parser.add_argument(
        "--responsive-baseline-check",
        action="store_true",
        help="with --staging-check, replay the expected broken baseline through responsive CUA actions",
    )
    parser.add_argument(
        "--protocol-replay-root",
        type=Path,
        help="non-mutating re-audit of a sealed matched-pair run root",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume an existing --output-root using its recorded summary",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(os.environ.get("CUA_SWE_PYTHON", sys.executable)),
        help="Python 3.11+ runtime visible inside the evaluation sandbox",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.attempts < 1:
        raise SystemExit("--attempts must be positive")
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be positive")
    if args.max_agent_tokens < 1:
        raise SystemExit("--max-agent-tokens must be positive")
    if args.iteration < 1:
        raise SystemExit("--iteration must be positive")
    if args.responsive_capability_check and not args.staging_check:
        raise SystemExit("--responsive-capability-check requires --staging-check")
    if args.responsive_baseline_check and not args.staging_check:
        raise SystemExit("--responsive-baseline-check requires --staging-check")
    if args.responsive_capability_check and args.responsive_baseline_check:
        raise SystemExit(
            "--responsive-capability-check and --responsive-baseline-check are mutually exclusive"
        )
    if args.staging_check and (
        args.luna_workflow
        or args.development_pair
        or args.visual_cua
        or args.evaluation_matrix
        or args.cua_only
        or args.code_only_only
        or args.model
        or args.task
        or args.run_attempt
        or args.retry_key
        or args.shard_id
        or args.execution_host
        or args.merge_shard
        or args.resume
        or args.dry_run
        or len(args.task_file or []) != 1
        or args.output_root is None
    ):
        raise SystemExit(
            "--staging-check requires exactly one --task-file and --output-root, "
            "and cannot be combined with evaluation, shard, merge, resume, or dry-run options"
        )
    if args.protocol_replay_root and (
        args.staging_check
        or args.luna_workflow
        or args.development_pair
        or args.visual_cua
        or args.evaluation_matrix
        or args.cua_only
        or args.code_only_only
        or args.model
        or args.task
        or args.task_file
        or args.run_attempt
        or args.retry_key
        or args.shard_id
        or args.execution_host
        or args.merge_shard
        or args.resume
        or args.dry_run
        or args.output_root is None
    ):
        raise SystemExit(
            "--protocol-replay-root requires only --output-root and cannot be "
            "combined with evaluation, staging, shard, merge, resume, or dry-run options"
        )
    if args.luna_workflow and args.development_pair:
        raise SystemExit("--luna-workflow and --development-pair are mutually exclusive")
    if args.evaluation_matrix and not (args.code_only_only or args.visual_cua):
        raise SystemExit(
            "--evaluation-matrix requires --code-only-only or --visual-cua"
        )
    if args.evaluation_matrix and not args.model:
        raise SystemExit("--evaluation-matrix requires at least one --model")
    if args.visual_cua and (args.luna_workflow or args.development_pair):
        raise SystemExit("--visual-cua cannot be combined with Luna paired workflows")
    if args.cua_only and (args.luna_workflow or args.development_pair):
        raise SystemExit("--cua-only cannot be combined with Luna paired workflows")
    if args.code_only_only and (args.luna_workflow or args.development_pair):
        raise SystemExit("--code-only-only cannot be combined with Luna paired workflows")
    if args.code_only_only and args.cua_only:
        raise SystemExit("--code-only-only and --cua-only are mutually exclusive")
    if args.code_only_only and args.visual_cua:
        raise SystemExit("--code-only-only and --visual-cua are mutually exclusive")
    if args.code_only_only and args.attempts != 1:
        raise SystemExit("--code-only-only requires exactly one attempt per task")
    if (
        args.code_only_only
        and not args.evaluation_matrix
        and (not args.model or len(set(args.model)) != 1)
    ):
        raise SystemExit("--code-only-only requires exactly one --model")
    if args.visual_cua and not args.cua_only:
        raise SystemExit("--visual-cua requires --cua-only")
    if args.visual_cua and args.attempts != 1:
        raise SystemExit("--visual-cua requires exactly one attempt per task")
    if (
        args.visual_cua
        and not args.evaluation_matrix
        and (not args.model or len(set(args.model)) != 1)
    ):
        raise SystemExit("--visual-cua requires exactly one --model")
    if args.luna_workflow and args.attempts != 3:
        raise SystemExit("--luna-workflow requires exactly three attempts per condition")
    if args.development_pair and args.attempts != 1:
        raise SystemExit("--development-pair requires exactly one attempt per condition")
    shard_execution = bool(args.run_attempt or args.retry_key)
    if (
        (args.luna_workflow or args.development_pair or args.visual_cua or args.code_only_only)
        and not args.dry_run
        and not args.merge_shard
        and not shard_execution
    ):
        raise SystemExit(
            "protected Luna execution requires a paired-attempt or complete-pair retry shard; "
            "use --run-attempt with --shard-id/--execution-host"
        )
    if shard_execution != bool(args.shard_id and args.execution_host):
        raise SystemExit(
            "--run-attempt/--retry-key require --shard-id and --execution-host"
        )
    if (
        shard_execution
        and (args.luna_workflow or args.development_pair or args.visual_cua or args.code_only_only)
        and not args.evaluation_matrix
        and args.max_workers != 1
    ):
        raise SystemExit("frontier-model shards require --max-workers 1")
    if args.merge_shard:
        try:
            run_root = merge_shards(args)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"MERGED_RUN_ROOT={run_root}", flush=True)
        return 0
    if args.protocol_replay_root:
        try:
            evidence = replay_protocol_evidence(
                input_root=args.protocol_replay_root,
                output_root=args.output_root,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(
            f"PROTOCOL_REPLAY={evidence['status']} "
            f"OUTPUT_ROOT={args.output_root.expanduser().absolute()}",
            flush=True,
        )
        return 0 if evidence["status"] == "pass" else 2
    host_lock = None
    if shard_execution:
        lock_path = Path("/tmp/cua-swe-luna-evaluation.lock")
        host_lock = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(host_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(
                "another protected evaluation shard is already running on this host"
            ) from exc
        host_lock.seek(0)
        host_lock.truncate()
        host_lock.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "shard_id": args.shard_id,
                    "execution_host": args.execution_host,
                    "actual_hostname": socket.gethostname(),
                }
            )
            + "\n"
        )
        host_lock.flush()
    args.python = args.python.expanduser().absolute()
    if not args.python.is_file():
        raise SystemExit(f"evaluation Python does not exist: {args.python}")
    if args.python.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise SystemExit(
            "evaluation Python must be outside the benchmark repository so it "
            "remains available after the repository is masked"
        )
    if args.staging_check:
        evidence = run_staging_demonstration(
            task_file=args.task_file[0],
            output_root=args.output_root.expanduser().absolute(),
            python_bin=args.python,
            port=args.base_port,
            responsive_capability=args.responsive_capability_check,
            responsive_baseline=args.responsive_baseline_check,
        )
        print(
            f"STAGING_CHECK={evidence['status']} "
            f"OUTPUT_ROOT={args.output_root.expanduser().absolute()}",
            flush=True,
        )
        return 0 if evidence["status"] == "pass" else 2
    trials = build_trials(args)
    if args.dry_run:
        print(json.dumps([{"key": trial.key, "port": trial.port} for trial in trials], indent=2))
        return 0
    unresolved_run_root = (
        args.output_root
        or REPO_ROOT / "artifacts" / "clean-ablation" / _utc_stamp()
    ).expanduser().absolute()
    if args.resume:
        try:
            _reject_symlink_tree(unresolved_run_root, "resume output root")
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    run_root = unresolved_run_root.resolve()
    if shard_execution:
        tmp_root = Path("/tmp").resolve()
        repo_root = REPO_ROOT.resolve()
        evaluation_root_text = os.environ.get("CUA_SWE_EVALUATION_ROOT")
        evaluation_root = (
            Path(evaluation_root_text).expanduser().resolve()
            if evaluation_root_text
            else None
        )
        allowed = (
            run_root.is_relative_to(tmp_root)
            or run_root.is_relative_to(repo_root)
            or (
                evaluation_root is not None
                and run_root.is_relative_to(evaluation_root)
            )
        )
        if not allowed:
            raise SystemExit(
                "shard output roots must be under /tmp, the masked benchmark "
                "repository, or CUA_SWE_EVALUATION_ROOT"
            )
    expected_manifest = _manifest_payload(args, trials)
    if args.resume:
        if not run_root.is_dir() or not (run_root / "manifest.json").is_file():
            raise SystemExit("--resume requires an existing clean-ablation --output-root")
        manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("evaluation_signature") != expected_manifest["evaluation_signature"]:
            raise SystemExit(
                "--resume inputs do not match the immutable evaluation signature; "
                "start a new iteration directory"
            )
        if manifest.get("selected_trial_keys") != expected_manifest["selected_trial_keys"]:
            raise SystemExit("--resume shard selection does not match the recorded manifest")
        if manifest.get("shard_id") != expected_manifest["shard_id"]:
            raise SystemExit("--resume shard ID does not match the recorded manifest")
        if manifest.get("execution_host") != expected_manifest["execution_host"]:
            raise SystemExit("--resume execution host does not match the recorded manifest")
        prior_summary = run_root / "summary.json"
        results: list[dict[str, Any]] = (
            json.loads(prior_summary.read_text(encoding="utf-8")).get("results", [])
            if prior_summary.is_file()
            else []
        )
        if any(result.get("infrastructure_error") is True for result in results):
            raise SystemExit(
                "an unscorable shard cannot be resumed; retry only the affected "
                "canonical trial in a new shard output root"
            )
    else:
        run_root.mkdir(parents=True, exist_ok=False)
        results = []
        manifest = expected_manifest
        _write_json(run_root / "manifest.json", manifest)
    print(f"RUN_ROOT={run_root}", flush=True)
    completed_keys = {result["trial"]["key"] for result in results}
    remaining = [trial for trial in trials if trial.key not in completed_keys]
    print(
        f"TRIALS={len(trials)} RECORDED={len(results)} REMAINING={len(remaining)} "
        f"MAX_WORKERS={args.max_workers}",
        flush=True,
    )

    if args.max_workers == 1:
        for trial in remaining:
            result = run_trial(
                trial,
                run_root,
                args.python,
                args.max_agent_tokens,
            )
            results.append(result)
            print(
                f"[{len(results):03d}/{len(trials):03d}] {trial.key} "
                f"status={result['status']} raw={result.get('benchmark_success', False)} "
                f"verifier_pass={result.get('verifier_success', False)} "
                f"duration={result.get('duration_sec', 0):.1f}s",
                flush=True,
            )
            write_summary(run_root, trials, results)
            if result.get("infrastructure_error") is True:
                print(f"FAIL_FAST={trial.key}", flush=True)
                break
    else:
        result_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=min(args.max_workers, len(remaining) or 1)) as executor:
            futures = {
                executor.submit(
                    run_trial,
                    trial,
                    run_root,
                    args.python,
                    args.max_agent_tokens,
                ): trial
                for trial in remaining
            }
            for future in as_completed(futures):
                trial = futures[future]
                result = future.result()
                with result_lock:
                    results.append(result)
                    print(
                        f"[{len(results):03d}/{len(trials):03d}] {trial.key} "
                        f"status={result['status']} raw={result.get('benchmark_success', False)} "
                        f"verifier_pass={result.get('verifier_success', False)} "
                        f"duration={result.get('duration_sec', 0):.1f}s",
                        flush=True,
                    )
                    write_summary(run_root, trials, results)
    write_summary(run_root, trials, results)
    selected_model_ids = {trial.model.model_id for trial in trials}
    if (
        selected_model_ids == {LUNA_MODEL_ID}
        and args.attempts == 3
        and _complete_result_set(manifest, results)
    ):
        all_advance = write_luna_assessment(run_root, manifest, results)
        print(f"LUNA_GATE={'advance' if all_advance else 'not_advance'}", flush=True)
    elif selected_model_ids == {LUNA_MODEL_ID} and args.attempts == 3:
        print("LUNA_GATE=deferred_until_all_shards_merge", flush=True)
    scored = [result for result in results if result.get("scorable") is True]
    unscorable = [result for result in results if result.get("scorable") is False]
    infrastructure_failures = sum(
        result.get("infrastructure_error") is True for result in unscorable
    )
    treatment_failures = len(unscorable) - infrastructure_failures
    passed = sum(bool(result.get("verifier_success")) for result in scored)
    print(
        f"COMPLETE verifier_passes={passed} scored_failures={len(scored) - passed} "
        f"infrastructure_failures={infrastructure_failures} "
        f"treatment_noncompliance={treatment_failures}",
        flush=True,
    )
    return 2 if unscorable else 0


if __name__ == "__main__":
    raise SystemExit(main())
