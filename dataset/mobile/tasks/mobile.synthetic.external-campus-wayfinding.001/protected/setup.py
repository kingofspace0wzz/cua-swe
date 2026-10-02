"""Trusted importer and actual pre-edit evidence capture. Never a public input."""
from pathlib import Path
import json

async def seed(page, ctx):
    inbox = ctx['fixture']['inbox']
    if len(inbox['campuses']) < 2:
        raise RuntimeError('invalid external inbox fixture')
    # Only external product inputs/default state are seeded. No route, user
    # interaction or expected output is injected. Ordinary reload never calls seed.
    imported = await page.evaluate('''(inbox) => {
      const key='campus-pocket.provider-inbox.v1';
      if(localStorage.getItem(key)) return false;
      localStorage.setItem(key,JSON.stringify(inbox));
      localStorage.removeItem('campus-pocket.trips.v1');
      return true;
    }''', inbox)
    await page.reload(wait_until='load')
    valid = await page.evaluate("() => !!localStorage.getItem('campus-pocket.provider-inbox.v1')")
    if not valid:
        raise RuntimeError('provider import did not persist')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'imported':imported,'external_inputs_only':True})+'\n')

async def capture(page, ctx):
    root=Path(ctx['output_dir']); result={'campuses':{}}
    await page.screenshot(path=str(root/'initial-trip.png'),full_page=False)
    result['initial_image']='initial-trip.png'
    for c in ctx['fixture']['inbox']['campuses']:
        await page.get_by_role('button',name='Change campus',exact=True).click()
        await page.get_by_role('button',name=c['title'],exact=True).click()
        await page.get_by_role('button',name='Original map',exact=True).click()
        image=page.get_by_role('img',name=c['title']+' original two-floor campus map',exact=True)
        image_path=c['id']+'-original-map.png'
        await image.screenshot(path=str(root/image_path))
        await page.screenshot(path=str(root/(c['id']+'-map-screen.png')),full_page=False)
        await page.get_by_role('button',name='Routing report',exact=True).click()
        pages=[]
        for i in range(len(c['report']['pages'])):
            # Read actual rendered content, not fixture expected strings.
            pages.append(await page.get_by_role('region',name='Provider report page',exact=True).inner_text())
            await page.screenshot(path=str(root/(c['id']+'-report-'+str(i+1)+'.png')),full_page=False)
            if i+1<len(c['report']['pages']):
                await page.get_by_role('button',name='Next page',exact=True).click()
        result['campuses'][c['id']]={'map_image':image_path,'report_pages':pages}
    first=ctx['fixture']['inbox']['campuses'][0]
    await page.get_by_role('button',name='Change campus',exact=True).click()
    await page.get_by_role('button',name=first['title'],exact=True).click()
    await page.get_by_role('button',name='Plan trip',exact=True).click()
    await page.screenshot(path=str(root/'ready-trip.png'),full_page=False)
    result['ready_image']='ready-trip.png'
    return result
