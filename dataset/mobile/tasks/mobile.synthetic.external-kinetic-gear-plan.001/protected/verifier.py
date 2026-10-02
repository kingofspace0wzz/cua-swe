"""Trusted user-visible oracle. No candidate source, JS values or storage reads."""
import asyncio, io, json, math, re, time
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from playwright.async_api import TimeoutError as UITimeout
# Independent author transcription of the drawings; NOT an external inbox field.
EDGES=[(1,2,'mesh'),(2,3,'axis'),(3,4,'mesh'),(4,5,'mesh'),(5,6,'axis'),(6,9,'crossed belt'),(9,10,'axis'),(10,11,'mesh'),(11,12,'mesh'),(3,7,'mesh'),(7,8,'mesh'),(8,13,'mesh'),(13,14,'axis'),(14,15,'mesh'),(14,16,'mesh'),(16,17,'mesh'),(6,18,'open belt'),(18,19,'axis'),(19,20,'mesh'),(20,21,'mesh'),(8,22,'mesh'),(22,23,'axis'),(23,24,'mesh')]
FIELDS=['Driving relation','Signed ratio','Phase','Unwrapped angle','Wrapped angle','Direction']

def number(text):
    value=text.strip().replace('−','-').replace('°','').replace('degrees','').strip()
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\s*/\s*[+-]?\d+(?:\.\d*)?)?',value):raise ValueError('not a displayed numeric value')
    bits=value.split('/');n=float(Fraction(bits[0].strip()))
    if len(bits)==2:n/=float(Fraction(bits[1].strip()))
    if not math.isfinite(n):raise ValueError('nonfinite display')
    return n

def parse_report(text):
    """Fields are scoped to a single Component block, and label anchored.
    Accepts div/section/article/list markup, line-separated label/value pairs,
    rational numbers and decimal numbers; rejects duplicate/missing fields.
    """
    heads=list(re.finditer(r'(?m)^\s*Component\s+(W\d{2})\b[^\n]*',text));result={}
    for i,h in enumerate(heads):
        key=h.group(1)
        if key in result:raise ValueError('duplicate component')
        body=text[h.end():heads[i+1].start() if i+1<len(heads) else len(text)]
        marks=list(re.finditer(r'(?mi)^\s*('+ '|'.join(FIELDS)+r')\s*:\s*',body))
        fields={}
        for j,m in enumerate(marks):
            label=m.group(1).lower()
            if label in fields:raise ValueError('duplicate field')
            fields[label]=body[m.end():marks[j+1].start() if j+1<len(marks) else len(body)].strip()
        if set(fields)!={x.lower() for x in FIELDS}:raise ValueError('incomplete state')
        rel=fields['driving relation'].lower()
        if re.fullmatch(r'driver\s*\(none\)',rel):parent=None;kind='driver'
        else:
            r=re.fullmatch(r'(w\d{2})\s*/\s*(external mesh|mesh|common axis|rigid common axis|axis|open belt|crossed belt)',rel)
            if not r:raise ValueError('incomplete immediate relation')
            parent=r.group(1).upper();kind={'external mesh':'mesh','common axis':'axis','rigid common axis':'axis'}.get(r.group(2),r.group(2))
        direction=fields['direction'].lower().replace('counter-clockwise','counterclockwise')
        if direction not in ('clockwise','counterclockwise'):raise ValueError('missing direction')
        result[key]={'parent':parent,'kind':kind,'ratio':number(fields['signed ratio']),'phase':number(fields['phase']),'angle':number(fields['unwrapped angle']),'wrapped':number(fields['wrapped angle']),'direction':direction}
    if not result:raise ValueError('no complete components')
    return result

