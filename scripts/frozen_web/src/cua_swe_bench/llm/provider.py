"""Single-prompt text model calls for the construction, evaluator, and baseline tools.

Endpoint routing and authentication come from the repository's central provider layer
(scripts/provider_client.py): the wire protocol (responses, chat-completions, anthropic,
or bedrock) selects the request shape, and CUA_SWE_PROVIDER_ROUTES optionally routes each
protocol to an operator-chosen base URL and key variable.
"""
from __future__ import annotations

import dataclasses
import json
import os
import time
from typing import Any

from pydantic import BaseModel

from cua_swe_bench.config import config_value, dotenv_values


WIRE_PROTOCOLS = ("responses", "chat-completions", "anthropic", "bedrock")

MODEL_ROLE_ENV_VARS = {
    "construction": [
        "CUA_SWE_LLM_CONSTRUCTION_MODEL",
        "FABLE_5_ID",
        "OPUS_48_ID",
        "CUA_SWE_LLM_MODEL",
    ],
    "evaluator": ["CUA_SWE_LLM_EVALUATOR_MODEL", "OPUS_48_ID", "CUA_SWE_LLM_MODEL"],
    "fast": ["CUA_SWE_LLM_FAST_MODEL", "CUA_SWE_LLM_MODEL"],
    "default": ["CUA_SWE_LLM_MODEL", "OPUS_48_ID"],
}
PROVIDER_ENV = "CUA_SWE_LLM_PROVIDER"
BASE_URL_ENV = "CUA_SWE_LLM_BASE_URL"
API_KEY_ENV_ENV = "CUA_SWE_LLM_API_KEY_ENV"
MISSING_MODEL_MESSAGE = "missing model id; set CUA_SWE_LLM_MODEL or pass --model-id"
SMOKE_PROMPT = "Reply with exactly: ok"


def _model_id_for_role(role: str, dotenv: dict[str, str]) -> str | None:
    env_names = MODEL_ROLE_ENV_VARS.get(role, MODEL_ROLE_ENV_VARS["default"])
    for name in env_names:
        value = config_value(name, dotenv)
        if value:
            return value
    return None


def default_protocol(model_id: str | None) -> str:
    """Claude models default to the Messages protocol; everything else to Responses."""
    return "anthropic" if (model_id or "").startswith("claude") else "responses"


def _provider_layer():
    from cua_swe_bench.provider_layer import load

    return load()


