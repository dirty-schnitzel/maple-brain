"""Tracker plan, Part 2: WHAT EACH PART OF THE PROTOTYPE BUYS. proto_mobs.py run with one setting changed at a
time, each over the same captures, one line of numbers per setting (several at once, one process each).

    python tools/perc/track/ablate.py [--caps short|sound|CAP ...] [--jobs 6] [--only NAME ...]

`short` = the 12 sound captures without the 30-minute one (the default: minutes instead of half an hour).
Columns: found %, id kept across a cover % (all / 0.6-1.5 s / 1.5-4 s), one id for life % (all / not counting a
change beside another mob of its kind), extra ids, frames remembered in view and the share of them that ended
with the mob seen again, ms a frame in Python (p50).
"""
import argparse
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache  # noqa: E402

SETTINGS = {
    "the prototype": {},
    "timers instead of the possible set": {"evidence": False},
    "mob speed as the v83 rule (x1)": {"speed_x": 1.0},
    "no look-alike feet": {"feet_fix": False},
    "facing not in the cost": {"facing_cost": 0.0},
    "limits 2 s": {"drawn_s": 2.0, "offscreen_s": 2.0},
    "limit 8 s when drawn over": {"drawn_s": 8.0},
    "limit 1 s when drawn over": {"drawn_s": 1.0},
    "absent at 25 % of the core": {"abs_share": 0.25},
    "absent at 60 % of the core": {"abs_share": 0.6},
    "every sighting is a mob at once": {"solid_seen": 0.0, "solid_on": 0.0},
    "world.py's edge rule (60 % on screen)": {"edge_new": 0.6},
    "first set half width 70 px": {"knock": 70.0},
    "no cost for a remembered track": {"remembered_cost": 0.0},
}


def one(job):
    name, kv, caps = job
    import proto_mobs as P
    import score as S
    from load import ticks
    cfg = P.Cfg()
    for k, v in kv.items():
        setattr(cfg, k, v)
    ss, fs, rems, ms = [], [], [], []
    for cap in caps:
        tk = ticks(cap)
        ch = cache.chains(cap, tk)
        rows, trk, m = P.run(cap, cfg)
        ss.append(S.score(tk, ch, rows, S.me_fn(tk)))
        fs.append(P.sticky(tk, ch, rows))
        rems += trk.rem
        ms.append(m)
    s, f = S.merge(ss), P.merge_sticky(fs)
    g = f["gaps"]

    def held(lo, hi):
        b = [h for d, h in g if lo < d <= hi]
        return 100 * np.mean(b) if b else float("nan")
    sw, sc = np.array(f["sw"]), np.array(f["sw_clear"])
    rin = Counter()
    for x in rems:
        rin["again" if x[1] == "seen again" else "other"] += x[4]
    tot = max(1, sum(rin.values()))
    return (name, 100 * s["found"][1] / max(1, s["found"][0]), held(0, 99), held(0.6, 1.5), held(1.5, 99),
            100 * np.mean(sw == 0), 100 * np.mean(sc == 0), int(sw.sum()), int(sc.sum()), sum(rin.values()),
            100 * rin["again"] / tot, float(np.percentile(np.concatenate(ms), 50)),
            100 * s["ghost"][1] / max(1, s["ghost"][0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", nargs="*", default=["short"])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    caps = cache.SOUND[1:] if a.caps == ["short"] else cache.SOUND if a.caps == ["sound"] else a.caps
    names = [n for n in SETTINGS if a.only is None or any(o.lower() in n.lower() for o in a.only)]
    print(f"{len(caps)} captures; settings: {len(names)}")
    print(f"{'setting':40s} found  held  .6-1.5 1.5-4  one-id  (clear)  extra (clear)  remembered-in-view  seen-again  ms p50  ghost%")
    with Pool(a.jobs) as pool:
        for r in pool.imap(one, [(n, SETTINGS[n], caps) for n in names]):
            print(f"{r[0]:40s} {r[1]:5.1f} {r[2]:5.1f} {r[3]:6.1f} {r[4]:5.1f}  {r[5]:6.1f}  {r[6]:6.1f}  {r[7]:6d} {r[8]:6d}  {r[9]:10d}  {r[10]:9.1f}  {r[11]:6.2f}  {r[12]:5.2f}", flush=True)


if __name__ == "__main__":
    main()
