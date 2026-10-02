#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent


def protected_runtime_origin() -> str | None:
    value = os.environ.get("CUA_SWE_EXTERNAL_SERVICE_ORIGIN", "").rstrip("/")
    if not value:
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("protected runtime origin must be a loopback HTTP origin")
    return value


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            source = (ROOT / "index.html").read_text(encoding="utf-8")
            origin = protected_runtime_origin()
            if origin:
                bootstrap = (
                    f'<script src="{origin}/runtime.js" '
                    'data-cua-swe-protected-runtime="1"></script>'
                )
                source = source.replace("</head>", bootstrap + "\n  </head>", 1)
            payload = source.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
