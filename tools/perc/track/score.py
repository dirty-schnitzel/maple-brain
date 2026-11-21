"""Tracker plan: grade a tracker's tracks against the hindsight truth (oracle.chains) - the plan's gate numbers.

    python tools/perc/track/score.py CAP [CAP ...]           today's tracker as the capture's ticks hold it (a
                                                             bank capture: the kept replay, dump.py, every frame)
    python tools/perc/track/score.py CAP --rows FILE.jsonl   another tracker's rows ({"n", "t", "mobs"}: a prototype)
    python tools/perc/track/score.py CAP [CAP ...] --pool    + the numbers of all of them together

Truth: a chain = one mob's life as the fit alone saw it, stitched across its unseen moments in hindsight.
HELD      a gap inside a chain (alive, unseen, >= 1 graded tick): the track on it before the gap is the track on
          it after the gap. By gap length; "by us" = within 220 px of our feet.
DEAD-LIVE a chain shows its first die pose at tick d: seconds from d until its track stops saying live / hit /
          hidden (0 = dying on that very tick). Chains that just VANISH (no die pose seen, not at an edge): seconds
          their track stayed live after the last sighting.
GHOST     live track-frames on screen with no chain (alive or dying, gaps interpolated) within 40 px.
SWITCHES  extra track ids per chain (0 = one track from birth to death).
FOUND     chain ticks in a live pose with a confirmed track of its type within 24 px.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from load import ROOT, anim_of, map_of, name_of, pct, ticks
from oracle import I, O, POSE, SX, SY, T, X, Y, chains, die_t, edge

LIVE = ("live", "hit", "hidden")
SW, PLAY_H = 1366, 700


def index(tk, ch) -> list:
    """Per chain: {tick index: point}, [(i_end, i_start)] gaps, first / last index, first die index."""
    out = []
    for c in ch:
        pts = {q[I]: q for p in c["parts"] for q in p["pts"]}
        gaps = [(c["parts"][k]["pts"][-1][I], c["parts"][k + 1]["pts"][0][I]) for k in range(len(c["parts"]) - 1)]
        d = next((i for i in sorted(pts) if anim_of(pts[i][POSE]).startswith("die")), None)
        out.append({"c": c, "pts": pts, "gaps": gaps, "i0": min(pts), "i1": max(pts), "die": d})
    return out


def pos_at(ci, i):
    """The chain's map feet at tick index i: its point, or the line across the gap it is in."""
    q = ci["pts"].get(i)
    if q is not None:
        return q[X], q[Y]
    for a, b in ci["gaps"]:
        if a < i < b:
            qa, qb = ci["pts"][a], ci["pts"][b]
            w = (i - a) / (b - a)
            return qa[X] + w * (qb[X] - qa[X]), qa[Y] + w * (qb[Y] - qa[Y])
    return None


def match(mobs, typ, x, y, r=24.0, states=None):
    """The confirmed track of this type nearest (x, y) within r (sighted ones first) -> its dict or None."""
    best = None
    for m in mobs:
        if m["state"] == "tentative" or m["mob"] != typ or (states and m["state"] not in states):
            continue
        dx, dy = abs(m["x"] - x), abs(m["y"] - y)
        if dx <= r and dy <= r:
            key = (m.get("src", "none") == "none", dx + dy)
            if best is None or key < best[0]:
                best = (key, m)
    return best[1] if best else None


