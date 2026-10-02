"""Behavior-only oracle. No candidate source, JS functions or storage reads.
Dedicated visible report containers; stage-local screenshot differences.
Expected wrong UI is false. Infrastructure faults are not swallowed.
"""
import asyncio,copy,json,math,re,time
from io import BytesIO
from pathlib import Path
from PIL import Image,ImageChops
from playwright.async_api import TimeoutError as PlaywrightTimeout
IDS=['received_registrations','live_pose_draft','identification_draft','complete_save_reload','edition_reset_isolation','evidence_viewer']
NUMBER=r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))'
LEDGER=re.compile(r'\b(P\d+)\s+([A-Za-z]+)\s+'+NUMBER+r'\s+'+NUMBER+r'\b')
TARGET=re.compile(r'\b(T\d+)\s+'+NUMBER+r'\s+'+NUMBER+r'\s+([A-Za-z]+)\s+'+NUMBER+r'\s+'+NUMBER+r'\b')
def parse_ledger(text):
    return [{'id':m[0],'name':m[1],'x':float(m[2]),'y':float(m[3])} for m in LEDGER.findall(text)]
def parse_targets(text):
    return [{'id':m[0],'x':float(m[1]),'y':float(m[2]),'name':m[3],'dx':float(m[4]),'dy':float(m[5])} for m in TARGET.findall(text)]
def project(p,x,y):
    # Independent complex-plane implementation, not the client affine helper.
    z=complex(x-300,y-300)
    if p['mirror']:z=complex(-z.real,z.imag)
    z*=complex(0,1)**p['turn']*p['scale']
    return (z.real+300+p['dx'],z.imag+300+p['dy'])
def invert(p,x,y):
    z=complex(x-300-p['dx'],y-300-p['dy'])/(complex(0,1)**p['turn']*p['scale'])
    if p['mirror']:z=complex(-z.real,z.imag)
    return (z.real+300,z.imag+300)
def expected(reg,record):
    ledger=[];targets=[]
    for p in record['rasterPoints']:
        x,y=invert(reg['pose'],p['x'],p['y'])
        ledger.append({'id':p['id'],'name':next((s['name'] for s in reg['stars'] if s['plate']==p['id']),'Unassigned'),'x':x,'y':y})
    for p in record['rasterTargets']:
        x,y=invert(reg['pose'],p['x'],p['y'])
        for s in sorted(reg['stars'],key=lambda s:(math.hypot(x-s['x'],y-s['y']),s['name']))[:2]:
            targets.append({'id':p['id'],'x':x,'y':y,'name':s['name'],'dx':x-s['x'],'dy':y-s['y']})
    return ledger,targets

def equivalent(actual,want):
    if len(actual)!=len(want):return False
    # Ledger order / target-neighbour row order are not requirements.
    actual=sorted(actual,key=lambda r:(r['id'],r.get('name','')));want=sorted(want,key=lambda r:(r['id'],r.get('name','')))
    for a,b in zip(actual,want):
        for k,v in b.items():
            if isinstance(v,str):
                if a.get(k)!=v:return False
            elif not isinstance(a.get(k),(int,float)) or abs(a[k]-v)>1.5:return False
    return True

def swap(reg,disc,name):
    r=copy.deepcopy(reg);a=next(s for s in r['stars'] if s['plate']==disc);b=next(s for s in r['stars'] if s['name']==name)
    a['plate'],b['plate']=b['plate'],a['plate'];return r

