from pathlib import Path
import http.client,json,os,signal,socket,subprocess,time,traceback,secrets
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright,TimeoutError as PlaywrightTimeout
from build_check import violations
V=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent).resolve()
W=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
ALLOW=30
used=set()
def port():
 for n in range(29500,29700):
  if n in used:continue
  with socket.socket() as s:
   try:s.bind(('127.0.0.1',n));used.add(n);return n
   except OSError:pass
 raise RuntimeError('owner29 author ports exhausted')
def fetch(url,token=None):
 with urlopen(Request(url,headers={'Authorization':'Bearer '+token} if token else {}),timeout=3) as r:return json.load(r)
def wait(url,proc):
 end=time.monotonic()+8
 while time.monotonic()<end:
  if proc.poll() is not None:raise RuntimeError('owned server exited during startup')
  try:
   with urlopen(url,timeout=.5) as r:
    if r.status==200:return
  except (OSError,http.client.HTTPException):pass
  time.sleep(.04)
 raise RuntimeError('owned server readiness timed out')
def canonical(rows):return sorted(json.dumps({'name':r['name'],'labels':r['labels'],'value':r['value']},sort_keys=True) for r in rows)
def status_text(kind,msv):
 if kind=='ingested':return 'Ingested \u00b7 sample age %d ms'%msv
 if kind=='canceled':return 'Canceled +%d ms \u00b7 incomplete'%msv
 return 'Rejected \u00b7 truncated body'
