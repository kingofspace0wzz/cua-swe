"""Pinned real CLI invocation inside the externally isolated source sandbox."""
import json
import os


def command(route, base_url, prompt, socket_path="/cap.sock"):
    mcp_args = ["-I", "/bridge/client.py", "--mode", "mcp", "--socket", socket_path]
    env = os.environ.copy()
    env.update(HOME="/cli-home", CODEX_HOME="/cli-home/.codex",
               MOBILE_BRIDGE_TOKEN="isolated-placeholder",
               ANTHROPIC_BASE_URL=base_url, ANTHROPIC_API_KEY="isolated-placeholder",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_AUTOUPDATER="1",
               CLAUDE_CODE_MAX_OUTPUT_TOKENS="16384")
    if route == "codex-sol":
        binary = "/cli/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
        config = {
            "model_catalog_json": "/bridge/model-catalog.json",
            "model_provider": "mobile_provider",
            "model_providers.mobile_provider.name": "Mobile provider broker",
            "model_providers.mobile_provider.base_url": base_url + "/v1",
            "model_providers.mobile_provider.env_key": "MOBILE_BRIDGE_TOKEN",
            "model_providers.mobile_provider.request_max_retries": 0,
            "model_providers.mobile_provider.stream_max_retries": 0,
            "model_providers.mobile_provider.requires_openai_auth": False,
            "model_providers.mobile_provider.supports_websockets": False,
            "model_reasoning_effort": "high",
            "agents.enabled": False,
            "features.multi_agent": False,
            "features.multi_agent_v2": False,
            "features.unbounded_connection_retries": False,
            "features.memories": False,
            "web_search": "disabled",
            "mcp_servers.mobile.command": "/usr/bin/python3",
            "mcp_servers.mobile.args": mcp_args,
            "mcp_servers.mobile.required": True,
            "mcp_servers.mobile.startup_timeout_sec": 20,
            "mcp_servers.mobile.tool_timeout_sec": 175,
            "mcp_servers.mobile.default_tools_approval_mode": "auto",
        }
        argv = [binary, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                "--strict-config", "--disable", "plugins", "--model", "gpt-5.6-sol",
                "--dangerously-bypass-approvals-and-sandbox", "--cd", "/workspace", "--skip-git-repo-check"]
        for key, value in config.items():
            argv += ["-c", key + "=" + json.dumps(value)]
        return argv + [prompt], env
    if route == "claude-opus5":
        binary = "/cli/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
        mcp = {"mcpServers": {"mobile": {"command": "/usr/bin/python3", "args": mcp_args}}}
        argv = [binary, "--bare", "-p", prompt, "--model", "claude-opus-5",
                "--effort", "high", "--dangerously-skip-permissions", "--no-chrome",
                "--no-session-persistence", "--output-format", "stream-json", "--verbose",
                "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
                "--mcp-config", json.dumps(mcp)]
        return argv, env
    raise ValueError("unselected CLI route")
