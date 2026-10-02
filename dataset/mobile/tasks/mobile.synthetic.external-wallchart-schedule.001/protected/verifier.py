"""Independent trusted reference: difference constraints by bounded relaxation.
This file is embedded into verifier.py when packaging (not a separate runtime mount).
"""
def solve(jobs, first=0, slip=None):
    ids=[j['id'] for j in jobs];by={j['id']:j for j in jobs};n=len(ids)
    edges=[]
    for j in jobs:
        for l in j['links']:
            w=l['lag']
            if l['type']!='SS':w+=by[l['from']]['duration']
            if l['type']=='FF':w-=j['duration']
            edges.append((l['from'],j['id'],w))
    def forward(lower):
        e={id:first for id in ids};e.update(lower)
        for _ in range(n):
            old=e.copy()
            for a,b,w in edges:e[b]=max(e[b],e[a]+w)
            if old==e:return e
        raise ValueError('cyclic oracle fixture')
    early=forward({});finish=max(early[id]+by[id]['duration'] for id in ids)
    latest={id:finish-by[id]['duration'] for id in ids}
    for _ in range(n):
        old=latest.copy()
        for a,b,w in edges:latest[a]=min(latest[a],latest[b]-w)
        if old==latest:break
    floats={id:latest[id]-early[id] for id in ids};critical={id for id in ids if floats[id]==0}
    tight={(a,b) for a,b,w in edges if a in critical and b in critical and early[b]==early[a]+w}
    paths=set()
    def trace(path):
        ns={b for a,b in tight if a==path[-1]}
        if ns:
            for b in ns:trace(path+(b,))
        else:paths.add(path)
    for id in critical-{b for a,b in tight}:trace((id,))
    violations={b for a,b,w in edges if by[b]['start']<by[a]['start']+w}|{id for id in ids if by[id]['start']<first}
    shifted=forward({slip['job']:early[slip['job']]+slip['days']}) if slip else early
    moved=max(shifted[id]+by[id]['duration'] for id in ids)
    return dict(early=early,late=latest,floats=floats,finish=finish,critical=sorted(critical),paths=[list(x) for x in sorted(paths)],violations=sorted(violations),slippedFinish=moved,delta=moved-finish)
from pathlib import Path
import json,re,time,copy
from playwright.async_api import TimeoutError as UITimeout

def field(text,label):
    m=re.search(r'(?:^|\n)\s*'+re.escape(label)+r'\s*:\s*([^\n]*)',text,re.I)
    return m.group(1).strip() if m else None

def normalized(text):
    return '\n'.join(line.strip() for line in text.replace('\r','').splitlines() if line.strip())

def parse_ledger(text,names):
    text=normalized(text)
    heading=re.compile(r'(?m)^('+ '|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True))+r')$')
    marks=list(heading.finditer(text));result={}
    for k,m in enumerate(marks):
        chunk=text[m.end():marks[k+1].start() if k+1<len(marks) else len(text)]
        row={}
        for label in ('Planned start','Duration','Planned end','Earliest start','Earliest end','Float'):
            value=field(chunk,label)
            if value is None or not re.fullmatch(r'-?\d+',value):return None
            row[label]=int(value)
        value=field(chunk,'Incoming')
        if value is None:return None
        incoming=set()
        if value!='None':
            for item in value.split(';'):
                match=re.fullmatch(r'\s*(.*?)\s*\|\s*(FS|SS|FF)\s*\|\s*lag\s*(\d+)\s*',item)
                if not match:return None
                incoming.add((match[1],match[2],int(match[3])))
        row['Incoming']=incoming
        if m[1] in result:return None
        result[m[1]]=row
    return result

def expected_ledger(jobs,names,r):
    return {names[j['id']]:{'Planned start':j['start'],'Duration':j['duration'],'Planned end':j['start']+j['duration'],'Earliest start':r['early'][j['id']],'Earliest end':r['early'][j['id']]+j['duration'],'Float':r['floats'][j['id']],'Incoming':{(names[l['from']],l['type'],l['lag']) for l in j['links']}} for j in jobs}

def report_matches(text,r,names,slip):
    text=normalized(text)
    for label,key in [('Earliest finish','finish'),('Slipped finish','slippedFinish'),('Finish movement','delta')]:
        if field(text,label)!=str(r[key]):return False
    for label,key in [('Planned violations','violations'),('Critical jobs','critical')]:
        value=field(text,label)
        if value is None:return False
        actual=set() if value=='None' else {s.strip() for s in value.split(';')}
        if actual!={names[id] for id in r[key]}:return False
    value=field(text,'Critical paths')
    if value is None:return False
    actual=set() if value=='None' else {tuple(v.strip() for v in p.split('→')) for p in value.split(';')}
    if actual!={tuple(names[id] for id in p) for p in r['paths']}:return False
    return (field(text,'Slip job') in names.values() if slip['days']==0 else field(text,'Slip job')==names[slip['job']]) and field(text,'Slip days')==str(slip['days'])

