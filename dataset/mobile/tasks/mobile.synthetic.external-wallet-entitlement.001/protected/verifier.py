from pathlib import Path
import json, re

async def grade(page, ctx):
    if not ctx['baseline'] or ctx['baseline'].get('capture_kind') != 'native_hook_pre_edit':
        raise RuntimeError('real pre-edit capture required')
    # Observe rendered UI only. Storage is used solely for a fresh external import
    # near the end, never to read implementation state or evaluator-success flags.
    observations=[]
    async def text(): return await page.locator('body').inner_text()
    async def visible(locator):
        for i in range(await locator.count()):
            if await locator.nth(i).is_visible(): return locator.nth(i)
        return None
    async def has(value): return await visible(page.get_by_text(value,exact=True)) is not None
    async def click(name):
        target=await visible(page.get_by_role('button',name=name,exact=True))
        if target is None or not await target.is_enabled():return False
        await target.click(timeout=1500)
        return True
    async def wallet():
        # No private state reset: navigate only through the visible control.
        await click('Back to wallet')
    async def choose(p):
        await wallet()
        return await click(p['title'])
    def entitlement(p):
        record=p['issuerRecord']; ref=record['admission']
        return next(x for x in record['entitlements'] if (x['entitlementId'],x['revision'])==(ref['entitlementId'],ref['revision']))
    async def balance(p,quantity=None):
        row=entitlement(p)
        count=(row['balance']['quantity'] if quantity is None else quantity)//row['chargePerVisit']['quantity']
        action=await visible(page.get_by_role('button',name='Validate one visit',exact=True))
        enabled=bool(action is not None and await action.is_enabled())
        expected_enabled=row['state']=='active' and count>0
        ok=(await has(f'{count} complete visits') and await has(f'Status: {row["state"]}') and enabled==expected_enabled and await has(p['title']))
        observations.append({'pass':p['passId'],'expected_visits':count,'expected_action':expected_enabled,'text':await text(),'passed':bool(ok)})
        return bool(ok)
    async def receipt(p,remaining):
        row=entitlement(p); content=await text()
        # The visible newest receipt must report the issuer's accepted debit and
        # exact entitlement revision. No data attribute, function or storage read.
        # Split before the next receipt so an old accepted history cannot satisfy.
        blocks=re.split(r'\n(Accepted|Refused)\n',content)
        newest=blocks[2] if len(blocks)>2 and blocks[1]=='Accepted' else ''
        # Whitespace and ordinary punctuation/layout are not part of the contract.
        normalized=re.sub(r'[^\w-]+',' ',newest).strip()
        charge=row['chargePerVisit']
        checks=[r'\bpassId '+re.escape(p['passId'])+r'\b',
                r'\bentitlementId '+re.escape(row['entitlementId'])+r'\b',
                r'\brevision '+str(row['revision'])+r'\b',
                r'\bdebit quantity '+str(charge['quantity'])+r' unit '+re.escape(charge['unit']),
                r'\bbalanceAfter quantity '+str(remaining)+r' unit '+re.escape(charge['unit'])]
        ok=all(re.search(pattern,normalized) for pattern in checks)
        observations.append({'receipt_text':content,'pass':p['passId'],'passed':bool(ok)})
        return bool(ok)
    async def redeem(p,remaining):
        if not await click('Validate one visit'):return False
        if not await click('Confirm validation'):
            await click('Cancel');return False
        ok=await receipt(p,remaining)
        await wallet()
        return await balance(p,remaining) and ok
    primary,paused,other=ctx['fixture']['inbox']['passes']
    initial=await balance(primary)
    # Evidence remains inspectable for both primary and held/other passes.
    evidence=True
    for p in (primary,paused,other):
        evidence=await choose(p) and evidence
        if await click('Issuer details'):
            evidence=(await has('Issuer reading guide') and await has('Imported issuer record') and await has(p['passId'])) and evidence
            for item in ctx['fixture']['inbox']['contract']:
                evidence=(await has(item['title'])) and evidence
        else:evidence=False
        await wallet()
    await choose(paused)
    secondary=await balance(paused)
    if await click('Receipts'):
        secondary=await has('Refused') and await has('Issuer hold: paused. No debit; balance is retained.') and secondary
    else:secondary=False
    await choose(other);secondary=await balance(other) and secondary and evidence
    await choose(primary)
    # Cancel must leave balance and receipt history untouched.
    wallet_before=await text()
    await click('Receipts');before=await text();await wallet()
    cancel=await click('Validate one visit') and await click('Cancel')
    cancel=(await text()==wallet_before) and cancel
    await click('Receipts');cancel=(await text()==before) and cancel;await wallet()
    row=entitlement(primary);b=row['balance']['quantity'];c=row['chargePerVisit']['quantity']
    validation=await redeem(primary,b-c)
    # A second validation rejects display-only fixes and stale-balance repairs.
    validation=await redeem(primary,b-2*c) and validation
    # Real independent notes, selection, navigation and ordinary reload.
    await choose(primary)
    note=await visible(page.get_by_label('Pass note',exact=True))
    persistence=note is not None
    if note is not None:await note.fill('Meet by the south gate',timeout=1500)
    await choose(other)
    note=await visible(page.get_by_label('Pass note',exact=True))
    persistence=(note is not None and await note.input_value()=='') and persistence
    if note is not None:await note.fill('Bring a jacket',timeout=1500)
    orow=entitlement(other);ob=orow['balance']['quantity']-orow['chargePerVisit']['quantity']
    persistence=await redeem(other,ob) and persistence
    await page.reload(wait_until='load')
    note=await visible(page.get_by_label('Pass note',exact=True))
    persistence=await balance(other,ob) and (note is not None and await note.input_value()=='Bring a jacket') and persistence
    await choose(primary)
    note=await visible(page.get_by_label('Pass note',exact=True))
    persistence=await balance(primary,b-2*c) and (note is not None and await note.input_value()=='Meet by the south gate') and persistence
    await page.screenshot(path=str(Path(ctx['output_dir'])/'graded-main.png'),full_page=False)
    # A second imported inbox varies only data under the already-visible contract.
    await page.evaluate('''inbox=>{localStorage.clear();localStorage.setItem('civic-gate-import',JSON.stringify(inbox));}''',ctx['fixture']['gradeInbox'])
    await page.reload(wait_until='load')
    active,held=ctx['fixture']['gradeInbox']['passes']
    general=await balance(active)
    rr=entitlement(active)
    general=await redeem(active,rr['balance']['quantity']-rr['chargePerVisit']['quantity']) and general
    await choose(held);general=await balance(held) and general
    await page.screenshot(path=str(Path(ctx['output_dir'])/'graded-other-import.png'),full_page=False)
    (Path(ctx['output_dir'])/'ui-observations.json').write_text(json.dumps(observations,indent=2))
    outcomes=[initial,secondary,validation,cancel,persistence,general]
    return {'execution':'complete','errors':[], 'expected_assertions':ctx['expected_assertions'],
            'assertions':[{'id':key,'passed':bool(value)} for key,value in zip(ctx['expected_assertions'],outcomes)]}
