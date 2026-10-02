from __future__ import annotations
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,mimetypes,os
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs,urlparse
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;PAYLOADS=json.loads((ROOT/"contract_payloads.json").read_text())
def embedded():
    workspace=Path(os.environ.get("CUA_SWE_WORKSPACE")or ROOT.parent).resolve()
    class H(BaseHTTPRequestHandler):
        def log_message(self,*_):return
        def do_GET(self):
            p=urlparse(self.path)
            if p.path=="/api/delegated-action":
                key="secondary" if parse_qs(p.query).get("scenario",[""])[0]=="secondary" else "primary";body=json.dumps(PAYLOADS[key]).encode();self.send_response(200);self.send_header("content-type","application/json");self.send_header("content-length",str(len(body)));self.end_headers();self.wfile.write(body);return
            target=(workspace/("index.html" if p.path=="/" else p.path.lstrip("/"))).resolve()
            if not target.is_relative_to(workspace)or not target.is_file():self.send_error(404);return
            body=target.read_bytes();self.send_response(200);self.send_header("content-type",mimetypes.guess_type(target.name)[0]or"text/plain");self.send_header("content-length",str(len(body)));self.end_headers();self.wfile.write(body)
    s=ThreadingHTTPServer(("127.0.0.1",0),H);Thread(target=s.serve_forever,daemon=True).start();return s,f"http://127.0.0.1:{s.server_port}"
def main():
    server=None;url=os.environ.get("CUA_SWE_WEB_URL")
    if not url:server,url=embedded()
    checks=[]
    try:
        with sync_playwright()as p:
            opts={"headless":True}
            if exe:=os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE"):opts["executable_path"]=exe
            b=p.chromium.launch(**opts);page=b.new_page(viewport={"width":1280,"height":720})
            for query,request,expected in [("","REQ-581","Approve with note"),("?scenario=secondary","REQ-944","Reject on behalf")]:
                page.goto(f"{url}/{query}");page.wait_for_selector("#delegated-action");actual=page.text_content("#delegated-action").strip();page.click("#trace-toggle");details=page.locator("#trace");text=details.text_content()or"";preserved=all(x in text for x in("selected_assignment_ref","assignment_ref","role_ref","grant_refs","grant_precedence","grant_ref","required_condition_refs","ui_mode","display_label","active_condition_refs","allowed_modes"));passed=actual==expected and request in page.text_content("h1")and details.is_visible()and preserved;checks.append({"scenario":request,"action":actual,"trace_preserved":preserved,"passed":passed})
            b.close()
    finally:
        if server:server.shutdown();server.server_close()
    passed=all(x["passed"]for x in checks);print(json.dumps({"passed":passed,"checks":checks},indent=2));return 0 if passed else 1
if __name__=="__main__":raise SystemExit(main())