def main():
 checks=[];failed=[];audits=[];infra=False;observations=[];cleanups=[]
 def ck(ok,label):
  checks.append(label)
  if not ok:failed.append(label)
 bad=violations()
 if bad:print(json.dumps({'passed':False,'infrastructure_error':False,'checks':['integrity before candidate execution'],'failed_checks':bad,'audits':[]}));return 1
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   try:
    for profile in ['visible','hidden-epoch-rotation','hidden-cadence-mix']:
     processes=[];ports=[];token=secrets.token_hex(32)
     try:
      sp=port();ports.append(sp);origin=f'http://127.0.0.1:{sp}'
      svc=subprocess.Popen(['node',str(V/'service.mjs'),'--port',str(sp),'--profile',profile],env={**os.environ,'SCRAPE_AUDIT_TOKEN':token},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);processes.append(svc);wait(origin+'/health',svc)
      ap=port();ports.append(ap);url=f'http://127.0.0.1:{ap}'
      app=subprocess.Popen(['node','server.mjs','--port',str(ap)],cwd=W,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':origin},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);processes.append(app);wait(url,app)
      page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(6000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      ck(page.goto(url).status==200,profile+' actual task HTTP200');page.locator('#app[data-ready=yes]').wait_for()
      opening=fetch(origin+'/audit',token);ck(not opening['running'] and all(not t['started'] for t in opening['current']),profile+' idle no-input control')
      board=opening['board'];revisions=opening['revisions'];superseded=opening['supersededRevisions']
      ck(len(board)==2 and board[0]['revision']!=board[1]['revision'],profile+' rollout owns two activation epochs with distinct active policy revisions')
      ck(all(e['revision'] in revisions for e in board),profile+' every scheduled epoch activates an owned policy revision')
      ck(opening['epochCode']==board[0]['code'] and opening['activeRevision']==board[0]['revision'],profile+' opening activation epoch matches the schedule head')
      for rev,grid in {**revisions,**superseded}.items():
       ck(len(grid)==2 and all(len(classes)==2 for classes in grid.values()),profile+' revision '+rev+' owns a two-tier by two-receiver-class deadline grid')
       ck(all(len({c['capMs'] for c in classes.values()})==2 for classes in grid.values()),profile+' revision '+rev+' sibling receiver classes own distinct approved caps')
       ck(all(c['freshMs']<c['capMs']<c['cancelMs'] for classes in grid.values() for c in classes.values()),profile+' revision '+rev+' fresh<cap<cancel ordering')
      revA,revB=board[0]['revision'],board[1]['revision']
      differing=[(t,k) for t in revisions[revA] for k in revisions[revA][t] if revisions[revA][t][k]['capMs']!=revisions[revB][t][k]['capMs']]
      ck(len(differing)>=2,profile+' consecutive activation epochs change at least two tier/class approved caps')
      ck(bool(superseded),profile+' superseded revisions remain published for audit only')
      all_cells=[c for grid in list(revisions.values())+list(superseded.values()) for classes in grid.values() for c in classes.values()]
      snap0=fetch(origin+'/snapshot')
      ck(snap0.get('profileCode')==opening['profileCode'],profile+' public profile code matches owned rollout')
      ck(snap0.get('epochCode')==opening['epochCode'],profile+' public activation epoch matches owned schedule state')
      ck(all(k not in snap0 for k in ('objectives','windows','revisions','supersededRevisions','board','activeRevision','reference')),profile+' structured snapshot excludes policy mapping and reference oracle')
      ck('PRV-' not in json.dumps(snap0),profile+' structured snapshot carries no policy revision token')
      ck(not snap0.get('history'),profile+' idle structured history has no compliant-reference oracle')
      for name,dims in (('activation-board-image',{'w':1400,'h':700,'complete':True}),('deadline-matrix-image',{'w':1400,'h':880,'complete':True})):
       image=page.locator('[data-test=%s]'%name)
       image.wait_for(state='visible')
       got=image.evaluate('(img)=>({w:img.naturalWidth,h:img.naturalHeight,complete:img.complete})')
       ck(got==dims,profile+' protected operator surface PNG loaded '+name)
      ck(page.locator('[data-test=profile-code]').inner_text().strip()==opening['profileCode'],profile+' live rollout profile displayed beside publications')
      ck(page.locator('[data-test=epoch-code]').inner_text().strip()==opening['epochCode'],profile+' live activation epoch displayed beside publications')
      for route in ('/api/activation-board','/api/deadline-matrix'):
       with urlopen(url+route,timeout=3) as rr:
        ck(rr.headers.get_content_type()=='image/png' and len(rr.read())>20000,profile+' application serves evaluator-owned PNG surface '+route)
      body_text=page.locator('body').inner_text()
      for w in all_cells:
       for value in (w['freshMs'],w['cancelMs'],w['capMs']):
        ck(str(value) not in body_text and ('%0.2f'%(value/1000)) not in body_text,profile+' deadline value remains outside DOM text '+str(value))
      for rev in list(revisions)+list(superseded):
       ck(rev not in body_text,profile+' policy revision token remains outside DOM text '+rev)
      reference=opening['reference']
      ck(len(reference)==8,profile+' protected compliance reference ledger retained')
      for x in reference:
       want=status_text(x['kind'],x['ms'])
       ck(want not in body_text,profile+' protected reference text absent from DOM '+x['key'])
       if x['kind']=='ingested':
        ck(x['ms']<revisions[x['revision']][x['tier']][x['receiverClass']]['freshMs'],profile+' protected reference receipt satisfies owned freshness '+x['key'])
      def run(label):
       page.locator('[data-action=run]').click();start=time.monotonic()
       while True:
        a=fetch(origin+'/audit',token)
        if a['episode'] and not a['running'] and all(t['started'] for t in a['current']):break
        if time.monotonic()-start>6.5:raise ValueError('candidate did not dispatch or complete diagnostic episode')
        time.sleep(.07)
       page.wait_for_timeout(300);pre=profile+'/'+label
       windows=a['revisions'][a['activeRevision']]
       ck(len(a['current'])==8,pre+' all targets retained')
       for t in a['current']:
        key=pre+'/'+t['key'];w=windows[t['tier']][t['klass']]
        ck(t.get('policyEpoch')==a['epochCode'],key+' attempt bound to the live activation epoch')
        ck(t.get('requestCount',0)>=1,key+' native exporter request received')
        ck(t.get('closed') is True,key+' native socket closed')
        if t['supported']:
         ck(t['accepted'],key+' complete samples actually ingested')
         ck(canonical(t['receivedSamples'])==canonical(t['expected']),key+' exact semantic sample multiset conserved')
         ck(t.get('receiptAgeMs',1e9)<=w['freshMs']+ALLOW,key+' published epoch/tier/class freshness objective')
         ck(t.get('responseFinished') is True,key+' complete native response before ingestion')
        else:
         ck(not t['accepted'] and not t['receivedSamples'],key+' no partial late or invalid ingestion')
         ck(t.get('closedMs',1e9)<=w['cancelMs']+ALLOW,key+' published epoch/tier/class cancellation objective')
         ck(not t.get('responseFinished'),key+' incomplete response correctly remains incomplete')
       snap=fetch(origin+'/snapshot');ck(len(snap['targets'])==8,pre+' public reporting keeps all targets')
       ck(snap.get('epochCode')==a['epochCode'],pre+' public activation epoch matches owned schedule state')
       for s,t in zip(snap['targets'],a['current']):
        ck(s['accepted']==t['accepted'] and canonical(s['receivedSamples'])==canonical(t['receivedSamples']),pre+'/'+t['key']+' report reflects actual receiver state')
        ck(s.get('tier')==t['tier'],pre+'/'+t['key']+' reported tier matches owned assignment')
        ck(s.get('receiverClass')==t['klass'],pre+'/'+t['key']+' reported receiver class matches owned assignment')
        ck(all(k not in s for k in ('expected','body','plan','supported','windows','klass','win','policyEpoch')),pre+'/'+t['key']+' oracle internals excluded from public response')
       accepted=sum(1 for t in a['current'] if t['accepted'])
       ck(page.locator('.pill.good').count()==accepted,pre+' displayed ingested pills equal actual receiver acceptances')
       for t in a['current']:
        shown=page.locator('[data-test=assign-%s]'%t['key']).inner_text().strip()
        ck(shown==t['tier']+' \u00b7 '+t['klass'],pre+'/'+t['key']+' displayed tier/class assignment matches owned rollout state')
       ck(page.locator('[data-test=epoch-code]').inner_text().strip()==a['epochCode'],pre+' displayed activation epoch matches owned schedule state')
       ck(not any(h.get('round')=='reference' for h in snap['history']),pre+' structured history excludes protected reference rows')
       # UI evidence is recorded; the semantic oracle above never matches a table layout.
       observations.append({'profile':profile,'episode':label,'body_text':page.locator('body').inner_text(),'audit_episode':a['episode'],'epoch':a['epochCode'],'revision':a['activeRevision']})
       if os.environ.get('OWNER29_SCREENSHOT_DIR'):
        dest=Path(os.environ['OWNER29_SCREENSHOT_DIR']);dest.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dest/f'{profile}-{label}.png'),full_page=True)
       audits.append(a);return a
      first=run('initial')
      ck(first['activeRevision']==board[0]['revision'],profile+' first episode governed by the schedule-head revision')
      if profile=='visible':
       page.locator('[data-action=detail][data-key=affected]').click();page.wait_for_timeout(100)
       shown_tier=page.locator('[data-test=tier]').inner_text().strip()
       shown_class=page.locator('[data-test=receiver-class]').inner_text().strip()
       actual=[t for t in first['current'] if t['key']=='affected'][0]
       ck(shown_tier==actual['tier'],profile+' request detail displays the owned tier assignment')
       ck(shown_class==actual['klass'],profile+' request detail displays the owned receiver-class assignment')
       ck('Collection tier' in page.locator('body').inner_text() and 'Receiver class' in page.locator('body').inner_text(),profile+' tier and receiver-class facts present in request detail')
       retained=fetch(origin+'/audit',token);ck(retained['current']==first['current'],profile+' opening detail does not alter completed evidence')
       page.reload();page.locator('#app[data-ready=yes]').wait_for();ck(fetch(origin+'/audit',token)['current']==first['current'],profile+' reload retains completed request diagnostics')
      page.locator('[data-action=reset]').click();page.wait_for_timeout(200);reset=fetch(origin+'/audit',token)
      ck(reset['episode']==0 and all(not t['started'] for t in reset['current']),profile+' explicit reset clears active episode only')
      ck(reset['epochCode']==board[1]['code'] and reset['activeRevision']==board[1]['revision'],profile+' reset advances the rollout to its next scheduled activation epoch')
      ck(page.locator('[data-test=epoch-code]').inner_text().strip()==reset['epochCode'],profile+' displayed activation epoch follows the owned schedule after reset')
      hist=fetch(origin+'/snapshot')['history']
      ck(len([h for h in hist if h.get('round')=='episode 1'])==8 and not any(h.get('round')=='reference' for h in hist),profile+' reset retains completed attempt rows without structured reference oracle')
      ck(all(h.get('policyEpoch')==board[0]['code'] for h in hist if h.get('round')=='episode 1'),profile+' retained ledger rows keep their original activation epoch provenance')
      body_after=page.locator('body').inner_text()
      ck(hist[0]['status'] in body_after,profile+' completed attempt evidence still displayed after reset')
      ck(board[0]['code'] in body_after,profile+' ledger keeps the prior activation epoch visible after reset')
      second=run('epoch-advance')
      ck(second['activeRevision']==board[1]['revision'] and second['activeRevision']!=first['activeRevision'],profile+' replay under the same profile is governed by a different active policy revision')
      ck([t['expected'] for t in first['current']]==[t['expected'] for t in second['current']],profile+' deterministic reset payload semantics')
      for endpoint in ['/api/audit','/api/runbook','/verifiers/profiles.json','/verifiers/service.mjs','/task.yaml','/gold.patch','/env/service.mjs']:
       try:
        with urlopen(url+endpoint,timeout=2) as r:status=r.status
       except HTTPError as e:status=e.code
       ck(status==404,profile+' protected HTTP route denied '+endpoint)
      try:fetch(origin+'/audit');denied=False
      except HTTPError as e:denied=e.code==403
      ck(denied,profile+' admin audit requires external authentication')
      ck(not errors,profile+' no browser runtime errors');page.close()
     finally:
      for proc in reversed(processes):
       if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
       try:proc.wait(timeout=2)
       except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
      for n in ports:
       with socket.socket() as s:
        closed=s.connect_ex(('127.0.0.1',n))!=0;cleanups.append({'port':n,'closed':closed});ck(closed,profile+' own port closed')
   finally:browser.close()
 except (PlaywrightTimeout,HTTPError,ValueError,KeyError,TypeError,IndexError) as e:failed.append('candidate behavior unavailable: '+str(e))
 except Exception:infra=True;failed.append(traceback.format_exc())
 print(json.dumps({'passed':not failed,'infrastructure_error':infra,'checks':checks,'failed_checks':failed,'audits':audits,'observations':observations,'cleanup':cleanups},sort_keys=True));return int(bool(failed))
if __name__=='__main__':
 signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('verifier work deadline 150s')));signal.alarm(150)
 raise SystemExit(main())
