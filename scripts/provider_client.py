"""Provider transports for the public evaluator; no benchmark-specific model registry."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, urlsplit
import uuid

import requests


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    region: str = ""
    max_output_tokens: int = 16384
    timeout: int = 600
    chat_token_limit: str = ""

    def __post_init__(self):
        if self.provider not in {"responses", "chat-completions", "anthropic", "bedrock"}:
            raise ValueError("provider must be responses, chat-completions, anthropic, or bedrock")
        if not self.model.strip() or self.max_output_tokens < 1 or self.timeout < 1:
            raise ValueError("model and positive token/timeout limits are required")
        if self.provider == "bedrock" and not re.fullmatch(r"[a-z0-9-]+", self.region):
            raise ValueError("Bedrock requires --region")
        defaults = {"responses": "https://api.openai.com/v1",
                    "anthropic": "https://api.anthropic.com/v1",
                    "bedrock": f"https://bedrock-runtime.{self.region}.amazonaws.com"}
        url = (self.base_url or defaults.get(self.provider, "")).rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("supply an http(s) API base URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base URL must not contain credentials, a query, or a fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("use HTTPS for remote endpoints; HTTP is available for local servers")
        object.__setattr__(self, "base_url", url)
        field = self.chat_token_limit or ("max_completion_tokens" if parsed.hostname == "api.openai.com" else "max_tokens")
        if field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("invalid Chat Completions token-limit field")
        object.__setattr__(self, "chat_token_limit", field)
        if not self.api_key_env:
            object.__setattr__(self, "api_key_env", {"anthropic": "ANTHROPIC_API_KEY", "bedrock": "AWS_BEARER_TOKEN_BEDROCK"}.get(self.provider, "OPENAI_API_KEY"))
        if self.api_key_env != "NONE" and not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.api_key_env):
            raise ValueError("api-key-env must be an environment variable name or NONE")

    def public_record(self):
        return asdict(self)

    @property
    def endpoint(self):
        suffix = {"responses": "/responses", "chat-completions": "/chat/completions", "anthropic": "/messages",
                  "bedrock": f"/model/{quote(self.model, safe='')}/converse"}[self.provider]
        return self.base_url + suffix


ROUTES_ENV = "CUA_SWE_PROVIDER_ROUTES"
ROUTE_FIELDS = {"base_url", "api_key_env", "region", "chat_token_limit"}


def route_config(provider, model, *, environ=None):
    """Resolve the operator's route for one wire protocol.

    CUA_SWE_PROVIDER_ROUTES optionally maps a wire protocol to
    {"base_url", "api_key_env", "region", "chat_token_limit"}. Unlisted protocols
    use the public defaults of ProviderConfig.
    """
    env = os.environ if environ is None else environ
    try:
        routes = json.loads(env.get(ROUTES_ENV) or "{}")
    except ValueError:
        raise ValueError(f"{ROUTES_ENV} must be a JSON object") from None
    if not isinstance(routes, dict) or not isinstance(routes.get(provider, {}), dict):
        raise ValueError(f"{ROUTES_ENV} must map wire protocols to route objects")
    route = routes.get(provider, {})
    if set(route) - ROUTE_FIELDS:
        raise ValueError(f"unsupported route fields: {sorted(set(route) - ROUTE_FIELDS)}")
    return ProviderConfig(provider=provider, model=model, **route)


class ProviderTransport:
    """Endpoint and credential routing for agents that build native request bodies.

    The agent owns its payload, retries, and error handling; this layer owns where the
    request goes and how it authenticates.
    """
    def __init__(self, config, *, token=None):
        self.config = config
        self.token = token if token is not None else ("" if config.api_key_env == "NONE" else os.environ.get(config.api_key_env, ""))
        if config.api_key_env != "NONE" and not self.token:
            raise ProviderError(f"set {config.api_key_env}, or use api_key_env NONE for an unauthenticated local endpoint")

    @classmethod
    def for_agent(cls, provider, model):
        """Build a transport from the routed configuration, then remove the routing and its
        credential from the environment so tool subprocesses inherit neither."""
        config = route_config(provider, model)
        token = "" if config.api_key_env == "NONE" else os.environ.pop(config.api_key_env, "")
        os.environ.pop(ROUTES_ENV, None)
        return cls(config, token=token)

    @property
    def endpoint(self):
        return self.config.endpoint

    def headers(self):
        headers = {"Content-Type": "application/json"}
        if self.config.provider == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if self.token:
                headers["x-api-key"] = self.token
        elif self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    def post(self, body, *, timeout, http=requests, **kwargs):
        return http.post(self.endpoint, data=body, headers=self.headers(), timeout=timeout, **kwargs)


def image_parts(data_url):
    match = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=]+)", data_url)
    if not match:
        raise ProviderError("screenshot must be a base64 PNG, JPEG, GIF, or WebP")
    base64.b64decode(match[2], validate=True)
    return match[1], match[2]


def tool_calls(output):
    return [item for item in output if item.get("type") == "function_call"]


class ProviderClient:
    """Adapt Responses-style tools and image inputs to four wire protocols.

    Provider credentials are used only in request headers. Persisted receipts contain
    unsigned request bodies, raw response bodies, and non-sensitive request IDs.
    """
    def __init__(self, config, tools, *, token=None, trace_dir=None, session=None):
        self.config = config
        self.model = config.model
        self.tools = tools
        self.request_timeout_seconds = config.timeout
        self.max_output_tokens = config.max_output_tokens
        self.token = token if token is not None else ("" if config.api_key_env == "NONE" else os.environ.get(config.api_key_env, ""))
        if config.api_key_env != "NONE" and not self.token:
            raise ProviderError(f"set {config.api_key_env}, or use --api-key-env NONE for an unauthenticated local endpoint")
        self.session = session or requests.Session()
        self.trace_dir = Path(trace_dir) if trace_dir else None
        if self.trace_dir:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.history = []
        self.previous = None
        self.pending = []
        self.index = 0

    def _parts(self, content, provider):
        if isinstance(content, str):
            content = [{"type": "input_text", "text": content}]
        out = []
        for part in content:
            if part["type"] in {"input_text", "output_text", "text"}:
                out.append({"text": part["text"]} if provider == "bedrock" else {"type": "text", "text": part["text"]})
            elif part["type"] == "input_image":
                media, data = image_parts(part["image_url"])
                if provider == "chat-completions":
                    out.append({"type": "image_url", "image_url": {"url": part["image_url"]}})
                elif provider == "anthropic":
                    out.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
                else:
                    out.append({"image": {"format": media.split('/')[1], "source": {"bytes": data}}})
            else:
                raise ProviderError(f"unsupported input content: {part['type']}")
        return out

    def _append_inputs(self, items):
        provider = self.config.provider
        if provider == "responses":
            self.history.extend(items)
            return
        results = [x for x in items if x.get("type") == "function_call_output"]
        messages = [x for x in items if x.get("type") != "function_call_output"]
        if provider == "chat-completions":
            self.history.extend({"role": "tool", "tool_call_id": x["call_id"], "content": str(x["output"])} for x in results)
            for x in messages:
                self.history.append({"role": x.get("role", "user"), "content": self._parts(x["content"], provider)})
            return
        content = []
        for x in results:
            if provider == "anthropic":
                content.append({"type": "tool_result", "tool_use_id": x["call_id"], "content": str(x["output"])})
            else:
                content.append({"toolResult": {"toolUseId": x["call_id"], "content": [{"text": str(x["output"])}]}})
        for x in messages:
            if x.get("role", "user") != "user":
                raise ProviderError("new Messages/Converse input must be a user message")
            content.extend(self._parts(x["content"], provider))
        self.history.append({"role": "user", "content": content})

    def _payload(self):
        p, c = self.config.provider, self.config
        if p == "responses":
            return {"model": c.model, "input": self.history, "tools": self.tools,
                    "tool_choice": "auto", "max_output_tokens": c.max_output_tokens}
        if p == "chat-completions":
            limit = c.chat_token_limit
            return {"model": c.model, "messages": self.history,
                    "tools": [{"type": "function", "function": {k: t[k] for k in ("name", "description", "parameters")}} for t in self.tools],
                    "tool_choice": "auto", limit: c.max_output_tokens}
        if p == "anthropic":
            return {"model": c.model, "messages": self.history, "max_tokens": c.max_output_tokens,
                    "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in self.tools]}
        return {"messages": self.history, "inferenceConfig": {"maxTokens": c.max_output_tokens},
                "toolConfig": {"tools": [{"toolSpec": {"name": t["name"], "description": t["description"], "inputSchema": {"json": t["parameters"]}}} for t in self.tools]}}

    def _normalize(self, raw, request_id):
        p = self.config.provider
        output = []
        if p == "responses":
            if not isinstance(raw.get("output"), list) or not raw.get("id") or raw.get("status") not in {"completed", "incomplete"} or raw.get("error"):
                raise ProviderError("invalid or failed Responses reply")
            self.history.extend(raw["output"])
            result = dict(raw)
        else:
            if p == "chat-completions":
                choices = raw.get("choices") or []
                if len(choices) != 1 or not raw.get("id"):
                    raise ProviderError("expected one Chat Completions choice and a response ID")
                choice = choices[0]; message = choice["message"]; reason = choice.get("finish_reason")
                if reason not in {"stop", "tool_calls", "length"}:
                    raise ProviderError("Chat Completions returned an unsupported termination")
                self.history.append({k: message[k] for k in ("role", "content", "tool_calls") if k in message})
                if message.get("content"):
                    output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": message["content"]}]})
                for call in message.get("tool_calls") or []:
                    output.append({"type": "function_call", "call_id": call["id"], "name": call["function"]["name"], "arguments": call["function"]["arguments"]})
                capped = reason == "length"
                usage = raw.get("usage") or {}
                usage = {**usage, "input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)}
            else:
                if p == "anthropic":
                    content = raw.get("content"); reason = raw.get("stop_reason")
                    if not raw.get("id") or not isinstance(content, list) or reason not in {"end_turn", "tool_use", "max_tokens", "stop_sequence"}:
                        raise ProviderError("invalid or failed Messages reply")
                    self.history.append({"role": "assistant", "content": content})
                    usage = raw.get("usage") or {}; capped = reason == "max_tokens"
                else:
                    message = (raw.get("output") or {}).get("message")
                    if not isinstance(message, dict) or raw.get("stopReason") not in {"end_turn", "tool_use", "max_tokens", "stop_sequence"}:
                        raise ProviderError("invalid or failed Converse reply")
                    self.history.append(message); content = message["content"]
                    usage = raw.get("usage") or {}; usage = {**usage, "input_tokens": usage.get("inputTokens", 0), "output_tokens": usage.get("outputTokens", 0)}
                    capped = raw["stopReason"] == "max_tokens"
                for block in content:
                    if "text" in block:
                        output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": block["text"]}]})
                    elif block.get("type") == "tool_use" or "toolUse" in block:
                        call = block.get("toolUse", block)
                        output.append({"type": "function_call", "call_id": call.get("toolUseId", call.get("id")), "name": call["name"], "arguments": json.dumps(call["input"])})
            result = {"id": raw.get("id") or request_id or str(uuid.uuid4()), "output": output,
                      "status": "incomplete" if capped else "completed", "usage": usage,
                      "incomplete_details": {"reason": "max_output_tokens"} if capped else None}
        # The adapter's logical model key is stable; retain the actual provider identity and receipt separately.
        result["provider_model"] = raw.get("model", self.model)
        result["model"] = self.model
        result["provider"] = self.config.provider
        calls = tool_calls(result["output"])
        available = {tool["name"] for tool in self.tools}
        if any(call.get("name") not in available for call in calls):
            raise ProviderError("provider requested an unavailable tool")
        ids = [x.get("call_id") for x in calls]
        if any(not x for x in ids) or len(ids) != len(set(ids)):
            raise ProviderError("missing or duplicate tool-call IDs")
        self.pending = ids
        return result

    def create(self, input_items, *, previous_response_id=None):
        if previous_response_id != self.previous:
            raise ProviderError("response continuation does not match this session")
        actual = [x["call_id"] for x in input_items if x.get("type") == "function_call_output"]
        if actual != self.pending:
            raise ProviderError("missing, reordered, or extra tool results")
        self._append_inputs(input_items)
        payload = self._payload()
        headers = ProviderTransport(self.config, token=self.token).headers()
        self.index += 1
        if self.trace_dir:
            (self.trace_dir / f"{self.index:03}-request.json").write_text(json.dumps({"endpoint": self.config.endpoint, "body": payload}, indent=2))
        try:
            response = self.session.post(self.config.endpoint, json=payload, headers=headers,
                                         timeout=self.request_timeout_seconds, allow_redirects=False)
        except requests.ReadTimeout:
            raise requests.ReadTimeout("provider read timed out") from None
        except requests.RequestException:
            raise ProviderError("provider transport failed") from None
        if not 200 <= response.status_code < 300:
            # Do not reflect provider error bodies or request headers into public logs.
            raise ProviderError(f"provider returned HTTP {response.status_code}")
        try:
            raw = response.json()
            if not isinstance(raw, dict): raise ValueError()
        except (ValueError, TypeError):
            raise ProviderError("provider returned invalid JSON") from None
        request_id = response.headers.get("x-request-id") or response.headers.get("x-amzn-requestid")
        if self.trace_dir:
            (self.trace_dir / f"{self.index:03}-response.json").write_text(json.dumps({"request_id": request_id, "body": raw}, indent=2))
        result = self._normalize(raw, request_id)
        self.previous = result["id"]
        return result
