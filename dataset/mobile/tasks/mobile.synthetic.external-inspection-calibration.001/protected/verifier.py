from pathlib import Path
from io import BytesIO
import re,json,math
from PIL import Image,ImageChops
from playwright.async_api import TimeoutError as UITimeout

# Independent affine interpolation of the disclosed station contract; does not call
# candidate functions or read its edit store. The fixture contains inputs, not answers.
def transform(p,stations,source,target):
    a,b,c=[s[source] for s in stations]
    ux,uy=b[0]-a[0],b[1]-a[1];vx,vy=c[0]-a[0],c[1]-a[1]
    dx,dy=p[0]-a[0],p[1]-a[1];det=ux*vy-vx*uy
    beta=(dx*vy-vx*dy)/det;gamma=(ux*dy-dx*uy)/det
    return [stations[0][target][i]*(1-beta-gamma)+stations[1][target][i]*beta+stations[2][target][i]*gamma for i in (0,1)]
def length(points,stations):
    a,b=[transform(p,stations,'sample','surface') for p in points]
    return math.dist(a,b)
def endpoint_tolerance(stations,attachment,frame):
    # One rendered CSS pixel per axis: <= 1/2 px pointer/endpoint snapping
    # plus <= 1/2 px raster/frame-edge localization (scene DPR=1).
    # A maps image displacement to surface displacement; translations cancel.
    origin=transform([0,0],stations,'image','surface')
    sx=attachment['width']/frame['width'];sy=attachment['height']/frame['height']
    bound=max(math.dist(transform([dx*sx,dy*sy],stations,'image','surface'),origin)
              for dx in (-1,1) for dy in (-1,1))
    # Reverse triangle inequality bounds length error by endpoint displacement.
    # The unmoved endpoint comes from fixed external inputs, not another tap.
    return bound+.05+1e-9  # nearest 0.1 mm display, floating arithmetic guard

