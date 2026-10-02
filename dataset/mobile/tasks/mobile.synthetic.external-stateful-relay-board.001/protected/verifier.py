"""Trusted behavioral checks. Oracle transcribed from the illustrated delivered panels.
No candidate source, JS variables or storage are correctness evidence.
"""
import asyncio, io, json, re, time
from pathlib import Path
from PIL import Image

GATES=['A1','A2','A3','B1','B2','B3','C1','C2']
MEM=['Q0','Q1','Q2']; LIGHTS=['Flare','Wash','Pearl']
GROUPS=['delivered_traces','edited_traces','draft_transactions','replay_and_lamps','saved_editions','edition_reset']

def oracle(d):
    u,v,w=d['initial']; result=[]
    for t in range(12):
        tap=int(d['tap'][t]); sweep=int(d['sweep'][t]); even=int(t%2==0 and d['allowEven']); odd=int(t%2==1 and d['allowOdd'])
        # A: rotated MASK's a is the upper gate's output; b is the ribbon.
        merge=tap|w; ribbon=sweep^u; spark=merge & (1-ribbon)
        # B: Spark feeds XOR, Ribbon feeds phase AND, Ember is Q1.D.
        weave=spark^v; latch=ribbon & odd; returned=weave|latch
        # C: Return XOR Loop drives Flare; old Kept/Echo merge drives Wash.
        flare=returned^w; wash=u|v
        nextq=[returned if even else u,merge if odd else v,wash if latch else w]
        result.append({'t':t,'inputs':[tap,sweep,even,odd], 'gates':[merge,ribbon,spark,weave,latch,returned,flare,wash], 'old':[u,v,w], 'next':nextq,'lights':[flare,wash,w]})
        u,v,w=nextq
    return result

def parse_report(text):
    """Readable report parser: grouped bit words or individually labeled bits.
    Uses no required tags/ids, accepts report order changes, whitespace and separators.
    """
    blocks=list(re.finditer(r'(?im)^\s*Tick\s+(\d+)\s*$',text)); out=[]
    for j,m in enumerate(blocks):
        b=text[m.end():blocks[j+1].start() if j+1<len(blocks) else len(text)]
        # Timeline frame headings are not report rows. A complete ledger row has
        # all five disclosed channel headings, regardless of HTML structure.
        if not all(re.search(r'(?im)^\s*'+label+r'\b',b) for label in ['Inputs','Gates','Old','Next','Lights']):
            continue
        row={'t':int(m[1])}
        for key,label,names in [('inputs','Inputs',['Tap','Sweep','E0','E1']),('gates','Gates',GATES),('old','Old',MEM),('next','Next',MEM),('lights','Lights',LIGHTS)]:
            line=re.search(r'(?im)^\s*'+label+r'\b[^\n]*',b)
            if not line:raise ValueError('missing readable '+label)
            s=line[0].strip(); tail=s.split(':',1)[1] if ':' in s else s
            # Named key=value (alternative) or compact word with printed heading (reference).
            values={k:int(v) for k,v in re.findall(r'(Tap|Sweep|E[01]|[ABC][123]|Q[012]|Flare|Wash|Pearl)\s*[=:]\s*([01])\b',tail)}
            if set(names)<=set(values):row[key]=[values[n] for n in names]
            else:
                heading=s.split(':',1)[0]; order=re.findall(r'Tap|Sweep|E[01]|[ABC][123]|Q[012]|Flare|Wash|Pearl',heading)
                bits=re.sub(r'[\s,|]','',tail)
                if set(order)!=set(names) or len(order)!=len(names) or not re.fullmatch('[01]{'+str(len(names))+'}',bits):raise ValueError('ambiguous '+label)
                vals=dict(zip(order,map(int,bits)));row[key]=[vals[n] for n in names]
        out.append(row)
    if len(out)!=12 or sorted(r['t'] for r in out)!=list(range(12)):raise ValueError('incomplete horizon')
    return sorted(out,key=lambda r:r['t'])

def expected_rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))
def lamp_pixels(png,row,colors):
    im=Image.open(io.BytesIO(png)).convert('RGB');w,h=im.size
    for i,bit in enumerate(row['lights']):
        expected=expected_rgb(colors[i] if bit else '#182334')
        x=round(w*(50+100*i)/300);y=round(h/2)
        samples=[im.getpixel((x+dx,y+dy)) for dx,dy in [(0,0),(-2,0),(2,0),(0,-2),(0,2)]]
        if any(max(abs(a-b) for a,b in zip(p,expected))>12 for p in samples):return False
    return True

