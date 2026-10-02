"""Authenticated provider gateway: credentials stay on the controller, agents get a scoped lease.

Every runtime agent (native agents, Codex, Claude Code, the public agent) calls models through
this gateway. The controller holds the provider credentials. For each trial it issues a lease: a
random token valid for one wire protocol and one model, revoked when the trial ends. The agent
presents the lease token where an API key would go; the gateway checks the protocol and the
requested model, replaces the token with the routed credential, and streams the reply back.
Lease tokens belong in the agent's environment, never on a command line or in result records.
"""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import re
import secrets
import threading
from urllib.parse import unquote, urlsplit

import requests

from provider_client import ProviderTransport, ROUTES_ENV, route_config

GATEWAY_PROTOCOLS = ("responses", "chat-completions", "anthropic")
TOKEN_ENV = "CUA_SWE_GATEWAY_TOKEN"
MAX_BODY = 64 * 1024 * 1024
# Client credentials and connection-level headers never pass through; the gateway sets auth itself.
DROPPED_REQUEST_HEADERS = {
    "host", "content-length", "connection", "keep-alive", "proxy-authorization", "proxy-connection",
    "te", "trailer", "transfer-encoding", "upgrade", "authorization", "x-api-key", "api-key",
    "cookie", "accept-encoding",
}
FORWARDED_RESPONSE_HEADERS = ("content-type", "x-request-id", "request-id", "x-amzn-requestid", "retry-after")


class Lease:
    """One trial's access: a token valid for a single protocol and model until revoked."""

    def __init__(self, gateway, protocol, model):
        self.gateway, self.protocol, self.model = gateway, protocol, model
        self.token = secrets.token_urlsafe(32)

    @property
    def base_url(self):
        return self.gateway.base_url(self.protocol)

    def provider_config(self, config):
        """Agent-side ProviderConfig for a ProviderClient that reads the lease token from TOKEN_ENV."""
        return replace(config, base_url=self.base_url, api_key_env=TOKEN_ENV)

    def environment(self, *, cli=False):
        """Agent environment for this lease. Includes the token: pass it as process
        environment, never as command-line arguments."""
        env = {TOKEN_ENV: self.token,
               ROUTES_ENV: json.dumps({self.protocol: {"base_url": self.base_url, "api_key_env": TOKEN_ENV}})}
        if cli and self.protocol == "responses":
            env.update({"CUA_SWE_CODEX_BASE_URL": self.base_url, "CUA_SWE_CODEX_API_KEY_ENV": TOKEN_ENV})
        if cli and self.protocol == "anthropic":
            env.update({"CUA_SWE_CLAUDE_BASE_URL": self.base_url})
        return env


class Gateway:
    def __init__(self, port, prefix, upstreams):
        self.port, self.prefix, self.upstreams = port, prefix, upstreams
        self._leases = {}
        self._lock = threading.Lock()

    def base_url(self, protocol):
        return f"http://127.0.0.1:{self.port}{self.prefix}/{protocol}"

    def serves(self, protocol):
        return protocol in self.upstreams

    @contextmanager
    def lease(self, protocol, model):
        if protocol not in self.upstreams:
            raise RuntimeError(f"provider configuration error: no authenticated {protocol} route on this controller")
        if not str(model).strip():
            raise ValueError("a lease requires a model")
        lease = Lease(self, protocol, str(model))
        with self._lock:
            self._leases[lease.token] = lease
        try:
            yield lease
        finally:
            with self._lock:
                self._leases.pop(lease.token, None)

    def _lease_for(self, presented):
        with self._lock:
            for token, lease in self._leases.items():
                if presented and hmac.compare_digest(token, presented):
                    return lease
        return None


def _upstream_url(base_url, rest, query):
    # SDK-style clients (e.g. Claude Code) append /v1 themselves; routed base URLs already include it.
    if base_url.endswith("/v1") and (rest == "v1" or rest.startswith("v1/")):
        rest = rest[3:]
    url = base_url + ("/" + rest if rest else "")
    return url + ("?" + query if query else "")


