"""Protected independent receiver oracle and browser consistency verifier."""
from pathlib import Path
import hashlib,json,os,socket,subprocess,time,traceback
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
from build_check import violations
ROOT=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
HERE=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
PROFILES=json.loads((HERE/'profiles.json').read_text())
CHECKS=[];FAILED=[];STATES=[];LIFECYCLE=[]
class InfrastructureError(RuntimeError):pass
def check(ok,label):
 CHECKS.append(label)
 if not ok:FAILED.append(label)
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def http(origin,route,data=None):
 r=Request(origin+'/'+route,data=None if data is None else json.dumps(data).encode(),headers={'content-type':'application/json'})
 with urlopen(r,timeout=3) as p:return json.load(p)
def http_bytes(origin,route):
 with urlopen(Request(origin+'/'+route),timeout=3) as p:return p.read()
def active_policy(profile):
 return next(row for row in PROFILES[profile]['policy']['profiles'] if row['status']=='active')
def wait(url):
 end=time.monotonic()+10
 while time.monotonic()<end:
  try:
   with urlopen(url,timeout=1) as r:
    if r.status==200:return
  except OSError:pass
  time.sleep(.08)
 raise RuntimeError('runtime unavailable '+url)
def hash_percent(ident):
 value=0
 for c in ident:value=(31*value+ord(c))%(2**32)
 return value%100
# This oracle never reads a submitted plan, renderer, or service expected-output field.
def received(spec,pipeline):
 first=10000+spec['offset'];duration=1880 if spec['shape']=='slow' else 620
 root=spec['id']+'-root';child=spec['id']+'-child';error=spec['shape']=='child-error'
 return {**spec,'pipeline':pipeline,'spans':[{'id':root,'parentId':None,'name':'request','status':'OK','startMs':0,'endMs':duration,'arrivalMs':first},{'id':child,'parentId':root,'name':'dependency' if error else 'backend','status':'ERROR' if error else 'OK','startMs':90,'endMs':duration-50,'arrivalMs':first+spec['lagMs']}]}
def expected_traces(profile,scenario,replayed):
 traces=[received(x,'live') for x in PROFILES[profile]['scenarios'][scenario]]
 if replayed:traces.append(received(PROFILES[profile]['replay'],'replay'))
 return traces
def truth(trace):
 spans=trace['spans'];error=any(s['status']=='ERROR' for s in spans)
 slow=max(s['endMs'] for s in spans)-min(s['startMs'] for s in spans)>=1500
 return {'sampled':error or slow or hash_percent(trace['id'])<5,'bucket':'error' if error else 'slow' if slow else 'ordinary'}
def semantic_errors(audit,profile,scenario,replayed):
 errors=[];expected=expected_traces(profile,scenario,replayed);actual=audit['actual']
 if audit['received']!=expected:errors.append('received spans and timestamps changed')
 expected_keep=[t['id'] for t in expected if truth(t)['sampled']]
 if [t['id'] for t in actual['exports']]!=expected_keep:errors.append('trace-store membership differs from independent received-span predicate')
 if any(t.get('spanCount')!=2 for t in actual['exports']):errors.append('sampled trace lost spans')
 metrics={'spansReceived':2*len(expected),'tracesCompleted':len(expected),'sampled':len(expected_keep),'dropped':len(expected)-len(expected_keep)}
 if actual['metrics']!=metrics:errors.append('retention counters differ')
 for t in actual['decisions']:
  e=next((x for x in expected if x['id']==t['id']),None)
  if e is None:errors.append('unreceived decision');continue
  if t['sampled']!=truth(e)['sampled']:errors.append('wrong keep/drop '+t['id'])
  if t['spans']!=e['spans']:errors.append('changed received detail')
 act=active_policy(profile)
 for t in actual['timeline']:
  first=next(x['spans'][0]['arrivalMs'] for x in expected if x['id']==t['traceId'])
  if not act['deliveryEnvelopeMs']<=t['decisionAtMs']-first<=act['decisionSloMs']:errors.append('decision outside the receiver-published envelope/SLO band')
 if actual['replayCount']!=int(replayed):errors.append('replay input missing/duplicated')
 return errors

