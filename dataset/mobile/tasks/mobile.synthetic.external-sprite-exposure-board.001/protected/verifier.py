"""Private construction oracle. UI interactions, visible text, and rendered pixels only.
No candidate JS functions, storage reads, source tests, or fixture-reported answers.
"""
import base64, io, json, re, time
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from playwright.async_api import TimeoutError as UITimeout
# APPROVAL is a manually inspectable editorial transcription, not seeded product input.
APPROVAL = {
  "raise": [
    {
      "cel": "rest",
      "facing": "right"
    },
    {
      "cel": "cradle",
      "facing": "right"
    },
    {
      "cel": "offer",
      "facing": "right"
    },
    {
      "cel": "lift-mid",
      "facing": "right"
    },
    {
      "cel": "lamp-high",
      "facing": "right"
    },
    {
      "cel": "look-up",
      "facing": "right"
    },
    {
      "cel": "settle",
      "facing": "right"
    }
  ],
  "cross": [
    {
      "cel": "rest",
      "facing": "left"
    },
    {
      "cel": "stride",
      "facing": "left"
    },
    {
      "cel": "toe-up",
      "facing": "left"
    },
    {
      "cel": "cross-step",
      "facing": "left"
    },
    {
      "cel": "balance",
      "facing": "left"
    },
    {
      "cel": "exit-step",
      "facing": "left"
    },
    {
      "cel": "settle",
      "facing": "left"
    }
  ],
  "catch": [
    {
      "cel": "reach-low",
      "facing": "right"
    },
    {
      "cel": "scoop",
      "facing": "right"
    },
    {
      "cel": "catch-chest",
      "facing": "right"
    },
    {
      "cel": "catch-high",
      "facing": "right"
    },
    {
      "cel": "balance",
      "facing": "right"
    },
    {
      "cel": "kneel",
      "facing": "right"
    },
    {
      "cel": "cradle",
      "facing": "right"
    }
  ],
  "greet": [
    {
      "cel": "hat-touch",
      "facing": "left"
    },
    {
      "cel": "bow-start",
      "facing": "left"
    },
    {
      "cel": "bow-deep",
      "facing": "left"
    },
    {
      "cel": "wave-low",
      "facing": "right"
    },
    {
      "cel": "wave-high",
      "facing": "right"
    },
    {
      "cel": "wave-wide",
      "facing": "right"
    },
    {
      "cel": "salute",
      "facing": "right"
    }
  ]
}


def number(s): return float(s.strip())
def parse_inspector(text):
    """Field-boundary parser: never consumes a following label into a value."""
    labels=['Beat','Cel','Facing','Exposure','Frame','Total','Seconds','FPS']
    pattern=r'(?m)^\s*('+'|'.join(labels)+r')\s*:?\s*\n?([^\n]+?)\s*$'
    result={k:v.strip() for k,v in re.findall(pattern,text)}
    # Inline alternative UI: each field is an ordinary 'Name: value' paragraph.
    return result

def parse_card(text):
    result={k:v.strip() for k,v in re.findall(r'(?m)^\s*(Cel|Facing|Start|End|Exposure):\s*([^\n]+)$',text)}
    beat=re.search(r'(?m)^Beat (\d+)\s*$',text)
    if beat: result['Beat']=int(beat.group(1))
    return result

def expected(clip,settings,t,loop=False):
    spans=[a+b for a,b in zip(settings['exposures'],settings['holds'])]
    length=sum(spans);t=t%length if loop else min(max(0,t),length-1)
    end=0
    for i,n in enumerate(spans):
        start=end;end+=n
        if t<end:return dict(APPROVAL[clip['id']][i],beat=i+1,time=t,start=start,end=end,exposure=n,total=length)
    raise AssertionError('author timing oracle invalid')

