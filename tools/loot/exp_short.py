"""E-L3b (PLAN-loot.md): the SHORT sighting groups (a drop seen on < 5 frames at one place) - what are they?
For each: when, where (map), frames, the nearest longer drop of the same item (dx, dy, dt to its start / end), our
distance. Prints a table + classes: 'before a long drop' (the flight in), 'after a long drop' (flying to a looter),
'alone'.

    python tools/loot/exp_short.py RUN [--find NAME] [--item ID] [--list 30]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, run_ticks  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="all")
ap.add_argument("--item", type=int, default=0)
ap.add_argument("--list", type=int, default=30)
a = ap.parse_args()
run = Path(a.run)
it = Items()
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("drops") is not None]
me = {k["frame"]: k for k in run_ticks(run)}
groups, open_ = [], []
for fi, r in enumerate(rows):
    cam, t = r["cam"], r["t"]
    for d in r["drops"]:
        mx, my = d["pos"][0] + cam[0], d["pos"][1] + cam[1]
        best = next((g for g in open_ if g["item"] == d["item"] and abs(g["mx"] - mx) <= 2 and abs(g["my"] - my) <= 10
                     and g["last"] != fi), None)
        if best is None:
            best = {"item": d["item"], "mx": mx, "my": my, "t0": t, "obs": [], "last": -1}
            open_.append(best)
            groups.append(best)
        best["obs"].append((fi, t, mx, my, d["n_seen"] / max(1, d["n_op"])))
        best["last"], best["t1"] = fi, t
    open_ = [g for g in open_ if t - g["t1"] <= 2.0]
long_ = [g for g in groups if len(g["obs"]) >= 5]
short = [g for g in groups if len(g["obs"]) < 5 and (not a.item or g["item"] == a.item)]
cls = Counter()
out = []
for g in short:
    best = None
    for L in long_:
        if L["item"] != g["item"]:
            continue
        for tag, tt in (("before", L["t0"] - g["t1"]), ("after", g["t0"] - L["t1"])):
            if 0 <= tt <= 1.5:
                dx, dy = g["mx"] - L["mx"], g["my"] - L["my"]
                if abs(dx) <= 160 and abs(dy) <= 160 and (best is None or tt < best[1]):
                    best = (tag, tt, dx, dy)
    k = me.get(rows[g["obs"][0][0]]["frame"]) or {}
    cam = rows[g["obs"][0][0]]["cam"]
    md = None
    if k.get("me"):
        md = (g["mx"] - cam[0] - k["me"][0], g["my"] - cam[1] - k["me"][1])
    cls[best[0] if best else "alone"] += 1
    out.append((g, best, md))
print(f"{run.name}: {len(groups)} groups, {len(long_)} long, {len(short)} short"
      f"{' of item ' + str(a.item) if a.item else ''}: {dict(cls)}")
n1 = Counter(len(g["obs"]) for g in short)
print("frames per short group:", dict(sorted(n1.items())), "| SEEN share p50",
      round(float(np.median([o[4] for g in short for o in g["obs"]])), 2) if short else "-")
for g, best, md in out[:a.list]:
    b = f"{best[0]} a long one by {best[1]:.2f} s, d ({best[2]:+.0f}, {best[3]:+.0f})" if best else "alone"
    m = f"us ({md[0]:+.0f}, {md[1]:+.0f})" if md else ""
    print(f"   {g['item']} {it.name(g['item'])[:16]:16s} t {g['t0']:.2f} n {len(g['obs'])} map ({g['mx']:.0f}, {g['my']:.0f}) "
          f"seen {g['obs'][0][4]:.2f} | {b} | {m}")