def inspect(page,origin,profile,scenario,replayed,label):
 a=http(origin,'audit');s=a['actual'];errors=semantic_errors(a,profile,scenario,replayed)
 check(not errors,label+': independent retention and finite decision budget'+(' / '+', '.join(errors) if errors else ''))
 check(s['scenarioId']==scenario,label+': scenario identity')
 expected=expected_traces(profile,scenario,replayed)
 filters=s['filter'];want=[t for t in expected if (filters['bucket']=='all' or truth(t)['bucket']==filters['bucket']) and (filters['decision']=='all' or (filters['decision']=='sampled')==truth(t)['sampled'])]
 check([x['id'] for x in s['decisions']]==[x['id'] for x in want],label+': filtered trace inventory')
 view=page.evaluate('''() => ({
 ready:document.querySelector('[data-testid=app]')?.dataset.ready,
 metrics:[...document.querySelectorAll('#funnel strong')].map(x=>Number(x.textContent)),
 rows:[...document.querySelectorAll('#decisions li')].map(x=>({id:x.dataset.traceId,kind:x.className,text:x.textContent})),
 exports:[...document.querySelectorAll('#exports code')].map(x=>x.textContent),
 details:document.querySelector('#detail').innerText,
 spans:[...document.querySelectorAll('#detail .spans li')].map(x=>x.innerText),
 buckets:[...document.querySelectorAll('#buckets tbody tr')].map(x=>[...x.querySelectorAll('td')].map(y=>y.textContent.trim())),
 scenarios:[...document.querySelectorAll('#scenario button')].map(x=>x.dataset.scenario),
 probeCount:document.querySelector('#probe').options.length,
 error:document.querySelector('#error').textContent,
 diagnostics:document.querySelector('#diagnostics').innerText,
 replayDisabled:document.querySelector('#replay').disabled,
 timelineCount:document.querySelectorAll('#timeline .timeline-row').length
 })''')
 check(view['ready']=='yes' and not view['error'],label+': ready/no UI errors')
 check(view['metrics']==list(s['metrics'].values()),label+': counters rendered from actual telemetry')
 check([x['id'] for x in view['rows']]==[x['id'] for x in s['decisions']],label+': all decision rows rendered')
 for row,actual in zip(view['rows'],s['decisions']):
  kind='sampled' if actual['sampled'] else 'dropped'
  check(row['kind']==kind and kind in row['text'],label+': honest keep/drop '+actual['id'])
 check(view['exports']==[x['id'] for x in s['exports']],label+': exports honestly rendered')
 selected=s['selected'];detail=view['details']
 check(selected['id'] in detail and selected['service'] in detail,label+': selected trace identity')
 check(('sampled' if selected['sampled'] else 'dropped') in detail,label+': selected decision')
 check('+'+str(selected['decisionAtMs']-selected['firstArrivalMs'])+' ms' in detail,label+': decision time visible')
 check(len(view['spans'])==len(selected['spans']),label+': every received span visible')
 for text,span in zip(view['spans'],selected['spans']):
  check(span['status'] in text and str(span['arrivalMs']-selected['firstArrivalMs'])+' ms' in text,label+': span status and receipt visible')
 want_buckets=[[x['label'],str(x['received']),str(x['sampled']),str(round(x['sampled']/x['received']*100))+'%' if x['received'] else '0%'] for x in s['buckets']]
 check(view['buckets']==want_buckets,label+': buckets agree with runtime')
 check(view['scenarios']==['delayed','early','interleaved'],label+': all incident windows retained')
 check(view['probeCount']==4,label+': all probes retained')
 check(str(s['diagnostics']['waitMs'])+' ms' in view['diagnostics'],label+': deployed decision wait honestly displayed')
 check(all(key not in s['diagnostics'] for key in ('deliveryEnvelopeMs','decisionBudgetMs','decisionSloMs'))and 'contract' not in a and 'policy' not in a,label+': policy service levels stay out of machine-readable telemetry')
 check(view['replayDisabled']==bool(replayed),label+': replay lifecycle rendered')
 check(view['timelineCount']==len(expected),label+': every trace timeline retained')
 STATES.append({'profile':profile,'scenario':scenario,'label':label,'semantic_correct':not errors,'state_sha256':hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()})
 return a

