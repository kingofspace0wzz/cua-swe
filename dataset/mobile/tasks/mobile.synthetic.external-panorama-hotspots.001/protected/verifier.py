"""Private behavioral verifier: UI actions, accessible rendered output and pixels only.
No calls into app JS, no localStorage reads, no output/source tag constraints.
"""
import math, re, json
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageChops, ImageStat
from playwright.async_api import TimeoutError as UITimeout

PIXEL_TOLERANCE=6.0
ANGLE_TOLERANCE=0.55

def projection(yaw, pitch, heading, elevation, width, height):
    # Independent camera-space derivation using yaw difference, then pitch rotation.
    d=math.radians(yaw-heading);p=math.radians(pitch);e=math.radians(elevation)
    x=math.cos(p)*math.sin(d)
    y=math.sin(p)*math.cos(e)-math.cos(p)*math.cos(d)*math.sin(e)
    z=math.sin(p)*math.sin(e)+math.cos(p)*math.cos(d)*math.cos(e)
    if z<=0:return None
    f=width/(2*math.tan(math.radians(36)))
    return (width/2+f*x/z,height/2-f*y/z)

def registered(review,capture):
    s=1 if capture['panoramaYawDirection']=='clockwise' else -1
    v=1 if capture['reviewElevationDirection']=='up' else -1
    return ((capture['northAtPanoramaYaw']+s*review['azimuth'])%360,v*review['elevation'])

def exported(yaw,pitch,capture):
    s=1 if capture['panoramaYawDirection']=='clockwise' else -1
    v=1 if capture['reviewElevationDirection']=='up' else -1
    return ((s*(yaw-capture['northAtPanoramaYaw']))%360,v*pitch)

def angular(a,b):return abs((a-b+180)%360-180)

def color_center(raw,color):
    im=Image.open(BytesIO(raw)).convert('RGB')
    target=tuple(int(color[i:i+2],16) for i in (1,3,5))
    pts=[(x,y) for y in range(im.height) for x in range(im.width)
         if max(abs(a-b) for a,b in zip(im.getpixel((x,y)),target))<=3]
    if len(pts)<10:return None
    return (sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts))

def image_preserved(before,after):
    # Compare original visible attachment, allowing rescaling/layout and tiny raster variance.
    a=Image.open(before).convert('RGB').resize((360,180))
    b=Image.open(BytesIO(after)).convert('RGB').resize((360,180))
    return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3 < 1.0

