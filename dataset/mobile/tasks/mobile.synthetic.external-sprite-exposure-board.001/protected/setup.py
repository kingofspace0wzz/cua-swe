"""Trusted deterministic import; no expected values, edits or UI interactions seeded."""
from pathlib import Path
import json
async def seed(page, ctx):
    await page.wait_for_load_state('domcontentloaded')
    installed = await page.evaluate('''inbox => {
      if (localStorage.getItem('celroom.inbox')) return false;
      localStorage.setItem('celroom.inbox', JSON.stringify(inbox)); return true;
    }''', ctx['fixture']['inbox'])
    if installed:
        await page.reload(wait_until='load')
    else:
        await page.wait_for_load_state('load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'external_inbox_installed':installed})+'\n')
async def capture(page, ctx):
    # Actual pre-edit app, no diagnosis/test screen opened and no repair-dependent heading wait.
    await page.wait_for_load_state('load')
    await page.screenshot(path=str(Path(ctx['output_dir'])/'reference.png'), full_page=False)
    return {'image':'reference.png','surface':'initial animation screen','external_import_only':True}