def timeline_matches(text,jobs,names,r):
    text=normalized(text)
    for j in jobs:
        name=names[j['id']]
        p=re.search(r'(?m)^'+re.escape(name)+r'\nPlanned:\s*(-?\d+)\s*→\s*(-?\d+)\nEarliest:\s*(-?\d+)\s*→\s*(-?\d+)\s*·\s*Float:\s*(-?\d+)',text)
        if not p or list(map(int,p.groups()))!=[j['start'],j['start']+j['duration'],r['early'][j['id']],r['early'][j['id']]+j['duration'],r['floats'][j['id']]]:return False
    return True

async def grade(page,ctx):
    if not ctx.get('baseline') or ctx['baseline'].get('capture_kind')!='native_hook_pre_edit':
        raise RuntimeError('Missing trusted pre-edit reference (infrastructure).')
    started=time.monotonic();page.set_default_timeout(650)
    assertions=[];events=[];records=ctx['fixture']['inbox'];approved=ctx['fixture']['approved']
    def nm(record):return {j['id']:j['name'] for j in record['jobs']}
    async def click(name):await page.get_by_role('button',name=name,exact=True).click()
    async def select(label,value):await page.get_by_label(label,exact=True).select_option(label=value)
    async def fill(label,value):await page.get_by_label(label,exact=True).fill(str(value))
    async def edition(record):await select('Refit edition',record['title']);await click('Schedule')
    async def region(name):return await page.get_by_role('region',name=name,exact=True).inner_text()
    async def state(record,jobs,slip,tag):
        names=nm(record);r=solve(jobs,record['firstDay'],slip)
        led=await region('Job ledger');rep=await region('Critical-path report');line=await region('Live schedule')
        results={'ledger':parse_ledger(led,names.values())==expected_ledger(jobs,names,r),'report':report_matches(rep,r,names,slip),'timeline':timeline_matches(line,jobs,names,r)}
        events.append({'tag':tag,'rendered_ledger':led,'rendered_report':rep,'rendered_timeline':line,'checks':results})
        return all(results.values())
    async def group(id,fn):
        before=time.monotonic()
        try:passed=bool(await fn());why=None
        except (UITimeout,AssertionError,ValueError,KeyError,TypeError) as e:
            passed=False;why=f'Visible workflow assertion unavailable: {type(e).__name__}: {str(e)[:220]}'
        # Browser/process death is not converted to a scored wrong answer.
        assertions.append({'id':id,'passed':passed});events.append({'group':id,'seconds':round(time.monotonic()-before,4),'failure':why})
    async def editor():
        control=page.get_by_label('Job to edit',exact=True)
        if not await control.is_visible():await page.get_by_text('Edit job and dependencies',exact=True).click()
    def initial(record):return copy.deepcopy(approved[record['id']]),{'job':'strip','days':0}
    async def preview():
        good=True
        for ri,record in enumerate(records):
            await edition(record);await click('Received chart')
            stage=page.get_by_label('Chart paper',exact=True)
            for k in range(3):
                await select('Chart sheet',f'Sheet {k+1}');await click('Read at 85%')
                good &= await stage.is_visible()
                await stage.screenshot(path=str(Path(ctx['output_dir'])/f'preview-{ri}-{k}.png'))
            # Actual viewport content must move, not just a zoom status label.
            await select('Chart sheet','Sheet 1');await click('Top left')
            before=await stage.screenshot();await click('Pan right');await click('Pan down');after=await stage.screenshot()
            good &= before!=after
            await click('Top left');await click('Fit sheet');fit=await stage.screenshot()
            good &= fit!=before
        await click('Schedule');return good
    async def complete():
        good=True
        for record in records:
            await edition(record);await click('Reset');jobs,slip=initial(record)
            good &= await state(record,jobs,slip,'complete-'+record['id'])
        return good
    async def edits():
        good=True
        for record in records:
            await edition(record);await click('Reset');jobs,slip=initial(record);names=nm(record)
            await editor();await select('Job to edit',names['planks']);job=next(j for j in jobs if j['id']=='planks')
            job['duration']+=2;job['start']+=1
            await fill('Planned start day',job['start']);await fill('Duration days',job['duration']);await click('Apply job edit')
            good &= await state(record,jobs,slip,'duration-'+record['id'])
            await select('Job to edit',names['tank']);tank=next(j for j in jobs if j['id']=='tank');tank['links'][0]['type']='FS'
            await page.get_by_label(re.compile('^Type for '+re.escape(names['survey']+' to '+names['tank']))).select_option('FS')
            good &= await state(record,jobs,slip,'retype-'+record['id'])
            await select('Job to edit',names['glaze']);glaze=next(j for j in jobs if j['id']=='glaze');glaze['links']=[l for l in glaze['links'] if l['from']!='strip']
            await page.get_by_role('button',name=re.compile('^Remove '+re.escape(names['strip']+' to '+names['glaze']))).click()
            good &= await state(record,jobs,slip,'remove-long-'+record['id'])
            await select('New predecessor',names['loom']);await select('New link type','SS');await fill('New link lag days',2);await click('Add dependency');glaze['links'].append({'from':'loom','type':'SS','lag':2})
            good &= await state(record,jobs,slip,'add-'+record['id'])
            await click('Undo');glaze['links'].pop();good &= await state(record,jobs,slip,'undo-'+record['id'])
            await click('Cancel');jobs,slip=initial(record);good &= await state(record,jobs,slip,'cancel-'+record['id'])
            # Signed planned dates are reportable violations, never earliest bounds.
            await click('Reset');jobs,slip=initial(record)
            await editor();await select('Job to edit',names['strip'])
            root=next(j for j in jobs if j['id']=='strip')
            root['start']=record['firstDay']
            await fill('Planned start day',root['start']);await click('Apply job edit')
            good &= await state(record,jobs,slip,'planned-at-first-'+record['id'])
            root['start']=record['firstDay']-1
            await fill('Planned start day',root['start'])
            good &= await page.get_by_label('Planned start day',exact=True).evaluate('(el) => el.checkValidity()')
            await click('Apply job edit')
            good &= await state(record,jobs,slip,'planned-before-first-'+record['id'])
            good &= not await page.get_by_role('alert').is_visible()
            await click('Save');await page.reload(wait_until='load');await edition(record)
            good &= await state(record,jobs,slip,'planned-negative-reload-'+record['id'])
            await editor();await select('Job to edit',names['strip'])
            await fill('Planned start day',record['firstDay']);await click('Apply job edit')
            await click('Cancel')
            good &= await state(record,jobs,slip,'planned-negative-cancel-'+record['id'])
            await click('Reset');jobs,slip=initial(record)
            good &= await state(record,jobs,slip,'planned-negative-reset-'+record['id'])
        return good
    async def cycle():
        record=records[0];await edition(record);await click('Reset');await editor();names=nm(record)
        await select('Job to edit',names['strip']);await select('New predecessor',names['trial']);await select('New link type','FS');await fill('New link lag days',0);await click('Add dependency')
        alert=page.get_by_role('alert');good=await alert.is_visible() and bool(re.search('cycle',await alert.inner_text(),re.I))
        await click('Received chart');good &= await page.get_by_label('Chart paper',exact=True).is_visible()
        await click('Reading guide');good &= await page.get_by_role('region',name='Reading guide',exact=True).is_visible()
        await click('Schedule');await click('Undo');jobs,slip=initial(record)
        return good and await state(record,jobs,slip,'cycle-undo')
    async def persistence():
        first,second=records;await edition(first);await click('Reset');jobs,slip=initial(first);names=nm(first);await editor()
        await select('Job to edit',names['tank']);job=next(j for j in jobs if j['id']=='tank');job['duration']+=3
        await fill('Duration days',job['duration']);await click('Apply job edit');job['links'][0]['type']='FS'
        await page.get_by_label(re.compile('^Type for '+re.escape(names['survey']+' to '+names['tank']))).select_option('FS')
        slip={'job':'frames','days':4};await select('Slip job',names['frames']);await fill('Slip days',4);await click('Preview slip')
        await fill('Yard notes','Port bracket — keep the chalk marks');await click('Save')
        await edition(second);await click('Reset');other,oslip=initial(second);good=await state(second,other,oslip,'other-untouched')
        await editor();await select('Job to edit',nm(second)['deck']);deck=next(j for j in other if j['id']=='deck');deck['start']+=2
        await fill('Planned start day',deck['start']);await click('Apply job edit');await click('Save')
        await edition(first);good &= await state(first,jobs,slip,'saved-first')
        await page.reload(wait_until='load');await click('Schedule');good &= await state(first,jobs,slip,'reload-first')
        good &= await page.get_by_label('Yard notes',exact=True).input_value()=='Port bracket — keep the chalk marks'
        await click('Reset');base,bs=initial(first);good &= await state(first,base,bs,'reset-first')
        good &= await page.get_by_label('Yard notes',exact=True).input_value()=='Port bracket — keep the chalk marks'
        await edition(second);good &= await state(second,other,oslip,'independent-second');await click('Reset')
        return good
    async def slip_export():
        good=True
        for record in records:
            await edition(record);await click('Reset');jobs,slip=initial(record);names=nm(record)
            slip={'job':'frames','days':5};await select('Slip job',names['frames']);await fill('Slip days',5);await click('Preview slip')
            good &= await state(record,jobs,slip,'slip-'+record['id'])
            await click('Export draft');text=await region('Export snapshot');r=solve(jobs,record['firstDay'],slip)
            # Export includes the same complete relevant semantic state, not a success flag.
            good &= parse_ledger(text,names.values())==expected_ledger(jobs,names,r)
            good &= report_matches(text,r,names,slip)
            good &= 'Yard notes:' in text
            await click('Close export');await click('Cancel')
        return good
    for id,fn in [('received_preview',preview),('both_complete_integrations',complete),('live_jobs_and_links',edits),('cycle_undo_cancel',cycle),('save_reload_independent_reset',persistence),('slip_and_complete_export',slip_export)]:await group(id,fn)
    elapsed=round(time.monotonic()-started,4)
    (Path(ctx['output_dir'])/'ui-observations.json').write_text(json.dumps({'elapsed_seconds':elapsed,'scene_timeout_ms':30000,'events':events},indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':assertions}
