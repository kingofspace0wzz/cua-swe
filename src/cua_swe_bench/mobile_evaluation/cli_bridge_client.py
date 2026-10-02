"""Source-sandbox side of the CLI bridge: localhost proxy and stdio pixel MCP.

No credentials, provider URL or host-runtime paths are available in this module.
The only cross-namespace interface is one mounted Unix-domain capability socket.
"""
from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import sys
import threading

MAX_BODY = 32 * 1024 * 1024


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout=180):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def request(path, endpoint, value):
    connection = UnixHTTP(path)
    try:
        body = json.dumps(value).encode()
        connection.request("POST", endpoint, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError("oversized capability response")
        decoded = json.loads(raw)
        if response.status != 200:
            raise ValueError(decoded.get("error", {}).get("message", "capability unavailable"))
        return decoded
    finally:
        connection.close()


def proxy(socket_path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_POST(self):
            self.connection.settimeout(2)
            connection = UnixHTTP(socket_path, timeout=605)
            started = False
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked request body unsupported")
                size = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= size <= MAX_BODY:
                    raise ValueError("invalid request length")
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError("truncated request")
                # Host validates the selected path/model and all budgets.
                headers = {"Content-Type": "application/json", "Connection": "close"}
                if self.headers.get("anthropic-beta"):
                    headers["anthropic-beta"] = self.headers["anthropic-beta"]
                connection.request("POST", "/provider" + self.path, raw, headers)
                response = connection.getresponse()
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Connection", "close")
                self.end_headers()
                started = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (OSError, ValueError, http.client.HTTPException):
                if not started:
                    self.send_response(502)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
            finally:
                self.close_connection = True
                connection.close()

        def do_GET(self):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
    thread.start()
    return server, thread


def stdio_mcp(socket_path, source=None, destination=None):
    source = source or sys.stdin
    destination = destination or sys.stdout
    initialized = False
    ready = False
    versions = {"2024-11-05", "2025-03-26", "2025-06-18"}
    for line in source:
        value = None
        try:
            if len(line.encode()) > MAX_BODY:
                raise ValueError("oversized MCP request")
            value = json.loads(line)
            if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
                raise ValueError("expected JSON-RPC object")
            method, params = value.get("method"), value.get("params", {})
            if "id" not in value:
                if method == "notifications/initialized" and initialized:
                    ready = True
                continue
            if method == "initialize":
                if initialized or not isinstance(params, dict):
                    raise ValueError("invalid initialize")
                version = params.get("protocolVersion")
                result = {
                    "protocolVersion": version if version in versions else "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "mobile-pixels", "version": "1.0.0"},
                }
                initialized = True
            elif method == "ping":
                result = {}
            elif not ready:
                raise ValueError("MCP initialization incomplete")
            elif method == "tools/list":
                result = request(socket_path, "/tools", {})
            elif method == "tools/call":
                if not isinstance(params, dict) or params.get("name") != "browser":
                    raise ValueError("unknown tool")
                result = request(socket_path, "/browser", params.get("arguments", {}))
            else:
                raise ValueError("unsupported MCP method")
            output = {"jsonrpc": "2.0", "id": value["id"], "result": result}
        except Exception as error:
            if isinstance(value, dict) and "id" not in value:
                continue
            output = {"jsonrpc": "2.0", "id": value.get("id") if isinstance(value, dict) else None,
                      "error": {"code": -32602, "message": str(error)}}
        destination.write(json.dumps(output, separators=(",", ":")) + "\n")
        destination.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--mode", choices=["mcp", "proxy"], required=True)
    args = parser.parse_args()
    if args.mode == "mcp":
        stdio_mcp(args.socket)
    else:
        server, thread = proxy(args.socket)
        print(json.dumps({"base_url": f"http://127.0.0.1:{server.server_address[1]}"}), flush=True)
        try:
            # Owner closes stdin to stop this owned helper.
            sys.stdin.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
