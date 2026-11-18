"""E-L11 (PLAN-loot.md): is a RESTING drop seen on every frame it is in view? (the per-frame recall against memory)
and what hides it when not. Over every recording, find_v3.

    python tools/loot/exp_seen.py [--find v3] [--runs a,b] [--sheet 40]

A resting drop = the REST sightings (exp_rules2's rule) of one item at one map x (+-2 px) on one foothold, >= 10
frames, gaps < 30 s. Between its first and last sighting, every frame where its box is wholly in the play area and in
the world (not under the minimap / quickslots / status bar) is an in-view frame; counted:
  REST      a REST sighting of it on that frame
  weak      a loose sighting of it that the rule dropped (unexplained cover > 0.2: something over it)
  none      nothing (fully covered, or the vote had too little of it)
Prints the shares, per recording too, the longest unseen stretches, and writes a sheet of unseen cases (4x) to
runs/loot_plan/unseen_<find>.png for the eye: what covers a drop.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, frame, map_of, sheet, world_mask, PLAY_H, ROOT, SW  # noqa: E402

RUNS = ["runs/play/20261116_154819_1", "runs/play/20261116_084844_2", "runs/play/20261116_085108_3",
        "runs/play/20261116_085215_4", "runs/play/20261116_084719_1", "runs/play/20261117_092718_1",
        "runs/v2/20261117_094333_1", "runs/v2/20261117_111248_1", "runs/play/20261116_012059_1"]
ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v3")
ap.add_argument("--runs", default="")
ap.add_argument("--sheet", type=int, default=40)
a = ap.parse_args()
it = Items()
tot = Counter()
cases = []
gaps = []
for run in [r for r in RUNS if not a.runs or any(x in r for x in a.runs.split(","))]:
    p = ROOT / run / "loot" / f"find_{a.find}.jsonl"
    if not p.exists():
        continue
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = [r for r in rows if r.get("drops") is not None]
    mid = map_of(ROOT / run)
    wm = world_mask(mid, (768, SW))
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

    drops, loose = [], {}
    for fi, r in enumerate(rows):
        cam, t = r["cam"], r["t"]
        for d in r["drops"]:
            n = max(1, d["n_op"])
            u = 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0) + d.get("n_front", 0)) / n
            bx = d["box"][0] + d["box"][2] / 2 + cam[0]
            by = d["box"][1] + d["box"][3] + cam[1]
            mx = d["pos"][0] + cam[0]
            gy = ground(bx, by)
            if gy is None or not -7 <= by - gy <= 5:
                continue
            rest = u <= 0.2 and d.get("n_mob", 0) < 0.5 * d["n_seen"]
            loose.setdefault((d["item"], round(mx)), []).append((fi, gy))
            if not rest:
                continue
            # (same foothold y within 12 px: the foothold looked up can flip between two stacked ones as the drop bobs)
            tr = next((x for x in drops if x["item"] == d["item"] and abs(x["mx"] - mx) <= 2 and abs(x["gy"] - gy) <= 12
                       and t - x["t1"] < 30), None)
            if tr is None:
                tr = {"item": d["item"], "mx": mx, "bx": bx, "gy": gy, "fis": set(), "w": d["box"][2], "h": d["box"][3],
                      "fi0": fi}
                drops.append(tr)
            tr["fis"].add(fi)
            tr["last"], tr["t1"] = fi, t
    c = Counter()
    for tr in drops:
        if len(tr["fis"]) < 10:
            continue
        lo = set()
        for dx in (-2, -1, 0, 1, 2):
            lo |= {fi for fi, gy in loose.get((tr["item"], round(tr["mx"]) + dx), []) if abs(gy - tr["gy"]) <= 12}
        run_len = 0
        for fi in range(tr["fi0"], tr["last"] + 1):
            cam = rows[fi]["cam"]
            x0, y1 = int(tr["bx"] - cam[0] - tr["w"] / 2), int(tr["gy"] - cam[1] + 5)
            y0, x1 = y1 - tr["h"] - 12, x0 + tr["w"]
            if x0 < 2 or x1 > SW - 2 or y0 < 2 or y1 > PLAY_H - 2 or not wm[y0:y1, x0:x1].all():
                continue
            k = "REST" if fi in tr["fis"] else ("weak" if fi in lo else "none")
            c[k] += 1
            if k == "REST":
                if run_len:
                    gaps.append((run_len, rows[fi]["t"] - t_gap0, run, tr["item"]))
                run_len = 0
            else:
                if run_len == 0:
                    t_gap0 = rows[fi]["t"]
                run_len += 1
                cases.append((run, rows[fi]["frame"], rows[fi]["t"], tr["item"], x0, y0, x1, y1, k))
    n = sum(c.values())
    tot += c
    if n:
        print(f"{run[-17:]}: resting drops {sum(1 for tr in drops if len(tr['fis']) >= 10):3d}, in-view drop-frames {n:6d}: REST "
              f"{100 * c['REST'] / n:.2f} %, weak {100 * c['weak'] / n:.2f} %, none {100 * c['none'] / n:.2f} %")
n = sum(tot.values())
print(f"ALL: in-view drop-frames {n}: REST {tot['REST']} = {100 * tot['REST'] / n:.2f} %, weak {tot['weak']} = "
      f"{100 * tot['weak'] / n:.2f} %, none {tot['none']} = {100 * tot['none'] / n:.2f} %")
if gaps:
    g = np.array([x[1] for x in gaps])
    print(f"unseen stretches (ended by a REST sighting): {len(gaps)}; length p50 {np.median(g):.2f} p90 {np.percentile(g, 90):.2f} "
          f"p99 {np.percentile(g, 99):.2f} max {g.max():.1f} s; >= 1 s: {int((g >= 1).sum())}, >= 5 s: {int((g >= 5).sum())}")
    fr = np.array([x[0] for x in gaps])
    nn = tot["weak"] + tot["none"]
    print(f"   unseen drop-frames by stretch length: < 1 s {int(fr[g < 1].sum())}, 1-5 s {int(fr[(g >= 1) & (g < 5)].sum())}, >= 5 s "
          f"{int(fr[g >= 5].sum())} of {nn} (a stretch of many seconds in view = the offline joining put two drops of one "
          f"item at one x together, or something lay over it that long)")
    for ln, dur, run, item in sorted(gaps, key=lambda x: -x[1])[:8]:
        print(f"      {run[-17:]} {it.name(item)[:16] if item < 9000000 else 'meso'}: {dur:.1f} s ({ln} frames)")
    short = tot["REST"] + int(fr[g < 1].sum())
    print(f"   counting only stretches < 1 s as unseen: REST {tot['REST']} of {short} = {100 * tot['REST'] / short:.2f} %")
rng = np.random.default_rng(1)
pick = [cases[int(i)] for i in rng.choice(len(cases), min(a.sheet, len(cases)), replace=False)] if cases else []
tiles, labels = [], []
for run, fr, t, item, x0, y0, x1, y1, k in sorted(pick):
    f = frame(ROOT / run, fr)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    a0, b0 = max(0, min(SW - 96, cx - 48)), max(0, min(PLAY_H - 80, cy - 48))
    crop = f[b0:b0 + 80, a0:a0 + 96].copy()
    cv2.rectangle(crop, (x0 - a0 - 1, y0 + 12 - b0 - 1), (x1 - a0, y1 - 5 - b0), (0, 255, 255), 1)
    tiles.append(crop)
    labels.append(f"{k} {it.name(item)[:10] if item < 9000000 else 'meso'} {run[-8:-2]} {t:.1f}")
if tiles:
    out = ROOT / "runs" / "loot_plan" / f"unseen_{a.find}.png"
    cv2.imwrite(str(out), sheet(tiles, cols=10, labels=labels, scale=2))
    print("->", out)
