#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "deterministic_fixture.js"
BOOTSTRAP = r"""(() => {
  "use strict";

  const STABILIZATION_DELAYS_MS = [0, 250, 750, 1500];
  let bootstrapCancelled = false;
  let originalReset = null;
  let preActionGuard = null;

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function runtimeAvailable() {
    return (
      window.gameAPI &&
      typeof window.gameAPI.reset === "function" &&
      typeof window.__cuaSweInstallHextrisCascadeFixture === "function" &&
      window.MainHex &&
      window.settings &&
      window.waveone
    );
  }

  function fixtureIsStable() {
    if (typeof window.__cuaSweInspectHextrisCascadeFixture !== "function") {
      return false;
    }
    const observed = window.__cuaSweInspectHextrisCascadeFixture();
    return (
      observed &&
      observed.fixtureId === "hextris-cascade-fixture-v1" &&
      observed.score === 0 &&
      observed.position === 0 &&
      observed.activeBlocks === 1 &&
      observed.api &&
      observed.api.game_state &&
      observed.api.game_state.environment &&
      observed.api.game_state.environment.settled_blocks === 7
    );
  }

  function protectedIncomingBlock() {
    if (!Array.isArray(window.blocks)) return null;
    for (const block of window.blocks) {
      if (block.__cuaSweFixtureRole === "incoming_red_v1") return block;
    }
    return null;
  }

  function startPreActionGuard() {
    if (preActionGuard !== null) {
      window.clearInterval(preActionGuard);
    }
    preActionGuard = window.setInterval(() => {
      if (!runtimeAvailable()) return;
      if (window.__cuaSweFixtureMode === "pair-only") {
        window.clearInterval(preActionGuard);
        preActionGuard = null;
        return;
      }
      const incoming = protectedIncomingBlock();
      if (
        incoming &&
        (window.MainHex.position !== 0 || incoming.iter > 0)
      ) {
        window.clearInterval(preActionGuard);
        preActionGuard = null;
        window.__cuaSweProtectedGuardReleased = true;
        return;
      }
      if (!fixtureIsStable()) {
        window.__cuaSweInstallHextrisCascadeFixture();
      }
    }, 100);
  }

  async function waitForRuntime() {
    while (!runtimeAvailable()) {
      await sleep(20);
    }
  }

  function wrapReset() {
    if (window.__cuaSweProtectedResetWrapped) return;
    originalReset = window.gameAPI.reset.bind(window.gameAPI);
    window.gameAPI.reset = async function protectedReset(options) {
      bootstrapCancelled = true;
      const result = await originalReset(options);
      if (result && result.ok) {
        window.__cuaSweInstallHextrisCascadeFixture();
        startPreActionGuard();
        window.__cuaSweProtectedRuntimeReady = true;
      }
      return result;
    };
    window.__cuaSweProtectedResetWrapped = true;
  }

  async function installPreparedChallenge() {
    await waitForRuntime();
    wrapReset();

    let elapsed = 0;
    for (const targetDelay of STABILIZATION_DELAYS_MS) {
      await sleep(targetDelay - elapsed);
      elapsed = targetDelay;
      if (bootstrapCancelled) return;
      const result = await originalReset({level: 1});
      if (!result || !result.ok) {
        throw new Error("protected Hextris reset failed");
      }
      window.__cuaSweInstallHextrisCascadeFixture();
      startPreActionGuard();
    }

    await sleep(100);
    if (bootstrapCancelled) return;
    if (!fixtureIsStable()) {
      window.setTimeout(installPreparedChallenge, 100);
      return;
    }
    window.__cuaSweProtectedRuntimeReady = true;
  }

  if (document.readyState === "complete") {
    window.setTimeout(installPreparedChallenge, 0);
  } else {
    window.addEventListener("load", installPreparedChallenge, {once: true});
  }
})();"""


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
