import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from provider_client import ProviderClient, ProviderConfig  # noqa: E402
from provider_relay import TOKEN_ENV, gateway, relay  # noqa: E402


@pytest.fixture
def upstream():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            seen.append({"method": self.command, "path": self.path,
                         "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            if self.path.endswith("/fail"):
                self.send_response(500); self.send_header("Content-Type", "application/json")
                self.end_headers(); self.wfile.write(b'{"secret": "provider detail"}'); return
            if self.path.startswith("/v1/messages"):
                self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.send_header("request-id", "req-1"); self.end_headers()
                for event in (b"event: a\ndata: 1\n\n", b"event: b\ndata: 2\n\n"):
                    self.wfile.write(event); self.wfile.flush()
                return
            reply = json.dumps({"id": "resp-1", "status": "completed", "output": [
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply))); self.end_headers(); self.wfile.write(reply)

        do_GET = do_POST = _reply

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", seen
    server.shutdown(); server.server_close()


def routed_env(base):
    return {"CUA_SWE_PROVIDER_ROUTES": json.dumps({
        "responses": {"base_url": base, "api_key_env": "HOST_OPENAI"},
        "anthropic": {"base_url": base, "api_key_env": "HOST_ANTHROPIC"}}),
        "HOST_OPENAI": "host-openai-key", "HOST_ANTHROPIC": "host-anthropic-key"}


def test_lease_swaps_its_token_for_the_host_credential(upstream):
    base, seen = upstream
    with gateway(environ=routed_env(base)) as gw:
        assert gw.serves("responses") and gw.serves("anthropic")
        with gw.lease("responses", "gpt-6-astra") as lease:
            env = lease.environment()
            routes = json.loads(env["CUA_SWE_PROVIDER_ROUTES"])
            assert routes == {"responses": {"base_url": lease.base_url, "api_key_env": TOKEN_ENV}}
            assert env[TOKEN_ENV] == lease.token and "CUA_SWE_CODEX_BASE_URL" not in env
            reply = requests.post(lease.base_url + "/responses", json={"model": "gpt-6-astra"},
                                  headers={"Authorization": "Bearer " + lease.token})
    assert reply.status_code == 200 and reply.json()["id"] == "resp-1"
    sent = seen[-1]
    assert sent["path"] == "/v1/responses"
    assert sent["headers"]["authorization"] == "Bearer host-openai-key"
    assert lease.token not in json.dumps(sent["headers"])
    assert "host-" not in json.dumps(env)


def test_lease_rejects_other_tokens_protocols_models_and_revoked_use(upstream):
    base, seen = upstream
    with gateway(environ=routed_env(base)) as gw:
        with gw.lease("responses", "gpt-6-astra") as lease:
            auth = {"Authorization": "Bearer " + lease.token}
            no_token = requests.post(lease.base_url + "/responses", json={"model": "gpt-6-astra"})
            guessed = requests.post(lease.base_url + "/responses", json={"model": "gpt-6-astra"},
                                    headers={"Authorization": "Bearer guess"})
            other_protocol = requests.post(gw.base_url("anthropic") + "/messages", json={"model": "gpt-6-astra"},
                                           headers={"x-api-key": lease.token})
            other_model = requests.post(lease.base_url + "/responses", json={"model": "claude-opus-5"}, headers=auth)
            no_model = requests.post(lease.base_url + "/responses", json={"input": "hi"}, headers=auth)
        revoked = requests.post(lease.base_url + "/responses", json={"model": "gpt-6-astra"}, headers=auth)
        wrong_prefix = requests.post(f"http://127.0.0.1:{gw.port}/guess/responses/responses", json={})
    assert [r.status_code for r in (no_token, guessed, other_protocol, other_model, no_model, revoked)] == [
        401, 401, 403, 403, 403, 401]
    assert wrong_prefix.status_code == 404
    assert seen == []


def test_cli_lease_streams_claude_code_requests(upstream):
    base, seen = upstream
    with gateway(environ=routed_env(base)) as gw:
        with gw.lease("anthropic", "claude-opus-5") as lease:
            env = lease.environment(cli=True)
            assert env["CUA_SWE_CLAUDE_BASE_URL"] == lease.base_url
            # Claude Code sends its key as x-api-key and appends /v1/messages to ANTHROPIC_BASE_URL.
            reply = requests.post(env["CUA_SWE_CLAUDE_BASE_URL"] + "/v1/messages?beta=true",
                                  json={"model": "claude-opus-5"},
                                  headers={"x-api-key": env[TOKEN_ENV], "anthropic-version": "2023-06-01",
                                           "anthropic-beta": "tools"}, stream=True)
            events = b"".join(reply.iter_content(chunk_size=None))
        with gw.lease("responses", "gpt-5.6-sol") as codex:
            codex_env = codex.environment(cli=True)
    assert reply.headers["content-type"] == "text/event-stream" and reply.headers["request-id"] == "req-1"
    assert events == b"event: a\ndata: 1\n\nevent: b\ndata: 2\n\n"
    sent = seen[-1]
    assert sent["path"] == "/v1/messages?beta=true"
    assert sent["headers"]["x-api-key"] == "host-anthropic-key"
    assert sent["headers"]["anthropic-beta"] == "tools"
    assert codex_env["CUA_SWE_CODEX_API_KEY_ENV"] == TOKEN_ENV and codex_env["CUA_SWE_CODEX_BASE_URL"] == codex.base_url


def test_unrouted_protocol_cannot_be_leased_and_error_bodies_stay_hidden(upstream):
    base, _ = upstream
    env = routed_env(base); del env["HOST_ANTHROPIC"]
    with gateway(environ=env) as gw:
        assert not gw.serves("anthropic")
        with pytest.raises(RuntimeError, match="no authenticated anthropic route"):
            with gw.lease("anthropic", "claude-opus-5"):
                pass
        with gw.lease("responses", "gpt-6-astra") as lease:
            failed = requests.post(lease.base_url + "/fail", json={"model": "gpt-6-astra"},
                                   headers={"Authorization": "Bearer " + lease.token})
    assert failed.status_code == 500 and b"provider detail" not in failed.content


def test_public_relay_serves_provider_client_with_a_scoped_lease(upstream, monkeypatch):
    base, seen = upstream
    config = ProviderConfig(provider="responses", model="m", base_url=base, api_key_env="HOST_OPENAI")
    with relay(config, "host-openai-key") as (local, lease_token):
        assert local.api_key_env == TOKEN_ENV and local.base_url.startswith("http://127.0.0.1:")
        monkeypatch.setenv(TOKEN_ENV, lease_token)
        client = ProviderClient(local, [])
        result = client.create([{"role": "user", "content": "hi"}])
    assert result["output"][0]["content"][0]["text"] == "ok"
    assert seen[-1]["headers"]["authorization"] == "Bearer host-openai-key"


def test_agent_transport_removes_routing_and_token_before_tools_start(upstream, monkeypatch):
    base, _ = upstream
    from provider_client import ProviderTransport
    with gateway(environ=routed_env(base)) as gw:
        with gw.lease("responses", "gpt-6-astra") as lease:
            for name, value in lease.environment().items():
                monkeypatch.setenv(name, value)
            transport = ProviderTransport.for_agent("responses", "gpt-6-astra")
            assert transport.endpoint == lease.base_url + "/responses"
            assert transport.headers()["Authorization"] == "Bearer " + lease.token
            import os
            assert TOKEN_ENV not in os.environ and "CUA_SWE_PROVIDER_ROUTES" not in os.environ
