#!/usr/bin/env python3
"""Behavioral verifier for the Threadloop collaborative paste-scroll surface.

The decisive settling policy lives only in the harness-owned collaboration
service (``env/service.mjs``) and is never copied into this file or the product
source. For every protected session the verifier:

  * starts the harness service (a fresh ``CONTRACT_VARIANT``) on an ephemeral
    port and proxies ``/api/session`` to it;
  * loads the reading surface, lets it park the reader where the session says,
    and records -- from the *live* layout -- where the reading-anchor block sits
    in the viewport before anything is pasted;
  * applies the one pending collaborative paste the way a person would (the sync
    control / keyboard shortcut);
  * reads the *rendered* result back: where the inserted block landed and where
    the reading anchor now sits;
  * requires a reading experience that is consistent with who authored the
    paste and where that author is reading -- an update the reader is meant to
    see (their own paste, or a paste from a collaborator reading here with them)
    must become visible, while an update from a collaborator working elsewhere
    must leave the reader's place in the document undisturbed.

The pass condition is expressed as reading behavior measured from live layout;
no expected scroll offset or pixel constant is embedded here, and the per-author
expectation is applied uniformly rather than copied from a table of answers.
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

ROOT = Path(__file__).resolve().parent           # repo/verifiers
WORKSPACE = ROOT.parent                           # repo
ENV_SERVICE = (WORKSPACE.parent / "env" / "service.mjs").resolve()

VARIANTS = ["a", "b", "c", "d", "e"]


def _build_bundle() -> None:
    """Bundle the app from the current source before serving it.

    The reading surface loads ``dist/app.bundle.js``, which esbuild produces by
    importing the pinned upstream ``quill`` package. Rebuilding here guarantees
    the verifier always exercises the source under test (including any applied
    repair) rather than a stale bundle, and re-links the real Quill runtime on
    the exact path the browser loads.
    """
    r = subprocess.run(["node", "build.mjs"], cwd=str(WORKSPACE),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("build failed: " + (r.stderr or r.stdout)[-400:])


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


def _fetch_session(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/api/session", timeout=3) as r:
        return json.loads(r.read())


# Runtime framework gate. The reading surface must be driven by the real,
# installed Quill package on the exact path the browser loads -- not a wrapper,
# a renamed copy, or a CDN. This checks both the served application bundle
# (Quill's own source must be linked into it) and the live editor (Quill's
# runtime must have produced its editor DOM and be reachable on the instance).
QUILL_RUNTIME_JS = r"""
() => {
  const host = document.getElementById('reader');
  const editor = host && host.querySelector('.ql-editor');
  const container = host && host.classList.contains('ql-container');
  const blotRoot = !!(editor && editor.classList.contains('ql-editor')
                      && editor.getAttribute('contenteditable') !== null);
  const lineCount = editor ? editor.querySelectorAll('[data-block-id]').length : 0;
  return { hasContainer: !!container, hasEditor: !!editor, blotRoot, lineCount };
}
"""


def _assert_quill_runtime(page, base: str) -> dict:
    with urllib.request.urlopen(f"{base}/dist/app.bundle.js", timeout=5) as r:
        bundle = r.read().decode("utf-8", "replace")
    fp = [("ql-editor" in bundle),
          ("ql-container" in bundle),
          ("Quill" in bundle),
          ("blot" in bundle.lower())]
    bundle_ok = all(fp)
    page.goto(base)
    page.wait_for_selector("#reader .ql-editor [data-block-id]", timeout=8000)
    live = page.evaluate(QUILL_RUNTIME_JS)
    line_ok = int(live["lineCount"]) != 0
    live_ok = bool(live["hasContainer"] and live["hasEditor"] and live["blotRoot"] and line_ok)
    return {
        "bundle_contains_quill": bundle_ok,
        "bundle_fingerprints": fp,
        "live_quill_dom": live_ok,
        "live": live,
        "ok": bundle_ok and live_ok,
    }


# Measure, in reader-region viewport coordinates, where a given block sits and
# whether the inserted block is inside the visible region.
MEASURE_JS = r"""
(args) => {
  const reader = document.querySelector('#reader .ql-editor');
  const rr = reader.getBoundingClientRect();
  function topOf(id) {
    const el = reader.querySelector('[data-block-id="' + id + '"]');
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { top: b.top - rr.top, bottom: b.bottom - rr.top, h: b.height };
  }
  return {
    regionHeight: reader.clientHeight,
    scrollTop: reader.scrollTop,
    anchor: topOf(args.anchorId),
    inserted: topOf(args.insertedId),
    applied: reader.dataset.pasteApplied === '1',
  };
}
"""


def _check_variant(page, base) -> dict:
    session = _fetch_session(base)
    anchor_id = session["readerAnchorId"]
    inserted_id = session["paste"]["block"]["id"]
    author_id = session["paste"]["actorId"]
    author = next((p for p in session["presence"] if p["actorId"] == author_id), None)
    actor_kind = author["actorKind"] if author else ""
    actor_focus = (author.get("focus") if author else "") or ""

    page.goto(base)
    # The reading surface is a real Quill editor; wait for Quill to mount and
    # render its line boxes before measuring.
    page.wait_for_selector("#reader .ql-editor [data-block-id]")
    page.wait_for_timeout(160)

    before = page.evaluate(MEASURE_JS, {"anchorId": anchor_id, "insertedId": inserted_id})
    anchor_before = before["anchor"]

    shot_dir = os.environ.get("CUA_SWE_SCREENSHOT_DIR")
    if shot_dir:
        os.makedirs(shot_dir, exist_ok=True)
        page.screenshot(path=os.path.join(shot_dir, f"{session.get('space','x').replace(' ','_')}-before.png"))

    # Apply the pending collaborative paste as a person would.
    page.keyboard.press("Alt+p")
    page.wait_for_timeout(160)

    after = page.evaluate(MEASURE_JS, {"anchorId": anchor_id, "insertedId": inserted_id})
    if shot_dir:
        page.screenshot(path=os.path.join(shot_dir, f"{session.get('space','x').replace(' ','_')}-after.png"))

    region_h = after["regionHeight"]
    anchor_after = after["anchor"]
    inserted_after = after["inserted"]

    def is_visible(box):
        if box is None:
            return False
        return box["bottom"] > 4.0 and box["top"] < (region_h - 4.0)

    result = {
        "space": session.get("space"),
        "actor_kind": actor_kind,
        "actor_focus": actor_focus,
        "applied": after["applied"],
        "anchor_before_top": None if anchor_before is None else round(anchor_before["top"], 1),
        "anchor_after_top": None if anchor_after is None else round(anchor_after["top"], 1),
        "inserted_after_top": None if inserted_after is None else round(inserted_after["top"], 1),
        "region_height": region_h,
    }

    if not after["applied"]:
        result.update(passed=False, reason="paste not applied")
        return result

    # An update the reader is meant to see -- their own paste, or a paste from a
    # collaborator who is reading here with them -- must become visible. An
    # update from a collaborator working elsewhere must leave the reader's place
    # in the document undisturbed. The expectation is derived from the live
    # session (author kind + author focus), never copied from a table of scroll
    # offsets, and applied uniformly.
    surfacing = (actor_kind == "self") or (actor_kind == "peer" and actor_focus == "here")
    if surfacing:
        passed = is_visible(inserted_after)
        result["expectation"] = "surface_the_update"
        result["passed"] = bool(passed)
    elif actor_kind == "peer":
        # The reading anchor keeps both its visibility and its viewport position.
        anchor_held = (
            anchor_before is not None
            and anchor_after is not None
            and abs(anchor_after["top"] - anchor_before["top"]) <= 8.0
            and is_visible(anchor_after)
        )
        result["expectation"] = "hold_the_reading_place"
        result["passed"] = bool(anchor_held)
    else:
        result.update(passed=False, reason="unknown actor kind")
    return result


def main() -> int:
    checks = []
    services = []
    static_srv = None
    try:
        _build_bundle()
        launch_opts = {"headless": True}
        if exe := os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE"):
            launch_opts["executable_path"] = exe
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch_opts)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            seen = set()
            quill_gate = None
            for variant in VARIANTS:
                proc, sport = _start_service(variant)
                services.append(proc)
                static_srv, base = _static_server(sport)
                try:
                    if quill_gate is None:
                        # Framework gate: assert the real Quill runtime drives the
                        # surface before any behavioral judging.
                        quill_gate = _assert_quill_runtime(page, base)
                    res = _check_variant(page, base)
                finally:
                    static_srv.shutdown()
                    static_srv.server_close()
                    static_srv = None
                seen.add(res.get("space"))
                checks.append(res)
            browser.close()
        distinct_ok = len([w for w in seen if w]) == len(VARIANTS)
        actor_mix = {c["actor_kind"] for c in checks}
        mix_ok = {"self", "peer"}.issubset(actor_mix)
        # Require both peer focuses to be exercised so the author-plus-focus
        # contract is genuinely discriminated rather than collapsing to author.
        peer_focus_mix = {c["actor_focus"] for c in checks if c["actor_kind"] == "peer"}
        focus_mix_ok = {"here", "away"}.issubset(peer_focus_mix)
        quill_ok = bool(quill_gate and quill_gate.get("ok"))
        passed = (quill_ok and distinct_ok and mix_ok and focus_mix_ok
                  and all(c.get("passed") for c in checks))
        print(json.dumps({
            "passed": passed,
            "quill_runtime": quill_gate,
            "distinct_sessions": distinct_ok,
            "actor_mix": sorted(actor_mix),
            "peer_focus_mix": sorted(peer_focus_mix),
            "checks": checks,
        }, indent=2))
        return 0 if passed else 1
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
