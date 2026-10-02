from pathlib import Path
from decimal import Decimal
import base64,json,os,signal,socket,subprocess,time,traceback,secrets,math
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright,TimeoutError as PlaywrightTimeout
from build_check import violations
V=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent).resolve()
W=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
PLAN=json.loads((V/'profiles.json').read_text())
class Infrastructure(Exception):pass
class CandidateFailure(Exception):pass
used=set()
def available(n):
 for table in ['tcp','tcp6','udp','udp6']:
  for line in Path('/proc/net/'+table).read_text().splitlines()[1:]:
   cols=line.split();port=int(cols[1].rsplit(':',1)[1],16)
   if port==n and (table.startswith('udp') or cols[3]=='0A'):return False
 return True
def block(count):
 for n in range(57100,57149-count):
  needed=set(range(n,n+count))
  if needed&used:continue
  if all(available(p) for p in needed):used.update(needed);return n
 raise Infrastructure('Author ports busy; no unrelated cleanup allowed')
def fetch(url,token=None,post=None):
 req=Request(url,headers={'Authorization':'Bearer '+token} if token else {},data=None if post is None else json.dumps(post).encode())
 if post is not None:req.add_header('Content-Type','application/json')
 with urlopen(req,timeout=2) as r:return json.load(r)
def wait(url,proc,is_candidate=False):
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  if proc.poll() is not None:raise (CandidateFailure if is_candidate else Infrastructure)('owned '+('candidate' if is_candidate else 'protected')+' startup exited')
  try:
   with urlopen(url,timeout=.4) as r:
    if r.status==200:return
  except OSError:pass
  time.sleep(.025)
 raise (CandidateFailure if is_candidate else Infrastructure)('owned startup timeout')
def equal(a,b):
 return isinstance(a,(float,int)) and math.isfinite(a) and math.isclose(a,float(b),abs_tol=1e-9,rel_tol=1e-9)
def formed(profile,form):
 # Relay announce batches are atomic; only live-forwarded groups split per whole line.
 if form=='batched-valid-lines':return profile['groups']
 out=[]
 for g in profile['groups']:
  if g['announce']:out.append(g)
  else:out.extend({'source':g['source'],'announce':False,'lines':[line]} for line in g['lines'])
 return out
def expected(profile,form):
 groups=formed(profile,form);convention=profile['convention']
 state={};events=[];packets=[]
 for receipt,group in enumerate(groups,1):
  lines=[]
  for line_index,line in enumerate(group['lines']):
   key=line['identity'];token=line['token'];value=Decimal(token);before=state.get(key,Decimal(0))
   relative=convention=='signed-delta' and token[0] in '+-' and not group['announce']
   state[key]=before+value if relative else value
   lines.append(f"{key}:{token}|g")
   events.append({'receipt':receipt,'lineIndex':line_index,'identity':key,'source':group['source'],'token':token,'metricType':'g','parsedValue':value,'before':before,'value':state[key],'announce':group['announce']})
  packets.append({'source':group['source'],'bytes':'\n'.join(lines).encode('ascii')})
 return packets,events,state

