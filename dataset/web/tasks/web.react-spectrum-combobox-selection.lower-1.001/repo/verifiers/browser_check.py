import os,subprocess,time
from playwright.sync_api import sync_playwright
from runtime_support import wait_for_service

SERVICE_PORT = os.environ.get("CUA_SWE_CONTRACT_SERVICE_PORT", "4321")
def check(variant,key,count):
 p=subprocess.Popen(['node','verifiers/contract_service.mjs','--host','127.0.0.1','--port',SERVICE_PORT],env={**os.environ,'CONTRACT_VARIANT':variant})
 try:
  wait_for_service(p, SERVICE_PORT)
  with sync_playwright() as pw:
   b=pw.chromium.launch(headless=True);page=b.new_page();page.goto('http://127.0.0.1:4181');page.wait_for_function("()=>document.querySelector('details')?.textContent.includes('Enter')");page.get_by_placeholder('Type a region or custom value').fill('Denmark');page.get_by_placeholder('Type a region or custom value').press(key);page.get_by_test_id('selection-count').get_by_text(f'{count} selected').wait_for();b.close()
 finally:p.terminate();p.wait()
check('a','Enter',3);check('b','Enter',2);print('single-key workspace policy verified')
