"""Offline tests for the package-level model provider (no network: the HTTP session is faked)."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from cua_swe_bench.cli import app
from cua_swe_bench.llm import ModelProvider, ModelProviderConfig
from cua_swe_bench.workflow import PreflightChecker


ENV_NAMES = [
    "CUA_SWE_LLM_MODEL",
    "CUA_SWE_LLM_CONSTRUCTION_MODEL",
    "CUA_SWE_LLM_EVALUATOR_MODEL",
    "CUA_SWE_LLM_FAST_MODEL",
    "CUA_SWE_LLM_PROVIDER",
    "CUA_SWE_LLM_BASE_URL",
    "CUA_SWE_LLM_API_KEY_ENV",
    "CUA_SWE_PROVIDER_ROUTES",
    "FABLE_5_ID",
    "OPUS_48_ID",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "TEST_LLM_KEY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # isolate from any developer .env file


class FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


REPLIES = {
    "responses": {
        "id": "resp_1",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}],
        "usage": {"input_tokens": 5, "output_tokens": 1},
    },
    "chat-completions": {
        "id": "chat_1",
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    },
    "anthropic": {
        "id": "msg_1",
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 1},
    },
    "bedrock": {
        "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 5, "outputTokens": 1},
    },
}


def test_missing_model_is_configuration_error():
    result = ModelProvider(ModelProviderConfig()).smoke_check(invoke=False)
    assert not result.ok and not result.invoked
    assert result.error_type == "ConfigurationError"
    assert "CUA_SWE_LLM_MODEL" in result.message


def test_config_from_env_and_default_protocol(monkeypatch):
    monkeypatch.setenv("CUA_SWE_LLM_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("CUA_SWE_LLM_EVALUATOR_MODEL", "gpt-5.6-luna")
    assert ModelProviderConfig.from_env().protocol == "anthropic"
    evaluator = ModelProviderConfig.from_env(model_role="evaluator")
    assert evaluator.model_id == "gpt-5.6-luna" and evaluator.protocol == "responses"
    monkeypatch.setenv("CUA_SWE_LLM_PROVIDER", "chat-completions")
    assert ModelProviderConfig.from_env().protocol == "chat-completions"


def test_config_reads_dotenv(tmp_path):
    (tmp_path / ".env").write_text("CUA_SWE_LLM_MODEL=claude-sonnet-5\nANTHROPIC_API_KEY=dotenv-key\n")
    result = ModelProvider.from_env().smoke_check(invoke=False)
    assert result.ok, result.message
    assert result.provider == "anthropic"
    assert result.base_url == "https://api.anthropic.com/v1"
    assert result.api_key_env == "ANTHROPIC_API_KEY"


def test_smoke_check_without_invoke_requires_key_but_no_network():
    config = ModelProviderConfig(model_id="gpt-5.6-luna")
    session = FakeSession(FakeResponse(200, {}))
    missing = ModelProvider(config, session=session).smoke_check(invoke=False)
    assert not missing.ok and missing.error_type == "ConfigurationError"
    assert "OPENAI_API_KEY" in missing.message
    assert session.calls == []


def test_smoke_check_without_invoke_reports_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    session = FakeSession(FakeResponse(200, {}))
    result = ModelProvider(ModelProviderConfig(model_id="gpt-5.6-luna"), session=session).smoke_check(invoke=False)
    assert result.ok and not result.invoked
    assert result.provider == "responses"
    assert result.base_url == "https://api.openai.com/v1"
    assert "pass --invoke" in result.message
    assert session.calls == []
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "protocol, endpoint",
    [
        ("responses", "https://llm.example.test/v1/responses"),
        ("chat-completions", "https://llm.example.test/v1/chat/completions"),
        ("anthropic", "https://llm.example.test/v1/messages"),
        ("bedrock", "https://llm.example.test/v1/model/test-model/converse"),
    ],
)
def test_invoke_each_wire_protocol_through_routes(monkeypatch, protocol, endpoint):
    route = {"base_url": "https://llm.example.test/v1", "api_key_env": "TEST_LLM_KEY"}
    if protocol == "bedrock":
        route["region"] = "test-region"
    monkeypatch.setenv("CUA_SWE_PROVIDER_ROUTES", json.dumps({protocol: route}))
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    session = FakeSession(FakeResponse(200, REPLIES[protocol], {"x-request-id": "req-1"}))
    config = ModelProviderConfig(model_id="test-model", provider=protocol, max_tokens=16, temperature=0.0)
    result = ModelProvider(config, session=session).smoke_check(invoke=True)

    assert result.ok and result.invoked, result.message
    assert result.output_preview == "ok"
    assert result.request_id == "req-1"
    assert result.provider == protocol and result.api_key_env == "TEST_LLM_KEY"
    (call,) = session.calls
    assert call["url"] == endpoint
    assert call["allow_redirects"] is False
    headers = call["headers"]
    if protocol == "anthropic":
        assert headers["x-api-key"] == "secret-key" and "anthropic-version" in headers
    else:
        assert headers["Authorization"] == "Bearer secret-key"
    body = json.loads(call["data"])
    text = json.dumps(body)
    assert "Reply with exactly: ok" in text
    if protocol == "bedrock":
        assert body["inferenceConfig"] == {"maxTokens": 16, "temperature": 0.0}
    else:
        assert body["model"] == "test-model" and body["temperature"] == 0.0
    assert "secret-key" not in result.model_dump_json()


def test_explicit_overrides_win_over_routes(monkeypatch):
    monkeypatch.setenv(
        "CUA_SWE_PROVIDER_ROUTES",
        json.dumps({"chat-completions": {"base_url": "https://routed.example.test/v1", "api_key_env": "OPENAI_API_KEY"}}),
    )
    session = FakeSession(FakeResponse(200, REPLIES["chat-completions"]))
    config = ModelProviderConfig(model_id="local-model").with_overrides(
        provider="chat-completions", base_url="http://127.0.0.1:8000/v1", api_key_env="NONE"
    )
    result = ModelProvider(config, session=session).converse_text("hello")
    assert result.ok and result.output_text == "ok"
    (call,) = session.calls
    assert call["url"] == "http://127.0.0.1:8000/v1/chat/completions"
    assert "Authorization" not in call["headers"]
    assert json.loads(call["data"])["max_tokens"] == 16


def test_http_error_does_not_reflect_body(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    session = FakeSession(FakeResponse(500, {"error": "echoed prompt text"}))
    result = ModelProvider(ModelProviderConfig(model_id="claude-opus-4-8"), session=session).converse_text("hi")
    assert not result.ok
    assert result.error_type == "HTTPError"
    assert result.message == "provider returned HTTP 500"
    assert "echoed" not in result.model_dump_json()


def test_remote_http_endpoint_is_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    config = ModelProviderConfig(model_id="gpt-5.4", base_url="http://llm.example.test/v1")
    result = ModelProvider(config).smoke_check(invoke=False)
    assert not result.ok and result.error_type == "ConfigurationError"


def test_unknown_protocol_is_rejected():
    result = ModelProvider(ModelProviderConfig(model_id="m", provider="carrier-pigeon")).smoke_check()
    assert not result.ok and "unsupported provider" in result.message


def test_provider_check_cli(monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("TEST_LLM_KEY", "secret")
    ok = runner.invoke(
        app,
        ["provider-check", "--model-id", "claude-opus-5", "--provider", "anthropic",
         "--base-url", "https://llm.example.test/v1", "--api-key-env", "TEST_LLM_KEY"],
    )
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.output.replace("\n", ""))  # rich may soft-wrap long lines
    assert payload["ok"] is True and payload["invoked"] is False
    assert payload["base_url"] == "https://llm.example.test/v1"
    missing = runner.invoke(app, ["provider-check"])
    assert missing.exit_code == 1
    assert "bedrock-check" not in runner.invoke(app, ["--help"]).output


def test_preflight_provider_gate(monkeypatch, tmp_path):
    skipped = PreflightChecker(project_root=tmp_path, tasks_root=tmp_path)._provider_gate()
    assert skipped.name == "provider_config_present" and skipped.status == "skip"
    monkeypatch.setenv("CUA_SWE_LLM_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    passed = PreflightChecker(project_root=tmp_path, tasks_root=tmp_path, require_provider=True)._provider_gate()
    assert passed.name == "provider_config_present" and passed.status == "pass"
