#!/usr/bin/env python3
# Behavioral verifier for the Allocation Ring Studio responsive-ring fixture.
#
# The decisive behavior lives only in the harness-owned board service
# (env/service.mjs) and in the studio's own live rendering; no settled plot box,
# resolved radius, or resolved center is copied into this file or the product
# source. For each protected board this verifier:
#   * starts the board service (a fresh CONTRACT_VARIANT) on an ephemeral port
#     and forwards /studio/board to it;
#   * loads the studio, which builds the card, docks the legend, and draws the
#     live ring under a ResizeObserver;
#   * walks every profile (widescreen, sidebar, stacked, compact) through the
#     same code path a profile click drives;
#   * measures the settled plot area straight off the DOM and reads the live
#     ring's rendered outer radius and fit flag from the studio's read-out;
#   * requires that on EVERY profile the ring is sized to the settled plot area
#     (radius == the tighter half-extent of the on-screen plot times the served
#     ring scale) and stays within its frame, recomputed live from what the
#     board serves.
#
# A build that sizes the ring from the raw card box (ignoring the legend dock
# and gutter) over-sizes the ring so it overflows the plot on every docked
# profile and fails. A build that only subtracts a fixed gutter fits the inline
# profile but still over-sizes the docked ones and fails. Nothing is hard-coded:
# every target is recomputed from what the running board serves and from the
# plot box the browser actually lays out.
from __future__ import annotations

import json
import mimetypes
import os
import socket
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
ENV_SERVICE = (WORKSPACE.parent / "env" / "service.mjs").resolve()

VARIANTS = ["ledger", "pension", "sovereign"]
PROFILES = ["widescreen", "sidebar", "stacked", "compact"]


def _launch(pw, launch_opts):
    try:
        return pw.chromium.launch(**launch_opts)
    except Exception as exc:
        if "EPERM" not in str(exc) and "mkdtemp" not in str(exc):
            raise
        fallback = WORKSPACE / ".pw-tmp"
        fallback.mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(fallback)
        return pw.chromium.launch(**launch_opts)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception as exc:
            last = exc
            time.sleep(0.15)
    raise RuntimeError(f"board service did not start on {port}: {last}")


def _start_service(variant: str):
    port = _free_port()
    env = dict(os.environ)
    env["CONTRACT_VARIANT"] = variant
    proc = subprocess.Popen(
        ["node", str(ENV_SERVICE), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    _wait_health(port)
    return proc, port


def _static_server(upstream_port: int):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_GET(self):
            p = urlparse(self.path)
            if p.path.startswith("/studio/board"):
                url = f"http://127.0.0.1:{upstream_port}{self.path}"
                try:
                    with urllib.request.urlopen(url, timeout=3) as r:
                        body = r.read()
                        ctype = r.headers.get("content-type", "application/json")
                        seal = r.headers.get("x-board-seal")
                except Exception:
                    self.send_error(502)
                    return
                self.send_response(200)
                self.send_header("content-type", ctype)
                if seal:
                    self.send_header("x-board-seal", seal)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            rel = "index.html" if p.path == "/" else p.path.lstrip("/")
            target = (WORKSPACE / rel).resolve()
            if not str(target).startswith(str(WORKSPACE)) or not target.is_file():
                target = WORKSPACE / "index.html"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("content-type", mimetypes.guess_type(target.name)[0] or "text/plain")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


SELECT_JS = "(p) => window.__selectProfile(p)"
BOARD_JS = "(p) => fetch(`/studio/board?profile=${p}`).then(r => r.json())"
PLOT_JS = r"""
() => {
  const el = document.querySelector('.plot-area');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { w: r.width, h: r.height };
}
"""
READ_JS = r"""
() => {
  const el = document.getElementById('live-readout');
  if (!el) return null;
  return {
    outer: Number(el.dataset.outer),
    cx: Number(el.dataset.cx),
    cy: Number(el.dataset.cy),
    plotw: Number(el.dataset.plotw),
    ploth: Number(el.dataset.ploth),
    fits: el.dataset.fits === '1',
  };
}
"""


def _check_variant(page, base) -> dict:
    page.goto(base)
    page.wait_for_selector('body[data-ready="1"]', timeout=15000)
    per_profile = []
    ok_all = True
    title = None
    for profile in PROFILES:
        page.evaluate(SELECT_JS, profile)
        page.wait_for_function(
            "(p) => document.body.dataset.profile === p && document.body.dataset.ready === '1'",
            arg=profile,
            timeout=8000,
        )
        page.wait_for_timeout(80)
        board = page.evaluate(BOARD_JS, profile)
        title = board["title"]
        ring_scale = board["ringScale"]
        plot = page.evaluate(PLOT_JS)
        read = page.evaluate(READ_JS)
        # Expected radius derives from the settled on-screen plot box.
        expected = (min(plot["w"], plot["h"]) / 2) * ring_scale
        # Tolerance is a couple of px plus a small fraction of the expected size
        # to absorb sub-pixel rounding, but far tighter than the raw-card error.
        eps = max(2.5, expected * 0.03)
        sized_to_plot = abs(read["outer"] - expected) <= eps
        fits = bool(read["fits"])
        correct = sized_to_plot and fits
        ok_all = ok_all and correct
        per_profile.append({
            "profile": profile,
            "dock": board["legend"]["dock"],
            "plot": {"w": round(plot["w"], 1), "h": round(plot["h"], 1)},
            "expected_outer": round(expected, 1),
            "got_outer": read["outer"],
            "eps": round(eps, 2),
            "sized_to_plot": sized_to_plot,
            "fits": fits,
            "correct": correct,
        })
    return {"board": title, "passed": bool(ok_all), "profiles": per_profile}


def main() -> int:
    checks = []
    services = []
    static_srv = None
    try:
        _tmp = WORKSPACE / ".pw-tmp"
        _tmp.mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(_tmp)
        launch_opts = {"headless": True}
        exe = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
        if exe:
            launch_opts["executable_path"] = exe
        with sync_playwright() as pw:
            browser = _launch(pw, launch_opts)
            page = browser.new_page(viewport={"width": 1360, "height": 900})
            seen = set()
            for variant in VARIANTS:
                proc, sport = _start_service(variant)
                services.append(proc)
                static_srv, base = _static_server(sport)
                try:
                    res = _check_variant(page, base)
                finally:
                    static_srv.shutdown()
                    static_srv.server_close()
                    static_srv = None
                seen.add(res.get("board"))
                checks.append(res)
            browser.close()
        distinct_ok = len([s for s in seen if s]) == len(VARIANTS)
        passed = distinct_ok and all(c.get("passed") for c in checks)
        print(json.dumps({"passed": passed, "distinct_boards": distinct_ok,
                          "checks": checks}, indent=2))
        assert passed, "the live ring must be sized to the settled plot area and stay within its frame on every profile of every board"
        return 0
    finally:
        if static_srv:
            static_srv.shutdown()
            static_srv.server_close()
        for proc in services:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
