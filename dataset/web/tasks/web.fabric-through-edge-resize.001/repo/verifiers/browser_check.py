#!/usr/bin/env python3
"""Bounded native through-edge check. 0 covered pass; 1 observed behavior; 2 infrastructure.
The constructor does not execute this program. It owns the existing service/app
startup and observes only screenshots, canvas layout and visible zoom readouts.
"""
import sys
sys.dont_write_bytecode = True
import copy, json, math, os, re, socket, subprocess, tempfile, time, traceback, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
SERVICE = WORKSPACE.parent / 'env/service.mjs'

class CoverageError(Exception): pass
class StopWorkflow(Exception): pass

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def healthy(p):
    for _ in range(100):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=.5) as r:
                if r.status == 200: return
        except Exception:
            time.sleep(.1)
    raise RuntimeError(f'service health timeout on {p}')

def screen(scene, box, point):
    from visible import projection
    a,b,c,d,e,f = projection(scene); x,y = point
    return (box[0]+a*x+c*y+e, box[1]+b*x+d*y+f)

def scene_point(scene, box, point):
    from visible import projection
    a,b,c,d,e,f = projection(scene)
    # Inverse of the independently composed camera and containing-frame plane.
    x,y = point[0]-box[0]-e, point[1]-box[1]-f
    det = a*d-b*c
    return ((d*x-c*y)/det, (-b*x+a*y)/det)

def edge_delta(scene, dx, dy):
    angle = math.radians(scene['object']['angle'])
    return (math.cos(angle)*dx-math.sin(angle)*dy, math.sin(angle)*dx+math.cos(angle)*dy)

def in_initial_axes(scene, vertices):
    """Public endpoints in the initial Blue axes, not application resize state.
    Endpoint ordering is only an oracle convention; no native key is implied.
    """
    s = copy.deepcopy(scene)
    cx,cy = scene['object']['left'],scene['object']['top']
    s['expected_polygon'] = [(cx+dx,cy+dy) for dx,dy in
                             (edge_delta(scene,x,y) for x,y in vertices)]
    return s

def parent_corners(scene):
    if 'expected_polygon' in scene: return scene['expected_polygon']
    w,h = scene['object']['width']/2,scene['object']['height']/2
    return in_initial_axes(scene,[(-w,-h),(w,-h),(w,h),(-w,h)])['expected_polygon']

def polygon_center(scene):
    corners = parent_corners(scene)
    return tuple(sum(p[i] for p in corners)/4 for i in (0,1))

def rotate(scene, angle):
    s = copy.deepcopy(scene); cx,cy = polygon_center(scene)
    co,si = math.cos(math.radians(angle)),math.sin(math.radians(angle))
    s['expected_polygon'] = [(cx+co*(x-cx)-si*(y-cy),cy+si*(x-cx)+co*(y-cy))
                             for x,y in parent_corners(scene)]
    return s

def translate(scene, dx, dy):
    s = copy.deepcopy(scene)
    s['expected_polygon'] = [(x+dx,y+dy) for x,y in parent_corners(scene)]
    return s

