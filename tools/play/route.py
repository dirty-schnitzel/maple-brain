"""Time per platform vs its spawns, platform-to-platform transitions, revisit intervals (map 10003061 hardcoded).
usage: python -I tools/play/route.py RUN"""
import json, sys, collections
sys.path.insert(0,'.')
from maplebrain.nav.navmap import NavMap
from pathlib import Path
d=sys.argv[1]
ticks=[json.loads(x) for x in open(d+'/ticks.jsonl')]
nm=NavMap.for_map(10003061, Path('assets/mcw'))
sp=collections.Counter()
for s in nm.spawns:
    p=nm.platform_at(s[0] if isinstance(s,(tuple,list)) else s.x, s[1] if isinstance(s,(tuple,list)) else s.y, tol=20)
    sp[p.id if p else None]+=1
plats=nm.platforms if isinstance(nm.platforms,dict) else {p.id:p for p in nm.platforms}
# platform sequence (platform ids only, dwell >=0.5s)
seq=[];cur=None;t0=0
for r in ticks:
    o=r['obs'];p=o.get('platform') if o.get('rope') is None else None
    if p is None: continue
    if p!=cur:
        if cur is not None: seq.append((cur,t0,o['t']))
        cur,t0=p,o['t']
seq.append((cur,t0,ticks[-1]['obs']['t']))
m=[]
for p,a,b in seq:
    if m and m[-1][0]==p: m[-1]=(p,m[-1][1],b)
    elif b-a<0.5 and m: continue
    else: m.append((p,a,b))
T=ticks[-1]['obs']['t']
tot=collections.Counter(); 
for p,a,b in m: tot[p]+=b-a
print("platform: time %, spawns, width, y")
for p,s in tot.most_common(16):
    pl=plats.get(p); print(f"  {p:4}  {100*s/T:4.1f} %  spawns {sp.get(p,0):2}  x {pl.left:.0f}..{pl.right:.0f} y {pl.y_at(pl.left):.0f}" if pl else p)
print("spawns on platforms never/barely visited:", {p:n for p,n in sp.items() if tot.get(p,0)<0.01*T})
tr=collections.Counter((a[0],b[0]) for a,b in zip(m,m[1:]))
print("top transitions:", tr.most_common(20))
# revisit interval per platform
for p in [x for x,_ in tot.most_common(8)]:
    starts=[a for q,a,b in m if q==p]; g=sorted(b-a for a,b in zip(starts,starts[1:]))
    if g: print(f"  revisit {p}: n {len(starts)} median {g[len(g)//2]:.0f}s")
