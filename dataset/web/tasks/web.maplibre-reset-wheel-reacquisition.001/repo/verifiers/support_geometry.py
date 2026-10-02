"""Author-only bounded three-plane fixture geometry, not a general numeric package.
Exact rational arithmetic on supplied decimal scalars (including str(float)) removes
near-parallel division/classification uncertainty. No approximate fast path. Native
support certification and optical input roundoff remain outside this offline kernel.
"""
from fractions import Fraction as F
L=F('0.520782470703125'); R=F('0.5207977294921875'); S=F(-65536000)
PIECES=((None,L,L,F(1400),F(0),'ridge'),(L,R,L,F(1400),S,'slope'),(R,None,R,F(400),F(0),'valley'))
def exact(v):
    return v if isinstance(v,F) else F(str(v))
def solve(o,d,rectangles):
    o=tuple(map(exact,o)); d=tuple(map(exact,d))
    if len(o)!=3 or len(d)!=3 or not any(d): raise ValueError('finite nonzero 3D ray required')
    hits=[]; accumulation=False; uncertain=[]; origin_contacts=0; merges=[]
    for ri,rect in enumerate(rectangles):
        xmin,xmax,ymin,ymax=map(exact,rect)
        if xmin>xmax or ymin>ymax: raise ValueError('inverted support rectangle')
        for pl,ph,base,z,slope,name in PIECES:
            xl=max(xmin,pl) if pl is not None else xmin
            xh=min(xmax,ph) if ph is not None else xmax
            low=F(0); high=None
            if xl>xh: continue
            for i,mn,mx in ((0,xl,xh),(1,ymin,ymax)):
                if d[i]:
                    a,b=sorted(((mn-o[i])/d[i],(mx-o[i])/d[i]))
                    low=max(low,a); high=b if high is None else min(high,b)
                elif not mn<=o[i]<=mx:
                    high=F(-1); break
            if high is not None and high<low: continue
            num=z+slope*(o[0]-base)-o[2]; den=d[2]-slope*d[0]
            if den and abs(den)<=F('1e-12')*max(F(1),abs(d[2]),abs(slope*d[0])):
                uncertain.append({'rectangle':ri,'piece':name,'denominatorExact':str(den)})
            if den:
                t=num/den
                if t<=0 or t<low or (high is not None and t>high): continue
            elif num: continue
            elif low>0: t=low  # positive singleton and positive interval entries count
            elif high is None or high>0:
                accumulation=True; continue  # positive extent accumulates at zero
            else:
                origin_contacts+=1; continue  # [0,0] is not a positive hit; keep searching
            q=tuple(o[i]+t*d[i] for i in range(3))
            assert xl<=q[0]<=xh and ymin<=q[1]<=ymax
            assert q[2]==z+slope*(q[0]-base)
            witness={'rectangle':ri,'piece':name,'clippedXY':list(map(str,(xl,xh,ymin,ymax)))}
            # Equality of exact ray parameter and exact position, plus proven membership
            # on both closed surfaces: same physical hit, never a |delta t| merge.
            # Different pieces may merge ONLY on the actual L/R shared edge. Same-piece
            # duplicates from overlapping/touching loaded support have identical surface.
            shared=None
            for h in hits:
                if h['tExact']!=str(t) or h['pointExact']!=list(map(str,q)): continue
                if h['piece']!=name and q[0] not in (L,R): continue
                shared=h; break
            if shared is not None:
                merges.append({'tExact':str(t),'reason':'exact shared terrain edge' if shared['piece']!=name else 'identical surface hit in overlapping closed support','witness':witness})
                shared['witnesses'].append(witness)
            else:
                hits.append({'t':float(t),'tExact':str(t),'p':list(map(float,q)),
                             'pointExact':list(map(str,q)),'piece':name,'residual':0.0,'witnesses':[witness]})
    hits.sort(key=lambda h:F(h['tExact']))
    return {'status':'unusable_coplanar_origin' if accumulation else 'hit' if hits else 'missing_or_no_positive_ground',
            'hits':hits,'roots':[h['t'] for h in hits],'exactRoots':[h['tExact'] for h in hits],
            'arithmetic':'exact rational supplied-decimal, support-aware; no float fast path',
            'uncertainNonzeroDenominatorsResolved':uncertain,'originOnlyContactsDiscarded':origin_contacts,'provenSharedHits':merges}