def score(tk, ch, rows, me_of=None) -> dict:
    """`tk`: the truth's ticks; `ch`: chains over them; `rows`: the graded tracker's rows ({"n", "t", "mobs"}), any
    subset of the ticks. -> the numbers (see the module doc)."""
    n2i = {k["n"]: i for i, k in enumerate(tk)}
    row_at = {n2i[r["n"]]: r for r in rows if r["n"] in n2i}
    ri = np.array(sorted(row_at))                                  # tick indices that were graded
    cis = index(tk, ch)
    held, dead, van, sw, found = [], [], [], [], [0, 0]
    for ci in cis:
        c = ci["c"]
        typ = c["type"]
        ids = []
        for i in ri[(ri >= ci["i0"]) & (ri <= ci["i1"])]:
            q = ci["pts"].get(int(i))
            if q is None or anim_of(q[POSE]).startswith("die"):
                continue
            m = match(row_at[int(i)]["mobs"], typ, q[X], q[Y])
            found[0] += 1
            found[1] += m is not None
            if m is not None and (not ids or ids[-1] != m["id"]):
                ids.append(m["id"])
        sw.append(max(0, len(ids) - 1))
        # --- gaps
        for (a, b), g in zip(ci["gaps"], c["gaps"]):
            ra = ri[(ri <= a) & (ri >= ci["i0"])]
            ra = [int(i) for i in ra if int(i) in ci["pts"]]
            rb = [int(i) for i in ri[(ri >= b) & (ri <= ci["i1"])] if int(i) in ci["pts"]]
            if not ra or not rb:
                continue
            ia, ib = ra[-1], rb[0]
            if not ((ri > ia) & (ri < ib)).any():
                continue                                           # no graded tick inside the gap
            qa, qb = ci["pts"][ia], ci["pts"][ib]
            if anim_of(qa[POSE]).startswith("die"):
                continue
            ma = match(row_at[ia]["mobs"], typ, qa[X], qa[Y])
            mb = match(row_at[ib]["mobs"], typ, qb[X], qb[Y])
            me = me_of(ia) if me_of else None
            by_us = me is not None and abs(qa[X] - me[0]) <= 220 and abs(qa[Y] - me[1]) <= 90
            held.append({"dt": tk[ib]["t"] - tk[ia]["t"], "dx": qb[X] - qa[X], "tracked": ma is not None,
                         "held": ma is not None and mb is not None and ma["id"] == mb["id"], "by_us": by_us,
                         "to_die": anim_of(qb[POSE]).startswith("die"), "t": tk[ia]["t"], "type": typ,
                         "sx": qa[SX], "sy": qa[SY], "amb": g[4]})
        # --- death / vanish
        d = ci["die"]
        last_live = [i for i in sorted(ci["pts"]) if not anim_of(ci["pts"][i][POSE]).startswith("die")]
        if d is not None and last_live:
            before = [int(i) for i in ri[ri < d] if int(i) in ci["pts"] and int(i) <= last_live[-1]]
            after = [int(i) for i in ri[ri >= d]]
            if before and after:
                q = ci["pts"][before[-1]]
                m = match(row_at[before[-1]]["mobs"], typ, q[X], q[Y])
                if m is not None:
                    t_leave = None
                    for i in after:
                        st = next((x["state"] for x in row_at[i]["mobs"] if x["id"] == m["id"]), None)
                        if st not in LIVE:
                            t_leave = tk[i]["t"]
                            break
                    if t_leave is not None:
                        dead.append({"s": t_leave - tk[after[0]]["t"], "t": tk[d]["t"], "id": m["id"]})
        elif d is None and c["end"] == "vanished":
            seen = [int(i) for i in ri[(ri >= ci["i0"]) & (ri <= ci["i1"])] if int(i) in ci["pts"]]
            if seen:
                q = ci["pts"][seen[-1]]
                m = match(row_at[seen[-1]]["mobs"], typ, q[X], q[Y])
                if m is not None:
                    t_leave = None
                    for i in ri[ri > seen[-1]]:
                        st = next((x["state"] for x in row_at[int(i)]["mobs"] if x["id"] == m["id"]), None)
                        if st not in LIVE:
                            t_leave = tk[int(i)]["t"]
                            break
                    if t_leave is not None:
                        van.append({"s": t_leave - tk[seen[-1]]["t"], "t": tk[seen[-1]]["t"], "id": m["id"],
                                    "sx": q[SX], "sy": q[SY]})
    # --- ghosts: live track-frames with no chain near
    alive = {}
    for k, ci in enumerate(cis):
        for i in ri[(ri >= ci["i0"]) & (ri <= ci["i1"])]:
            p = pos_at(ci, int(i))
            if p is not None:
                alive.setdefault(int(i), []).append(p)
    ghost = [0, 0]
    ghost_ids = Counter()
    for i in ri:
        r = row_at[int(i)]
        ps = alive.get(int(i), [])
        for m in r["mobs"]:
            if m["state"] not in LIVE or not (0 <= m["sx"] < SW and 0 <= m["sy"] < PLAY_H):
                continue
            ghost[0] += 1
            if not any(abs(m["x"] - x) <= 40 and abs(m["y"] - y) <= 40 for x, y in ps):
                ghost[1] += 1
                ghost_ids[m["id"]] += 1
    return {"held": held, "dead": dead, "van": van, "sw": sw, "found": found, "ghost": ghost, "ghost_ids": ghost_ids,
            "chains": len(cis), "rows": len(ri)}


