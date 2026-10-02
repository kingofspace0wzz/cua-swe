from pathlib import Path
import json,os,socket,subprocess,time,traceback
from urllib.request import urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
from build_check import violations
from oracle import expected, route_key
from acceptance import row_matches, history_matches, annotation_errors, rendered_annotations_match
V=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
W=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
PROFILES=json.loads((V/'profiles.json').read_text())

def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def fetch(url):
 with urlopen(url,timeout=3) as r:return json.load(r)
def wait(url,process):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  if process.poll() is not None:raise RuntimeError('own runtime child exited')
  try:
   with urlopen(url,timeout=1) as r:
    if r.status==200:return
  except OSError:pass
  time.sleep(.05)
 raise RuntimeError('runtime not ready')
def clock(t):return f'{t//60}:{t%60:02}'
def main():
 checks=[];failed=[];infra=False;details=[]
 def ck(ok,label):
  checks.append(label)
  if not ok:failed.append(label)
 bad=violations()
 if bad:
  print(json.dumps({'passed':False,'infrastructure_error':False,'checks':['integrity before candidate execution'],'failed_checks':bad}));return 1
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   try:
    for key,pf in PROFILES.items():
     processes=[];sp,ap=port(),port();su=f'http://127.0.0.1:{sp}';au=f'http://127.0.0.1:{ap}'
     try:
      svc=subprocess.Popen(['node',str(V/'service.mjs'),'--port',str(sp),'--profile',key],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(svc);wait(su+'/health',svc)
      app=subprocess.Popen(['node','server.mjs','--port',str(ap)],cwd=W,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':su},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(app);wait(au,app)
      page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(1600);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      response=page.goto(au);ck(response.status==200,key+' HTTP200');page.locator('#app[data-ready=yes]').wait_for()
      def click(selector):page.locator(selector).click();page.wait_for_timeout(35)
      def inspect(label):
       audit=fetch(su+'/audit');scenario=next(s for s in pf['scenarios'] if s['id']==audit['scenario']);want=expected(pf,scenario,audit['cursor']);snap=audit['snapshot'];rows=want[audit['target']][-7:]
       selector_pairs=page.locator('[data-test=receiver-selector-pair]').evaluate_all('(rows)=>rows.map(r=>[r.querySelector("[data-test=selector-key]").innerText,r.querySelector("[data-test=selector-value]").innerText])')
       selector_expected=pf['receivers'][0]['match']
       ck(snap['delivery'].get('match')==selector_expected and page.locator('[data-test=receiver-selector]').count()==1 and len(dict(selector_pairs))==len(selector_pairs) and dict(selector_pairs)==selector_expected,key+'/'+label+' actual receiver selector mapping')
       core_rule=pf['rules'][0]
       ck(all(snap['rule'].get(k)==core_rule[k] for k in ('name','query','forSeconds')),key+'/'+label+' exact rule query and hold')
       ck(set(audit['history'])==set(want) and all(isinstance(audit['history'].get(k),list) and len(audit['history'][k])==len(v) for k,v in want.items()),key+'/'+label+' exact history identities and lengths')
       for target,history in want.items():
        actual=audit['history'].get(target,[])
        for i,row in enumerate(history):
         ck(i<len(actual) and row_matches(actual[i],row),f'{key}/{label}/{target}/{i} independent semantics')
       rendered=page.locator('[data-test=timeline] tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.innerText))')
       display=[[clock(x['t']),str(x['condition']).lower(),x['state'],'—' if x['activeAt'] is None else clock(x['activeAt']),x['fingerprint'] or '—'] for x in rows]
       ck(rendered==display,key+'/'+label+' timeline pixels data')
       firing=sum(h[-1]['state']=='firing' for h in want.values())
       ck(page.locator('[data-test=firing]').inner_text()==f'firing {firing}' and page.locator('[data-test=delivered]').inner_text()==f'delivered {firing}' and page.locator('[data-test=unrouted]').inner_text()=='unrouted 0',key+'/'+label+' correct receiver delivery')
       expected_journal=[]
       for target_row in scenario['targets']:
        actual_last=audit['history'][target_row['id']][-1]
        rk=route_key(pf,target_row)
        alert_key=actual_last.get('fingerprint') if actual_last.get('condition') else None
        expected_journal.append({'target':target_row['id'],'state':actual_last.get('state'),'alert':alert_key,'route':rk,'status':('aligned' if alert_key==rk else 'divergent') if actual_last.get('condition') else 'idle'})
       ck(snap['delivery'].get('journal')==expected_journal,key+'/'+label+' journal reflects runtime identities')
       ck(all(audit['history'][target_row['id']][-1].get('fingerprint')==route_key(pf,target_row) for target_row in scenario['targets'] if want[target_row['id']][-1]['condition']),key+'/'+label+' alert identity correlates with receiver route identity')
       rendered_journal=page.locator('[data-test=journal] tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.innerText))')
       journal_display=[[e['target'],e['state'],e['alert'] or '\u2014',e['route'],e['status']] for e in expected_journal]
       ck(rendered_journal==journal_display,key+'/'+label+' journal pixels data')
       ck(('route '+pf['receivers'][0]['name']) in page.locator('.tabs span').inner_text(),key+'/'+label+' route name visible')
       ck(page.locator('[data-action=scenario]').count()==len(pf['scenarios']) and page.locator('[data-action=target]').count()==len(scenario['targets']),key+'/'+label+' inventories')
       if page.locator('[data-test=labels]').count():
        prev,cur=rows[-2]['labels'],rows[-1]['labels'];keys=sorted(set(prev)|set(cur))
        actual=page.locator('[data-test=labels] tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.innerText))')
        ck(actual==[[k,prev.get(k,'—'),cur.get(k,'—')] for k in keys],key+'/'+label+' label diff')
        actual=page.locator('[data-test=annotations] .pair').evaluate_all('(rows)=>rows.map(r=>[r.querySelector("b").innerText,r.querySelector("span").innerText])')
        protected_actual=audit['history'][audit['target']][-1]
        ck(rendered_annotations_match(actual,protected_actual,rows[-1]),key+'/'+label+' annotation detail matches validated actual')
       details.append({'profile':key,'state':label,'history_matches':history_matches(audit['history'],want),'cursor':audit['cursor'],'state_name':rows[-1]['state'],'required_annotations':rows[-1]['annotations'],'actual_annotations':audit['history'][audit['target']][-1]['annotations'],'journal':snap['delivery'].get('journal')})
       return audit
      first=inspect('opening')['snapshot']
      selector_cases=[{}, {'rotation':'secondary'}, {'team':'platform & response','cluster':'west<2>'}, {'route_key':'value with spaces','unicode':'équipe'}]
      for selector_index,selector in enumerate(selector_cases):
       rendered_selector=page.evaluate("""async ({snapshot,selector})=>{const {deliveryPanel}=await import('/src/views/delivery.js');const root=document.createElement('div');root.innerHTML=deliveryPanel({...snapshot,delivery:{...snapshot.delivery,match:selector}});return {panels:root.querySelectorAll('[data-test=receiver-selector]').length,pairs:Array.from(root.querySelectorAll('[data-test=receiver-selector-pair]'),r=>[r.querySelector('[data-test=selector-key]')?.textContent,r.querySelector('[data-test=selector-value]')?.textContent])};}""",{'snapshot':first,'selector':selector})
       ck(rendered_selector['panels']==1 and len(dict(rendered_selector['pairs']))==len(rendered_selector['pairs']) and dict(rendered_selector['pairs'])==selector,key+'/selector-renderer-'+str(selector_index)+' generic escaped selector mapping')
      click('[data-action=view][data-value=labels]');inspect('identity-detail')
      for scenario in pf['scenarios']:
       click(f'[data-action=scenario][data-value="{scenario["id"]}"]');inspect(scenario['id'])
       click('[data-action=target][data-value=two]');inspect(scenario['id']+'-second')
       click('[data-action=target][data-value=one]')
       for n in range(8):click('[data-action=advance]');inspect(scenario['id']+'-advance-'+str(n))
       click('[data-action=replay]');one=inspect(scenario['id']+'-replay')['snapshot'];click('[data-action=replay]');ck(fetch(su+'/snapshot')==one,key+' repeated replay')
      click('[data-action=reset]');ck(inspect('reset')['snapshot']==first,key+' reset deterministic')
      before=page.evaluate('performance.timeOrigin');page.reload();page.locator('#app[data-ready=yes]').wait_for();ck(page.evaluate('performance.timeOrigin')!=before,key+' actual reload');ck(inspect('reload')['snapshot']==first,key+' reload deterministic')
      for endpoint in ['/api/audit','/env/service.mjs','/verifiers/profiles.json','/gold.patch','/task.yaml']:
       try:
        with urlopen(au+endpoint,timeout=2) as r:status=r.status
       except HTTPError as e:status=e.code
       ck(status==404,key+' hidden HTTP denied '+endpoint)
      ck(not errors,key+' no JS errors');page.close()
     finally:
      for p in reversed(processes):
       if p.poll() is None:p.terminate()
       try:p.wait(timeout=3)
       except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
      for n in (ap,sp):
       with socket.socket() as sock:ck(sock.connect_ex(('127.0.0.1',n))!=0,key+' own child port closed')
   finally:browser.close()
 except HTTPError as error:
  infra=error.code!=500;failed.append('runtime rejected candidate rule: '+str(error))
 except Exception:
  infra=True;failed.append(traceback.format_exc())
 result={'passed':not failed,'infrastructure_error':infra,'checks':checks,'failed_checks':failed,'states':details}
 print(json.dumps(result,sort_keys=True));return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
