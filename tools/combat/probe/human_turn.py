"""The user: a mob comes close behind -> how fast do they press toward it (from keys.jsonl)."""
import json,sys,bisect
R=sys.argv[1]
T=[json.loads(x) for x in open(R+'/ticks.jsonl',encoding='utf-8')]
K=[json.loads(x) for x in open(R+'/keys.jsonl',encoding='utf-8')]
K=[k for k in K if not k.get('inj') and k['key'] in('left','right') and k['down']]
kt=[k['t'] for k in K]
def face(t):
    i=bisect.bisect_right(kt,t); return (1 if K[i-1]['key']=='right' else -1) if i else 0
best={};ep={};out=[]
for r in T:
    o=r['obs'];t=o['t'];p=o.get('me_map') or o.get('map_pos')
    for m in o.get('mobs') or []:
        if m['src']!='none': best[m['id']]=max(best.get(m['id'],0),m.get('score') or 0)
    if not p: continue
    f=face(t)
    if not f: continue
    cur=set()
    for m in o.get('mobs') or []:
        if m.get('kind')=='mob' and m['state'] in('live','hit') and best.get(m['id'],0)>=0.8 and abs(m['y']-p[1])<=40 and -110<=(m['x']-p[0])*f<-5:
            cur.add(m['id']); ep.setdefault(m['id'],(t,f))
    for i in list(ep):
        t0,f0=ep[i]
        if f!=f0: out.append(('turned',t-t0)); del ep[i]
        elif i not in cur: out.append(('left',t-t0)); del ep[i]
tu=sorted(d for k,d in out if k=='turned'); le=sorted(d for k,d in out if k=='left')
q=lambda v:[round(v[min(int(p*len(v)),len(v)-1)],2) for p in(.5,.9)] if v else None
print(f'user: mob within 110 px behind {len(out)}x; turned to it {len(tu)}x after (median, p90) {q(tu)} s; it left first {len(le)}x after {q(le)} s')
