"""Private behavioral verifier. UI actions, rendered boxes/pixels and visible fields only.
No candidate functions, attributes encoding transforms, storage, or source are read.
"""
from pathlib import Path
from io import BytesIO
import math, json
from PIL import Image, ImageChops

ASSERTIONS=['flat_placement_orientation','upright_panel_placement','inverse_artwork_edit','note_edit_preserves_marker','proof_panel_isolation','reload_persistence']

# Independent declared-contract implementation; no candidate adapter import.
def expected(panel,u,v,heading):
    p=panel['placement'];x=u+p['trim']['left'];y=v+p['trim']['top']
    dx=math.cos(math.radians(heading));dy=math.sin(math.radians(heading))
    if p['reflectedX']:x=p['rawSize']['width']-x;dx=-dx
    c=math.cos(math.radians(p['rotationClockwise']));s=math.sin(math.radians(p['rotationClockwise']))
    return (p['sheetOrigin']['x']+c*x-s*y,p['sheetOrigin']['y']+s*x+c*y,math.degrees(math.atan2(s*dx+c*dy,c*dx-s*dy)))

class MissingVisibleControl(Exception): pass

async def grade(page,ctx):
    if not ctx['baseline'] or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('Missing real pre-edit capture; infrastructure-invalid')
    if ctx['expected_assertions']!=ASSERTIONS:raise RuntimeError('Verifier/Task configuration mismatch')
    out=Path(ctx['output_dir']);checks={k:[] for k in ASSERTIONS};events=[]
    async def visible(loc):
        if await loc.count()!=1 or not await loc.is_visible():
            raise MissingVisibleControl('Required visible control absent or ambiguous: '+str(loc))
        return loc
    async def click(name):
        loc=await visible(page.get_by_role('button',name=name,exact=True));await loc.click(timeout=1000)
    async def choose(proof,panel):
        await (await visible(page.get_by_label('Proof',exact=True))).select_option(label=proof['title'],timeout=1000)
        await click(panel['title'])
    async def fields():
        result={}
        for k,label in [('u','Panel u'),('v','Panel v'),('heading','Heading degrees'),('note','Panel note')]:
            loc=await visible(page.get_by_label(label,exact=True));value=await loc.input_value()
            try:result[k]=float(value) if k!='note' else value
            except ValueError:result[k]=None
        return result
    def close(got,want,tol=.06):
        return all(got.get(k) is not None and abs(got[k]-want[k])<=tol for k in ('u','v','heading')) and got.get('note')==want['note']
    async def save(values):
        for k,label in [('u','Panel u'),('v','Panel v'),('heading','Heading degrees'),('note','Panel note')]:
            await (await visible(page.get_by_label(label,exact=True))).fill(str(values[k]),timeout=1000)
        await click('Save review')
    async def marker():
        loc=page.get_by_role('button',name='Review marker',exact=True)
        if await loc.count()!=1 or not await loc.is_visible():return None
        b=await loc.bounding_box()
        return (b['x']+b['width']/2,b['y']+b['height']/2) if b else None
    async def artbox():return await (await visible(page.get_by_role('img',name='Review artwork',exact=True))).bounding_box()
    def screen(b,w,h,x,y):
        s=min(b['width']/w,b['height']/h)
        return b['x']+(b['width']-w*s)/2+x*s,b['y']+(b['height']-h*s)/2+y*s
    def near(a,b,tol=4):return a is not None and math.hypot(a[0]-b[0],a[1]-b[1])<=tol
    async def observe(proof,panel,values,flat,tag):
        # Difference of visible marker vs hidden marker removes the original proof artwork.
        # No required marker color, SVG path, CSS selector, transform attribute or source shape.
        art=await artbox();center=await marker()
        x,y,angle=expected(panel,values['u'],values['v'],values['heading']) if flat else (values['u'],values['v'],values['heading'])
        w,h=(proof['sheet']['width'],proof['sheet']['height']) if flat else (panel['width'],panel['height'])
        target=screen(art,w,h,x,y)
        raw=await page.screenshot()
        await click('Hide marker');hidden=await page.screenshot();await click('Show marker')
        img=Image.open(BytesIO(raw)).convert('RGB');bg=Image.open(BytesIO(hidden)).convert('RGB')
        diff=ImageChops.difference(img,bg)
        outward=[]
        # The oriented symbol has a center anchor and a directional shaft. Measure the
        # far changed pixels' direction, not their color or prescribed path.
        if center:
            for yy in range(max(0,int(center[1]-55)),min(img.height,int(center[1]+56))):
                for xx in range(max(0,int(center[0]-55)),min(img.width,int(center[0]+56))):
                    dx,dy=xx+.5-center[0],yy+.5-center[1]
                    if 20<math.hypot(dx,dy)<54 and max(diff.getpixel((xx,yy)))>35:outward.append((dx,dy))
        direction_error=360
        if len(outward)>8:
            vx=sum(q[0] for q in outward);vy=sum(q[1] for q in outward)
            actual=math.degrees(math.atan2(vy,vx));direction_error=abs((actual-angle+180)%360-180)
        ok=near(center,target) and direction_error<10
        events.append({'case':tag,'flat':flat,'target_px':target,'rendered_anchor_px':center,'heading_error_deg':direction_error,'changed_direction_pixels':len(outward),'passed':ok})
        if not ok:(out/(tag+'.png')).write_bytes(raw)
        return ok
    reviews=[]
    try:
        # Six edits cover both layouts, all orientations, asymmetric trim, reflection,
        # reused IDs in reordered panels and independent proof/panel identity.
        for ri,proof in enumerate(ctx['fixture']['records']):
            for pi,panel in enumerate(proof['panels']):
                await choose(proof,panel)
                values={'u':round(panel['width']*(.31+.07*pi),2),'v':round(panel['height']*(.43+.04*ri),2),'heading':25+pi*47+ri*19,'note':f'Review {ri+1}.{pi+1}: keep seam clear'}
                await save(values)
                checks['flat_placement_orientation'].append(await observe(proof,panel,values,True,f'flat-{ri}-{pi}'))
                await click('Individual panel')
                checks['upright_panel_placement'].append(await observe(proof,panel,values,False,f'panel-{ri}-{pi}'))
                checks['upright_panel_placement'].append(close(await fields(),values))
                await click('Flat sheet')
                if panel['placement']['rotationClockwise']==90:
                    # A tap on sheet artwork must invert the panel transform. No hidden setters.
                    tap_u=round(panel['width']*.58,2);tap_v=round(panel['height']*.61,2)
                    x,y,_=expected(panel,tap_u,tap_v,values['heading']);b=await artbox();px,py=screen(b,proof['sheet']['width'],proof['sheet']['height'],x,y)
                    await page.mouse.click(px,py)
                    got=await fields()
                    intended={**values,'u':tap_u,'v':tap_v}
                    checks['inverse_artwork_edit'].append(close(got,intended,tol=2))
                    await click('Save review')
                    values=got if all(isinstance(got[k],(int,float)) for k in ('u','v','heading')) else intended  # invalid visible values already fail above
                    checks['inverse_artwork_edit'].append(await observe(proof,panel,values,True,f'tap-{ri}-{pi}'))
                before=await marker()
                values={**values,'note':values['note']+' · approved'}
                await (await visible(page.get_by_label('Panel note',exact=True))).fill(values['note'],timeout=1000)
                await click('Save review');after=await marker()
                checks['note_edit_preserves_marker'].append(near(before,after,.5) and close(await fields(),values))
                reviews.append((proof,panel,values))
        # Revisit every saved review after all cross-proof edits, then ordinary reload.
        for proof,panel,values in reviews:
            await choose(proof,panel)
            checks['proof_panel_isolation'].append(close(await fields(),values))
        await page.reload(wait_until='load')
        for i,(proof,panel,values) in enumerate(reviews):
            await choose(proof,panel)
            got=await fields();b=await artbox();x,y,_=expected(panel,values['u'],values['v'],values['heading'])
            target=screen(b,proof['sheet']['width'],proof['sheet']['height'],x,y)
            checks['reload_persistence'].append(close(got,values) and near(await marker(),target))
            events.append({'case':f'reload-{i}','visible_values':got,'expected_values':values})
        await page.screenshot(path=str(out/'graded.png'))
    except MissingVisibleControl as exc:
        # An observed missing product control is a concrete false assertion. Native
        # timeouts, policy failures, setup errors and browser crashes are NOT caught.
        events.append({'visible_failure':str(exc)})
        for key in checks:checks[key].append(False)
    (out/'ui-observations.json').write_text(json.dumps({'events':events,'checks':checks},indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ASSERTIONS,'assertions':[{'id':k,'passed':bool(checks[k]) and all(checks[k])} for k in ASSERTIONS]}