def main():
 checks=[];failed=[];audits=[];cleanup=[];infra=False;observations=[]
 def ck(ok,label):
  checks.append(label)
  if not ok:failed.append(label)
 bad=violations()
 if bad:print(json.dumps({'passed':False,'infrastructure_error':False,'checks':['integrity before candidate execution'],'failed_checks':bad,'audits':[]}));return 1
 def stop(proc):
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
 def settle(origin,token,expected_count):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   a=fetch(origin+'/audit',token)
   if a['transportErrors']:
    # Only the protected native witness can report transport failure. No decoder/output error takes this path.
    raise Infrastructure('Protected native transport witness: '+json.dumps(a['transportErrors']))
   if a['writer'] and not a['running']:
    if a['committedReceipt']>=expected_count or not a['receipts'] or a['clockNow']-a['receipts'][-1]['receivedAt']>1050:return a
   time.sleep(.025)
  a=fetch(origin+'/audit',token)
  if a['running']:raise Infrastructure('Protected native producer did not finish')
  # No producer start, no decoder work, and missing sink events are candidate failures, never transport infrastructure.
  return a
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   try:
    for profile in PLAN['profiles']:
     for form in PLAN['transport_forms']:
      label=profile['id']+'/'+form;packets,events,want=expected(profile,form);procs=[];ports=[];page=None;token=secrets.token_hex(32)
      try:
       relay_ports=1+max(f['port_offset'] for f in profile['relays'])
       sp=block(relay_ports);ports.extend(range(sp,sp+relay_ports));origin=f'http://127.0.0.1:{sp}'
       svc=subprocess.Popen(['timeout','-k','2s','50s','node',str(V/'service.mjs'),'--port',str(sp),'--profile',profile['id'],'--form',form],env={**os.environ,'GAUGE_AUDIT_TOKEN':token},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);procs.append(svc);wait(origin+'/health',svc)
       empty=fetch(origin+'/audit',token);time.sleep(.06);empty2=fetch(origin+'/audit',token)
       ck(empty['receipts']==empty2['receipts']==[] and not empty2['history'] and not empty2['writer'] and empty2['state']=={},label+' independent no-input native control')
       ap=block(1);ports.append(ap);url=f'http://127.0.0.1:{ap}'
       def start_app():
        proc=subprocess.Popen(['timeout','-k','2s','45s','node','server.mjs','--port',str(ap)],cwd=W,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':origin},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);procs.append(proc);wait(url,proc,True);return proc
       app=start_app();page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(3000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
       ck(page.goto(url).status==200,label+' actual built task HTTP200');page.locator('#app[data-ready=yes]').wait_for()
       def grade(stage,at):
        a=settle(origin,token,len(packets));prefix=label+'/'+stage
        ck(a['epoch']==at,prefix+' deterministic session epoch '+str(at))
        actual_writer=[(x['source'],base64.b64decode(x['base64'])) for x in a['writer']]
        native=[(x['source'],base64.b64decode(x['base64'])) for x in a['receipts']]
        wanted=[(p['source'],p['bytes']) for p in packets]
        ck(actual_writer==wanted,prefix+' independent relay writer exact original bytes once')
        ck(native==wanted,prefix+' native witness complete order multiplicity and relay attribution')
        ck(all(x['sent'] for x in a['writer']),prefix+' all original kernel sends completed')
        ck(not a['contamination'],prefix+' no foreign native injection')
        ck(not a['sinkErrors'],prefix+' no invalid submitted sink events')
        ck(len(a['history'])==len(events),prefix+' all gauge update events conserved')
        for index,e in enumerate(events):
         got=a['history'][index] if index<len(a['history']) else {}
         item=prefix+'/update'+str(index+1)
         ck(all(got.get(k)==e[k] for k in ['receipt','lineIndex','identity','source']),item+' receipt identity attribution and multiplicity')
         ck(got.get('token')==e['token'] and got.get('metricType')=='g' and equal(got.get('parsedValue'),e['parsedValue']),item+' intact lexical token type and numeric parse')
         ck(equal(got.get('before'),e['before']) and equal(got.get('value'),e['value']),item+' native gauge state transition under the deployed relay generation')
         ck(isinstance(got.get('ageMs'),(int,float)) and 0<=got['ageMs']<=1000,item+' public one-second processing bound')
        ck(set(a['state'])==set(want) and all(equal(a['state'].get(k),v) for k,v in want.items()),prefix+' complete native-unit state')
        # The unsigned absolute stream is a protected healthy control even when signed update semantics fail.
        healthy=profile['identities'][2];healthy_events=[e for e in events if e['identity']==healthy];actual_healthy=[e for e in a['history'] if e['identity']==healthy]
        ck(len(actual_healthy)==len(healthy_events) and all(equal(g.get('value'),e['value']) for g,e in zip(actual_healthy,healthy_events)),prefix+' healthy unsigned absolute stream')
        # Relay sync registers are unaffected unsigned controls.
        registers={f['id']+'.sync' for f in profile['relays']}
        reg_events=[e for e in events if e['identity'] in registers];actual_reg=[g for g in a['history'] if g.get('identity') in registers]
        ck(len(actual_reg)==len(reg_events) and all(equal(g.get('value'),e['value']) and g.get('identity')==e['identity'] for g,e in zip(actual_reg,reg_events)),prefix+' relay sync registers stored as published')
        # Announce restatements are authoritative absolute readings under either relay generation.
        ann_events=[(i,e) for i,e in enumerate(events) if e['announce']]
        ck(all(index<len(a['history']) and equal(a['history'][index].get('value'),e['parsedValue']) for index,e in ann_events),prefix+' announce restatements applied as authoritative readings')
        public=fetch(url+'/api/snapshot');ck(public['state']==a['state'] and public['history']==a['history'] and public['receipts']==a['receipts'],prefix+' public diagnostics reflect actual receipt sink')
        ck('writer' not in public and 'transportErrors' not in public and 'archive' not in public and 'convention' not in public,prefix+' protected writer intent and provisioning excluded from public data')
        leak=json.dumps(public)
        ck(all(term not in leak for term in ['signed-delta','absolute-reading','convention','pass-through','folding','updateMode','update_mode']),prefix+' no machine-readable relay-generation field on any public surface')
        page.wait_for_timeout(150);body_text=page.locator('body').inner_text()
        opening=[e for e in events if e['receipt']==1]
        ck(all(f"{e['identity']}:{e['token']}|g" in body_text for e in opening),prefix+' opening relay announce batch visible in the datagram capture')
        lead=profile['identities'][0]
        first_signed=next(e for e in events if e['identity']==lead and e['token'][0] in '+-' and not e['announce'])
        ck(f"{first_signed['identity']}:{first_signed['token']}|g" in body_text,prefix+' signed live datagram visible in the capture')
        ck(profile['relays'][0]['id'] in body_text,prefix+' relay attribution visible on operator console')
        ck(('Epoch '+str(at)) in body_text,prefix+' session epoch visible on operator console')
        observations.append({'profile':label,'stage':stage,'body_text':body_text,'epoch':a['epoch']})
        if os.environ.get('OWNER32_SCREENSHOT_DIR'):
         dest=Path(os.environ['OWNER32_SCREENSHOT_DIR']);dest.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dest/f"{profile['id']}-{form}-{stage}.png"))
        audits.append({'profile':profile['id'],'form':form,'stage':stage,'audit':a});return a
       first=grade('opening-seeded-capture',1);time.sleep(.15);idle=fetch(origin+'/audit',token)
       ck(idle['receipts']==first['receipts'] and idle['history']==first['history'] and idle['state']==first['state'],label+' idle preserves gauges and multiplicity')
       page.locator('[data-action=select]').first.click();page.locator('[data-action=history]').click();page.wait_for_timeout(100)
       before_reload=fetch(origin+'/audit',token);page.reload();page.locator('#app[data-ready=yes]').wait_for();page.wait_for_timeout(120);after_reload=fetch(origin+'/audit',token)
       ck(before_reload['receipts']==after_reload['receipts'] and before_reload['history']==after_reload['history'],label+' browser reload read-only no reseed')
       if profile['id']=='A' and form=='batched-valid-lines':
        stop(app);app=start_app();page.reload();page.locator('#app[data-ready=yes]').wait_for();page.wait_for_timeout(150);restart=fetch(origin+'/audit',token)
        ck(restart['receipts']==after_reload['receipts'] and restart['history']==after_reload['history'] and restart['state']==after_reload['state'],label+' worker process restart hydrates retained sink without duplicate updates')
       page.locator('[data-action=reset]').click();page.wait_for_timeout(100);reset=fetch(origin+'/audit',token)
       ck(not reset['history'] and not reset['receipts'] and not reset['writer'] and not reset['state'],label+' reset clears actual session')
       page.reload();page.locator('#app[data-ready=yes]').wait_for();page.wait_for_timeout(100);reset_reload=fetch(origin+'/audit',token)
       ck(not reset_reload['receipts'] and not reset_reload['history'],label+' empty reset remains no-input on reload')
       page.locator('[data-action=run]').click();second=grade('reset-replay',3)
       ck([(h['identity'],h['value']) for h in first['history']]==[(h['identity'],h['value']) for h in second['history']],label+' deterministic fresh replay')
       for endpoint in ['/api/audit','/verifiers/profiles.json','/verifiers/service.mjs','/task.yaml','/gold.patch','/env/service.mjs']:
        try:
         with urlopen(url+endpoint,timeout=1) as response:status=response.status
        except HTTPError as e:status=e.code
        ck(status==404,label+' protected route denied '+endpoint)
       try:fetch(origin+'/audit');denied=False
       except HTTPError as e:denied=e.code==403
       ck(denied,label+' runtime audit requires external token')
       ck(not errors,label+' no browser exceptions')
      except (CandidateFailure,PlaywrightTimeout,HTTPError,ValueError,KeyError,TypeError,OSError) as e:
       ck(False,label+' candidate behavior unavailable: '+str(e))
      finally:
       if page:page.close()
       for proc in reversed(procs):stop(proc)
       for n in sorted(set(ports)):
        closed=available(n);cleanup.append({'profile':label,'port':n,'closed':closed});ck(closed,label+' owned TCP/UDP port closed '+str(n))
   finally:browser.close()
 except Infrastructure as e:infra=True;failed.append(str(e))
 except Exception:infra=True;failed.append(traceback.format_exc())
 result={'passed':not failed,'infrastructure_error':infra,'checks':checks,'failed_checks':failed,'audits':audits,'observations':observations,'cleanup':cleanup,'receipt_witness_outside_candidate':True,'decoder_output_loss_is_candidate_failure':True,'automatic_resends':0}
 print(json.dumps(result,sort_keys=True));return int(bool(failed))
if __name__=='__main__':
 signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(Infrastructure('author verifier deadline120s')));signal.alarm(120)
 raise SystemExit(main())
