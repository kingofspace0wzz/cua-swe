"""Trusted imported inbox only. No answer state, UI edits, or candidate readiness contract."""
from pathlib import Path
import json
async def seed(page, ctx):
    await page.wait_for_load_state('load')
    await page.evaluate('(inbox) => localStorage.setItem("mural.inbox.v1", JSON.stringify(inbox))',ctx['fixture']['inbox'])
    await page.reload(wait_until='load')
    with (Path(ctx['output_dir'])/'seed-calls.jsonl').open('a') as f:
        f.write(json.dumps({'phase':ctx['phase'],'external_inbox_only':True})+'\n')
async def capture(page, ctx):
    await page.screenshot(path=str(Path(ctx['output_dir'])/'pre-edit-inbox.png'))
    return {'image':'pre-edit-inbox.png','capture':'actual imported inbox before editing','external_input_count':len(ctx['fixture']['inbox'])}
