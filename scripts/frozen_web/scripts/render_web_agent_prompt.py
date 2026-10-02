#!/usr/bin/env python3
"""Render matched web-agent prompts for browser and code-only conditions."""

from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass


CAPABILITY_BLOCK_START = "<!-- CUA-SWE CAPABILITY POLICY START -->"
CAPABILITY_BLOCK_END = "<!-- CUA-SWE CAPABILITY POLICY END -->"
PROMPT_REVISIONS = ("original-web-20260906", "original-gpt6")


def _original_policy(policy: str, revision: str) -> str:
    """Restore the policy used in the selected original evaluation cohort."""
    if revision not in PROMPT_REVISIONS:
        raise ValueError(f"unknown original prompt revision: {revision}")
    if revision == "original-gpt6":
        return policy
    paragraphs = policy.split("\n\n")
    policy = "\n\n".join(
        paragraph for paragraph in paragraphs
        if not paragraph.startswith("IMPORTANT: Do not use curl, wget,")
    )
    return policy.replace(
        "Any direct local-application request invalidates the evaluation row even if the\n"
        "patch passes its verifier.\n",
        "",
    )


@dataclass(frozen=True)
class PromptParts:
    """The common text and the condition-specific capability policy."""

    common_prefix: str
    capability_policy: str
    common_suffix: str


def _common_prefix(*, task_id: str, task_instruction: str) -> str:
    return f"""# CUA-SWE Web Task

You are a coding agent in a broken web application workspace. Solve the task
by inspecting and editing the local application source.

## Task ID

`{task_id}`

## Task

{task_instruction}

## Capability Policy

{CAPABILITY_BLOCK_START}
"""


def _common_suffix(*, build_command: str) -> str:
    return f"""
{CAPABILITY_BLOCK_END}

## Public Task Build Command

```bash
{build_command}
```

## Requirements

1. Make a focused source change that solves the task while preserving the
   application behavior described in the task.
2. You may inspect application source and configuration, edit source files,
   and run the public build command and existing non-browser unit tests.
3. Do not inspect or modify benchmark task files, verifier files, gold or
   negative patches, replay documents, or evaluation artifacts. The benchmark
   harness evaluates the workspace after the agent exits.
4. Do not use web search or external documentation; use the local workspace
   and the capabilities allowed above.
5. Write `rollout_notes.md` in the directory named by
   `CUA_SWE_AGENT_ROLLOUT_DIR`, summarizing the work performed, source files
   inspected and changed, checks run, and any relevant observations.
"""


def _code_only_policy() -> str:
    return """Browser and computer-use capabilities are unavailable in this
condition. Do not launch or access the application through a browser, GUI/CUA
adapter, screenshot or image tool, Playwright, Puppeteer, Selenium, browser
protocol, or HTTP request to the local application. Do not start a development
or preview server.

IMPORTANT: Do not use curl, wget, Python or Node HTTP clients, raw sockets, or
any other mechanism to contact localhost or the retained application. A direct
local-application request invalidates the evaluation row even if the patch
passes its verifier."""