class ModelProviderConfig(BaseModel):
    model_id: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    max_tokens: int = 16
    temperature: float | None = None

    @classmethod
    def from_env(cls, model_role: str = "default") -> "ModelProviderConfig":
        dotenv = dotenv_values()
        return cls(
            model_id=_model_id_for_role(model_role, dotenv),
            provider=config_value(PROVIDER_ENV, dotenv),
            base_url=config_value(BASE_URL_ENV, dotenv),
            api_key_env=config_value(API_KEY_ENV_ENV, dotenv),
        )

    def with_overrides(
        self,
        model_id: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> "ModelProviderConfig":
        return self.model_copy(
            update={
                "model_id": model_id or self.model_id,
                "provider": provider or self.provider,
                "base_url": base_url or self.base_url,
                "api_key_env": api_key_env or self.api_key_env,
            }
        )

    @property
    def protocol(self) -> str:
        return self.provider or default_protocol(self.model_id)


class ModelCheckResult(BaseModel):
    ok: bool
    model_id: str | None
    provider: str | None
    base_url: str | None
    api_key_env: str | None
    invoked: bool
    latency_ms: int | None = None
    request_id: str | None = None
    usage: dict[str, Any] | None = None
    output_preview: str | None = None
    message: str = ""
    error_type: str | None = None


class ModelTextResult(BaseModel):
    ok: bool
    model_id: str | None
    provider: str | None
    base_url: str | None
    api_key_env: str | None
    latency_ms: int | None = None
    request_id: str | None = None
    usage: dict[str, Any] | None = None
    output_text: str = ""
    message: str = ""
    error_type: str | None = None


class _CallError(Exception):
    def __init__(self, error_type: str, message: str, latency_ms: int | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.latency_ms = latency_ms


class ModelProvider:
    def __init__(self, config: ModelProviderConfig, session: Any = None) -> None:
        self.config = config
        self.session = session
        self._resolved: Any = None

    @classmethod
    def from_env(cls, model_role: str = "default") -> "ModelProvider":
        return cls(ModelProviderConfig.from_env(model_role=model_role))

    def smoke_check(self, invoke: bool = False) -> ModelCheckResult:
        try:
            transport = self._transport()
        except _CallError as exc:
            return self._error(invoked=False, error_type=exc.error_type, message=exc.message)

        if not invoke:
            return ModelCheckResult(
                **self._identity(),
                ok=True,
                invoked=False,
                message=f"{transport.config.provider} provider client initialized; pass --invoke to test a model call",
            )

        try:
            outcome = self._call(transport, SMOKE_PROMPT)
        except _CallError as exc:
            return self._error(invoked=True, error_type=exc.error_type, message=exc.message, latency_ms=exc.latency_ms)
        text = outcome["text"]
        return ModelCheckResult(
            **self._identity(),
            ok=True,
            invoked=True,
            latency_ms=outcome["latency_ms"],
            request_id=outcome["request_id"],
            usage=outcome["usage"],
            output_preview=text[:200] if text else None,
            message=f"{transport.config.provider} invocation succeeded",
        )

    def converse_text(self, prompt: str) -> ModelTextResult:
        try:
            transport = self._transport()
            outcome = self._call(transport, prompt)
        except _CallError as exc:
            return self._text_error(error_type=exc.error_type, message=exc.message, latency_ms=exc.latency_ms)
        return ModelTextResult(
            **self._identity(),
            ok=True,
            latency_ms=outcome["latency_ms"],
            request_id=outcome["request_id"],
            usage=outcome["usage"],
            output_text=outcome["text"] or "",
            message=f"{transport.config.provider} invocation succeeded",
        )

    # Routing and authentication -------------------------------------------------

    def _transport(self) -> Any:
        if not self.config.model_id:
            raise _CallError("ConfigurationError", MISSING_MODEL_MESSAGE)
        protocol = self.config.protocol
        if protocol not in WIRE_PROTOCOLS:
            raise _CallError(
                "ConfigurationError",
                f"unsupported provider {protocol!r}; use one of {', '.join(WIRE_PROTOCOLS)}",
            )
        try:
            layer = _provider_layer()
        except ModuleNotFoundError as exc:
            if (exc.name or "").startswith("cua_swe_bench"):
                raise _CallError(
                    "MissingDependency",
                    "provider layer unavailable; run from a checkout that contains scripts/provider_client.py",
                ) from None
            raise _CallError(
                "MissingDependency",
                f"{exc.name or 'a dependency'} is not installed; install with `python3 -m pip install -e \".[provider]\"`",
            ) from None
        except (ImportError, RuntimeError) as exc:
            raise _CallError("MissingDependency", f"provider layer unavailable: {exc}") from None
        try:
            provider_config = layer.route_config(protocol, self.config.model_id, environ=self._route_environ(layer, protocol))
            provider_config = dataclasses.replace(provider_config, max_output_tokens=self.config.max_tokens)
        except ValueError as exc:
            raise _CallError("ConfigurationError", str(exc)) from None
        self._resolved = provider_config
        token = None
        if provider_config.api_key_env != "NONE":
            token = config_value(provider_config.api_key_env, dotenv_values()) or ""
        try:
            return layer.ProviderTransport(provider_config, token=token)
        except layer.ProviderError as exc:
            raise _CallError("ConfigurationError", str(exc)) from None

    def _route_environ(self, layer: Any, protocol: str) -> dict[str, str]:
        """Apply explicit base URL / key-variable overrides on top of the operator's route."""
        raw = os.environ.get(layer.ROUTES_ENV) or "{}"
        overrides = {
            key: value
            for key, value in (("base_url", self.config.base_url), ("api_key_env", self.config.api_key_env))
            if value
        }
        if not overrides:
            return {layer.ROUTES_ENV: raw}
        try:
            routes = json.loads(raw)
        except ValueError:
            return {layer.ROUTES_ENV: raw}  # route_config reports the malformed value
        if not isinstance(routes, dict) or not isinstance(routes.get(protocol, {}), dict):
            return {layer.ROUTES_ENV: raw}
        route = dict(routes.get(protocol, {}))
        route.update(overrides)
        return {layer.ROUTES_ENV: json.dumps({**routes, protocol: route})}

    def _identity(self) -> dict[str, Any]:
        resolved = self._resolved
        return {
            "model_id": self.config.model_id,
            "provider": resolved.provider if resolved else self.config.protocol,
            "base_url": resolved.base_url if resolved else self.config.base_url,
            "api_key_env": resolved.api_key_env if resolved else self.config.api_key_env,
        }

    # Request/response shapes ----------------------------------------------------

    def _payload(self, protocol: str, prompt: str, chat_token_limit: str) -> dict[str, Any]:
        model = self.config.model_id
        max_tokens = self.config.max_tokens
        temperature = self.config.temperature
        if protocol == "responses":
            body: dict[str, Any] = {"model": model, "input": prompt, "max_output_tokens": max_tokens}
        elif protocol == "chat-completions":
            body = {"model": model, "messages": [{"role": "user", "content": prompt}], chat_token_limit: max_tokens}
        elif protocol == "anthropic":
            body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        else:
            inference: dict[str, Any] = {"maxTokens": max_tokens}
            if temperature is not None:
                inference["temperature"] = temperature
            return {"messages": [{"role": "user", "content": [{"text": prompt}]}], "inferenceConfig": inference}
        if temperature is not None:
            body["temperature"] = temperature
        return body

    def _call(self, transport: Any, prompt: str) -> dict[str, Any]:
        import requests

        config = transport.config
        body = json.dumps(self._payload(config.provider, prompt, config.chat_token_limit)).encode("utf-8")
        http = self.session or requests
        start = time.perf_counter()
        try:
            response = transport.post(body, timeout=config.timeout, http=http, allow_redirects=False)
        except requests.RequestException as exc:
            raise _CallError(type(exc).__name__, "provider transport failed", self._elapsed(start)) from None
        latency_ms = self._elapsed(start)
        if not 200 <= response.status_code < 300:
            # Provider error bodies are not reflected; they can echo request content.
            raise _CallError("HTTPError", f"provider returned HTTP {response.status_code}", latency_ms)
        try:
            raw = response.json()
            if not isinstance(raw, dict):
                raise ValueError
        except (ValueError, TypeError):
            raise _CallError("InvalidResponse", "provider returned invalid JSON", latency_ms) from None
        headers = getattr(response, "headers", None) or {}
        request_id = headers.get("x-request-id") or headers.get("request-id") or raw.get("id")
        usage = raw.get("usage")
        return {
            "latency_ms": latency_ms,
            "request_id": request_id if isinstance(request_id, str) else None,
            "usage": usage if isinstance(usage, dict) else None,
            "text": self._output_text(config.provider, raw),
        }

    @staticmethod
    def _elapsed(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _output_text(self, protocol: str, raw: dict[str, Any]) -> str | None:
        parts: list[str] = []
        if protocol == "responses":
            for item in raw.get("output") or []:
                if isinstance(item, dict) and item.get("type") == "message":
                    for block in item.get("content") or []:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
        elif protocol == "chat-completions":
            for choice in raw.get("choices") or []:
                message = choice.get("message") if isinstance(choice, dict) else None
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    parts.append(message["content"])
        else:
            if protocol == "anthropic":
                content = raw.get("content")
            else:
                output = raw.get("output")
                message = output.get("message") if isinstance(output, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        text = "\n".join(parts).strip()
        return text or None

    # Error results ---------------------------------------------------------------

    def _error(
        self,
        invoked: bool,
        error_type: str,
        message: str,
        latency_ms: int | None = None,
    ) -> ModelCheckResult:
        return ModelCheckResult(
            **self._identity(),
            ok=False,
            invoked=invoked,
            latency_ms=latency_ms,
            message=message,
            error_type=error_type,
        )

    def _text_error(
        self,
        error_type: str,
        message: str,
        latency_ms: int | None = None,
    ) -> ModelTextResult:
        return ModelTextResult(
            **self._identity(),
            ok=False,
            latency_ms=latency_ms,
            message=message,
            error_type=error_type,
        )