# Collect each label/value association once, before ancestors can combine it
# with unrelated status numbers. No app selectors or preferred readout subtree.
ZOOM_READOUTS_JS = r"""() => {
 const labelPattern = /\b(?:zoom|magnification|scale(?:\s+factor)?)\b/i;
 const readings = [], consumed = new Set();
 const firstSummary = e => Array.from(e.children).find(n => n.tagName==='SUMMARY');
 const hiddenByClosedDetails = e => {
  for (let child=e, p=e.parentElement; p; child=p, p=p.parentElement) {
   if (p.tagName==='DETAILS' && !p.open && child!==firstSummary(p)) return true;
  }
  return false;
 };
 const visible = e => {
  if (hiddenByClosedDetails(e)) return false;
  for (let p=e; p; p=p.parentElement) {
   const s=getComputedStyle(p);
   if (s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || s.opacity==='0') return false;
  }
  const r=e.getBoundingClientRect();
  return !!(r.width && r.height);
 };
 const displayedValue = e => e.tagName==='SELECT'
  ? Array.from(e.selectedOptions, o=>o.label || o.textContent).join(' ')
  : e.value;
 // Native labels (wrapped or for=), aria-labelledby and aria-label associate a
 // displayed field value explicitly. Read .value, not the initial attribute or
 // a select's opaque option ID. Range/password/check controls do not display it.
 for (const e of document.querySelectorAll('input, textarea, select, output')) {
  if (!visible(e) || (e.tagName==='INPUT' && !/^(text|number|search|tel|url|email)$/.test(e.type))) continue;
  const labels = Array.from(e.labels || []).filter(visible);
  const refs = (e.getAttribute('aria-labelledby') || '').split(/\s+/)
   .map(id=>document.getElementById(id)).filter(n=>n && visible(n));
  const names = [...labels, ...refs];
  const label = names.map(n=>n.innerText).join(' ') || e.getAttribute('aria-label') || '';
  if (!labelPattern.test(label)) continue;
  readings.push({label, value:displayedValue(e)});
  consumed.add(e);
  names.forEach(n=>consumed.add(n));
 }
 const walk = e => {
  if (consumed.has(e) || /^(SCRIPT|STYLE|TEMPLATE|NOSCRIPT)$/.test(e.tagName)) return '';
  if (hiddenByClosedDetails(e)) return '';
  const s=getComputedStyle(e);
  if (s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || s.opacity==='0') return '';
  if (e.tagName==='DETAILS' && !e.open) {
   const summary=firstSummary(e);
   return summary ? walk(summary) : '';
  }
  let text;
  if (/^(INPUT|TEXTAREA|SELECT|OUTPUT)$/.test(e.tagName)) {
   if (!visible(e) || (e.tagName==='INPUT' && !/^(text|number|search|tel|url|email)$/.test(e.type))) return '';
   text=displayedValue(e);
  } else {
   text=Array.from(e.childNodes, n=>n.nodeType===Node.TEXT_NODE
    ? (visible(e) || s.display==='contents' ? n.textContent : '')
    : n.nodeType===Node.ELEMENT_NODE ? walk(n) : '').join(' ');
  }
  if (!text.trim() && visible(e)) text=e.getAttribute('aria-label') || '';
  // A standalone numeric/percentage display is also a readout. Do not
  // require literal zoom/magnification wording or a preferred DOM subtree.
  if (/^\s*[+-]?\d+(?:\.\d+)?\s*(?:%|[x×])?\s*$/.test(text)) {
   readings.push({label:'standalone numeric display', value:text});
   return '';
  }
  if (labelPattern.test(text) && /\d/.test(text)) {
   readings.push(text);
   return ''; // Never reinterpret this label in an aggregate ancestor.
  }
  return text;
 };
 walk(document.body);
 return readings;
}"""

