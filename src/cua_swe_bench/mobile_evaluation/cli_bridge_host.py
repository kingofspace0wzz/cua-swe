"""Host-only Unix socket broker for selected provider and pixel capabilities."""
from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import socketserver
import threading

from .cli_transport import TransportStop, write_json

MAX_BODY = 32 * 1024 * 1024


def image_records(value):
    """Record exact actual image bytes; never infer delivery from CLI events."""
    rows = []
    if isinstance(value, list):
        for child in value:
            rows.extend(image_records(child))
    elif isinstance(value, dict):
        encoded = None
        if value.get("type") == "input_image":
            url = value.get("image_url")
            if isinstance(url, str) and url.startswith("data:image/") and ";base64," in url:
                encoded = url.split(";base64,", 1)[1]
            else:
                raise TransportStop("configuration", "only inline CLI image payloads supported")
        elif value.get("type") == "image":
            source = value.get("source")
            if isinstance(source, dict) and source.get("type") == "base64":
                encoded = source.get("data")
            elif isinstance(value.get("data"), str):
                encoded = value["data"]
            elif source is not None:
                raise TransportStop("configuration", "only inline CLI image payloads supported")
        if encoded is not None:
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as error:
                raise TransportStop("configuration", "malformed inline image") from error
            rows.append({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        for child in value.values():
            if isinstance(child, (list, dict)):
                rows.extend(image_records(child))
    return rows


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    # Closing the broker is an evidence barrier: every accepted request must
    # finish before the attempt inventories artifacts or closes its runtime.
    daemon_threads = False
    block_on_close = True


class CapabilityBroker:
    """Trusted callbacks own runtime/scope checks; no arbitrary host operations."""
    def __init__(self, socket_path, root, transport, browser_tool, browser_callback):
        if browser_tool.get("name") != "browser":
            raise ValueError("exact browser tool required")
        self.socket_path, self.root = str(socket_path), Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.transport, self.budget = transport, transport.budget
        self.browser_tool, self.browser_callback = browser_tool, browser_callback
        self.lock = threading.Lock()
        self.counter = 0
        self.images = set()
        self.actions = 0
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def json_response(self, status, value):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)
                self.close_connection = True

            def stop_response(self, status, value):
                try:
                    self.json_response(status, value)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    # The owned CLI may already have been stopped at its cap.
                    # Its terminal fault/cap is retained before this best-effort
                    # error reply; do not turn that closed peer into a thread
                    # exception or invent a delivered response.
                    if not owner.closed and owner.budget.stop is None:
                        raise

            def do_POST(self):
                self.connection.settimeout(2)
                headers_sent = False
                try:
                    if self.headers.get("Transfer-Encoding"):
                        raise TransportStop("configuration", "chunked requests unsupported")
                    length = int(self.headers.get("Content-Length", "-1"))
                    if not 0 <= length <= MAX_BODY:
                        raise TransportStop("configuration", "invalid request length")
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise TransportStop("configuration", "truncated request")
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise TransportStop("configuration", "request must be object")
                    if self.path == "/tools":
                        if body:
                            raise TransportStop("configuration", "tools request must be empty")
                        self.json_response(200, {"tools": [owner.browser_tool]})
                        return
                    if self.path == "/browser":
                        with owner.lock:
                            owner.check_open()
                            owner.actions += 1
                            action_id = owner.actions
                            write_json(owner.root / f"browser-{action_id:04d}.request.json", body)
                            # Callback performs source scope/extraction/sync before
                            # returning only pixel content and public action status.
                            result = owner.browser_callback(body)
                            owner.validate_tool_result(result)
                            images = image_records(result.get("content", []))
                            owner.images.update(i["sha256"] for i in images)
                            write_json(owner.root / f"browser-{action_id:04d}.result.json",
                                       {"content": result, "images": images})
                        self.json_response(200, result)
                        return
                    if not self.path.startswith("/provider/"):
                        raise TransportStop("configuration", "unsupported capability")
                    path = self.path[len("/provider"):]
                    with owner.lock:
                        owner.check_open()
                        owner.counter += 1
                        images = image_records(body)
                        write_json(owner.root / f"provider-{owner.counter:03d}.images.json",
                                   {"images": [{**r, "matches_created_pixel_image": r["sha256"] in owner.images}
                                               for r in images]})

                    def sink(kind, value):
                        nonlocal headers_sent
                        if kind == "headers":
                            self.send_response(value["status_code"])
                            content_type = next((v for k, v in value["headers"].items()
                                                 if k.lower() == "content-type"), "application/octet-stream")
                            self.send_header("Content-Type", content_type)
                            self.send_header("Connection", "close")
                            self.end_headers()
                            headers_sent = True
                        else:
                            self.wfile.write(value)
                            self.wfile.flush()
                    owner.transport.forward(path, body, sink, self.headers.get("anthropic-beta"))
                except TransportStop as error:
                    owner.budget.latch(error.category, str(error))
                    if not headers_sent:
                        self.stop_response(409, {"error": {"type": "mobile_attempt_stopped",
                                                          "category": error.category, "message": str(error)}})
                except Exception as error:
                    owner.budget.latch("bridge", f"{type(error).__name__}: {error}")
                    if not headers_sent:
                        self.stop_response(500, {"error": {"type": "bridge_error", "message": "Capability failed"}})
                finally:
                    self.close_connection = True

            def do_GET(self):
                self.json_response(404, {"error": {"message": "unsupported method"}})

        self.server = UnixServer(self.socket_path, Handler)
        Path(self.socket_path).chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .1}, daemon=True)
        self.thread.start()

    def check_open(self):
        if self.closed:
            raise TransportStop("cancelled", "attempt closed")
        if self.budget.stop:
            raise TransportStop(*self.budget.stop)
        if self.budget.remaining() <= 0:
            raise TransportStop("time_cap", "active CLI deadline reached")

    @staticmethod
    def validate_tool_result(result):
        if not isinstance(result, dict) or set(result) - {"content", "isError"}:
            raise TransportStop("bridge", "invalid pixel capability response")
        content = result.get("content")
        if not isinstance(content, list):
            raise TransportStop("bridge", "pixel content missing")
        for item in content:
            if not isinstance(item, dict):
                raise TransportStop("bridge", "pixel content malformed")
            if item.get("type") == "text" and set(item) == {"type", "text"} and isinstance(item["text"], str):
                continue
            if (item.get("type") == "image" and set(item) == {"type", "data", "mimeType"}
                    and item["mimeType"] == "image/png" and isinstance(item["data"], str)):
                continue
            raise TransportStop("bridge", "nonpixel capability response blocked")

    def close(self, *, cancel_transport=True):
        self.closed = True
        if cancel_transport:
            self.transport.cancel()
        try:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        finally:
            self.transport.cancel()
            Path(self.socket_path).unlink(missing_ok=True)
