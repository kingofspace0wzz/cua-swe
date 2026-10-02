from pathlib import Path
import json

async def seed(page, ctx):
    inbox = ctx['fixture']['inbox']
    await page.evaluate('''inbox => {
      localStorage.clear();
      localStorage.setItem('civic-gate-import', JSON.stringify(inbox));
    }''', inbox)
    # Verify the import mechanism, not repaired values or candidate UI structure.
    actual = await page.evaluate("JSON.parse(localStorage.getItem('civic-gate-import'))")
    if actual != inbox:
        raise RuntimeError('external inbox import failed')
    await page.reload(wait_until='load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as stream:
        stream.write(json.dumps({'phase':ctx['phase'],'external_import':True})+'\n')

async def capture(page, ctx):
    # No diagnosis, validation, saved notes or test UI is opened by capture.
    name = 'pre-edit-wallet.png'
    await page.screenshot(path=str(Path(ctx['output_dir'])/name), full_page=False)
    return {'image':name, 'visible_text':await page.locator('body').inner_text(),
            'scene':'Untouched imported wallet, before editing'}