def default(clip): return dict(exposures=clip['exposures'][:],holds=clip['holds'][:],start=0,rate=1)
def matches(text,e,fps):
    p=parse_inspector(text)
    try:return (int(p['Beat'].split('/')[0])==e['beat'] and p['Cel']==e['cel'] and p['Facing']==e['facing'] and abs(number(p['Frame'])-e['time'])<.06 and number(p['Exposure'])==e['exposure'] and number(p['Total'])==e['total'] and abs(number(p['FPS'])-fps)<.02 and abs(number(p['Seconds'])-e['time']/fps)<.002)
    except (KeyError,ValueError):return False

def cel_image(edition,pose):
    cel=next(c for c in edition['cels'] if c['id']==pose['cel'])
    sheet=next(s for s in edition['sheets'] if s['id']==cel['sheet'])
    image=Image.open(io.BytesIO(base64.b64decode(sheet['image'].split(',')[1]))).convert('RGB')
    x,y,w,h=cel['rect'];im=image.crop((x,y,x+w,y+h))
    return im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if pose['facing']=='left' else im

def foreground(im):
    """Ignore camera border/background and compare normalized actual artwork.
    Background estimated from a corner; tolerate scaling/framing, not wrong pose/facing.
    """
    im=im.convert('RGB');bg=im.getpixel((min(3,im.width-1),min(3,im.height-1)))
    delta=ImageChops.difference(im,Image.new('RGB',im.size,bg)).convert('L')
    mask=delta.point(lambda x:255 if x>38 else 0)
    # Discard a thin element border (ordinary framing is not a test requirement).
    d=__import__('PIL.ImageDraw',fromlist=['Draw']).Draw(mask)
    d.rectangle((0,0,im.width-1,im.height-1),outline=0,width=max(1,round(min(im.size)*.012)))
    box=mask.getbbox()
    if not box:return None
    return im.crop(box).resize((112,128),Image.Resampling.BILINEAR),mask.crop(box).resize((112,128),Image.Resampling.NEAREST)

def visual_distance(actual,reference):
    a=foreground(actual);b=foreground(reference)
    if a is None or b is None:return (1.,255.)
    am,bm=a[1],b[1];area=sum(1 for x,y in zip(am.getdata(),bm.getdata()) if x or y)
    mismatch=sum(1 for x,y in zip(am.getdata(),bm.getdata()) if bool(x)!=bool(y))/max(1,area)
    diff=ImageChops.difference(a[0],b[0]);color=sum(ImageStat.Stat(diff,ImageChops.darker(am,bm)).mean)/3
    return mismatch,color

def visual_ok(actual,reference):
    shape,color=visual_distance(actual,reference)
    return shape<.14 and color<22

