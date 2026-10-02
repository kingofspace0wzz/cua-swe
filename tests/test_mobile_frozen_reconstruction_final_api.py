"""Provider-envelope and route isolation regressions; no network/model/browser."""
from pathlib import Path
import base64
import importlib.util
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
from cua_swe_bench.mobile_evaluation import final_api as api
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nisolated-envelope-test").decode()


def message(model, content, stop="tool_use", identity="msg1"):
    return {"type": "message", "role": "assistant", "id": identity, "model": model,
            "content": content, "stop_reason": stop, "usage": {"input_tokens": 1, "output_tokens": 2}}


class AdapterTests(unittest.TestCase):
    def test_declared_routes_keep_budgets_and_reject_deprecated_or_unknown_routes(self):
        self.assertEqual(len(api.ROUTES), 9)
        for key, route in api.ROUTES.items():
            with self.subTest(key=key):
                p = api.protocol_class(key)()
                record = p.record()
                self.assertEqual(record["request_model"], route["request_model"])
                self.assertEqual(p.model, route["returned_model"])
                self.assertEqual((p.responses, p.active_seconds, p.max_output_tokens, p.transport_attempts),
                                 (60, 2700, 16384, 1))
                self.assertEqual(p.provider, "anthropic" if route["api"] == "messages" else "responses")
                self.assertNotIn("region", record)
                self.assertEqual(record["route_id"], key)
        for key in ("unlisted-gpt6", "arbitrary-model"):
            with self.assertRaises(api.Fault):
                api.protocol_class(key)

    def test_tools_and_images_preserve_exact_payload_and_results_precede_observations(self):
        tools = [{"name": "shell", "description": "source shell", "parameters": {"type": "object"}}]
        self.assertEqual(api.messages_tools(tools),
                         [{"name": "shell", "description": "source shell", "input_schema": {"type": "object"}}])
        items = [{"role": "user", "content": [{"type": "input_text", "text": "real pixels"},
                                             {"type": "input_image", "image_url": "data:image/png;base64," + PNG}]},
                 {"type": "function_call_output", "call_id": "call1", "output": "literal tool result"}]
        content = api.messages_input(items)
        self.assertEqual([b["type"] for b in content], ["tool_result", "text", "image"])
        self.assertEqual(content[0]["content"], "literal tool result")
        self.assertEqual(content[2]["source"], {"type": "base64", "media_type": "image/png", "data": PNG})

    def test_text_only_input_stays_image_free_and_remote_image_urls_are_rejected(self):
        content = api.messages_input([{"role": "user", "content": [{"type": "input_text", "text": "task"}]}])
        self.assertEqual(content, [{"type": "text", "text": "task"}])
        for image in ("https://example.invalid/image.png", "data:image/png;base64,not base64!"):
            with self.assertRaises(Exception):
                api.messages_input([{"role": "user", "content": [{"type": "input_image", "image_url": image}]}])

    def test_wrong_returned_model_and_duplicate_calls_are_invalid(self):
        with self.assertRaises(api.Fault):
            api.response_facade(message("claude-opus-5", [], "end_turn"), "claude-fable-5")
        call = {"type": "tool_use", "id": "same", "name": "shell", "input": {"command": "pwd"}}
        with self.assertRaises(api.Fault):
            api.response_facade(message("claude-fable-5", [call, call]), "claude-fable-5")

    def test_token_cap_and_tool_identity_survive_envelope_conversion(self):
        raw = message("claude-fable-5", [
            {"type": "thinking", "thinking": "private thinking", "signature": "opaque-signature"},
            {"type": "tool_use", "id": "exact-call", "name": "shell", "input": {"command": "echo '\u03b1'"}},
        ], "max_tokens")
        facade = api.response_facade(raw, "claude-fable-5")
        self.assertEqual(facade["status"], "incomplete")
        self.assertEqual(facade["incomplete_details"]["reason"], "max_output_tokens")
        self.assertEqual(facade["output"][0]["call_id"], "exact-call")
        self.assertEqual(json.loads(facade["output"][0]["arguments"]), {"command": "echo '\u03b1'"})
        self.assertEqual(facade["usage"], raw["usage"])

    def test_messages_continuation_keeps_signed_content_images_and_exact_tool_results(self):
        with tempfile.TemporaryDirectory(prefix="mobile-reconstruction-api-envelope-") as directory:
            protocol = api.protocol_class("claude-opus48")()
            adapter = api.MessagesAdapter.__new__(api.MessagesAdapter)
            adapter.protocol, adapter.root = protocol, Path(directory).resolve()
            adapter.route = api.ROUTES[protocol.route_id]
            from cua_swe_bench.provider_layer import load
            layer = load()
            adapter.transport = layer.ProviderTransport(
                layer.ProviderConfig("anthropic", "claude-opus-4-8", base_url="https://provider.invalid/v1"),
                token="TEST_KEY_ONLY")
            adapter.endpoint = adapter.transport.endpoint
            adapter.tools, adapter.messages, adapter.previous, adapter.pending_call_ids = [], [], None, []
            adapter.request_timeout_seconds, adapter.index = 600, 0
            signed = {"type": "thinking", "thinking": "retained", "signature": "unchanged-signature"}
            replies = [
                message(protocol.model, [signed, {"type": "tool_use", "id": "call1", "name": "browser",
                                                  "input": {"action": {"type": "screenshot"}}}]),
                message(protocol.model, [{"type": "text", "text": "done"}], "end_turn", "msg2"),
            ]
            requests = []

            def post(url, **kwargs):
                requests.append({"url": url, "payload": json.loads(kwargs["data"]), "timeout": kwargs["timeout"],
                                 "headers": kwargs["headers"]})
                raw = replies.pop(0)
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: raw)

            adapter.http = SimpleNamespace(post=post)
            adapter.create([{"role": "user", "content": [{"type": "input_text", "text": "task"}]}])
            with self.assertRaises(api.Fault):
                adapter.create([{"role": "user", "content": [{"type": "input_text", "text": "missing result"}]}],
                               previous_response_id="msg1")
            self.assertEqual(len(requests), 1)
            adapter.create([
                {"type": "function_call_output", "call_id": "call1", "output": "pixels delivered"},
                {"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64," + PNG}]},
            ], previous_response_id="msg1")
            payload = requests[1]["payload"]
            self.assertEqual(payload["model"], "claude-opus-4-8")
            self.assertEqual(requests[1]["url"], "https://provider.invalid/v1/messages")
            self.assertEqual(requests[1]["headers"]["x-api-key"], "TEST_KEY_ONLY")
            self.assertEqual(requests[1]["headers"]["anthropic-version"], "2023-06-01")
            self.assertEqual(payload["messages"][1]["content"][0], signed)
            self.assertEqual(payload["messages"][2]["content"][0]["tool_use_id"], "call1")
            self.assertEqual(payload["messages"][2]["content"][1]["source"]["data"], PNG)
            self.assertEqual(payload["thinking"], {"type": "adaptive"})
            self.assertEqual(payload["output_config"], {"effort": "high"})
            self.assertEqual(payload["max_tokens"], 16384)
            self.assertNotIn("temperature", payload)
            self.assertNotIn("top_p", payload)
            self.assertEqual(len(list(Path(directory).glob("*-messages-response.json"))), 2)

    def test_route_context_restores_globals_after_exception(self):
        before = api.runner.Protocol, api.runner.Agent, api.admission.Protocol
        with self.assertRaisesRegex(RuntimeError, "intentional"):
            with api.selected_runner_context("gpt56-terra"):
                self.assertEqual(api.runner.Protocol().model, "gpt-5.6-terra")
                self.assertEqual(api.admission.Protocol().route_id, "gpt56-terra")
                raise RuntimeError("intentional")
        self.assertEqual((api.runner.Protocol, api.runner.Agent, api.admission.Protocol), before)

    def test_dispatch_uses_selected_transport_and_cannot_override_it(self):
        for key, expected in (("gpt6-astra", api.responses_client), ("claude-fable5", api.MessagesAdapter)):
            with self.subTest(key=key), patch.object(api.runner, "run_attempt") as run:
                api.run_api_attempt(key, "placeholder-task")
                self.assertIs(run.call_args.kwargs["client_factory"], expected)
        with self.assertRaises(api.Fault):
            api.run_api_attempt("gpt6-astra", client_factory=lambda: None)


