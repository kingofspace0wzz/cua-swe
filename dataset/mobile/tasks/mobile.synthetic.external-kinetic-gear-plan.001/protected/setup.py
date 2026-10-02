from pathlib import Path
import json
async def seed(page, ctx):
    # Product input only. No candidate headings, renderer tags or correct model required.
    await page.wait_for_load_state('load')
    await page.evaluate('inbox => { if (!localStorage.getItem("tideglass.inbox")) localStorage.setItem("tideglass.inbox", JSON.stringify(inbox)); }', ctx['fixture']['inbox'])
    await page.reload(wait_until='load')

async def capture(page, ctx):
    # Actual pre-edit rendering, not expected repair output. Return to the initial workspace.
    out=Path(ctx['output_dir']);page.set_default_timeout(1200)
    await page.screenshot(path=str(out/'initial.png'))
    refs={}
    editions=ctx['fixture']['inbox']['editions']
    for edition in editions:
        await page.get_by_label('Edition',exact=True).select_option(edition['id'])
        await page.get_by_role('button',name='Originals',exact=True).click()
        for i,sheet in enumerate(edition['sheets']):
            await page.get_by_label('Drawing sheet',exact=True).select_option(str(i))
            picture=page.get_by_role('img',name=sheet['title']+' — original maker attachment',exact=True)
            await picture.screenshot(path=str(out/f'original-{edition["id"]}-{i}.png'))
            refs[f'{edition["id"]}-{i}']=f'original-{edition["id"]}-{i}.png'
    await page.get_by_label('Edition',exact=True).select_option(editions[0]['id'])
    await page.get_by_role('button',name='Preview',exact=True).click()
    await page.evaluate('window.scrollTo(0,0)')
    await page.screenshot(path=str(out/'initial-restored.png'))
    return {'scene':'Original pre-edit preview; no report or attachment left open','originals':refs,'image':'initial.png'}
