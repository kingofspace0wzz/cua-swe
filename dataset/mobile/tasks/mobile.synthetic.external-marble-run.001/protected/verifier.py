"""Independent toy-contract oracle + rendered UI checks, never client JS/storage reads.
No DOM tag, source code, private function, color or storage schema is required.
Public-facing names identify controls/regions. Receipts are visible provider JSON.
"""
from pathlib import Path
from io import BytesIO
import json, math, re, time
from PIL import Image, ImageChops
from playwright.async_api import TimeoutError as ActionTimeout

ASSERTIONS=['harbor_motion','orchard_motion','absolute_replay','draft_and_inverse_receipt','independent_saved_tracks','received_evidence_preserved']

def oracle(r,t,edit=None):
    """Direct remaining-time walk (not the client's compiled itinerary)."""
    pts={n['id']:(n['y']/2,r['board']['height']-n['x']/2) for n in r['nodes']}
    base=1/(.8*r['launch']['pace']);release=.4*r['launch']['release']
    if edit:
        base,release=edit['speed'],edit['release'];pts[edit['node']]=(edit['X'],edit['Y'])
    ratio={m['id']:m['ratio'] for m in r['materials']};ev={e['node']:e for e in r['events']}
    material=r['launch']['material'];count=0
    def state(point,speed,phase):return dict(x=point[0],y=point[1],speed=speed,phase=phase,material=material,contacts=count)
    remaining=max(0,t)-release
    if remaining<0:return state(pts[r['route'][0]],0,'Waiting')
    for a,b in zip(r['route'],r['route'][1:]):
        start,end=pts[a],pts[b];duration=math.dist(start,end)*ratio[material]/base
        if remaining < duration-1e-9:
            q=remaining/duration
            return state((start[0]+q*(end[0]-start[0]),start[1]+q*(end[1]-start[1])),base/ratio[material],'Rolling')
        remaining-=duration
        if b in ev:
            e=ev[b];count+=1;material=e['material'];hold=e['hold']*.4
            if remaining<hold-1e-9:return state(end,0,'Contact '+b)
            remaining-=hold
    return state(pts[r['route'][-1]],0,'Finished')

def expected_receipt(r,edit):
    q=json.loads(json.dumps(r))
    q['launch']['pace']=1/(edit['speed']*.8);q['launch']['release']=edit['release']/.4
    for n in q['nodes']:
        if n['id']==edit['node']:n['x']=2*(r['board']['height']-edit['Y']);n['y']=2*edit['X']
    return q

def equivalent(a,b):
    # Record collections are keyed, so a legitimate alternative can reorder them.
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):return False
        if a and isinstance(a[0],dict):
            key='id' if 'id' in a[0] else 'node'
            if all(key in x for x in a+b):
                aa={x[key]:x for x in a};bb={x[key]:x for x in b}
                return len(aa)==len(a) and len(bb)==len(b) and equivalent(aa,bb)
        return all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return math.isclose(a,b,abs_tol=.0006,rel_tol=.0001)
    return a==b

