"""The data model's placement, measured on the kept replay (docs/prompts/tracker-plan.md, Part 1 item 2): how far
from a surface do the feet of each kind of thing sit, as today's perception reports them? That decides the one
placement rule's tolerance and what "how sure" (the distance to the surface) looks like per kind.

    python tools/model/place_footage.py CAP [CAP ...]      per capture + pooled
    python tools/model/place_footage.py --sound            the 13 sound captures of REPORT-track-before.md

Per kind, `off` = feet y - the nearest surface's y at the feet's x (map px, y down: + = below the surface):
    mobs      the fit's sightings (FrameFacts.fit), by animation; walkers and flyers apart
    us        our name tag (centre x, top y) + the camera
    players   the other name tags (ours, mobs' own tags and NPCs' taken out)
    drops     FrameFacts.drops kind "rest": the picture's bottom-centre
Also: does a mob ever change chain? (the hindsight truth's lives: the chains its standing sightings sit on)
Reads only. No GPU.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "track"))
sys.path.insert(0, str(ROOT / "tools" / "model"))

SOUND = ("20261121_000219_2#0 20261120_235747_1#0 20261118_232410_1#0 20261118_232410_1#1 20261118_232410_1#2 "
         "20261118_232410_1#3 20261118_232410_1#4 20261118_232410_1#5 20261118_232410_1#7 20261118_232410_1#9 "
         "20261118_232410_1#12 20261118_232410_1#13 20261119_204522_1#4").split()


def hist(v, edges=(-1e9, -40, -16, -9, -5, -3, -2, -1, 0, 1, 2, 3, 5, 9, 16, 40, 1e9)):
    """Counts of v in integer bins: '<-40', '-40..-17', ..., exact small values apart."""
    v = np.asarray(v, float)
    if not len(v):
        return "-"
    out = []
    labels = ["< -40", "-40..-17", "-16..-10", "-9..-6", "-5..-4", "-3", "-2", "-1", "0", "+1", "+2", "+3", "+4..5",
              "+6..9", "+10..16", "+17..40", "> +40"]
    bins = [(-1e9, -40.5), (-40.5, -16.5), (-16.5, -9.5), (-9.5, -5.5), (-5.5, -3.5), (-3.5, -2.5), (-2.5, -1.5),
            (-1.5, -0.5), (-0.5, 0.5), (0.5, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 5.5), (5.5, 9.5), (9.5, 16.5),
            (16.5, 40.5), (40.5, 1e9)]
    for lab, (lo, hi) in zip(labels, bins):
        n = int(((v > lo) & (v <= hi)).sum())
        if n:
            out.append(f"{lab}: {100 * n / len(v):.1f}%")
    return ", ".join(out)


def one(cap):
    import dump
    import load
    from nav_audit import Index, nav_nolinks
    from maplebrain.config import Config
    mid = dump.meta(cap)["map"]
    mj = json.loads((ROOT / "assets" / "mcw" / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
    nm = nav_nolinks(mj, Config().nav)
    ix = Index(nm)
    mobs_json = {}
    for s in mj.get("mobs") or []:
        if s["id"] not in mobs_json:
            mobs_json[s["id"]] = json.loads((ROOT / "assets" / "mcw" / "mobs" / str(s["id"]) / "mob.json")
                                            .read_text(encoding="utf-8"))
    flyers = {i for i, m in mobs_json.items() if (m.get("frames") or {}).get("fly")}
    npcs = [(n["x"], n["y"]) for n in mj.get("npcs") or []]
    rows = dump.rows(cap)
    res = defaultdict(list)                                  # kind -> [off]
    n_tag = n_me = 0
    X, Y, K = [], [], []
    for r in rows:
        C = r["C"]
        if C is None:
            continue
        f = r["facts"]
        fit = f.get("fit") or []
        for m in fit:
            anim = m["pose"].rsplit("_", 1)[0]
            cls = "fly" if m["type"] in flyers else ("jump" if anim.startswith("jump") else
                                                     "die" if anim.startswith("die") else
                                                     "hit" if anim.startswith("hit") else
                                                     "stand/move" if anim in ("stand", "move") else anim)
            X.append(m["feet"][0] + C[0])
            Y.append(m["feet"][1] + C[1])
            K.append("mob " + cls + ("" if m["opacity"] >= 0.9 else " (fading)"))
        tag = f.get("tag")
        if tag is not None:
            n_me += 1
            X.append(tag[0] + tag[2] / 2 + C[0])
            Y.append(tag[1] + C[1])
            K.append("us")
        for x, y, w, h in f.get("tags") or []:
            cx, ty = x + w / 2, y
            if tag is not None and abs(cx - (tag[0] + tag[2] / 2)) < 12 and abs(ty - tag[1]) < 8:
                continue                                     # ours
            if any(abs(cx - m["feet"][0]) < 30 and -6 <= ty - m["feet"][1] <= 30 for m in fit):
                continue                                     # a mob's own tag (world._occlusion's rule)
            mx, my = cx + C[0], ty + C[1]
            if any(abs(mx - nx) < 40 and abs(my - ny) < 40 for nx, ny in npcs):
                continue                                     # an NPC's
            n_tag += 1
            X.append(mx)
            Y.append(my)
            K.append("player tag")
        for d in f.get("drops") or []:
            if d.get("kind") == "rest":
                res["drop rest (dy as the finder reports it)"].append(d["dy"])
    if X:
        X, Y = np.array(X, float), np.array(Y, float)
        for a in range(0, len(X), 20000):                    # N x S broadcast in pieces
            pid, off = ix.nearest_many(X[a:a + 20000], Y[a:a + 20000], 1e9)
            for k, o in zip(K[a:a + 20000], off):
                res[k].append(float(o))
    # --- does a mob change chain? the hindsight truth's lives
    tk = load.ticks(cap)
    import oracle
    ch = oracle.chains(tk)
    lives = moved = 0
    kinds = Counter()
    floor_of = floors(nm)
    for c in ch:
        seq = []
        for p in c["parts"]:
            pts = p["pts"]
            xs = np.array([q[oracle.X] for q in pts], float)
            ys = np.array([q[oracle.Y] for q in pts], float)
            an = [load.anim_of(q[oracle.POSE]) for q in pts]
            pid, off = ix.nearest_many(xs, ys, 3.0) if len(xs) else ([], [])
            for a, pp in zip(an, pid):
                if a in ("stand", "move") and pp >= 0 and (not seq or seq[-1] != int(pp)):
                    seq.append(int(pp))
        if c["type"] in flyers or not seq:
            continue
        lives += 1
        if len(set(seq)) > 1:
            moved += 1
            for a, b in zip(seq, seq[1:]):
                kinds["same floor (a join)" if floor_of[a] == floor_of[b] else "another floor"] += 1
    return res, {"lives": lives, "moved": moved, "kinds": kinds, "frames": len(rows), "map": mj["name"]}


def floors(nm):
    """chain id -> floor id (chains joined end to end at the same height, both ways)."""
    from nav_audit import UF, joins
    uf = UF(nm.platforms)
    for k, a, b, _ in joins(nm):
        if k == "end-end":
            uf.join(a, b)
    return {i: uf.find(i) for i in nm.platforms}


def show(name, res, extra=None):
    print(f"== {name}")
    for k in sorted(res):
        v = np.array(res[k], float)
        near = v[np.abs(v) <= 40]
        print(f"   {k:44s} n {len(v):7d}   {hist(v)}")
        if len(near) and k.startswith(("us", "player", "mob stand", "mob hit", "mob die", "drop")):
            print(f"   {'':44s} within 40 px: median {np.median(near):+.1f}, |off - median| <= 1: "
                  f"{100 * np.mean(np.abs(near - np.median(near)) <= 1):.1f}%, <= 2: "
                  f"{100 * np.mean(np.abs(near - np.median(near)) <= 2):.1f}%, <= 4: "
                  f"{100 * np.mean(np.abs(near - np.median(near)) <= 4):.1f}%")
    if extra:
        print(f"   mob lives (walkers, the hindsight truth): {extra['lives']}; with standing sightings on more than one "
              f"chain: {extra['moved']}; the changes: {dict(extra['kinds'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    a = ap.parse_args()
    caps = SOUND if a.sound else a.caps
    pool = defaultdict(list)
    tot = {"lives": 0, "moved": 0, "kinds": Counter()}
    for cap in caps:
        res, ex = one(cap)
        show(f"{cap} ({ex['map']}, {ex['frames']} frames)", res, ex)
        for k, v in res.items():
            pool[k] += v
        tot["lives"] += ex["lives"]
        tot["moved"] += ex["moved"]
        tot["kinds"].update(ex["kinds"])
    if len(caps) > 1:
        show(f"POOLED ({len(caps)} captures)", pool, tot)


if __name__ == "__main__":
    main()
