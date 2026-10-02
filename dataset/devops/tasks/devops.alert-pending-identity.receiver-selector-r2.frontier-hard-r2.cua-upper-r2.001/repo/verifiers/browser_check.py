from pathlib import Path
import hashlib,json,os,socket,subprocess,time,traceback
from urllib.request import urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from build_check import violations
from oracle import expected, epoch_context, expected_routes, expected_deliveries
from acceptance import row_matches, history_matches, annotation_errors, rendered_annotations_match
V=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
W=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
PROFILES=json.loads((V/'profiles.json').read_text())
RUNBOOK_SHEET=(V/'runbook.png').read_bytes()

def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def fetch(url):
 with urlopen(url,timeout=3) as r:return json.load(r)
def fetch_raw(url):
 with urlopen(url,timeout=3) as r:return r.status,r.headers.get('content-type'),r.read()
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
def policy_of(routing,scope):
 return ((routing or {}).get('epoch') or {}).get(scope,{}) .get('policy') or '—'
def scoped_pairs(epoch,routing):
 return [[scope,str(policy_of(routing,scope)),key,str(value)] for scope,pairs in (epoch or {}).items() for key,value in (pairs or {}).items()]
def selector_text(match):
 return ', '.join(f'{key}={value}' for key,value in (match or {}).items())
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
     declared={'epoch':{scope:{'keys':sorted(((spec or {}).get('pairs') or [{}])[0]),'policy':(spec or {}).get('policy')} for scope,spec in ((pf.get('routing') or {}).get('epoch') or {}).items()}}
     try:
      svc=subprocess.Popen(['node',str(V/'service.mjs'),'--port',str(sp),'--profile',key],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(svc);wait(su+'/health',svc)
      app=subprocess.Popen(['node','server.mjs','--port',str(ap)],cwd=W,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':su},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(app);wait(au,app)
      page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(1600);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      response=page.goto(au);ck(response.status==200,key+' HTTP200')
      ready=True
      try:page.locator('#app[data-ready=yes]').wait_for()
      except PlaywrightTimeout:
       ready=False
       surface=page.locator('#app').inner_text(timeout=1000) if page.locator('#app').count() else ''
       ck(False,key+' console renders after import and configure; shown instead: '+surface[:160])
      if not ready:
       page.close();continue
      def click(selector):page.locator(selector).click();page.wait_for_timeout(35)
      def inspect(label):
       audit=fetch(su+'/audit');scenario=next(s for s in pf['scenarios'] if s['id']==audit['scenario']);want=expected(pf,scenario,audit['cursor']);snap=audit['snapshot'];rows=want[audit['target']][-7:]
       routes_expected=expected_routes(pf,scenario,audit['cursor'])
       route_counts,unrouted_expected=expected_deliveries(routes_expected,want)
       primary_index=next(i for i,r in enumerate(routes_expected) if r['family']==pf['rules'][0]['family'])
       primary=routes_expected[primary_index]
       selector_pairs=page.locator('[data-test=receiver-selector-pair]').evaluate_all('(rows)=>rows.map(r=>[r.querySelector("[data-test=selector-key]").innerText,r.querySelector("[data-test=selector-value]").innerText])')
       ck(snap['delivery'].get('match')==primary['match'] and snap['delivery'].get('receiver')==primary['name'] and page.locator('[data-test=receiver-selector]').count()==1 and len(dict(selector_pairs))==len(selector_pairs) and dict(selector_pairs)==primary['match'],key+'/'+label+' actual receiver selector mapping')
       epoch_expected=epoch_context(pf,scenario,audit['cursor'])
       epoch_pairs=page.locator('[data-test=routing-epoch-pair]').evaluate_all('(rows)=>rows.map(r=>[r.querySelector("[data-test=epoch-scope]").innerText,r.querySelector("[data-test=epoch-policy]").innerText,r.querySelector("[data-test=epoch-key]").innerText,r.querySelector("[data-test=epoch-value]").innerText])')
       ck(snap['delivery'].get('epoch')==epoch_expected and page.locator('[data-test=routing-epoch]').count()==1 and sorted(epoch_pairs)==sorted(scoped_pairs(epoch_expected,pf.get('routing'))) and len(epoch_pairs)==len({(s,k) for s,_,k,_ in epoch_pairs}),key+'/'+label+' actual routing epoch context and policy class')
       routes_want=[{**route,'delivered':route_counts[i]} for i,route in enumerate(routes_expected)]
       ck(snap.get('routes')==routes_want,key+'/'+label+' actual route resolution and per-route delivery')
       routes_rendered=page.locator('[data-test=routes] tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.innerText))')
       routes_display=[[str(i+1),route['name'],route['family'],selector_text(route['match']),str(route_counts[i])] for i,route in enumerate(routes_expected)]
       ck(page.locator('[data-test=routes]').count()==1 and routes_rendered==routes_display,key+'/'+label+' route table pixels')
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
       ck(snap['delivery'].get('firing')==firing and snap['delivery'].get('delivered')==route_counts[primary_index] and snap['delivery'].get('unrouted')==unrouted_expected and page.locator('[data-test=firing]').inner_text()==f'firing {firing}' and page.locator('[data-test=delivered]').inner_text()==f'delivered {route_counts[primary_index]}' and page.locator('[data-test=unrouted]').inner_text()==f'unrouted {unrouted_expected}' and route_counts[primary_index]==firing and unrouted_expected==0,key+'/'+label+' correct receiver delivery')
       unaffected=[i for i,route in enumerate(routes_expected) if i!=primary_index]
       ck(all(route_counts[i]==0 for i in unaffected),key+'/'+label+' unaffected route stays empty')
       ck(page.locator('[data-action=scenario]').count()==len(pf['scenarios']) and page.locator('[data-action=target]').count()==len(scenario['targets']),key+'/'+label+' inventories')
       if page.locator('[data-test=labels]').count():
        prev,cur=rows[-2]['labels'],rows[-1]['labels'];keys=sorted(set(prev)|set(cur))
        actual=page.locator('[data-test=labels] tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.innerText))')
        ck(actual==[[k,prev.get(k,'—'),cur.get(k,'—')] for k in keys],key+'/'+label+' label diff')
        actual=page.locator('[data-test=annotations] .pair').evaluate_all('(rows)=>rows.map(r=>[r.querySelector("b").innerText,r.querySelector("span").innerText])')
        protected_actual=audit['history'][audit['target']][-1]
        ck(rendered_annotations_match(actual,protected_actual,rows[-1]),key+'/'+label+' annotation detail matches validated actual')
       details.append({'profile':key,'state':label,'history_matches':history_matches(audit['history'],want),'cursor':audit['cursor'],'state_name':rows[-1]['state'],'required_annotations':rows[-1]['annotations'],'actual_annotations':audit['history'][audit['target']][-1]['annotations'],'epoch':snap['delivery'].get('epoch'),'routes':snap.get('routes')})
       return audit
      def inspect_runbook(label):
       page.locator('[data-test=runbook]').wait_for()
       try:page.wait_for_function("()=>{const i=document.querySelector('[data-test=runbook]');return !!i&&i.complete&&i.naturalWidth>0;}",timeout=1600)
       except PlaywrightTimeout:pass
       status,ctype,body=fetch_raw(au+'/api/runbook')
       ck(status==200 and str(ctype).startswith('image/png') and hashlib.sha256(body).hexdigest()==hashlib.sha256(RUNBOOK_SHEET).hexdigest(),key+'/'+label+' runbook document served byte-exact as png')
       state=page.locator('[data-test=runbook]').evaluate_all('(imgs)=>imgs.map(i=>[i.currentSrc.split("/").slice(-2).join("/"),i.naturalWidth,i.naturalHeight,i.complete])')
       ck(state==[['api/runbook',1240,700,True]],key+'/'+label+' runbook pixels rendered from the evaluator document')
      catalog=fetch(su+'/catalog')
      ck(catalog.get('routing')==declared,key+' catalog declares epoch keys and opaque policy classes only (no ownership, no runbook mapping)')
      first=inspect('opening')['snapshot']
      selector_cases=[{}, {'rotation':'secondary'}, {'team':'platform & response','cluster':'west<2>'}, {'route_key':'value with spaces','unicode':'équipe'}]
      for selector_index,selector in enumerate(selector_cases):
       rendered_selector=page.evaluate("""async ({snapshot,selector,routing})=>{const {deliveryPanel}=await import('/src/views/delivery.js');const root=document.createElement('div');root.innerHTML=deliveryPanel({...snapshot,delivery:{...snapshot.delivery,match:selector}},routing);return {panels:root.querySelectorAll('[data-test=receiver-selector]').length,pairs:Array.from(root.querySelectorAll('[data-test=receiver-selector-pair]'),r=>[r.querySelector('[data-test=selector-key]')?.textContent,r.querySelector('[data-test=selector-value]')?.textContent])};}""",{'snapshot':first,'selector':selector,'routing':declared})
       ck(rendered_selector['panels']==1 and len(dict(rendered_selector['pairs']))==len(rendered_selector['pairs']) and dict(rendered_selector['pairs'])==selector,key+'/selector-renderer-'+str(selector_index)+' generic escaped selector mapping')
      epoch_cases=[
       ({},{'epoch':{}}),
       ({'capture':{},'evaluation':{'window':'w99'}},{'epoch':{'evaluation':{'policy':'RC-9'}}}),
       ({'capture':{'desk':'night shift & <ops>'},'evaluation':{'lane':'équipe','cycle':'c 9'}},{'epoch':{'capture':{'policy':'P & <5>'},'evaluation':{'policy':'σ-2'}}}),
       ({'intake':{'desk':'a'},'relay':{'feed':'b & <c>'},'sweep':{'window':'w 3'}},{'epoch':{'intake':{'policy':'RC-2'},'relay':{},'sweep':{'policy':None}}}),
      ]
      for epoch_index,(epoch,routing_case) in enumerate(epoch_cases):
       rendered_epoch=page.evaluate("""async ({snapshot,epoch,routing})=>{const {deliveryPanel}=await import('/src/views/delivery.js');const root=document.createElement('div');root.innerHTML=deliveryPanel({...snapshot,delivery:{...snapshot.delivery,epoch}},routing);return {panels:root.querySelectorAll('[data-test=routing-epoch]').length,pairs:Array.from(root.querySelectorAll('[data-test=routing-epoch-pair]'),r=>[r.querySelector('[data-test=epoch-scope]')?.textContent,r.querySelector('[data-test=epoch-policy]')?.textContent,r.querySelector('[data-test=epoch-key]')?.textContent,r.querySelector('[data-test=epoch-value]')?.textContent])};}""",{'snapshot':first,'epoch':epoch,'routing':routing_case})
       ck(rendered_epoch['panels']==1 and sorted(rendered_epoch['pairs'])==sorted(scoped_pairs(epoch,routing_case)) and len(rendered_epoch['pairs'])==len({(s,k) for s,_,k,_ in rendered_epoch['pairs']}),key+'/epoch-renderer-'+str(epoch_index)+' generic escaped routing epoch and policy mapping')
      route_cases=[
       [],
       [{'name':'a &<b>','family':'fam 1','match':{'k 1':'v & <x>'},'delivered':3}],
       [{'name':'r1','family':'f1','match':{},'delivered':0},{'name':'r2','family':'f2','match':{'flux':'équipe'},'delivered':2}],
      ]
      for route_index,routes_case in enumerate(route_cases):
       rendered_routes=page.evaluate("""async ({snapshot,routes})=>{const {routesPanel}=await import('/src/views/routes.js');const root=document.createElement('div');root.innerHTML=routesPanel({...snapshot,routes});return {panels:root.querySelectorAll('[data-test=routes]').length,rows:Array.from(root.querySelectorAll('[data-test=routes] tbody tr'),r=>Array.from(r.cells).map(c=>c.textContent))};}""",{'snapshot':first,'routes':routes_case})
       route_display=[[str(i+1),route['name'],route['family'],selector_text(route['match']),str(route['delivered'])] for i,route in enumerate(routes_case)]
       ck(rendered_routes['panels']==1 and rendered_routes['rows']==route_display,key+'/routes-renderer-'+str(route_index)+' generic escaped route table mapping')
      click('[data-action=view][data-value=runbook]');inspect_runbook('runbook-view');inspect('runbook-view-state')
      click('[data-action=view][data-value=labels]');inspect('identity-detail')
      for scenario in pf['scenarios']:
       click(f'[data-action=scenario][data-value="{scenario["id"]}"]');inspect(scenario['id'])
       click('[data-action=target][data-value=two]');inspect(scenario['id']+'-second')
       click('[data-action=target][data-value=one]')
       for n in range(8):click('[data-action=advance]');inspect(scenario['id']+'-advance-'+str(n))
       click('[data-action=replay]');one=inspect(scenario['id']+'-replay')['snapshot'];click('[data-action=replay]');ck(fetch(su+'/snapshot')==one,key+' repeated replay')
      click('[data-action=reset]');ck(inspect('reset')['snapshot']==first,key+' reset deterministic')
      click('[data-action=view][data-value=runbook]');inspect_runbook('runbook-after-reset');click('[data-action=view][data-value=series]')
      before=page.evaluate('performance.timeOrigin');page.reload();page.locator('#app[data-ready=yes]').wait_for();ck(page.evaluate('performance.timeOrigin')!=before,key+' actual reload');ck(inspect('reload')['snapshot']==first,key+' reload deterministic')
      for endpoint in ['/api/audit','/env/service.mjs','/verifiers/profiles.json','/verifiers/runbook.png','/gold.patch','/task.yaml']:
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
