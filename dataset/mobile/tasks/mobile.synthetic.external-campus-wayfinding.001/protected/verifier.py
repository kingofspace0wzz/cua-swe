"""Behavioral UI verifier; independent exhaustive oracle, no client internals.
No assertion reads candidate source/storage/private JS or asks the app for a score.
Missing/disabled expected visible controls return false. Browser/hook errors remain
infrastructure exceptions. Link-ID order admits any tied permitted shortest path.
"""
from pathlib import Path
import json, re, math
from PIL import Image, ImageChops, ImageStat

def compact(text): return ' '.join(text.split())
def oracle(c, origin, destination, step_free):
    adjacent={s['id']:[] for s in c['stops']}
    for e in c['walk_links']:
        if e['state']=='closed' or (step_free and e['access']!='step-free'): continue
        adjacent[e['from_stop']].append((e['to_stop'],e))
        if e['flow']=='both': adjacent[e['to_stop']].append((e['from_stop'],e))
    best=math.inf
    def walk(node,seen,total):
        nonlocal best
        if node==destination: best=min(best,total);return
        if total>=best:return
        for end,edge in adjacent[node]:
            if end not in seen:walk(end,seen|{end},total+edge['travel_m'])
    walk(origin,{origin},0)
    return best

async def click(page,name):
    control=page.get_by_role('button',name=name,exact=isinstance(name,str))
    if not await control.count():return False
    control=control.first
    if not await control.is_visible() or not await control.is_enabled():return False
    await control.click(timeout=1500)
    return True

async def campus(page,c):
    return await click(page,'Change campus') and await click(page,c['title'])

async def choose(page,c,origin,destination,step_free):
    if not await click(page,'Plan trip'):return False
    labels={s['id']:s for s in c['stops']}
    for key,value in [('Origin',origin),('Destination',destination)]:
        if not await click(page,re.compile('^'+key+':')):return False
        s=labels[value]
        if not await click(page,f"{s['label']} · Level {s['level']}"):return False
    desired='Step-free: '+('on' if step_free else 'off')
    if not await page.get_by_role('button',name=desired,exact=True).count():
        if not await click(page,re.compile('^Step-free:')):return False
    return bool(await page.get_by_role('button',name=desired,exact=True).count())

async def route_check(page,c,origin,destination,step_free,events):
    text=await page.locator('body').inner_text()
    # Prefer the visible route region, but a different structure with the same
    # user-visible controls/directions works too. No required HTML tags or IDs.
    region=page.get_by_role('region',name='Route result',exact=True)
    route_text=await region.inner_text() if await region.count() else text
    best=oracle(c,origin,destination,step_free)
    if math.isinf(best):
        ok=bool(re.search(r'(no route available|no permitted route|route unavailable)',route_text,re.I))
        # No unavailable message alongside a stale suggested connector sequence.
        ok=ok and not any(re.search(r'(?<!\w)'+re.escape(e['id'])+r'(?!\w)',route_text) for e in c['walk_links'])
        events.append({'campus':c['id'],'origin':origin,'destination':destination,'step_free':step_free,'expected':'unavailable','observed':route_text,'passed':ok});return ok
    lengths=re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:m\b|metres?\b|meters?\b)',route_text,re.I)
    if not lengths or abs(float(lengths[0])-best)>0.01:
        events.append({'campus':c['id'],'origin':origin,'destination':destination,'step_free':step_free,'expected_m':best,'observed':route_text,'passed':False});return False
    links={e['id']:e for e in c['walk_links']}; stops={s['id']:s for s in c['stops']}
    pattern=r'(?<!\w)('+ '|'.join(re.escape(k) for k in links)+r')(?!\w)'
    shown=list(re.finditer(pattern,route_text));cursor=origin;cost=0;ok=True
    last=0
    for found in shown:
        edge=links[found.group(1)]
        if cursor==edge['from_stop']:end=edge['to_stop']
        elif cursor==edge['to_stop'] and edge['flow']=='both':end=edge['from_stop']
        else:ok=False;break
        if edge['state']!='open' or (step_free and edge['access']!='step-free'):ok=False;break
        # Directions must name the traversed stops; the sample UI places those
        # before connector metadata. A refactor may put metadata first instead.
        next_match=next((m.start() for m in shown if m.start()>found.start()),len(route_text))
        nearby=route_text[max(last-70,0):next_match]
        if not all(s['label'] in nearby for s in (stops[cursor],stops[end])):ok=False
        for sid in (cursor,end):
            level=stops[sid]['level']
            if not re.search(r'(?:\bL|\blevel\s*|\bfloor\s*)'+str(level)+r'\b',nearby,re.I):ok=False
        cost+=edge['travel_m'];cursor=end;last=found.end()
    ok=ok and cursor==destination and abs(cost-best)<0.01
    if origin!=destination and not shown:ok=False
    events.append({'campus':c['id'],'origin':origin,'destination':destination,'step_free':step_free,'expected_m':best,'observed':route_text,'passed':bool(ok)})
    return bool(ok)

