"""Bind normalized API records to the original provider requests and replies."""
import json
from pathlib import Path

from cua_swe_bench.mobile_evaluation.agent import SHELL, FINISH, BROWSER
from cua_swe_bench.mobile_evaluation.core import evidence, verify_ref
from cua_swe_bench.mobile_evaluation.final_api import (
    messages_input, messages_tools, response_facade,
)
from .cli_evidence import require
from .settings import provider_config


def read(path):
    return json.loads(Path(path).read_text())


def audit_api_agent(root, protocol, condition):
    root = Path(root)
    agent = read(root / "agent.json")
    messages_api = protocol["provider_api"] == "Anthropic Messages"
    # The routed endpoint for this route, resolved from the same private runtime configuration.
    endpoint = provider_config(protocol.get("route_id", "gpt6-astra"),
                               "anthropic" if messages_api else "responses",
                               protocol.get("request_model", protocol["model"])).endpoint
    tools = [SHELL, FINISH] + ([BROWSER] if condition == "cua" else [])
    count = agent["responses"]
    require(1 <= count <= protocol["responses"], "API response count exceeds protocol")
    require(len(agent["requests"]) == count and len(agent["usage"]) == count,
            "API receipt accounting differs")
    wire_requests = sorted(root.glob("wire-*-request.json"))
    require(len(wire_requests) in {count, count + 1}, "unexpected API transport dispatch count")
    require(len(list(root.glob("wire-*-response.json"))) == count,
            "extra or missing original provider reply")
    previous, messages, seen = None, [], set()
    for index, receipt in enumerate(agent["requests"], 1):
        require(receipt["request"] == evidence(root / f"{index:03}-request.json")
                and receipt["response"] == evidence(root / f"{index:03}-response.json"),
                "nonsequential or borrowed normalized receipt")
        request, response = read(receipt["request"]["path"]), read(receipt["response"]["path"])
        require(request["previous_response_id"] == previous and request["tools"] == tools,
                "API context or tool treatment changed")
        require(request["model"] == protocol["model"]
                and request["reasoning"] == {"effort": protocol["reasoning"]}
                and request["max_output_tokens"] == protocol["max_output_tokens"]
                and request["transport_attempts"] == 1, "API normalized settings changed")
        wire = read(root / f"wire-{index:03}-request.json")
        raw = read(root / f"wire-{index:03}-response.json")
        require(wire["url"] == endpoint and wire["transport_attempt"] == 1
                and wire["allow_redirects"] is False
                and wire["timeout"] == request["timeout_seconds"]
                and 0 < wire["timeout"] <= protocol["request_timeout_seconds"],
                "API wire endpoint/timeout/retry policy changed")
        require(raw["status_code"] == 200, "non-200 API reply")
        original = json.loads(raw["body"])
        if messages_api:
            messages.append({"role": "user", "content": messages_input(request["input"])})
            expected = {
                "model": protocol["request_model"], "messages": messages,
                "tools": messages_tools(tools), "tool_choice": {"type": "auto"},
                "max_tokens": protocol["max_output_tokens"],
                "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"},
            }
            require(wire["body"] == expected, "Messages wire payload differs")
            provider_ref = response["provider_response"]
            require(provider_ref == evidence(root / f"{index:03}-messages-response.json")
                    and verify_ref(provider_ref) and read(provider_ref["path"]) == original,
                    "Messages primary response differs from original wire")
            normalized = {**response_facade(original, protocol["model"]),
                          "provider_response": provider_ref}
            require(response == normalized, "Messages normalization changed provider output")
            messages.append({"role": "assistant", "content": original["content"]})
        else:
            expected = {k: request[k] for k in (
                "model", "input", "tools", "tool_choice", "max_output_tokens", "reasoning")}
            if previous:
                expected["previous_response_id"] = previous
            require(wire["body"] == expected and response == original,
                    "Responses wire payload or original response differs")
        require(response["id"] == receipt["response_id"] and response["id"] not in seen
                and response["model"] == protocol["model"]
                and response.get("usage") == agent["usage"][index - 1],
                "API provider identity/usage differs")
        seen.add(response["id"])
        previous = response["id"]
    if len(wire_requests) == count + 1:
        index = count + 1
        deadline = read(root / f"{index:03}-deadline.json")
        wire = read(root / f"wire-{index:03}-request.json")
        error = read(root / f"wire-{index:03}-error.json")
        require(agent["termination"] == "time_cap" and error["error_type"] == "ReadTimeout"
                and error["error_module"] == "requests.exceptions"
                and deadline["termination"] == "time_cap"
                and 0 < deadline["timeout_seconds"] < protocol["request_timeout_seconds"]
                and deadline["elapsed_seconds"] >= protocol["active_seconds"] - 1
                and deadline["active_budget_seconds"] == protocol["active_seconds"]
                and deadline["request"] == evidence(root / f"{index:03}-request.json")
                and wire["url"] == endpoint and wire["transport_attempt"] == 1
                and wire["allow_redirects"] is False
                and wire["timeout"] == deadline["timeout_seconds"],
                "uncompleted API request is not a documented deadline cap")
    else:
        require(not list(root.glob("wire-*-error.json")), "unexpected API transport error")
    return {"passed": True, "format": "normalized_api_bound_to_original_wire",
            "responses": count, "transport_dispatches": len(wire_requests),
            "provider_api": protocol["provider_api"], "original_wire_identity_verified": True}