async def grade(page,ctx):
    if not ctx.get('baseline') or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('required pre-edit native reference missing (infrastructure)')
    started=time.monotonic();out=Path(ctx['output_dir']);events=[];rows=[];pixels=[]
    page.set_default_timeout(950)  # wrong/missing UI becomes explicit false, not a 30s hook timeout
    editions=ctx['fixture']['inbox']['editions']
    async def click(n): await page.get_by_role('button',name=n,exact=True).click()
    async def field(n,v):
        el=page.get_by_label(n,exact=True);await el.fill(str(v));await el.press('Tab')
    async def choose(edition,clip):
        await page.get_by_label('Edition',exact=True).select_option(label=edition['label'])
        await page.get_by_label('Clip',exact=True).select_option(label=clip['label'])
    async def seek(t):await field('Frame',t);await click('Scrub')
    async def inspector():return await page.get_by_label('Cel inspector',exact=True).inner_text()
    async def sprite_check(edition,e,tag):
        raw=await page.get_by_label('Current sprite',exact=True).screenshot(animations='disabled')
        im=Image.open(io.BytesIO(raw));ref=cel_image(edition,e);distance=visual_distance(im,ref);ok=visual_ok(im,ref)
        pixels.append({'case':tag,'distance':distance,'passed':ok})
        if not ok: (out/(tag+'.png')).write_bytes(raw)
        return ok
    async def run(name,fn):
        begin=time.monotonic()
        try:ok=bool(await fn())
        except (UITimeout,AssertionError,KeyError,ValueError) as error:
            ok=False;events.append({'group':name,'visible_failure':str(error)[:300]})
        rows.append({'id':name,'passed':ok});events.append({'group':name,'seconds':round(time.monotonic()-begin,3)})
    async def contacts():
        ok=True
        for ed in editions:
            for clip in ed['clips']:
                await choose(ed,clip);await click('Review beats')
                # One screenshot per seven-beat contact sheet; text and sprite targets may be any HTML/SVG/Canvas elements.
                targets=[page.get_by_label(f'Beat {i+1} sprite',exact=True) for i in range(7)]
                boxes=[await t.bounding_box() for t in targets]
                scroll=await page.evaluate('({x:scrollX,y:scrollY})')
                raw=await page.screenshot(full_page=True,animations='disabled');image=Image.open(io.BytesIO(raw))
                (out/f"contact-{ed['id']}-{clip['id']}.png").write_bytes(raw)
                time_at=0
                for i in range(7):
                    e=expected(clip,default(clip),time_at);p=parse_card(await page.get_by_label(f'Beat {i+1} review',exact=True).inner_text())
                    semantic=p.get('Beat')==i+1 and p.get('Cel')==e['cel'] and p.get('Facing')==e['facing'] and all(p.get(k)==str(e[v]) for k,v in [('Start','start'),('End','end'),('Exposure','exposure')])
                    b=boxes[i]
                    if b:
                        x,y=b['x']+scroll['x'],b['y']+scroll['y'];im=image.crop((round(x),round(y),round(x+b['width']),round(y+b['height'])))
                        distance=visual_distance(im,cel_image(ed,e));visual=visual_ok(im,cel_image(ed,e))
                    else:distance=None;visual=False
                    pixels.append({'case':f"{ed['id']}/{clip['id']}/{i+1}",'distance':distance,'passed':visual});ok &= semantic and visual;time_at=e['end']
                await click('Back to animation')
        return ok
    await run('complete_performance_both_editions',contacts)
    async def boundaries():
        ok=True
        for ed in editions:
            clip=ed['clips'][0];s=default(clip);await choose(ed,clip)
            # Exact frame boundary, interior of a held beat, zero, and nonloop end.
            boundary=sum(s['exposures'][:2])+sum(s['holds'][:2])
            for tag,t in [('zero',0),('boundary',boundary),('middle',boundary+1.5),('end',999)]:
                await seek(t);e=expected(clip,s,t);ok &= matches(await inspector(),e,ed['fps']);ok &= await sprite_check(ed,e,ed['id']+'-'+tag)
            await page.get_by_label('Loop',exact=True).check();await seek(-.5)
            ok &= matches(await inspector(),expected(clip,s,-.5,True),ed['fps'])
            await seek(0);await page.get_by_label('Reverse',exact=True).check();await click('Step')
            e=expected(clip,s,-1,True);ok &= matches(await inspector(),e,ed['fps']);ok &= await sprite_check(ed,e,ed['id']+'-reverse')
            await click('Reset transport');ok &= matches(await inspector(),expected(clip,s,0),ed['fps'])
            ok &= not await page.get_by_label('Reverse',exact=True).is_checked()
            await page.get_by_label('Loop',exact=True).uncheck()
        return ok
    await run('boundaries_reverse_and_actual_stage',boundaries)
    async def drafts():
        ed=editions[0];clip=ed['clips'][2];s=default(clip);await choose(ed,clip);await seek(3.5);await click('Edit clip')
        await page.get_by_label('Edited beat',exact=True).select_option(label='Beat 2')
        await field('Base exposure',6);await field('Extra hold',4);await field('Start frame',5);await field('Rate multiplier',1.5)
        d=default(clip);d['exposures'][1]=6;d['holds'][1]=4;d.update(start=5,rate=1.5)
        ok=matches(await inspector(),expected(clip,d,5),ed['fps']*1.5)
        ok &= await sprite_check(ed,expected(clip,d,5),'draft-actual')
        await click('Cancel');ok &= matches(await inspector(),expected(clip,s,3.5),ed['fps'])
        await page.reload(wait_until='load');ok &= matches(await inspector(),expected(clip,s,0),ed['fps'])
        return ok
    await run('draft_preview_cancel',drafts)
    async def persistence():
        ed=editions[0];clip=ed['clips'][3];await choose(ed,clip);await click('Edit clip')
        await page.get_by_label('Edited beat',exact=True).select_option(label='Beat 3')
        await field('Base exposure',7);await field('Extra hold',5);await field('Start frame',6);await field('Rate multiplier',.5);await click('Save')
        d=default(clip);d['exposures'][2]=7;d['holds'][2]=5;d.update(start=6,rate=.5)
        ok=matches(await inspector(),expected(clip,d,6),ed['fps']*.5)
        await page.reload(wait_until='load');ok &= matches(await inspector(),expected(clip,d,6),ed['fps']*.5)
        await seek(sum(d['exposures'][:3])+sum(d['holds'][:3]))
        e=expected(clip,d,sum(d['exposures'][:3])+sum(d['holds'][:3]));ok &= matches(await inspector(),e,ed['fps']*.5)
        ok &= await sprite_check(ed,e,'saved-shifted-boundary')
        other=editions[1];oc=other['clips'][3];await choose(other,oc)
        ok &= matches(await inspector(),expected(oc,default(oc),0),other['fps'])
        await click('Edit clip');await field('Extra hold',3);await field('Start frame',2);await click('Save')
        await choose(ed,clip);ok &= matches(await inspector(),expected(clip,d,6),ed['fps']*.5)
        await click('Undo');ok &= matches(await inspector(),expected(clip,default(clip),0),ed['fps'])
        await page.reload(wait_until='load');ok &= matches(await inspector(),expected(clip,default(clip),0),ed['fps'])
        await choose(other,oc);od=default(oc);od['holds'][0]=3;od['start']=2
        ok &= matches(await inspector(),expected(oc,od,2),other['fps'])
        await click('Reset clip');ok &= matches(await inspector(),expected(oc,default(oc),0),other['fps'])
        await click('Undo');ok &= matches(await inspector(),expected(oc,od,2),other['fps'])
        return ok
    await run('atomic_save_reload_undo_independent_editions',persistence)
    async def playback():
        ed=editions[1];clip=ed['clips'][1];await choose(ed,clip);await click('Edit clip');await field('Rate multiplier',2);await click('Save');await seek(0)
        start=time.monotonic();await click('Play');await page.wait_for_timeout(260);await click('Pause');elapsed=time.monotonic()-start
        p=parse_inspector(await inspector());t=float(p.get('Frame','nan'))
        # Scheduling-tolerant visible frame delta, NOT animation callback inspection.
        ok=2<t<min(12,elapsed*ed['fps']*2+3)
        frozen=await inspector();await page.wait_for_timeout(80);ok &= frozen==await inspector()
        await seek(999);await click('Play');await page.wait_for_timeout(100)
        ok &= await page.get_by_role('button',name='Play',exact=True).count()==1
        await page.get_by_label('Reverse',exact=True).check();await seek(0);await click('Play');await page.wait_for_timeout(100)
        ok &= await page.get_by_role('button',name='Play',exact=True).count()==1
        await click('Reset transport');return ok
    await run('play_pause_rate_and_nonloop_stops',playback)
    async def viewer():
        # Baseline diagnosis remains accessible; verify both edition guides and all attachment controls.
        ok=True
        for ed in editions:
            await choose(ed,ed['clips'][0]);await click('Received')
            body=await page.locator('body').inner_text();ok &= 'Start inclusive' in body or 'Beat start is included' in body
            for name in ['Atlas 1','Atlas 2','Board 1','Board 2']:
                await click(name);await click('Next detail');ok &= await page.get_by_role('button',name='Previous detail',exact=True).is_visible();await click('Fit sheet')
            await click('Back to animation')
        return ok
    await run('received_evidence_accessible',viewer)
    elapsed=round(time.monotonic()-started,3)
    (out/'ui-observations.json').write_text(json.dumps({'events':events,'pixels':pixels,'grade_seconds':elapsed},indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':rows}
