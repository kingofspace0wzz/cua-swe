"""Host-only, one-shot streaming provider transport for an isolated CLI broker.

No credentials or auth headers are returned. The owning broker enforces the
whole-request deadline and tears down this process group on cancellation.
Stdout is one JSON header line followed by the exact raw response body.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROUTES = {
    "codex-sol": ("responses", "gpt-5.6-sol"),
    "claude-opus5": ("anthropic", "claude-opus-5"),
}
BASE_ENV = {"PATH", "LANG", "PYTHONDONTWRITEBYTECODE", "CUA_MOBILE_CONFIG"}
# Locale variables the interpreter or OS may inject (PEP 538 coercion).
LOCALE_ENV = {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}


def routed_transport(route):
    """Endpoint and key for this route from the private runtime config and host environment."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from cua_swe_bench.mobile_evaluation.settings import provider_transport
    protocol, model = ROUTES[route]
    return provider_transport(route, protocol, model)


def run(request, transport=None):
    import requests

    if set(request) != {"route", "body", "timeout_seconds", "anthropic_beta"}:
        raise ValueError("invalid host transport request")
    _, model = ROUTES[request["route"]]
    body = request["body"]
    if body.get("model") != model or body.get("stream") is not True:
        raise ValueError("wrong model or non-streaming CLI request")
    timeout = request["timeout_seconds"]
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ValueError("invalid transport deadline")
    beta = request["anthropic_beta"]
    if beta is not None and (not isinstance(beta, str) or len(beta) > 8192 or "\n" in beta or "\r" in beta):
        raise ValueError("invalid beta header")
    transport = transport or routed_transport(request["route"])
    endpoint = transport.endpoint
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {**transport.headers(), "Accept": "text/event-stream"}
    if request["route"] == "claude-opus5":
        if beta:
            headers["anthropic-beta"] = beta
    elif beta:
        raise ValueError("Anthropic header on Responses route")
    # Requests does not retry by default; make the policy explicit and exclude
    # host proxy/netrc configuration as another credential/network input.
    with requests.Session() as session:
        session.trust_env = False
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
        with session.post(endpoint, data=data, headers=headers,
                          timeout=(min(30, timeout), timeout), stream=True,
                          allow_redirects=False) as response:
            safe_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() in {"content-type", "x-request-id", "request-id"}
            }
            envelope = {"status_code": response.status_code, "headers": safe_headers,
                        "transport_attempts": 1}
            sys.stdout.buffer.write(json.dumps(envelope).encode() + b"\n")
            sys.stdout.buffer.flush()
            total = 0
            for block in response.iter_content(chunk_size=1024):
                total += len(block)
                if total > 32 * 1024 * 1024:
                    raise RuntimeError("oversized provider response")
                if block:
                    sys.stdout.buffer.write(block)
                    sys.stdout.buffer.flush()


def main():
    # The broker launches with a clean environment plus only the routed key.
    # Refuse any other inherited variable as an unreviewed credential/network input.
    request = json.load(sys.stdin)
    transport = routed_transport(request.get("route"))
    allowed = BASE_ENV | LOCALE_ENV | ({transport.config.api_key_env} - {"NONE"})
    if set(os.environ) - allowed:
        raise RuntimeError("host transport inherited unexpected environment")
    run(request, transport)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not serialize request objects, sessions, or auth headers.
        print(json.dumps({"error_type": type(error).__name__, "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
