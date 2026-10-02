"""Private behavioral oracle. No client imports, DOM drawing internals or storage reads.
Math implements the received finite contract. Screenshots sample visible colors/marks;
ordinary controls and readable receipts establish inverse edits and persistence.
"""
from pathlib import Path
import json, math, re, io
from PIL import Image

def solve(a,b):
    m=[list(map(float,r))+[float(v)] for r,v in zip(a,b)]; n=len(b)
    for i in range(n):
        k=max(range(i,n),key=lambda k:abs(m[k][i]));m[i],m[k]=m[k],m[i]
        d=m[i][i]
        if abs(d)<1e-13:raise ValueError('invalid external calibration')
        m[i]=[v/d for v in m[i]]
        for j in range(n):
            if j!=i:
                d=m[j][i];m[j]=[v-d*w for v,w in zip(m[j],m[i])]
    return [r[-1] for r in m]
def fit(pairs):
    a=[];b=[]
    for (x,y),(u,v) in pairs:
        a.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);b.extend([u,v])
    return solve(a,b)+[1.]
def project(h,p):
    x,y=p;d=h[6]*x+h[7]*y+h[8]
    return [(h[0]*x+h[1]*y+h[2])/d,(h[3]*x+h[4]*y+h[5])/d]
def inside(p,poly):
    x,y=p;yes=False
    for (ax,ay),(bx,by) in zip(poly,poly[1:]+poly[:1]):
        cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax)
        if abs(cross)<1e-5 and min(ax,bx)-1e-7<=x<=max(ax,bx)+1e-7 and min(ay,by)-1e-7<=y<=max(ay,by)+1e-7:return True
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:yes=not yes
    return yes
def near(a,b,t=.035):return a is not None and b is not None and all(abs(x-y)<=t for x,y in zip(a,b))
def rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))
def average(poly):return [sum(p[i] for p in poly)/len(poly) for i in (0,1)]

class Office:
    def __init__(self,p):
        self.p=p;self.report=next(a['data'] for a in p['attachments'] if a['kind']=='registration-report')
        self.f=self.report['stationFrame'];self.by={r['panelId']:r for r in self.report['panels']}
        self.h={};self.reverse={}
        for key,r in self.by.items():
            self.h[key]=fit([(c['local'],c['station']) for c in r['controls']])
            self.reverse[key]=fit([(c['station'],c['local']) for c in r['controls']])
    def local(self,pid,source):
        r=self.by[pid];x,y,w,h=r['sourceWindow'];u,v=(source[0]-x)/w,(source[1]-y)/h
        if r['orientation']['reflectU']:u=1-u
        for _ in range(r['orientation']['quarterTurnsClockwise']%4):u,v=1-v,u
        return [u,v]
    def station(self,pid,source):return project(self.h[pid],self.local(pid,source))
    def wall(self,pid,source):
        e,n=self.station(pid,source);f=self.f;s=f['stationUnitsPerWallUnit']
        return [(e-f['originEast'])/s,f['wallHeight']-(n-f['originNorth'])/s]
    def source(self,pid,wall):
        f=self.f;s=f['stationUnitsPerWallUnit'];station=[wall[0]*s+f['originEast'],(f['wallHeight']-wall[1])*s+f['originNorth']]
        u,v=project(self.reverse[pid],station);r=self.by[pid]
        for _ in range(r['orientation']['quarterTurnsClockwise']%4):u,v=v,1-u
        if r['orientation']['reflectU']:u=1-u
        x,y,w,h=r['sourceWindow'];return [x+u*w,y+v*h]
    def in_source(self,pid,p):
        x,y,w,h=self.by[pid]['sourceWindow'];return x-1e-7<=p[0]<=x+w+1e-7 and y-1e-7<=p[1]<=y+h+1e-7
    def visible(self,panel,w):return inside(w,panel['displayPolygon']) and not any(inside(w,h) for h in panel['obstructions'])
    def owner(self,w):
        for pid in self.report['seamPriority']:
            p=next(p for p in self.p['panels'] if p['id']==pid)
            if self.visible(p,w) and self.in_source(pid,self.source(pid,w)):return pid
        return None
    def color(self,w):
        color='#edf0f5'
        for p in self.p['panels']:
            pid=p['id']
            if self.visible(p,w):
                source=self.source(pid,w)
                if self.in_source(pid,source):
                    for shape in self.p['artwork']['shapes']:
                        if inside(source,shape['points']):color=shape['color']
            if any(inside(w,h) for h in p['obstructions']):color='#a7aeb8'
        return rgb(color)
    def safe_source(self,pid,offset=0):
        x,y,w,h=self.by[pid]['sourceWindow'];choices=[]
        for u,v in [(.62,.32),(.34,.64),(.72,.66),(.26,.28),(.5,.78),(.72,.24)]:
            source=[x+u*w,y+v*h];pt=self.wall(pid,source)
            if all(self.owner([pt[0]+dx,pt[1]+dy])==pid for dx,dy in [(0,0),(-12,0),(12,0),(0,-12),(0,12)]):choices.append(source)
        if not choices:raise ValueError('fixture has no safe edit point')
        return choices[offset%len(choices)]
    def seam(self):
        a,b=self.p['panels'];shared=[p for p in a['displayPolygon'] if any(near(p,q,1e-6) for q in b['displayPolygon'])]
        if len(shared)!=2:raise ValueError('expected disclosed adjacent seam')
        w=average(shared)
        if self.owner(w) is None:raise ValueError('invalid fixture seam')
        return w
    def samples(self):
        pins=[self.wall(p['panelId'],p['source']) for p in self.p['pins']];samples=[]
        for y in range(10,291,10):
            for x in range(10,351,10):
                if any(math.dist([x,y],pin)<15 for pin in pins):continue
                c=self.color([x,y])
                if all(self.color([x+dx,y+dy])==c for dx,dy in [(-4,0),(4,0),(0,-4),(0,4),(-3,-3),(3,3)]):samples.append((x,y,c))
        return samples

