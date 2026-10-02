from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, mimetypes, os
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PAYLOADS = json.loads((ROOT / "contract_payloads.json").read_text())

def embedded():
    workspace = Path(os.environ.get("CUA_SWE_WORKSPACE") or ROOT.parent).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): return
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/support-window":
                key = "secondary" if parse_qs(parsed.query).get("scenario", [""])[0] == "secondary" else "primary"
                body = json.dumps(PAYLOADS[key]).encode(); self.send_response(200)
                self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            target = (workspace / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))).resolve()
            if not target.is_relative_to(workspace) or not target.is_file(): self.send_error(404); return
            body = target.read_bytes(); self.send_response(200); self.send_header("content-type", mimetypes.guess_type(target.name)[0] or "text/plain"); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"

def main():
    server = None; url = os.environ.get("CUA_SWE_WEB_URL")
    if not url: server, url = embedded()
    checks = []
    try:
        with sync_playwright() as p:
            opts = {"headless": True}
            if executable := os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE"): opts["executable_path"] = executable
            browser = p.chromium.launch(**opts); page = browser.new_page(viewport={"width": 1280, "height": 720})
            cases = [
                ("", "SUP-410", "Oct 8, 2026, 5:00 AM (America/Chicago)"),
                ("?scenario=secondary", "SUP-944", "Jan 8, 2027, 8:30 AM (Europe/Berlin)"),
            ]
            for query, case_ref, expected in cases:
                page.goto(f"{url}/{query}"); page.wait_for_selector("#support-window")
                actual = page.text_content("#support-window").strip(); page.click("#details-tab")
                details = page.locator("#details"); text = details.text_content() or ""
                preserved = all(x in text for x in ("week_anchor_epoch_ms", "selected_slot_ref", "day_code_map", "start_quanta", "quantum_minutes", "display_zone"))
                passed = actual == expected and case_ref in page.text_content("h1") and details.is_visible() and preserved
                checks.append({"scenario": case_ref, "window": actual, "details_visible": details.is_visible(), "details_preserved": preserved, "passed": passed})
            browser.close()
    finally:
        if server: server.shutdown(); server.server_close()
    passed = all(x["passed"] for x in checks); print(json.dumps({"passed": passed, "checks": checks}, indent=2)); return 0 if passed else 1

if __name__ == "__main__": raise SystemExit(main())

