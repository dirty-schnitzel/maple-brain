import json,collections,statistics as st,sys
R=sys.argv[1] if len(sys.argv)>1 else 'runs/v2'
L=[json.loads(l) for l in open(R+'/ticks.jsonl',encoding='utf-8')]
KEYS={'q','c','space'}
held=lambda l: bool(KEYS&set(l['timings'].get('held',[])))
T=[l['obs']['t'] for l in L]
ev=[];lastalive={};done=set()
for i,l in enumerate(L):
    o=l['obs'];v=l['timings'].get('v2') or {}
    for m in o.get('mobs',[]):
        if m['src']!='none' and m['state'] in('live','hit'): lastalive[m['id']]=o['t']
    if not held(l): continue
    for m in o.get('mobs',[]):
        if m['state']=='dying' and m['id'] not in done:
            # was it the one we fought? target in the last 1 s, close in front
            s=l['timings'].get('self') or {}; f=v.get('facing') or 0
            if s.get('x') is None or not -20<=(m['x']-s['x'])*f<=180 or abs(m['y']-s['y'])>60: continue
            done.add(m['id'])
            up=next((j for j in range(i,len(L)) if not held(L[j])),None)
            if up is None: continue
            # did we stay on another mob? (held_on) -> skip: the hold was right
            other=any(mm['id']!=m['id'] and mm['state'] in('live','hit') and mm['src']!='none' and (mm.get('score') or 0)>=0.7
                      and -10<=(mm['x']-s['x'])*f<=165 and abs(mm['y']-s['y'])<=60 for mm in o['mobs'])
            ev.append(dict(id=m['id'],seen_dying=o['t'],last_alive=lastalive.get(m['id']),key_up=T[up],other=other,
                           anim_first=next((L[k]['obs']['t'] for k in range(max(i-40,0),i+1) for mm in L[k]['obs']['mobs'] if mm['id']==m['id'] and (mm.get('anim') or '').startswith('die')),o['t'])))
solo=[e for e in ev if not e['other']]
print('deaths in front while holding:',len(ev),' with no other mob in reach:',len(solo))
d1=[e['seen_dying']-e['last_alive'] for e in solo if e['last_alive']]
d2=[e['key_up']-e['seen_dying'] for e in solo]
tot=[e['key_up']-e['last_alive'] for e in solo if e['last_alive']]
q=lambda v:(round(st.median(v),2),round(sorted(v)[int(.9*len(v))],2)) if v else None
print('last seen alive -> tracker says dying  (median, p90):',q(d1))
print('tracker says dying -> attack key up     (median, p90):',q(d2))
print('last seen alive -> key up, total        (median, p90):',q(tot))
for e in solo[:20]: print({k:(round(v,2) if isinstance(v,float) else v) for k,v in e.items()})