async def grade(page,ctx):
    out=Path(ctx['output_dir']);ids=ctx['expected_assertions'];ok={k:True for k in ids};details=[]
    async def click(name,exact=True):
        loc=page.get_by_role('button',name=name,exact=exact)
        if await loc.count()!=1:return False
        try: await loc.click(timeout=900);return True
        except UITimeout:return False
    async def text():return await page.locator('body').inner_text()
    async def reads(value,tolerance=.16):
        return any(abs(float(n)-value)<=tolerance for n in re.findall(r'(\d+(?:\.\d+)?)\s*mm',await text()))
    async def image(name):
        loc=page.get_by_role('img',name='Inspection attachment',exact=True)
        if await loc.count()!=1:return None,None
        try:
            await loc.scroll_into_view_if_needed(timeout=800)
            # Observable attachment content frame, independent of SVG/canvas/DOM
            # overlay internals. Borders/padding are decoration, not image pixels.
            box=await loc.evaluate("""el => {
                const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                const n=k=>parseFloat(s[k])||0;
                const l=n('borderLeftWidth')+n('paddingLeft');
                const t=n('borderTopWidth')+n('paddingTop');
                return {x:r.x+l,y:r.y+t,
                    width:r.width-l-n('borderRightWidth')-n('paddingRight'),
                    height:r.height-t-n('borderBottomWidth')-n('paddingBottom')};
            }""")
            if not box or min(box['width'],box['height'])<100:return None,None
            raw=await page.screenshot(path=str(out/name),clip=box)
            return Image.open(BytesIO(raw)).convert('RGB'),box
        except UITimeout:return None,None
    def aligned(anno,original,points,record):
        if anno is None or original is None or anno.size!=original.size:return False
        d=ImageChops.difference(anno,original);w,h=d.size
        for p in points:
            x=p[0]/record['attachment']['width']*w;y=p[1]/record['attachment']['height']*h
            count=0
            for yy in range(max(0,int(y)-11),min(h,int(y)+12)):
                for xx in range(max(0,int(x)-11),min(w,int(x)+12)):
                    if max(d.getpixel((xx,yy)))>45:count+=1
            if count<36:return False
        return True
    async def fail_all(reason):
        for k in ok:ok[k]=False
        details.append({'missing_workflow':reason})
    # Use only UI record navigation. No reseeding between records or after reload.
    for index,r in enumerate(ctx['fixture']['providerInbox']):
        if not await click('Inbox') or not await click(r['title'],False):
            await fail_all('record selection '+r['title']);break
        stations=r['report']['data']['calibration']['controlPoints'];points=r['report']['data']['traces'][0]['points']
        expected=[transform(p,stations,'sample','image') for p in points]
        metric=await reads(length(points,stations));ok['surface_lengths'] &= metric
        anno,box=await image(f'{index}-annotation.png')
        if not await click('Original'):
            await fail_all('Original');break
        orig,_=await image(f'{index}-original.png')
        registration=aligned(anno,orig,expected,r);ok['registered_overlays'] &= registration
        if not await click('Report'):
            await fail_all('Report');break
        sheet=await text()
        await click('Payload');payload_before=await text()
        # Report and original preservation are compared through visible rendering,
        # never by trusting a client declaration or its storage schema.
        await click('Annotation')
        # Edit endpoint 2 at a new nontrivial image-space location.
        target=[116,178] if index==0 else [178,166]
        await click('Move end')
        _,b=await image(f'{index}-move-ready.png')
        if b is None:
            await fail_all('attachment bounds');break
        x=round(b['x']+target[0]/r['attachment']['width']*b['width']);y=round(b['y']+target[1]/r['attachment']['height']*b['height'])
        # Actual click through the rendered attachment frame, never its outer border.
        tapped=[(x-b['x'])/b['width']*r['attachment']['width'],(y-b['y'])/b['height']*r['attachment']['height']]
        await page.mouse.click(x,y)
        new_points=[points[0],transform(tapped,stations,'image','sample')]
        new_expected=[expected[0],tapped]
        tolerance=endpoint_tolerance(stations,r['attachment'],b)
        moved,_=await image(f'{index}-moved.png')
        edit_pass=aligned(moved,orig,new_expected,r) and await reads(length(new_points,stations),tolerance)
        ok['endpoint_roundtrip'] &= edit_pass
        # Cancel must leave geometry and note unchanged.
        if await click('Edit note'):
            inp=page.get_by_role('textbox',name='Note text',exact=True)
            if await inp.count()==1:
                await inp.fill('Discard this draft')
                await click('Cancel')
                cancelled,_=await image(f'{index}-cancelled.png')
                ok['cancel_isolated'] &= ('Discard this draft' not in await text() and cancelled is not None and moved is not None and all(high<=2 for low,high in ImageChops.difference(cancelled,moved).getextrema()))
            else:ok['cancel_isolated']=False
        else:ok['cancel_isolated']=False
        note='Checked on site '+str(index+1)
        if await click('Edit note'):
            inp=page.get_by_role('textbox',name='Note text',exact=True)
            if await inp.count()==1:await inp.fill(note);await click('Save note')
            else:ok['save_navigation_reload']=False
        else:ok['save_navigation_reload']=False
        await click('Inbox');other=ctx['fixture']['providerInbox'][1-index]
        await click(other['title'],False);await click('Inbox');await click(r['title'],False)
        await page.reload(wait_until='load')
        retained,_=await image(f'{index}-reloaded.png')
        ok['save_navigation_reload'] &= note in await text() and aligned(retained,orig,new_expected,r) and await reads(length(new_points,stations),tolerance)
        await click('Original');orig_after,_=await image(f'{index}-original-after.png')
        same=orig is not None and orig_after is not None and orig.size==orig_after.size and ImageChops.difference(orig,orig_after).getbbox() is None
        await click('Report');sheet_after=await text();await click('Payload');payload_after=await text()
        ok['provider_unchanged'] &= same and sheet==sheet_after and payload_before==payload_after
        await click('Annotation')
        details.append({'record':r['id'],'registration':registration,'surface_length':metric,'endpoint_roundtrip':edit_pass,'expected_initial_mm':length(points,stations),'expected_edited_mm':length(new_points,stations),'attachment_frame_css':b,'click_css':[x,y],'tapped_image':tapped,'endpoint_tolerance_mm':tolerance})
    (out/'observations.json').write_text(json.dumps(details,indent=2)+'\n')
    return {'execution':'complete','errors':[],'expected_assertions':ids,'assertions':[{'id':k,'passed':bool(ok[k])} for k in ids]}
