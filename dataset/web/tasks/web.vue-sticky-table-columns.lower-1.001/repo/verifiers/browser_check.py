import os,subprocess,time
from playwright.sync_api import sync_playwright
from runtime_support import wait_for_service

SERVICE_PORT = os.environ.get("CUA_SWE_CONTRACT_SERVICE_PORT", "4331")
def check(variant,expected):
 p=subprocess.Popen(['node','verifiers/contract_service.mjs','--host','127.0.0.1','--port',SERVICE_PORT],env={**os.environ,'CONTRACT_VARIANT':variant})
 try:
  wait_for_service(p, SERVICE_PORT)
  with sync_playwright() as pw:
   b=pw.chromium.launch(headless=True);page=b.new_page();page.goto('http://127.0.0.1:4201');page.get_by_test_id('table-shell').evaluate('(e)=>e.scrollLeft=260');left=page.locator('tbody .name').first.evaluate('(e)=>getComputedStyle(e).left');assert left==f'{expected}px',(variant,left);b.close()
 finally:p.terminate();p.wait()
check('a',44);print('active compact sticky geometry verified')
