"""Reach of our attack, measured on a recording: for every attack press (Keys.swing_keys), the screen offset (dx in front,
dy = mob feet - our feet, y down) of each mob that turned hit/dying 0.15..0.9 s later (HIT) vs mobs that stayed
live (MISS: out of reach, or not reached by a 1-mob skill). Screen px on both sides -> no camera error.
usage: reach.py RUN [--keys KEY,KEY]"""
import bisect
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # run as a plain script too
from maplebrain.config import Keys


def main(run, keys=Keys().swing_keys):
    ticks = [json.loads(x) for x in open(f"{run}/ticks.jsonl")]
    kl = [json.loads(x) for x in open(f"{run}/keys.jsonl")]
    att = [k["t"] for k in kl if k["key"] in keys and k["down"]]
    turns = [(k["t"], k["key"]) for k in kl if k["key"] in ("left", "right") and k["down"]]
    tt = [t for t, _ in turns]
    T = [r["obs"]["t"] for r in ticks]

    def facing(t):
        i = bisect.bisect_right(tt, t)
        return turns[i - 1][1] if i else None

    hist = collections.defaultdict(list)                 # id -> [(t, state)]
    for r in ticks:
        for m in r["obs"].get("mobs") or []:
            hist[m["id"]].append((r["obs"]["t"], m["state"]))
    hit, miss = [], []
    for ta in att:
        i = bisect.bisect_left(T, ta)
        if i >= len(ticks):
            break
        o = ticks[i]["obs"]
        me, f = o.get("me"), facing(ta)
        if me is None or f is None:
            continue
        sgn = 1 if f == "right" else -1
        for m in o.get("mobs") or []:
            if m.get("kind") != "mob" or m["state"] not in ("live", "hit") or m.get("sx") is None:
                continue
            dx, dy = sgn * (m["sx"] - me[0]), m["sy"] - me[1]
            if abs(dx) > 220 or abs(dy) > 150:
                continue
            later = [s for t, s in hist[m["id"]] if ta + 0.15 <= t <= ta + 0.9]
            (hit if any(s in ("hit", "dying") for s in later) else miss).append((round(dx), round(dy)))
    print(f"{len(att)} presses; mobs within 220 px: HIT {len(hit)}  no reaction {len(miss)}")
    same = lambda v: [x for x, y in v if abs(y) <= 30]
    h, m = sorted(same(hit)), sorted(same(miss))
    q = lambda v, p: v[min(len(v) - 1, int(p * len(v)))] if v else None
    print("same level (|dy| <= 30): HIT dx p5/p10/p50/p90/p95", [q(h, p) for p in (.05, .1, .5, .9, .95)])
    print("histogram dx (20 px bins): bin hit / no-reaction  -> share hit")
    hb, mb = collections.Counter(x // 20 * 20 for x in h), collections.Counter(x // 20 * 20 for x in m)
    for b in range(-200, 220, 20):
        if hb[b] or mb[b]:
            print(f"  {b:5d} {hb[b]:4d} {mb[b]:4d}  {hb[b] / (hb[b] + mb[b]):.2f}")
    print("dy of HITs (any dx in 0..150): p5/p50/p95",
          [q(sorted(y for x, y in hit if 0 <= x <= 150), p) for p in (.05, .5, .95)])


if __name__ == "__main__":
    a = sys.argv[1:]
    k = a[a.index("--keys") + 1].split(",") if "--keys" in a else Keys().swing_keys
    main(a[0], tuple(k))
