"""Trusted import of external product inputs only, independent of candidate DOM."""
from pathlib import Path
import json
async def seed(page, ctx):
    await page.wait_for_load_state('load')
    await page.evaluate('''inbox => {
      if (localStorage.getItem('marble-post-inbox') === null)
        localStorage.setItem('marble-post-inbox', JSON.stringify(inbox));
    }''', ctx['fixture'])
    await page.reload(wait_until='load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'seed':'external inbox only','candidate_checks':False})+'\n')
async def capture(page, ctx):
    # Pre-edit initial scene only. Do not open the viewer or perform repair checks.
    await page.screenshot(path=str(Path(ctx['output_dir'])/'initial.png'))
    return {'scene':'Initial run; received viewer closed; no edits','image':'initial.png'}
