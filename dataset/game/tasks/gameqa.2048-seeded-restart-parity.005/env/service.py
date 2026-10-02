#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


OPENINGS = {
    160: [
        [0, 0, 0, 4],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 4],
    ],
    1337: [
        [0, 0, 0, 2],
        [0, 0, 0, 0],
        [0, 0, 2, 0],
        [0, 0, 0, 0],
    ],
    3735928559: [
        [0, 0, 0, 0],
        [4, 0, 2, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ready": True})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/check":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            seed = int(payload["seed"]) & 0xFFFFFFFF
            board = payload["board"]
            expected = OPENINGS.get(seed)
            self._json(
                200,
                {
                    "available": expected is not None,
                    "match": expected is not None and board == expected,
                },
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"available": False, "match": None})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
