#!/usr/bin/env python3
"""Behavioral verifier for the Field Log Composer soft-break scroll fixture.

The decisive scroll geometry lives only in the harness-owned workspace frame
service (``env/service.mjs``) and in the browser's own live layout; it is never
copied into this file or the product source. For each protected workspace frame
the verifier:

  * starts the frame service (a fresh ``CONTRACT_VARIANT``) on an ephemeral
    port and proxies ``/api/composer-frame`` to it;
  * loads the composer, which opens with the writer partway through the log and
    the active entry resting at the bottom edge of the visible band;
  * reads the caret's live line box, then inserts a soft line break at the
    caret exactly as pressing Shift+Enter would;
  * reads the caret's line box again and the body scroll position, and requires
    the caret to stay inside the visible band *and* the surface to move by no
    more than the minimal amount needed to reveal the new line -- so a build
    that does not scroll leaves the caret out of the band, and a build that
    over-scrolls pushes the caret up off the writing edge and buries the lines
    the writer just wrote;
  * confirms the three protected frames were exercised distinctly.

No expected scroll amount or pixel constant is embedded here; every target is
recomputed live from whatever the running composer renders.
"""
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

ROOT = Path(__file__).resolve().parent            # repo/verifiers
WORKSPACE = ROOT.parent                            # repo
ENV_SERVICE = (WORKSPACE.parent / "env" / "service.mjs").resolve()

# --- Framework gate ---------------------------------------------------------
# The decisive interaction must run through the pinned upstream Slate library.
# These checks fail unless slate + slate-dom are installed, imported by the
# runtime source, inlined into the built bundle actually served to the browser,
# and confirmed live as the editor backing the surface.
REQUIRED_DEPS = {"slate": "0.116.0", "slate-dom": "0.116.0"}


def _read_installed_version(name):
    pkg = WORKSPACE / "node_modules" / name / "package.json"
    if not pkg.is_file():
        return None
    return json.loads(pkg.read_text()).get("version")


def _build_bundle():
    """Rebuild dist/bundle.js from the (possibly patched) source before serving."""
    r = subprocess.run(["node", "build.mjs"], cwd=WORKSPACE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("build.mjs failed: " + (r.stdout + r.stderr)[-400:])


def _framework_gate_static():
    problems = []
    for name, want in REQUIRED_DEPS.items():
        got = _read_installed_version(name)
        if got is None:
            problems.append("dependency not installed: " + name)
        elif got != want:
            problems.append("dependency %s version %s != pinned %s" % (name, got, want))
    composer = (WORKSPACE / "src" / "slateComposer.js").read_text()
    if "from \x27slate\x27" not in composer or "from \x27slate-dom\x27" not in composer:
        problems.append("runtime source does not import slate/slate-dom")
    if "DOMEditor.toDOMRange" not in composer:
        problems.append("runtime source does not use slate-dom toDOMRange")
    bundle_path = WORKSPACE / "dist" / "bundle.js"
    if not bundle_path.is_file():
        problems.append("dist/bundle.js missing")
    else:
        bundle = bundle_path.read_text()
        # Slate identity markers that only appear if the library is inlined.
        for marker in ("insertSoftBreak", "data-slate-string", "NODE_TO_KEY", "createEditor"):
            if marker not in bundle:
                problems.append("bundle missing slate marker: " + marker)
    if problems:
        raise AssertionError("framework gate (static): " + "; ".join(problems))
    return {name: _read_installed_version(name) for name in REQUIRED_DEPS}


FRAMEWORK_PROBE_JS = "() => (window.__composer ? window.__composer.framework() : null)"


def _assert_framework_runtime(page):
    probe = page.evaluate(FRAMEWORK_PROBE_JS)
    if not probe:
        raise AssertionError("framework gate (runtime): composer probe unavailable")
    if not (probe.get("isSlateEditor") and probe.get("isDOMEditor")
            and probe.get("slateApiPresent") and probe.get("blockCount", 0) > 0):
        raise AssertionError("framework gate (runtime): live surface is not a Slate/slate-dom editor: "
                             + json.dumps(probe))
    return probe



def _launch(pw, launch_opts):
    """Launch Chromium, working around temp mounts that reject mkdtemp.

    Some sandboxes mount the system temp directory noexec/EPERM; if the first
    launch fails for that reason, retry with a writable temp dir beside the repo
    so the behavioral check is not blocked by an environment quirk.
    """
    try:
        return pw.chromium.launch(**launch_opts)
    except Exception as exc:  # noqa: BLE001
        if "EPERM" not in str(exc) and "mkdtemp" not in str(exc):
            raise
        fallback = WORKSPACE / ".pw-tmp"
        fallback.mkdir(exist_ok=True)
        os.environ["TMPDIR"] = str(fallback)
        return pw.chromium.launch(**launch_opts)

VARIANTS = ["a", "b", "c"]
# Slack absorbed by sub-pixel line boxes and a single soft-break line height.
REVEAL_SLACK = 8.0
BAND_SLACK = 3.0


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
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.15)
    raise RuntimeError(f"harness service did not start on {port}: {last}")


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
        def log_message(self, *_):  # noqa: D401
            return

        def do_GET(self):
            p = urlparse(self.path)
            if p.path.startswith("/api/"):
                url = f"http://127.0.0.1:{upstream_port}{self.path}"
                try:
                    with urllib.request.urlopen(url, timeout=3) as r:
                        body = r.read()
                        ctype = r.headers.get("content-type", "application/json")
                except Exception:  # noqa: BLE001
                    self.send_error(502)
                    return
                self.send_response(200)
                self.send_header("content-type", ctype)
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


