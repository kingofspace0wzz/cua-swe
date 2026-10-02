"""Trusted imported inbox only. No expected schedules or candidate results are seeded."""
from pathlib import Path
import json
async def seed(page,ctx):
    # Native worker already navigated to the isolated app origin. Installing the
    # external product input is the only state mutation. Reload does NOT run seed.
    await page.wait_for_load_state('domcontentloaded')
    fixture=ctx['fixture']
    await page.evaluate('(records) => { if (!localStorage.getItem("brine-external-inbox")) localStorage.setItem("brine-external-inbox", JSON.stringify(records)); }',fixture['inbox'])
    await page.reload(wait_until='load')
async def capture(page,ctx):
    # Actual pre-edit reference, no repair/diagnosis interactions.
    await page.screenshot(path=str(Path(ctx['output_dir'])/'baseline.png'))
    return {'image':'baseline.png','scene':'Initial received-refit workspace, no viewer/guide/test UI open','source':'native_hook_pre_edit'}
