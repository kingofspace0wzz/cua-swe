"""Trusted imported product inputs only; never repaired results or user actions."""
from pathlib import Path
import json

async def seed(page, ctx):
    fixture = ctx['fixture']
    if not isinstance(fixture, dict) or len(fixture.get('records', [])) < 2:
        raise RuntimeError('Missing imported proof attachments: infrastructure-invalid')
    # Called once for each fresh context. Ordinary reload never calls seed.
    await page.evaluate('(inbox) => localStorage.setItem("foldnote.imported", JSON.stringify(inbox))', fixture)
    await page.reload(wait_until='load')
    await page.get_by_role('heading', name='Foldnote', exact=True).wait_for(state='visible')
    await page.get_by_role('button', name='Source proof', exact=True).wait_for(state='visible')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'], 'input_records':len(fixture['records']), 'reviews_seeded':False})+'\n')

async def capture(page, ctx):
    out=Path(ctx['output_dir'])
    await page.screenshot(path=str(out/'initial-editor.png'))
    records=[]
    # Genuine original source observations before edits. No expected outcomes seeded.
    for i, proof in enumerate(ctx['fixture']['records']):
        await page.get_by_label('Proof', exact=True).select_option(label=proof['title'])
        await page.get_by_role('button',name='Source proof',exact=True).click()
        art=page.get_by_role('img',name='Source proof artwork',exact=True)
        await art.screenshot(path=str(out/f'source-proof-{i}.png'))
        await page.get_by_role('button',name='Panel report',exact=True).click()
        await page.screenshot(path=str(out/f'report-{i}.png'))
        records.append({'proof':proof['title'],'source_image':f'source-proof-{i}.png','report_image':f'report-{i}.png','report_text':await page.locator('main').inner_text()})
        await page.get_by_role('button',name='← Source proof',exact=True).click()
    # Leave exactly the initial editor, not diagnosis UI or tests.
    await page.get_by_label('Proof',exact=True).select_option(label=ctx['fixture']['records'][0]['title'])
    await page.get_by_role('button',name='Flat sheet',exact=True).click()
    await page.screenshot(path=str(out/'returned-editor.png'))
    return {'scene':'Initial flat-sheet editor, first proof and first panel; no reviews edited','initial_image':'initial-editor.png','returned_image':'returned-editor.png','external_observations':records}
