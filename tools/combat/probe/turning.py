"""Mobs close behind us: how long until we face them, what the bot was doing meanwhile; and mobs that hit us."""
import json,sys,collections,statistics as st
KEYS={'q','c','space'}
def q(v,ps=(.5,.9)): v=sorted(v); return [round(v[min(int(p*len(v)),len(v)-1)],2) for p in ps] if v else None
for R in sys.argv[1:]:
    L=[json.loads(l) for l in open(R+'/ticks.jsonl',encoding='utf-8')]
    best={}
    ep={};done=[];why=collections.Counter();held_behind=0.0;prev=None
    hp_prev=None;hits=[];pending=[]
    for l in L:
        o=l['obs'];t=o['t'];s=l['timings'].get('self') or {};v=l['timings'].get('v2') or {};f=v.get('facing') or 0
        dt=0 if prev is None else min(t-prev,0.2);prev=t
        for m in o.get('mobs',[]):
            if m['src']!='none': best[m['id']]=max(best.get(m['id'],0),m.get('score') or 0)
        if s.get('x') is None or not f or s.get('state')!='ground': continue
        live=[m for m in o.get('mobs',[]) if m.get('kind')=='mob' and m['state'] in('live','hit') and best.get(m['id'],0)>=0.8 and abs(m['y']-s['y'])<=40]
        behind=[m for m in live if -110<=(m['x']-s['x'])*f<-5]
        front=[m for m in live if -5<=(m['x']-s['x'])*f<=165]
        held=bool(KEYS&set(l['timings'].get('held',[])))
        if held and behind and not front: held_behind+=dt
        cur={m['id'] for m in behind}
        for m in behind:
            if m['id'] not in ep: ep[m['id']]=(t,f)
        for i in list(ep):
            t0,f0=ep[i]
            if i not in cur:
                turned = f!=f0
                done.append((t-t0,turned)); del ep[i]
        if behind:
            why[(v.get('weapon'),v.get('footwork'),'target behind' if v.get('target') in cur else 'target elsewhere')]+=dt
        # being hit: HP drop -> which side was the nearest mob, and when did we face it
        hp=o.get('hp_now')
        if hp is not None and hp_prev is not None and hp<hp_prev-5:
            near=sorted(live,key=lambda m:abs(m['x']-s['x']))
            if near and abs(near[0]['x']-s['x'])<=80:
                side=1 if near[0]['x']>s['x'] else -1
                pending.append([t,side,f==side,None])
        for p in pending:
            if p[3] is None and f==p[1]: p[3]=t-p[0]
        if hp is not None: hp_prev=hp
    print(f'== {R}  ({L[-1]["obs"]["t"]:.0f} s)')
    print(f'  attack held with a mob close behind and none in front: {held_behind:.1f} s')
    turned=[d for d,tu in done if tu]; left=[d for d,tu in done if not tu]
    print(f'  mob came within 110 px behind: {len(done)}x; we turned to it {len(turned)}x after (median, p90) {q(turned)} s; it left/died first {len(left)}x after {q(left)} s')
    print('  time with a mob close behind, by what the bot was doing (weapon, footwork, target):')
    for k,vv in why.most_common(7): print(f'     {vv:5.1f} s  {k}')
    already=sum(1 for p in pending if p[2]); lat=[p[3] for p in pending if not p[2] and p[3] is not None]; never=sum(1 for p in pending if not p[2] and p[3] is None)
    print(f'  hit by a mob within 80 px: {len(pending)}x; already facing it {already}; turned to it after (median, p90) {q(lat)} s; never turned {never}')
