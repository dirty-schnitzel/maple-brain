"""Kills by LAST HIT: a mob counts as ours if our attack (space/c) came <= W s (default 0.8, use 1.0) before it
turned dying, with it <= 130 px in front of us at that swing, same level.  usage: kills.py RUN [W]"""
import json, sys, bisect, collections
d=sys.argv[1]; W=float(sys.argv[2]) if len(sys.argv)>2 else 0.8
ticks=[json.loads(x) for x in open(d+'/ticks.jsonl')]
keys=[json.loads(x) for x in open(d+'/keys.jsonl')]
att=[k['t'] for k in keys if k['key'] in ('space','c') and k['down']]
turns=[(k['t'],k['key']) for k in keys if k['key'] in ('left','right') and k['down']]
tt=[t for t,_ in turns]
def facing(t):
    i=bisect.bisect_right(tt,t); return turns[i-1][1] if i else None
hist=collections.defaultdict(list)  # id -> [(t,x,y,state)]
mepos=[]
for r in ticks:
    o=r['obs']
    if o.get('map_pos'): mepos.append((o['t'],*o['map_pos']))
    for m in o.get('mobs') or []:
        if m.get('kind')=='mob': hist[m['id']].append((o['t'],m['x'],m['y'],m['state']))
mt=[p[0] for p in mepos]
def me_at(t):
    i=max(0,bisect.bisect_right(mt,t)-1); return mepos[i]
def mob_at(h,t):
    best=min(h,key=lambda e:abs(e[0]-t)); return best
ours=[];near_not=0;far=0;dxs=[]
for i,h in hist.items():
    die=next((e for e in h if e[3]=='dying'),None)
    if not die: continue
    td=die[0]; j=bisect.bisect_right(att,td)
    if j==0 or td-att[j-1]>W:
        _,mx,my=me_at(td)[:3] if False else (0,*me_at(td)[1:])
        if abs(die[1]-mx)<200 and abs(die[2]-my)<40: near_not+=1
        else: far+=1
        continue
    ta=att[j-1]; m=mob_at(h,ta); _,mx,my=me_at(ta)
    dx=m[1]-mx; f=facing(ta)
    infront = (dx>=-25 if f=='right' else dx<=25)
    if abs(dx)<=130 and abs(m[2]-my)<=45 and infront:
        ours.append(td); dxs.append(round(dx if f=='right' else -dx))
    else: far+=1
T=ticks[-1]['obs']['t']
print(f"deaths {sum(1 for h in hist.values() if any(e[3]=='dying' for e in h))}: OUR last hit {len(ours)} = {60*len(ours)/T:.1f}/min; near us but not our hit {near_not}; elsewhere {far}")
dxs.sort(); print("our reach at the killing swing (px in front): median",dxs[len(dxs)//2],"p10",dxs[len(dxs)//10],"p90",dxs[9*len(dxs)//10])
c=collections.Counter(int(t//60) for t in ours); print("per minute:",[c[i] for i in range(int(T//60)+1)])
g=sorted(b-a for a,b in zip(sorted(ours),sorted(ours)[1:])); print("time between kills median %.1f p10 %.1f p90 %.1f"%(g[len(g)//2],g[len(g)//10],g[9*len(g)//10]))
print("attack presses per kill %.1f"%(len(att)/len(ours)))
# delay from last attack to dying, for deaths within 130 px in front at the same level (no window)
dl=[]
for i,h in hist.items():
    die=next((e for e in h if e[3]=='dying'),None)
    if not die: continue
    td=die[0]; j=bisect.bisect_right(att,td)
    if j==0: continue
    _,mx,my=me_at(td)
    if abs(die[1]-mx)<=130 and abs(die[2]-my)<=45: dl.append(round(td-att[j-1],1))
print("delay last attack -> dying (near deaths):", sorted(collections.Counter(min(x,5.0) for x in dl).items()))