async def grade(page,ctx):
    baseline=ctx.get('baseline')
    if not baseline or baseline.get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('Infrastructure: real pre-edit reference missing')
    out=Path(ctx['output_dir']);events=[]
    passed={key:True for key in ctx['expected_assertions']}
    async def click(name):
        await page.get_by_role('button',name=name,exact=True).click(timeout=900)
    active_record=None
    async def select(record):
        nonlocal active_record
        await click(record['title'])
        active_record=record
    async def view(heading,elevation):
        await page.get_by_label('Heading (°)',exact=True).fill(str(heading),timeout=900)
        await page.get_by_label('Elevation (°)',exact=True).fill(str(elevation),timeout=900)
        await click('Set view')
    async def label(text):
        await page.get_by_label('Review label',exact=True).fill(text,timeout=900)
        await click('Save review')
    async def saved():
        text=await page.get_by_label('Saved review record',exact=True).inner_text(timeout=900)
        a=re.search(r'Azimuth\s*:?\s*([-+\d.]+)',text,re.I)
        e=re.search(r'Elevation\s*:?\s*([-+\d.]+)',text,re.I)
        return (float(a[1]),float(e[1]),text) if a and e else (None,None,text)
    async def record_ok(expected, text=None):
        a,e,t=await saved()
        return (a is not None and 0<=a<360 and angular(a,expected[0])<=ANGLE_TOLERANCE
                and abs(e-expected[1])<=ANGLE_TOLERANCE and (text is None or text in t))
    async def bounds():
        region=page.get_by_label('Panorama tour window',exact=True)
        await region.scroll_into_view_if_needed(timeout=900)
        return region,await region.bounding_box(timeout=900)
    async def marker_near(yaw,pitch,heading,elevation,landmark=None,reference='forward'):
        region,b=await bounds()
        raw=await region.screenshot(timeout=1000)
        current=Image.open(BytesIO(raw)).convert('RGB')
        ref=baseline['state']['originals'][active_record['id']]['projections'][reference]
        original=Image.open(Path(ctx['baseline_dir'])/ref).convert('RGB').resize(current.size)
        q=projection(yaw,pitch,heading,elevation,b['width'],b['height'])
        if not q:return False
        # Pixels, not a required DOM overlay/tag/color. These bare-artwork references
        # are actual pre-edit app captures at the same camera rays. A visible canvas
        # ring, an SVG overlay, or an HTML marker are all observable this way.
        scale_x=current.width/b['width'];scale_y=current.height/b['height']
        delta=ImageChops.difference(current,original)
        changed=[]
        for yy in range(max(0,int((q[1]-45)*scale_y)),min(current.height,int((q[1]+45)*scale_y)+1)):
            for xx in range(max(0,int((q[0]-45)*scale_x)),min(current.width,int((q[0]+45)*scale_x)+1)):
                if max(delta.getpixel((xx,yy)))>60:
                    changed.append((xx/scale_x,yy/scale_y))
        if len(changed)<20:
            events.append({'visible_overlay_missing':True,'reference':reference});return False
        got=((min(p[0] for p in changed)+max(p[0] for p in changed))/2,
             (min(p[1] for p in changed)+max(p[1] for p in changed))/2)
        error=math.hypot(got[0]-q[0],got[1]-q[1])
        result=error<=PIXEL_TOLERANCE
        if landmark:
            c=color_center(raw,landmark['medallionColor'])
            result=result and c is not None and math.hypot(c[0]/scale_x-q[0],c[1]/scale_y-q[1])<=PIXEL_TOLERANCE
        events.append({'expected_marker':q,'observed_overlay_center':got,'error_css_px':error,'landmark':landmark['name'] if landmark else None,'passed':result})
        return result
    async def run(key,fn):
        # Missing/wrong visible controls are explicit behavioral false, not hook exceptions.
        try:
            value=await fn()
            passed[key]=passed[key] and bool(value)
        except UITimeout as exc:
            passed[key]=False;events.append({'assertion':key,'visible_action_timeout':str(exc)[:350]})

    final=[]
    for i,r in enumerate(ctx['fixture']['records']):
        capture=r['capture'];initial=registered(r['review'],capture)
        start=r['initialView'];h=start['heading'];e=5 if i==0 else -4
        # Select context is required for every group; if a visible scene control is absent,
        # dependent behavioral groups fail explicitly without inventing measurements.
        try:await select(r)
        except UITimeout:
            for k in passed:passed[k]=False
            events.append({'scene_unreachable':r['title']});continue
        landmark=min(r['landmarks'],key=lambda l:angular(l['panoramaYaw'],initial[0])+abs(l['panoramaLatitude']-initial[1]))
        async def forward():
            await view(h,e)
            return await marker_near(*initial,h,e,landmark)
        await run('registered_placement',forward)
        async def seam():
            ok=True
            # All equivalent rays, not a pixel x modulo shortcut. Both captures tested.
            for heading in (initial[0]-360,initial[0],initial[0]+360):
                await view(heading,initial[1]-7)
                ok=(await marker_near(*initial,heading,initial[1]-7,landmark,'seam')) and ok
            return ok
        await run('spherical_view_and_seam',seam)
        target=r['landmarks'][1]
        target_yaw=target['panoramaYaw'];target_pitch=target['panoramaLatitude']
        edit_h=target_yaw-13;edit_e=target_pitch+8
        expected=exported(target_yaw,target_pitch,capture)
        new_label=f'Reviewed {target["name"]}'
        async def inverse():
            await view(edit_h,edit_e)
            region,b=await bounds()
            p=projection(target_yaw,target_pitch,edit_h,edit_e,b['width'],b['height'])
            # Tap the medallion using visible projected artwork, not an application setter.
            raw=await region.screenshot(timeout=1000)
            center=color_center(raw,target['medallionColor'])
            if not center or math.hypot(center[0]-p[0],center[1]-p[1])>PIXEL_TOLERANCE:return False
            await click('Move hotspot')
            # Button click may scroll; re-read the displayed window bounds.
            region,b=await bounds()
            await page.mouse.click(b['x']+p[0],b['y']+p[1])
            await click('Save review')
            return (await record_ok(expected)) and (await marker_near(target_yaw,target_pitch,edit_h,edit_e,target,'inverse'))
        await run('inverse_edit_and_saved_angles',inverse)
        async def label_only():
            # A window change before a label-only save must not reinterpret the anchor.
            await view(target_yaw+11,target_pitch-6)
            await label(new_label)
            return (await record_ok(expected,new_label)) and (await marker_near(target_yaw,target_pitch,target_yaw+11,target_pitch-6,target,'label'))
        await run('label_save_preserves_anchor',label_only)
        final.append((r,target,expected,new_label))
        async def originals():
            await click('Original panorama')
            image=page.get_by_role('img',name='Complete original panorama',exact=True)
            raw=await image.screenshot(timeout=1000)
            ref=baseline['state']['originals'][r['id']]
            ok=image_preserved(Path(ctx['baseline_dir'])/ref['image'],raw)
            await click('Back to tour');await click('Capture guide')
            table=await page.get_by_role('table',name='Capture orientation record',exact=True).inner_text(timeout=900)
            ok=ok and table==ref['orientation_text']
            await click('Back to tour')
            return ok
        await run('original_and_capture_preserved',originals)

    async def persistence():
        ok=True
        await page.reload(wait_until='load',timeout=3000)
        for r,target,expected,new_label in reversed(final):
            await select(r)
            await view(target['panoramaYaw']-8,target['panoramaLatitude']+5)
            ok=(await record_ok(expected,new_label)) and ok
            ok=(await marker_near(target['panoramaYaw'],target['panoramaLatitude'],target['panoramaYaw']-8,target['panoramaLatitude']+5,target,'reload')) and ok
        return ok and len(final)==len(ctx['fixture']['records'])
    await run('independent_scene_reload',persistence)
    await page.screenshot(path=str(out/'graded.png'),timeout=1500)
    (out/'ui-observations.json').write_text(json.dumps({'tolerance_css_px':PIXEL_TOLERANCE,'tolerance_degrees':ANGLE_TOLERANCE,'events':events},indent=2))
    return {'execution':'complete','errors':[], 'expected_assertions':ctx['expected_assertions'],
            'assertions':[{'id':key,'passed':passed[key]} for key in ctx['expected_assertions']]}
