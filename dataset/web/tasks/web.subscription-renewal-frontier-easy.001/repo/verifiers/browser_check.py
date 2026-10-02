from __future__ import annotations
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,mimetypes,os
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs,urlparse
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;PAYLOADS=json.loads((ROOT/"contract_payloads.json").read_text())
def embedded():
    workspace=Path(os.environ.get("CUA_SWE_WORKSPACE") or ROOT.parent).resolve()
    class H(BaseHTTPRequestHandler):
        def log_message(self,*_):return
        def do_GET(self):
            p=urlparse(self.path)
            if p.path=="/api/subscription-cycle":
                key="secondary" if parse_qs(p.query).get("scenario",[""])[0]=="secondary" else "primary";body=json.dumps(PAYLOADS[key]).encode();self.send_response(200);self.send_header("content-type","application/json");self.send_header("content-length",str(len(body)));self.end_headers();self.wfile.write(body);return
            target=(workspace/("index.html" if p.path=="/" else p.path.lstrip("/"))).resolve()
            if not target.is_relative_to(workspace) or not target.is_file():self.send_error(404);return
            body=target.read_bytes();self.send_response(200);self.send_header("content-type",mimetypes.guess_type(target.name)[0] or "text/plain");self.send_header("content-length",str(len(body)));self.end_headers();self.wfile.write(body)
    s=ThreadingHTTPServer(("127.0.0.1",0),H);Thread(target=s.serve_forever,daemon=True).start();return s,f"http://127.0.0.1:{s.server_port}"
def main():
    server=None;url=os.environ.get("CUA_SWE_WEB_URL")
    if not url:server,url=embedded()
    checks=[]
    try:
        with sync_playwright() as p:
            opts={"headless":True}
            if exe:=os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE"):opts["executable_path"]=exe
            b=p.chromium.launch(**opts);page=b.new_page(viewport={"width":1280,"height":720})
            for query,entity,expected in [('', 'SUB-731', 'Renews 2026-01-29 10:00'), ('?scenario=secondary', 'SUB-118', 'Next cycle 2026-06-11 09:00')]:
                page.goto(f"{url}/{query}");page.wait_for_selector('#renewal-value');actual=page.text_content('#renewal-value').strip();page.click('#calculation-toggle');details=page.locator('#calculation');text=details.text_content() or "";preserved=all(x in text for x in ('anchor_epoch_ms', 'anchor_application', 'interval_quanta', 'quantum_days', 'grace_quanta', 'grace_application', 'display_zone', 'value_format', 'display_pattern'));passed=actual==expected and entity in page.text_content("h1") and details.is_visible() and preserved;checks.append({"scenario":entity,"actual":actual,'calculation_preserved':preserved,"passed":passed})
            b.close()
    finally:
        if server:server.shutdown();server.server_close()
    passed=all(x["passed"] for x in checks);print(json.dumps({"passed":passed,"checks":checks},indent=2));return 0 if passed else 1
if __name__=="__main__":raise SystemExit(main())