def oracle(edition,D=0,phases=None):
    # Iterative edge expansion, exact rational arithmetic; unlike client recursive floats.
    parts={int(c['id'][1:]):c for c in edition['components']}
    phase={n:Fraction(str((phases or {}).get(c['id'],c['phase']))) for n,c in parts.items()}
    values={1:{'parent':None,'kind':'driver','ratio':Fraction(1),'phase':phase[1],'angle':Fraction(str(D))+phase[1]}}
    pending=list(reversed(EDGES))
    while pending:
        progress=False
        for e in pending[:]:
            a,b,k=e
            if a not in values:continue
            factor=Fraction(1) if k=='axis' else Fraction(parts[a]['size'],parts[b]['size'])*(1 if k=='open belt' else -1)
            values[b]={'parent':f'W{a:02}','kind':k,'ratio':values[a]['ratio']*factor,'phase':phase[b],'angle':values[a]['angle']*factor+phase[b]}
            pending.remove(e);progress=True
        if not progress:raise RuntimeError('invalid trusted reference DAG')
    result={}
    for n,v in values.items():
        v['wrapped']=v['angle']%360;v['direction']='clockwise' if v['ratio']>0 else 'counterclockwise'
        result[f'W{n:02}']={k:float(x) if isinstance(x,Fraction) else x for k,x in v.items()}
    return result

def equal(actual,expected):
    if actual.keys()!=expected.keys():return False
    for key in expected:
        for field,want in expected[key].items():
            have=actual[key].get(field)
            if isinstance(want,(int,float)):
                if not isinstance(have,(int,float)) or abs(have-want)>0.0011:return False
            elif have!=want:return False
    return True

def image_distance(a,b):
    def normalized(raw):return Image.open(io.BytesIO(raw)).convert('RGB').resize((96,132),Image.Resampling.LANCZOS)
    return sum(ImageStat.Stat(ImageChops.difference(normalized(a),normalized(b))).mean)/3