def _browser_policy(
    *,
    launcher: str,
    session_file: str,
    artifacts_dir: str,
    url: str,
    viewport: str,
    observation_mode: str = "structured",
    visual_transport: str = "mcp",
) -> str:
    launcher_q = shlex.quote(launcher)
    session_q = shlex.quote(session_file)
    artifacts_q = shlex.quote(artifacts_dir)
    url_q = shlex.quote(url)
    viewport_q = shlex.quote(viewport)
    observation_mode_q = shlex.quote(observation_mode)
    if observation_mode == "visual":
        if visual_transport == "mcp":
            return f"""Browser GUI capability is available only through the protected
`visual_cua` MCP tools. Start with `visual_cua.start`, then use
`visual_cua.act` for coordinate actions and `visual_cua.observe` when another
observation is needed. Every successful tool result attaches screenshot pixels
directly to the model. Infer the visible UI from those pixels and choose click
and scroll coordinates from the screenshot itself.

The tools do not provide body text, DOM data, element labels, coordinates,
viewport metadata, URL metadata, accessibility trees, or OCR. Do not use the
shell launcher, Playwright, Puppeteer, Selenium, browser developer protocols,
HTTP requests, raw sockets, or any other browser path. The retained application
is already running at `{url}`; do not start, replace, or stop its server.

IMPORTANT: Do not use curl, wget, Python or Node HTTP clients, raw sockets, or
any other mechanism to contact localhost or the retained application. All
runtime application observation must come from screenshot pixels returned by
the protected CUA tools. A direct local-application request invalidates the
evaluation row even if the patch passes its verifier."""
        if visual_transport != "shell":
            raise ValueError(f"unsupported visual transport: {visual_transport}")
        return f"""Browser GUI capability is available only through the protected
CUA-SWE launcher shown below. Do not invoke, inspect, probe, or call
`web_cua_tool.py` directly, and do not use Playwright, Puppeteer, Selenium,
browser developer protocols, HTTP requests, raw sockets, or any other browser
path.

IMPORTANT: Do not use curl, wget, Python or Node HTTP clients, raw sockets, or
any other mechanism to contact localhost or the retained application. All
runtime application observation must come from screenshot pixels returned by
the protected launcher. A direct local-application request invalidates the
evaluation row even if the patch passes its verifier.

Every successful `start`, `observe`, or `act` command returns JSON containing
an `observation.screenshot_path`. Immediately call the `view_image` tool with
that exact path before issuing another browser command. Infer visible UI state
only from the attached screenshot pixels; the JSON itself does not provide DOM,
OCR, accessibility, body-text, element-label, or coordinate metadata.

The retained application is already running at `{url}`; do not start, replace,
or stop its server. Start one protected browser session with this exact shape:

```bash
{launcher_q} start --url {url_q} --artifacts-dir {artifacts_q} \\
  --session-file {session_q} --viewport {viewport_q} \\
  --observation-mode visual
{launcher_q} observe --session-file {session_q}

{launcher_q} act --session-file {session_q} \\
  --kind click --x <x> --y <y>
{launcher_q} act --session-file {session_q} \\
  --kind type --text "<text>"
{launcher_q} act --session-file {session_q} \\
  --kind press --text "<key_or_chord>"
{launcher_q} act --session-file {session_q} \\
  --kind key_hold --text "<one_or_two_keys>" --duration-ms <1_to_2000>
{launcher_q} act --session-file {session_q} \\
  --kind scroll --x <x> --y <y> --delta-y <signed_pixels>
{launcher_q} act --session-file {session_q} \\
  --kind drag --x <start_x> --y <start_y> \\
  --end-x <end_x> --end-y <end_y> --steps <1_to_100>
{launcher_q} act --session-file {session_q} \\
  --kind resize --width <width> --height <height>
{launcher_q} act --session-file {session_q} \\
  --kind wait --duration-ms <1_to_2000>
```

Use only one `start` per browser session. A failed command may be corrected,
but do not probe launcher or adapter help interfaces."""
    elif observation_mode == "structured":
        observation_contract = """Adapter observations provide a screenshot path, body text, viewport and
navigation metadata, and interactive-element centers. Scroll coordinates
select the scroll container beneath the pointer."""
    else:
        raise ValueError(f"unsupported observation mode: {observation_mode}")
    return f"""Browser GUI capability is available only through the protected
CUA-SWE adapter shown below. Do not use Playwright, Puppeteer, Selenium,
browser developer protocols, or task-specific browser automation directly.
Do not query the local application with curl, wget, HTTP libraries, raw
sockets, or terminal-based requests; runtime application evidence must come
through the protected CUA-SWE adapter.
Any direct local-application request invalidates the evaluation row even if the
patch passes its verifier.
The retained application is already running at `{url}`; do not start, replace,
or stop its server.

```bash
{launcher_q} start --url {url_q} --artifacts-dir {artifacts_q} \\
  --session-file {session_q} --viewport {viewport_q} \\
  --observation-mode {observation_mode_q}
{launcher_q} observe --session-file {session_q}

{launcher_q} act --session-file {session_q} \\
  --kind click --x <x> --y <y>
{launcher_q} act --session-file {session_q} \\
  --kind type --text "<text>"
{launcher_q} act --session-file {session_q} \\
  --kind scroll --x <x> --y <y> --delta-y <signed_pixels>
{launcher_q} act --session-file {session_q} \\
  --kind drag --x <start_x> --y <start_y> \\
  --end-x <end_x> --end-y <end_y> --steps <1_to_100>
{launcher_q} act --session-file {session_q} \\
  --kind drag_start --x <start_x> --y <start_y>
{launcher_q} act --session-file {session_q} \\
  --kind drag_move --x <x> --y <y> --steps <1_to_100>
{launcher_q} act --session-file {session_q} \\
  --kind drag_end --x <end_x> --y <end_y> --steps <1_to_100>
{launcher_q} act --session-file {session_q} \\
  --kind resize --width <width> --height <height>
{launcher_q} act --session-file {session_q} --kind back
{launcher_q} act --session-file {session_q} --kind forward
{launcher_q} act --session-file {session_q} --kind wait
```

{observation_contract} A staged drag remains active between `drag_start`,
`drag_move`, and `drag_end`."""