def same_image(reference,observed):
    with Image.open(reference) as r,Image.open(observed) as a:
        # Compare attachment pixels, not source bytes/URLs or surrounding UI.
        r=r.convert('RGB').resize((360,450));a=a.convert('RGB').resize((360,450))
        delta=ImageStat.Stat(ImageChops.difference(r,a))
        return max(delta.mean)<3.0

async def grade(page,ctx):
    if not ctx['baseline'] or ctx['baseline']['capture_kind']!='native_hook_pre_edit':
        raise RuntimeError('actual pre-edit capture required')
    baseline=ctx['baseline']['state'];root=Path(ctx['output_dir']);events=[];results={}
    a,b=ctx['fixture']['inbox']['campuses']
    async def trip(c,o,d,s):
        if not await choose(page,c,o,d,s):
            events.append({'missing_visible_trip_control':True});return False
        return await route_check(page,c,o,d,s,events)
    entered=await campus(page,a)
    initial=[]
    for o,d,s in [('A','F',False),('A','E',False)]:initial.append(entered and await trip(a,o,d,s))
    results['permitted_shortest_route']=all(initial)
    detours=[]
    for o,d,s in [('A','F',True),('C','F',True)]:detours.append(entered and await trip(a,o,d,s))
    results['step_free_detour']=all(detours)
    directed=[]
    for o,d,s in [('F','A',False),('A','G',True),('A','A',True)]:directed.append(entered and await trip(a,o,d,s))
    results['direction_and_unavailable']=all(directed)
    saved=entered and await trip(a,'C','F',True) and await click(page,'Save trip')
    saved=saved and await choose(page,a,'A','E',False)
    saved=saved and await click(page,'Open saved trip')
    # Ordinary reload: no seeding, setters, storage reads or injected interactions.
    await page.reload(wait_until='load')
    expected_buttons=['Origin: Lift base','Destination: Studio','Step-free: on']
    selection=all([bool(await page.get_by_role('button',name=n,exact=True).count()) for n in expected_buttons])
    saved_text=await page.locator('body').inner_text()
    saved=saved and selection and 'Juniper Annex · Lift base → Studio · Step-free on' in compact(saved_text)
    saved=saved and await route_check(page,a,'C','F',True,events)
    results['saved_trip_and_reload']=bool(saved)
    entered_b=await campus(page,b)
    second=[]
    # Same disclosed contract, different stops, order, direction, transition and costs.
    for o,d,s in [('P','T',False),('P','T',True),('T','P',True),('T','P',False),('R','T',True),('P','U',True)]:
        second.append(entered_b and await trip(b,o,d,s))
    await page.reload(wait_until='load')
    second.append(b['title'] in (await page.locator('body').inner_text()))
    results['second_campus_generalization']=all(second)
    reports_ok=True;maps_ok=True
    for c in (a,b):
        if not await campus(page,c):reports_ok=False;maps_ok=False;continue
        if not await click(page,'Original map'):maps_ok=False
        else:
            image=page.get_by_role('img',name=re.compile(re.escape(c['title'])+'.*map',re.I))
            if not await image.count():maps_ok=False
            else:
                target=root/(c['id']+'-graded-map.png')
                await image.first.screenshot(path=str(target),timeout=1500)
                maps_ok=maps_ok and same_image(Path(ctx['baseline_dir'])/baseline['campuses'][c['id']]['map_image'],target)
        if not await click(page,'Routing report'):reports_ok=False;continue
        for i,report in enumerate(c['report']['pages']):
            rendered=await page.locator('body').inner_text()
            # Match content, not tags, columns, CSS or a private DOM implementation.
            needed=[report['title'],*(report.get('paragraphs') or [])]
            if report.get('table'):
                needed+=report['table']['columns']
                needed += [str(cell) for row in report['table']['rows'] for cell in row]
            observed=compact(rendered)
            original=compact(baseline['campuses'][c['id']]['report_pages'][i])
            page_ok=all(compact(s) in observed and compact(s) in original for s in needed)
            reports_ok=reports_ok and page_ok
            events.append({'report':c['id'],'page':i+1,'passed':page_ok})
            if i+1<len(c['report']['pages']) and not await click(page,'Next page'):
                reports_ok=False;break
    results['original_artifacts_preserved']=reports_ok and maps_ok
    await click(page,'Plan trip')
    await page.screenshot(path=str(root/'grade-final.png'),full_page=False)
    (root/'ui-observations.json').write_text(json.dumps(events,indent=2))
    return {'execution':'complete','errors':[],'expected_assertions':ctx['expected_assertions'],'assertions':[{'id':key,'passed':bool(results[key])} for key in ctx['expected_assertions']]}