def verify_panel(page,app_origin,service_origin,profile,label):
 canonical=http_bytes(service_origin,'service-levels')
 served=http_bytes(app_origin,'api/service-levels')
 check(canonical[:8]==b'\x89PNG\r\n\x1a\n' and served==canonical,label+': policy panel served byte-identically through the console host')
 width=int.from_bytes(canonical[16:20],'big');height=int.from_bytes(canonical[20:24],'big')
 img=page.evaluate('''() => {const img=document.querySelector('#diagnostics img');if(!img)return null;const r=img.getBoundingClientRect();const s=getComputedStyle(img);return {src:img.currentSrc,complete:img.complete,nw:img.naturalWidth,nh:img.naturalHeight,x:r.x,y:r.y,w:r.width,h:r.height,display:s.display,visibility:s.visibility,opacity:Number(s.opacity)}}''')
 check(bool(img) and img['complete'] and '/api/service-levels' in img['src'] and img['nw']==width and img['nh']==height,label+': operator diagnostics embed the receiver-published policy panel')
 check(bool(img) and img['display']!='none' and img['visibility']=='visible' and img['opacity']>0.9 and img['w']>=0.9*width and img['h']>=0.9*height and img['x']>=0 and img['x']+img['w']<=1280,label+': policy panel visibly rendered at legible scale')
 return {'width':width,'height':height,'sha256':hashlib.sha256(canonical).hexdigest()}
