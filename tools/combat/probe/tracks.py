import json,sys,collections,statistics as st
import numpy as np
L=[json.loads(l) for l in open(f'runs/v2/{sys.argv[1]}/ticks.jsonl',encoding='utf-8')]
T=collections.defaultdict(list); kinds=collections.Counter()
for l in L:
    s=l['timings'].get('self') or {}
    for m in l['obs'].get('mobs',[]):
        kinds[m.get('kind')]+=1
        if s.get('x') is None: continue
        T[(m['id'],m['mob'],m.get('kind'))].append((l['obs']['t'],m['x'],m['y'],s['x'],s['y'],m['src'],m.get('score') or 0,m['state'],l['timings'].get('v2',{}).get('target')==m['id'],bool(set(l['timings'].get('held',[]))&{'q','c','space'})))
print('kinds',dict(kinds),'tracks',len(T))
rows=[]
for k,v in T.items():
    sc=[r[6] for r in v if r[5]!='none']; 
    if not sc: continue
    near=[r for r in v if abs(r[1]-r[3])<=170 and abs(r[2]-r[4])<=60]
    rows.append(dict(id=k[0],mob=k[1],n=len(v),near=len(near),maxs=max(sc),med=st.median(sc),seen=len(sc)/len(v),die=any(r[7]=='dying' for r in v),tgt=sum(r[8] for r in v),held=sum(r[9] for r in near),t0=v[0][0],dur=v[-1][0]-v[0][0]))
weak=[r for r in rows if r['maxs']<0.8]; strong=[r for r in rows if r['maxs']>=0.8]
print('tracks strong(max>=.8)',len(strong),'weak',len(weak))
for name,g in (('strong',strong),('weak',weak)):
    print(name,'ticks near us',sum(r['near'] for r in g),'as target ticks',sum(r['tgt'] for r in g),'key held near',sum(r['held'] for r in g),'by mob',collections.Counter(r['mob'] for r in g),'died',sum(r['die'] for r in g))
print('weak tracks (top by ticks targeted):')
for r in sorted(weak,key=lambda r:-r['tgt'])[:14]:
    print({k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()})
# ticks with key held: strongest mob in sure reach is weak-only?
