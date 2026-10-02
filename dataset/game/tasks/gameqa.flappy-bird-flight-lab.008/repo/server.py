#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4477)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    handler = lambda *handler_args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *handler_args,
        directory=str(root),
        **kwargs,
    )
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
