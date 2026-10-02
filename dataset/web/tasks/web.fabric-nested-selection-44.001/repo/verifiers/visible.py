"""Protected screenshot-only observer. Feed + input operations supply geometry.
Marker centers are discovered as unordered visible blobs, never from Fabric.
No assumption that the projected edges are perpendicular or a rotation stem is 40px.
"""
import math
from PIL import Image, ImageDraw

W, H = 1000, 780


# Independent public fixture arithmetic, never read from candidate objects.
IDENTITY = [1, 0, 0, 1, 0, 0]
PALETTE = {'outer': (52,56,64), 'inner': (85,91,101), 'amber': (226,164,59)}


def multiply(a, b):
    A,B,C,D,E,F = a; g,h,i,j,k,l = b
    return [A*g+C*h, B*g+D*h, A*i+C*j, B*i+D*j, A*k+C*l+E, B*k+D*l+F]


def frame(x, y, angle, sx=1, sy=1):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [c*sx, s*sx, -s*sy, c*sy, x, y]


def outer(scene):
    x, y = scene['fixture_center']
    return frame(x, y, -15, 1.1, .9)


def projection(scene):
    parent = multiply(outer(scene), frame(0, 0, -10)) if scene.get('artwork') == 'nested' else IDENTITY
    return multiply(scene['viewportTransform'], parent)


def polygon(matrix, o, offset):
    a,b,c,d,e,f = matrix
    angle = math.radians(o.get('angle', 0))
    co, si = math.cos(angle), math.sin(angle)
    corners = []
    for u, v in [(-.5,-.5), (.5,-.5), (.5,.5), (-.5,.5)]:
        x = o['left'] + co*u*o['width'] - si*v*o['height']
        y = o['top'] + si*u*o['width'] + co*v*o['height']
        corners.append((a*x+c*y+e+offset[0], b*x+d*y+f+offset[1]))
    return corners


def project(scene, offset):
    if 'expected_polygon' in scene:
        a,b,c,d,e,f = projection(scene)
        corners = [(a*x+c*y+e+offset[0], b*x+d*y+f+offset[1])
                   for x,y in scene['expected_polygon']]
    else:
        corners = polygon(projection(scene), scene['object'], offset)
    return corners, math.hypot(*scene['viewportTransform'][:2])


def preserved_polygons(scene, offset):
    if scene.get('artwork') != 'nested': return []
    camera = scene['viewportTransform']; parent = outer(scene)
    def rect(w,h,x=0,y=0,angle=0):
        return dict(left=x, top=y, width=w, height=h, angle=angle)
    return [
        ('outer', polygon(multiply(camera,parent), rect(180,120), offset)),
        ('inner', polygon(multiply(camera,multiply(parent,frame(0,0,-10))), rect(120,80), offset)),
        ('amber', polygon(multiply(camera,parent), rect(16,16,60,0), offset)),
    ]


def dist(p, q):
    return math.hypot(p[0]-q[0], p[1]-q[1])