class RoutedTransportTests(unittest.TestCase):
    PROVIDERS = {"gpt6-astra": {"base_url": "https://provider.invalid/v1", "api_key_env": "TEST_MOBILE_KEY"},
                 "claude-opus5": {"base_url": "https://provider.invalid/v1", "api_key_env": "TEST_MOBILE_KEY"}}

    def test_route_configuration_fixes_wire_protocol_and_rejects_other_fields(self):
        from cua_swe_bench.mobile_evaluation import settings
        with patch.dict(settings.CONFIG, {"providers": self.PROVIDERS}):
            config = settings.provider_config("gpt6-astra", "responses", "gpt-6-astra")
            self.assertEqual(config.endpoint, "https://provider.invalid/v1/responses")
            self.assertEqual(config.api_key_env, "TEST_MOBILE_KEY")
            config = settings.provider_config("claude-opus5", "anthropic", "claude-opus-5")
            self.assertEqual(config.endpoint, "https://provider.invalid/v1/messages")
        with patch.dict(settings.CONFIG, {"providers": {"gpt6-astra": {**self.PROVIDERS["gpt6-astra"], "extra": "x"}}}):
            with self.assertRaises(ValueError):
                settings.provider_config("gpt6-astra", "responses", "gpt-6-astra")

    def test_pinned_responses_client_uses_routed_auth_and_traces_no_headers(self):
        from cua_swe_bench.mobile_evaluation import agent, settings
        seen = []

        class HTTP:
            RequestException = Exception

            def post(self, url, **kwargs):
                seen.append((url, kwargs["headers"]))
                body = {"id": "r1", "model": "gpt-6-astra", "status": "completed", "output": []}
                return SimpleNamespace(status_code=200, headers={"content-type": "application/json"},
                                       text=json.dumps(body), json=lambda: body, raise_for_status=lambda: None)

        with tempfile.TemporaryDirectory(prefix="mobile-reconstruction-routed-") as directory, \
                patch.dict(settings.CONFIG, {"providers": self.PROVIDERS}), \
                patch.dict("os.environ", {"TEST_MOBILE_KEY": "TEST_KEY_ONLY"}):
            root = Path(directory).resolve()
            client = agent.responses_client(api.protocol_class("gpt6-astra")(), [], root)
            client.trace_http.http = HTTP()
            client.create([{"role": "user", "content": [{"type": "input_text", "text": "task"}]}])
            self.assertEqual(seen, [("https://provider.invalid/v1/responses",
                                     {"Content-Type": "application/json", "Authorization": "Bearer TEST_KEY_ONLY"})])
            wire = json.loads((root / "wire-001-request.json").read_text())
            self.assertEqual(wire["url"], "https://provider.invalid/v1/responses")
            self.assertNotIn("TEST_KEY_ONLY", json.dumps(wire))

    def test_cli_worker_receives_only_the_routed_host_key(self):
        from cua_swe_bench.mobile_evaluation import cli_transport, settings
        environ = {"TEST_MOBILE_KEY": "TEST_KEY_ONLY", "OTHER_SECRET": "x", "CUA_MOBILE_CONFIG": "/private/config.json"}
        with patch.dict(settings.CONFIG, {"providers": self.PROVIDERS}):
            env = cli_transport.worker_environment("claude-opus5", environ)
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                               "CUA_MOBILE_CONFIG": "/private/config.json", "TEST_MOBILE_KEY": "TEST_KEY_ONLY"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