def render_prompt(
    *,
    condition: str,
    task_id: str,
    task_instruction: str,
    build_command: str,
    launcher: str | None = None,
    session_file: str | None = None,
    artifacts_dir: str | None = None,
    url: str | None = None,
    viewport: str | None = None,
    observation_mode: str = "structured",
    visual_transport: str = "mcp",
    prompt_revision: str = "original-web-20260906",
) -> str:
    """Render a prompt whose only condition-specific text is the policy block."""

    if condition == "code-only":
        capability_policy = _code_only_policy()
    elif condition == "browser":
        browser_values = {
            "launcher": launcher,
            "session_file": session_file,
            "artifacts_dir": artifacts_dir,
            "url": url,
            "viewport": viewport,
        }
        missing = [name for name, value in browser_values.items() if not value]
        if missing:
            raise ValueError(
                "browser prompt requires: " + ", ".join(sorted(missing))
            )
        capability_policy = _browser_policy(
            launcher=launcher,
            session_file=session_file,
            artifacts_dir=artifacts_dir,
            url=url,
            viewport=viewport,
            observation_mode=observation_mode,
            visual_transport=visual_transport,
        )
    else:
        raise ValueError(f"unsupported condition: {condition}")

    return (
        _common_prefix(task_id=task_id, task_instruction=task_instruction)
        + _original_policy(capability_policy, prompt_revision)
        + _common_suffix(build_command=build_command)
    )


def parse_prompt(prompt: str) -> PromptParts:
    """Split a prompt so tests can enforce the matched-prompt contract."""

    if prompt.count(CAPABILITY_BLOCK_START) != 1:
        raise ValueError("prompt must contain one capability-policy start marker")
    if prompt.count(CAPABILITY_BLOCK_END) != 1:
        raise ValueError("prompt must contain one capability-policy end marker")
    before, remainder = prompt.split(CAPABILITY_BLOCK_START, 1)
    capability_policy, after = remainder.split(CAPABILITY_BLOCK_END, 1)
    return PromptParts(
        common_prefix=before + CAPABILITY_BLOCK_START,
        capability_policy=capability_policy.strip("\n"),
        common_suffix=CAPABILITY_BLOCK_END + after,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=("browser", "code-only"), required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-instruction", required=True)
    parser.add_argument("--build-command", required=True)
    parser.add_argument(
        "--prompt-revision", choices=PROMPT_REVISIONS,
        default="original-web-20260906",
    )
    parser.add_argument("--launcher")
    parser.add_argument("--session-file")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--url")
    parser.add_argument("--viewport")
    parser.add_argument(
        "--observation-mode",
        choices=("structured", "visual"),
        default="structured",
    )
    parser.add_argument(
        "--visual-transport",
        choices=("mcp", "shell"),
        default="mcp",
    )
    return parser


def main() -> int:
    args = _argument_parser().parse_args()
    print(
        render_prompt(
            condition=args.condition,
            task_id=args.task_id,
            task_instruction=args.task_instruction,
            build_command=args.build_command,
            launcher=args.launcher,
            session_file=args.session_file,
            artifacts_dir=args.artifacts_dir,
            url=args.url,
            viewport=args.viewport,
            observation_mode=args.observation_mode,
            visual_transport=args.visual_transport,
            prompt_revision=args.prompt_revision,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
