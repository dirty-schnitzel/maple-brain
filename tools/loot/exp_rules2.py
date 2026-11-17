"""E-L8c (PLAN-loot.md): the per-frame drop RULE, scored over every recording (find_v3: measured minimap mask, the
mob fit's explained pixels, characters' body boxes). Supersedes exp_rules.py's table.

    python tools/loot/exp_rules2.py [--find v3] [--runs a,b] [--save]

Every loose sighting (>= 40 SEEN px, SEEN share >= 0.25, ABSENT <= 0.15) gets its facts:
  s      SEEN share of the picture's opaque pixels on screen
  u      unexplained cover = 1 - (SEEN + ABSENT + under an accepted drop) / opaque
  mob    share of its SEEN pixels the mob fit's accepted mobs explained (it IS the mob: Stirge Wing on a Stirge)
  ring   share of the known pixels around the picture showing the scene / a drop / a fit mob / a character box
  dy     box bottom - the foothold under it (resting drops: -7..+5)
and a CLASS by behaviour only (no eye): rest (a group >= 20 frames, x fixed, y bobbing 3..8, at the resting height),
flight / pickup (short groups of the same item just before / after a rest group, near it), screen (fixed on screen
while the camera moves: UI), worn (equips not at rest), other.
Scored: the rule's two kinds - REST (dy in -7..+5, u <= U, mob < 0.5) and AIR (not at the resting height, u <= U,
mob < 0.5, ring >= R) - per class: how many sightings each rule keeps.
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
ap.add_argument("--find", default="v3")
ap.add_argument("--runs", default="")
ap.add_argument("--save", action="store_true")
ap.add_argument("--u", type=float, default=0.2)
ap.add_argument("--ring", type=float, default=0.3)
a = ap.parse_args()
it = Items()
S = []           # every sighting: dict
frames_total = 0
for run in [r for r in RUNS if not a.runs or any(x in r for x in a.runs.split(","))]:
    p = ROOT / run / "loot" / f"find_{a.find}.jsonl"
    if not p.exists():
        print("missing", p)
        continue
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = [r for r in rows if r.get("drops") is not None]
    frames_total += len(rows)
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

    groups, open_, sgroups, sopen = [], [], [], []
    for fi, r in enumerate(rows):
        cam, t = r["cam"], r["t"]
        for d in r["drops"]:
            n = max(1, d["n_op"])
            mx, my = d["pos"][0] + cam[0], d["pos"][1] + cam[1]
            byb = d["box"][1] + d["box"][3] + cam[1]
            gy = ground(d["box"][0] + d["box"][2] / 2 + cam[0], byb)
            # FRONT (unseen under front scenery of the foothold's layer) is explained cover only for a drop ON that
            # foothold: in the air the foothold below says nothing about the thing's layer
            at_rest = gy is not None and -7 <= byb - gy <= 5
            o = {"run": run[-10:], "fi": fi, "t": t, "item": d["item"], "box": d["box"], "mx": mx, "my": my, "cam": cam,
                 "s": d["n_seen"] / n,
                 "u": 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0) + (d.get("n_front", 0) if at_rest else 0)) / n,
                 "front": d.get("n_front", 0) / n,
                 "mob": d.get("n_mob", 0) / max(1, d["n_seen"]), "chr": d.get("n_char", 0) / max(1, d["n_seen"]),
                 "ring": d["ring_e2"] / d["ring_n2"] if d.get("ring_n2", 0) >= 60 else float("nan"),
                 "ring0": d["ring_e"] / d["ring_n"] if d.get("ring_n", 0) >= 60 else float("nan"),
                 "dy": byb - gy if gy is not None else float("nan"), "n_seen": d["n_seen"],
                 "fs": d["n_fseen"] / max(1, d["n_feat"]), "frame": r["frame"]}
            g = next((g for g in open_ if g["item"] == d["item"] and abs(g["mx"] - mx) <= 2 and abs(g["my"] - my) <= 10
                      and g["last"] != fi), None)
            if g is None:
                g = {"item": d["item"], "mx": mx, "my": my, "t0": t, "obs": [], "last": -1}
                open_.append(g)
                groups.append(g)
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
            S.append(o)
        open_ = [g for g in open_ if t - g["t1"] <= 2.0]
        sopen = [s for s in sopen if t - s["t1"] <= 1.0]
    for g in groups:
        ys = np.array([o["my"] for o in g["obs"]])
        xs = np.array([o["mx"] for o in g["obs"]])
        dys = np.array([o["dy"] for o in g["obs"]])
        g["rest"] = (len(g["obs"]) >= 20 and xs.max() - xs.min() <= 2 and 3 <= ys.max() - ys.min() <= 8
                     and np.nanmean((dys >= -7) & (dys <= 5)) >= 0.9)
    for s in sgroups:
        cx = np.array([o["cam"][0] for o in s["obs"]])
        cy = np.array([o["cam"][1] for o in s["obs"]])
        s["screen"] = len(s["obs"]) >= 12 and max(cx.max() - cx.min(), cy.max() - cy.min()) >= 12
    rest = [g for g in groups if g["rest"]]
    for g in groups:
        kind = "meso" if g["item"] >= 9000000 else it.kind(g["item"])
        c = "rest" if g["rest"] else None
        if c is None:
            for L in rest:
                if L["item"] != g["item"] or abs(g["mx"] - L["mx"]) > 160 or abs(g["my"] - L["my"]) > 170:
                    continue
                if 0 <= L["t0"] - g["t1"] <= 1.6:
                    c = "flight"
                    break
                if 0 <= g["t0"] - L["t1"] <= 0.8:
                    c = "pickup"
            if c is None:
                c = "worn" if kind in EQUIP else "other"
        for o in g["obs"]:
            o["cls"] = "screen" if o["sg"]["screen"] and c != "rest" else c
    print(f"{run[-17:]}: {len(rows)} frames, rest drops {len(rest)}, sightings {dict(Counter(o['cls'] for g in groups for o in g['obs']))}")

A = lambda key, v: np.array([o[key] for o in v], float)  # noqa: E731
q = lambda arr, p: float(np.nanpercentile(arr, p)) if len(arr) else float("nan")  # noqa: E731
print(f"\n{frames_total} frames, {len(S)} loose sightings")
by = defaultdict(list)
for o in S:
    by[o["cls"]].append(o)
for c in ("rest", "flight", "pickup", "screen", "worn", "other"):
    v = by.get(c) or []
    if not v:
        continue
    dy = A("dy", v)
    on = (dy >= -7) & (dy <= 5)
    print(f"{c:7s} n {len(v):6d} | SEEN p1 {q(A('s', v), 1):.2f} p5 {q(A('s', v), 5):.2f} p50 {q(A('s', v), 50):.2f} | unexplained "
          f"p95 {q(A('u', v), 95):.2f} p99 {q(A('u', v), 99):.2f}, <= {a.u}: {100 * (A('u', v) <= a.u).mean():.1f} % | mob >= 0.5: "
          f"{100 * (A('mob', v) >= 0.5).mean():.1f} % | ring p1 {q(A('ring', v), 1):.2f} p5 {q(A('ring', v), 5):.2f} p50 "
          f"{q(A('ring', v), 50):.2f} (scene + drops only: p1 {q(A('ring0', v), 1):.2f} p5 {q(A('ring0', v), 5):.2f}) | at the resting "
          f"height {100 * on.mean():.1f} %")
    if c in ("worn", "other", "screen"):
        print("        ", [(i, it.name(i)[:16], r, n) for (i, r), n in Counter((o["item"], o["run"]) for o in v).most_common(7)])


def rule(o, u=a.u, ring=a.ring):
    if o["u"] > u or o["mob"] >= 0.5:
        return None
    if -7 <= o["dy"] <= 5:
        return "REST"
    if np.isnan(o["ring"]) or o["ring"] >= ring:
        return "AIR"
    return None


print(f"\nthe rule (u <= {a.u}, mob < 0.5; REST at the resting height, AIR elsewhere with ring >= {a.ring}):")
for c in ("rest", "flight", "pickup", "screen", "worn", "other"):
    v = by.get(c) or []
    if not v:
        continue
    k = Counter(rule(o) for o in v)
    print(f"   {c:7s} n {len(v):6d}: REST {k['REST']:6d} ({100 * k['REST'] / len(v):5.1f} %)  AIR {k['AIR']:5d} "
          f"({100 * k['AIR'] / len(v):5.1f} %)  none {k[None]:5d}")
# what the rule calls REST / AIR outside the certain classes: by item (for the eye)
for kind in ("REST", "AIR"):
    v = [o for o in S if rule(o) == kind and o["cls"] in ("screen", "worn", "other")]
    c = Counter((o["cls"], o["item"]) for o in v)
    print(f"   {kind} outside rest / flight / pickup: {len(v)}: "
          + ", ".join(f"{cl} {it.name(i)[:14] if i < 9000000 else 'meso'} {n}" for (cl, i), n in c.most_common(12)))
print("\nu sweep, REST kept of the rest class | worn kept as REST or AIR | screen kept:")
for u in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4):
    kr = sum(rule(o, u) == "REST" for o in by["rest"])
    kw = sum(rule(o, u) is not None for o in by.get("worn") or [])
    ks = sum(rule(o, u) is not None for o in by.get("screen") or [])
    print(f"   u <= {u:.2f}: {100 * kr / max(1, len(by['rest'])):.2f} % | {kw} / {len(by.get('worn') or [])} | {ks} / "
          f"{len(by.get('screen') or [])}")
print("\nREST with a ring bar too (ring >= R or no ring): kept of the rest class | screen (UI) sightings kept as REST | as AIR:")
for R in (0.0, 0.1, 0.2, 0.3, 0.5):
    okr = lambda o: np.isnan(o["ring"]) or o["ring"] >= R  # noqa: E731
    kr = sum(rule(o) == "REST" and okr(o) for o in by["rest"])
    ks = sum(rule(o) == "REST" and okr(o) for o in by.get("screen") or [])
    ka = sum(rule(o, ring=R) == "AIR" for o in by.get("screen") or [])
    print(f"   R {R:.1f}: {100 * kr / max(1, len(by['rest'])):.2f} % | {ks} / {len(by.get('screen') or [])} | {ka}")
# per item: how many rest drops (groups) and sightings
gi = Counter()
for o in by["rest"]:
    gi[o["item"]] += 1
print("\nrest sightings by item:", ", ".join(f"{it.name(i)[:18] if i < 9000000 else 'meso' + str(i - 9000000)} {n}" for i, n in gi.most_common(20)))
if a.save:
    out = ROOT / "runs" / "loot_plan" / f"rules2_{a.find}.json"
    keep = ("run", "frame", "t", "item", "box", "s", "u", "mob", "chr", "ring", "ring0", "dy", "n_seen", "cls")
    out.write_text(json.dumps([{k: (None if isinstance(o[k], float) and np.isnan(o[k]) else o[k]) for k in keep} for o in S]),
                   encoding="utf-8")
    print("->", out)
