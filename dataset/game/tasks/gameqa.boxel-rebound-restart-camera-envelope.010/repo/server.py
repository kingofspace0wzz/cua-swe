#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=51700)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), SimpleHTTPRequestHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
