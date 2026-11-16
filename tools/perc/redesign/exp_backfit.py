"""E8: where does the client draw each background layer? Measured, not assumed, per recording - then one formula
for all maps.

    python exp_backfit.py fit RUN [N]       -> RUN/backfit.json: per frame the exact camera (scene registration on
                                               tiles / objects) and per (rx, ry) group of layers the shift from
                                               today's `scene.back_pos` that explains the most pixels
    python exp_backfit.py solve RUN [RUN..] -> which arithmetic reproduces every measured position

A measurement counts only where the layer shows: the best shift must beat the runner-up by MARGIN pixels.
RESULT 2026-11-16, 7 maps (Ant Tunnel IV, Dark Cave, Dangerous Steam, Line 1, Transfer Area, Perion Street Corner,
Land of Wild Boar): `off + trunc(r * (C + off) / 100)` with off 683 (x) / 468 (y) - the numbers are in HANDOFF.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))

REACH, MARGIN = 6, 1500


from frames import map_of, read  # noqa: E402  (read: a recording's 1 px capture error undone, RUN/xshift.txt)


def fit(run: Path, n: int = 40):
    import torch
    from maplebrain.scene import PLAY_H, Scene, back_pos
    from scene_check import ui_mask
    scene = Scene.load(map_of(run))
    ticks = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame") and k["obs"].get("cam")]
    ticks = [ticks[int(i * (len(ticks) - 1) / max(1, n - 1))] for i in range(min(n, len(ticks)))]
    ui = torch.from_numpy(ui_mask(PLAY_H, 1366)).to(scene.dev)
    groups = defaultdict(list)
    for b, _ in scene.backs:
        if b["known"]:
            groups[(b["rx"], b["ry"])].append(b)
    orig = {id(b): (b["x"], b["y"]) for b, _ in scene.backs}
    rows = []
    for k in ticks:
        frame = read(run, k["frame"])
        ft = torch.from_numpy(np.ascontiguousarray(frame[:PLAY_H])).to(scene.dev)
        reg = scene.locate(ft, seed=k["obs"]["cam"], mask=ui)
        if reg is None:
            continue
        C = reg[0]

        def score():
            e, kn = scene.expected(C)
            return int((((ft.float() - e).abs().amax(dim=2) <= 4) & kn & ui).sum())

        row = {"frame": k["frame"], "C": C, "groups": []}
        for _ in range(2):                                           # twice: the groups hide each other
            row["groups"] = []
            for g, bs in groups.items():
                got = {}
                for ax in (0, 1):
                    key = "xy"[ax]
                    sc = {}
                    for d in range(-REACH, REACH + 1):
                        for b in bs:
                            b[key] += d
                        sc[d] = score()
                        for b in bs:
                            b[key] -= d
                    best = max(sc, key=sc.get)
                    second = max(v for d, v in sc.items() if d != best)
                    for b in bs:
                        b[key] += best
                    got[key] = (best, sc[best] - second)
                b0 = bs[0]
                tot = (b0["x"] - orig[id(b0)][0], b0["y"] - orig[id(b0)][1])
                # position of the layer's origin relative to its own (x, y), as measured
                px, py = back_pos(dict(b0, x=0, y=0, origin=[0, 0], flip=0), C)
                row["groups"].append({"r": g, "pos": (px + tot[0], py + tot[1]), "d": tot,
                                      "margin": (got["x"][1], got["y"][1])})
        for b, _ in scene.backs:
            b["x"], b["y"] = orig[id(b)]
        rows.append(row)
        print(k["frame"][:6], C, " ".join(f"r{tuple(q['r'])} d{tuple(q['d'])} m{tuple(q['margin'])}" for q in row["groups"]),
              flush=True)
    (run / "backfit.json").write_text(json.dumps({"map": map_of(run), "rows": rows}))


RND = {"trunc": lambda v: int(v), "floor": lambda v: int(np.floor(v)), "ceil": lambda v: int(np.ceil(v)),
       "round": lambda v: int(np.floor(v + 0.5))}


def forms():
    """Candidate arithmetic: name -> f(r, C, off)."""
    out = {}
    for name, rnd in RND.items():
        out[f"off + {name}(r*(C+off)/100)"] = lambda r, C, off, rnd=rnd: off + rnd(r * (C + off) / 100)
        out[f"-C + {name}((100+r)*(C+off)/100)"] = lambda r, C, off, rnd=rnd: -C + rnd((100 + r) * (C + off) / 100)
    return out


def solve(runs):
    obs = {0: [], 1: []}                                             # axis -> (run, r, C, pos)
    for run in runs:
        d = json.loads((run / "backfit.json").read_text())
        for row in d["rows"]:
            for q in row["groups"]:
                for ax in (0, 1):
                    if q["margin"][ax] >= MARGIN and q["r"][ax] != -100:
                        obs[ax].append((run.name, q["r"][ax], row["C"][ax], q["pos"][ax]))
    for ax in (0, 1):
        o = obs[ax]
        print(f"axis {'xy'[ax]}: {len(o)} measured positions on {len({x[0] for x in o})} runs, r values "
              f"{sorted({x[1] for x in o})}")
        res = []
        for name, f in forms().items():
            for off in range(300, 760):
                hit = sum(f(r, C, off) == p for _, r, C, p in o)
                res.append((hit, name, off))
        res.sort(reverse=True)
        for hit, name, off in res[:6]:
            per = defaultdict(lambda: [0, 0])
            for run, r, C, p in o:
                per[run][0] += f_ok(name, r, C, off, p)
                per[run][1] += 1
            print(f"  {hit:5d} of {len(o)}  {name}, off {off}   per run: " +
                  " ".join(f"{k[-8:]}:{a}/{b}" for k, (a, b) in sorted(per.items())))


def f_ok(name, r, C, off, p):
    return forms()[name](r, C, off) == p


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        fit(ROOT / sys.argv[2] if not Path(sys.argv[2]).is_absolute() else Path(sys.argv[2]),
            int(sys.argv[3]) if len(sys.argv) > 3 else 40)
    else:
        solve([ROOT / a for a in sys.argv[2:]])