async def grade(page,ctx):
    if not ctx.get('baseline') or ctx['baseline']['capture_kind']!='native_hook_pre_edit':
        raise RuntimeError('missing actual pre-edit reference: infrastructure-invalid')
    started=time.monotonic();out=Path(ctx['output_dir']);editions=ctx['fixture']['inbox']['editions'];events=[];results=[]
    page.set_default_timeout(800)
    async def click(name):await page.get_by_role('button',name=name,exact=True).click()
    async def edition(e):await page.get_by_label('Edition',exact=True).select_option(e['id'])
    async def preview():await click('Preview')
    async def reset():
        await preview()
        if await page.get_by_role('button',name='Cancel phase',exact=True).is_visible():await click('Cancel phase')
        await click('Reset')
    async def report(e,D=0,phases=None):
        await click('State report')
        raw=await page.get_by_role('region',name='State report',exact=True).inner_text()
        try:actual=parse_report(raw)
        except (ValueError,ZeroDivisionError):return False
        wanted=oracle(e,D,phases);passed=equal(actual,wanted)
        events.append({'edition':e['id'],'D':D,'phases':phases or {},'complete_states':actual,'passed':passed})
        return passed
    async def angle(D):
        await preview();await page.get_by_label('Driver angle (degrees)',exact=True).fill(str(D));await click('Apply angle')
    async def phase(part,value,commit=True):
        await page.get_by_label('Component',exact=True).select_option(part);await click('Edit phase');await page.get_by_label('Phase draft (degrees)',exact=True).fill(str(value))
        if commit:await click('Save phase')
    async def picture():
        await preview();return await page.get_by_role('region',name='Mechanism preview',exact=True).screenshot()
    async def group(key,fn):
        t=time.monotonic()
        try:passed=bool(await fn())
        except (UITimeout,AssertionError,ValueError,ZeroDivisionError) as exc:
            passed=False;events.append({'group':key,'visible_failure':type(exc).__name__,'detail':str(exc)[:350]})
        # Crashes, setup, browser protocol and other unexpected exceptions propagate as infrastructure-invalid.
        results.append({'id':key,'passed':passed});events.append({'group':key,'seconds':time.monotonic()-t})
    async def all_editions():
        ok=True
        for e in editions:
            await edition(e);await reset();ok=(await report(e)) and ok
        return ok
    async def driver_motion():
        e=editions[0];await edition(e);await reset();before=await picture()
        await angle(137.5);after=await picture();ok=image_distance(before,after)>0.15 and await report(e,137.5)
        await angle(-211.25);ok=(await report(e,-211.25)) and ok
        await preview();await page.get_by_label('Step direction',exact=True).select_option('-1');await click('Step');ok=(await report(e,-226.25)) and ok
        await preview();await click('Undo');ok=(await report(e,-211.25)) and ok
        # Slider uses a real focused keyboard step, not DOM state mutation.
        await preview();slider=page.get_by_label('Driver slider',exact=True);await slider.focus()
        await page.keyboard.press('ArrowRight');D=float(await page.get_by_label('Driver angle (degrees)',exact=True).input_value())
        ok=(-212<D<-208) and (await report(e,D)) and ok
        await preview();await click('Play');await asyncio.sleep(.57);await click('Pause');played=float(await page.get_by_label('Driver angle (degrees)',exact=True).input_value())
        steps=(D-played)/15;ok=(1<=steps<=3 and abs(steps-round(steps))<1e-6) and (await report(e,played)) and ok
        stable1=await picture();await asyncio.sleep(.12);stable2=await picture();ok=image_distance(stable1,stable2)<0.02 and ok
        (out/'wheels-before.png').write_bytes(before);(out/'wheels-after.png').write_bytes(after)
        return ok
    async def draft_cancel():
        e=editions[0];await edition(e);await reset();await angle(92.5);before=await picture()
        await phase('W03',37.5,False);draft_picture=await picture();ok=await report(e,92.5,{'W03':37.5})
        # Inspector parses the same semantic fields but is independently rendered.
        selected=parse_report(await page.get_by_role('region',name='Selected component state',exact=True).inner_text())
        want={'W03':oracle(e,92.5,{'W03':37.5})['W03']};ok=equal(selected,want) and image_distance(before,draft_picture)>0.08 and ok
        await click('Cancel phase');ok=(await report(e,92.5)) and ok
        await preview();await click('Undo');ok=(await report(e,0)) and ok
        return ok
    async def save_reload():
        e=editions[0];await edition(e);await reset();await phase('W03',17.25);await phase('W14',-33.5)
        ok=await report(e,0,{'W03':17.25,'W14':-33.5})
        await preview();await click('Undo');ok=(await report(e,0,{'W03':17.25})) and ok
        await phase('W14',-33.5);await angle(-123.75)
        await phase('W22',123,False);await page.reload(wait_until='load')
        ok=(await report(e,-123.75,{'W03':17.25,'W14':-33.5})) and ok
        await preview();ok=(await page.get_by_label('Step direction',exact=True).input_value()=='-1') and ok
        return ok
    async def edition_persistence():
        e,f=editions[:2];saved={'W03':17.25,'W14':-33.5}
        await edition(f);await reset();await angle(405.5);await phase('W19',-27.25)
        ok=await report(f,405.5,{'W19':-27.25})
        await phase('W10',111,False);await edition(e);ok=(await report(e,-123.75,saved)) and ok
        await reset();ok=(await report(e)) and ok
        await preview();await click('Undo');ok=(await report(e,-123.75,saved)) and ok
        await reset();await page.reload(wait_until='load');ok=(await report(e)) and ok
        await edition(f);ok=(await report(f,405.5,{'W19':-27.25})) and ok
        # Edition two also gets an independent negative angle and a driver-phase edit.
        await angle(-77.5);await phase('W01',-18.25);ok=(await report(f,-77.5,{'W19':-27.25,'W01':-18.25})) and ok
        return ok
    async def originals():
        ok=True;refs=ctx['baseline']['state']['originals']
        for e in editions:
            await edition(e);await click('Guide');text=await page.get_by_role('heading',name='Maker guide',exact=True).inner_text();ok=bool(text) and ok
            await click('Originals')
            for i,s in enumerate(e['sheets']):
                await page.get_by_label('Drawing sheet',exact=True).select_option(str(i));await click('Fit')
                pic=page.get_by_role('img',name=s['title']+' — original maker attachment',exact=True)
                raw=await pic.screenshot();reference=(Path(ctx['baseline_dir'])/refs[f'{e["id"]}-{i}']).read_bytes()
                ok=image_distance(raw,reference)<1.5 and ok
            # Zoom then Fit uses normal product controls; comparison is framing independent.
            await click('Zoom in');await click('Zoom in');await click('Fit')
        return ok
    for key,fn in [('complete_both_editions',all_editions),('driver_reverse_step_motion',driver_motion),('phase_draft_cancel',draft_cancel),('saved_phases_undo_reload',save_reload),('edition_reset_independence',edition_persistence),('originals_preserved_accessible',originals)]:await group(key,fn)
    (out/'visible-observations.json').write_text(json.dumps({'events':events,'hook_seconds':time.monotonic()-started},indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':results}
