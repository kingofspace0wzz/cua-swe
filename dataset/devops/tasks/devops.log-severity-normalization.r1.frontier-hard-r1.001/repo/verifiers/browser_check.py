#!/usr/bin/env python3
"""Independent protected event-semantics and live operator-view verification."""
from pathlib import Path
import json,os,socket,subprocess,time,sys,signal
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from playwright.sync_api import sync_playwright
from build_check import violations
HERE=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
ROOT=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
def port():
 # Explicit construction allocation; evaluation's contained network is isolated.
 start=int(os.environ.get('OWNER23_PORT_START','55320'))
 for number in range(start,min(start+16,55500)):
  with socket.socket() as s:
   s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
   try:s.bind(('127.0.0.1',number));return number
   except OSError:pass
 raise RuntimeError('runtime did not start: owner23 port allocation exhausted')
def request(origin,path,data=None):
 req=Request(origin+'/'+path,data=None if data is None else json.dumps(data).encode(),headers={'content-type':'application/json'})
 with urlopen(req,timeout=3) as r:return json.load(r)
def ready(origin):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  try:
   with urlopen(origin,timeout=1) as r:
    if r.status==200:return
  except (OSError,URLError):pass
  time.sleep(.05)
 raise RuntimeError('runtime did not start: '+origin)
