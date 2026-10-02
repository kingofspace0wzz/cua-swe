#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


IDENTITY = {"u": "u", "v": "v", "w": "w"}
FORWARD = {"u": "v", "v": "w", "w": "u"}
INVERSE = {"u": "w", "v": "u", "w": "v"}


class Handler(BaseHTTPRequestHandler):
    card_path: Path

    def send_payload(self, content_type: str, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_payload("application/json", b'{"status":"ok"}')
            return
        if self.path == "/ticket":
            payload = json.dumps(
                {
                    "alternatives": [IDENTITY, FORWARD, INVERSE],
                    "receipt": {"u": 31, "v": 47, "w": 59},
                    "issued": 1,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_payload("application/json", payload)
            return
        if self.path == "/route-card.png":
            self.send_payload("image/png", self.card_path.read_bytes())
            return
        self.send_error(404)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument(
        "--card",
        type=Path,
        default=Path(__file__).resolve().parent / "env" / "route-card.png",
    )
    args = parser.parse_args()
    Handler.card_path = args.card.resolve()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
