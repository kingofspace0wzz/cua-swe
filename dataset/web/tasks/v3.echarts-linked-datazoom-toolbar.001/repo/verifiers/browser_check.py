#!/usr/bin/env python3
# Behavioral verifier for the Fleet Analytics Console linked-zoom fixture.
#
# The decisive behavior lives only in the harness-owned workspace API
# (env/service.mjs) and in the console's own live rendering; no resolved linked
# window, mapping policy, or expected range is copied into this file or the
# product source. For each protected workspace the verifier:
#   * starts the workspace API (a fresh CONTRACT_VARIANT) on an ephemeral port
#     and forwards /api/workspace/ to it;
#   * loads the console, which draws the master chart, the linked charts, and
#     the toolbox;
#   * runs the workspace's scripted toolbox rubber-band gesture through the same
#     code path a manual selection runs;
#   * reads each linked chart's live rendered visible window (the concrete data
#     interval printed in its panel header) straight off the DOM read-out;
#   * requires that every linked chart frames the slice of its OWN domain that
#     corresponds to the fraction the analyst rubber-banded on the master,
#     recomputed live from that chart's served domain and the served gesture.
#
# A build that copies the master's raw data window onto siblings, or that copies
# the master's raw sample-index range onto siblings, lands the linked charts on
# the wrong slice for charts whose domain differs from the master's, and fails.
# Nothing is hard-coded: every target is recomputed from what the running
# workspace serves.
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

VARIANTS = ["alpha", "beta", "gamma"]


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
    raise RuntimeError(f"workspace API did not start on {port}: {last}")


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
            if p.path.startswith("/api/workspace/"):
                url = f"http://127.0.0.1:{upstream_port}{self.path}"
                try:
                    with urllib.request.urlopen(url, timeout=3) as r:
                        body = r.read()
                        ctype = r.headers.get("content-type", "application/json")
                        link = r.headers.get("x-workspace-link")
                except Exception:
                    self.send_error(502)
                    return
                self.send_response(200)
                self.send_header("content-type", ctype)
                if link:
                    self.send_header("x-workspace-link", link)
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


READ_WINDOW_JS = r"""
(chartId) => {
  const el = document.querySelector(`[data-chart-window="${chartId}"]`);
  if (!el) return null;
  return { lo: Number(el.dataset.lo), hi: Number(el.dataset.hi) };
}
"""

MANIFEST_JS = "() => fetch('/api/workspace/manifest').then(r => r.json())"
RUN_JS = "(win) => window.__runToolboxZoom(win)"


def _expected_window(domain, fraction):
    # The correct linked window frames the same fraction of THIS chart's own
    # domain that the analyst rubber-banded on the master. This is the contract
    # the verifier owns; it is not present in agent-visible source.
    d0, d1 = domain
    span = d1 - d0
    return (d0 + fraction[0] * span, d0 + fraction[1] * span)


def _check_variant(page, base) -> dict:
    page.goto(base)
    page.wait_for_selector("body[data-ready=\"1\"]", timeout=15000)
    page.wait_for_timeout(80)
    manifest = page.evaluate(MANIFEST_JS)
    charts = manifest["charts"]
    fraction = manifest["gesture"]["window"]
    linked = [c for c in charts if c["role"] == "linked"]
    title = manifest["title"]

    # Baseline: every linked chart shows its full domain before the gesture.
    baseline = {c["id"]: page.evaluate(READ_WINDOW_JS, c["id"]) for c in linked}
    base_full = all(
        abs(baseline[c["id"]]["lo"] - c["domain"][0]) <= 1e-6
        and abs(baseline[c["id"]]["hi"] - c["domain"][1]) <= 1e-6
        for c in linked
    )

    # Run the scripted toolbox rubber-band on the master.
    page.evaluate(RUN_JS, fraction)
    page.wait_for_timeout(40)

    per_chart = []
    ok_all = base_full
    for c in linked:
        got = page.evaluate(READ_WINDOW_JS, c["id"])
        exp_lo, exp_hi = _expected_window(c["domain"], fraction)
        # Tolerance scales with the chart's own domain span so a narrow-domain
        # chart is not judged by a coarse absolute epsilon.
        span = c["domain"][1] - c["domain"][0]
        eps = max(0.05, span * 0.01)
        moved = (
            abs(got["lo"] - c["domain"][0]) > eps
            or abs(got["hi"] - c["domain"][1]) > eps
        )
        correct = abs(got["lo"] - exp_lo) <= eps and abs(got["hi"] - exp_hi) <= eps
        ok_all = ok_all and moved and correct
        per_chart.append({
            "id": c["id"],
            "domain": c["domain"],
            "expected": [round(exp_lo, 3), round(exp_hi, 3)],
            "got": got,
            "moved": moved,
            "correct": correct,
            "eps": round(eps, 4),
        })

    return {
        "workspace": title,
        "fraction": fraction,
        "baseline_full": base_full,
        "passed": bool(ok_all),
        "linked": per_chart,
    }


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
            page = browser.new_page(viewport={"width": 1280, "height": 720})
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
                seen.add(res.get("workspace"))
                checks.append(res)
            browser.close()
        distinct_ok = len([s for s in seen if s]) == len(VARIANTS)
        passed = distinct_ok and all(c.get("passed") for c in checks)
        print(json.dumps({"passed": passed, "distinct_workspaces": distinct_ok,
                          "checks": checks}, indent=2))
        assert passed, "each linked chart must zoom to the window framing the same domain slice as the master rubber-band on every workspace"
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
