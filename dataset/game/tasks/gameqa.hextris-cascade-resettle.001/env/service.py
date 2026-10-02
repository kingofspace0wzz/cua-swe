#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "deterministic_fixture.js"
BOOTSTRAP = r"""
(() => {
  "use strict";

  async function installPreparedChallenge() {
    if (
      !window.gameAPI ||
      typeof window.gameAPI.reset !== "function" ||
      typeof window.__cuaSweInstallHextrisCascadeFixture !== "function"
    ) {
      window.setTimeout(installPreparedChallenge, 20);
      return;
    }

    if (!window.__cuaSweProtectedResetWrapped) {
      const originalReset = window.gameAPI.reset.bind(window.gameAPI);
      window.gameAPI.reset = async function protectedReset(options) {
        const result = await originalReset(options);
        if (result && result.ok) {
          window.__cuaSweInstallHextrisCascadeFixture();
        }
        return result;
      };
      window.__cuaSweProtectedResetWrapped = true;
    }

    await window.gameAPI.reset({level: 1});
    window.__cuaSweProtectedRuntimeReady = true;
  }

  if (document.readyState === "complete") {
    window.setTimeout(installPreparedChallenge, 0);
  } else {
    window.addEventListener("load", installPreparedChallenge, {once: true});
  }
})();
"""


class Handler(BaseHTTPRequestHandler):
    def send_payload(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_payload(200, "text/plain; charset=utf-8", b"ok\n")
            return
        if path == "/runtime.js":
            payload = (
                FIXTURE.read_text(encoding="utf-8") + "\n" + BOOTSTRAP
            ).encode("utf-8")
            self.send_payload(
                200,
                "text/javascript; charset=utf-8",
                payload,
            )
            return
        self.send_payload(404, "text/plain; charset=utf-8", b"not found\n")

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
