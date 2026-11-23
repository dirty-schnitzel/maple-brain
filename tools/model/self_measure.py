"""The data model's dynamic values, "measured live" tried on a recording (docs/prompts/tracker-plan.md, Part 1 item 6):
can our own walk speed, jump, swing length and EXP per kill be read off what perception already reports + our keys?

    python tools/model/self_measure.py CAP

Inputs: the kept replay's rows (our tag + the camera -> our feet on the map, HUD HP / MP / EXP) and the capture's
keys.jsonl. Reads only, no GPU.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "track"))
sys.path.insert(0, str(ROOT / "tools" / "model"))


def pct(v, ps=(5, 25, 50, 75, 95)):
    v = np.asarray(v, float)
    return [round(float(np.percentile(v, p)), 1) for p in ps] if len(v) else None


def held_at(keys, name):
    """[(t_down, t_up)] of one key."""
    out, down = [], None
    for k in keys:
        if k["key"] != name:
            continue
        if k["down"] and down is None:
            down = k["t"]
        elif not k["down"] and down is not None:
            out.append((down, k["t"]))
            down = None
    return out


def main():
    cap = sys.argv[1]
    import dump
    import load
    from nav_audit import Index, nav_nolinks
    from maplebrain.config import Config
    mid = dump.meta(cap)["map"]
    mj = json.loads((ROOT / "assets" / "mcw" / "maps" / str(mid) / "map.json").read_text(encoding="utf-8"))
    ix = Index(nav_nolinks(mj, Config().nav))
    rows = dump.rows(cap)
    keys = load.keys(cap)
    print(f"{cap}: {len(rows)} frames, {len(keys)} key events; keys pressed: "
          f"{dict(Counter(k['key'] for k in keys if k['down']).most_common(16))}")
    t = np.array([r["t"] for r in rows])
    ok = np.array([r["me_map"] is not None for r in rows])
    x = np.array([r["me_map"][0] if r["me_map"] else np.nan for r in rows])
    y = np.array([r["me_map"][1] if r["me_map"] else np.nan for r in rows])
    print(f"our feet known on {ok.mean():.1%} of frames; frame gap ms p50/p99 {pct(1000 * np.diff(t), (50, 99))}")
    pid, off = ix.nearest_many(np.nan_to_num(x), np.nan_to_num(y), 1e9)
    off = np.where(ok, off, np.nan)
    stand = np.abs(off - np.nanmedian(off[np.abs(off) < 20])) <= 2
    print(f"standing (feet within 2 px of a surface): {np.nanmean(stand):.1%} of frames; the tag's own offset: "
          f"{np.nanmedian(off[np.abs(off) < 20]):+.0f} px")

    def in_any(spans, tt):
        a = np.zeros(len(tt), bool)
        for d, u in spans:
            a |= (tt >= d) & (tt <= u)
        return a

    left, right = in_any(held_at(keys, "left"), t), in_any(held_at(keys, "right"), t)
    # --- walk speed: over 0.25 s windows while one walk key is held the whole window and we stand the whole window
    W = 15
    v = []
    for i in range(0, len(t) - W, 5):
        s = slice(i, i + W + 1)
        if not (stand[s].all() and ok[s].all()):
            continue
        if left[s].all() != right[s].all() and (left[s].all() or right[s].all()):
            if (pid[s] == pid[i]).all():
                v.append(abs(x[i + W] - x[i]) / (t[i + W] - t[i]))
    v = np.array(v)
    print(f"WALK: |vx| over 0.25 s windows on one chain with one walk key held throughout: n {len(v)}, px/s "
          f"p5/p25/p50/p75/p95 {pct(v)}; the top plateau (p90-p99) {pct(v, (90, 95, 99))}")
    h = np.histogram(v, bins=np.arange(0, 220, 10))
    print("      histogram (10 px/s bins from 0): " + " ".join(str(int(n)) for n in h[0]))
    # --- jumps: from a jump-key press while standing: the apex above the take-off height, the air time, the x travel
    jkey = Config().keys.jump
    apex, air, dx, vxs = [], [], [], []
    for d, u in held_at(keys, jkey):
        i = int(np.searchsorted(t, d))
        if i < 2 or i + 90 >= len(t) or not stand[i - 1] or not ok[i:i + 90].all():
            continue
        j = i
        while j < i + 12 and stand[j]:                      # the frame we leave the ground
            j += 1
        if j == i + 12:
            continue
        k = j
        while k < j + 80 and not stand[k]:
            k += 1
        if k == j + 80:
            continue
        y0 = y[j - 1]
        up = y0 - np.nanmin(y[j:k])
        if up < 20:
            continue
        land_dy = y[k] - y0
        apex.append(up)
        if abs(land_dy) <= 3:                                # landed at the take-off height: a level hop
            air.append(t[k] - t[j - 1])
            dx.append(abs(x[k] - x[j - 1]))
            if air[-1] > 0.2:
                vxs.append(dx[-1] / air[-1])
    print(f"JUMP ({jkey}): n {len(apex)}; apex above take-off px {pct(apex)}; level hops n {len(air)}: air s {pct(air)}, "
          f"x travel px {pct(dx)}, sideways px/s {pct(vxs)}")
    # --- rope climbing speed: frames where up / down is held and we are off every surface, moving only in y
    upk, dnk = in_any(held_at(keys, "up"), t), in_any(held_at(keys, "down"), t)
    cv = []
    for i in range(0, len(t) - W, 5):
        s = slice(i, i + W + 1)
        if ok[s].all() and (upk[s].all() or dnk[s].all()) and not stand[s].any() and np.ptp(x[s]) <= 1:
            cv.append(abs(y[i + W] - y[i]) / (t[i + W] - t[i]))
    cv = np.array(cv)
    print(f"CLIMB: |vy| over 0.25 s windows with up / down held, x still, off every surface: n {len(cv)}, px/s {pct(cv)}")
    # --- the HUD: MP steps (casts), HP steps (hurt), EXP steps (kills we damaged)
    mp = [(r["t"], r["facts"]["mp"][0]) for r in rows if r["facts"].get("mp")]
    hp = [(r["t"], r["facts"]["hp"][0]) for r in rows if r["facts"].get("hp")]
    ex = [(r["t"], r["facts"]["exp_points"]) for r in rows if r["facts"].get("exp_points") is not None]
    print(f"HUD read: HP on {len(hp) / len(rows):.1%} of frames, MP {len(mp) / len(rows):.1%}, EXP {len(ex) / len(rows):.1%}")

    def steps(series):
        out, last = [], None
        for tt, vv in series:
            if last is not None and vv != last:
                out.append((tt, vv - last))
            last = vv
        return out

    ms = steps(mp)
    drops = [(tt, -d) for tt, d in ms if d < 0]
    print(f"MP: {len(ms)} changes; drops by size {dict(Counter(d for _, d in drops).most_common(8))}; rises "
          f"{dict(Counter(d for _, d in ms if d > 0).most_common(6))}")
    att = Config().keys.attack
    presses = [k["t"] for k in keys if k["down"] and k["key"] == att]
    if drops and presses:
        pr = np.array(presses)
        lag = []
        for tt, d in drops:
            i = np.searchsorted(pr, tt) - 1
            if i >= 0:
                lag.append(tt - pr[i])
        lag = np.array(lag)
        print(f"   MP drop after the last '{att}' press, s: {pct(lag[lag < 2])}  (n {int((lag < 2).sum())} of {len(drops)} drops)")
        cast_t = np.array([tt for tt, d in drops])
        gaps = np.diff(cast_t)
        g = gaps[gaps < 2.0]
        print(f"   gaps between MP drops < 2 s: n {len(g)}, s p1/p5/p25/p50 {pct(g, (1, 5, 25, 50))}; histogram 0.5-1.3 s by "
              f"0.05: " + " ".join(str(int(n)) for n in np.histogram(g, bins=np.arange(0.5, 1.35, 0.05))[0]))
    es = steps(ex)
    print(f"EXP: {len(es)} changes; by size {dict(Counter(d for _, d in es).most_common(12))}")
    hs = steps(hp)
    print(f"HP: {len(hs)} changes; drops {sum(1 for _, d in hs if d < 0)} (sizes p5/p50/p95 "
          f"{pct([-d for _, d in hs if d < 0], (5, 50, 95))}), rises {sum(1 for _, d in hs if d > 0)} "
          f"(sizes {dict(Counter(d for _, d in hs if d > 0).most_common(6))})")
    # misreads: a value that changes and comes straight back within 3 frames
    for name, series in (("HP", hp), ("MP", mp), ("EXP", ex)):
        vals = [vv for _, vv in series]
        flick = sum(1 for i in range(1, len(vals) - 2) if vals[i] != vals[i - 1] and vals[i - 1] in vals[i + 1:i + 3])
        print(f"   {name}: values that change and come straight back within 2 frames (a misread): {flick}")


if __name__ == "__main__":
    main()
