#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
EXPECTED_DELAY_MS=2100
UNKNOWN="⬜"; EXPLODED="💥"
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): return
    def send_json(self,status,payload):
        body=json.dumps(payload,separators=(",",":")).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.send_json(200,{"ready":True}) if self.path=="/health" else self.send_json(404,{"error":"not_found"})
    def do_POST(self):
        if self.path!="/check": return self.send_json(404,{"error":"not_found"})
        try:
            length=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(length)); board=payload.get("board") or []; engine=payload.get("engine_state")
            cells=[cell for row in board if isinstance(row,list) for cell in row]
            all_unknown=bool(cells) and all(cell==UNKNOWN for cell in cells)
            exploded=EXPLODED in cells
            verdict="live"
            if all_unknown and engine=="lost": verdict="stale"
            elif exploded and engine=="started": verdict="pending"
            elif engine=="lost": verdict="committed"
            elif all_unknown and engine=="not_started": verdict="fresh"
            self.send_json(200,{"available":True,"verdict":verdict,"expected_delay_ms":EXPECTED_DELAY_MS})
        except Exception:
            self.send_json(400,{"available":False,"verdict":"unknown","expected_delay_ms":EXPECTED_DELAY_MS})
def main():
    p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,required=True); a=p.parse_args(); ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=="__main__": main()
