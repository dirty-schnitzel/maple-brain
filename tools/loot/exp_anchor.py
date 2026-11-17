"""E-L12 (PLAN-loot.md): where exactly does a resting drop sit? Per resting drop (>= 60 REST sightings at one map x):
the lowest and highest y of the client's drawing position `pos` (= picture corner + the file's origin) against the
foothold's y AT pos.x, at the box centre's x, and the bob range; per item and all together. Also the candidates and
features a frame (find_v3's own counters).

    python tools/loot/exp_anchor.py [--find v3]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, map_of, ROOT  # noqa: E402

RUNS = ["runs/play/20261116_154819_1", "runs/play/20261116_084844_2", "runs/play/20261116_085108_3",
        "runs/play/20261116_085215_4", "runs/play/20261116_084719_1", "runs/play/20261117_092718_1",
        "runs/v2/20261117_094333_1", "runs/v2/20261117_111248_1", "runs/play/20261116_012059_1"]
ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v3")
a = ap.parse_args()
it = Items()
res = defaultdict(list)
cands, feats, ndrops = [], [], []
maps = defaultdict(Counter)
for run in RUNS:
    p = ROOT / run / "loot" / f"find_{a.find}.jsonl"
    if not p.exists():
        continue
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = [r for r in rows if r.get("drops") is not None]
    mid = map_of(ROOT / run)
    mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
    FH = np.array([[f["x1"], f["y1"], f["x2"], f["y2"]] if f["x1"] < f["x2"] else [f["x2"], f["y2"], f["x1"], f["y1"]]
                   for f in (mp.get("footholds") or {}).values() if f["x1"] != f["x2"]], float)

    def ground(mx, my):
        on = (FH[:, 0] <= mx) & (FH[:, 2] >= mx)
        if not on.any():
            return None
        ya = FH[on, 1] + (mx - FH[on, 0]) * (FH[on, 3] - FH[on, 1]) / (FH[on, 2] - FH[on, 0])
        below = ya >= my - 14
        return float(ya[below].min()) if below.any() else None

    tr = {}
    for r in rows:
        cam = r["cam"]
        cands.append(r["ms"]["cands"])
        feats.append(r["ms"]["feat"])
        ndrops.append(len(r["drops"]))
        for d in r["drops"]:
            n = max(1, d["n_op"])
            if 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0) + d.get("n_front", 0)) / n > 0.2 or d["n_seen"] < 0.9 * n:
                continue
            px, py = d["pos"][0] + cam[0], d["pos"][1] + cam[1]
            bx, by = d["box"][0] + d["box"][2] / 2 + cam[0], d["box"][1] + d["box"][3] + cam[1]
            g = ground(bx, by)
            if g is None or not -7 <= by - g <= 5:
                continue
            k = (d["item"], round(px), round(g / 12))
            tr.setdefault(k, []).append((py, by, px, bx))
    for (item, _, _), v in tr.items():
        if len(v) < 60:
            continue
        v = np.array(v)
        gp, gb = ground(v[0, 2], v[:, 1].max()), ground(v[0, 3], v[:, 1].max())
        if gp is None or gb is None:
            continue
        res[item].append((v[:, 0].max() - gp, v[:, 0].min() - gp, v[:, 1].max() - gb, v[:, 0].max() - v[:, 0].min()))
        maps[mid][item] += 1
print(f"per frame over {len(cands)} frames: candidates (>= 12 votes) p50 {np.median(cands):.0f} p90 {np.percentile(cands, 90):.0f} max "
      f"{max(cands)}; features p50 {np.median(feats):.0f} p90 {np.percentile(feats, 90):.0f} max {max(feats)}; loose sightings p50 "
      f"{np.median(ndrops):.0f} p90 {np.percentile(ndrops, 90):.0f} max {max(ndrops)}")
allv = []
for item, v in sorted(res.items(), key=lambda x: -len(x[1])):
    v = np.array(v)
    allv.append(v)
    print(f"   {item:8d} {it.name(item)[:22]:22s} n {len(v):3d} | lowest pos y - foothold(pos x): "
          f"{dict(sorted(Counter(np.round(v[:, 0]).astype(int).tolist()).items()))} | highest: "
          f"{dict(sorted(Counter(np.round(v[:, 1]).astype(int).tolist()).items()))} | box bottom - foothold(centre x): "
          f"{dict(sorted(Counter(np.round(v[:, 2]).astype(int).tolist()).items()))} | bob {dict(sorted(Counter(v[:, 3].astype(int).tolist()).items()))}")
v = np.concatenate(allv)
print(f"ALL n {len(v)}: lowest pos y - foothold(pos x) {dict(sorted(Counter(np.round(v[:, 0]).astype(int).tolist()).items()))}; "
      f"bob range {dict(sorted(Counter(v[:, 3].astype(int).tolist()).items()))}")
for mid, c in maps.items():
    print(f"map {mid}: " + ", ".join(f"{it.name(i)[:20] if i < 9000000 else 'meso' + str(i - 9000000)} {n}" for i, n in c.most_common()))
