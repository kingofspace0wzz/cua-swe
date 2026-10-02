import os, subprocess, time
from playwright.sync_api import sync_playwright
from runtime_support import wait_for_service

SERVICE_PORT = os.environ.get("CUA_SWE_CONTRACT_SERVICE_PORT", "4311")

def check(variant, expected):
    env={**os.environ,'CONTRACT_VARIANT':variant}
    service=subprocess.Popen(['node','verifiers/contract_service.mjs','--host','127.0.0.1','--port',SERVICE_PORT],env=env)
    try:
        wait_for_service(service, SERVICE_PORT)
        with sync_playwright() as p:
            page=p.chromium.launch(headless=True).new_page(viewport={'width':1280,'height':720})
            page.goto('http://127.0.0.1:4173'); page.get_by_role('button',name='Export').click(); page.get_by_text('Workspace export guide').click(); page.get_by_role('button',name='Preview export').click()
            page.get_by_text(expected).wait_for(timeout=3000)
    finally: service.terminate(); service.wait(timeout=3)

check('a','3 products ready')
check('b','5 products ready')
print('current-search export contract verified')