async def grade(page,ctx):
    if not ctx['baseline'] or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':raise RuntimeError('Missing native pre-edit reference')
    page.set_default_timeout(850)
    out=Path(ctx['output_dir']);events=[]
    good={k:True for k in ctx['expected_assertions']}
    def check(k,value,detail):good[k]=good[k] and bool(value);events.append({'group':k,'passed':bool(value),'detail':detail})
    async def click(name):
        b=page.get_by_role('button',name=name,exact=True)
        if await b.count()!=1 or not await b.is_visible() or not await b.is_enabled():return False
        await b.click();return True
    async def fill(label,value):
        f=page.get_by_label(label,exact=True)
        if await f.count()!=1 or not await f.is_visible():return False
        await f.fill(str(value));return True
    async def text():return await page.locator('body').inner_text()
    async def selected():
        t=await text();s=re.search(r'Source x:\s*([-\d.]+)\s*·\s*y:\s*([-\d.]+)',t);w=re.search(r'Wall x:\s*([-\d.]+)\s*·\s*y:\s*([-\d.]+)',t);p=re.search(r'Panel:\s*([^\n]+)',t)
        return {'source':[float(v) for v in s.groups()] if s else None,'wall':[float(v) for v in w.groups()] if w else None,'label':p.group(1).strip() if p else None}
    def matches(state,oracle,pid,source,tolerance=.035):
        label=next(p['label'] for p in oracle.p['panels'] if p['id']==pid)
        return state['label']==label and near(state['source'],source,tolerance) and near(state['wall'],oracle.wall(pid,source),tolerance)
    async def place(domain,point):
        a=await fill(domain+' X',point[0]);b=await fill(domain+' Y',point[1]);c=await click('Place '+domain.lower()+' coordinates');return a and b and c
    async def picture(name):
        image=page.get_by_role('img',name='Wall preview',exact=True)
        if await image.count()!=1 or not await image.is_visible():return None,None
        await image.scroll_into_view_if_needed();box=await image.bounding_box()
        raw=await image.screenshot();(out/name).write_bytes(raw)
        return Image.open(io.BytesIO(raw)).convert('RGB'),box
    def pixel(image,pt,oracle):
        x=min(image.width-1,max(0,int(pt[0]*image.width/oracle.p['wall']['width'])))
        y=min(image.height-1,max(0,int(pt[1]*image.height/oracle.p['wall']['height'])))
        return image.getpixel((x,y))
    async def mark(oracle,pid,source,name):
        im,_=await picture(name)
        if im is None:return False
        center=oracle.wall(pid,source)
        # A selected mark must be visible at the actual mapped location, not merely
        # a correct textual readout. Allow alternate DOM/SVG/canvas implementations.
        colors=[pixel(im,[center[0]+dx,center[1]+dy],oracle) for dx in range(-12,13) for dy in range(-12,13)]
        purple=sum(1 for r,g,b in colors if 70<r<180 and g<110 and b>r*1.15)
        black=sum(1 for r,g,b in colors if max(r,g,b)<65)
        white=sum(1 for r,g,b in colors if min(r,g,b)>235)
        return purple>=15 and black>=15 and white>=3
    async def tap(oracle,point):
        image=page.get_by_role('img',name='Wall preview',exact=True)
        if await image.count()!=1:return False
        await image.scroll_into_view_if_needed();b=await image.bounding_box()
        if not b:return False
        await page.mouse.click(b['x']+point[0]*b['width']/oracle.p['wall']['width'],b['y']+point[1]*b['height']/oracle.p['wall']['height']);return True
    saved_states=[]
    for index,p in enumerate(ctx['fixture']['inbox']):
        o=Office(p);key=p['id'];opened=await click(p['title'])
        check('external_evidence_access',opened,{'packet':key,'open':opened})
        # Diagnose independently of plan import: every received artifact is reachable.
        evidence=await click('Received packet')
        evidence=await click('Received provider guide') and evidence
        evidence=('Projection Office v2' in await text()) and evidence
        evidence=await click('Registration report') and evidence
        evidence=('Station frame and ownership' in await text()) and evidence
        for title in ('Source artwork','Intended projection plate'):
            evidence=await click(title) and evidence
            img=page.get_by_role('img',name=title,exact=True)
            evidence=(await img.count()==1 and await img.is_visible()) and evidence
            if await img.count()==1 and await img.is_visible():await img.screenshot(path=str(out/f'{key}-{title.replace(" ","-")}.png'))
        check('external_evidence_access',evidence,{'packet':key,'received_documents':evidence})
        await click('Plan')
        im,_=await picture(f'{key}-initial-wall.png');samples=o.samples();bad=[]
        if im is not None:
            for x,y,c in samples:
                observed=pixel(im,[x,y],o)
                if max(abs(a-b) for a,b in zip(c,observed))>28:bad.append([x,y,c,observed])
        check('projective_artwork_and_clipping',im is not None and len(samples)>150 and len(bad)<=max(3,int(len(samples)*.015)),{'packet':key,'samples':len(samples),'mismatches':bad[:40],'mismatch_count':len(bad)})
        for pin in p['pins']:
            await click('Select '+pin['label']);s=await selected()
            check('pin_roundtrip_and_selection',matches(s,o,pin['panelId'],pin['source']) and await mark(o,pin['panelId'],pin['source'],f'{key}-{pin["label"]}-mark.png'),{'packet':key,'received_pin':pin['label'],'observed':s})
        await click('Select Start');first,second=p['panels'];src=o.safe_source(first['id']);await place('Source',src)
        check('pin_roundtrip_and_selection',matches(await selected(),o,first['id'],src),{'packet':key,'source_move':await selected()})
        other_src=o.safe_source(second['id']);target=o.wall(second['id'],other_src)
        await place('Wall',target)
        check('pin_roundtrip_and_selection',matches(await selected(),o,second['id'],other_src) and await mark(o,second['id'],other_src,f'{key}-inverse-mark.png'),{'packet':key,'wall_move':await selected()})
        # Exercise actual diagram hit testing as well as exact numeric controls.
        tap_src=o.safe_source(first['id'],1);target=o.wall(first['id'],tap_src);tapped=await tap(o,target)
        check('pin_roundtrip_and_selection',tapped and matches(await selected(),o,first['id'],tap_src,2.0),{'packet':key,'tap':await selected()})
        before=await selected();seam=o.seam();pid=o.owner(seam);seam_src=o.source(pid,seam)
        await place('Wall',seam)
        seam_ok=matches(await selected(),o,pid,seam_src)
        accepted=await selected();reject_ok=True
        for invalid in [average(first['obstructions'][0]),[-10,50],[5,5]]:
            await place('Wall',invalid);reject_ok=reject_ok and await selected()==accepted and 'Rejected:' in await text()
        window=o.by[pid]['sourceWindow']
        await place('Source',[window[0]-3,window[1]+window[3]/2])
        reject_ok=reject_ok and await selected()==accepted and 'Rejected:' in await text()
        await click('Undo');undo_ok=await selected()==before
        check('ownership_and_rejection',seam_ok and reject_ok and undo_ok,{'packet':key,'seam_owner':pid,'seam':accepted,'invalid_unchanged':reject_ok,'undo_ignores_rejections':undo_ok})
        # Save a nonseam cross-panel inverse edit. Distinct notes expose isolation.
        await place('Wall',o.wall(second['id'],other_src));note='Office check '+str(index+1)
        await fill('Plan note',note);await click('Save plan');saved_state=await selected();saved_states.append((p,o,other_src,note,saved_state))
        await click('Saved receipt');body=await text()
        expected=[('Source',other_src),('Local',o.local(second['id'],other_src)),('Station',o.station(second['id'],other_src))]
        receipt_ok=note in body and ('Panel ID: '+second['id']) in body
        for label,want in expected:
            m=re.search(label+r':\s*([-\d.]+),\s*([-\d.]+)',body)
            receipt_ok=receipt_ok and bool(m) and near([float(v) for v in m.groups()],want)
        # Unselected Finish remains received, including label and precise domains.
        finish=p['pins'][1];tail=body.split('Finish',1)[-1];m=re.search(r'Source:\s*([-\d.]+),\s*([-\d.]+)',tail)
        receipt_ok=receipt_ok and bool(m) and near([float(v) for v in m.groups()],finish['source'])
        check('receipt_serialization',receipt_ok,{'packet':key,'receipt_text':body})
        await click('Plan');await place('Wall',o.wall(first['id'],src));await fill('Plan note','discard me');await click('Cancel edits')
        cancel_ok=await selected()==saved_state
        field=page.get_by_label('Plan note',exact=True);cancel_ok=cancel_ok and await field.count()==1 and await field.input_value()==note
        await place('Wall',o.wall(first['id'],src));await click('Reopen saved');reopen_ok=await selected()==saved_state
        check('save_cancel_packet_isolation',cancel_ok and reopen_ok,{'packet':key,'cancel':cancel_ok,'reopen':reopen_ok})
        await click('Inbox')
    await page.reload(wait_until='load')
    for p,o,source,note,state in saved_states:
        await click(p['title']);await click('Select Start');field=page.get_by_label('Plan note',exact=True)
        isolated=await selected()==state and await field.count()==1 and await field.input_value()==note
        check('save_cancel_packet_isolation',isolated,{'packet':p['id'],'after_reload':await selected(),'isolated':isolated})
        await click('Select Finish');finish=p['pins'][1]
        check('save_cancel_packet_isolation',matches(await selected(),o,finish['panelId'],finish['source']),{'packet':p['id'],'untouched_pin':await selected()})
        await click('Inbox')
    (out/'ui-observations.json').write_text(json.dumps(events,indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':[{'id':k,'passed':bool(good[k])} for k in ctx['expected_assertions']]}
