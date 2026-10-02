"""Deadline-bounded streaming transport and response validation for real CLIs.

The CLI never imports this host-only module. Network forwarding and MCP wiring
are separate; all provider processes have exact local ownership and are reaped.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import threading
import time

from .settings import provider_config

# Endpoints and keys are routed per route from the private runtime configuration.
ROUTES = {
    "codex-sol": {
        "request_model": "gpt-5.6-sol", "returned_model": "gpt-5.6-sol",
        "path": "/v1/responses", "kind": "responses", "provider": "responses",
    },
    "claude-opus5": {
        "request_model": "claude-opus-5", "returned_model": "claude-opus-5",
        "path": "/v1/messages", "kind": "messages", "provider": "anthropic",
    },
}


def worker_environment(route_id, environ=None):
    """Clean worker environment plus only this route's host-side key, if any."""
    environ = os.environ if environ is None else environ
    route = ROUTES[route_id]
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if "CUA_MOBILE_CONFIG" in environ:
        env["CUA_MOBILE_CONFIG"] = environ["CUA_MOBILE_CONFIG"]
    key = provider_config(route_id, route["provider"], route["request_model"]).api_key_env
    if key != "NONE" and key in environ:
        env[key] = environ[key]
    return env


class TransportStop(Exception):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def pinned_request(route_id, path, body):
    """Preserve the actual CLI envelope; only impose its missing output cap."""
    route = ROUTES[route_id]
    paths = {route["path"]}
    if route["kind"] == "messages":
        paths.add(route["path"] + "?beta=true")
    if path not in paths:
        raise TransportStop("configuration", "unsupported CLI provider endpoint")
    if not isinstance(body, dict) or body.get("model") != route["request_model"]:
        raise TransportStop("wrong_model", "CLI requested an unselected model")
    if body.get("stream") is not True:
        raise TransportStop("configuration", "expected actual CLI streaming request")
    result = copy.deepcopy(body)
    if route["kind"] == "responses":
        if result.get("reasoning", {}).get("effort") != "high":
            raise TransportStop("configuration", "CLI reasoning is not high")
        key = "max_output_tokens"
    else:
        if result.get("thinking") != {"type": "adaptive"} or result.get("output_config", {}).get("effort") != "high":
            raise TransportStop("configuration", "CLI reasoning is not adaptive/high")
        key = "max_tokens"
    original = result.get(key)
    if original is not None and (type(original) is not int or original <= 0):
        raise TransportStop("configuration", "invalid CLI output-token limit")
    result[key] = min(original, 16384) if original is not None else 16384
    overrides = {} if original == result[key] else {key: {"original": original, "sent": result[key]}}
    return result, overrides


