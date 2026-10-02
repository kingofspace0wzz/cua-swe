"""Native Web agents route requests through the shared ProviderTransport; no network."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROUTE_BASE = "http://127.0.0.1:9/v1"


def _load(name: str, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"_transport_test_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


class _Reply:
    status_code = 200
    text = "{}"

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _capture(module, monkeypatch, payload):
    calls = []

    def post(url, *, data, headers, timeout):
        calls.append({"url": url, "body": json.loads(data), "headers": headers, "timeout": timeout})
        return _Reply(payload)

    monkeypatch.setattr(module.requests, "post", post)
    return calls


def _route(monkeypatch, protocol, key_env):
    monkeypatch.setenv(
        "CUA_SWE_PROVIDER_ROUTES",
        json.dumps({protocol: {"base_url": ROUTE_BASE, "api_key_env": key_env}}),
    )
    monkeypatch.setenv(key_env, "fixture-secret")


def test_responses_agent_uses_routed_endpoint_and_bearer_header(monkeypatch):
    agent = _load("run_responses_agent", monkeypatch)
    _route(monkeypatch, "responses", "FIXTURE_RESPONSES_KEY")
    client = agent.ResponsesClient("gpt-5.6-sol", request_attempts=1)
    assert client.endpoint == ROUTE_BASE + "/responses"
    assert "FIXTURE_RESPONSES_KEY" not in __import__("os").environ
    calls = _capture(agent, monkeypatch, {"id": "r1", "output": []})
    assert client.create([{"role": "user", "content": "go"}])["id"] == "r1"
    (call,) = calls
    assert call["url"] == ROUTE_BASE + "/responses"
    assert call["headers"]["Authorization"] == "Bearer fixture-secret"
    assert call["body"]["model"] == "gpt-5.6-sol"
    assert call["timeout"] == 600
    base_argv = ["run_responses_agent.py", "--model", "m", "--workspace", ".",
                 "--rollout-dir", ".", "--prompt", "p"]
    monkeypatch.setattr(sys, "argv", base_argv)
    assert agent.parse_args().model == "m"
    monkeypatch.setattr(sys, "argv", [*base_argv, "--region", "x"])
    with pytest.raises(SystemExit):
        agent.parse_args()


def test_responses_agent_uses_public_default_without_routes(monkeypatch):
    agent = _load("run_responses_agent", monkeypatch)
    monkeypatch.delenv("CUA_SWE_PROVIDER_ROUTES", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret")
    client = agent.ResponsesClient("gpt-5.6-sol")
    assert client.endpoint == "https://api.openai.com/v1/responses"
    assert client.transport.headers()["Authorization"] == "Bearer fixture-secret"


def test_anthropic_agent_uses_messages_headers(monkeypatch):
    agent = _load("run_anthropic_cua_agent", monkeypatch)
    _route(monkeypatch, "anthropic", "FIXTURE_ANTHROPIC_KEY")
    client = agent.MessagesClient("claude-opus-4-8", request_attempts=1)
    calls = _capture(agent, monkeypatch, {"id": "m1", "content": []})
    client.create([{"role": "user", "content": "go"}])
    (call,) = calls
    assert call["url"] == ROUTE_BASE + "/messages"
    assert call["headers"]["x-api-key"] == "fixture-secret"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in call["headers"]
    assert "anthropic_version" not in call["body"]


def test_anthropic_typed_missing_key_is_a_typed_transport_failure(monkeypatch):
    agent = _load("run_anthropic_cua_agent", monkeypatch)
    monkeypatch.delenv("CUA_SWE_PROVIDER_ROUTES", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    client = agent.MessagesClient("claude-opus-4-8", typed_submission_schema=schema)
    monkeypatch.setattr(agent.requests, "post", lambda *a, **k: pytest.fail("dispatched"))
    with pytest.raises(agent.TypedTerminalProvider) as caught:
        client.create([{"role": "user", "content": "go"}], request_number=1)
    assert caught.value.transport_telemetry == {
        "dispatch_attempted": False,
        "failure_kind": "no_credentials",
        "http_status": None,
        "transport_stage": "credential_resolution",
    }
    with pytest.raises(agent.ProviderError):
        agent.MessagesClient("claude-opus-4-8")


@pytest.mark.parametrize("script,factory", [
    ("run_kimi_cua_agent", lambda m: m.ChatClient("kimi-k2.5")),
    ("run_qwen_cua_agent", lambda m: m.QwenChatClient("qwen3-vl-235b-a22b-instruct")),
])
def test_chat_agents_use_chat_completions_route(script, factory, monkeypatch):
    agent = _load(script, monkeypatch)
    _route(monkeypatch, "chat-completions", "FIXTURE_CHAT_KEY")
    client = factory(agent)
    calls = _capture(agent, monkeypatch, {"id": "c1", "choices": []})
    client.create([{"role": "user", "content": "go"}])
    (call,) = calls
    assert call["url"] == ROUTE_BASE + "/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer fixture-secret"
    assert call["timeout"] == 300


def _runner(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import run_clean_ablation as runner
    import run_model_matrix as matrix

    return runner, matrix


CHAT_ROUTES = json.dumps({
    "chat-completions": {
        "base_url": "https://gateway.example.test/v1",
        "api_key_env": "GATEWAY_CHAT_KEY",
    },
})


def test_provider_secret_names_cover_every_controller_key(monkeypatch):
    runner, matrix = _runner(monkeypatch)
    env = {
        "CUA_SWE_PROVIDER_ROUTES": CHAT_ROUTES,
        "CUA_SWE_CODEX_API_KEY_ENV": "CODEX_GATEWAY_TOKEN",
        "EXAMPLE_VENDOR_API_KEY": "x",
    }
    names = set(matrix.provider_secret_env_names(env))
    assert {
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CUA_SWE_PROVIDER_TOKEN",
        "GATEWAY_CHAT_KEY", "CODEX_GATEWAY_TOKEN", "EXAMPLE_VENDOR_API_KEY",
    } <= names
    names = runner._expected_tool_names("code-only", "anthropic")
    assert "provider_client.py" in names and "run_anthropic_cua_agent.py" in names
    assert "provider_client.py" not in runner._expected_tool_names("code-only", "codex")


LOCAL_CHAT_ROUTES = json.dumps({
    "chat-completions": {"base_url": "http://127.0.0.1:9/v1", "api_key_env": "GATEWAY_CHAT_KEY"},
})


def _fake_executables(tmp_path):
    """A pass-through strace that records its argv, and a launcher that records its env."""
    strace = tmp_path / "fake_strace"
    strace.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "argv = sys.argv[1:]\n"
        "out = argv[argv.index('-o') + 1]\n"
        "open(out, 'w').write(json.dumps(argv))\n"
        "rest = argv[argv.index('-o') + 2:]\n"
        "os.execvp(rest[0], rest)\n",
        encoding="utf-8",
    )
    strace.chmod(0o755)
    (tmp_path / "run_code_only_agent.sh").write_text(
        "#!/usr/bin/env bash\n"
        "exec \"$CUA_SWE_PYTHON\" -c 'import json, os; print(json.dumps({k: os.environ.get(k) for k in "
        "(\"CUA_SWE_GATEWAY_TOKEN\", \"CUA_SWE_PROVIDER_ROUTES\", \"OPENAI_API_KEY\", "
        "\"GATEWAY_CHAT_KEY\", \"CUA_SWE_CODEX_BASE_URL\")}))'\n",
        encoding="utf-8",
    )
    return strace


def test_trial_lease_reaches_agent_only_through_environment(monkeypatch, tmp_path):
    import requests

    runner, matrix = _runner(monkeypatch)
    monkeypatch.setenv("CUA_SWE_PROVIDER_ROUTES", LOCAL_CHAT_ROUTES)
    monkeypatch.setenv("GATEWAY_CHAT_KEY", "chat-fixture-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-fixture-secret")
    monkeypatch.setenv("CUA_SWE_CODEX_BASE_URL", "https://stale.example.test/v1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    strace = _fake_executables(tmp_path)
    relay = matrix._load_provider_module("provider_relay")
    with relay.gateway() as gateway:
        monkeypatch.setattr(matrix, "_GATEWAY", gateway)
        assert gateway.serves("chat-completions") and not gateway.serves("anthropic")
        monkeypatch.setattr(
            runner.shutil, "which", lambda name: str(strace) if name == "strace" else f"/usr/bin/{name}"
        )
        monkeypatch.setattr(runner, "_sandbox_command", lambda *a, **k: ([], "test"))
        monkeypatch.setattr(runner, "_public_build_command", lambda task: "npm run build")
        task = SimpleNamespace(id="web.example", instruction="Fix it.")
        model = runner.ModelSpec("kimi25", "Kimi K2.5", "kimi", "kimi-k2.5")
        trial = runner.CleanTrial(0, tmp_path / "task.yaml", "web.example", "example",
                                  "digest", model, 1, "code-only", 43100)
        audit = tmp_path / "audit.json"
        command = runner._agent_command(trial, task, tmp_path, tmp_path, tmp_path,
                                        Path(sys.executable), "profile", audit)
        argv = shlex.split(command.removesuffix(" </dev/null"))
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GATEWAY_CHAT_KEY"):
            assert argv[argv.index(name) - 1] == "-u"
        for name in ("CUA_SWE_GATEWAY_TOKEN", "CUA_SWE_PROVIDER_ROUTES"):
            assert name not in command
        with runner._provider_lease("kimi", "kimi-k2.5") as lease_environment:
            token = lease_environment["CUA_SWE_GATEWAY_TOKEN"]
            result = runner.run_agent_command(command, cwd=tmp_path, timeout_sec=60,
                                              lease_environment=lease_environment)
            assert result.ok, result.stderr
            seen = json.loads(result.stdout)
            lease_url = json.loads(seen["CUA_SWE_PROVIDER_ROUTES"])["chat-completions"]["base_url"]
            live = requests.post(lease_url + "/chat/completions", json={"model": "kimi-k2.5"},
                                 headers={"Authorization": "Bearer " + token}, timeout=10)
        assert seen["CUA_SWE_GATEWAY_TOKEN"] == token
        assert seen["OPENAI_API_KEY"] is None and seen["GATEWAY_CHAT_KEY"] is None
        assert seen["CUA_SWE_CODEX_BASE_URL"] is None
        assert lease_url.startswith(f"http://127.0.0.1:{gateway.port}/")
        assert token not in result.command and token not in runner._command_dict(result)["command"]
        assert token not in audit.read_text() and "chat-fixture-secret" not in audit.read_text()
        assert live.status_code == 502  # authorized; the fixture upstream is unreachable
        revoked = requests.post(lease_url + "/chat/completions", json={"model": "kimi-k2.5"},
                                headers={"Authorization": "Bearer " + token}, timeout=10)
        assert revoked.status_code == 401
        lifecycle = runner._isolated_lifecycle_environment(tmp_path)
        for name in ("CUA_SWE_GATEWAY_TOKEN", "CUA_SWE_PROVIDER_ROUTES", "GATEWAY_CHAT_KEY",
                     "OPENAI_API_KEY", "CUA_SWE_PROVIDER_CONFIG"):
            assert lifecycle[lifecycle.index(name) - 1] == "-u"
        with pytest.raises(RuntimeError, match="provider configuration error"):
            runner._require_provider_route("anthropic")
