import json,sys,collections,warnings,random
sys.path.insert(0,'.'); warnings.filterwarnings('ignore')
from pathlib import Path
import cv2,numpy as np
from maplebrain.perception.gpu_sprites import GpuSpriteDetector
g=GpuSpriteDetector.for_map(10005063,Path('assets/mcw'),min_score=0.4)
L=[json.loads(l) for l in open('runs/v2/ticks.jsonl',encoding='utf-8')]
peak={}
cases=[]
for l in L:
    o=l['obs'];s=l['timings'].get('self') or {}
    for m in o.get('mobs',[]):
        if m['src']!='none': peak[m['id']]=max(peak.get(m['id'],0),m.get('score') or 0)
    if not l.get('frame') or s.get('x') is None or not o.get('cam'): continue
    for m in o.get('mobs',[]):
        if m['src']=='none' and m['state'] in('live','hit','hidden') and peak.get(m['id'],0)>=0.9 \
           and abs(m['x']-s['x'])<=170 and abs(m['y']-s['y'])<=60 and 0.05<(m.get('unseen') or 0)<=1.0:
            cases.append((l,m))
print('unseen near-us moments of proven mobs (with frame):',len(cases))
random.seed(1); cases=random.sample(cases,min(60,len(cases)))
res=collections.Counter(); rows=[]
for l,m in cases:
    f=cv2.imread(f"runs/v2/frames/{l['frame']}")
    cam=l['obs']['cam']; px,py=m['x']-cam[0],m['y']-cam[1]           # where the tracker thinks the feet are
    hits=g.find(f)
    near=[h for h in hits if abs(h.feet[0]-px)<=60 and abs(h.feet[1]-py)<=40]
    same=[h for h in near if h.mob_id==m['mob']]
    best=max(same,key=lambda h:h.score,default=None)
    if best is None: k='detector finds nothing there'
    elif best.score>=0.8: k='detector finds it >=0.8'
    elif best.score>=0.65: k='detector 0.65-0.8'
    else: k='detector only <0.65'
    res[k]+=1
    off=(round(best.feet[0]-px),round(best.feet[1]-py)) if best else None
    rows.append((round(l['obs']['t'],2),m['id'],m['mob'],m['state'],round(m.get('unseen',0),2),k,round(best.score,2) if best else None,off,m.get('vis'),l['obs'].get('me')))
print(dict(res))
for r in rows[:30]: print(r)
