"""E-L8 (PLAN-loot.md): which of a sighting's numbers tell a real drop from the false classes - over every recording.

    python tools/loot/exp_rules.py [--find v2] [--runs a,b] [--save]

Sightings (the loose prototype rule: >= 40 SEEN px, SEEN share >= 0.25, ABSENT <= 0.15) are grouped per item and map
place, then CLASSED without the eye, by behaviour only:
  rest     a group on >= 20 frames whose x stays and whose y bobs (range 3..8 px): a drop lying there - certain
  flight   a meso's short groups within 1.5 s before a rest group of the same item, <= 160 px from it: flying in
  pickup   ... within 0.6 s after a rest group ended: flying to the looter
  screen   a group whose SCREEN place stays (+-1 px) on >= 12 frames while the camera moves >= 12 px: UI
  worn     an equip's sightings in no rest group
  other    the rest (short groups of items: to look at)
Per class: sightings, SEEN share, unexplained cover u = 1 - (SEEN + ABSENT + under an accepted drop) / opaque, ring
(share of the known pixels around the picture that show the scene or a drop), feature share. Then rules are scored:
recall on rest + flight sightings / false sightings kept per class.
--save: runs/loot_plan/rules_<find>.json (per class the arrays) for the plan's tables.
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
EQUIP = ("Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants", "Ring", "Shield", "Shoes", "Weapon")
ap = argparse.ArgumentParser()
ap.add_argument("--find", default="v2")
ap.add_argument("--runs", default="")
ap.add_argument("--save", action="store_true")
a = ap.parse_args()
it = Items()
runs = [r for r in RUNS if not a.runs or any(x in r for x in a.runs.split(","))]
ALL = defaultdict(list)          # class -> [(s, u, ring or nan, fshare, run, item, t, box, n_seen)]
per_run = {}
ground_off = defaultdict(list)   # item -> lowest (box bottom - foothold y)
for run in runs:
    p = ROOT / run / "loot" / f"find_{a.find}.jsonl"
    if not p.exists():
        print("missing", p)
        continue
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = [r for r in rows if r.get("drops") is not None]
    mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_of(ROOT / run)) / "map.json").read_text(encoding="utf-8"))
    FH = np.array([[f["x1"], f["y1"], f["x2"], f["y2"]] if f["x1"] < f["x2"] else [f["x2"], f["y2"], f["x1"], f["y1"]]
                   for f in (mp.get("footholds") or {}).values() if f["x1"] != f["x2"]], float)

    def ground(mx, my):
        on = (FH[:, 0] <= mx) & (FH[:, 2] >= mx)
        if not on.any():
            return None
        ya = FH[on, 1] + (mx - FH[on, 0]) * (FH[on, 3] - FH[on, 1]) / (FH[on, 2] - FH[on, 0])
        below = ya >= my - 14
        return float(ya[below].min()) if below.any() else None

    groups, open_ = [], []
    sgroups, sopen = [], []
    for fi, r in enumerate(rows):
        cam, t = r["cam"], r["t"]
        for d in r["drops"]:
            mx, my = d["pos"][0] + cam[0], d["pos"][1] + cam[1]
            g = next((g for g in open_ if g["item"] == d["item"] and abs(g["mx"] - mx) <= 2 and abs(g["my"] - my) <= 10
                      and g["last"] != fi), None)
            if g is None:
                g = {"item": d["item"], "mx": mx, "my": my, "t0": t, "obs": [], "last": -1}
                open_.append(g)
                groups.append(g)
            o = {"fi": fi, "t": t, "mx": mx, "my": my, "d": d, "cam": cam}
            g["obs"].append(o)
            g["last"], g["t1"] = fi, t
            o["g"] = g
            sg = next((s for s in sopen if s["item"] == d["item"] and abs(s["x"] - d["box"][0]) <= 1
                       and abs(s["y"] - d["box"][1]) <= 1 and s["last"] != fi), None)
            if sg is None:
                sg = {"item": d["item"], "x": d["box"][0], "y": d["box"][1], "obs": [], "last": -1}
                sopen.append(sg)
                sgroups.append(sg)
            sg["obs"].append(o)
            sg["last"], sg["t1"] = fi, t
            o["sg"] = sg
        open_ = [g for g in open_ if t - g["t1"] <= 2.0]
        sopen = [s for s in sopen if t - s["t1"] <= 1.0]
    for g in groups:
        ys = np.array([o["my"] for o in g["obs"]])
        xs = np.array([o["mx"] for o in g["obs"]])
        g["rest"] = len(g["obs"]) >= 20 and xs.max() - xs.min() <= 2 and 3 <= ys.max() - ys.min() <= 8
        g["ymax"] = float(ys.max())
    for s in sgroups:
        cx = np.array([o["cam"][0] for o in s["obs"]])
        cy = np.array([o["cam"][1] for o in s["obs"]])
        s["screen"] = len(s["obs"]) >= 12 and max(cx.max() - cx.min(), cy.max() - cy.min()) >= 12
    rest = [g for g in groups if g["rest"]]
    cls_n = Counter()
    for g in groups:
        kind = "meso" if g["item"] >= 9000000 else it.kind(g["item"])
        if g["rest"]:
            c = "rest"
        else:
            c = None
            for L in rest:
                if L["item"] != g["item"] or abs(g["mx"] - L["mx"]) > 160 or abs(g["my"] - L["my"]) > 160:
                    continue
                if 0 <= L["t0"] - g["t1"] <= 1.5:
                    c = "flight"
                    break
                if 0 <= g["t0"] - L["t1"] <= 0.6:
                    c = "pickup"
            if c is None:
                c = "worn" if kind in EQUIP else "other"
        for o in g["obs"]:
            d = o["d"]
            cc = "screen" if o["sg"]["screen"] and c != "rest" else c
            n = max(1, d["n_op"])
            s_ = d["n_seen"] / n
            u = 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0)) / n
            ring = d["ring_e"] / d["ring_n"] if d.get("ring_n", 0) >= 60 else float("nan")
            fs = d["n_fseen"] / max(1, d["n_feat"])
            byb = d["box"][1] + d["box"][3] + o["cam"][1]
            gy = ground(d["box"][0] + d["box"][2] / 2 + o["cam"][0], byb)
            dyg = byb - gy if gy is not None else float("nan")
            ALL[cc].append((s_, u, ring, fs, run[-10:], d["item"], o["t"], tuple(d["box"]), d["n_seen"], dyg,
                            len(g["obs"]), o["fi"]))
            cls_n[cc] += 1
        if g["rest"]:
            lo = max(g["obs"], key=lambda o: o["my"])
            d = lo["d"]
            bx = d["box"][0] + d["box"][2] / 2 + lo["cam"][0]
            by = d["box"][1] + d["box"][3] + lo["cam"][1]
            gy = ground(bx, by)
            if gy is not None:
                ground_off[g["item"]].append((by - gy, g["ymax"] - gy))
    per_run[run] = (len(rows), len(groups), len(rest), dict(cls_n))
    print(f"{run[-17:]}: {len(rows)} frames, groups {len(groups)}, rest drops {len(rest)}, sightings by class {dict(cls_n)}")

print()
for c in ("rest", "flight", "pickup", "screen", "worn", "other"):
    v = ALL.get(c) or []
    if not v:
        continue
    s_ = np.array([x[0] for x in v])
    u = np.array([x[1] for x in v])
    rg = np.array([x[2] for x in v])
    fs = np.array([x[3] for x in v])
    q = lambda arr, p: float(np.nanpercentile(arr, p))  # noqa: E731
    print(f"{c:7s} n {len(v):6d} | SEEN share p1 {q(s_, 1):.2f} p5 {q(s_, 5):.2f} p50 {q(s_, 50):.2f} p95 {q(s_, 95):.2f} | "
          f"unexplained cover p50 {q(u, 50):.2f} p95 {q(u, 95):.2f} p99 {q(u, 99):.2f} | ring p1 {q(rg, 1):.2f} p5 "
          f"{q(rg, 5):.2f} p50 {q(rg, 50):.2f} (no ring {100 * np.isnan(rg).mean():.1f} %) | feature share p5 {q(fs, 5):.2f}")
    dg = np.array([x[9] for x in v])
    on = (dg >= -7) & (dg <= 5)
    print(f"        box bottom - foothold y in -7..+5 (resting height): {100 * on.mean():.1f} %; no foothold under: "
          f"{100 * np.isnan(dg).mean():.1f} %; values p5 {q(dg, 5):.0f} p50 {q(dg, 50):.0f} p95 {q(dg, 95):.0f}")
    if c in ("worn", "other", "screen"):
        top = Counter((x[5], x[4]) for x in v).most_common(8)
        print("        ", [(i, it.name(i)[:16], r, n) for (i, r), n in top])
    if c == "other":
        gl = np.array([x[10] for x in v])
        print(f"        'other' on the ground (-7..+5): {int(on.sum())}; off the ground: {int((~on).sum())} "
              f"(of them mesos {sum(1 for x, o_ in zip(v, on) if not o_ and x[5] >= 9000000)}); group length p50 "
              f"{np.median(gl):.0f}; off-ground items: "
              f"{[(i, it.name(i)[:14], n) for i, n in Counter(x[5] for x, o_ in zip(v, on) if not o_ and x[5] < 9000000).most_common(8)]}")
print()
good = (ALL.get("rest") or []) + (ALL.get("flight") or [])
bad = {c: ALL.get(c) or [] for c in ("screen", "worn", "other")}


def keep(x, s_min, u_max, ring_min):
    return x[0] >= s_min and x[1] <= u_max and (np.isnan(x[2]) or x[2] >= ring_min)


print("rule (SEEN share >=, unexplained cover <=, ring >=): kept of rest + flight | false kept: screen / worn / other")
for s_min, u_max, ring_min in ((0.25, 1.0, 0.0), (0.5, 1.0, 0.0), (0.7, 1.0, 0.0), (0.25, 0.5, 0.0), (0.25, 0.3, 0.0),
                               (0.25, 0.2, 0.0), (0.25, 1.0, 0.3), (0.25, 1.0, 0.5), (0.25, 0.3, 0.3), (0.25, 0.3, 0.5),
                               (0.25, 0.2, 0.5), (0.25, 0.2, 0.3), (0.25, 0.1, 0.3)):
    kg = sum(keep(x, s_min, u_max, ring_min) for x in good)
    kb = {c: sum(keep(x, s_min, u_max, ring_min) for x in v) for c, v in bad.items()}
    print(f"   ({s_min:.2f}, {u_max:.1f}, {ring_min:.1f}): {kg} / {len(good)} = {100 * kg / max(1, len(good)):.2f} % | "
          f"{kb['screen']} / {len(bad['screen'])}, {kb['worn']} / {len(bad['worn'])}, {kb['other']} / {len(bad['other'])}")
print()
print("resting drops: box bottom - foothold y at the lowest point of the bob, per item (n, values):")
for i, v in sorted(ground_off.items(), key=lambda x: -len(x[1])):
    b = Counter(int(round(x[0])) for x in v)
    print(f"   {i:8d} {it.name(i)[:26]:26s} n {len(v):3d} bottom-foothold {dict(sorted(b.items()))}")
if a.save:
    out = ROOT / "runs" / "loot_plan" / f"rules_{a.find}.json"
    out.write_text(json.dumps({c: [[float(x[0]), float(x[1]), None if np.isnan(x[2]) else float(x[2]), float(x[3]), x[4],
                                    x[5], x[6], list(x[7]), x[8], None if np.isnan(x[9]) else float(x[9]), x[10], x[11]]
                                   for x in v] for c, v in ALL.items()}), encoding="utf-8")
    print("->", out)