def sse_events(raw):
    """Decode events for audit; raw stream bytes are preserved separately."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TransportStop("provider", "provider SSE is not UTF8") from error
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n\n"):
        raise TransportStop("provider", "truncated SSE event boundary")
    result = []
    for block in text.split("\n\n"):
        data = "\n".join(line[5:].lstrip(" ") for line in block.split("\n") if line.startswith("data:"))
        if not data or data == "[DONE]":
            continue
        try:
            value = json.loads(data)
        except ValueError as error:
            raise TransportStop("provider", "malformed SSE JSON") from error
        if not isinstance(value, dict):
            raise TransportStop("provider", "SSE data is not an object")
        result.append(value)
    return result


def response_receipt(route_id, envelope, raw):
    route = ROUTES[route_id]
    if envelope.get("status_code") != 200:
        raise TransportStop("provider", f"provider HTTP{envelope.get('status_code')}")
    content_type = next((v for k, v in envelope.get("headers", {}).items() if k.lower() == "content-type"), "")
    if "text/event-stream" not in content_type.lower():
        raise TransportStop("provider", "streaming provider returned non-SSE content")
    events = sse_events(raw)
    if any(e.get("type") in {"error", "response.failed"} for e in events):
        raise TransportStop("provider", "provider emitted a stream error")
    if route["kind"] == "responses":
        terminal = [e for e in events if e.get("type") in {"response.completed", "response.incomplete"}]
        if len(terminal) != 1:
            raise TransportStop("provider", "missing or duplicated terminal Responses receipt")
        response = terminal[0].get("response", {})
        if not response.get("id") or response.get("model") != route["returned_model"]:
            raise TransportStop("wrong_model", "missing receipt or unexpected returned model")
        expected_status = "completed" if terminal[0]["type"] == "response.completed" else "incomplete"
        if response.get("status") != expected_status:
            raise TransportStop("provider", "terminal Responses status mismatch")
        if expected_status == "incomplete" and response.get("incomplete_details", {}).get("reason") != "max_output_tokens":
            raise TransportStop("provider", "unrecognized Responses truncation")
        if not isinstance(response.get("output"), list):
            raise TransportStop("provider", "terminal Responses output missing")
        for event in events:
            embedded = event.get("response")
            if isinstance(embedded, dict):
                if embedded.get("id", response["id"]) != response["id"]:
                    raise TransportStop("provider", "stream response identity changed")
                if embedded.get("model", response["model"]) != response["model"]:
                    raise TransportStop("wrong_model", "stream model identity changed")
        # Preserve policy refusal as a provider restriction, not a task failure.
        if any(c.get("type") == "refusal" for item in response["output"] for c in item.get("content", [])):
            raise TransportStop("provider_policy", "provider policy refusal")
        return {"id": response["id"], "model": response["model"], "usage": response.get("usage"),
                "status": response["status"], "events": len(events)}
    starts = [e.get("message", {}) for e in events if e.get("type") == "message_start"]
    stops = [e for e in events if e.get("type") == "message_stop"]
    deltas = [e for e in events if e.get("type") == "message_delta" and e.get("delta", {}).get("stop_reason") is not None]
    if len(starts) != 1 or len(stops) != 1 or len(deltas) != 1:
        raise TransportStop("provider", "missing or duplicated terminal Messages receipt")
    start = starts[0]
    if start.get("type") != "message" or start.get("role") != "assistant":
        raise TransportStop("provider", "invalid Messages start receipt")
    if not start.get("id") or start.get("model") != route["returned_model"]:
        raise TransportStop("wrong_model", "missing receipt or unexpected returned model")
    order = [e.get("type") for e in events]
    if not order.index("message_start") < events.index(deltas[0]) < order.index("message_stop"):
        raise TransportStop("provider", "Messages terminal events out of order")
    stop = deltas[0]["delta"]["stop_reason"]
    if stop == "refusal":
        raise TransportStop("provider_policy", "provider policy refusal")
    if stop not in {"end_turn", "tool_use", "max_tokens", "stop_sequence"}:
        raise TransportStop("provider", "unsupported Messages stop reason")
    return {"id": start["id"], "model": start["model"], "stop_reason": stop,
            "usage": {"start": start.get("usage"), "end": deltas[0].get("usage")}, "events": len(events)}


class Budget:
    """One shared budget for all CLI generation requests; faults latch closed."""
    def __init__(self, responses=60, seconds=2700, clock=time.monotonic, started=None):
        self.clock, self.started = clock, clock() if started is None else started
        self.responses, self.seconds = responses, seconds
        self.dispatched, self.completed = 0, 0
        self.stop = None
        self.lock = threading.Lock()

    def remaining(self):
        return self.seconds - (self.clock() - self.started)

    def reserve(self):
        with self.lock:
            if self.stop:
                raise TransportStop(*self.stop)
            if self.remaining() <= 0:
                self.stop = ("time_cap", "active CLI deadline reached")
                raise TransportStop(*self.stop)
            if self.dispatched >= self.responses:
                self.stop = ("response_cap", "CLI generation budget exhausted")
                raise TransportStop(*self.stop)
            self.dispatched += 1
            return self.dispatched

    def latch(self, category, message):
        with self.lock:
            if self.stop is None:
                self.stop = (category, message)


def write_json(path, value):
    with Path(path).open("x") as output:
        json.dump(value, output, indent=2)
        output.write("\n")


class OwnedStreamingTransport:
    """Stream one owned host worker, enforcing an absolute active deadline.

    `sink` receives ('headers', envelope) and ('body', exact_bytes). It may write
    directly to the isolated CLI connection; it never receives auth headers.
    The controller must close the attempt after any TransportStop.
    """
    def __init__(self, route_id, root, budget, worker_argv):
        self.route_id, self.route = route_id, ROUTES[route_id]
        self.root, self.budget, self.worker_argv = Path(root), budget, list(worker_argv)
        self.root.mkdir(parents=True, exist_ok=False)
        self.process_lock = threading.Lock()
        self.processes = {}
        self.cancelled = threading.Event()
        self.generation_lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()
        with self.process_lock:
            for process in self.processes.values():
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def forward(self, path, body, sink, anthropic_beta=None):
        # Real CLI background/auxiliary requests share this same generation
        # budget and are serialized. No unsupported route is forwarded.
        with self.generation_lock:
            try:
                pinned, overrides = pinned_request(self.route_id, path, body)
                if self.cancelled.is_set():
                    raise TransportStop("cancelled", "owned CLI session closed")
                number = self.budget.reserve()
                return self._forward(number, path, body, pinned, overrides, sink, anthropic_beta)
            except TransportStop as error:
                self.budget.latch(error.category, str(error))
                raise

    def _send(self, process, request, deadline):
        """A blocked input pipe must not disable cancellation or the deadline."""
        fd = process.stdin.fileno()
        os.set_blocking(fd, False)
        view = memoryview(request)
        while view:
            remaining = deadline - self.budget.clock()
            if remaining <= 0:
                raise TransportStop("time_cap", "absolute CLI deadline reached while sending request")
            if self.cancelled.is_set():
                raise TransportStop("cancelled", "owned CLI session closed")
            _, ready, _ = select.select([], [fd], [], min(remaining, 0.25))
            if ready:
                try:
                    count = os.write(fd, view[:65536])
                except BlockingIOError:
                    continue
                view = view[count:]
        process.stdin.close()

    def _forward(self, number, path, original, body, overrides, sink, beta):
        prefix = self.root / f"{number:03d}"
        deadline = self.budget.started + self.budget.seconds
        timeout = min(600, self.budget.remaining())
        write_json(prefix.with_suffix(".request.json"), {
            "route": self.route_id, "path": path, "original_body": original, "sent_body": body,
            "request_overrides": overrides, "timeout_seconds": timeout,
            "transport_attempts": 1, "anthropic_beta": beta,
            "started_monotonic": self.budget.clock(),
            "worker_argv": self.worker_argv,
        })
        request = json.dumps({"route": self.route_id, "body": body,
                              "timeout_seconds": timeout, "anthropic_beta": beta}).encode()
        process = None
        envelope = None
        receipt = None
        raw_path = prefix.with_suffix(".raw")
        before = time.monotonic()
        error_record = None
        try:
            with prefix.with_suffix(".stderr").open("xb") as stderr, raw_path.open("xb") as raw_output:
                process = subprocess.Popen(self.worker_argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=stderr, env=worker_environment(self.route_id),
                                           start_new_session=True)
                with self.process_lock:
                    self.processes[number] = process
                    if self.cancelled.is_set():
                        os.killpg(process.pid, signal.SIGKILL)
                self._send(process, request, deadline)
                header = b""
                total = 0
                while True:
                    remaining = deadline - self.budget.clock()
                    if remaining <= 0:
                        raise TransportStop("time_cap", "absolute CLI deadline reached during transport")
                    if self.cancelled.is_set():
                        raise TransportStop("cancelled", "owned CLI session closed")
                    ready, _, _ = select.select([process.stdout], [], [], min(remaining, 0.25))
                    if not ready:
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    if envelope is None:
                        header += chunk
                        if b"\n" not in header:
                            if len(header) > 65536:
                                raise TransportStop("provider", "oversized host transport header")
                            continue
                        line, chunk = header.split(b"\n", 1)
                        try:
                            envelope = json.loads(line)
                            if not isinstance(envelope, dict) or set(envelope) != {"status_code", "headers", "transport_attempts"}:
                                raise ValueError("invalid envelope")
                            if envelope["transport_attempts"] != 1:
                                raise ValueError("transport count mismatch")
                        except ValueError as error:
                            raise TransportStop("provider", "invalid host transport header") from error
                        write_json(prefix.with_suffix(".envelope.json"), envelope)
                        sink("headers", envelope)
                    if chunk:
                        total += len(chunk)
                        if total > 32 * 1024 * 1024:
                            raise TransportStop("provider", "oversized provider stream")
                        raw_output.write(chunk)
                        raw_output.flush()
                        sink("body", chunk)
                process.wait(timeout=5)
                if self.cancelled.is_set() and process.returncode < 0:
                    raise TransportStop("cancelled", "owned CLI transport was cancelled")
                if process.returncode != 0 or envelope is None:
                    raise TransportStop("provider", "host streaming transport failed; raw diagnostic retained")
            receipt = response_receipt(self.route_id, envelope, raw_path.read_bytes())
            usage = receipt.get("usage") or {}
            output_tokens = (usage.get("end") or {}).get("output_tokens") if self.route["kind"] == "messages" else usage.get("output_tokens")
            cap = body["max_tokens" if self.route["kind"] == "messages" else "max_output_tokens"]
            if type(output_tokens) is not int or output_tokens < 0 or output_tokens > cap:
                raise TransportStop("provider", "missing or out-of-budget provider output-token receipt")
            self.budget.completed += 1
            write_json(prefix.with_suffix(".receipt.json"), receipt)
            return receipt
        except TransportStop as error:
            error_record = {"category": error.category, "message": str(error)}
            raise
        except Exception as error:
            if self.cancelled.is_set() and isinstance(error, BrokenPipeError):
                error_record = {"category": "cancelled", "message": "owned CLI transport cancelled during delivery"}
                raise TransportStop("cancelled", error_record["message"]) from error
            error_record = {"category": "provider", "message": f"{type(error).__name__}: {error}"}
            raise TransportStop("provider", "CLI streaming delivery failed; original diagnostic retained") from error
        finally:
            if process is not None:
                # The process group belongs solely to this request. PID remains
                # owned until wait, so it cannot be reused before the kill.
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=8)
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                if process.stdout is not None:
                    process.stdout.close()
                with self.process_lock:
                    self.processes.pop(number, None)
            write_json(prefix.with_suffix(".completion.json"), {
                "seconds": time.monotonic() - before, "pid": process.pid if process else None,
                "returncode": process.returncode if process else None, "error": error_record,
                "reaped": process is not None and process.poll() is not None,
                "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.exists() else None,
                "valid_receipt": receipt,
            })
