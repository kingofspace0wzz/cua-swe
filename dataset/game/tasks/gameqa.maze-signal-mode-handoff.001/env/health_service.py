#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


WALKABLE = [
    [1, 1], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1],
    [1, 2], [2, 2], [3, 2], [4, 2], [5, 2], [6, 2], [7, 2], [8, 2], [9, 2],
    [1, 3], [3, 3], [5, 3], [7, 3], [9, 3],
    [1, 4], [3, 4], [5, 4], [7, 4], [9, 4],
    [1, 5], [2, 5], [3, 5], [4, 5], [5, 5], [6, 5], [7, 5], [8, 5], [9, 5],
]

SCENARIO = {
    "width": 11,
    "height": 7,
    "tickMs": 120,
    "walkable": WALKABLE,
    "playerStart": {"x": 1, "y": 5},
    "pulse": {"x": 3, "y": 5},
    "exit": {"x": 9, "y": 1},
    "phase": {"initial": "corner", "next": "track", "ticks": 5},
    "alertTicks": 8,
    "releaseTicks": 4,
    "rover": {
        "dock": {"x": 5, "y": 3},
        "junction": {"x": 5, "y": 2},
        "cornerStep": {"x": 4, "y": 2},
        "trackStep": {"x": 6, "y": 2},
    },
    "seals": {
        "scenario": "route-seal-kestrel-731",
        "phase": "phase-proof-cedar-284",
        "release": "release-proof-mica-619",
        "branch": "branch-proof-lumen-452",
        "collision": "collision-proof-sable-907",
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/api/scenario":
            self._json(SCENARIO)
            return
        self.send_error(404)

    def _json(self, value: object) -> None:
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