def _requested_model(protocol, rest, body):
    if protocol == "bedrock":
        match = re.fullmatch(r"model/([^/]+)/(?:converse|converse-stream)", rest)
        return unquote(match[1]) if match else None
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None
    return payload.get("model") if isinstance(payload, dict) else None


def _presented_token(headers):
    auth = headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-api-key", "").strip()


def _resolve_upstreams(environ):
    upstreams = {}
    for protocol in GATEWAY_PROTOCOLS:
        try:
            config = route_config(protocol, "routed", environ=environ)
        except ValueError:
            continue  # e.g. chat-completions without a configured base URL
        token = "" if config.api_key_env == "NONE" else environ.get(config.api_key_env, "")
        if config.api_key_env != "NONE" and not token:
            continue  # this controller holds no credential for the protocol
        upstreams[protocol] = (config, token)
    return upstreams


@contextmanager
def gateway(*, environ=None, upstreams=None):
    """Serve routed protocols on 127.0.0.1 for leaseholders, with the controller's credentials.

    upstreams maps protocol -> (ProviderConfig, token); by default it is resolved from
    CUA_SWE_PROVIDER_ROUTES and the routed key variables in the controller environment.
    """
    if upstreams is None:
        upstreams = _resolve_upstreams(os.environ if environ is None else environ)
    prefix = "/" + secrets.token_hex(16)
    holder = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _fail(self, status, message):
            body = json.dumps({"error": {"type": "gateway_error", "message": message}}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _forward(self, method):
            gw = holder["gateway"]
            parts = urlsplit(self.path)
            if not parts.path.startswith(prefix + "/"):
                self.send_error(404); return
            protocol, _, rest = parts.path[len(prefix) + 1:].partition("/")
            lease = gw._lease_for(_presented_token(self.headers))
            if lease is None:
                self._fail(401, "missing, unknown, or revoked gateway lease"); return
            if protocol != lease.protocol or protocol not in upstreams:
                self._fail(403, f"lease does not cover the {protocol} protocol"); return
            config, token = upstreams[protocol]
            body = None
            if method == "POST":
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= MAX_BODY:
                    self.send_error(413); return
                body = self.rfile.read(length)
                if _requested_model(protocol, rest, body) != lease.model:
                    self._fail(403, f"lease covers only model {lease.model}"); return
            headers = {k: v for k, v in self.headers.items() if k.lower() not in DROPPED_REQUEST_HEADERS}
            auth = ProviderTransport(config, token=token).headers()
            if any(k.lower() == "anthropic-version" for k in headers):
                auth.pop("anthropic-version", None)
            if any(k.lower() == "content-type" for k in headers):
                auth.pop("Content-Type", None)
            headers.update(auth)
            try:
                response = requests.request(method, _upstream_url(config.base_url, rest, parts.query),
                                            data=body, headers=headers, timeout=config.timeout,
                                            allow_redirects=False, stream=True)
            except requests.RequestException:
                self._fail(502, "provider transport failed"); return
            with response:
                if not 200 <= response.status_code < 300:
                    # Do not reflect provider error bodies into agent-visible logs.
                    self._fail(response.status_code, f"provider returned HTTP {response.status_code}"); return
                self.send_response(response.status_code)
                for name in FORWARDED_RESPONSE_HEADERS:
                    if name in response.headers:
                        self.send_header(name, response.headers[name])
                self.send_header("Connection", "close")
                self.end_headers()
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        self.wfile.write(chunk); self.wfile.flush()

        def do_POST(self):
            try:
                self._forward("POST")
            except ValueError:
                self.send_error(400)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            try:
                self._forward("GET")
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    holder["gateway"] = Gateway(server.server_port, prefix, upstreams)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield holder["gateway"]
    finally:
        server.shutdown(); server.server_close(); thread.join()


@contextmanager
def relay(config, token):
    """Single-route gateway for the public evaluator.

    Yields (agent_config, lease_token): agent_config reads the token from TOKEN_ENV and is
    valid only for config.provider and config.model while the context is open.
    """
    with gateway(upstreams={config.provider: (config, token)}) as gw:
        with gw.lease(config.provider, config.model) as lease:
            yield lease.provider_config(config), lease.token