def stop(procs):
 for p in reversed(procs):
  if p.poll() is None:p.terminate()
 for p in reversed(procs):
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)
def start(profile):
 procs=[]
 try:
  sp=port();service='http://127.0.0.1:'+str(sp)
  procs.append(subprocess.Popen(['node',str(HERE/'log_service.mjs'),'--port',str(sp),'--profile',profile],cwd=HERE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL));ready(service+'/health')
  ap=port();app='http://127.0.0.1:'+str(ap)
  procs.append(subprocess.Popen(['node','server.mjs','--port',str(ap)],cwd=ROOT,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':service},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL));ready(app)
  return procs,app,service
 except Exception:stop(procs);raise
def run():
 checks=[];failed=[];coverage=[];infra=False
 def check(value,label):
  checks.append(label)
  if not value:failed.append(label)
 bad=violations()
 if bad:return {'passed':False,'infrastructure_error':False,'checks':['protected entrypoints and source symlinks'],'failed_checks':['integrity: '+', '.join(bad)],'coverage':[]}
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   try:
    for profile in ['visible','hidden','hidden-range']:
     procs,app,service=start(profile)
     try:
      page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(3000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      response=page.goto(app,wait_until='domcontentloaded');check(response.status==200,profile+': actual task HTTP 200')
      page.locator('#app[data-ready="yes"]').wait_for();opening=request(service,'audit')
      def click(selector):
       page.locator(selector).click();page.locator('#app[data-ready="yes"]').wait_for()
      def inspect(label):
       a=request(service,'audit');snap=a['snapshot'];prefix=profile+': '+label;expected={x['raw']['recordId']:x for x in a['expected']};actual={x.get('raw',{}).get('recordId'):x for x in a['actual']}
       check(a['actual']==a['expected'],prefix+' independent event semantics and complete original records')
       check(set(actual)==set(expected) and len(a['actual'])==len(a['expected']),prefix+' every original record exactly once')
       check(sorted(snap['accepted'])==sorted(b['deliveryId'] for b in snap['batches']),prefix+' every delivery accepted once')
       for record_id,x in expected.items():
        y=actual.get(record_id,{})
        check(y.get('severity')==x['severity'],prefix+' '+record_id+' normalized severity preserves numeric rank')
        check(y.get('raw')==x['raw'],prefix+' '+record_id+' raw telemetry and correlation unchanged')
        check(y.get('receiverId')==x['receiverId'] and y.get('deliveryId')==x['deliveryId'],prefix+' '+record_id+' receiver delivery identity')
       check(page.locator('[data-scenario]').count()==3,prefix+' replay sessions preserved')
       check(page.locator('[data-action="retry"]').count()==1 and page.locator('[data-action="reset"]').count()==1,prefix+' lifecycle controls preserved')
       check(page.locator('[data-test="delivery"]').inner_text()==str(len(snap['accepted']))+' / '+str(snap['retries']),prefix+' actual delivery counters')
       click('[data-tab="inventory"]')
       inventory=page.locator('[data-test="inventory"] tr').evaluate_all('(rs)=>rs.map(r=>Array.from(r.querySelectorAll("td")).map(c=>c.textContent))')
       check(inventory==[[r['name']+r['id'],r['source']['format'],r['output']['format'],r['resource']['service.name'],r['pipeline']] for r in snap['receivers']],prefix+' deployed receiver inventory visible')
       click('[data-tab="logs"]')
       check(page.locator('[data-test="receiver"] option').count()==len(snap['receivers']),prefix+' receiver selection preserved')
       for receiver in snap['receivers']:
        page.locator('[data-test="receiver"]').select_option(receiver['id'])
        page.wait_for_function('(v)=>document.querySelector("[data-test=receiver]").value===v',arg=receiver['id'])
        for mode in ['all','severe']:
         page.locator('[data-test="filter"]').select_option(mode)
         page.wait_for_function('(v)=>document.querySelector("[data-test=filter]").value===v',arg=mode)
         want=[x for b in snap['batches'] if b['receiverId']==receiver['id'] for raw in b['records'] for x in [expected[raw['recordId']]] if mode=='all' or x['severity']['band'] in ['ERROR','FATAL']]
         # Wait for view redraw, then read actual text, not application data attributes.
         page.wait_for_timeout(15)
         shown=page.locator('[data-test="records"] tr').evaluate_all('(rs)=>rs.map(r=>[r.querySelector("button").dataset.record,r.querySelector(".badge").textContent,r.querySelector("td small").textContent])')
         check(shown==[[x['raw']['recordId'],x['severity']['band'],str(x['severity']['number'])] for x in want],prefix+' '+receiver['id']+' '+mode+' actual displayed membership severity and rank')
         check(page.locator('[data-test="counts"]').inner_text()==str(len(want))+' shown / '+str(len([x for x in expected.values() if x['receiverId']==receiver['id']]))+' received',prefix+' '+receiver['id']+' '+mode+' visible counts')
         if mode=='all':
          # Every detail remains accessible, including trace/span and timestamps.
          for x in want:
           loc=page.locator('[data-record="'+x['raw']['recordId']+'"]')
           if loc.count()!=1:check(False,prefix+' missing record detail '+x['raw']['recordId']);continue
           loc.click();page.locator('#app[data-ready="yes"]').wait_for()
           raw=x['raw'];check(json.loads(page.locator('[data-test="raw-body"]').inner_text())==raw['body'],prefix+' '+raw['recordId']+' visible raw body')
           check(page.locator('[data-test="raw-number"]').inner_text()==str(raw.get('severityNumber','—')),prefix+' '+raw['recordId']+' raw numeric severity')
           check(page.locator('[data-test="raw-text"]').inner_text()==str(raw.get('severityText','—')),prefix+' '+raw['recordId']+' raw severity text')
           check(page.locator('[data-test="timestamp"]').inner_text()==raw['timeUnixNano'] and page.locator('[data-test="correlation"]').inner_text()==raw['traceId']+' / '+raw['spanId'],prefix+' '+raw['recordId']+' visible correlation')
           check(page.locator('[data-test="delivery-id"]').inner_text()==x['deliveryId'] and page.locator('[data-test="resource"]').inner_text()==receiver['resource']['service.name'],prefix+' '+raw['recordId']+' visible delivery and resource')
       coverage.append({'profile':profile,'state':label,'actual':a['actual'],'expected':a['expected'],'accepted':snap['accepted'],'retries':snap['retries']})
       return a
      for index,scenario in enumerate(['incident','healthy','recovery']):
       if index:click('[data-scenario="'+scenario+'"]')
       first=inspect(scenario)
       # Retry twice; semantic/UI full inspection once avoids multiplying routine work.
       for repetition in range(2):
        click('[data-action="retry"]');after=request(service,'audit')
        check(after['actual']==first['actual'],profile+': '+scenario+' retry '+str(repetition)+' idempotent')
        check(after['snapshot']['retries']==repetition+1,profile+': '+scenario+' retry counter')
      click('[data-action="reset"]');reset=inspect('reset');check(reset['actual']==opening['actual'],profile+': deterministic reset')
      page.reload(wait_until='domcontentloaded');page.locator('#app[data-ready="yes"]').wait_for();reload=request(service,'audit')
      check(reload['actual']==opening['actual'],profile+': reload preserves reconstructed records')
      for path in ['api/audit','api/reset','verifiers/browser_check.py','gold.patch','env/service.mjs','task.yaml','src/../verifiers/profiles.json']:
       try:
        with urlopen(app+'/'+path,timeout=2) as r:status=r.status
       except HTTPError as e:status=e.code
       check(status==404,profile+': protected HTTP denied '+path)
      check(not errors,profile+': no page errors');check(page.locator('#app').get_attribute('data-error') is None,profile+': no action failures');page.close()
     finally:stop(procs)
   finally:browser.close()
 except Exception as e:
  if isinstance(e,RuntimeError) and 'runtime did not start' in str(e):infra=True
  failed.append(type(e).__name__+': '+str(e))
 return {'passed':not failed,'infrastructure_error':infra,'checks':checks,'failed_checks':failed,'coverage':coverage}
if __name__=='__main__':
 signal.signal(signal.SIGALRM,lambda *args: (_ for _ in ()).throw(TimeoutError('native verifier exceeded 110 seconds')));signal.alarm(110)
 result=run();signal.alarm(0);print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
