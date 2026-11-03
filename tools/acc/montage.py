"""python tools/acc/montage.py runs/NAME t0 t1 out.png  - crops around us, tick info on top"""
import json, sys, cv2, numpy as np
run, t0, t1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
rows = [json.loads(l) for l in open(run + "/ticks.jsonl", encoding="utf-8")]
sel = [r for r in rows if r["frame"] and t0 <= r["obs"]["t"] <= t1][:24]
tiles = []
for r in sel:
    im = cv2.imread(run + "/frames/" + r["frame"]); o = r["obs"]
    x, y = (int(o["me"][0]), int(o["me"][1])) if o["me"] else (683, 580)
    c = cv2.resize(im[max(0, y - 120):y + 30, max(0, x - 200):x + 200], (400, 150))
    tg = o["target"]; d = "" if not tg else f"{tg[0] + tg[2] / 2 - x:+.0f}"
    cv2.putText(c, f"{o['t']:.2f} {o['target_src'][:3]} {d} e{o['exp_points']} {','.join(a[:9] for a in r['actions'])}",
                (2, 12), 0, 0.38, (0, 255, 255), 1)
    for b, *_ in o["sprite_mobs"]:
        bx = int((b[0] - x + 200)); cv2.rectangle(c, (bx, 140), (bx + int(b[2]), 148), (255, 0, 255), 2)
    tiles.append(c)
while len(tiles) % 3: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]))
print(len(sel))