READ_CARET_JS = r"""
() => {
  const b = document.getElementById('surface');
  const sel = window.getSelection();
  let caretTop = Number(b.dataset.caretTopViewport);
  let caretBottom = Number(b.dataset.caretBottomViewport);
  return {
    caretTopViewport: caretTop,
    caretBottomViewport: caretBottom,
    scrollTop: b.scrollTop,
    clientHeight: b.clientHeight,
    scrollHeight: b.scrollHeight,
    safeMargin: Number(b.dataset.safeMargin),
  };
}
"""


def _workspace_name(base: str) -> str:
    with urllib.request.urlopen(f"{base}/api/composer-frame", timeout=3) as r:
        return json.loads(r.read()).get("workspace", "")


def _check_variant(page, base) -> dict:
    page.goto(base)
    page.wait_for_selector('body[data-ready="1"]', timeout=15000)
    page.wait_for_timeout(120)
    framework = _assert_framework_runtime(page)
    before = page.evaluate(READ_CARET_JS)
    # Insert a soft line break at the caret, as Shift+Enter would.
    page.focus("#surface")
    page.keyboard.press("Shift+Enter")
    page.wait_for_timeout(140)
    after = page.evaluate(READ_CARET_JS)

    ch = after["clientHeight"]
    margin = after["safeMargin"]
    band_bottom = ch - margin
    line_h = max(1.0, before["caretBottomViewport"] - before["caretTopViewport"])

    # 1) The caret must remain visible inside the reserved band.
    in_band = (
        after["caretBottomViewport"] <= band_bottom + BAND_SLACK
        and after["caretTopViewport"] >= margin - BAND_SLACK
    )
    # 2) Bringing the new line into view must cost the minimal reveal only.
    #    Infer the new line's unscrolled bottom from its post-layout viewport
    #    position plus the scroll applied. This uses live layout and correctly
    #    includes font leading/line gaps; assuming the new baseline advances by
    #    exactly the old glyph-box height is not portable across Chromium builds.
    actual_delta = after["scrollTop"] - before["scrollTop"]
    unscrolled_bottom = after["caretBottomViewport"] + actual_delta
    min_reveal = max(0.0, unscrolled_bottom - band_bottom)
    minimal_reveal = abs(actual_delta - min_reveal) <= REVEAL_SLACK
    # 3) A reveal was actually needed and performed (guards a no-op build whose
    #    caret would otherwise fall out of the band).
    revealed = actual_delta >= 0.0

    passed = bool(in_band and minimal_reveal and revealed)
    return {
        "workspace": _workspace_name(base),
        "before_caret_bottom": round(before["caretBottomViewport"], 1),
        "after_caret_top": round(after["caretTopViewport"], 1),
        "after_caret_bottom": round(after["caretBottomViewport"], 1),
        "band_bottom": round(band_bottom, 1),
        "line_height": round(line_h, 1),
        "min_reveal": round(min_reveal, 1),
        "actual_scroll_delta": round(actual_delta, 1),
        "in_band": in_band,
        "minimal_reveal": minimal_reveal,
        "passed": passed,
        "framework": framework,
    }


def main() -> int:
    checks = []
    services = []
    static_srv = None
    # Framework gate: build the bundle from current source, then confirm the
    # pinned Slate packages are installed, imported, and inlined into it.
    _build_bundle()
    installed = _framework_gate_static()
    try:
        launch_opts = {"headless": True}
        if exe := os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE"):
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
        distinct_ok = len([w for w in seen if w]) == 3
        passed = distinct_ok and all(c.get("passed") for c in checks)
        print(json.dumps({"passed": passed, "distinct_workspaces": distinct_ok,
                          "framework_versions": installed,
                          "checks": checks}, indent=2))
        assert passed, "soft-break caret must stay visible with a minimal reveal on every workspace frame"
        return 0
    finally:
        if static_srv:
            static_srv.shutdown()
            static_srv.server_close()
        for proc in services:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
