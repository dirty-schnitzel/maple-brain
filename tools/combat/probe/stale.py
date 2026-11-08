import json,sys,collections,random
KEYS={'q','c','space'}
def load(r): return [json.loads(l) for l in open((f"runs/v2/{r}/" if r else "runs/v2/")+"ticks.jsonl",encoding='utf-8')]
def analyse(r,T=0.5,SOL=0.7):
    L=load(r); last={}; c=collections.Counter(); ex=collections.defaultdict(list); prev=None
    for l in L:
        o=l['obs'];t=o['t'];s=l['timings'].get('self') or {};v=l['timings'].get('v2') or {};f=v.get('facing') or 0
        dt=0 if prev is None else min(t-prev,0.2); prev=t
        for m in o.get('mobs',[]):
            if m['src']!='none' and (m.get('score') or 0)>=SOL and not (m.get('anim') or '').startswith('die'): last[m['id']]=t
        if not set(l['timings'].get('held',[]))&KEYS or s.get('x') is None or not f: continue
        inr=[m for m in o.get('mobs',[]) if m.get('kind')=='mob' and m['state'] in('live','hit','hidden') and -10<=(m['x']-s['x'])*f<=165 and abs(m['y']-s['y'])<=60]
        fresh=[m for m in inr if t-last.get(m['id'],-9)<=T]
        k='solid' if fresh else 'stale' if inr else 'nothing'
        c[k]+=dt; ex[k].append(l)
    return L,c,ex
if __name__=='__main__':
    for r,lab in (('20261107_184350_1','0.65 skill'),('20261107_191504_1','0.65'),('20261107_191658_1','0.70'),('20261107_191756_1','0.80'),('20261107_191848_2','0.80')):
        L,c,ex=analyse(r); tot=sum(c.values()) or 1
        print(f"{lab:10} {r[9:]} {L[-1]['obs']['t']:4.0f}s key down {tot:5.1f}s | solid {c['solid']/tot:4.0%} stale {c['stale']/tot:4.0%} nothing {c['nothing']/tot:4.0%}")
    r='20261107_191848_2'
    for T in (0.3,0.5,0.8,1.2):
        L,c,ex=analyse(r,T); tot=sum(c.values())
        print('T',T,{k:round(v/tot,2) for k,v in c.items()})
    L,c,ex=analyse(r)
    random.seed(4)
    F=[l for l in ex['stale']+ex['nothing'] if l.get('frame') is not None]
    S=random.sample(F,12); S.sort(key=lambda l:l['obs']['t'])
    print('sample',[round(l['obs']['t'],2) for l in S])
    import cv2,numpy as np
    tiles=[]
    for l in S:
        f=cv2.imread(f"runs/v2/{r}/frames/{l['frame']}");o=l['obs'];s=l['timings']['self'];cam=o.get('cam');v=l['timings']['v2']
        cx,cy=(int(o['me'][0]),int(o['me'][1])) if o.get('me') else (int(s['x']-cam[0]),int(s['y']-cam[1]))
        x0=min(max(cx-170,0),1026);y0=min(max(cy-130,0),578);t=f[y0:y0+190,x0:x0+340].copy()
        for m in o['mobs']:
            if m['state'] in('live','hit','hidden'):
                px,py=int(m['x']-cam[0]-x0),int(m['y']-cam[1]-y0)
                cv2.drawMarker(t,(px,py-30),(0,0,255) if m['src']=='none' else (0,255,255),cv2.MARKER_CROSS,14,2)
        cv2.rectangle(t,(0,0),(340,14),(0,0,0),-1);cv2.putText(t,f"{o['t']:.2f} f{v.get('facing')} tgt {v.get('target')}",(2,11),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
        tiles.append(t)
    cv2.imwrite('runs/minimap_check/stale.png',cv2.vconcat([cv2.hconcat(tiles[i:i+3]) for i in range(0,12,3)]))