async def grade(page,ctx):
    if not ctx.get('baseline') or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('infrastructure: missing real pre-edit reference')
    start=time.monotonic(); page.set_default_timeout(700);page.set_default_navigation_timeout(4000)
    records=ctx['fixture']['inbox']['records']; results={k:True for k in GROUPS};events=[]; parser_samples={}
    async def click(name):await page.get_by_role('button',name=name,exact=True).click()
    async def select(r):await page.get_by_label('Show edition',exact=True).select_option(label=r['title'])
    async def report(label,expected):
        # inner_text reads rendered report, not hidden app state; ignores offscreen scroll position.
        text=await page.locator('body').inner_text()
        try:actual=parse_report(text)
        except ValueError as e:events.append({'case':label,'report_error':str(e)});return False
        parser_samples[label]={'visible_text':text,'parsed':actual}
        match=actual==expected
        events.append({'case':label,'trace_match':match,'mismatch_ticks':[a['t'] for a,b in zip(actual,expected) if a!=b]})
        return match
    async def setbit(label,value):await page.get_by_label(label,exact=True).set_checked(bool(value))
    async def scrub(t):
        slider=page.get_by_label('Scrub tick',exact=True)
        # Supported keyboard actions on a visible range, not candidate JS setters.
        await slider.focus();current=int(await slider.input_value())
        for _ in range(abs(t-current)):await slider.press('ArrowRight' if t>current else 'ArrowLeft')
    async def lamp(label,t,r,d):
        await scrub(t)
        loc=page.get_by_role('img',name='Light stage',exact=True)
        await loc.scroll_into_view_if_needed();png=await loc.screenshot(timeout=1500)
        (Path(ctx['output_dir'])/(label+'.png')).write_bytes(png)
        good=lamp_pixels(png,oracle(d)[t],r['colors']);events.append({'case':label,'tick':t,'lamp_pixels_match':good});return good
    async def fields(d):
        for k,label in [('allowEven','Allow even'),('allowOdd','Allow odd')]:
            if await page.get_by_label(label,exact=True).is_checked()!=bool(d[k]):return False
        for i,v in enumerate(d['initial']):
            if await page.get_by_label(f'Initial Q{i}',exact=True).is_checked()!=bool(v):return False
        for key,title in [('tap','Tap'),('sweep','Sweep')]:
            for t,v in enumerate(d[key]):
                if await page.get_by_label(f'{title} tick {t}',exact=True).is_checked()!=bool(v):return False
        return await page.get_by_label('Edition notes',exact=True).input_value()==d['note']
    async def guard(group,fn):
        from playwright.async_api import TimeoutError as UITimeout
        try:await fn()
        except (UITimeout,AssertionError,ValueError) as e:
            # Expected wrong visible behavior is explicit false, not a hook exception.
            results[group]=False;events.append({'group':group,'visible_failure':str(e)[:240]})
    edited={}
    async def delivered():
        for r in records:
            await select(r);results['delivered_traces'] &= await report(r['id']+'-default',oracle(r['defaults']))
        # Input contract must remain reachable; no seed depends on these labels.
        await click('Designer inbox');await click('Guide')
        text=await page.locator('body').inner_text()
        results['delivered_traces'] &= 'simultaneously' in text and 'bridges' in text
        await click('Reference sheets')
        for i in range(3):
            await page.get_by_label('Reference sheet',exact=True).select_option(str(i))
            # Checks only that the product image visibly loaded, not its answer content.
            image=page.locator('img').first
            results['delivered_traces'] &= await image.is_visible() and await image.evaluate('(e)=>e.complete && e.naturalWidth>0')
        await click('Show')
    await guard('delivered_traces',delivered)
    async def edits():
        for idx,r in enumerate(records):
            await select(r);await click('Edit sequence');d=json.loads(json.dumps(r['defaults']))
            # Different changes cover both clock phases and simultaneous feedback.
            d['initial'][1]=1-d['initial'][1];await setbit('Initial Q1',d['initial'][1])
            d['tap'][2]=1-d['tap'][2];await setbit('Tap tick 2',d['tap'][2])
            d['sweep'][3]=1-d['sweep'][3];await setbit('Sweep tick 3',d['sweep'][3])
            d['allowEven']=False if idx==0 else True;d['allowOdd']=True if idx==0 else False
            await setbit('Allow even',d['allowEven']);await setbit('Allow odd',d['allowOdd'])
            results['edited_traces'] &= await report(r['id']+'-phase-edit',oracle(d))
            # Turn phase back on: not an undisclosed special mode.
            d['allowEven']=True;d['allowOdd']=True
            await setbit('Allow even',True);await setbit('Allow odd',True)
            d['note']='Saved rehearsal '+r['id'];await page.get_by_label('Edition notes',exact=True).fill(d['note'])
            results['edited_traces'] &= await report(r['id']+'-feedback-edit',oracle(d))
            # Save a nondefault phase enable as well as inputs/initial/note.
            d['allowEven']=idx!=0;d['allowOdd']=idx==0
            await setbit('Allow even',d['allowEven']);await setbit('Allow odd',d['allowOdd'])
            edited[r['id']]=d;await click('Save')
    await guard('edited_traces',edits)
    async def transactions():
        r=records[0];await select(r);d=edited.get(r['id'],r['defaults']);await click('Edit sequence')
        await setbit('Initial Q2',1-d['initial'][2]);await click('Undo')
        results['draft_transactions'] &= await report('undo',oracle(d)) and await fields(d)
        await setbit('Allow odd',False);await page.get_by_label('Edition notes',exact=True).fill('discard me')
        await click('Cancel');await click('Edit sequence')
        results['draft_transactions'] &= await fields(d) and await report('cancel',oracle(d))
        await click('Cancel')
        # Zero frames are an ordinary disclosed input, not a reset shortcut.
        await click('Edit sequence');zero=json.loads(json.dumps(d))
        zero['tap']=[0]*12;zero['sweep']=[0]*12
        for t in range(12):
            await setbit(f'Tap tick {t}',False);await setbit(f'Sweep tick {t}',False)
        results['draft_transactions'] &= await report('zero-input-draft',oracle(zero))
        await click('Cancel')
    await guard('draft_transactions',transactions)
    async def replay():
        for r in records:
            await select(r);d=edited.get(r['id'],r['defaults'])
            for t in (0,3,7):results['replay_and_lamps'] &= await lamp(r['id']+'-lamp-'+str(t),t,r,d)
            await click('Back');await click('Step')
            results['replay_and_lamps'] &= (await page.get_by_label('Scrub tick',exact=True).input_value())=='7'
            # Verify Back really selected previous row, not merely any button with that name.
            await click('Back')
            png=await page.get_by_role('img',name='Light stage',exact=True).screenshot(timeout=1500)
            results['replay_and_lamps'] &= await page.get_by_label('Scrub tick',exact=True).input_value()=='6' and lamp_pixels(png,oracle(d)[6],r['colors'])
        await scrub(0);await click('Play');await asyncio.sleep(records[-1]['rateMs']/1000+0.09);await click('Pause')
        frozen=await page.get_by_label('Scrub tick',exact=True).input_value();await asyncio.sleep(0.1)
        results['replay_and_lamps'] &= int(frozen)>=1 and frozen==await page.get_by_label('Scrub tick',exact=True).input_value()
    await guard('replay_and_lamps',replay)
    async def saved():
        await page.reload(wait_until='load')
        for r in records:
            await select(r);d=edited.get(r['id'],r['defaults']);await click('Edit sequence')
            results['saved_editions'] &= await fields(d) and await report(r['id']+'-reload',oracle(d))
            await click('Cancel')
        # Unsaved initial/input/note edits must be abandoned on ordinary reload.
        r=records[1];await click('Edit sequence');await setbit('Initial Q0',1-edited.get(r['id'],r['defaults'])['initial'][0]);await page.get_by_label('Edition notes',exact=True).fill('abandoned')
        await page.reload(wait_until='load');await select(r);await click('Edit sequence')
        results['saved_editions'] &= await fields(edited.get(r['id'],r['defaults']));await click('Cancel')
    await guard('saved_editions',saved)
    async def reset():
        await select(records[0]);await click('Reset edition');await page.reload(wait_until='load')
        for idx,r in enumerate(records):
            await select(r);d=r['defaults'] if idx==0 else edited.get(r['id'],r['defaults']);await click('Edit sequence')
            results['edition_reset'] &= await fields(d) and await report(r['id']+'-reset-isolation',oracle(d));await click('Cancel')
        await select(records[1]);await click('Reset edition')
        results['edition_reset'] &= await report('second-reset',oracle(records[1]['defaults']))
    await guard('edition_reset',reset)
    elapsed=time.monotonic()-start
    (Path(ctx['output_dir'])/'observations.json').write_text(json.dumps({'events':events,'hook_seconds':elapsed},indent=2))
    (Path(ctx['output_dir'])/'actual-parser-fixtures.json').write_text(json.dumps(parser_samples,indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':[{'id':k,'passed':bool(results[k])} for k in GROUPS]}
