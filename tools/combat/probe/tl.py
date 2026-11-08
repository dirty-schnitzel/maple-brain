import json,sys
R=sys.argv[1];a,b=float(sys.argv[2]),float(sys.argv[3]);step=int(sys.argv[4]) if len(sys.argv)>4 else 4
L=[json.loads(l) for l in open(R+'/ticks.jsonl',encoding='utf-8')]
n=0
for l in L:
    o=l['obs'];t=o['t']
    if not a<=t<=b: continue
    n+=1
    if n%step: continue
    s=l['timings'].get('self') or {};v=l['timings'].get('v2') or {}
    f=v.get('facing') or 0
    ms=[]
    for m in o.get('mobs',[]):
        if m.get('kind')!='mob' or s.get('x') is None: continue
        dx=(m['x']-s['x'])*f; dy=m['y']-s['y']
        if abs(dx)<=260 and abs(dy)<=90:
            ms.append(f"{m['id']}:{m['state'][:4]} dx{dx:.0f} dy{dy:.0f} u{m.get('unseen')} {m.get('src')} {m.get('anim')} s{m.get('score')}")
    print(f"{t:6.2f} {v.get('mode')} w={v.get('weapon')} fw={v.get('footwork')} f={f} tg={v.get('target')} held={l['timings'].get('held')} st={s.get('state')} x={s.get('x')} mp={o.get('mp_now')} exp={o.get('exp_points')} | {' ; '.join(ms)}")