async def grade(page,ctx):
    start=time.monotonic();out=Path(ctx['output_dir']);records=ctx['fixture']['approved'];keys=list(records)
    results={k:False for k in IDS};trace=[];serial=0
    async def click(name):
        loc=page.get_by_role('button',name=name,exact=True)
        if await loc.count()!=1 or not await loc.is_enabled():return False
        try:await loc.click(timeout=650);return True
        except PlaywrightTimeout:return False
    async def choose(label,value):
        loc=page.get_by_label(label,exact=True)
        if await loc.count()!=1 or not await loc.is_enabled():return False
        try:await loc.select_option(str(value),timeout=650);return True
        except PlaywrightTimeout:return False
    async def text_region(name):
        loc=page.get_by_role('region',name=name,exact=True)
        if await loc.count()!=1:return ''
        return await loc.inner_text(timeout=650)
    async def settle_sheet():
        # Bounded observation of attachment readiness; malformed candidates simply fail.
        for _ in range(12):
            if await page.get_by_role('region',name='Plate logical stage',exact=True).count():return True
            await asyncio.sleep(.025)
        return False
    async def edition(key):
        ok=await choose('Observation edition',key)
        await click('Plate');return bool(await settle_sheet() and ok)
    async def report(reg,rec,note=None,label='report'):
        if not await click('Review'):return False
        lt=await text_region('Identification ledger');tt=await text_region('Target measurements')
        l,t=parse_ledger(lt),parse_targets(tt);el,et=expected(reg,rec)
        ok=equivalent(l,el) and equivalent(t,et)
        if note is not None:ok=ok and note in await text_region('Saved notes')
        trace.append({'step':label,'ledger_text':lt,'targets_text':tt,'parsed_ledger':l,'parsed_targets':t,'passed':bool(ok)})
        return bool(ok)
    async def preview(reg,label):
        nonlocal serial
        if not await click('Plate') or not await settle_sheet():return False
        if not await choose('Sheet zoom',1):return False
        if await page.get_by_role('button',name='Hide observation labels',exact=True).count():await click('Hide observation labels')
        if await page.get_by_role('button',name='Hide registration marks',exact=True).count():await click('Hide registration marks')
        stage=page.get_by_role('region',name='Plate logical stage',exact=True)
        if await stage.count()!=1:return False
        try:
            serial+=1
            off=Image.open(BytesIO(await stage.screenshot(path=str(out/f'{serial:02}-{label}-off.png'),timeout=1000))).convert('RGB')
            if not await click('Show registration marks'):return False
            on=Image.open(BytesIO(await stage.screenshot(path=str(out/f'{serial:02}-{label}-on.png'),timeout=1000))).convert('RGB')
        except PlaywrightTimeout:return False
        if off.size!=on.size or min(on.size)<200:return False
        # Normalize all observations to the 600-unit sheet; never assume page origin,
        # viewport framing, canvas/SVG implementation, exact color or decorative labels.
        diff=ImageChops.difference(off,on);w,h=diff.size;mask=set()
        for y in range(h):
            for x in range(w):
                if max(diff.getpixel((x,y)))>40:mask.add((x,y))
        components=[]
        while mask:
            todo=[mask.pop()];pixels=[]
            while todo:
                x,y=todo.pop();pixels.append((x,y))
                for q in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
                    if q in mask:mask.remove(q);todo.append(q)
            if len(pixels)>=3:
                components.append((sum(p[0]+.5 for p in pixels)/len(pixels)*600/w,sum(p[1]+.5 for p in pixels)/len(pixels)*600/h,len(pixels)))
        wanted=[project(reg['pose'],s['x'],s['y']) for s in reg['stars'] if s['plate']]
        # Cropped projections are allowed after deliberate bad-pose draft edits;
        # initial and saved tested registrations also have many interior checks.
        wanted=[p for p in wanted if 12<p[0]<588 and 12<p[1]<588]
        okay=bool(wanted) and all(any(math.dist(p,c[:2])<=3 for c in components) for p in wanted)
        # No static/extra field crosses in the interior (labels explicitly disabled).
        okay=okay and all(any(math.dist(p,c[:2])<=3 for p in wanted) for c in components if 14<c[0]<586 and 14<c[1]<586)
        # Labels are checked as visible text, never by tag or decorative box geometry.
        okay=await click('Show observation labels') and okay
        for star in reg['stars']:
            xy=project(reg['pose'],star['x'],star['y'])
            if star['plate'] and 12<xy[0]<560 and 25<xy[1]<588:
                lab=stage.get_by_text(re.compile(r'^'+re.escape(star['plate'])+r'\s+'+re.escape(star['name'])+r'$'))
                okay=(await lab.count()==1 and await lab.is_visible()) and okay
        await click('Hide observation labels')
        trace.append({'step':label,'overlay_centers':components,'passed':bool(okay)})
        return bool(okay)
    async def snapshot(reg,rec,label,note=None,pixels=True):
        a=await report(reg,rec,note,label);b=await preview(reg,label) if pixels else True;return bool(a and b)

    # 1. Both delivered external records, complete semantic and visible geometry.
    initial=[]
    for key in keys:
        reg=copy.deepcopy(records[key]['registration']);reg['notes']=''
        opened=await edition(key)
        initial.append(opened and await snapshot(reg,records[key],'initial-'+key))
    results['received_registrations']=all(initial)
    key=keys[0];rec=records[key];base=copy.deepcopy(rec['registration']);base['notes']=''
    await edition(key)
    # 2. Live shift, Undo, Cancel, then mounting/reflection/ratio composition.
    ok=await click('Edit registration');ok=await click('Shift right 5') and ok
    shifted=copy.deepcopy(base);shifted['pose']['dx']+=5
    ok=await snapshot(shifted,rec,'shift') and ok
    ok=await click('Undo') and ok;ok=await snapshot(base,rec,'undo-shift',pixels=False) and ok
    ok=await click('Shift up 5') and ok;ok=await click('Cancel') and ok
    ok=await snapshot(base,rec,'cancel-shift',pixels=False) and ok
    ok=await click('Edit registration') and ok
    changed=copy.deepcopy(base);changed['pose'].update(turn=(base['pose']['turn']+1)%4,mirror=not base['pose']['mirror'],scale=.9 if base['pose']['scale']!=.9 else 1.1)
    for control,value in [('Clockwise turn',changed['pose']['turn']),('Emulsion mounting',str(changed['pose']['mirror']).lower()),('Scale ratio',changed['pose']['scale'])]:ok=await choose(control,value) and ok
    ok=await snapshot(changed,rec,'mounting-scale') and ok
    ok=await click('Cancel') and ok;results['live_pose_draft']=bool(ok)
    # 3. One-P exchange, live ledger AND mark movement, reversible draft.
    names=[s for s in base['stars'] if s['plate']];a,b=names[0],names[1]
    exchanged=swap(base,a['plate'],b['name'])
    ok=await click('Edit registration');ok=await choose('Plate observation',a['plate']) and ok
    ok=await choose('Assign finder star',b['name']) and ok;ok=await click('Reassign observation') and ok
    ok=await snapshot(exchanged,rec,'reassignment') and ok
    ok=await click('Undo') and ok;ok=await snapshot(base,rec,'undo-reassignment',pixels=False) and ok
    ok=await choose('Plate observation',a['plate']) and ok
    ok=await choose('Assign finder star',b['name']) and ok;ok=await click('Reassign observation') and ok
    ok=await click('Auto-identify') and ok;ok=await snapshot(base,rec,'auto-identify',pixels=False) and ok
    ok=await click('Undo') and ok;ok=await snapshot(exchanged,rec,'undo-auto',pixels=False) and ok
    ok=await click('Cancel') and ok;results['identification_draft']=bool(ok)
    # 4. Save ALL draft fields, ordinary reload, independent saved edition state.
    saves={};okay=[]
    for index,key in enumerate(keys):
        rec=records[key];state=copy.deepcopy(rec['registration']);state['notes']='Observation checked '+key
        ns=[s for s in state['stars'] if s['plate']];a,b=ns[0],ns[1];state=swap(state,a['plate'],b['name'])
        state['pose']['dx']+=5 if index==0 else -5;state['pose']['turn']=(state['pose']['turn']+1)%4
        state['pose']['mirror']=not state['pose']['mirror'];state['pose']['scale']=1 if state['pose']['scale']!=1 else .9
        good=await edition(key);good=await click('Edit registration') and good
        good=await click('Shift right 5' if index==0 else 'Shift left 5') and good
        for control,value in [('Clockwise turn',state['pose']['turn']),('Emulsion mounting',str(state['pose']['mirror']).lower()),('Scale ratio',state['pose']['scale'])]:good=await choose(control,value) and good
        good=await choose('Plate observation',a['plate']) and good;good=await choose('Assign finder star',b['name']) and good;good=await click('Reassign observation') and good
        notes=page.get_by_label('Observer draft notes',exact=True)
        if await notes.count()==1:
            await notes.fill('Temporary note',timeout=650);await notes.press('Tab',timeout=650)
            good=await click('Undo') and good
            good=((await notes.input_value(timeout=650))=='') and good
            await notes.fill(state['notes'],timeout=650);await notes.press('Tab',timeout=650)
        else:good=False
        good=await click('Save registration') and good;saves[key]=state;okay.append(good)
    await page.reload(wait_until='load')
    for key in keys:
        good=await edition(key);good=await snapshot(saves[key],records[key],'saved-'+key,saves[key]['notes']) and good;okay.append(good)
    results['complete_save_reload']=all(okay)
    # 5. Reset first; saved second survives, reload first restores shipped state.
    key=keys[0];good=await edition(key);good=await click('Reset this edition') and good
    await page.reload(wait_until='load');good=await edition(key) and good
    good=await snapshot(base,records[key],'reset','No notes yet.') and good
    key=keys[1];good=await edition(key) and good
    good=await snapshot(saves[key],records[key],'independent',saves[key]['notes'],pixels=False) and good
    results['edition_reset_isolation']=bool(good)
    # 6. Evidence remains available; actual scale and scroll-pan, not hidden diagnostics.
    good=await edition(keys[0]);stage=page.get_by_role('region',name='Plate logical stage',exact=True)
    fit=await stage.bounding_box() if await stage.count()==1 else None
    good=await choose('Sheet zoom',2) and good
    big=await stage.bounding_box() if await stage.count()==1 else None
    good=good and bool(fit and big and abs(big['width']/fit['width']-2)<.05)
    if big:
        # Use a visible input action; observe movement of the logical sheet bounds.
        viewport=page.get_by_label('Sheet pan area',exact=True);box=await viewport.bounding_box() if await viewport.count()==1 else None
        if box:
            await viewport.scroll_into_view_if_needed(timeout=650);box=await viewport.bounding_box();await page.mouse.move(box['x']+box['width']/2,box['y']+min(100,box['height']/2));before=await stage.bounding_box();await page.mouse.wheel(180,140)
            await asyncio.sleep(.06);after=await stage.bounding_box();good=good and bool(after and (after['x']<before['x']-20 or after['y']<before['y']-20))
        else:good=False
    good=await choose('Sheet zoom',1) and good;good=await click('Finder') and good
    finder=page.get_by_role('region',name='Finder logical stage',exact=True);good=(await finder.count()==1) and good
    good=await click('Guide') and good
    # Guide is an ordinary heading, not an expected registration answer.
    good=(await page.get_by_role('heading',name='Reading the two sheets',exact=True).count()==1) and good
    await click('Plate');results['evidence_viewer']=bool(good)
    duration=time.monotonic()-start
    (out/'visible-parser-fixtures.json').write_text(json.dumps({'source':'actual rendered UI in this native grade','trace':trace},indent=2)+'\n')
    (out/'timing.json').write_text(json.dumps({'grade_seconds':duration,'configured_hook_cap_ms':30000,'headroom_target_seconds':10,'native_certification':'requires positive AND negative controls'})+'\n')
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':[{'id':k,'passed':bool(results[k])} for k in IDS]}