def zoom_values(texts):
 # Inputs are already associated, non-overlapping readouts, not aggregate
 # ancestor innerText. Every statement must agree; a heading cannot hide a
 # wrong live value. Explicit labeled fields with no numeric value also fail.
 values=[]
 for text in texts:
  if isinstance(text,dict):
   matches=list(re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*(%|[x×])?',text['value'],re.I))
   values.extend(float(m[1])/(100 if m[2]=='%' else 1) for m in matches)
   if not matches:values.append(float('inf'))
   continue
  matches=list(re.finditer(r'\b(?:zoom|magnification|scale(?:\s+factor)?)\b[^\d]*?([+-]?\d+(?:\.\d+)?)\s*(%|[x×])?',text,re.I))
  if not matches:
   matches=list(re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*(%|[x×])?[^\d]*?\b(?:zoom|magnification|scale(?:\s+factor)?)\b',text,re.I))
  for m in matches:values.append(float(m[1])/(100 if m[2]=='%' else 1))
 return values

def main():
    # All raw evidence lives outside protected verifier source. A short writable
    # /tmp directory is the ordinary fallback, not a directory beside this file.
    base = os.environ.get('CUA_SWE_VERIFIER_ARTIFACTS')
    artifact_error = None
    try:
        out = Path(base) if base else Path(tempfile.mkdtemp(prefix='fabric-through-edge-', dir='/tmp'))
        out.mkdir(parents=True, exist_ok=True)
        probe = out/'.native-write-probe'
        probe.write_text(''); probe.unlink()
    except Exception as error:
        artifact_error = dict(kind='artifact-directory', raw=repr(error), traceback=traceback.format_exc())
        out = Path(tempfile.mkdtemp(prefix='fabric-through-edge-fallback-', dir='/tmp'))
    evidence = Path(tempfile.mkdtemp(prefix='native-', dir=out))
    result = dict(checker='fabric-native-through-edge-01', observations=[], actions=[],
                  runtime_errors=[], coverage_issues=[], workflow_stops=[], required_workflows=['nested-B', 'single-C'],
                  completed_workflows=[], evidence_dir=str(evidence), native_executed=True)
    if artifact_error: result['runtime_errors'].append(artifact_error)
    processes, logs = [], []
    scratch = tempfile.TemporaryDirectory(prefix='fv-', dir='/tmp')
    def save():
        (out/'native-results.json').write_text(json.dumps(result, indent=2))
    def record_action(kind, **details):
        item = dict(index=len(result['actions']), kind=kind, time=time.time(), **details)
        result['actions'].append(item)
        with (evidence/'actions.jsonl').open('a') as f: f.write(json.dumps(item)+'\n')
    try:
        from visible import check, projection
        from playwright.sync_api import sync_playwright
        sp, ap = port(), port()
        while ap == sp: ap = port()
        for name, cmd, env in [
            ('service', ['node', str(SERVICE), '--port', str(sp)], dict(os.environ, TMPDIR=scratch.name)),
            ('app', ['node', str(WORKSPACE/'server.mjs'), '--port', str(ap)],
             dict(os.environ, TMPDIR=scratch.name, CUA_SWE_EXTERNAL_SERVICE_ORIGIN=f'http://127.0.0.1:{sp}'))]:
            log = (evidence/(name+'.log')).open('w'); logs.append(log)
            processes.append(subprocess.Popen(cmd, cwd=WORKSPACE, env=env, stdout=log, stderr=log))
        healthy(sp); healthy(ap)
        bodies = {}
        for preset in 'BC':
            with urllib.request.urlopen(f'http://127.0.0.1:{sp}/scene?preset={preset}', timeout=3) as r:
                bodies[preset] = r.read()
            (evidence/('feed-'+preset+'.json')).write_bytes(bodies[preset])
        with sync_playwright() as pw:
            opts = dict(headless=True, args=['--no-sandbox'], env=dict(os.environ, TMPDIR=scratch.name))
            if os.environ.get('CUA_SWE_VERIFIER_CHROME_PATH'):
                opts['executable_path'] = os.environ['CUA_SWE_VERIFIER_CHROME_PATH']
            browser = pw.chromium.launch(**opts)
            context = browser.new_context(viewport={'width':1000, 'height':780}, device_scale_factor=1, service_workers='block')
            page = context.new_page()
            page.on('pageerror', lambda e: result['runtime_errors'].append(dict(kind='pageerror', raw=str(e))))
            def console_message(message):
                with (evidence/'console.jsonl').open('a') as log:
                    log.write(json.dumps(dict(type=message.type, text=message.text))+'\n')
            page.on('console', console_message)
            held = False
            def move(point):
                record_action('mouse.move', point=point)
                page.mouse.move(*point)
            def down():
                nonlocal held
                record_action('mouse.down', button='left'); page.mouse.down(); held = True
            def up():
                nonlocal held
                record_action('mouse.up', button='left'); page.mouse.up(); held = False
            def load(preset, artwork='nested'):
                record_action('navigate', preset=preset, artwork=artwork)
                body = bodies[preset]; page.unroute('**/scene*')
                page.route('**/scene*', lambda route: route.fulfill(status=200, content_type='application/json', body=body))
                page.goto(f'http://127.0.0.1:{ap}/?preset={preset}&artwork={artwork}', wait_until='networkidle', timeout=15000)
                page.wait_for_timeout(150)
                # Read-only rendered layout; never read application objects/state.
                boxes = page.locator('canvas').evaluate_all('(els)=>els.map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})')
                (evidence/('layout-'+artwork+'-'+preset+'.json')).write_text(json.dumps(boxes))
                box = next((b for b in boxes if abs(b[2]-800)<1 and abs(b[3]-600)<1), None)
                if not box: raise CoverageError('existing 800x600 artboard not discoverable')
                s = json.loads(body)
                if s['object'].get('originX') != 'center' or s['object'].get('originY') != 'center':
                    raise CoverageError('protected feed origin unsupported')
                s['artwork'] = artwork
                if artwork == 'nested':
                    s['fixture_center'] = [s['object']['left'], s['object']['top']]
                    s['object'] = dict(left=0, top=0, width=60, height=36, angle=15,
                                       originX='center', originY='center', padding=0)
                return s, box
            def snapshot(label, scene, box, selected=True, scored=True):
                page.wait_for_timeout(100)
                path = evidence/(label+'.png'); page.screenshot(path=str(path))
                observation = dict(label=label, screenshot=str(path), expected=copy.deepcopy(scene), box=box,
                                   action_index=len(result['actions'])-1, scored=scored, errors=[], metrics={})
                result['observations'].append(observation); save()
                if not scored: return observation
                if result['runtime_errors']:
                    observation['coverage_issues'] = ['runtime errors precede pixel observation']
                    raise CoverageError('page runtime error; screenshot retained')
                errors, metrics = check(path, scene, box, selected=selected)
                observation.update(errors=errors, metrics=metrics)
                save()
                readings = page.evaluate(ZOOM_READOUTS_JS); values = zoom_values(readings)
                zoom = math.hypot(*scene['viewportTransform'][:2])
                # Recognized numeric readouts still must agree. An equivalent
                # label alone cannot fail; camera geometry is checked in pixels.
                if values and any(abs(v-zoom)>.001 for v in values): errors.append('visible camera zoom value')
                if not values: metrics.setdefault('coverage_issues', []).append('numeric camera readout not recognized; no label-based failure')
                observation['visible_text'] = page.locator('body').inner_text()
                observation.update(errors=errors, metrics=metrics, readouts=readings, zoom_values=[v if math.isfinite(v) else str(v) for v in values], expected_zoom=zoom)
                result['coverage_issues'].extend(dict(label=label, reason=x) for x in metrics.get('coverage_issues', []))
                save()
                print(label+': '+('FAIL '+', '.join(errors) if errors else 'COVERAGE' if metrics.get('coverage_issues') else 'PASS'), flush=True)
                return observation
            def acquire(observation, control=None, offset=(0,0), fill=False):
                metrics = observation['metrics']
                if observation['errors']: raise StopWorkflow('prior visible behavior diverged; dependent acquisition stopped')
                if metrics.get('coverage_issues'): raise CoverageError('prior observation unsupported; dependent acquisition stopped')
                if fill:
                    point = metrics.get('fill_point')
                    if point is None: raise CoverageError('ordinary fill acquisition not supported by visible blue patch')
                    return point
                center = metrics.get('rotation_marker') if control == 'rotation' else metrics.get('input_controls', {}).get(str(control))
                if center is None: raise CoverageError(f'unsupported visible acquisition: {control}')
                from PIL import Image
                im = Image.open(observation['screenshot']).convert('RGB')
                ox,oy,bw,bh = observation['box']
                def supported_pixel(x,y):
                    return ox <= x < ox+bw and oy <= y < oy+bh and 0 <= x < im.width and 0 <= y < im.height
                def opaque_red(x,y):
                    if not supported_pixel(x,y): return False
                    r,g,b = im.getpixel((x,y))
                    return r>155 and r-g>75 and r-b>75
                def core(x,y):
                    return all(opaque_red(x+dx,y+dy) for dx,dy in [(0,0),(-1,0),(1,0),(0,-1),(0,1)])
                desired = (center[0]+offset[0],center[1]+offset[1])
                if core(round(desired[0]),round(desired[1])): return desired
                # Find a genuinely supported small grab displacement in the
                # discovered marker, not a guessed screen/control-key position.
                blob = min(metrics['markers'],key=lambda m: math.dist(m['center'],center))
                choices = []
                for y in range(math.ceil(center[1]-blob['height']/2),math.floor(center[1]+blob['height']/2)+1):
                    for x in range(math.ceil(center[0]-blob['width']/2),math.floor(center[0]+blob['width']/2)+1):
                        radius = math.dist((x,y),center)
                        if radius <= 4.5 and (offset==(0,0) or radius>=1.5) and core(x,y):
                            choices.append((x,y))
                if not choices and ('light-ring' in [blob['kind'],*blob.get('representations',[])]):
                    # Equivalent hollow controls: use a visible ring position.
                    for y in range(math.ceil(center[1]-blob['height']/2),math.floor(center[1]+blob['height']/2)+1):
                        for x in range(math.ceil(center[0]-blob['width']/2),math.floor(center[0]+blob['width']/2)+1):
                            if (offset==(0,0) or math.dist((x,y),center)>=1.5) and supported_pixel(x,y) and (opaque_red(x,y) or min(im.getpixel((x,y)))>215):
                                choices.append((x,y))
                if not choices: raise CoverageError('no visibly supported grab position on discovered marker')
                return min(choices,key=lambda q: math.dist(q,desired))
            def gesture(label, current, scene, box, control, expected_at, pointer_at, offset=(0,0), fill=False, thorough=True, checkpoints=(3,6)):
                def safe(point):
                    x,y,w,h = box
                    if not (x+12 <= point[0] <= x+w-12 and y+12 <= point[1] <= y+h-12):
                        raise CoverageError('planned input is not safely inside the visible artboard')
                    return point
                start = safe(acquire(current, control, offset, fill))
                # Validate the complete planned path before taking ownership.
                for k in range(1,7): safe(pointer_at(start,k/6))
                observed_center = (current['metrics'].get('rotation_marker') if control=='rotation'
                                   else current['metrics'].get('input_controls', {}).get(str(control)))
                actual_offset = [start[i]-observed_center[i] for i in (0,1)] if observed_center else None
                record_action('acquisition', label=label, geometric_location=control,
                              observed_center=observed_center, start=start,
                              requested_offset=offset, grab_offset=actual_offset)
                move(start); down()
                if thorough:
                    acq = snapshot(label+'-acquired', scene, box)
                    if acq['errors']:
                        up(); snapshot(label+'-released-at-acquisition', scene, box, scored=False)
                        raise StopWorkflow('acquisition changed geometry')
                    if acq['metrics'].get('coverage_issues'):
                        up(); snapshot(label+'-released-unsupported-acquisition',scene,box,scored=False)
                        raise CoverageError('acquired observation unsupported')
                final, next_scene = None, scene
                for k in range(1,7):
                    t = k/6
                    move(pointer_at(start, t))
                    if k == 6 or (thorough and k in checkpoints):
                        next_scene = expected_at(t)
                        final = snapshot(label+('-preview' if k==6 else f'-preview-{k}-of-6'), next_scene, box)
                        if final['errors'] or final['metrics'].get('coverage_issues'):
                            up(); move((940,740)); snapshot(label+'-release-after-stop', next_scene, box, scored=False)
                            raise StopWorkflow('preview diverged or observation unsupported; no further dependent input')
                up(); move((940,740)); final = snapshot(label+'-released', next_scene, box)
                if final['errors']: raise StopWorkflow('release behavior diverged')
                if final['metrics'].get('coverage_issues'): raise CoverageError('released observation unsupported')
                return next_scene, final
            def linear_pointer(scene, dx, dy):
                a,b,c,d,_,_ = projection(scene)
                return lambda start,t: (start[0]+t*(a*dx+c*dy), start[1]+t*(b*dx+d*dy))
            def select_blue(label, scene, box):
                unselected = snapshot(label+'-unselected', scene, box, selected=False)
                point = acquire(unselected, fill=True)
                record_action('native-click-blue', label=label, point=point)
                move(point); down(); up(); move((940,740))
                selected = snapshot(label+'-selected', scene, box)
                if selected['errors']: raise StopWorkflow('selection geometry diverged')
                if selected['metrics'].get('coverage_issues'): raise CoverageError('selection observation unsupported')
                return selected
            # Bounded primary crossing sequence plus one compact independent
            # Single segment. All control numbers below index expected geometric
            # corners/midpoints; they are never Fabric names or signed axes.
            for label, preset, artwork in [('nested-B','B','nested'),('single-C','C','single')]:
                try:
                    s, box = load(preset, artwork)
                    obs = select_blue(label,s,box) if artwork == 'nested' else snapshot(label+'-selected',s,box)
                    initial = copy.deepcopy(s)
                    ex,ey = edge_delta(initial,1,0); a,b,c,d,_,_ = projection(initial)
                    vx,vy = a*ex+c*ey,b*ex+d*ey; length = math.hypot(vx,vy)
                    off = (3*vx/length,3*vy/length)
                    if artwork == 'nested':
                        # Fixed midpoint (-30,0); moving midpoint (30-96t,0).
                        # t=1/6 and t=1 have substantial area. Ordinary moves
                        # traverse collapse; no zero-area observation/acquisition.
                        dx,dy = edge_delta(initial,-96,0)
                        s,obs = gesture(label+'-side-cross',obs,s,box,5,
                            lambda t: in_initial_axes(initial,[(-30,-18),(30-96*t,-18),(30-96*t,18),(-30,18)]),
                            linear_pointer(initial,dx,dy),offset=off,checkpoints=(1,6))
                        # Reacquire the actual visible corner at (-66,18), index
                        # 2 in this polygon ordering, irrespective of native key.
                        # Fixed corner (-30,-18); moving (-66-12t,18-66t).
                        dx,dy = edge_delta(initial,-12,-66)
                        s,obs = gesture(label+'-corner-cross',obs,s,box,2,
                            lambda t: in_initial_axes(initial,[(-30,-18),(-66-12*t,-18),(-66-12*t,18-66*t),(-30,18-66*t)]),
                            linear_pointer(initial,dx,dy),offset=(2,-2),checkpoints=(1,6))
                        before = s
                        s,obs = gesture(label+'-fill-continuation',obs,s,box,None,
                            lambda t: translate(before,3*t,2*t),linear_pointer(s,3,2),fill=True)
                    else:
                        # Public Single feed rectangle: right side minus 20,
                        # a small existing rotation, then ordinary body movement.
                        w,h = initial['object']['width']/2,initial['object']['height']/2
                        dx,dy = edge_delta(initial,-20,0)
                        s,obs = gesture(label+'-side',obs,s,box,5,
                            lambda t: in_initial_axes(initial,[(-w,-h),(w-20*t,-h),(w-20*t,h),(-w,h)]),
                            linear_pointer(initial,dx,dy),offset=off,thorough=False)
                        before = s
                        def rotate_pointer(start,t):
                            x,y = scene_point(before,box,start)
                            cx,cy = polygon_center(before)
                            co,si = math.cos(math.radians(10*t)),math.sin(math.radians(10*t))
                            return screen(before,box,(cx+co*(x-cx)-si*(y-cy),cy+si*(x-cx)+co*(y-cy)))
                        s,obs = gesture(label+'-rotate',obs,s,box,'rotation',
                            lambda t: rotate(before,10*t),rotate_pointer,thorough=False)
                        before = s
                        s,obs = gesture(label+'-fill',obs,s,box,None,
                            lambda t: translate(before,2*t,-2*t),linear_pointer(s,2,-2),fill=True,thorough=False)
                    result['completed_workflows'].append(label)
                    save()
                except (CoverageError, StopWorkflow) as error:
                    result['workflow_stops'].append(dict(workflow=label, kind=type(error).__name__, raw=str(error)))
                    if isinstance(error,CoverageError): result['coverage_issues'].append(dict(label=label,reason=str(error)))
                    if held: up()
                    save()
            browser.close()
    except Exception as error:
        result['runtime_errors'].append(dict(kind=type(error).__name__, raw=repr(error), traceback=traceback.format_exc()))
        traceback.print_exc()
        try:
            page.screenshot(path=str(evidence/'runtime-last.png'))
        except Exception as screenshot_error:
            result['runtime_errors'].append(dict(kind='last-screenshot', raw=repr(screenshot_error)))
    finally:
        for p in processes:
            if p.poll() is None: p.terminate()
        for p in processes:
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        for log in logs: log.close()
        scratch.cleanup()
        failures = [dict(label=o['label'], errors=o['errors']) for o in result['observations'] if o['errors']]
        result['behavior_failures'] = failures
        result['missing_workflows'] = sorted(set(result['required_workflows'])-set(result['completed_workflows']))
        incomplete = bool(result['runtime_errors'] or result['coverage_issues'] or result['missing_workflows'])
        result['coverage_complete'] = not incomplete
        # A reached semantic failure is never overwritten by a later missing
        # acquisition, runtime exception, or legacy control_passed convention.
        code = 1 if failures else 2 if incomplete else 0
        result.update(exit_code=code, status='observed-behavior-failure' if failures else 'coverage-or-infrastructure' if incomplete else 'pass',
                      passed=code==0, raw_success=code==0)
        save(); print('Native evidence:', out, flush=True)
    return code

if __name__ == '__main__':
    sys.exit(main())
