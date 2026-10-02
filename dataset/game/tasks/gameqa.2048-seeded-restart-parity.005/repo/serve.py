#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Handler(SimpleHTTPRequestHandler):
    service_origin = ""

    def _proxy_runtime_check(self) -> None:
        if not self.service_origin:
            body = json.dumps({"available": False, "match": None}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        length = int(self.headers.get("Content-Length", "0"))
        incoming = self.rfile.read(length)
        request = Request(
            self.service_origin + "/check",
            data=incoming,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=2) as response:
                body = response.read()
                status = response.status
        except HTTPError as error:
            body = error.read()
            status = error.code
        except (OSError, URLError):
            body = json.dumps({"available": False, "match": None}).encode()
            status = 502

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/runtime-check":
            self._proxy_runtime_check()
            return
        self.send_error(404)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    Handler.service_origin = os.environ.get("CUA_SWE_PARITY_SERVICE_ORIGIN", "")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
