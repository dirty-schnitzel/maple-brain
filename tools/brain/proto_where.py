"""Brain plan, prototype 2: WHERE NEXT - when the user leaves a platform, does a simple EXP-per-second score pick
the platform they went to? (PLAN-brain.md, "What was measured", 3). Open loop on a kept replay: the user's choices
are the answers, the score only ranks them.

    python tools/brain/proto_where.py CAP [--area auto|all|N,N,...] [--respawn 7.1] [--lam 0.5] [--tau 3.0]

A VISIT = consecutive standing frames on one node (1 s or more; air and rope frames between do not end it). At the
end of each visit that is followed by a visit to ANOTHER node, every candidate node N is scored from what the state
held at that frame:
    known(N)   mobs the tracker holds on N: seen (live / hit / tentative) + remembered (hidden / offscreen)
    due(N)     N's spawn points whose last seen spawn (the tracker's spawn_seen) is RESPAWN s or more ago by the time
               we would arrive, and whose mob from then is no longer held (dead or gone); a point with no spawn
               seen yet counts as due
    travel(N)  the graph's seconds table from the node we leave (track/graph.py: route()'s seconds)
    score(N) = (known(N) + lam * due(N)) / (travel(N) + tau)          - mobs per second of getting there + clearing
Baselines: the nearest node (least travel), the most mobs known, the most spawn points.
The candidates: --area auto = the nodes the user stood on for >= 2 % of standing frames in this capture (their
chosen area - what platform mode would mark), all = every floor node with a spawn point, or a list.
Report: how often the user's next node is the score's first / in its first three, against the baselines.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "brain"))
from proto_play import load_state, stay_dir  # noqa: E402
from maplebrain.track.graph import Graph, PLACES  # noqa: E402

HELD = ("live", "hit", "tentative", "hidden", "offscreen")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--area", default="auto")
    ap.add_argument("--respawn", type=float, default=7.1)
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--tau", type=float, default=3.0)
    a = ap.parse_args()
    d, stay = stay_dir(a.cap)
    g = Graph.for_map(stay["map"], ROOT / "assets" / "mcw")
    fr, events = load_state(a.cap)
    fx = np.array([f[1][0] if f[1] else np.nan for f in fr])
    fy = np.array([f[1][1] if f[1] else np.nan for f in fr])
    ok = ~np.isnan(fx)
    idx = np.flatnonzero(ok)
    pl = g.place(fx[ok], fy[ok], climb=np.ones(ok.sum(), bool))
    stand = collections.Counter(int(n) for n, p in zip(pl.node, pl.place) if PLACES[int(p)] == "stand")
    tot = max(1, sum(stand.values()))

    visits = []
    for k, (p, n) in enumerate(zip(pl.place, pl.node)):
        if PLACES[int(p)] != "stand":
            continue
        i = int(idx[k])
        if visits and visits[-1][0] == int(n):
            visits[-1][2], visits[-1][4] = fr[i][0], i
        else:
            visits.append([int(n), fr[i][0], fr[i][0], i, i])
    visits = [v for v in visits if v[2] - v[1] >= 1.0]

    spawn_nodes = collections.Counter(int(n) for n in g.spawn_node)
    if a.area == "auto":
        cand = sorted(n for n, c in stand.items() if c / tot >= 0.02 and n in spawn_nodes)
    elif a.area == "all":
        cand = sorted(spawn_nodes)
    else:
        cand = [int(x) for x in a.area.split(",")]
    print(f"{a.cap} {stay['name']}: {len(visits)} visits of 1 s or more; candidates ({a.area}): {cand}")

    # spawn history: point index -> [(t, mob id)]; mob id -> death / gone time
    sp_hist = collections.defaultdict(list)
    ended = {}
    for e in events:
        if e.get("ev") == "spawn_seen":
            sp_hist[int(e["point"])].append((e["t"], e["id"]))
        elif e.get("ev") in ("mob_died", "mob_gone", "mob_left"):
            ended.setdefault(e["id"], e["t"])
    pt_index = list(g.spawn_index)
    pt_node = {int(i): int(n) for i, n in zip(g.spawn_index, g.spawn_node)}

    def due(node, t_now, t_arrive):
        c = 0
        for pi, nn in pt_node.items():
            if nn != node:
                continue
            h = [x for x in sp_hist.get(pi, []) if x[0] <= t_now]
            if not h:
                c += 1
                continue
            t_sp, mid = h[-1]
            alive = ended.get(mid) is None or ended[mid] > t_now
            if not alive and t_arrive - t_sp >= a.respawn:
                c += 1
        return c

    hits = collections.Counter()
    n_dec = 0
    rows = []
    for v0, v1 in zip(visits, visits[1:]):
        if v1[0] == v0[0] or v0[0] not in g.index or v1[0] not in cand:
            continue
        i = v0[4]
        t = fr[i][0]
        known = collections.Counter(nd for (_, _, _, _, nd, s) in fr[i][7] if s in HELD)
        options = [n for n in cand if n != v0[0] and n in g.index]
        if v1[0] not in options or len(options) < 2:
            continue
        sc, near, most, pts, look2 = {}, {}, {}, {}, {}

        def sec(x, y):
            s_ = g.seconds(x, y)
            return s_ if np.isfinite(s_) else 60.0
        val = {n: known.get(n, 0) + a.lam * due(n, t, t + sec(v0[0], n)) for n in options}
        for n in options:
            tr = sec(v0[0], n)
            sc[n] = val[n] / (tr + a.tau)
            near[n] = -tr
            most[n] = known.get(n, 0) + 1e-3 * -tr
            pts[n] = spawn_nodes.get(n, 0) + 1e-3 * -tr
            # two steps: N, then the best M (the node we leave counts again: its points refill meanwhile)
            best = 0.0
            for m in [c for c in cand if c != n and c in g.index]:
                vm = val.get(m, a.lam * due(m, t, t + tr + a.tau + sec(n, m)))
                best = max(best, (val[n] + vm) / (tr + a.tau + sec(n, m) + a.tau))
            look2[n] = best
        n_dec += 1
        for name, s in (("score", sc), ("look 2", look2), ("nearest", near), ("most known", most),
                        ("most points", pts)):
            order = sorted(s, key=lambda n: -s[n])
            r = order.index(v1[0])
            hits[(name, 1)] += r == 0
            hits[(name, 3)] += r < 3
        rows.append((round(t, 1), v0[0], v1[0], sorted(sc, key=lambda n: -sc[n])[:3]))
    print(f"decisions: {n_dec} (leaving one candidate for another), {len(options)} options each at most")
    for name in ("score", "look 2", "nearest", "most known", "most points"):
        print(f"  {name:12s} first {hits[(name, 1)]:3d} ({hits[(name, 1)] / max(1, n_dec):.0%})   "
              f"in the first three {hits[(name, 3)]:3d} ({hits[(name, 3)] / max(1, n_dec):.0%})")
    print("  (t, left, went to, the score's first three):")
    for r in rows[:40]:
        print("   ", r)


if __name__ == "__main__":
    main()
