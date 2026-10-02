#!/usr/bin/env python3
"""Behavioral verifier for the Draft Composer keyboard-focus resume fixture.

The composer is a real Tiptap/ProseMirror editor; the decisive resume geometry
lives only in the harness-owned service (env/service.mjs) and is never copied
into this file or the product source. Each protected workspace payload carries
several same-shape pixel anchors; exactly one still lands on a rendered glyph
line while the others were captured under an earlier layout and now fall into
the blank region between wrapped paragraphs. For each payload the verifier
renders the composer, returns focus with the keyboard (Tab then Alt+R), reads
the caret line box back from the live Tiptap layout, independently derives the
authoritative anchor and its visual line from the running ProseMirror layout,
and requires the resumed caret to land on that same line and column -- never at
document start. It also proves the Tiptap runtime actually loaded and was used.

No expected document position or pixel constant is embedded here; the target is
recomputed live from whatever the running Tiptap editor renders, including which
saved anchor is the authoritative on-line one.
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

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
ENV_SERVICE = (WORKSPACE.parent / "env" / "service.mjs").resolve()

VARIANTS = ["a", "b", "c"]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(port, timeout=10.0):
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
    raise RuntimeError(f"harness service did not start on {port}: {last}")


def _start_service(variant):
    port = _free_port()
    env = dict(os.environ)
    env["CONTRACT_VARIANT"] = variant
    proc = subprocess.Popen(
        ["node", str(ENV_SERVICE), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    _wait_health(port)
    return proc, port


def _static_server(upstream_port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_GET(self):
            p = urlparse(self.path)
            if p.path.startswith("/api/"):
                url = f"http://127.0.0.1:{upstream_port}{self.path}"
                try:
                    with urllib.request.urlopen(url, timeout=3) as r:
                        body = r.read()
                        ctype = r.headers.get("content-type", "application/json")
                except Exception:
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


ANCHOR_LINE_JS = r"""
(anchors) => {
  const surface = document.getElementById("surface");
  const editor = surface.__editor;
  if (!editor) return { lineTop: null, anchorLeft: null, authoritativeCount: 0 };
  const view = editor.view;
  const rootRect = view.dom.getBoundingClientRect();
  const size = view.state.doc.content.size;

  // Independently derive which saved anchor is the authoritative on-line one:
  // posAtCoords always snaps to a position, but only a point that actually
  // falls on a rendered glyph line has a resolved box that vertically contains
  // it. A carried-over anchor from an earlier layout snaps to an off-line
  // paragraph boundary in the blank gap and fails this containment.
  const onLine = [];
  for (const anchor of anchors) {
    const targetY = rootRect.top + anchor.y;
    const targetX = rootRect.left + anchor.x;
    const hit = view.posAtCoords({ left: targetX, top: targetY });
    if (!hit) continue;
    let box;
    try { box = view.coordsAtPos(hit.pos); } catch (e) { continue; }
    if (targetY >= box.top && targetY <= box.bottom) {
      onLine.push(anchor);
    }
  }
  if (onLine.length !== 1) {
    return { lineTop: null, anchorLeft: null, authoritativeCount: onLine.length };
  }
  const anchor = onLine[0];
  const targetY = rootRect.top + anchor.y;
  const targetX = rootRect.left + anchor.x;
  let bestTop = null, bestDy = Infinity, bestLeft = null, bestColDx = Infinity;
  for (let pos = 1; pos <= size; pos++) {
    let c;
    try { c = view.coordsAtPos(pos); } catch (e) { continue; }
    const cy = (c.top + c.bottom) / 2;
    const dy = Math.abs(cy - targetY);
    if (dy < bestDy) { bestDy = dy; bestTop = c.top - rootRect.top; }
    if (dy < 12) {
      const dx = Math.abs(c.left - targetX);
      if (dx < bestColDx) { bestColDx = dx; bestLeft = c.left - rootRect.left; }
    }
  }
  return { lineTop: bestTop, anchorLeft: bestLeft, authoritativeCount: 1 };
}
"""

READ_CARET_JS = r"""
() => {
  const surface = document.getElementById("surface");
  const editor = surface.__editor;
  const pmRoot = editor ? editor.view.dom : null;
  const active = pmRoot !== null && document.activeElement === pmRoot;
  return {
    active,
    caretPos: Number(surface.dataset.caretPos),
    caretTop: Number(surface.dataset.caretTop),
    caretLeft: Number(surface.dataset.caretLeft),
  };
}
"""

# Prove the decisive runtime path actually loaded and used Tiptap/ProseMirror.
IMPORT_EVIDENCE_JS = r"""
() => {
  const surface = document.getElementById("surface");
  const editor = surface && surface.__editor;
  const view = editor && editor.view;
  return {
    hasEditor: !!editor,
    isTiptapEditor: !!(editor && editor.constructor && editor.constructor.name === "Editor"),
    hasProseMirrorView: !!(view && typeof view.posAtCoords === "function" && typeof view.coordsAtPos === "function"),
    hasProseMirrorDom: !!(view && view.dom && view.dom.classList.contains("ProseMirror")),
    hasProseMirrorState: !!(view && view.state && typeof view.state.doc.content.size === "number"),
  };
}
"""


def _fetch_anchors(base):
    with urllib.request.urlopen(f"{base}/api/resume-bookmark", timeout=3) as r:
        payload = json.loads(r.read())
    bm = payload["bookmark"]
    if isinstance(bm.get("anchors"), list):
        return [a for a in bm["anchors"] if isinstance(a, dict)]
    if isinstance(bm.get("anchor"), dict):
        return [bm["anchor"]]
    return []


def _fetch_workspace(base):
    with urllib.request.urlopen(f"{base}/api/resume-bookmark", timeout=3) as r:
        return json.loads(r.read()).get("workspace", "")


def _build_bundle():
    # Rebuild the browser bundle from source so the patched src/ is the code
    # actually exercised. This also re-imports the real Tiptap runtime.
    proc = subprocess.run(
        ["node", str(WORKSPACE / "build.mjs")],
        cwd=str(WORKSPACE), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("bundle build failed: " + (proc.stderr or proc.stdout))


def _check_variant(page, base):
    page.goto(base)
    page.wait_for_selector(".ProseMirror p")
    page.wait_for_timeout(120)
    # Runtime dependency gate: the real Tiptap/ProseMirror editor must be live.
    evidence = page.evaluate(IMPORT_EVIDENCE_JS)
    import_ok = all(evidence.values())
    anchors = _fetch_anchors(base)
    # Independently derive the authoritative anchor and its visual line from the
    # live ProseMirror layout. Exactly one saved anchor must land on a rendered
    # glyph line; anything else means the payload no longer discriminates.
    line = page.evaluate(ANCHOR_LINE_JS, anchors)
    # Return focus with the keyboard exactly as a person would.
    page.keyboard.press("Tab")
    page.wait_for_timeout(40)
    page.keyboard.press("Alt+r")
    page.wait_for_timeout(140)
    caret = page.evaluate(READ_CARET_JS)
    if line["lineTop"] is None:
        return {"passed": False,
                "reason": "authoritative anchor line unresolved",
                "authoritative_count": line.get("authoritativeCount"),
                "import_ok": import_ok, "evidence": evidence}
    line_top = line["lineTop"]
    anchor_left = line["anchorLeft"]
    on_anchor_line = abs(caret["caretTop"] - line_top) <= 6.0
    near_anchor_col = anchor_left is not None and abs(caret["caretLeft"] - anchor_left) <= 24.0
    not_doc_start = caret["caretPos"] > 1 and not (caret["caretTop"] <= 6.0 and caret["caretLeft"] <= 6.0)
    passed = bool(import_ok and caret["active"] and on_anchor_line and near_anchor_col and not_doc_start)
    return {
        "workspace": _fetch_workspace(base),
        "import_ok": import_ok,
        "evidence": evidence,
        "caret_pos": caret["caretPos"],
        "caret_top": round(caret["caretTop"], 1),
        "caret_left": round(caret["caretLeft"], 1),
        "anchor_line_top": round(line_top, 1),
        "anchor_left": None if anchor_left is None else round(anchor_left, 1),
        "on_anchor_line": on_anchor_line,
        "near_anchor_col": near_anchor_col,
        "not_doc_start": not_doc_start,
        "passed": passed,
    }


def main():
    _build_bundle()
    checks = []
    services = []
    static_srv = None
    try:
        launch_opts = {"headless": True}
        exe = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
        if exe:
            launch_opts["executable_path"] = exe
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch_opts)
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
        import_ok = all(c.get("import_ok") for c in checks)
        passed = distinct_ok and import_ok and all(c.get("passed") for c in checks)
        print(json.dumps({"passed": passed, "distinct_workspaces": distinct_ok,
                          "tiptap_runtime_import_ok": import_ok,
                          "checks": checks}, indent=2))
        return 0 if passed else 1
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
