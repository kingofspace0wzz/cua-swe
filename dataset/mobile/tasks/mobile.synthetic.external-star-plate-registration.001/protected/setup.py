"""Trusted local external import. No answers, navigation or repaired state seeded."""
import json
from pathlib import Path
async def seed(page, ctx):
    await page.evaluate('''inbox => {
      const key='larkspur.provider-inbox.v1';
      if (!localStorage.getItem(key)) localStorage.setItem(key,JSON.stringify(inbox));
    }''', ctx['fixture']['inbox'])
    await page.reload(wait_until='load')
    # Only document readiness, independent of candidate DOM or registration validity.
    await page.wait_for_load_state('load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'import':'external inbox only','approved_seeded':False})+'\n')
async def capture(page, ctx):
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    await page.screenshot(path=str(Path(ctx['output_dir'])/'pre-edit.png'),full_page=False)
    return {'image':'pre-edit.png','url':page.url,'viewport':page.viewport_size,
            'kind':'actual initial unedited page; no diagnostics/test interactions'}
