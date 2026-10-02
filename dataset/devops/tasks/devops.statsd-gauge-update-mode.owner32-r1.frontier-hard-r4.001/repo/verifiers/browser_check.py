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
def active(entries,at):
 current=entries[0]
 for entry in entries:
  if entry['from_epoch']<=at:current=entry
 return current
def expected(profile,form,at):
 wave=active(profile['waves'],at)
 groups=wave['groups'] if form=='batched-valid-lines' else [{'source':g['source'],'operations':[o]} for g in wave['groups'] for o in g['operations']]
 state={};events=[];packets=[]
 for receipt,group in enumerate(groups,1):
  lines=[]
  for line_index,op in enumerate(group['operations']):
   key=op['identity'];value=Decimal(op['value']);before=state.get(key,Decimal(0));state[key]=value if op['operation']=='set' else before+value
   lines.append(f"{key}:{op['wire_token']}|g")
   events.append({'receipt':receipt,'lineIndex':line_index,'identity':key,'source':group['source'],'token':op['wire_token'],'metricType':'g','parsedValue':value,'before':before,'value':state[key]})
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
      label=profile['id']+'/'+form;procs=[];ports=[];page=None;token=secrets.token_hex(32)
      try:
       fleet_ports=1+max(f['port_offset'] for f in PLAN['fleet'])
       sp=block(fleet_ports);ports.extend(range(sp,sp+fleet_ports));origin=f'http://127.0.0.1:{sp}'
       svc=subprocess.Popen(['timeout','-k','2s','50s','node',str(V/'service.mjs'),'--port',str(sp),'--profile',profile['id'],'--form',form],env={**os.environ,'GAUGE_AUDIT_TOKEN':token},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);procs.append(svc);wait(origin+'/health',svc)
       empty=fetch(origin+'/audit',token);time.sleep(.06);empty2=fetch(origin+'/audit',token)
       ck(empty['receipts']==empty2['receipts']==[] and not empty2['history'] and not empty2['writer'] and empty2['state']=={},label+' independent no-input native control')
       ck([p['id'] for p in empty2['producers']]==[f['id'] for f in PLAN['fleet']],label+' fleet inventory published before any traffic')
       ap=block(1);ports.append(ap);url=f'http://127.0.0.1:{ap}'
       def start_app():
        proc=subprocess.Popen(['timeout','-k','2s','45s','node','server.mjs','--port',str(ap)],cwd=W,env={**os.environ,'CUA_SWE_EXTERNAL_SERVICE_ORIGIN':origin},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);procs.append(proc);wait(url,proc,True);return proc
       app=start_app();page=browser.new_page(viewport={'width':1280,'height':720});page.set_default_timeout(3000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
       ck(page.goto(url).status==200,label+' actual built task HTTP200');page.locator('#app[data-ready=yes]').wait_for()
       def grade(stage,at):
        packets,events,want=expected(profile,form,at)
        a=settle(origin,token,len(packets));prefix=label+'/'+stage
        ck(a['epoch']==at,prefix+' deterministic session epoch '+str(at))
        actual_writer=[(x['source'],base64.b64decode(x['base64'])) for x in a['writer']]
        native=[(x['source'],base64.b64decode(x['base64'])) for x in a['receipts']]
        wanted=[(p['source'],p['bytes']) for p in packets]
        ck(actual_writer==wanted,prefix+' independent producer exact original bytes once per provisioned endpoint')
        ck(native==wanted,prefix+' native witness complete order multiplicity and producer attribution')
        ck(all(x['sent'] for x in a['writer']),prefix+' all original kernel sends completed')
        ck(not a['contamination'],prefix+' no foreign native injection')
        ck(not a['sinkErrors'],prefix+' no invalid submitted sink events')
        ck(len(a['history'])==len(events),prefix+' all gauge update events conserved')
        for index,e in enumerate(events):
         got=a['history'][index] if index<len(a['history']) else {}
         item=prefix+'/update'+str(index+1)
         ck(all(got.get(k)==e[k] for k in ['receipt','lineIndex','identity','source']),item+' receipt identity attribution and multiplicity')
         ck(got.get('token')==e['token'] and got.get('metricType')=='g' and equal(got.get('parsedValue'),e['parsedValue']),item+' intact lexical token type and numeric parse')
         ck(equal(got.get('before'),e['before']) and equal(got.get('value'),e['value']),item+' native gauge state transition under epoch-active update mode')
         ck(isinstance(got.get('ageMs'),(int,float)) and 0<=got['ageMs']<=1000,item+' public one-second processing bound')
        ck(set(a['state'])==set(want) and all(equal(a['state'].get(k),v) for k,v in want.items()),prefix+' complete native-unit state')
        # The unsigned absolute relay stream is a protected healthy control even when signed update semantics fail.
        healthy=profile['identities'][2];healthy_events=[e for e in events if e['identity']==healthy];actual_healthy=[e for e in a['history'] if e['identity']==healthy]
        ck(len(actual_healthy)==len(healthy_events) and all(equal(g.get('value'),e['value']) for g,e in zip(actual_healthy,healthy_events)),prefix+' healthy unsigned relay stream')
        # Every currently-absolute endpoint is a protected control: repeated identical signed readings stay stable in this epoch.
        snapshot_sources={f['id'] for f in PLAN['fleet'] if active(f['provisioning'],at)['gauge_update_mode']=='absolute-reading'}
        snapshot_ids={e['identity'] for e in events if e['source'] in snapshot_sources}
        actual_snapshot=[g for g in a['history'] if g.get('identity') in snapshot_ids]
        snapshot_events=[e for e in events if e['identity'] in snapshot_ids]
        ck(len(actual_snapshot)==len(snapshot_events) and all(equal(g.get('value'),e['value']) for g,e in zip(actual_snapshot,snapshot_events)),prefix+' snapshot-channel readings stored as published this epoch')
        # Per provisioned endpoint: the epoch-active update mode must hold for every stream that endpoint feeds.
        for f in PLAN['fleet']:
         src_events=[e for e in events if e['source']==f['id']]
         actual_src=[g for g in a['history'] if g.get('source')==f['id']]
         ck(len(actual_src)==len(src_events) and all(equal(g.get('value'),e['value']) and equal(g.get('before'),e['before']) for g,e in zip(actual_src,src_events)),prefix+' epoch-active update mode holds for endpoint '+f['id'])
        ck([(p['id'],p['channel']) for p in a['producers']]==[(f['id'],active(f['provisioning'],at)['channel']) for f in PLAN['fleet']],prefix+' runtime inventory publishes the epoch-active channel per endpoint')
        public=fetch(url+'/api/snapshot');ck(public['state']==a['state'] and public['history']==a['history'] and public['receipts']==a['receipts'],prefix+' public diagnostics reflect actual receipt sink')
        ck(public.get('producers')==a.get('producers'),prefix+' fleet inventory served through public console data')
        ck('writer' not in public and 'transportErrors' not in public and 'archive' not in public and 'fleetProvisioning' not in public and 'activeProvisioning' not in public,prefix+' protected writer intent and provisioning record excluded from public data')
        ck(all(set(p)=={'id','label','channel','endpoint'} for p in public['producers']),prefix+' producer cards expose only public inventory fields')
        ck('gauge_update_mode' not in json.dumps(public) and 'signed-delta' not in json.dumps(public) and 'absolute-reading' not in json.dumps(public),prefix+' no machine-readable update-mode field on any public surface')
        body_text=page.locator('body').inner_text()
        active_channels={active(f['provisioning'],at)['channel'] for f in PLAN['fleet']}
        all_channels={entry['channel'] for f in PLAN['fleet'] for entry in f['provisioning']}
        ck(all(f['label'] in body_text and active(f['provisioning'],at)['channel'] in body_text for f in PLAN['fleet']),prefix+' epoch-active fleet inventory visible on operator console')
        ck(all(channel not in body_text for channel in sorted(all_channels-active_channels)),prefix+' channels retired by the rollout absent from operator console')
        ck(('Epoch '+str(at)) in body_text,prefix+' session epoch visible on operator console')
        bulletin=PLAN['fleet_bulletin']
        ck(public.get('bulletin')==bulletin,prefix+' provisioning bulletin served through public console data')
        ck(bulletin in body_text,prefix+' provisioning bulletin visible on operator console')
        neutral=['delta','relative','increment','adjust','snapshot','absolute','direct','reading','report','level','relay','sweep','census','statsd','gateway','publish','event','recorder','shift']
        inventory=' '.join(p['label']+' '+p['channel'] for p in a['producers']).lower()
        ck(all(term not in inventory for term in neutral),prefix+' inventory wording semantically neutral about update mode')
        # Behavioral calibration: the channel self-check is the only public mode evidence.
        for f in PLAN['fleet']:
         mode=active(f['provisioning'],at)['gauge_update_mode']
         src_events=[e for e in events if e['source']==f['id']]
         head=src_events[:3]
         calibrated=(len(head)==3 and len({e['identity'] for e in head})==1
          and head[0]['token'][0] in '+-' and head[1]['token'][0] in '+-' and head[2]['token'][0] not in '+-'
          and head[2]['parsedValue']==(head[0]['parsedValue']+head[1]['parsedValue'] if mode=='signed-delta' else head[1]['parsedValue'])
          and head[0]['parsedValue']+head[1]['parsedValue']!=head[1]['parsedValue']
          and all(e['identity']!=head[0]['identity'] for e in src_events[3:]))
         ck(calibrated,prefix+' channel self-check opens the epoch and settles to the endpoint register for '+f['id'])
         actual_head=[g for g in a['history'] if g.get('source')==f['id']][:3]
         ck(len(head)==3 and len(actual_head)==3 and all(g.get('identity')==head[0]['identity'] for g in actual_head),prefix+' channel self-check precedes ordinary traffic in the sink for '+f['id'])
        opening=[e for e in events if e['source']==PLAN['fleet'][0]['id']][:3]
        ck(all(f"{e['identity']}:{e['token']}|g" in body_text for e in opening),prefix+' opening channel-check pulses and settle visible in the datagram capture')
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
       page.locator('[data-action=run]').click();second=grade('rollout-replay',3)
       page.locator('[data-action=run]').click();third=grade('rollout-repeat',4)
       ck([(h['identity'],h['value']) for h in second['history']]==[(h['identity'],h['value']) for h in third['history']],label+' deterministic post-rollout replay')
       ck([(h['identity'],h['value']) for h in first['history']]!=[(h['identity'],h['value']) for h in second['history']],label+' rollout epochs graded as distinct runtime states')
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
