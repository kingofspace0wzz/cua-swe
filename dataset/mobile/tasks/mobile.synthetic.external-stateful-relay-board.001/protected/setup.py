from pathlib import Path

async def seed(page, ctx):
    # Input import only. No solved results, edits, UI assumptions or test assertions.
    await page.wait_for_load_state('load')
    await page.evaluate('(inbox) => localStorage.setItem("lantern.provider.inbox", JSON.stringify(inbox))', ctx['fixture']['inbox'])
    await page.reload(wait_until='load')

async def capture(page, ctx):
    path = Path(ctx['output_dir']) / 'pre-edit.png'
    await page.screenshot(path=str(path), full_page=False)
    return {'image': 'pre-edit.png', 'kind': 'actual_pre_edit_app', 'viewport': {'width':400,'height':800}}
