"""The user's own attack presses: hold vs tap, press length, gap between presses, around kills."""
import json,sys,collections,statistics as st
from pathlib import Path
def q(v,ps=(.1,.5,.9)): v=sorted(v); return [round(v[min(int(p*len(v)),len(v)-1)],3) for p in ps] if v else None
for r in sys.argv[1:]:
    K=[json.loads(l) for l in open(Path(r)/'keys.jsonl',encoding='utf-8')]
    K=[k for k in K if not k.get('inj')]
    cnt=collections.Counter(k['key'] for k in K if k['down'])
    att='space' if cnt['space']>=cnt['q'] else 'q'
    downs=[];lens=[];d0=None
    for k in K:
        if k['key']!=att: continue
        if k['down'] and d0 is None: d0=k['t'];downs.append(k['t'])
        elif not k['down'] and d0 is not None: lens.append(k['t']-d0);d0=None
    gaps=[b-a for a,b in zip(downs,downs[1:])]
    dur=K[-1]['t']-K[0]['t'] if K else 0
    short=[x for x in lens if x<0.35]
    print(f"{Path(r).name}: {dur/60:.1f} min, keys {dict(cnt.most_common(7))}")
    print(f"  attack '{att}': {len(downs)} presses; press length p10/50/90 {q(lens)}s; taps (<0.35s) {len(short)/max(len(lens),1):.0%}; long holds >1s {sum(x>1 for x in lens)}")
    print(f"  gap press->next press p10/50/90 {q(gaps)}s; gap release->next press p10/50/90 {q([b-(a+l) for a,b,l in zip(downs,downs[1:],lens)])}s")
    hist=collections.Counter(min(int(x/0.1),15) for x in lens); print('  press length histogram (0.1 s bins):',sorted(hist.items()))