async def grade(page,ctx):
    if not ctx.get('baseline') or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('Infrastructure: required pre-edit native capture missing')
    started=time.monotonic();out=Path(ctx['output_dir']);details=[];results=[]
    page.set_default_timeout(400)
    packets=ctx['fixture']['packets'];a,b=packets[:2];ra,rb=a['record'],b['record']
    def button(name):return page.get_by_role('button',name=name,exact=True)
    async def click(name):
        q=button(name)
        if await q.count()!=1 or not await q.is_visible() or not await q.is_enabled():return False
        try:await q.click(timeout=500);return True
        except ActionTimeout:return False
    async def fill(name,value):
        q=page.get_by_label(name,exact=True)
        if await q.count()!=1 or not await q.is_visible():return False
        try:await q.fill(str(value),timeout=500);return True
        except ActionTimeout:return False
    async def text(region):
        q=page.get_by_role('region',name=region,exact=True)
        return await q.inner_text() if await q.count()==1 and await q.is_visible() else ''
    async def goto(t):return await fill('Replay seconds',t) and await click('Go to time')
    async def check(r,t,edit=None):
        want=oracle(r,t,edit);raw=await text('Replay readout');ok=True;got={}
        for key,label in [('x','X'),('y','Y'),('speed','Speed'),('contacts','Contacts')]:
            m=re.search(r'\b'+label+r'\s*[:=]?\s*(-?\d+(?:\.\d+)?)',raw,re.I)
            got[key]=float(m[1]) if m else None
            ok=ok and got[key] is not None and abs(got[key]-want[key])<.008
        m=re.search(r'\bTime\s*[:=]?\s*(\d+(?:\.\d+)?)',raw,re.I)
        ok=ok and m is not None and abs(float(m[1])-t)<.008
        ok=ok and bool(re.search(r'\b'+re.escape(want['phase'])+r'\b',raw,re.I)) and bool(re.search(r'\b'+re.escape(want['material'])+r'\b',raw,re.I))
        details.append({'record':r['id'],'time':t,'edit':edit,'expected':want,'readout':raw,'passed':bool(ok)})
        return bool(ok)
    async def board():
        # Screenshot the visible board, whether SVG, canvas or a normal container.
        q=page.get_by_label('Track board',exact=True)
        if await q.count()!=1 or not await q.is_visible():return None
        await q.scroll_into_view_if_needed(timeout=500)
        box=await q.bounding_box()
        if not box:return None
        return Image.open(BytesIO(await page.screenshot(clip=box))).convert('RGB')
    def graphical(im0,im1,r,p0,p1):
        if im0 is None or im1 is None or im0.size!=im1.size:return False
        diff=ImageChops.difference(im0,im1);W,H=im0.size
        # Style-independent motion evidence near BOTH the old and new board locations.
        # Does not require a particular DOM/canvas/SVG, color or exact marble radius.
        for p in (p0,p1):
            x=p['x']/r['board']['width']*W;y=p['y']/r['board']['height']*H
            radius=max(9,W*.04);n=0
            for yy in range(max(0,int(y-radius)),min(H,int(y+radius)+1)):
                for xx in range(max(0,int(x-radius)),min(W,int(x+radius)+1)):
                    if max(diff.getpixel((xx,yy)))>35:n+=1
            if n<12:return False
        return True
    async def trajectory(pk,times,photo_time):
        r=pk['record'];ok=await click(pk['title']);ok=(await goto(0)) and ok
        im0=await board()
        for t in times:
            moved=await goto(t);matches=await check(r,t);ok=ok and moved and matches
        await goto(photo_time);im1=await board()
        image_ok=graphical(im0,im1,r,oracle(r,0),oracle(r,photo_time))
        if im1:im1.save(out/(r['id']+'-motion.png'))
        details.append({'graphics':r['id'],'motion_observed':image_ok})
        return ok and image_ok
    async def receipt():
        if not await click('Save receipt'):return None
        raw=await text('Save receipt')
        try:value=json.loads(raw[raw.index('{'):])
        except (ValueError,TypeError):value=None
        await click('Close receipt');return value
    async def edit(e):
        ok=await click('Edit plan')
        # Switching nodes first captures the original numeric controls.
        ok=(await click('Node '+e['node'])) and ok
        for field,key in [('Base speed','speed'),('Release seconds','release'),('Node X','X'),('Node Y','Y')]:ok=(await fill(field,e[key])) and ok
        return ok
    async def group(name,fn):
        # Expected wrong controls/output are explicit false, not generic hook failures.
        # Unexpected fixture/Playwright failures propagate as infrastructure-invalid.
        try:value=await fn()
        except ActionTimeout as exc:
            details.append({'group':name,'visible_action_timeout':str(exc)[:300]});value=False
        results.append({'id':name,'passed':bool(value)})
    async def g1():return await trajectory(a,[0,.5,1,4,7,7.5,8,14,20,20.5,23,25.5,33],4)
    async def g2():return await trajectory(b,[0,.5,1.5,2.5,3,3.25,5.125,7,7.25,8,8.75,12],5.125)
    async def g3():
        ok=await click(a['title']);await goto(14)
        for action,t in [('Reverse',13.5),('Play',14),('Step back',13.5),('Step forward',14),('Reset',0),('Reverse',0)]:
            acted=await click(action);matches=await check(ra,t);ok=ok and acted and matches
        for t in [23,7.5,4]:ok=(await goto(t)) and (await check(ra,t)) and ok
        slider=page.get_by_label('Scrub time',exact=True)
        if await slider.count()!=1:return False
        await slider.focus();await slider.press('ArrowRight')
        return await check(ra,4.125) and ok
    ea=dict(speed=1.6,release=.8,node='B',X=7.5,Y=7.25)
    eb=dict(speed=2.5,release=.2,node='M',X=8.5,Y=4.75)
    async def g4():
        ok=await click(a['title']);ok=await edit(ea) and ok
        ok=await click('Preview draft') and ok;await goto(2.375);ok=await check(ra,2.375,ea) and ok
        ok=await click('Cancel') and ok;ok=await check(ra,2.375) and ok
        ok=await edit(ea) and ok;ok=await click('Save plan') and ok
        got=await receipt();ok=equivalent(got,expected_receipt(ra,ea)) and ok
        for t in [0,3.375,7.625,18.875,30]:await goto(t);ok=await check(ra,t,ea) and ok
        details.append({'receipt':'first edited track','matches_contract':equivalent(got,expected_receipt(ra,ea))})
        return ok
    async def g5():
        ok=await click(b['title']);await goto(5.125);ok=await check(rb,5.125) and ok
        ok=await edit(eb) and ok;ok=await click('Save plan') and ok
        got=await receipt();ok=equivalent(got,expected_receipt(rb,eb)) and ok
        await goto(4.375);ok=await check(rb,4.375,eb) and ok
        # Unsaved draft gets abandoned, not persisted into either plan or receipt.
        unsaved=dict(eb,speed=4.2,X=8.25)
        ok=await edit(unsaved) and ok;ok=await click('Preview draft') and ok
        await page.reload(wait_until='load')
        for pk,r,e,t in [(a,ra,ea,9.375),(b,rb,eb,4.375)]:
            ok=await click(pk['title']) and ok;await goto(t);ok=await check(r,t,e) and ok
            ok=equivalent(await receipt(),expected_receipt(r,e)) and ok
            ok=await click('Reset') and ok;ok=await check(r,0,e) and ok
        return ok
    async def g6():
        ok=True
        for pk in (a,b):
            ok=await click(pk['title']) and ok;ok=await click('Received packet') and ok
            # The immutable received JSON, not app-supplied expected values.
            ok=await click('Record') and ok;raw=await text('Received attachment')
            try:got=json.loads(raw[raw.index('{'):])
            except (ValueError,TypeError):got=None
            ok=equivalent(got,pk['record']) and ok
            ok=await click('Exposures') and ok
            image=page.get_by_role('img',name=re.compile('independent office drawing'))
            ok=(await image.count()==1 and await image.is_visible()) and ok
            raw=await text('Received attachment');ok=pk['exposures'][0]['title'] in raw and ok
            ok=await click('Guide') and ok;raw=await text('Received attachment')
            ok=ctx['fixture']['guide'][0]['title'] in raw and ok
            ok=await click('Back to run') and ok
        return ok
    for name,fn in zip(ASSERTIONS,[g1,g2,g3,g4,g5,g6]):await group(name,fn)
    seconds=time.monotonic()-started
    (out/'ui-observations.json').write_text(json.dumps({'seconds':seconds,'observations':details},indent=2))
    await page.screenshot(path=str(out/'final.png'))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':results}
