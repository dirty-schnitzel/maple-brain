import json,sys,cv2,numpy as np
R,t0,t1,step,out=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),sys.argv[5]
L=[json.loads(l) for l in open(R+"/ticks.jsonl",encoding='utf-8')]
F=[l for l in L if l.get('frame') is not None]
tiles=[];t=t0
while t<=t1:
    l=min(F,key=lambda x:abs(x['obs']['t']-t)); t+=step
    f=cv2.imread(f"{R}/frames/{l['frame']}")
    o=l['obs'];s=l['timings'].get('self') or {};cam=o.get('cam')
    if o.get('me'): cx,cy=int(o['me'][0]),int(o['me'][1])
    elif cam and s.get('x') is not None: cx,cy=int(s['x']-cam[0]),int(s['y']-cam[1])
    else: cx,cy=683,500
    x0=min(max(cx-170,0),1366-340);y0=min(max(cy-130,0),768-190)
    c=f[y0:y0+190,x0:x0+340].copy()
    v=l['timings'].get('v2') or {}
    txt=f"{o['t']:.2f} {','.join(l['timings'].get('held',[]))} {s.get('state')} {v.get('weapon')} f{v.get('facing')}"
    cv2.rectangle(c,(0,0),(340,14),(0,0,0),-1); cv2.putText(c,txt,(2,11),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
    tiles.append(c)
cols=3
while len(tiles)%cols: tiles.append(np.zeros_like(tiles[0]))
g=cv2.vconcat([cv2.hconcat(tiles[i:i+cols]) for i in range(0,len(tiles),cols)])
cv2.imwrite(out,g); print(g.shape)