def report(s, name="") -> str:
    h = s["held"]
    L = [f"{name}: {s['chains']} chains, {s['rows']} graded ticks; found {100 * s['found'][1] / max(1, s['found'][0]):.1f} % of "
         f"{s['found'][0]} live chain-ticks"]
    tr = [x for x in h if x["tracked"]]
    L.append(f"  HELD: {sum(x['held'] for x in tr)} / {len(tr)} gaps = {100 * np.mean([x['held'] for x in tr]) if tr else 0:.1f} % "
             f"(+ {len(h) - len(tr)} gaps of mobs it had no track on)")
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 99)):
        b = [x for x in tr if lo < x["dt"] <= hi]
        if b:
            L.append(f"     gap {lo}-{hi} s: {sum(x['held'] for x in b):3d} / {len(b):3d} = {100 * np.mean([x['held'] for x in b]):5.1f} %"
                     f"   |dx| > 30 px: {sum(x['held'] for x in b if abs(x['dx']) > 30)} / {sum(1 for x in b if abs(x['dx']) > 30)}")
    bu = [x for x in tr if x["by_us"]]
    if bu:
        L.append(f"     by us: {sum(x['held'] for x in bu)} / {len(bu)} = {100 * np.mean([x['held'] for x in bu]):.1f} %")
    d = [x["s"] for x in s["dead"]]
    if d:
        L.append(f"  DEAD-LIVE (die pose seen, n {len(d)}): s p50/p90/max {pct(d, (50, 90, 100))}; > 0.1 s: {np.mean(np.array(d) > 0.1):.0%}")
    v = [x["s"] for x in s["van"]]
    if v:
        L.append(f"  VANISHED (no die pose, n {len(v)}): track stayed live s p50/p90/max {pct(v, (50, 90, 100))}")
    g = s["ghost"]
    L.append(f"  GHOST: {g[1]} of {g[0]} live track-frames = {100 * g[1] / max(1, g[0]):.2f} % (tracks: {len(s['ghost_ids'])})")
    sw = np.array(s["sw"])
    L.append(f"  SWITCHES: {int(sw.sum())} extra ids over {len(sw)} chains ({100 * np.mean(sw == 0):.1f} % of chains on one track)")
    return "\n".join(L)


def merge(ss: list) -> dict:
    """Several captures' score dicts -> one (lists joined, counts added)."""
    out = {"held": [], "dead": [], "van": [], "sw": [], "found": [0, 0], "ghost": [0, 0], "ghost_ids": Counter(),
           "chains": 0, "rows": 0}
    for k, s in enumerate(ss):
        for key in ("held", "dead", "van", "sw"):
            out[key] += s[key]
        for key in ("found", "ghost"):
            out[key] = [out[key][0] + s[key][0], out[key][1] + s[key][1]]
        out["ghost_ids"].update({(k, i): n for i, n in s["ghost_ids"].items()})
        out["chains"] += s["chains"]
        out["rows"] += s["rows"]
    return out


def me_fn(tk):
    def me_of(i):
        k = tk[i]
        if k.get("me_map"):
            return k["me_map"]
        if k.get("me") and k.get("C"):
            return (k["me"][0] + k["C"][0], k["me"][1] + k["C"][1])        # (our tag: centre x, top y)
        return None
    return me_of


def score_cap(cap, rows_file=None) -> dict:
    tk = ticks(cap)
    ch = chains(tk)
    if rows_file:
        p = Path(rows_file) if Path(rows_file).is_absolute() else ROOT / rows_file
        rows = [json.loads(x) for x in open(p, encoding="utf-8")]
    else:
        rows = tk
    return score(tk, ch, rows, me_fn(tk))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--rows", default=None)
    ap.add_argument("--pool", action="store_true")
    a = ap.parse_args()
    ss = []
    for cap in a.caps:
        s = score_cap(cap, a.rows)
        ss.append(s)
        print(report(s, f"{name_of(cap)} [{Path(a.rows).stem if a.rows else 'today' + chr(39) + 's tracker, every frame'}]"),
              flush=True)
    if a.pool and len(ss) > 1:
        print(report(merge(ss), f"POOLED ({len(ss)} captures)"))
    _ = map_of, edge, die_t, O


if __name__ == "__main__":
    main()
