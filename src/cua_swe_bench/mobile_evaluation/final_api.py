"""Isolated final Mobile API routing; provider availability is verified separately.

Run one selected route per process. The runner, tools, budgets and screenshot
transport remain identical across models; only provider-specific envelopes vary.
Ported from the frozen evaluator used for the reviewed Mobile release.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import base64
import json

from cua_swe_bench.mobile_evaluation import admission, runner
from cua_swe_bench.mobile_evaluation.agent import Agent, TraceHTTP, responses_client
from cua_swe_bench.mobile_evaluation.core import Fault, Protocol, evidence, sha, write_json
from .settings import provider_transport

# Source: final-evaluation-model-mapping-20260920-002.json. These are exact
# declared routes, not evidence of present provider availability. Endpoints and
# keys are resolved per route from the private runtime configuration.
ROUTES = {
    "gpt56-sol": {"api": "responses", "request_model": "gpt-5.6-sol", "returned_model": "gpt-5.6-sol"},
    "gpt56-luna": {"api": "responses", "request_model": "gpt-5.6-luna", "returned_model": "gpt-5.6-luna"},
    "gpt56-terra": {"api": "responses", "request_model": "gpt-5.6-terra", "returned_model": "gpt-5.6-terra"},
    "claude-opus5": {"api": "messages", "request_model": "claude-opus-5", "returned_model": "claude-opus-5"},
    "claude-opus48": {"api": "messages", "request_model": "claude-opus-4-8", "returned_model": "claude-opus-4-8"},
    "claude-sonnet5": {"api": "messages", "request_model": "claude-sonnet-5", "returned_model": "claude-sonnet-5"},
    "claude-fable5": {"api": "messages", "request_model": "claude-fable-5", "returned_model": "claude-fable-5"},
    "grok46": {"api": "responses", "request_model": "grok-4.6", "returned_model": "grok-4.6"},
    "gpt6-astra": {"api": "responses", "request_model": "gpt-6-astra", "returned_model": "gpt-6-astra"},
}
WIRE = {"responses": "responses", "messages": "anthropic"}


def protocol_class(route_id):
    if route_id not in ROUTES:
        raise Fault("configuration", "undeclared final evaluation model route")
    route = dict(ROUTES[route_id])
    selected_id = route_id

    @dataclass(frozen=True)
    class SelectedProtocol(Protocol):
        name: str = "mobile-final-api-v1"
        model: str = route["returned_model"]
        provider: str = WIRE[route["api"]]
        reasoning: str = "adaptive/high" if route["api"] == "messages" else "high"
        route_id: str = selected_id

        def record(self):
            result = {**super().record(), "provider_api": "Anthropic Messages" if route["api"] == "messages" else "Responses",
                      "request_model": route["request_model"], "returned_model": route["returned_model"],
                      "adapter": evidence(__file__), "route_id": selected_id}
            if route["api"] == "messages":
                result.update(client_sha256=sha(__file__), thinking={"type": "adaptive"}, output_config={"effort": "high"})
            return result
    return SelectedProtocol


def messages_tools(tools):
    return [
        {"name": tool["name"], "description": tool["description"],
         "input_schema": tool["parameters"]}
        for tool in tools
    ]


def messages_input(items):
    """Preserve every tool result/text/image; Messages requires results first."""
    results, observations = [], []
    for item in items:
        if item.get("type") == "function_call_output":
            results.append({
                "type": "tool_result", "tool_use_id": item["call_id"],
                "content": item["output"],
            })
        elif item.get("role") == "user":
            for content in item["content"]:
                if content["type"] == "input_text":
                    observations.append({"type": "text", "text": content["text"]})
                elif content["type"] == "input_image":
                    prefix = "data:image/png;base64,"
                    url = content["image_url"]
                    if not url.startswith(prefix):
                        raise Fault("image_delivery", "Messages adapter expects unchanged PNG pixels")
                    data = url[len(prefix):]
                    base64.b64decode(data, validate=True)
                    observations.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": data},
                    })
                else:
                    raise Fault("provider", "unsupported input content")
        else:
            raise Fault("provider", "unsupported provider input item")
    if not results and not observations:
        raise Fault("provider", "empty provider input")
    return results + observations


def response_facade(raw, expected_model):
    """Retain the provider receipt/model; map only its API envelope for Agent."""
    if raw.get("type") != "message" or raw.get("role") != "assistant" or not raw.get("id"):
        raise Fault("provider", "invalid Messages receipt")
    if raw.get("model") != expected_model:
        raise Fault("wrong_model", f"returned model {raw.get('model')!r}")
    if raw.get("stop_reason") not in {"tool_use", "end_turn", "max_tokens", "stop_sequence"}:
        raise Fault("provider", f"unsupported Messages stop reason {raw.get('stop_reason')!r}")
    content = raw.get("content")
    if not isinstance(content, list):
        raise Fault("provider", "invalid Messages content")
    output, call_ids = [], set()
    for block in content:
        if block.get("type") == "tool_use":
            if not block.get("id") or block["id"] in call_ids:
                raise Fault("provider", "missing or duplicate tool call identity")
            if not isinstance(block.get("input"), dict) or not isinstance(block.get("name"), str):
                raise Fault("provider", "invalid tool call input")
            call_ids.add(block["id"])
            output.append({
                "type": "function_call", "call_id": block["id"], "name": block["name"],
                "arguments": json.dumps(block["input"], ensure_ascii=False),
            })
        elif block.get("type") == "text":
            output.append({"type": "message", "role": "assistant",
                           "content": [{"type": "output_text", "text": block["text"]}]})
        elif block.get("type") not in {"thinking", "redacted_thinking"}:
            raise Fault("provider", f"unsupported response content {block.get('type')!r}")
    incomplete = raw["stop_reason"] == "max_tokens"
    return {
        "id": raw["id"], "model": raw["model"],
        "status": "incomplete" if incomplete else "completed",
        "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
        "output": output, "usage": raw.get("usage"),
        "provider_api": "Anthropic Messages", "provider_stop_reason": raw["stop_reason"],
    }


class MessagesAdapter:
    def __init__(self, protocol, tools, root):
        route = ROUTES[protocol.route_id]
        if route["api"] != "messages" or protocol.model != route["returned_model"]:
            raise Fault("configuration", "wrong declared Messages route")
        self.route = route
        import requests
        # Host-side routing: the key stays in this process and never enters a sandbox.
        try:
            self.transport = provider_transport(protocol.route_id, WIRE["messages"], route["request_model"])
        except Exception as exc:
            raise Fault("provider", f"provider route unavailable: {exc}") from None
        self.http = TraceHTTP(requests, root)
        self.protocol, self.root = protocol, Path(root)
        self.tools = messages_tools(tools)
        self.request_timeout_seconds = protocol.request_timeout_seconds
        self.messages, self.previous, self.pending_call_ids = [], None, []
        self.index = 0
        self.endpoint = self.transport.endpoint

    def create(self, items, previous_response_id=None):
        if previous_response_id != self.previous:
            raise Fault("provider", "Messages continuation does not match prior receipt")
        content = messages_input(items)
        result_ids = [b["tool_use_id"] for b in content if b["type"] == "tool_result"]
        if result_ids != self.pending_call_ids:
            raise Fault("provider", "missing, reordered or extra tool results")
        self.messages.append({"role": "user", "content": content})
        payload = {
            "model": self.route["request_model"], "messages": self.messages, "tools": self.tools,
            "tool_choice": {"type": "auto"}, "max_tokens": self.protocol.max_output_tokens,
            "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"},
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        # TraceHTTP retains the payload + raw response (never auth headers), disables redirects.
        # requests.post has no configured transport retry; exactly one dispatch.
        response = self.http.post(
            self.endpoint, data=body, headers=self.transport.headers(),
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()
        facade = response_facade(raw, self.protocol.model)
        self.index += 1
        raw_ref = write_json(self.root / f"{self.index:03}-messages-response.json", raw)
        # Preserve complete signed thinking blocks and all assistant/tool content.
        self.messages.append({"role": "assistant", "content": raw["content"]})
        self.previous = raw["id"]
        self.pending_call_ids = [
            b["id"] for b in raw["content"] if b.get("type") == "tool_use"
        ]
        facade["provider_response"] = raw_ref
        return facade



@contextmanager
def selected_runner_context(route_id):
    """Per-process binding, restored even if a preflight/attempt raises."""
    SelectedProtocol = protocol_class(route_id)

    class SelectedAgent(Agent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.protocol = SelectedProtocol()

    old = runner.Protocol, runner.Agent, admission.Protocol
    runner.Protocol, runner.Agent, admission.Protocol = SelectedProtocol, SelectedAgent, SelectedProtocol
    try:
        yield
    finally:
        runner.Protocol, runner.Agent, admission.Protocol = old


def run_api_attempt(route_id, *args, **kwargs):
    """Final dispatcher must first verify release, route preflight and approval."""
    if "client_factory" in kwargs:
        raise Fault("configuration", "final model transport cannot be overridden")
    protocol_class(route_id)  # Reject undeclared routes before entering the context.
    factory = MessagesAdapter if ROUTES[route_id]["api"] == "messages" else responses_client
    with selected_runner_context(route_id):
        return runner.run_attempt(*args, client_factory=factory, **kwargs)
