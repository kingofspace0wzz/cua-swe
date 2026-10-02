from pathlib import Path
import json
async def seed(page,ctx):
    # Deterministic simulation of an external provider import. No edit/results seeded.
    await page.evaluate('(records)=>{localStorage.clear();localStorage.setItem("fieldline.providerInbox",JSON.stringify(records));}',ctx['fixture']['providerInbox'])
    await page.reload(wait_until='load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'imported_records':len(ctx['fixture']['providerInbox']),'default_edits':False})+'\n')
async def capture(page,ctx):
    await page.screenshot(path=str(Path(ctx['output_dir'])/'baseline.png'))
    return {'image':'baseline.png','scene':'Initial imported inspection, Annotation tab; no diagnostic UI left open','visible_text':await page.locator('body').inner_text()}