def settle(page):page.wait_for_timeout(70)
def run_profile(browser,profile):
 service_port,app_port=port(),port();service_origin=f'http://127.0.0.1:{service_port}';app_origin=f'http://127.0.0.1:{app_port}'
 processes=[]
 try:
  svc=subprocess.Popen(['node',str(HERE/'sampler_service.mjs'),'--port',str(service_port),'--profile',profile],cwd=HERE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(svc)
  try:wait(service_origin+'/health')
  except Exception as e:raise InfrastructureError('protected service startup: '+str(e)) from e
  app=subprocess.Popen(['node','server.mjs','--port',str(app_port)],cwd=ROOT,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':service_origin},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(app);wait(app_origin)
  page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(1500)
  response=page.goto(app_origin,wait_until='domcontentloaded',timeout=10000);check(response.status==200,profile+': task page HTTP200');page.locator('[data-testid=app][data-ready=yes]').wait_for();settle(page)
  opening=http(service_origin,'snapshot');initial=inspect(page,service_origin,profile,'delayed',False,profile+': opening')
  panel=verify_panel(page,app_origin,service_origin,profile,profile+': opening');STATES.append({'profile':profile,'label':profile+': policy panel','panel_sha256':panel['sha256']})
  for scenario in ['delayed','early','interleaved']:
   if scenario!='delayed':
    button=page.locator('[data-scenario="'+scenario+'"]')
    check(button.count()==1,profile+': window reachable '+scenario)
    if not button.count():continue
    button.click();settle(page)
   a=inspect(page,service_origin,profile,scenario,False,profile+': '+scenario)
   # Every trace can be selected, including ordinary controls and child errors.
   for item in list(a['actual']['decisions']):
    row=page.locator('[data-trace-id="'+item['id']+'"] button')
    if row.count()!=1:check(False,profile+': missing selectable trace');continue
    row.click();settle(page)
    selected=http(service_origin,'snapshot')['selected'];check(selected['id']==item['id'],profile+': selection changes detail')
    check(selected['id'] in page.locator('#detail').inner_text(),profile+': selected trace displayed')
   for kind,value in [('bucket','error'),('bucket','slow'),('bucket','ordinary'),('bucket','all'),('decision','sampled'),('decision','dropped'),('decision','all')]:
    page.locator('#'+kind).select_option(value);settle(page);inspect(page,service_origin,profile,scenario,False,profile+': '+scenario+' '+kind+' '+value)
  # Replay is tested even if a candidate deletes its effect; that is a scorable failure.
  current=http(service_origin,'snapshot')['scenarioId'];page.locator('#replay').click();settle(page)
  inspect(page,service_origin,profile,current,True,profile+': replay')
  first=http(service_origin,'snapshot');http(service_origin,'replay',{});check(http(service_origin,'snapshot')==first,profile+': replay idempotent')
  act=active_policy(profile)
  for probe in PROFILES[profile]['probes']:
   page.locator('#probe').select_option(probe['id']);page.locator('#run-probe').click();settle(page);a=http(service_origin,'audit');p=a['actual']['probeResult'];expected=received(probe['trace'],'probe')
   check(a['probeTrace']=={k:v for k,v in expected.items() if k!='pipeline'},profile+': protected probe payload')
   check(p is not None and p['id']==expected['id'] and p['sampled']==truth(expected)['sampled'],profile+': unseen probe outcome '+probe['id'])
   if p:check(act['deliveryEnvelopeMs']<=p['decisionAtMs']-p['firstArrivalMs']<=act['decisionSloMs'],profile+': probe decision inside the published envelope/SLO band')
   check(('Would sample' if p and p['sampled'] else 'Would drop') in page.locator('#probe-result').inner_text(),profile+': probe result rendered')
  page.reload(wait_until='domcontentloaded');settle(page);check(http(service_origin,'snapshot')==opening,profile+': reload repeats pristine opening')
  http(service_origin,'reset',{});page.reload(wait_until='domcontentloaded');settle(page);check(http(service_origin,'snapshot')==opening,profile+': reset and replay deterministic')
  verify_panel(page,app_origin,service_origin,profile,profile+': after reset')
  for endpoint in ['api/audit','api/reset','verifiers/browser_check.py','gold.patch','task.yaml','env/service.mjs','unrecognized']:
   try:
    with urlopen(app_origin+'/'+endpoint,timeout=2) as response:code=response.status
   except HTTPError as e:code=e.code
   check(code==404,profile+': protected HTTP blocked '+endpoint)
  page.close()
 finally:
  for p in reversed(processes):
   if p.poll() is None:p.terminate()
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
  for n in [app_port,service_port]:
   with socket.socket() as s:s.settimeout(.2);closed=s.connect_ex(('127.0.0.1',n))!=0
   check(closed,profile+': own runtime port closed');LIFECYCLE.append({'port':n,'closed':closed})

def main():
 bad=violations()
 if bad:
  print(json.dumps({'passed':False,'infrastructure_error':False,'checks':['protected build/proxy and source symlinks'],'failed_checks':['integrity: '+', '.join(bad)]}));return 1
 infra=False
 try:
  with sync_playwright() as p:
   try:browser=p.chromium.launch(headless=True)
   except Exception as e:raise InfrastructureError('native browser startup: '+str(e)) from e
   try:
    for profile in ['visible','hidden','hidden-order']:run_profile(browser,profile)
   finally:browser.close()
 except Exception as e:
  # Missing controls or candidate application failures remain scorable failures.
  infra=isinstance(e,InfrastructureError)
  FAILED.append(type(e).__name__+': '+str(e));CHECKS.append('application workflow completed')
 result={'passed':not FAILED,'infrastructure_error':infra,'checks':CHECKS,'failed_checks':FAILED,'states':STATES,'lifecycle':LIFECYCLE,'oracle':'independent Python predicate over protected receiver fixture; never submitted plan or renderer'}
 print(json.dumps(result,indent=2));return 0 if not FAILED else 1
if __name__=='__main__':raise SystemExit(main())
