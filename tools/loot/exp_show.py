"""E-L2b (PLAN-loot.md): look at what the prototype finder found - per item where on screen (fixed screen spots =
UI), share of exact pixels, and a sheet of crops (frame 3x | the client's picture 3x) for the eye.

    python tools/loot/exp_show.py RUN [--find NAME] [--n 48] [--item ID] [--out NAME]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, frame, sheet  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="all")
ap.add_argument("--n", type=int, default=48)
ap.add_argument("--item", type=int, default=0)
ap.add_argument("--out", default="")
a = ap.parse_args()
run = Path(a.run)
it = Items()
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("drops") is not None]
by = defaultdict(list)
for r in rows:
    for d in r["drops"]:
        by[d["item"]].append((r, d))
print(f"{run.name} find_{a.find}: {len(rows)} frames, {sum(len(r['drops']) for r in rows)} drop sightings, "
      f"drops per frame p50 {np.median([len(r['drops']) for r in rows]):.0f} max {max(len(r['drops']) for r in rows)}")
for item, lst in sorted(by.items(), key=lambda x: -len(x[1])):
    scr = Counter((d["box"][0], d["box"][1]) for _, d in lst)
    top, n_top = scr.most_common(1)[0]
    share = np.array([d["n_seen"] / d["n_op"] for _, d in lst])
    ab = np.array([d["n_abs"] / d["n_op"] for _, d in lst])
    ys = np.array([d["box"][1] + d["box"][3] for _, d in lst])
    print(f"  {item:8d} {it.name(item)[:28]:28s} n {len(lst):5d} | seen share p10 {np.percentile(share, 10):.2f} p50 "
          f"{np.median(share):.2f} p90 {np.percentile(share, 90):.2f} | absent p90 {np.percentile(ab, 90):.2f} | "
          f"most common screen spot {top} x{n_top} ({100 * n_top / len(lst):.0f} %) | bottom y {ys.min()}..{ys.max()}")
todo = [(r, d) for r in rows for d in r["drops"] if not a.item or d["item"] == a.item]
if todo:
    step = max(1, len(todo) // a.n)
    tiles, labels = [], []
    cache = {}
    for r, d in todo[::step][:a.n]:
        if r["frame"] not in cache:
            cache.clear()
            cache[r["frame"]] = frame(run, r["frame"])
        f = cache[r["frame"]]
        x, y, w, h = d["box"]
        P = 14
        x0, y0 = max(0, x - P), max(0, y - P)
        crop = f[y0:y + h + P, x0:x + w + P]
        pic = it.raw(d["item"])[0] if d["item"] < 9000000 else it.meso(d["item"] - 9000000)[d["f"]][0]
        ic = np.full((crop.shape[0], pic.shape[1] + 4, 3), 90, np.uint8)
        al = pic[..., 3:4] / 255.0
        ph = min(pic.shape[0], ic.shape[0] - P)
        ic[P:P + ph, 2:2 + pic.shape[1]] = (pic[:ph, :, :3] * al[:ph] + 90 * (1 - al[:ph])).astype(np.uint8)
        tiles.append(np.concatenate([crop, ic], axis=1))
        labels.append(f"{d['item']} {d['n_seen']}/{d['n_op']} t{r['t']:.1f}")
    p = run / "loot" / f"show_{a.out or a.find}{'_' + str(a.item) if a.item else ''}.png"
    cv2.imwrite(str(p), sheet(tiles, cols=8, labels=labels, scale=3))
    print("->", p)
