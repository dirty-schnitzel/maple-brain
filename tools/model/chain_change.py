"""Does a mob leave its foothold chain, and how? (docs/prompts/tracker-plan.md, Part 1: the memory design leans on it)

    python tools/model/chain_change.py CAP [CAP ...]

Per mob life of the hindsight truth (oracle.chains): its standing sightings (stand / move pose, feet within 3 px of
a surface) name a chain. A change of chain is classed by what lies between the last sighting on A and the first on B:
    stitch    the change falls inside a gap the truth stitched (the mob was unseen: maybe two mobs joined)
    air       sightings in between with the feet > 3 px off every surface (a jump or a fall)
    direct    one frame to the next with no air sighting (a join, or a placement flip between close surfaces)
Per mob type: lives, lives that changed chain, changes by class; and the sideways / vertical size of the "air" ones.
Reads only, no GPU.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "track"))
sys.path.insert(0, str(ROOT / "tools" / "model"))
SETTLE = 15                      # standing sightings in a row (0.25 s at 60 a second) for "it lives on this chain"


def main():
    import dump
    import load
    import oracle
    from nav_audit import Index, nav_nolinks
    from maplebrain.config import Config
    tot = defaultdict(lambda: {"lives": 0, "changed": 0, "kinds": Counter(), "air": [], "jumper": False, "name": "",
                               "settled": [], "settled_lives": set()})
    for cap in sys.argv[1:]:
        mid = dump.meta(cap)["map"]
        mj = json.loads((ROOT / "assets" / "mcw" / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
        nm = nav_nolinks(mj, Config().nav)
        ix = Index(nm)
        info = {}
        for s in mj.get("mobs") or []:
            if s["id"] not in info:
                m = json.loads((ROOT / "assets" / "mcw" / "mobs" / str(s["id"]) / "mob.json").read_text(encoding="utf-8"))
                info[s["id"]] = (m["name"], "jump" in m["framebooks"], "fly" in m["framebooks"])
        tk = load.ticks(cap)
        for c in oracle.chains(tk):
            name, jumper, flyer = info.get(c["type"], (str(c["type"]), False, False))
            if flyer:
                continue
            key = (mj["name"], name)
            T = tot[key]
            T["jumper"], T["name"] = jumper, name
            pts, part_of = [], []
            for k, p in enumerate(c["parts"]):
                pts += p["pts"]
                part_of += [k] * len(p["pts"])
            if not pts:
                continue
            xs = np.array([q[oracle.X] for q in pts], float)
            ys = np.array([q[oracle.Y] for q in pts], float)
            pid, off = ix.nearest_many(xs, ys, 1e9)
            an = [load.anim_of(q[oracle.POSE]) for q in pts]
            T["lives"] += 1
            # settled changes: runs of >= SETTLE standing sightings in a row on one chain; a change = two such runs
            # on different chains inside one unstitched part (a pass through a platform's level mid-jump is 1-3
            # frames: not a run)
            runs, cur = [], None
            for i in range(len(pts)):
                if an[i] in ("stand", "move") and abs(off[i]) <= 3:
                    if cur is not None and cur[0] == int(pid[i]) and cur[3] == part_of[i]:
                        cur[2] = i
                    else:
                        if cur is not None and cur[2] - cur[1] + 1 >= SETTLE:
                            runs.append(tuple(cur))
                        cur = [int(pid[i]), i, i, part_of[i]]
            if cur is not None and cur[2] - cur[1] + 1 >= SETTLE:
                runs.append(tuple(cur))
            for a, b in zip(runs, runs[1:]):
                if a[0] != b[0] and a[3] == b[3]:
                    T["settled"].append((xs[b[1]] - xs[a[2]], ys[b[1]] - ys[a[2]], pts[b[1]][oracle.T] - pts[a[2]][oracle.T]))
                    T["settled_lives"].add(id(c))
            last = None                                       # (index, chain) of the last standing sighting
            changed = False
            for i in range(len(pts)):
                if an[i] not in ("stand", "move") or abs(off[i]) > 3:
                    continue
                if last is not None and int(pid[i]) != last[1]:
                    j = last[0]
                    between = range(j + 1, i)
                    if part_of[i] != part_of[j]:
                        kind = "stitch"
                    elif any(abs(off[b]) > 3 for b in between):
                        kind = "air"
                        T["air"].append((xs[i] - xs[j], ys[i] - ys[j], pts[i][oracle.T] - pts[j][oracle.T],
                                         float(min(off[b] for b in between))))
                    else:
                        kind = "direct"
                    T["kinds"][kind] += 1
                    changed = True
                last = (i, int(pid[i]))
            T["changed"] += changed
    print(f"{'map / mob':52s} {'jumps':5s} {'lives':>6s} {'changed':>8s}   changes by class")
    for key in sorted(tot):
        T = tot[key]
        air = np.array(T["air"], float).reshape(-1, 4)
        extra = ""
        if len(air):
            extra = (f"   air changes: |dx| p50/p90 {np.percentile(np.abs(air[:, 0]), 50):.0f}/{np.percentile(np.abs(air[:, 0]), 90):.0f},"
                     f" dy p10/p50/p90 {np.percentile(air[:, 1], 10):+.0f}/{np.percentile(air[:, 1], 50):+.0f}/"
                     f"{np.percentile(air[:, 1], 90):+.0f} px, highest above ground p50 {np.percentile(-air[:, 3], 50):.0f} px,"
                     f" s p50 {np.percentile(air[:, 2], 50):.2f}")
        st = np.array(T["settled"], float).reshape(-1, 3)
        if len(st):
            extra += (f"\n{'':52s} SETTLED on another chain (>= {SETTLE} standing frames each side, no stitch): {len(st)} changes "
                      f"in {len(T['settled_lives'])} lives; |dx| p50/p90 {np.percentile(np.abs(st[:, 0]), 50):.0f}/"
                      f"{np.percentile(np.abs(st[:, 0]), 90):.0f}, dy min/p50/max {st[:, 1].min():+.0f}/{np.percentile(st[:, 1], 50):+.0f}/"
                      f"{st[:, 1].max():+.0f} px, s between p50 {np.percentile(st[:, 2], 50):.2f}")
        print(f"{(key[0][:28] + ' / ' + key[1])[:52]:52s} {'yes' if T['jumper'] else 'no':5s} {T['lives']:6d} "
              f"{T['changed']:8d}   {dict(T['kinds'])}{extra}")


if __name__ == "__main__":
    main()
