"""Trusted one-time external import and actual pre-edit references. Not solver files."""
from pathlib import Path
import json

async def seed(page, ctx):
    # Ordinary reload never runs seed. Guard also makes repeat invocation harmless.
    inserted = await page.evaluate('''payload => {
      if (localStorage.getItem('northline.imports.v1')) return false;
      localStorage.setItem('northline.imports.v1',JSON.stringify(payload));
      return true;
    }''', ctx['fixture'])
    if inserted:
        await page.reload(wait_until='load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'inserted':inserted,'input_only':True})+'\n')

async def capture(page, ctx):
    out=Path(ctx['output_dir'])
    originals={}
    for i, record in enumerate(ctx['fixture']['records']):
        await page.get_by_role('button',name=record['title'],exact=True).click(timeout=2000)
        await page.get_by_role('button',name='Original panorama',exact=True).click(timeout=2000)
        image=page.get_by_role('img',name='Complete original panorama',exact=True)
        await image.wait_for(state='visible',timeout=2000)
        # Decode browser images only; no app functions, source or private answers read.
        await page.evaluate('async () => { await Promise.all([...document.images].map(i=>i.decode())); }')
        filename=f'original-{i}.png'
        await image.screenshot(path=str(out/filename),timeout=2000)
        await page.screenshot(path=str(out/f'original-flow-{i}.png'),timeout=2000)
        await page.get_by_role('button',name='Back to tour',exact=True).click(timeout=2000)
        await page.get_by_role('button',name='Capture guide',exact=True).click(timeout=2000)
        orientation=await page.get_by_role('table',name='Capture orientation record',exact=True).inner_text(timeout=2000)
        await page.screenshot(path=str(out/f'capture-guide-{i}.png'),full_page=True,timeout=2000)
        originals[record['id']]={'image':filename,'orientation_text':orientation,'projections':{}}
        await page.get_by_role('button',name='Back to tour',exact=True).click(timeout=2000)
        # Actual bare-artwork camera references. The broken review is outside these
        # windows; we do not remove/hide it or inject any repaired output.
        c=record['capture']; review=record['review']
        sign=1 if c['panoramaYawDirection']=='clockwise' else -1
        vertical=1 if c['reviewElevationDirection']=='up' else -1
        yaw=(c['northAtPanoramaYaw']+sign*review['azimuth'])%360
        pitch=vertical*review['elevation']
        target=record['landmarks'][1]; ty=target['panoramaYaw'];tp=target['panoramaLatitude']
        views={'forward':(record['initialView']['heading'],5 if i==0 else -4),
               'seam':(yaw,pitch-7),'inverse':(ty-13,tp+8),
               'label':(ty+11,tp-6),'reload':(ty-8,tp+5)}
        for key,(h,e) in views.items():
            await page.get_by_label('Heading (°)',exact=True).fill(str(h),timeout=2000)
            await page.get_by_label('Elevation (°)',exact=True).fill(str(e),timeout=2000)
            await page.get_by_role('button',name='Set view',exact=True).click(timeout=2000)
            name=f'panorama-{i}-{key}.png'
            await page.get_by_label('Panorama tour window',exact=True).screenshot(path=str(out/name),timeout=2000)
            originals[record['id']]['projections'][key]=name
        await page.get_by_label('Heading (°)',exact=True).fill(str(record['initialView']['heading']),timeout=2000)
        await page.get_by_label('Elevation (°)',exact=True).fill(str(record['initialView']['elevation']),timeout=2000)
        await page.get_by_role('button',name='Set view',exact=True).click(timeout=2000)
    await page.get_by_role('button',name=ctx['fixture']['records'][0]['title'],exact=True).click(timeout=2000)
    await page.screenshot(path=str(out/'initial.png'),timeout=2000)
    return {'originals':originals,'initial_image':'initial.png','scene':'First tour, initial view, no unsaved edits; guide and original viewer closed.'}
