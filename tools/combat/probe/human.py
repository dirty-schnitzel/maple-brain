"""The user's own play: gaps between presses in a fight, and presses after their own kills (clean or not)."""
import json,sys,bisect,collections
R=sys.argv[1]
T=[json.loads(x) for x in open(R+'/ticks.jsonl',encoding='utf-8')]
K=[json.loads(x) for x in open(R+'/keys.jsonl',encoding='utf-8')]
K=[k for k in K if not k.get('inj')]
att=[k['t'] for k in K if k['key']=='space' and k['down']]
turns=[(k['t'],k['key']) for k in K if k['key'] in('left','right') and k['down']]
tt=[t for t,_ in turns]
face=lambda t:(1 if turns[bisect.bisect_right(tt,t)-1][1]=='right' else -1) if bisect.bisect_right(tt,t) else 0
times=[r['obs']['t'] for r in T]
def tick(t): return T[max(0,bisect.bisect_right(times,t)-1)]
def me(r):
    o=r['obs']; p=o.get('me_map') or o.get('map_pos'); return p
first_dying={}
for r in T:
    for m in r['obs'].get('mobs') or []:
        if m.get('kind')=='mob' and m['state']=='dying' and m['id'] not in first_dying: first_dying[m['id']]=(r['obs']['t'],m['x'],m['y'])
kills=[]
for i,(td,x,y) in first_dying.items():
    j=bisect.bisect_right(att,td)-1
    if j<0 or td-att[j]>1.0: continue
    r=tick(att[j]);p=me(r)
    if not p: continue
    f=face(att[j]); dx=(x-p[0])*f
    if 0<=dx<=130 and abs(y-p[1])<=40: kills.append((td,att[j]))
def live_in_front(t):
    r=tick(t);p=me(r);f=face(t)
    if not p: return None
    return any(m.get('kind')=='mob' and m['state'] in('live','hit') and -10<=(m['x']-p[0])*f<=165 and abs(m['y']-p[1])<=40 for m in r['obs'].get('mobs') or [])
clean=extra=0;ex=[]
for td,ta in kills:
    after=[a for a in att if td<a<=td+1.0]
    wasted=[a for a in after if live_in_front(a) is False]
    if wasted: extra+=1; ex.append(round(len(wasted),0))
    else: clean+=1
print(f'user kills by last hit: {len(kills)}; clean (no press at nothing within 1 s after the death): {clean}; with presses at nothing: {extra} ({collections.Counter(ex)})')
g=[b-a for a,b in zip(att,att[1:]) if b-a<2.0]
g.sort()
print('gaps between presses in a fight (<2 s) n',len(g),'p10/25/50/75/90',[round(g[int(p*len(g))],3) for p in(.1,.25,.5,.75,.9)])
print('death -> next press (any) p50:',sorted([min([a for a in att if a>td],default=td+9)-td for td,_ in kills])[len(kills)//2])
print('killing press -> death (when the death shows) p10/50/90:',[round(sorted(td-ta for td,ta in kills)[int(p*len(kills))],2) for p in (.1,.5,.9)])
