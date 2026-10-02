from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
PROMPT_HELPER = SCRIPTS_ROOT / "render_web_agent_prompt.py"


def _load_prompt_helper():
    spec = importlib.util.spec_from_file_location("render_web_agent_prompt", PROMPT_HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_wrapper(
    tmp_path: Path,
    *,
    wrapper_name: str,
    capture_name: str,
    observation_mode: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> list[str]:
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

Path(os.environ["CUA_SWE_TEST_ARGV_CAPTURE"]).write_text(
    json.dumps(sys.argv[1:]), encoding="utf-8"
)
names = ("CUA_SWE_PROVIDER_ROUTES", "CUA_SWE_GATEWAY_TOKEN")
Path(os.environ["CUA_SWE_TEST_ARGV_CAPTURE"] + ".env").write_text(
    json.dumps({name: os.environ.get(name) for name in names}), encoding="utf-8"
)
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    fake_launcher = tmp_path / "web_cua_launcher"
    fake_launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_launcher.chmod(0o755)

    rollout_dir = tmp_path / f"rollout-{capture_name}"
    capture_path = tmp_path / f"{capture_name}.json"
    environment = {
        **os.environ,
        "CUA_SWE_AGENT_ROLLOUT_DIR": str(rollout_dir),
        "CUA_SWE_TASK_ID": "web.prompt-contract.001",
        "CUA_SWE_TASK_INSTRUCTION": "Repair the retained interactive workspace.",
        "CUA_SWE_BUILD_COMMAND": "npm run build -- --mode benchmark",
        "CUA_SWE_AGENT_PYTHON": sys.executable,
        "CUA_SWE_WEB_CUA_PYTHON": sys.executable,
        "CUA_SWE_CODEX_BIN": str(fake_codex),
        "CUA_SWE_WEB_CUA_LAUNCHER": str(fake_launcher),
        "CUA_SWE_TEST_ARGV_CAPTURE": str(capture_path),
        "CUA_SWE_TASK_VALIDATION_FLOW": "LEAKED_VALIDATION_FLOW",
        "CUA_SWE_TASK_CONTEXT": "LEAKED_TASK_CONTEXT",
    }
    for name in ("CUA_SWE_CODEX_BASE_URL", "CUA_SWE_CODEX_API_KEY_ENV", "CUA_SWE_CLAUDE_BASE_URL",
                 "CUA_SWE_PROVIDER_ROUTES", "CUA_SWE_GATEWAY_TOKEN"):
        environment.pop(name, None)
    if observation_mode is not None:
        environment["CUA_SWE_WEB_OBSERVATION_MODE"] = observation_mode
    environment.update(extra_env or {})
    result = subprocess.run(
        ["bash", str(SCRIPTS_ROOT / wrapper_name)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(capture_path.read_text(encoding="utf-8"))


def test_wrappers_render_matched_prompts_with_only_capability_policy_different(
    tmp_path: Path,
):
    helper = _load_prompt_helper()
    browser_argv = _run_wrapper(
        tmp_path,
        wrapper_name="run_web_cua_agent.sh",
        capture_name="browser",
    )
    code_only_argv = _run_wrapper(
        tmp_path,
        wrapper_name="run_code_only_agent.sh",
        capture_name="code-only",
    )

    browser_prompt = browser_argv[-1]
    code_only_prompt = code_only_argv[-1]
    browser_parts = helper.parse_prompt(browser_prompt)
    code_only_parts = helper.parse_prompt(code_only_prompt)

    assert browser_parts.common_prefix == code_only_parts.common_prefix
    assert browser_parts.common_suffix == code_only_parts.common_suffix
    assert browser_parts.capability_policy != code_only_parts.capability_policy
    assert (
        browser_prompt.replace(browser_parts.capability_policy, "<CAPABILITY>")
        == code_only_prompt.replace(code_only_parts.capability_policy, "<CAPABILITY>")
    )

    common_text = browser_parts.common_prefix + browser_parts.common_suffix
    assert "web.prompt-contract.001" in common_text
    assert "Repair the retained interactive workspace." in common_text
    assert "npm run build -- --mode benchmark" in common_text
    assert common_text.count("rollout_notes.md") == 1

    assert "Browser GUI capability is available" in browser_parts.capability_policy
    assert "--kind resize" in browser_parts.capability_policy
    assert "capabilities are unavailable" in code_only_parts.capability_policy
    assert "HTTP request to the local application" in code_only_parts.capability_policy


def test_prompt_contract_has_no_condition_coaching_or_context_leak(tmp_path: Path):
    prompts = []
    for wrapper_name, capture_name in (
        ("run_web_cua_agent.sh", "browser"),
        ("run_code_only_agent.sh", "code-only"),
    ):
        argv = _run_wrapper(
            tmp_path,
            wrapper_name=wrapper_name,
            capture_name=capture_name,
        )
        prompts.append(argv[-1])

    combined = "\n".join(prompts)
    for forbidden in (
        "LEAKED_VALIDATION_FLOW",
        "LEAKED_TASK_CONTEXT",
        "Expected Validation Flow",
        "Additional Context",
        "Reason about the bug statically",
        "Use the CUA adapter CLI to observe the initial app state",
        "reproduce the reported failure",
        "exit promptly",
        "code_only_notes.md",
    ):
        assert forbidden not in combined
    assert all(prompt.count("rollout_notes.md") == 1 for prompt in prompts)


def test_wrapper_model_defaults_match_gpt_56_luna(tmp_path: Path):
    model_defaults = []
    for wrapper_name, capture_name in (
        ("run_web_cua_agent.sh", "browser"),
        ("run_code_only_agent.sh", "code-only"),
    ):
        argv = _run_wrapper(
            tmp_path,
            wrapper_name=wrapper_name,
            capture_name=capture_name,
        )
        model_defaults.append(argv[argv.index("--model") + 1])
        assert 'model_reasoning_effort="medium"' in argv

    assert model_defaults == ["gpt-5.6-luna"] * 2


def test_wrappers_use_builtin_codex_provider_unless_base_url_is_set(tmp_path: Path):
    for wrapper_name, capture_name in (
        ("run_web_cua_agent.sh", "browser"),
        ("run_code_only_agent.sh", "code-only"),
    ):
        default_dir = tmp_path / "default"
        routed_dir = tmp_path / "routed"
        default_dir.mkdir(exist_ok=True)
        routed_dir.mkdir(exist_ok=True)
        default_argv = _run_wrapper(
            default_dir, wrapper_name=wrapper_name, capture_name=capture_name
        )
        assert not any("model_provider" in item for item in default_argv)
        routed_argv = _run_wrapper(
            routed_dir,
            wrapper_name=wrapper_name,
            capture_name=capture_name,
            extra_env={
                "CUA_SWE_CODEX_BASE_URL": "https://gateway.example.test/v1",
                "CUA_SWE_CODEX_API_KEY_ENV": "GATEWAY_KEY",
            },
        )
        assert 'model_provider="cua_swe"' in routed_argv
        assert 'model_providers.cua_swe.base_url="https://gateway.example.test/v1"' in routed_argv
        assert 'model_providers.cua_swe.env_key="GATEWAY_KEY"' in routed_argv
        assert 'model_providers.cua_swe.wire_api="responses"' in routed_argv
        assert not any("requires_openai_auth" in item for item in routed_argv)
        gateway_dir = tmp_path / "gateway"
        gateway_dir.mkdir(exist_ok=True)
        gateway_argv = _run_wrapper(
            gateway_dir,
            wrapper_name=wrapper_name,
            capture_name=capture_name,
            extra_env={
                "CUA_SWE_CODEX_BASE_URL": "http://127.0.0.1:9/prefix/responses",
                "CUA_SWE_CODEX_API_KEY_ENV": "NONE",
            },
        )
        assert 'model_providers.cua_swe.base_url="http://127.0.0.1:9/prefix/responses"' in gateway_argv
        assert "model_providers.cua_swe.requires_openai_auth=false" in gateway_argv
        assert not any("env_key" in item for item in gateway_argv)
        lease_dir = tmp_path / "lease"
        lease_dir.mkdir(exist_ok=True)
        lease_argv = _run_wrapper(
            lease_dir,
            wrapper_name=wrapper_name,
            capture_name=capture_name,
            extra_env={
                "CUA_SWE_CODEX_BASE_URL": "http://127.0.0.1:9/prefix/responses",
                "CUA_SWE_CODEX_API_KEY_ENV": "CUA_SWE_GATEWAY_TOKEN",
                "CUA_SWE_GATEWAY_TOKEN": "lease-fixture-token",
                "CUA_SWE_PROVIDER_ROUTES": "{}",
            },
        )
        assert 'model_providers.cua_swe.env_key="CUA_SWE_GATEWAY_TOKEN"' in lease_argv
        assert not any("lease-fixture-token" in item for item in lease_argv)
        seen = json.loads((lease_dir / f"{capture_name}.json.env").read_text(encoding="utf-8"))
        assert seen == {"CUA_SWE_PROVIDER_ROUTES": None, "CUA_SWE_GATEWAY_TOKEN": "lease-fixture-token"}


def _claude_environment(tmp_path: Path, extra_env: dict[str, str]) -> dict[str, str]:
    fake_claude = tmp_path / "fake_claude.py"
    fake_claude.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

names = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
         "CUA_SWE_PROVIDER_ROUTES", "CUA_SWE_GATEWAY_TOKEN")
Path(os.environ["CUA_SWE_TEST_ARGV_CAPTURE"]).write_text(
    json.dumps({name: os.environ.get(name) for name in names}), encoding="utf-8"
)
""",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)
    return _run_wrapper(
        tmp_path,
        wrapper_name="run_web_cua_agent.sh",
        capture_name="claude",
        extra_env={
            "CUA_SWE_AGENT_RUNTIME": "claude",
            "CUA_SWE_CLAUDE_BIN": str(fake_claude),
            "CUA_SWE_CLAUDE_MODEL": "claude-opus-5",
            **extra_env,
        },
    )


def test_claude_code_presents_its_gateway_lease(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    gateway = _claude_environment(
        tmp_path,
        {
            "CUA_SWE_CLAUDE_BASE_URL": "http://127.0.0.1:9/prefix/anthropic",
            "CUA_SWE_GATEWAY_TOKEN": "lease-fixture-token",
            "CUA_SWE_PROVIDER_ROUTES": "{}",
        },
    )
    assert gateway == {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9/prefix/anthropic",
        "ANTHROPIC_API_KEY": "lease-fixture-token",
        "ANTHROPIC_MODEL": "claude-opus-5",
        "CUA_SWE_PROVIDER_ROUTES": None,
        "CUA_SWE_GATEWAY_TOKEN": None,
    }
    standalone = _claude_environment(tmp_path, {"ANTHROPIC_API_KEY": "standalone-key"})
    assert standalone["ANTHROPIC_BASE_URL"] is None
    assert standalone["ANTHROPIC_API_KEY"] == "standalone-key"


def test_claude_code_gateway_requires_a_lease_token(tmp_path: Path):
    with pytest.raises(AssertionError, match="CUA_SWE_GATEWAY_TOKEN"):
        _claude_environment(tmp_path, {"CUA_SWE_CLAUDE_BASE_URL": "http://127.0.0.1:9/prefix/anthropic"})


def test_visual_prompt_is_screenshot_only_and_starts_visual_adapter():
    helper = _load_prompt_helper()
    prompt = helper.render_prompt(
        condition="browser",
        task_id="web.visual-contract.001",
        task_instruction="Repair the retained interactive workspace.",
        build_command="npm run build",
        launcher="/tools/web_cua_launcher",
        session_file="/rollout/session.json",
        artifacts_dir="/rollout/cua-adapter",
        url="http://127.0.0.1:47000",
        viewport="1280x720",
        observation_mode="visual",
    )
    policy = helper.parse_prompt(prompt).capability_policy

    assert "visual_cua.start" in policy
    assert "attaches screenshot pixels" in policy
    assert "do not provide" in policy
    assert "body text" in policy
    assert "interactive-element centers" not in policy


def test_visual_wrapper_registers_the_screenshot_mcp_server(tmp_path: Path):
    argv = _run_wrapper(
        tmp_path,
        wrapper_name="run_web_cua_agent.sh",
        capture_name="visual",
        observation_mode="visual",
    )

    combined = "\n".join(argv)
    assert "mcp_servers.visual_cua.command" in combined
    assert "web_cua_mcp.py" in combined
    assert "mcp_servers.visual_cua.tool_timeout_sec=90" in combined
    assert "mcp_servers.visual_cua.env.CUA_SWE_WEB_CUA_LAUNCHER" in combined
    assert "mcp_servers.visual_cua.env.CUA_SWE_AGENT_ROLLOUT_DIR" in combined


def test_both_wrappers_delegate_prompt_rendering_to_the_shared_helper():
    for wrapper_name in ("run_web_cua_agent.sh", "run_code_only_agent.sh"):
        wrapper = (SCRIPTS_ROOT / wrapper_name).read_text(encoding="utf-8")
        assert wrapper.count("render_web_agent_prompt.py") == 1
        assert "cat <<PROMPT_EOF" not in wrapper
        assert "CUA_SWE_TASK_VALIDATION_FLOW" not in wrapper
        assert "CUA_SWE_TASK_CONTEXT" not in wrapper