def segdist(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return dist(p, (a[0]+t*dx, a[1]+t*dy))


def basis(corners):
    """Independent inverse of the two projected edge vectors (fractions, not dots)."""
    o = corners[0]
    ex = (corners[1][0]-o[0], corners[1][1]-o[1])
    ey = (corners[3][0]-o[0], corners[3][1]-o[1])
    det = ex[0]*ey[1]-ex[1]*ey[0]
    if abs(det) < 1e-8:
        raise ValueError('degenerate protected geometry')
    def local(x, y):
        dx, dy = x-o[0], y-o[1]
        return ((dx*ey[1]-dy*ey[0])/det, (ex[0]*dy-ex[1]*dx)/det)
    # Distances between each pair of parallel edges, for pixel-sized margins.
    return local, abs(det)/math.hypot(*ey), abs(det)/math.hypot(*ex)


def components(points):
    points = set(points)
    result = []
    while points:
        todo = [points.pop()]
        comp = set(todo)
        while todo:
            x, y = todo.pop()
            for q in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if q in points:
                    points.remove(q); comp.add(q); todo.append(q)
        result.append(comp)
    return result


def markers(red, white):
    # Thick red cores distinguish filled controls from the thin connected frame.
    # White rings also admit hollow/round/outlined controls. No square-only test.
    cores = {(x, y) for x, y in red if all((x+dx, y+dy) in red
             for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    proposals = []
    for kind, parts in [('red-core', components(cores)), ('light-ring', components(white))]:
        for comp in parts:
            xs = [x+.5 for x, y in comp]; ys = [y+.5 for x, y in comp]
            w, h = max(xs)-min(xs)+1, max(ys)-min(ys)+1
            if len(comp) < 14 or not (4 <= w <= 32 and 4 <= h <= 32):
                continue
            if kind == 'light-ring' and not any((round(x), round(y)) in red
                    for x in xs[::max(1, len(xs)//12)] for y in ys[::max(1, len(ys)//12)]):
                continue
            center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2)
            proposals.append(dict(center=center, width=w, height=h, area=len(comp), kind=kind,
                                  radius=math.hypot(w, h)/2+2))
    merged = []
    for p in proposals:
        near = next((m for m in merged if dist(m['center'], p['center']) < 5), None)
        if near:
            near['radius'] = max(near['radius'], p['radius'])
            near['width'] = max(near['width'], p['width'])
            near['height'] = max(near['height'], p['height'])
            near['representations'] = [near['kind'], p['kind']]
        else:
            merged.append(p)
    return merged


def red_pixel(r, g, b):
    # Recognize red composited over the artboard, blue fill, or their antialiased
    # boundary mixture. Fabric normally fades selection during fill movement.
    # rgb = background + alpha*(red-background) + beta*(blue-background),
    # where alpha >= 0, beta >= 0 and alpha+beta <= 1. This is palette algebra,
    # independent of candidate geometry and without requiring opaque controls.
    if r > 155 and r-g > 75 and r-b > 75: return True
    for R,G,B in [(15,17,21), *PALETTE.values()]:
        ar,ag,ab = 255-R,64-G,64-B
        br,bg,bb = 120-R,170-G,220-B
        det = ar*bg-br*ag
        alpha = (bg*(r-R)-br*(g-G))/det
        beta = (ar*(g-G)-ag*(r-R))/det
        if (.15 <= alpha <= 1.03 and beta >= -.04 and alpha+beta <= 1.04
                and abs(b-(B+ab*alpha+bb*beta)) <= 9): return True
    return False


def check(path, scene, box, selected=True):
    im = Image.open(path).convert('RGB')
    errors, coverage, metrics = [], [], {}
    if im.size != (W, H):
        return [], {'coverage_issues': ['unsupported screenshot dimensions'], 'image_size': im.size}
    ox, oy, bw, bh = box
    def on_canvas(x, y, margin=0):
        return ox+margin <= x < ox+bw-margin and oy+margin <= y < oy+bh-margin
    corners, _ = project(scene, box[:2])
    edges = list(zip(corners, corners[1:]+corners[:1]))
    mids = [((a[0]+b[0])/2, (a[1]+b[1])/2) for a, b in edges]
    local, hx, hy = basis(corners)
    blue, red, white = set(), set(), set()
    layer_pixels = {name: set() for name in PALETTE} if scene.get("artwork") == "nested" else {}
    for y in range(H):
        for x in range(W):
            r, g, b = im.getpixel((x, y))
            if on_canvas(x, y) and abs(r-120) <= 12 and abs(g-170) <= 12 and abs(b-220) <= 12:
                blue.add((x, y))
            if red_pixel(r, g, b) and on_canvas(x, y):
                red.add((x, y))
            if on_canvas(x, y) and min(r, g, b) > 215:
                white.add((x, y))
            if on_canvas(x,y):
                for name,points in layer_pixels.items():
                    R,G,B = PALETTE[name]
                    if abs(r-R)<=6 and abs(g-G)<=6 and abs(b-B)<=6: points.add((x,y))
    blobs = markers({p for p in red if on_canvas(*p)}, white)
    metrics.update(blue_pixels=len(blue), red_pixels=len(red), expected_corners=corners,
                   projected_altitudes=[hx, hy], markers=blobs)
    # Greedy nearest-pair association has no dependence on marker enumeration order.
    expected = corners+mids
    wanted = {i for i, q in enumerate(expected) if on_canvas(*q, 18)}
    pairs = sorted((dist(q, m['center']), i, j) for i, q in enumerate(expected)
                   if i in wanted for j, m in enumerate(blobs))
    assigned, used = {}, set()
    for distance, i, j in pairs:
        if i not in assigned and j not in used and distance <= 24:
            assigned[i] = (j, distance); used.add(j)
    metrics['control_matches'] = {str(i): dict(marker=j, error=d) for i, (j, d) in assigned.items()}
    if selected and len(assigned) < len(wanted):
        coverage.append('unrecognized or unassignable visible edge controls')
    for i, (j, d) in assigned.items():
        if selected and len(assigned) == len(wanted) and d > 2.5:
            errors.append(f'visible edge control {i} displaced {d:.3f}px')
    # Rotation input comes from the one remaining exterior visible marker, not
    # a computed camera angle, stem normal, control ordering, or fixed distance.
    exterior = []
    for j, m in enumerate(blobs):
        u, v = local(*m['center'])
        if j not in used and not (0 <= u <= 1 and 0 <= v <= 1) and min(segdist(m['center'], *edge) for edge in edges) > 12:
            exterior.append(j)
    rotation = blobs[exterior[0]]['center'] if len(exterior) == 1 else None
    metrics['rotation_marker'] = rotation
    metrics['input_controls'] = {str(i): blobs[j]['center'] for i, (j, d) in assigned.items() if d <= 2.5}
    if selected and rotation is None:
        coverage.append('rotation marker not uniquely supported by visible pixels')
    unknown_controls = selected and (len(assigned) < len(wanted) or rotation is None)
    def near_marker(x, y):
        # Unknown representations are observation coverage, not paint defects.
        # Reserve ordinary marker neighborhoods only for ambiguous observations.
        if unknown_controls and any(abs(x-q[0])<=18 and abs(y-q[1])<=18 for q in expected): return True
        return any(abs(x-m['center'][0]) <= m['width']/2+3 and abs(y-m['center'][1]) <= m['height']/2+3 for m in blobs)
    cx = sum(q[0] for q in corners)/4; cy = sum(q[1] for q in corners)/4
    candidates = sorted(blue, key=lambda q: (q[0]+.5-cx)**2+(q[1]+.5-cy)**2)
    metrics['fill_point'] = next(((x+.5,y+.5) for x,y in candidates
        if not near_marker(x+.5,y+.5) and all((x+dx,y+dy) in blue
        for dx in range(-3,4) for dy in range(-3,4))), None)
    if not selected and len(red) > 40: errors.append('unexpected selection before native click')
    # Native fixture paints Amber after the inner group and Blue.
    # Its independently prescribed footprint occludes Blue, including its edge.
    amber = next((basis(poly) for name, poly in preserved_polygons(scene, box[:2])
                  if name == 'amber'), None)
    def blue_occluded(x, y):
        if amber is None: return False
        transform, ax, ay = amber
        u, v = transform(x, y)
        return -4/ax <= u <= 1+4/ax and -4/ay <= v <= 1+4/ay
    counts = [[0, 0] for _ in range(16)]
    for y in range(max(0, math.floor(min(p[1] for p in corners))), min(H, math.ceil(max(p[1] for p in corners)))):
        for x in range(max(0, math.floor(min(p[0] for p in corners))), min(W, math.ceil(max(p[0] for p in corners)))):
            u, v = local(x+.5, y+.5)
            if 8/hx < u < 1-8/hx and 8/hy < v < 1-8/hy and on_canvas(x, y) and not near_marker(x+.5, y+.5) and not blue_occluded(x+.5, y+.5):
                i = min(3, int(u*4))+4*min(3, int(v*4))
                counts[i][0] += 1
                counts[i][1] += (x, y) in blue
    total, hits = map(sum, zip(*counts))
    tiles = [b/a for a, b in counts if a >= 30]
    ratio = hits/max(1, total)
    metrics.update(interior_samples=total, interior_coverage=ratio, tile_counts=counts, tile_coverage=tiles)
    if total < 500 or len(tiles) < 4:
        coverage.append('insufficient visible interior area')
    else:
        if ratio < (.8 if unknown_controls else .98): errors.append('shape interior coverage')
        if not unknown_controls and min(tiles) < .95: errors.append('distributed shape tile coverage <95%')
    extra_blue = 0
    for x, y in blue:
        u, v = local(x+.5, y+.5)
        if not (-2/hx <= u <= 1+2/hx and -2/hy <= v <= 1+2/hy and on_canvas(x, y)):
            extra_blue += 1
    metrics['unexpected_blue'] = extra_blue
    if extra_blue > max(30, len(blue)*.002): errors.append('unexpected shape paint/silhouette or clipping')
    reports = []
    for a, b in edges:
        length = dist(a, b)
        tx, ty = (b[0]-a[0])/length, (b[1]-a[1])/length
        nx, ny = -ty, tx
        # Endpoint order may reverse on crossing. Aim inward toward the
        # polygon center; camera determinant alone does not determine winding.
        if nx*(cx-(a[0]+b[0])/2) + ny*(cy-(a[1]+b[1])/2) < 0:
            nx, ny = -nx, -ny
        paint, samples, slots = [], [], []
        for step in range(8, int(length)-7, 2):
            x, y = a[0]+tx*step, a[1]+ty*step
            if not on_canvas(x, y, 6) or near_marker(x, y): continue
            paint.append(None if blue_occluded(x+nx*4, y+ny*4) else
                         any((round(x+nx*off), round(y+ny*off)) in blue for off in [2, 3, 4, 5]))
            hits = []
            for yy in range(round(y)-3, round(y)+4):
                for xx in range(round(x)-3, round(x)+4):
                    off = (xx+.5-x)*nx+(yy+.5-y)*ny
                    along = (xx+.5-x)*tx+(yy+.5-y)*ty
                    if (xx, yy) in red and abs(off) <= 2 and abs(along) <= 1.7: hits.append(off)
            slots.append((step, bool(hits)))
            if hits: samples.append((step, sum(hits)/len(hits)))
        support = len(samples)/max(1, len(paint))
        visible_paint = [value for value in paint if value is not None]
        paint_support = sum(visible_paint)/max(1, len(visible_paint))
        if len(samples) > 1:
            mx = sum(x for x, y in samples)/len(samples); my = sum(y for x, y in samples)/len(samples)
            slope = sum((x-mx)*(y-my) for x, y in samples)/max(1e-9, sum((x-mx)**2 for x, y in samples))
            offset = my-slope*mx
            angle = abs(math.degrees(math.atan(slope)))
            displacement = max(abs(offset), abs(offset+slope*length))
        else: angle = displacement = None
        quarters = [[hit for pos, hit in slots if k/4 <= pos/length < (k+1)/4] for k in range(4)]
        reports.append(dict(length=length, eligible=len(paint), support=support, paint_support=paint_support,
                            direction_error_deg=angle, max_displacement=displacement, samples=samples))
        if len(paint) < 4:
            coverage.append('insufficient visible edge length')
            continue
        if not unknown_controls and visible_paint and paint_support < .95: errors.append('shape boundary/silhouette support')
        if not selected or unknown_controls: continue
        # Allows a dashed frame, but requires distributed evidence on every side.
        if support < .5 or any(sum(q)/len(q) < .25 for q in quarters if q):
            errors.append('frame edge coverage/alignment')
        if angle is None or angle > .75 or displacement > 2:
            errors.append('frame edge direction/displacement')
    metrics['edges'] = reports
    # Do not classify unknown marker representations as extra graphics failures.
    if selected and not coverage:
        extra_red = sum(not (near_marker(x+.5, y+.5) or
            any(segdist((x+.5, y+.5), a, b) <= 2 for a, b in edges) or
            (rotation and any(segdist((x+.5, y+.5), q, rotation) <= 2 for q in mids))) for x, y in red)
        metrics['unexpected_red'] = extra_red
        if extra_red > 40: errors.append('substantial extra/misplaced selection graphics')
    # The same projected-basis/palette observer checks native background layers.
    # Exclude only publicly prescribed occlusion and observed selection markers.
    layers = preserved_polygons(scene, box[:2])
    layer_report = {}
    for index, (name, poly) in enumerate(layers):
        loc, ax, ay = basis(poly)
        occluders = [basis(q) for _,q in layers[index+1:]] + ([] if name == 'amber' else [basis(corners)])
        colored = layer_pixels[name]
        def covered(x,y):
            for f, h1, h2 in occluders:
                u,v = f(x,y)
                if -4/h1 <= u <= 1+4/h1 and -4/h2 <= v <= 1+4/h2: return True
            return near_marker(x,y) or any((round(x)+dx,round(y)+dy) in red
                for dx in range(-2,3) for dy in range(-2,3))
        tiles = [[0,0] for _ in range(16)]
        for y in range(max(0,math.floor(min(q[1] for q in poly))), min(H,math.ceil(max(q[1] for q in poly)))):
            for x in range(max(0,math.floor(min(q[0] for q in poly))), min(W,math.ceil(max(q[0] for q in poly)))):
                u,v = loc(x+.5,y+.5)
                if (4/ax < u < 1-4/ax and 4/ay < v < 1-4/ay
                        and on_canvas(x,y,2) and not covered(x+.5,y+.5)):
                    tile = tiles[min(3,int(u*4))+4*min(3,int(v*4))]
                    tile[0] += 1; tile[1] += (x,y) in colored
        total, hits = map(sum,zip(*tiles))
        ratios = [b/a for a,b in tiles if a >= 20]
        extra = sum(not (-2/ax <= loc(x+.5,y+.5)[0] <= 1+2/ax and
                         -2/ay <= loc(x+.5,y+.5)[1] <= 1+2/ay) for x,y in colored)
        borders = []
        for a,b in zip(poly,poly[1:]+poly[:1]):
            length = dist(a,b); nx,ny = -(b[1]-a[1])/length,(b[0]-a[0])/length
            pcx = sum(q[0] for q in poly)/4; pcy = sum(q[1] for q in poly)/4
            if nx*(pcx-(a[0]+b[0])/2) + ny*(pcy-(a[1]+b[1])/2) < 0:
                nx,ny = -nx,-ny
            samples, occluded_samples = [], 0
            for step in range(6,int(length)-5,2):
                t=step/length; x=a[0]+t*(b[0]-a[0]); y=a[1]+t*(b[1]-a[1])
                ix,iy=x+4*nx,y+4*ny
                if on_canvas(ix,iy,3):
                    if covered(ix,iy): occluded_samples += 1
                    else: samples.append((round(ix),round(iy)) in colored)
            borders.append(dict(samples=len(samples), occluded_samples=occluded_samples,
                                support=sum(samples)/max(1,len(samples))))
        layer_report[name] = dict(polygon=poly, pixels=len(colored), interior_samples=total,
            coverage=hits/max(1,total), tile_counts=tiles, unexpected_paint=extra, edges=borders)
        if total < 200 or len(ratios) < 3: coverage.append(name+' insufficient visible preservation area')
        elif hits/total < .98 or min(ratios) < .94: errors.append(name+' changed visible geometry/paint')
        if extra > max(30,len(colored)*.002): errors.append(name+' unexpected silhouette')
        for edge in borders:
            if edge['samples'] < 4:
                if edge['samples'] + edge['occluded_samples'] < 4:
                    coverage.append(name+' insufficient visible boundary')
            elif edge['support'] < .95: errors.append(name+' boundary changed')
    metrics['preserved_layers'] = layer_report
    metrics['coverage_issues'] = list(dict.fromkeys(coverage))
    overlay = im.copy(); draw = ImageDraw.Draw(overlay)
    draw.line(corners+[corners[0]], fill='#00ff80', width=1)
    for m in blobs:
        x, y = m['center']; r = m['radius']
        draw.ellipse((x-r, y-r, x+r, y+r), outline='#ffff00')
    draw.text((10, 765), ('FAIL ' if errors else 'COVERAGE ' if coverage else 'PASS ')+('; '.join(errors+coverage))[:125], fill='white')
    overlay.save(path.with_name(path.stem+'-overlay.png'))
    return list(dict.fromkeys(errors)), metrics
